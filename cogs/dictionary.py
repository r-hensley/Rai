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
        timeout = 60
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

    async def fetch_rae_data(self, formatted_word: str):
        url = f"https://dle.rae.es/{formatted_word}/"
        headers = OrderedDict({
            'Host': "dle.rae.es",
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0'
        })
        req = Request(url, headers=headers)
        urlopen_task = utils.asyncio_task(urlopen, req)
        resp = await urlopen_task
        webpage = resp.read()
        soup = BeautifulSoup(webpage, "html5lib")
        articles = soup.find_all('article', class_="o-main__article")

        # in headers: <meta name="rights" content="Real Academia Española © Todos los derechos reservados">
        copyright_text = resp.headers.get("rights", "Real Academia Española © Todos los derechos reservados")

        return articles, url, copyright_text

    @commands.command(aliases=['rae'])
    async def get_rae_def_results(self, ctx, *, word: str):
        """
        Look up definitions of a word from the Real Academia Española dictionary.
        - Example usage: `;rae libro`.
        
        This is a command developed by `@jobcuenca`. For inquiries, suggestions, and problem reports,
        you can contact him through the provided Discord account.
        
        -------
        Buscar definiciones de palabras del Diccionario de la Real Academia Española.
        - Ejemplo de uso: `;rae libro`.
        
        Este comando fue desarrollado por `@jobcuenca`. Para consultas, sugerencias y reportes de problemas,
        puedes contactarlo a través de la cuenta de Discord proporcionada.
        """
        logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

        # noinspection PyUnresolvedReferences
        formatted_word = urllib.parse.quote(word)  # Convert text to a URL-supported format
        articles, url, copyright_text = await self.fetch_rae_data(formatted_word)

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

        embeds = []

        for article in articles:
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
            for definition_item in (definitions_list.find_all("li", class_=["j", "j1", "j2", "j3", "j4", "j5", "j6", "l2"])):
                definition_text = ' '.join(definition_item.stripped_strings)
                # Remove extra spaces before periods and commas
                definition_text = re.sub(r'\s+([.,)|])', r'\1', definition_text)
                definitions.append(definition_text)

            # Split an article into multiple pages/embeds if the number of entries exceeds 10
            chunk_size = 10
            chunks = [definitions[i:i + chunk_size] for i in range(0, len(definitions), chunk_size)]

            for i, chunk in enumerate(chunks):
                description = "\n".join(chunk)
                embed = discord.Embed(
                    title=title,
                    url=url,
                    description=description,
                    color=discord.Color.blue()
                )
                embeds.append(embed)

        await self.send_embeds(ctx, embeds, copyright_text)

    @commands.command(aliases=['raeexp'])
    async def get_rae_exp_results(self, ctx, *, word: str):
        """
        Look up expressions of a word from the Real Academia Española dictionary.
        - Example usage: `;raeexp libro`.

        This is a command developed by `@jobcuenca`. For inquiries, suggestions, and problem reports,
        you can contact him through the provided Discord account.

        -------
        Buscar expresiones de palabras del Diccionario de la Real Academia Española.
        - Ejemplo de uso: `;raeexp libro`.

        Este comando fue desarrollado por `@jobcuenca`. Para consultas, sugerencias y reportes de problemas,
        puedes contactarlo a través de la cuenta de Discord proporcionada.
        """
        #logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

        # noinspection PyUnresolvedReferences
        formatted_word = urllib.parse.quote(word)  # Convert text to a URL-supported format
        articles, url, copyright_text = await self.fetch_rae_data(formatted_word)

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

        embeds = []
        has_expressions = False

        for article in articles:

            title = article.find("h1", class_="c-page-header__title").text.strip()
            expressions = {}

            # Find all elements with the 'h' class (They're example sentences)
            examples = article.find_all("span", class_="h")
            # Directly wrap the content with asterisks to italicize it
            for example in examples:
                example_text = example.get_text(strip=False)
                example.string = f"*{example_text}*"

            # Find all h3 tags containing expressions
            h3_tags = article.find_all("h3", class_=["k5", "k6", "l2"])

            # Iterate through each h3 tag to get definitions
            for h3 in h3_tags:
                has_expressions = True
                expression = h3.text.strip()
                definition = h3.find_next_sibling("ol")
                if definition:
                    definitions = [li.text.strip() for li in definition.find_all("li", class_="m")]
                    expressions[expression] = definitions

            # Split an article into multiple pages/embeds if the number of entries exceeds 10
            chunk_size = 6
            chunks = [list(expressions.items())[i:i + chunk_size] for i in range(0, len(expressions), chunk_size)]

            for chunk in chunks:
                description = ""
                for expression, definitions in chunk:
                    description += f"**{expression}**\n"
                    for definition in definitions:
                        description += f"{definition}\n"

                embed = discord.Embed(
                    title=title,
                    url=url,
                    description=description,
                    color=discord.Color.blue()
                )
                embeds.append(embed)

        # Check if there are expressions for the word
        if not has_expressions:
            embedded_error = discord.Embed(
                title="Palabra sin expresiones disponibles",
                description=f'La palabra `{word}` no tiene expresiones disponibles en el diccionario.',
                color=0xFF5733
            )
            await utils.safe_reply(ctx, embed=embedded_error)
            return

        await self.send_embeds(ctx, embeds, copyright_text)

    @commands.command(aliases=['raesin'])
    async def get_rae_syn_results(self, ctx, *, word: str):
        """
        Look up synonyms of a word from the Real Academia Española dictionary.
        - Example usage: `;raesin llamar`.

        This is a command developed by `@jobcuenca`. For inquiries, suggestions, and problem reports,
        you can contact him through the provided Discord account.

        -------
        Buscar sinónimos de palabras del Diccionario de la Real Academia Española.
        - Ejemplo de uso: `;raesin llamar`.

        Este comando fue desarrollado por `@jobcuenca`. Para consultas, sugerencias y reportes de problemas,
        puedes contactarlo a través de la cuenta de Discord proporcionada.
        """
        logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

        # noinspection PyUnresolvedReferences
        formatted_word = urllib.parse.quote(word)  # Convert text to a URL-supported format
        articles, url, copyright_text = await self.fetch_rae_data(formatted_word)

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

        embeds = []
        has_synonyms = False
        has_antonyms = False

        for article in articles:
            synonyms = []
            title = article.find("h1", class_="c-page-header__title").text.strip()

            # Find all tags containing synonyms
            synonyms_section = article.find("section", class_=["c-section"], id=re.compile("^sinonimos"))

            if synonyms_section:
                synonyms_ul_tag = synonyms_section.find("ul", class_=["c-related-words"])
                if synonyms_ul_tag:
                    has_synonyms = True
                    synonym_lists = synonyms_ul_tag.find_all("li")
                    for synonym_list in synonym_lists:
                        synonym_text = ' '.join(synonym_list.stripped_strings)
                        # Remove extra spaces before periods and commas
                        synonym_text = re.sub(r'\s+([.,)|])', r'\1', synonym_text)
                        synonyms.append(f'- {synonym_text}')

            # Split an article into multiple pages/embeds if the number of entries exceeds 10
            chunk_size = 10
            chunks = [synonyms[i:i + chunk_size] for i in range(0, len(synonyms), chunk_size)]

            for chunk in chunks:
                description = "\n".join(chunk)
                embed = discord.Embed(
                    title=title,
                    url=url,
                    description=f'**Sinónimos**: \n{description}',
                    color=discord.Color.blue()
                )
                embeds.append(embed)

        # Check if there are synonyms for the word
        if not has_synonyms:
            embedded_error = discord.Embed(
                title="Palabra sin sinónimos disponibles",
                description=f'La palabra `{word}` no tiene sinónimos disponibles en el diccionario.',
                color=0xFF5733
            )
            await utils.safe_reply(ctx, embed=embedded_error)
            return

        await self.send_embeds(ctx, embeds, copyright_text)


    @commands.command(aliases=['raeant'])
    async def get_rae_ant_results(self, ctx, *, word: str):
        """
        Look up antonyms of a word from the Real Academia Española dictionary.
        - Example usage: `;raeant hacer`.

        This is a command developed by `@jobcuenca`. For inquiries, suggestions, and problem reports,
        you can contact him through the provided Discord account.

        -------
        Buscar antónimos de palabras del Diccionario de la Real Academia Española.
        - Ejemplo de uso: `;raeant hacer`.

        Este comando fue desarrollado por `@jobcuenca`. Para consultas, sugerencias y reportes de problemas,
        puedes contactarlo a través de la cuenta de Discord proporcionada.
        """
        logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

        # noinspection PyUnresolvedReferences
        formatted_word = urllib.parse.quote(word)  # Convert text to a URL-supported format
        articles, url, copyright_text = await self.fetch_rae_data(formatted_word)

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

        embeds = []
        has_antonyms = False

        for article in articles:
            antonyms = []
            title = article.find("h1", class_="c-page-header__title").text.strip()

            # Find all tags containing antonyms
            antonyms_section = article.find("section", class_=["c-section"], id=re.compile("^antonimos"))
            if antonyms_section:
                antonyms_ul_tag = antonyms_section.find("ul", class_=["c-related-words"])
                if antonyms_ul_tag:
                    has_antonyms = True
                    antonym_lists = antonyms_ul_tag.find_all("li")
                    for antonym_list in antonym_lists:
                        antonym_text = ' '.join(antonym_list.stripped_strings)
                        # Remove extra spaces before periods and commas
                        antonym_text = re.sub(r'\s+([.,)|])', r'\1', antonym_text)
                        antonyms.append(f'- {antonym_text}')

            # Split an article into multiple pages/embeds if the number of entries exceeds 10
            chunk_size = 10
            chunks = [antonyms[i:i + chunk_size] for i in range(0, len(antonyms), chunk_size)]

            for chunk in chunks:
                description = "\n".join(chunk)
                embed = discord.Embed(
                    title=title,
                    url=url,
                    description=f'**Antónimos**: \n{description}',
                    color=discord.Color.blue()
                )
                embeds.append(embed)

        # Check if there are antonyms for the word
        if not has_antonyms:
            embedded_error = discord.Embed(
                title="Palabra sin antónimos disponibles",
                description=f'La palabra `{word}` no tiene antónimos disponibles en el diccionario.',
                color=0xFF5733
            )
            await utils.safe_reply(ctx, embed=embedded_error)
            return

        await self.send_embeds(ctx, embeds, copyright_text)

async def setup(bot):
    await bot.add_cog(Dictionary(bot))
