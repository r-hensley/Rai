import discord
from discord.ext import commands
import os
import urllib.parse
import aiohttp
from dotenv import load_dotenv

# Load env vars once at startup, not every time a command runs
load_dotenv()

class PaginationView(discord.ui.View):
    def __init__(self, author, has_definitions, embeds):
        timeout = 60 if has_definitions else 15

        super().__init__(timeout=timeout)
        self.author = author
        self.embeds = embeds
        self.current_page = 0
        self.total_pages = len(embeds)
        self.has_definitions = has_definitions
        self.update_buttons()

        if not self.has_definitions:
            self.remove_item(self.children[2])
            self.remove_item(self.children[1])
            self.remove_item(self.children[0])

    def update_buttons(self):
        # Disable "◄" if on page 0
        self.children[0].disabled = self.current_page == 0
        # Update page indicx    ator
        self.children[1].label = f"{self.current_page + 1}/{self.total_pages}"
        # Disable "►" if on the last page
        self.children[2].disabled = self.current_page == self.total_pages - 1

    @discord.ui.button(label="◄", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("You cannot control this menu.\nNo puedes interactuar con este menú", ephemeral=True)
        
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.gray, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="►", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("You cannot control this menu.\nNo puedes interactuar con este menú", ephemeral=True)

        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label="✖", style=discord.ButtonStyle.red)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()

    async def on_timeout(self) -> None:
        if self.message: 
            try:
                if not self.has_definitions:
                    await self.message.delete()
                else:
                    await self.message.edit(view=None)
            except discord.NotFound:
                pass
        self.stop()

class MerriamWebster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collegiate_key = os.getenv('ENG_DICT_API_KEY')
        self.thesaurus_key = os.getenv('ENG_THES_API_KEY')
        self.footer_text = "Merriam-Webster Dictionary | Command by @jobcuenca\nFEATURE IN EARLY DEVELOPMENT. Ping the developer for suggestions or issues."

    async def fetch_definitions(self, word, dict_type):
        # 1. Determine which key and reference to use
        if dict_type == "the":
            full_dict_type = "thesaurus"
            key = self.thesaurus_key
            ref = "thesaurus"
        else:
            full_dict_type = "dictionary"
            key = self.collegiate_key
            ref = "collegiate"

        if not key:
            print(f"Error: Missing API key for {dict_type}")
            return []

        safe_word = urllib.parse.quote(word)
        url = f"https://www.dictionaryapi.com/api/v3/references/{ref}/json/{safe_word}?key={key}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    embeds = []

                    if not data:
                        return []

                    # API returns empty list or list of strings (suggestions) if word not found
                    if isinstance(data[0], str):
                        for i in range(0, len(data), 10):
                            # Slice a chunk of 10 suggestions
                            chunk = data[i : i + 10]
                            description = "\n".join([f"* {suggestion}" for suggestion in chunk])
                            
                            embed = discord.Embed(
                                title="No definitions found", 
                                description=f"No definitions found for **{word}** in the {full_dict_type} dictionary.\n\n**Did you mean:**\n{description}",
                                color=discord.Color.red()
                            )
                            embed.set_footer(text=self.footer_text)
                            embeds.append(embed) 
                        
                        return embeds

                    for i in range(0, len(data), 4):
                        chunk = data[i : i + 4]
                        description = ""
                        for entry in chunk:
                            meta = entry.get('meta', {})
                            headword = meta.get('id', word).split(':')[0]
                            
                            shortdefs = entry.get('shortdef', [])
                            defs_text = "\n".join([f"* {defn}" for defn in shortdefs]) if shortdefs else "No short definition found."
                            
                            # If thesaurus, get synonyms and antonyms
                            synonyms_text = ""
                            antonyms_text = ""
                            thesaurus_footnote = ""
                            if dict_type == "the":
                                thesaurus_footnote = "Note: Only the top 10 synonyms and antonyms are shown."
                                syn_lists = meta.get('syns', [])
                                ant_lists = meta.get('ants', [])
                                if syn_lists and len(syn_lists) > 0:
                                    # Get top 5 from the first list
                                    top_syns = syn_lists[0][:10] 
                                    synonyms_text = f"\n**Synonyms:** {', '.join(top_syns)}"
                                if ant_lists and len(ant_lists) > 0:
                                    # Get top 5 from the first list
                                    top_ants = ant_lists[0][:10] 
                                    antonyms_text = f"\n**Antonyms:** {', '.join(top_ants)}"

                            description += f"### {headword.capitalize()} ({entry.get('fl', 'unknown')}):\n{defs_text}{synonyms_text}{antonyms_text}\n"
                        
                        embed = discord.Embed(
                            title=f"{word.capitalize()}",
                            url=f"https://www.merriam-webster.com/{full_dict_type}/{safe_word}",
                            description=description.strip(),
                            color=discord.Color.blue()
                        )
                        embed.set_footer(text=f"{self.footer_text}\n{thesaurus_footnote}" if thesaurus_footnote else self.footer_text)
                        embeds.append(embed)
                    return embeds
        return []

    @commands.command(aliases=["web", "webster"])
    async def webster_dictionary(self, ctx, arg1: str, *, arg2: str = None):
        """
        Look up definitions of a word from the Merriam-Webster Dictionary.
        - Format: 
            Dictionary: `;web dic <word>` or `;web <word>`.
            Thesaurus: `;web the <word>`.
        - Example usage: `;web book`, `;web the happy`

        Note: Thesaurus only returns the top 10 synonyms and antonyms.

        This command developed by `@jobcuenca` is in **EARLY DEVELOPMENT**. For inquiries, suggestions, and problem reports,
        you can contact him through the provided Discord account.

        -------

        Buscar definiciones de palabras del Diccionario Merriam-Webster.
        - Formato:
            Diccionario: `;web dic <word>` or `;web <word>`.
            Tesauro: `;web the <word>`.
        - Ejemplo de uso: `;web book`, `;web the happy`

        Nota: El tesauro solo devuelve los 10 sinónimos y antónimos principales.

        Este comando desarrollado por `@jobcuenca` está en **DESARROLLO INICIAL**. Para consultas, sugerencias y reportes de problemas,
        puedes contactarlo a través de la cuenta de Discord proporcionada.
        """ 
        has_definitions = True
        valid_types = ["dic", "the"]
        
        # Check if the first argument is a dictionary type
        if arg1.lower() in valid_types:
            full_dict_type = "thesaurus" if arg1.lower() == "the" else "dictionary"
            dict_type = arg1.lower()
            word = arg2
        else:
            full_dict_type = "dictionary"
            dict_type = "dic" # Default to dictinionary/collegiate
            # Combine args back together if the user typed multiple words (e.g. "test drive")
            word = f"{arg1} {arg2}" if arg2 else arg1

        if not word:
            await ctx.send(
                """
                Incorrect command usage.
                - Format:
                    Dictionary: `;web dic <word>` or `;web <word>`.
                    Thesaurus: `;web the <word>`.
                - Example usage: `;web book`
                -------
                Uso incorrecto del comando.
                - Formato:
                    Diccionario: `;web dic <word>` or `;web <word>`.
                    Tesauro: `;web the <word>`.
                - Ejemplo de uso: `;web book`.
                """
                )
            return

        # Pass dict_type explicitly to the function
        embeds = await self.fetch_definitions(word, dict_type)
        
        if not embeds:
            title = "No definitions found"
            description = f"No definitions found for **{word}** in the {full_dict_type} dictionary.\nPlease check the spelling or try another word."
            
            embed = discord.Embed(
                            title=title, 
                            description=description,
                            color=discord.Color.red()
                        )
            embed.set_footer(text=self.footer_text)
            has_definitions = False
            
            embeds.append(embed)
        
        view = PaginationView(ctx.author, has_definitions, embeds)
        message = await ctx.reply(embed=embeds[0], view=view)
        view.message = message

async def setup(bot):
    await bot.add_cog(MerriamWebster(bot))