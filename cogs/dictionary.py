import logging
import urllib

from collections import OrderedDict
from urllib.request import urlopen, Request

import discord
from bs4 import BeautifulSoup
from discord.ext import commands

from cogs.utils.BotUtils import bot_utils as utils

class Dictionary(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
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
        word = urllib.parse.quote(word)  # Convert text to a URL-supported format
        url = f"https://dle.rae.es/{word}/"
        headers = OrderedDict({
            'Host': "dle.rae.es",
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0'
        })
        req = Request(url, headers=headers)
        urlopen_task = utils.asyncio_task(urlopen, req)
        resp = await urlopen_task
        webpage = resp.read()
        soup = BeautifulSoup(webpage, "lxml")

        # Check if the word exists by looking for the main article
        if soup:
            main_article = soup.find("article",
                                     class_="o-main__article")
            if not main_article:
                embedded_error = discord.Embed(
                    title="Palabra no encontrada",
                    description=f'La palabra `{word}` no existe en el diccionario. '
                                f'Por favor verifique que la palabra esté escrita correctamente.',
                    color=0xFF5733
                )
                await utils.safe_reply(ctx, embed=embedded_error)
                return

        article = soup.find("article")
        title = article.find("h1", class_="c-page-header__title").text.strip()
        definitions = []
        # in headers: <meta name="rights" content="Real Academia Española © Todos los derechos reservados">
        copyright_text = resp.headers.get("rights", "Real Academia Española © Todos los derechos reservados")

        # Find the ordered list containing definitions
        definitions_list = article.find("ol", class_="c-definitions")

        # Remove the entire footer section (with synonyms, etc.)
        footer = article.find_all("div", class_="c-definitions__item-footer")
        for footer_item in footer:
            footer_item.decompose()

        # Remove the examples (to be fixed)
        examples = article.find_all("span", class_="h")
        for example in examples:
            example.decompose()

        # Iterate through each list item
        for i, definition_item in enumerate(
                definitions_list.find_all("li", class_=["j", "j1", "j2", "j3", "j4", "j5", "j6", "l2"]),
                start=1):
            abbr = definition_item.find_all("abbr", class_=["g", "d", "c"])
            # Exclude specific titles
            filtered_abbr = [
                ab for ab in abbr
                if not any(ab.get("title", "").startswith(exclude) for exclude in
                           ["usado también como", "Usado también como", "usado más como", "Usado más como",
                            "Por extensión", "por extensión", "Aplicado a", "aplicado a"])
            ]
            abbr_text = " ".join([ab.text.strip() for ab in filtered_abbr]) if filtered_abbr else ""

            # Remove the number before the definition
            numbers = definition_item.find_all("span", class_="n_acep")
            for number in numbers:
                number.decompose()

            # Extract the main definition text
            definition_text = str(i) + ". " + abbr_text + " " + " ".join(
                span.text.strip() for span in definition_item.find_all(["span", "a"])
            )

            definitions.append(definition_text + ".")

        final_result = "\n".join(definitions)

        embedded_result = discord.Embed(title=title, url=url,
                                        description=f'{final_result}',
                                        color=discord.Color.blue())
        
        embedded_result.set_footer(text=f"{copyright_text} | Command by jobcuenca",)

        await utils.safe_reply(ctx, embed=embedded_result)

async def setup(bot):
    await bot.add_cog(Dictionary(bot))
        
