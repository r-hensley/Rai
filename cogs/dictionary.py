import logging
import urllib

from collections import OrderedDict
from urllib.request import urlopen, Request

import discord
from bs4 import BeautifulSoup
from discord.ext import commands

import re
import asyncio

from cogs.utils.BotUtils import bot_utils as utils

# Silence asyncio warnings
logging.getLogger("asyncio").setLevel(logging.ERROR)

class Dictionary(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_embeds(self, ctx, embeds, copyright_text):
        timeout = 45
        if not embeds:
            return

        # Send the embed without any reactions if there is only a single page
        if len(embeds) == 1:
            embed = embeds[0]
            embed.set_footer(text=f"Página 1 de 1 | {copyright_text} | Comando de jobcuenca")
            message = await utils.safe_reply(ctx, embed=embed)

            await message.add_reaction("❌")  # Close/delete

            def check(reaction, reactor):
                return reactor == ctx.author and str(reaction.emoji) == "❌" and reaction.message.id == message.id

            while True:
                try:
                    reactions, user = await self.bot.wait_for("reaction_add", timeout=timeout, check=check)

                    # Remove user reaction to keep it clean
                    await message.remove_reaction(reactions.emoji, user)

                    if str(reactions.emoji) == "❌":
                        message = await message.delete()
                        return

                except asyncio.TimeoutError:
                    break

            # Clean up reactions after timeout
            await message.clear_reactions()
            return

        current_page = 0

        # Set footer for the first page
        embed = embeds[current_page]
        embed.set_footer(text=f"Página {current_page + 1} de {len(embeds)} | {copyright_text} | Comando de jobcuenca")

        message = await utils.safe_reply(ctx, embed=embeds[current_page])

        # Add navigation reactions
        await message.add_reaction("⬅️")  # Previous
        await message.add_reaction("➡️")  # Next
        await message.add_reaction("❌")  # Close/delete

        def check(reaction, reactor):
            return reactor == ctx.author and str(reaction.emoji) in ["⬅️", "➡️", "❌"] and reaction.message.id == message.id

        while True:
            try:
                reactions, user = await self.bot.wait_for("reaction_add", timeout=timeout, check=check)

                # Remove user reaction to keep it clean
                await message.remove_reaction(reactions.emoji, user)

                if str(reactions.emoji) == "⬅️" and current_page > 0:
                    current_page -= 1
                elif str(reactions.emoji) == "➡️" and current_page < len(embeds) - 1:
                    current_page += 1
                elif str(reactions.emoji) == "❌":
                    message = await message.delete()
                    return

                embed = embeds[current_page]

                # Update page number in footer
                embed.set_footer(
                    text=f"Página {current_page + 1} de {len(embeds)} | {copyright_text} | Comando de jobcuenca")

                await message.edit(embed=embeds[current_page])

            except asyncio.TimeoutError:
                break

        # Clean up reactions after timeout
        await message.clear_reactions()

    @commands.command(aliases=['rae'])
    async def get_rae_results(self, ctx, *, word: str):
        """
        Look up definitions of a word from the Real Academia Española dictionary.
        - Example usage: `j!rae libro`.
        
        This is a command developed by `@jobcuenca`. For inquiries, suggestions, and problem reports,
        you can contact him through the provided Discord account.
        
        -------
        Buscar definiciones de palabras del Diccionario de la Real Academia Española.
        - Ejemplo de uso: `j!rae libro`.
        
        Este comando fue desarrollado por `@jobcuenca`. Para consultas, sugerencias y reportes de problemas,
        puedes contactarlo a través de la cuenta de Discord proporcionada.
        """
        logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

        # noinspection PyUnresolvedReferences
        formatted_word = urllib.parse.quote(word)  # Convert text to a URL-supported format
        url = f"https://dle.rae.es/{formatted_word}/"
        headers = OrderedDict({
            'Host': "dle.rae.es",
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0'
        })
        req = Request(url, headers=headers)
        urlopen_task = utils.asyncio_task(urlopen, req)
        resp = await urlopen_task
        webpage = resp.read()
        soup = BeautifulSoup(webpage, "lxml")
        articles = soup.find_all('article', class_="o-main__article")

        # Check if the word exists by looking for the main article
        if not articles:
            embedded_error = discord.Embed(
                title="Palabra no encontrada",
                description=f'La palabra `{word}` no existe en el diccionario. '
                            f'Por favor verifique que la palabra esté escrita correctamente.',
                color=0xFF5733
            )
            await utils.safe_reply(ctx, embed=embedded_error)
            return

        # in headers: <meta name="rights" content="Real Academia Española © Todos los derechos reservados">
        copyright_text = resp.headers.get("rights", "Real Academia Española © Todos los derechos reservados")

        embeds = []

        for i, article in enumerate(articles, start=1):
            title = article.find("h1", class_="c-page-header__title").text.strip()
            definitions = []

            # Find the ordered list containing definitions
            definitions_list = article.find("ol", class_="c-definitions")

            # Remove the entire footer section (with synonyms, etc.)
            footer = article.find_all("div", class_="c-definitions__item-footer")
            for footer_item in footer:
                footer_item.decompose()

            # Find all elements with the 'h' class (They're example sentences)
            examples = article.find_all("span", class_="h")
            # Directly wrap the content with asterisks to italicize it
            for example in examples:
                example_text = example.get_text(strip=False)
                example.string = f"*{example_text}*"

                # Iterate through each list item
            for i, definition_item in enumerate(
                    definitions_list.find_all("li", class_=["j", "j1", "j2", "j3", "j4", "j5", "j6", "l2"]),
                    start=1):
                definition_text = ' '.join(definition_item.stripped_strings)
                # Remove extra spaces before periods and commas
                definition_text = re.sub(r'\s+([.,)|])', r'\1', definition_text)
                definitions.append(definition_text)

            final_result = "\n".join(definitions)

            embedded_result = discord.Embed(title=title, url=url,
                                            description=f'{final_result}',
                                            color=discord.Color.blue())

            embeds.append(embedded_result)

        await self.send_embeds(ctx, embeds, copyright_text)

async def setup(bot):
    await bot.add_cog(Dictionary(bot))
