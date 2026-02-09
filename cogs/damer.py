from typing import Optional
from urllib.parse import quote

import aiohttp
import html
import logging
import re

from enum import Enum
from lxml.html import HtmlElement, fromstring as from_html_string

import discord
from discord.ext import commands

from cogs.utils.BotUtils import bot_utils as utils


# Silence asyncio warnings
logging.getLogger("asyncio").setLevel(logging.ERROR)


class DamerMode(Enum):
    DEF = "def"
    EXP = "exp"
    SPFC = "specific phrase"


FORCED_TAB = u'\u3164\u3164'


class ExcepciónDNE(Exception):
    pass


class Aproximación:
    def __init__(self, término: str, normalizado: str, href: str):
        self.término = término or ''
        self.normalizado = normalizado or ''
        self.href = href or ''

    def __eq__(self, otro):
        if isinstance(otro, Aproximación):
            return (self.término == otro.término and
                    self.normalizado == otro.normalizado and
                    self.href == otro.href)
        return False

    def __str__(self):
        if self.href:
            return f'[{self.término}](https://www.asale.org/damer{self.href}) {self.normalizado}'
        else:
            return f'{self.término} ({self.normalizado})'


class Acepción:
    def __init__(self, índice_primario='', índice_secundario='', texto_entrada='', texto_entrada_raw=''):
        self.texto_entrada = (texto_entrada or '').strip()
        self.índice_primario = índice_primario or ''
        self.índice_secundario = índice_secundario or ''
        self.texto_entrada_raw = (texto_entrada_raw or '').strip()

    def __eq__(self, otro):
        if isinstance(otro, Acepción):
            return (self.texto_entrada == otro.texto_entrada
                    and self.texto_entrada_raw == otro.texto_entrada_raw
                    and self.índice_primario == otro.índice_primario
                    and self.índice_secundario == otro.índice_secundario)
        return False

    def __str__(self):
        if self.índice_primario:
            return f'{self.índice_primario}\n{FORCED_TAB}{self.índice_secundario} {self.texto_entrada}'
        return f'{FORCED_TAB}{self.índice_secundario} {self.texto_entrada}'


class Expresión:
    def __init__(self,
                 índice='',
                 texto_entrada='',
                 texto_entrada_raw='',
                 subsignificados: Optional[list[tuple[str, str]]] = None,
                 marcador=''):
        if subsignificados is None:
            subsignificados = []
        self.índice = índice or ''
        self.texto_entrada = (texto_entrada or '').strip()
        self.texto_entrada_raw = (texto_entrada_raw or '').strip()
        self.expresión = self.texto_entrada_raw.split('.')[0]
        self.subsignificados = subsignificados or []  # lista de tuple(índice, texto)
        self.marcador = marcador or ''

    def __eq__(self, otro):
        if isinstance(otro, Expresión):
            return (self.índice == otro.índice
                    and self.expresión == otro.expresión
                    and self.texto_entrada == otro.texto_entrada
                    and self.texto_entrada_raw == otro.texto_entrada_raw
                    and self.subsignificados == otro.subsignificados
                    and self.marcador == otro.marcador)
        return False

    def __str__(self):
        str_marcador = f'{self.marcador}\n' if self.marcador else ''
        if self.subsignificados:
            texto_subsignificados = f'\n{FORCED_TAB}{FORCED_TAB}'.join([f'{s[0]} {s[1]}' for s in self.subsignificados])
            return f'{str_marcador}{FORCED_TAB}{self.índice} {self.texto_entrada}\n{FORCED_TAB}{FORCED_TAB}{texto_subsignificados}'
        else:
            return f'{str_marcador}{FORCED_TAB}{self.índice} {self.texto_entrada}'

    def imprimir_sin_índices(self):
        if self.subsignificados:
            texto_subsignificados = f'\n{FORCED_TAB}'.join([f'{s[0]} {s[1]}' for s in self.subsignificados])
            return f'{self.texto_entrada}\n{FORCED_TAB}{texto_subsignificados}'
        else:
            return self.texto_entrada


class Entrada:
    def __init__(self, encabezado: str, etimología: str = '', acepciones: list[Acepción] = None, expresiones: list[Expresión] = None):
        self.encabezado = encabezado or ''
        self.etimología = etimología or ''
        self.acepciones = acepciones or []
        self.expresiones = expresiones or []

    def __eq__(self, otro):
        if isinstance(otro, Entrada):
            return (self.encabezado == otro.encabezado
                    and self.etimología == otro.etimología
                    and self.acepciones == otro.acepciones
                    and self.expresiones == otro.expresiones)
        return False

    def __str__(self):
        texto_acepciones = 'Acepciones:\n' + '\n'.join([str(a) for a in self.acepciones]) if self.acepciones else ''
        texto_expresiones = 'Expresiones:\n' + '\n'.join([str(e) for e in self.expresiones]) if self.expresiones else ''
        texto_etimología = f' {self.etimología}' if self.etimología else ''
        return f'{self.encabezado}{texto_etimología}\n{texto_acepciones}\n\n{texto_expresiones}\n'

    def busca_expresión(self, expresión: str) -> Expresión:
        if expresión:
            for expr in self.expresiones:
                if expr.expresión == expresión:
                    return expr
        return None


class Buscador:
    MAPA_ÍNDICES = {
        '0': u'\u2070',
        '1': u'\u00B9',
        '2': u'\u00B2',
        '3': u'\u00B3',
        '4': u'\u2074',
        '5': u'\u2075',
        '6': u'\u2076',
        '7': u'\u2077',
        '8': u'\u2078',
        '9': u'\u2079',
    }
    RE_NÚMEROS_ROMANOS = re.compile(r'^[IVXLCDM]+\.')
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0'
    TEXTO_COPYRIGHT = 'Diccionario de americanismos © 2010 | Asociación de Academias de la Lengua Española © Todos los derechos reservados'

    # Devuelve True si no hay resultados
    @staticmethod
    def verificar_dne(término: str, resultados_elem: HtmlElement) -> bool:
        if resultados_elem.text and resultados_elem.text.startswith('Aviso:'):
            for resultados_span in resultados_elem.iterchildren(tag='span'):
                if resultados_span.text and resultados_span.text.startswith('La palabra '):
                    for resultados_b in resultados_span.iterchildren(tag='b'):
                        if resultados_b.text == término:
                            return resultados_b.tail and resultados_b.tail.endswith('no está en el Diccionario.')
        return False

    # Devuelve una lista de aproximaciones
    @staticmethod
    def recoger_aproximaciones(_término: str,
                               resultados_elem: HtmlElement) -> list[Aproximación]:
        aproximaciones = []
        for aprox_elem in resultados_elem.iterfind('.//a[@data-acc="LISTA APROX"]'):
            texto = aprox_elem.text or ''
            if not texto:
                # Puede estar en itálica
                texto = aprox_elem.findtext('i') or ''
                if texto:
                    texto = f'_{texto}_'

            aproximación = Aproximación(
                html.unescape(texto or ''),
                html.unescape((aprox_elem.tail or '').strip()),
                html.unescape(aprox_elem.attrib.get('href', '')),
            )
            aproximaciones.append(aproximación)
        return aproximaciones

    @staticmethod
    def extraer_índices(fila_elem: HtmlElement, etimología: str = '') -> list[str]:
        # La cantidad de celdas vacías determina el formato de los índices
        cant_cel_vacías_inic = 0
        for celda_elem in fila_elem.iterchildren(tag='td'):
            if celda_elem.keys():
                break
            cant_cel_vacías_inic = cant_cel_vacías_inic + 1

        # Extrae los índices
        índ_primario = ''
        índ_secundario = ''
        índ_terciario = ''
        índ_elems = fila_elem.findall('.//td[@class="da7"]')
        if len(índ_elems) == 2:
            if cant_cel_vacías_inic == 1:
                índ_primario = (índ_elems[0].findtext('span') or '').strip()
                índ_secundario = (índ_elems[1].findtext('span') or '').strip()
            else:
                raise Exception('Formato inválido de índices')
        elif len(índ_elems) == 1:
            if cant_cel_vacías_inic == 1:
                índ_primario = (índ_elems[0].findtext('span') or '').strip()
            elif cant_cel_vacías_inic == 2:
                secundario_elem = índ_elems[0].find('span')
                índ_secundario = html.unescape(secundario_elem.text or '').strip()

                # Algunos índices tipo 'a.', 'b.', etc. llevan superíndices
                sup_elem = secundario_elem.find('sup')
                if sup_elem is not None:
                    texto_sup = html.unescape(sup_elem.text or '').strip()
                    if texto_sup:
                        texto_sup = ''.join([Buscador.MAPA_ÍNDICES.get(c, c) for c in texto_sup])
                    tail_sup = html.unescape(sup_elem.tail or '').strip()
                    índ_secundario = índ_secundario + texto_sup + tail_sup
            elif cant_cel_vacías_inic == 3:
                índ_terciario = (índ_elems[0].findtext('span') or '').strip()
            else:
                raise Exception('Formato inválido de índices')
        índ_primario = índ_primario.strip()
        if etimología and not índ_primario:
            índ_primario = etimología
        return [índ_primario, índ_secundario.strip(), índ_terciario.strip()]

    @staticmethod
    def extraer_y_combinar_textos(elem: HtmlElement,
                                  negrita=True,
                                  filtro_clases: set[str] = None) -> tuple[str, str]:
        fragmentos = []
        fragmentos_raw = []
        for text_elem in elem.iterchildren():
            clase_elem = text_elem.get('class')
            if filtro_clases and clase_elem and clase_elem not in filtro_clases:
                continue
            elem_tag = text_elem.tag
            if elem_tag not in ('a', 'span', 'i'):
                continue

            if elem_tag == 'i':
                # Ponlo en itálica
                en_itálica, en_itálica_raw = Buscador.extraer_y_combinar_textos(text_elem, filtro_clases=filtro_clases)
                if en_itálica:
                    if en_itálica.endswith(' '):
                        fragmentos.append(f'_{en_itálica.rstrip()}_ ')
                    else:
                        fragmentos.append(f'_{en_itálica}_')
                    fragmentos_raw.append(en_itálica_raw)
            else:
                fragmento = text_elem.text or ''
                if fragmento:
                    fragmento = html.unescape(fragmento)
                    if text_elem.get('class') == 'da3' and negrita:
                        # Ponlo en negrita
                        fragmentos.append(f'**{fragmento}**')
                    elif elem_tag == 'a' and text_elem.get('href'):
                        fragmentos.append(f'[{fragmento}](https://www.asale.org/damer/{text_elem.get("href")})')
                    else:
                        fragmentos.append(fragmento)
                    fragmentos_raw.append(fragmento)

            fragmento_tail = text_elem.tail or ''
            if fragmento_tail:
                fragmento_tail = html.unescape(fragmento_tail)
                fragmentos.append(fragmento_tail)
                fragmentos_raw.append(fragmento_tail)

        return ''.join(fragmentos), ''.join(fragmentos_raw)

    @staticmethod
    def extraer_texto_de_fila(fila_elem: HtmlElement) -> tuple[str, str]:
        fragmentos = []
        fragmentos_raw = []
        for celda_elem in fila_elem.iterchildren(tag='td'):
            if celda_elem.get('class') == 'da7':
                # Nos saltamos las celdas de índices
                continue

            # A veces las clasificaciones (adj., m., f., etc.) salen en el texto del elemento 'td'
            if celda_elem.text:
                # No queremos puro whitespace
                if celda_elem.text.strip():
                    texto_celda = html.unescape(celda_elem.text)
                    fragmentos.append(texto_celda)
                    fragmentos_raw.append(texto_celda)

            # Recoge todo el texto de los elementos, teniendo en cuenta si están en itálica, negrita, etc.
            texto_fila, texto_fila_raw = Buscador.extraer_y_combinar_textos(celda_elem)
            fragmentos.append(texto_fila)
            fragmentos_raw.append(texto_fila_raw)

        return ''.join(fragmentos).replace('.__', '. ').replace('__', ''), ''.join(fragmentos_raw)

    # Devuelve dos listas - la primera contiene acepciones y la segunda contiene expresiones
    @staticmethod
    def extraer_acepciones_expresiones(elem_entrada: HtmlElement) -> tuple[list[Acepción], list[Expresión]]:
        acepciones: list[Acepción] = []
        expresiones: list[Expresión] = []
        modo_expresiones = False
        expr_pendiente: Optional[Expresión] = None
        expr_subsignificados: list[tuple[str, str]] = []
        expr_marcador = ''
        índice_con_etim = ''  # índice primario con etimología
        for fila_elem in elem_entrada.iterfind('.//tr'):
            # Averigua si esta fila es para el encabezado o para la etimología
            es_encabezado = False
            es_etimología = False
            for celda_elem in fila_elem.iterchildren(tag='td'):
                if celda_elem.get('class') == 'da2':
                    if es_encabezado or es_etimología:
                        break
                    for span_elem in celda_elem.iterdescendants(tag='span'):
                        span_class = span_elem.get('class')
                        if span_class == 'da8':
                            es_encabezado = True
                            break
                        elif span_class in ('da3', 'da1'):
                            índice_con_etim += Buscador.extraer_y_combinar_textos(celda_elem, negrita=False)[0]
                            es_etimología = True
                            break
            if es_encabezado or es_etimología:
                continue

            índices = Buscador.extraer_índices(fila_elem, etimología=índice_con_etim)
            if índice_con_etim:
                índice_con_etim = ''  # solo le asignamos la etimología a la primera acepción

            # Las acepciones van primero, luego las expresiones
            if not modo_expresiones and índices[0] and not Buscador.RE_NÚMEROS_ROMANOS.match(índices[0]):
                modo_expresiones = True

            if modo_expresiones and índices[0] and not (índices[1] or índices[2]):
                # Marcador de expresiones
                expr_marcador = índices[0]

            # Extrae el texto de la entrada
            texto_entero, texto_entero_raw = Buscador.extraer_texto_de_fila(fila_elem)
            if modo_expresiones:
                if índices[1]:
                    # Nueva expresión - agrega la anterior a la lista si existe
                    if expr_pendiente is not None:
                        expr_pendiente.subsignificados = expr_subsignificados
                        expresiones.append(expr_pendiente)
                    expr_pendiente = Expresión(índices[1], texto_entrada=texto_entero, texto_entrada_raw=texto_entero_raw, marcador=expr_marcador)
                    expr_subsignificados = []
                    expr_marcador = ''
                elif índices[2]:
                    # Significado para la expresión pendiente
                    expr_subsignificados.append((índices[2], texto_entero))
                elif índices[0] == '▶':
                    # Fin de lista de expresiones con definiciones - agrega la anterior a la lista si existe
                    if expr_pendiente is not None:
                        expr_pendiente.subsignificados = expr_subsignificados
                        expresiones.append(expr_pendiente)
                    expresiones.append(Expresión(índices[0], texto_entrada=texto_entero, texto_entrada_raw=texto_entero_raw))
                    expr_pendiente = None
            elif texto_entero:
                acep = Acepción(índice_primario=índices[0], índice_secundario=índices[1], texto_entrada=texto_entero, texto_entrada_raw=texto_entero_raw)
                acepciones.append(acep)

        if expr_pendiente is not None:
            expr_pendiente.subsignificados = expr_subsignificados
            expresiones.append(expr_pendiente)
        return acepciones, expresiones

    # Extrae los resultados y devuelve las Entradas correspondientes
    # Lanza una ExcepciónDNE si no hay resultados.
    @staticmethod
    def parsear_resultados(término: str, raw_html: str) -> list[Entrada]:
        doc = from_html_string(raw_html)
        resultados = doc.xpath('//div[@class="bloque-txt" and @id="resultados"]')
        if not resultados:
            raise Exception('No se pudo analizar el documento: no se encontró ningún elemento con resultados.')
        resultados_el = resultados[0]

        # Verifica existencia de resultados
        if Buscador.verificar_dne(término, resultados_el):
            mensaje = f'Aviso: La palabra **{término}** no está en el Diccionario.'
            aproximaciones = Buscador.recoger_aproximaciones(término, resultados_el)
            if aproximaciones:
                mensaje += ' Las entradas que se muestran a continuación podrían estar relacionadas:\n'
            ret_str_parts = [mensaje]
            for aprox in aproximaciones:
                ret_str_parts.append(str(aprox))
            raise ExcepciónDNE('\n'.join(ret_str_parts))
        else:
            entradas = []
            for elem_entrada in resultados_el.iterfind('entry'):
                # Extrae las acepciones relevantes
                if término in html.unescape(elem_entrada.attrib.get('key', '')).split('|'):
                    # Extrae el encabezado (y la etimología primaria si existe)
                    encabezado, etimología_primaria = Buscador.extraer_encabezado_etimología(elem_entrada)
                    if not encabezado:
                        raise Exception('No se encontró ningún elemento de encabezado.')
                    acepciones, expresiones = Buscador.extraer_acepciones_expresiones(elem_entrada)
                    if not (acepciones or expresiones):
                        raise Exception('No se extrajo ninguna acepción/expresión.')
                    entradas.append(Entrada(encabezado, etimología_primaria, acepciones, expresiones))
            return entradas

    @staticmethod
    def extraer_encabezado_etimología(elem_entrada: HtmlElement) -> tuple[str, str]:
        # La primera fila de la tabla contiene el encabezado y la etimología primaria
        elem_tabla = elem_entrada.find('table')
        if elem_tabla is None:
            return '', ''
        elem_encabezado = elem_tabla.find('.//td[@class="da2"]')
        if elem_encabezado is None:
            return '', ''

        texto_encabezado, _ = Buscador.extraer_y_combinar_textos(elem_encabezado, filtro_clases={'da8'})
        etimología, _ = Buscador.extraer_y_combinar_textos(elem_encabezado, filtro_clases={'da1'})
        return (texto_encabezado.strip(), etimología.strip())

    @staticmethod
    async def búsqueda_damer(término: str) -> list[Entrada]:
        safe_term = quote(término, safe="")
        url_búsqueda = f"https://www.asale.org/damer/{safe_term}"
        async with aiohttp.ClientSession(headers={'User-Agent': Buscador.USER_AGENT}) as sesión:
            async with sesión.get(url_búsqueda) as resp:
                if resp.status != 200:
                    raise Exception(f'Búsqueda fallida para el término: {término}.')
                raw_html = await resp.text()
        return Buscador.parsear_resultados(término, raw_html)


class PaginationView(discord.ui.View):
    def __init__(self,
                 ctx: commands.Context,
                 embeds: list[discord.Embed],
                 author: discord.User | discord.Member,
                 caller_mode: DamerMode,
                 damer_def_available: bool,
                 damer_exp_available: bool,
                 gen_embeds_callback,
                 start_index: int = 0):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.bot: commands.Bot = self.ctx.bot
        self.embeds = embeds
        self.author = author
        self.word: str | None = None
        self.caller_mode = caller_mode
        self.damer_def_available = damer_def_available
        self.damer_exp_available = damer_exp_available
        self.gen_embeds_callback = gen_embeds_callback
        self.current_page = start_index
        if self.current_page < 0:
            self.current_page = 0
        elif self.current_page >= len(embeds):
            self.current_page = len(embeds) - 1

        self.message: Optional[discord.Message] = None  # set in DamerDictionary.send_embeds

        # Set initial buttons
        self.update_buttons()

    def update_buttons(self):
        button_mapping = {
            DamerMode.DEF: (self.damer_def_button, self.damer_def_available),
            DamerMode.EXP: (self.damer_exp_button, self.damer_exp_available),
        }

        # Clear existing buttons
        self.clear_items()

        # Add navigation buttons
        self.add_item(self.prev_button)
        self.add_item(self.page_indicator)
        self.add_item(self.next_button)
        self.add_item(self.close_button)
        if len(self.embeds) >= 10:
            self.seek_start_button.row = 1
            self.prev_button_x5.row = 1
            self.next_button_x5.row = 1
            self.seek_end_button.row = 1
            self.add_item(self.seek_start_button)
            self.add_item(self.prev_button_x5)
            self.add_item(self.next_button_x5)
            self.add_item(self.seek_end_button)

        # Add function buttons
        if self.caller_mode == DamerMode.DEF:
            caller_button = self.damer_def_button
        elif self.caller_mode == DamerMode.EXP:
            caller_button = self.damer_exp_button
        else:
            caller_button = None

        for button, button_availability in button_mapping.values():
            button.row = 1 if len(self.embeds) < 10 else 2
            button.disabled = not button_availability
            self.add_item(button)

            # If caller button, disable it and change colour to grey
            if caller_button and button == caller_button:
                caller_button.disabled = True
                caller_button.style = discord.ButtonStyle.gray

        # Update button states
        self.prev_button.disabled = self.prev_button_x5.disabled = self.seek_start_button.disabled = self.current_page == 0
        self.next_button.disabled = self.next_button_x5.disabled = self.seek_end_button.disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="◄", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_embed(interaction)

    @discord.ui.button(label="◄◄", style=discord.ButtonStyle.blurple)
    async def prev_button_x5(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 5
            if self.current_page < 0:
                self.current_page = 0
            await self.update_embed(interaction)

    @discord.ui.button(label="▮◄◄", style=discord.ButtonStyle.blurple)
    async def seek_start_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page = 0
            await self.update_embed(interaction)

    @discord.ui.button(label="✖", style=discord.ButtonStyle.red)
    async def close_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.message:
            await interaction.message.delete()
        self.stop()

    @discord.ui.button(label="►", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await self.update_embed(interaction)

    @discord.ui.button(label="►►▮", style=discord.ButtonStyle.blurple)
    async def seek_end_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page = len(self.embeds) - 1
            await self.update_embed(interaction)

    @discord.ui.button(label="►►", style=discord.ButtonStyle.blurple)
    async def next_button_x5(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 5
            if self.current_page >= len(self.embeds):
                self.current_page = len(self.embeds) - 1
            await self.update_embed(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.gray, disabled=True)
    async def page_indicator(self, _interaction: discord.Interaction, _button: discord.ui.Button):
        pass

    @discord.ui.button(label="Def", style=discord.ButtonStyle.green)
    async def damer_def_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.gen_embeds_callback(self.ctx, self.word, caller_mode=DamerMode.DEF)
        if interaction.message:
            await interaction.message.delete()
        self.stop()

    @discord.ui.button(label="Exp", style=discord.ButtonStyle.green)
    async def damer_exp_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.gen_embeds_callback(self.ctx, self.word, caller_mode=DamerMode.EXP)
        if interaction.message:
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


class DamerDictionary(commands.Cog):
    ENTRIES_PER_EMBED = 10

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger('damer')
        self.log.setLevel(logging.ERROR)

    async def send_embeds(self,
                          ctx: commands.Context,
                          embeds: list[discord.Embed],
                          lookup_word,
                          caller_mode: DamerMode,
                          damer_def_available=False,
                          damer_exp_available=False,
                          start_index: int = 0):
        if not embeds:
            return

        view = PaginationView(ctx,
                              embeds,
                              ctx.author,
                              caller_mode,
                              damer_def_available,
                              damer_exp_available,
                              gen_embeds_callback=self._generate_and_send_embeds,
                              start_index=start_index)
        view.word = lookup_word

        # Prepare initial embed
        initial_embed = embeds[start_index].copy()

        # Update page indicator label
        view.page_indicator.label = f'{start_index + 1}/{len(embeds)}'

        # Disable navigation buttons for single page embeds
        if len(embeds) == 1:
            view.prev_button.disabled = True
            view.next_button.disabled = True
            view.prev_button_x5.disabled = True
            view.next_button_x5.disabled = True
            view.seek_start_button.disabled = True
            view.seek_end_button.disabled = True

        message = await utils.safe_reply(ctx, embed=initial_embed, view=view)
        view.message = message

    def _get_embeds(self,
                    entradas: list[Entrada],
                    caller_mode: DamerMode,
                    lookup_word: str,
                    target_phrase: str = '') -> list[discord.Embed]:
        embeds = []
        for entrada in entradas:
            if caller_mode == DamerMode.SPFC:
                expr = entrada.busca_expresión(target_phrase)
                if expr:
                    specific_phrase_embed = discord.Embed(
                        title=entrada.encabezado,
                        url=f'https://www.asale.org/damer/{lookup_word}',
                        description=expr.imprimir_sin_índices(),
                        color=discord.Color.blue()
                    )
                    specific_phrase_embed.set_footer(text=f'{Buscador.TEXTO_COPYRIGHT} | Comando hecho por perkinql')
                    return [specific_phrase_embed]
            else:
                # Split an entry into multiple pages/embeds if the number of items exceeds 10
                to_iterate = entrada.expresiones if caller_mode == DamerMode.EXP else entrada.acepciones
                if to_iterate:
                    chunks = [to_iterate[i:i + self.ENTRIES_PER_EMBED]
                              for i in range(0, len(to_iterate), self.ENTRIES_PER_EMBED)]

                    for i, chunk in enumerate(chunks):
                        description = '\n'.join(str(acep) for acep in chunk)
                        if entrada.etimología and i == 0:
                            description = f'_{entrada.etimología}_\n\n{description}'

                        embed = discord.Embed(
                            title=entrada.encabezado,
                            url=f'https://www.asale.org/damer/{lookup_word}',
                            description=description,
                            color=discord.Color.blue()
                        )
                        embed.set_footer(text=f'{Buscador.TEXTO_COPYRIGHT} | Comando hecho por perkinql')
                        embeds.append(embed)

        if caller_mode == DamerMode.SPFC:
            embedded_error = discord.Embed(
                title="No se pudo encontrar la expresión solicitada.",
                description=f'La expresión solicitada no aparece en las entradas de {lookup_word}',
                color=0xFF5733
            )
            embedded_error.set_footer(text=f'{Buscador.TEXTO_COPYRIGHT} | Comando hecho por perkinql')
            return [embedded_error]
        return embeds

    async def _generate_and_send_embeds(self,
                                        ctx: commands.Context,
                                        lookup_term: str,
                                        caller_mode: DamerMode,
                                        entradas: list[Entrada] | None = None):
        lookup_parts = lookup_term.split()
        lookup_word = lookup_parts[0]
        target_phrase = ''

        # Check if we're looking up a specific phrase
        if len(lookup_parts) > 1:
            caller_mode = DamerMode.SPFC
            lookup_word, target_phrase = self._generate_target_word_and_phrase(lookup_parts)

        # get entries and handle exceptions
        try:
            if not entradas:
                entradas = await Buscador.búsqueda_damer(lookup_word)
        except ExcepciónDNE as e_dne:
            embedded_error = discord.Embed(
                title="Palabra sin entradas disponibles",
                description=str(e_dne),
                color=0xFF5733
            )
            embedded_error.set_footer(text=f'{Buscador.TEXTO_COPYRIGHT} | Comando hecho por perkinql')
            return await self.send_embeds(ctx, [embedded_error], lookup_word,
                                          caller_mode=caller_mode)

        except Exception as e:
            self.log.exception(f'El comando falló con la búsqueda: {lookup_term}.')
            embedded_error = discord.Embed(
                title="Chuta, algo salió mal.",
                description=str(e),
                color=0xFF5733
            )
            embedded_error.set_footer(text='Comando hecho por perkinql - avísenle')
            return await self.send_embeds(ctx, [embedded_error], lookup_word,
                                          caller_mode=caller_mode)

        # handle no entries found
        if not entradas:
            embedded_error = discord.Embed(
                title="Palabra sin definiciones disponibles",
                description=f'La palabra `{lookup_word}` no tiene entradas disponibles en el diccionario.',
                color=0xFF5733
            )
            embedded_error.set_footer(text=f'{Buscador.TEXTO_COPYRIGHT} | Comando hecho por perkinql')
            return await self.send_embeds(ctx,
                                          [embedded_error],
                                          lookup_word,
                                          caller_mode=caller_mode,)

        damer_def_available = any([e.acepciones for e in entradas])
        damer_exp_available = any([e.expresiones for e in entradas])

        # Handle case where only expressions are available and user requested definitions
        if caller_mode == DamerMode.DEF and not damer_def_available and damer_exp_available:
            return await self._generate_and_send_embeds(ctx, lookup_word, caller_mode=DamerMode.EXP,
                                                        entradas=entradas)
        elif caller_mode == DamerMode.EXP and not damer_exp_available:
            embed = discord.Embed(
                title="Palabra sin expresiones disponibles",
                description=f'La palabra `{lookup_word}` no tiene expresiones disponibles en el diccionario.',
                color=discord.Color.blue()
            )
            embed.set_footer(text=f'{Buscador.TEXTO_COPYRIGHT} | Comando hecho por perkinql')
            return await self.send_embeds(ctx, [embed], lookup_word,
                                          caller_mode=caller_mode,
                                          damer_def_available=damer_def_available)

        embeds = self._get_embeds(entradas, caller_mode, lookup_word, target_phrase)
        return await self.send_embeds(ctx, embeds, lookup_word,
                                      caller_mode=caller_mode,
                                      damer_def_available=damer_def_available,
                                      damer_exp_available=damer_exp_available)

    @commands.command(aliases=['damer'])
    async def get_damer_def_results(self, ctx, *, lookup_term: str):
        """
        Look up definitions of a word from the Diccionario de Americanismos from the ASALE.
        - Example usage: `;damer ñurdo`.

        This is a command developed by `@perkinql`. For inquiries, suggestions, complaints, and bug reports,
        you can contact him through the provided Discord account.
        -------
        Buscar definiciones de palabras del Diccionario de Americanismos de la ASALE.
        - Ejemplo de uso: `;rae ñurdo`.

        Este comando fue desarrollado por `@perkinql`. Para consultas, sugerencias, quejas y reportes de problemas,
        puedes contactarte con él a través de la cuenta de Discord proporcionada.
        """
        await self._generate_and_send_embeds(ctx, self._sanitize_input(lookup_term), caller_mode=DamerMode.DEF)

    @commands.command(aliases=['damerexp'])
    async def get_damer_exp_results(self, ctx, *, lookup_term: str):
        """
        Look up expressions of a word from the Diccionario de Americanismos from the ASALE.
        - Example usage: `;damerexp pronto`.

        This is a command developed by `@perkinql`. For inquiries, suggestions, complaints, and bug reports,
        you can contact him through the provided Discord account.
        -------
        Buscar expresiones de palabras del Diccionario de Americanismos de la ASALE.
        - Ejemplo de uso: `;damerexp pronto`.

        Este comando fue desarrollado por `@perkinql`. Para consultas, sugerencias, quejas y reportes de problemas,
        puedes contactarte con él a través de la cuenta de Discord proporcionada.
        """
        await self._generate_and_send_embeds(ctx, self._sanitize_input(lookup_term), caller_mode=DamerMode.EXP)

    @classmethod
    def _sanitize_input(cls, input: str) -> str:
        return re.sub(r'[^.,a-záéíóúüñ\-?!¿¡ ()]', '', input.strip().lower())

    @classmethod
    def _generate_target_word_and_phrase(cls, lookup_parts: list[str]) -> tuple[str, str]:
        '''
        Given the list of words to look up, returns the search term and the target expression
        to look for, if applicable.
        '''

        # Handle single word lookup
        if len(lookup_parts) == 1:
            # Handle edge cases like 'dársela'
            matches = re.match(r'^(.*[áéí]r)sel[aeo]s?$', lookup_parts[0])
            if matches and matches.groups():
                key_word = matches.groups()[0]
                if key_word.endswith('ár'):
                    key_word = re.sub(r'ár$', 'ar', key_word)
                elif key_word.endswith('ér'):
                    key_word = re.sub(r'ér$', 'er', key_word)
                elif key_word.endswith('ír'):
                    key_word = re.sub(r'ír$', 'ir', key_word)
                # Entries like 'dársela' don't replace the infinitive with ~
                return key_word, lookup_parts[0]
            return lookup_parts[0], ''

        # Skip non-key words
        non_key_words = {'no', 'que', 'ya', 'de', 'a', 'con', 'como', 'por', 'para', 'del', 'lo', 'la', 'los', 'las', 'el', 'como', 'al', 'todo'}
        key_index = -1
        for i, part in enumerate(lookup_parts):
            if part not in non_key_words:
                key_index = i
                break
        if key_index < 0:
            return '', ''

        base_part = lookup_parts[key_index]
        modified_parts = list(lookup_parts)

        # Handle direct object after infinitive (e.g. pasarlo, hacerles)
        matches = re.match(r'^(.*[aei]r)(l[aeo]s?)$', base_part)
        if matches and len(matches.groups()) == 2:
            key_word = matches.groups()[0]
            modified_parts[key_index] = f'~{matches.groups()[1]}'
            return key_word, ' '.join(modified_parts)

        # Handle pronominal (no object) (e.g. hacerse)
        matches = re.match(r'^(.*[aei]r)se$', base_part)
        if matches and matches.groups():
            key_word = matches.groups()[0]
            modified_parts[key_index] = '~se'
            return key_word, ' '.join(modified_parts)

        # Handle pronominal with object (e.g. pasárselo)
        matches = re.match(r'^(.*[áéí]r)sel[aeo]s?$', base_part)
        if matches and matches.groups():
            key_word = matches.groups()[0]
            if key_word.endswith('ár'):
                key_word = re.sub(r'ár$', 'ar', key_word)
            elif key_word.endswith('ér'):
                key_word = re.sub(r'ér$', 'er', key_word)
            elif key_word.endswith('ír'):
                key_word = re.sub(r'ír$', 'ir', key_word)
            # Entries like 'dársele vuelta el paraguas' don't replace the infinitive with ~
            return key_word, ' '.join(lookup_parts)

        modified_parts[key_index] = '~'
        return base_part, ' '.join(modified_parts)


async def setup(bot):
    await bot.add_cog(DamerDictionary(bot))
