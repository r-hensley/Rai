import re
import logging
import urllib

from collections import OrderedDict
from urllib.request import urlopen, Request

import discord
from bs4 import BeautifulSoup
from discord.ext import commands

from cogs.utils.BotUtils import bot_utils as utils

# Silence asyncio warnings
logging.getLogger("asyncio").setLevel(logging.ERROR)


class PaginationView(discord.ui.View):
    def __init__(self, embeds, author, caller_function, is_rae_def_available, is_rae_exp_available,
                 is_rae_syn_available, is_rae_ant_available, bot, ctx):
        super().__init__(timeout=60)
        self.bot = bot
        self.embeds = embeds
        self.author = author
        self.current_page = 0
        self.message = None
        self.word = None
        self.caller_function = caller_function
        self.is_rae_def_available = is_rae_def_available
        self.is_rae_exp_available = is_rae_exp_available
        self.is_rae_syn_available = is_rae_syn_available
        self.is_rae_ant_available = is_rae_ant_available
        self.ctx = ctx

        # Set initial buttons
        self.update_buttons()

    def update_buttons(self):
        button_mapping = {
            "get_rae_def_results": (self.rae_def_button, self.is_rae_def_available),
            "get_rae_exp_results": (self.rae_exp_button, self.is_rae_exp_available),
            "get_rae_syn_results": (self.rae_syn_button, self.is_rae_syn_available),
            "get_rae_ant_results": (self.rae_ant_button, self.is_rae_ant_available),
        }

        # Clear existing buttons
        self.clear_items()

        # Add navigation buttons
        self.add_item(self.prev_button)
        self.add_item(self.page_indicator)
        self.add_item(self.next_button)
        self.add_item(self.close_button)

        if not self.caller_function == 'check_article_availability':
            # Add RAE function buttons
            caller_button = button_mapping.get(self.caller_function)[0]

            for button, button_availability in button_mapping.values():
                button.row = 1
                button.disabled = not button_availability
                self.add_item(button)

                # If caller button, disable it and change colour to grey
                if button == caller_button:
                    caller_button.disabled = True
                    caller_button.style = discord.ButtonStyle.gray

        # Update button states
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="◄", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_embed(interaction)

    @discord.ui.button(label="✖", style=discord.ButtonStyle.red)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()

    @discord.ui.button(label="►", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await self.update_embed(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.gray, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Def", style=discord.ButtonStyle.green)
    async def rae_def_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        command = self.bot.get_command('get_rae_def_results')
        if command:
            await self.ctx.invoke(command, word=self.word)
        await interaction.message.delete()
        self.stop()

    @discord.ui.button(label="Exp", style=discord.ButtonStyle.green)
    async def rae_exp_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        command = self.bot.get_command('get_rae_exp_results')
        if command:
            await self.ctx.invoke(command, word=self.word)
        await interaction.message.delete()
        self.stop()

    @discord.ui.button(label="Sin", style=discord.ButtonStyle.green)
    async def rae_syn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        command = self.bot.get_command('get_rae_syn_results')
        if command:
            await self.ctx.invoke(command, word=self.word)
        await interaction.message.delete()
        self.stop()

    @discord.ui.button(label="Ant", style=discord.ButtonStyle.green)
    async def rae_ant_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        command = self.bot.get_command('get_rae_ant_results')
        if command:
            await self.ctx.invoke(command, word=self.word)
        await interaction.message.delete()
        self.stop()

    async def update_embed(self, interaction):
        # Update page indicator
        self.page_indicator.label = f"{self.current_page + 1}/{len(self.embeds)}"

        embed = self.embeds[self.current_page].copy()

        # Update buttons state
        self.update_buttons()

        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the original author to interact
        return interaction.user.id == self.author.id

    async def on_timeout(self) -> None:
        if self.message:
            try:
                # Remove all buttons after timeout
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
        self.stop()


class Dictionary(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.caller_function = None
        self.is_rae_def_available = False
        self.is_rae_exp_available = False
        self.is_rae_syn_available = False
        self.is_rae_ant_available = False
        self.superscript_characters = "⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᵠʳˢᵗᵘᵛʷˣʸᶻ"
        self.punctuation_without_spaces = "].,:)|»"
        self.definition_classes = ["j", "j1",
                                   "j2", "j3", "j4", "j5", "j6", "l2"]
        self.expression_classes = [
            "k1", "k2", "k3", "k4", "k5", "k6", "l1", "l2", "l3", "l4", "l5", "l6", "b"]

    async def send_embeds(self, ctx, embeds, formatted_word):
        if not embeds:
            return

        view = PaginationView(embeds, ctx.author, self.caller_function, self.is_rae_def_available, self.is_rae_exp_available,
                              self.is_rae_syn_available, self.is_rae_ant_available, self.bot, ctx)
        view.word = formatted_word

        # Prepare initial embed
        initial_embed = embeds[0].copy()

        # Update page indicator label
        view.page_indicator.label = f"1/{len(embeds)}"

        # Disable navigation buttons for single page embeds
        if len(embeds) == 1:
            view.prev_button.disabled = True
            view.next_button.disabled = True

        message = await utils.safe_reply(ctx, embed=initial_embed, view=view)
        view.message = message

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
        self.check_info_availability(articles)

        # in headers: <meta name="rights" content="Real Academia Española © Todos los derechos reservados">
        copyright_text = resp.headers.get(
            "rights", "Real Academia Española © Todos los derechos reservados")

        return articles, url, copyright_text, soup

    def check_info_availability(self, articles):
        # Reset availability status from previous calls
        self.reset_availability()
        for article in articles:
            # Check definition/etymology availability
            definition_section = article.find("ol", class_="c-definitions")
            intro_section = article.find(class_="c-text-intro")
            definition = None

            # Leave out intros that are part of expressions
            if intro_section:
                prev_el = intro_section.find_previous_sibling()
                while prev_el and not prev_el.name:
                    prev_el = prev_el.find_previous_sibling()
                
                if prev_el and prev_el.name == "h3":
                    intro_section = None
                    
            if definition_section:
                definition = definition_section.find(
                    "li", class_=self.definition_classes)

            if (definition or intro_section):
                self.is_rae_def_available = True
                
            # Check expression availability
            expression = article.find("h3", class_=self.expression_classes)
            if expression:
                self.is_rae_exp_available = True

            # Check synonym availability
            synonym_section = article.find(
                "section", class_=["c-section"], id=re.compile("^sinonimos"))
            if synonym_section:
                synonym = synonym_section.find(
                    "ul", class_=["c-related-words"])
                if synonym:
                    self.is_rae_syn_available = True

            # Check antonym availability
            antonym_section = article.find(
                "section", class_=["c-section"], id=re.compile("^antonimos"))
            if antonym_section:
                antonym = antonym_section.find(
                    "ul", class_=["c-related-words"])
                if antonym:
                    self.is_rae_ant_available = True

        return

    def reset_availability(self):
        self.is_rae_def_available = False
        self.is_rae_exp_available = False
        self.is_rae_syn_available = False
        self.is_rae_ant_available = False

    async def check_article_availability(self, ctx, word):
        # noinspection PyUnresolvedReferences
        # Convert text to a URL-supported format
        formatted_word = urllib.parse.quote(word)
        main_articles, url, copyright_text, soup = await self.fetch_rae_data(formatted_word)

        related_words = []
        embeds = []

        if not main_articles:
            self.caller_function = "check_article_availability"

            soup = self.format_article(soup)
            related_words_div = soup.find("div", class_="o-main__content")
            if related_words_div:
                related_words_articles = related_words_div.find_all("article")
                for article in related_words_articles:
                    related_words.append("- " +
                                         article.text.strip())

            if related_words:
                # Split an article into multiple pages/embeds if the number of related words exceeds 10
                chunk_size = 10
                chunks = [related_words[i:i + chunk_size]
                          for i in range(0, len(related_words), chunk_size)]

                new_line = '\n'  # my version of python can't have \n in f-string
                for chunk in chunks:
                    description = f'La palabra `{word}` no existe en el diccionario. Las entradas que se muestran a continuación podrían estar relacionadas:\n' \
                        f'{new_line.join(chunk)}'  # Join words in the chunk

                    embed = discord.Embed(
                        title="Palabra no encontrada",
                        description=description,
                        color=0xFF5733
                    )

                    embed.set_footer(
                        text=f'{copyright_text} | Comando hecho por jobcuenca')
                    embeds.append(embed)

                await self.send_embeds(ctx, embeds, formatted_word)
                return None, None, None, None

            embedded_error = discord.Embed(
                title="Palabra no encontrada",
                description=f'La palabra `{word}` no existe en el diccionario. '
                f'Por favor verifique que la palabra esté escrita correctamente.',
                color=0xFF5733
            )
            embedded_error.set_footer(
                text=f'{copyright_text} | Comando hecho por jobcuenca')

            await utils.safe_reply(ctx, embed=embedded_error, delete_after=5)
            return None, None, None, None

        return main_articles, url, copyright_text, formatted_word

    def trim_spaces_before_symbols(self, text):
        text = re.sub(
            r'\s+([' + re.escape(self.punctuation_without_spaces +
                                 self.superscript_characters) + '])', r'\1',
            text)
        return text

    async def handle_synonyms_antonyms(self, words_section, embeds, copyright_text, title, url):
        word_type = ""
        words = []
        if self.caller_function == "get_rae_syn_results":
            word_type = "Sinónimos"
        elif self.caller_function == "get_rae_ant_results":
            word_type = "Antónimos"

        if words_section:
            ul_tag = words_section.find("ul", class_=["c-related-words"])
            if ul_tag:
                lists = ul_tag.find_all("li")
                for lst in lists:
                    text = ' '.join(lst.stripped_strings)
                    # Remove extra spaces before periods and commas
                    text = self.trim_spaces_before_symbols(text)
                    words.append(f'- {text}')

        # Split an article into multiple pages/embeds if the number of entries exceeds 10
        chunk_size = 10
        chunks = [words[i:i + chunk_size]
                  for i in range(0, len(words), chunk_size)]

        for chunk in chunks:
            description = "\n".join(chunk)
            embed = discord.Embed(
                # title=title,
                # url=url,
                description=f'# [{title}]({url})\n**{word_type}**: \n{description}',
                color=discord.Color.blue()
            )
            embed.set_footer(
                text=f'{copyright_text} | Comando hecho por jobcuenca')
            embeds.append(embed)

        return embeds

    def to_superscript(self, article):
        superscript_map = str.maketrans(
            "0123456789abcdefghijklmnopqrstuvwxyz", self.superscript_characters)

        for sup_tag in article.find_all("sup"):
            sup_tag_text = sup_tag.string
            sup_tag.string = sup_tag_text.translate(superscript_map)
        return article

    def to_italicize(self, article):
        italic_tags = article.find_all(lambda tag:
                                       tag.name in ["em", "i"] or
                                       (tag.name == "span" and "h" in tag.get(
                                           "class", []))
                                       )
        if italic_tags:
            for italic_tag in italic_tags:
                italic_tag_text = italic_tag.get_text(strip=False)
                italic_tag.string = f"*{italic_tag_text}*"

        return article

    def to_bold(self, article):
        bold_tags = article.find_all(["b", "strong"])
        if bold_tags:
            for bold_tag in bold_tags:
                bold_tag_text = bold_tag.get_text(strip=False)
                bold_tag.string = f"**{bold_tag_text}**"

        return article

    def to_underline(self, article):
        underline_tags = article.find_all(lambda tag:
                                          (tag.name == "u") or (
                                              tag.name == "span" and "u" in tag.get("class", []))
                                          )

        if underline_tags:
            for underline_tag in underline_tags:
                underline_tag_text = underline_tag.get_text(strip=False)
                underline_tag.string = f"__{underline_tag_text}__"

        return article

    def to_hyperlink(self, article):
        link_tags = article.find_all(["a"], class_=["a"])
        if link_tags:
            for link_tag in link_tags:
                link_tag_text = link_tag.get_text(strip=False)
                link_tag.string = f"[{link_tag_text}](https://dle.rae.es{link_tag.get('href')})"

        return article

    def format_article(self, article):
        article = self.to_superscript(article)
        article = self.to_italicize(article)
        article = self.to_bold(article)
        article = self.to_underline(article)
        article = self.to_hyperlink(article)

        return article

    @commands.command(aliases=['rae', 'dle'])
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
        logging.basicConfig(level=logging.ERROR,
                            format="%(asctime)s - %(levelname)s - %(message)s")

        self.caller_function = "get_rae_def_results"

        articles, url, copyright_text, formatted_word = await self.check_article_availability(ctx, word)
        if not articles:
            return

        embeds = []

        if not self.is_rae_def_available:
            embedded_error = discord.Embed(
                title="Palabra sin definiciones disponibles",
                description=f'La palabra `{word}` no tiene definiciones disponibles en el diccionario.',
                color=0xFF5733
            )
            embeds.append(embedded_error)
            await self.send_embeds(ctx, embeds, formatted_word)
            return

        for article in articles:
            # Format words according to their HTML tag or class
            article = self.format_article(article)

            header = article.find("h1", class_="c-page-header__title")
            inner_header = article.find("header", class_="c-section__title")
            title = header.text.strip() if header else "No Title Found"

            intro_texts = []
            current_element = inner_header if inner_header else None
            # Iterate through next siblings
            if current_element:
                for sibling in current_element.find_next_siblings():
                    if "c-definitions" in sibling.get("class", []):
                        break
                    if sibling.find_previous_sibling().name == "h3":
                        break
                    if "c-text-intro" in sibling.get("class", []):
                        intro_texts.append(sibling.get_text().strip())
               

            intro_texts_with_newlines = ["-# " + text + "\n" for text in intro_texts]
            intro_texts_combined = ''.join(intro_texts_with_newlines)

            definitions = []

            # Find the ordered list containing definitions
            definitions_list = article.find("ol", class_="c-definitions")

            # Remove the entire footer section (with synonyms, etc.)
            footer = article.find_all(
                "div", class_="c-definitions__item-footer")
            for footer_item in footer:
                footer_item.decompose()

            if definitions_list:
                # Iterate through each list item
                for definition_item in (definitions_list.find_all("li", class_=self.definition_classes)):
                    definition_text = ' '.join(
                        definition_item.stripped_strings)
                    # Remove extra spaces before certain punctuation marks and superscript characters
                    definition_text = self.trim_spaces_before_symbols(
                        definition_text)
                    definitions.append(definition_text)

            # Split an article into multiple pages/embeds if the number of entries exceeds 10
            chunk_size = 10
            chunks = [definitions[i:i + chunk_size]
                      for i in range(0, len(definitions), chunk_size)]

            if chunks:
                for i, chunk in enumerate(chunks):
                    description = "\n".join(chunk)

                    # Include the intro texts only on the first page
                    if i == 0:
                        description = f'{intro_texts_combined + description}'
                    
                    embed = discord.Embed(
                        # title=title,
                        # url=url,
                        description=f'# [{title}]({url})\n{description}',
                        color=discord.Color.blue()
                    )
                    embed.set_footer(
                        text=f'{copyright_text} | Comando hecho por jobcuenca')
                    embeds.append(embed)
            elif intro_texts_combined:
                embed = discord.Embed(
                    # title=title,
                    # url=url,
                    description=f'# [{title}]({url})\n{intro_texts_combined}',
                    color=discord.Color.blue()
                )
                embed.set_footer(
                    text=f'{copyright_text} | Comando hecho por jobcuenca')
                embeds.append(embed)

        await self.send_embeds(ctx, embeds, formatted_word)

    @commands.command(aliases=['raeexp', 'dleexp'])
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
        logging.basicConfig(level=logging.ERROR,
                            format="%(asctime)s - %(levelname)s - %(message)s")

        self.caller_function = "get_rae_exp_results"

        articles, url, copyright_text, formatted_word = await self.check_article_availability(ctx, word)
        if not articles:
            return

        embeds = []

        if not self.is_rae_exp_available:
            embedded_error = discord.Embed(
                title="Palabra sin expresiones disponibles",
                description=f'La palabra `{word}` no tiene expresiones disponibles en el diccionario.',
                color=0xFF5733
            )
            embeds.append(embedded_error)
            await self.send_embeds(ctx, embeds, formatted_word)
            return

        for article in articles:
            article = self.format_article(article)

            title = article.find("h1", class_="c-page-header__title").text.strip()
            expressions = {}

            h3_tags = article.find_all("h3", class_=self.expression_classes)

            for h3 in h3_tags:
                expression = h3.text.strip()
                next_tag = h3.find_next_sibling()
                intro_text = None
                definition = None
                print(expression)

                if next_tag:
                    if next_tag.name == "div" and "c-text-intro" in next_tag.get("class", []):
                        intro_text = next_tag.text.strip() 
                        definition = next_tag.find_next_sibling("ol")
                    elif next_tag.name == "ol":
                        definition = next_tag
                    else:
                        pass
                    
                defs_list = []
                if definition:
                    defs_list = [li.text.strip() for li in definition.find_all("li", class_="m")]
                
                expressions[expression] = (intro_text, defs_list)

            # Chunking
            chunk_size = 6
            chunks = [list(expressions.items())[i:i + chunk_size]
                    for i in range(0, len(expressions), chunk_size)]
            
            for chunk in chunks:
                description = ""
                
                for expression, (current_intro, definitions) in chunk:
                    
                    if current_intro:
                        description += f"**{expression}**\n-# {current_intro}\n"
                    else:
                        description += f"**{expression}**\n"
                    
                    if definitions:
                        for definition in definitions:
                            description += f"{definition}\n"
                    
                    description = description + "\n"

                embed = discord.Embed(
                    # title=title,
                    # url=url,
                    description=f'# [{title}]({url})\n{description}',
                    color=discord.Color.blue()
                )
                embed.set_footer(
                    text=f'{copyright_text} | Comando hecho por jobcuenca')
                embeds.append(embed)

        await self.send_embeds(ctx, embeds, formatted_word)

    @commands.command(aliases=['raesin', 'dlesin'])
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
        logging.basicConfig(level=logging.ERROR,
                            format="%(asctime)s - %(levelname)s - %(message)s")

        self.caller_function = "get_rae_syn_results"

        articles, url, copyright_text, formatted_word = await self.check_article_availability(ctx, word)
        if not articles:
            return

        embeds = []

        if not self.is_rae_syn_available:
            embedded_error = discord.Embed(
                title="Palabra sin sinónimos disponibles",
                description=f'La palabra `{word}` no tiene sinónimos disponibles en el diccionario.',
                color=0xFF5733
            )
            embeds.append(embedded_error)
            await self.send_embeds(ctx, embeds, formatted_word)
            return

        for article in articles:
            article = self.to_superscript(article)
            title = article.find(
                "h1", class_="c-page-header__title").text.strip()

            # Find all tags containing synonyms
            synonyms_section = article.find(
                "section", class_=["c-section"], id=re.compile("^sinonimos"))
            embeds = await self.handle_synonyms_antonyms(synonyms_section, embeds, copyright_text, title, url)

        await self.send_embeds(ctx, embeds, formatted_word)

    @commands.command(aliases=['raeant', 'dleant'])
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
        logging.basicConfig(level=logging.ERROR,
                            format="%(asctime)s - %(levelname)s - %(message)s")

        self.caller_function = "get_rae_ant_results"

        articles, url, copyright_text, formatted_word = await self.check_article_availability(ctx, word)
        if not articles:
            return

        embeds = []

        if not self.is_rae_ant_available:
            embedded_error = discord.Embed(
                title="Palabra sin antónimos disponibles",
                description=f'La palabra `{word}` no tiene antónimos disponibles en el diccionario.',
                color=0xFF5733
            )
            embeds.append(embedded_error)
            await self.send_embeds(ctx, embeds, formatted_word)
            return

        for article in articles:
            article = self.to_superscript(article)
            title = article.find(
                "h1", class_="c-page-header__title").text.strip()

            # Find all tags containing antonyms
            antonyms_section = article.find(
                "section", class_=["c-section"], id=re.compile("^antonimos"))
            embeds = await self.handle_synonyms_antonyms(antonyms_section, embeds, copyright_text, title, url)

        await self.send_embeds(ctx, embeds, formatted_word)


async def setup(bot):
    await bot.add_cog(Dictionary(bot))
