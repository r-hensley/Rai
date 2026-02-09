import pytest
import os

from cogs.damer import DamerDictionary, Buscador, Acepción, Expresión, ExcepciónDNE

@pytest.fixture
def fetch_parsed_html():
    def _fetch_parsed_html(filename: str):
        html_path = os.path.join('tests', 'cogs', 'damer_sample_htmls', filename)
        with open(html_path, 'r') as html_file:
            return html_file.read()
    return _fetch_parsed_html


class TestDamer:
    def test_sanitize_input(self):
        assert DamerDictionary._sanitize_input('fine') == 'fine'
        assert DamerDictionary._sanitize_input('FINE WITH SPACES') == 'fine with spaces'
        assert DamerDictionary._sanitize_input('áéíóúüÁÉÍÓÚÜñÑ.-!¿¡?::,()') == 'áéíóúüáéíóúüññ.-!¿¡?,()'
        assert DamerDictionary._sanitize_input('hacérsele (algo)') == 'hacérsele (algo)'

    def test_generate_target_word_and_phrase(self):
        assert DamerDictionary._generate_target_word_and_phrase('término'.split()) == ('término', '')
        assert DamerDictionary._generate_target_word_and_phrase('pasarlo chancho'.split()) == ('pasar', '~lo chancho')
        assert DamerDictionary._generate_target_word_and_phrase('pasarla chancho'.split()) == ('pasar', '~la chancho')
        assert DamerDictionary._generate_target_word_and_phrase('estar un montón'.split()) == ('estar', '~ un montón')
        assert DamerDictionary._generate_target_word_and_phrase('hacerle la barba'.split()) == ('hacer', '~le la barba')
        assert DamerDictionary._generate_target_word_and_phrase('no estar ni tibio'.split()) == ('estar', 'no ~ ni tibio')
        assert DamerDictionary._generate_target_word_and_phrase('hacerse alka'.split()) == ('hacer', '~se alka')
        assert DamerDictionary._generate_target_word_and_phrase('no estar ni tibio'.split()) == ('estar', 'no ~ ni tibio')
        assert DamerDictionary._generate_target_word_and_phrase('dársela'.split()) == ('dar', 'dársela')
        assert DamerDictionary._generate_target_word_and_phrase('dárselas'.split()) == ('dar', 'dárselas')
        assert DamerDictionary._generate_target_word_and_phrase('dársele vuelta el paraguas'.split()) == ('dar', 'dársele vuelta el paraguas')
        assert DamerDictionary._generate_target_word_and_phrase('hacérsele (algo)'.split()) == ('hacer', 'hacérsele (algo)')
        assert DamerDictionary._generate_target_word_and_phrase('pasárselo por la galleta'.split()) == ('pasar', 'pasárselo por la galleta')
        assert DamerDictionary._generate_target_word_and_phrase('pasársela por la galleta'.split()) == ('pasar', 'pasársela por la galleta')
        assert DamerDictionary._generate_target_word_and_phrase('a todo dar'.split()) == ('dar', 'a todo ~')
        assert DamerDictionary._generate_target_word_and_phrase('írsele el tren'.split()) == ('ir', 'írsele el tren')
        assert DamerDictionary._generate_target_word_and_phrase('no irse chancho con mazorca'.split()) == ('ir', 'no ~se chancho con mazorca')
        assert DamerDictionary._generate_target_word_and_phrase('írsela campechaneando'.split()) == ('ir', 'írsela campechaneando')
        assert DamerDictionary._generate_target_word_and_phrase('ir de pinch hitter'.split()) == ('ir', '~ de pinch hitter')

    def test_primary_etymology(self, fetch_parsed_html):
        # Test primary etymology without formatting
        entradas = Buscador.parsear_resultados('living', fetch_parsed_html('living.html'))
        assert len(entradas) == 1
        entrada = entradas[0]
        assert entrada.encabezado == '_living._'
        assert entrada.etimología == '(Voz inglesa).'
        assert len(entrada.acepciones) == 1
        assert entrada.acepciones[0] == Acepción(
            índice_primario='I.',
            índice_secundario='1.',
            texto_entrada='m. _Cu_, _Bo_, _Ch_, _Py._ Juego de sofá y sillones de una sala de estar.',
            texto_entrada_raw='m. Cu, Bo, Ch, Py. Juego de sofá y sillones de una sala de estar.'
        )
        assert len(entrada.expresiones) == 1
        assert entrada.expresiones[0] == Expresión(
            índice='a. ǁ',
            texto_entrada='~** comedor.** m. _Ni_, _Cu_, _Bo_, _Ch_, _Py_, _Ar._ Habitación de una casa en la que se hace la vida social.',
            texto_entrada_raw='~ comedor. m. Ni, Cu, Bo, Ch, Py, Ar. Habitación de una casa en la que se hace la vida social.',
            subsignificados=[],
            marcador='■'
        )
        assert entrada.expresiones[0].expresión == '~ comedor'

        # Test primary etymology with italics
        entradas = Buscador.parsear_resultados('country', fetch_parsed_html('country.html'))
        assert len(entradas) == 1
        entrada = entradas[0]
        assert entrada.encabezado == '_country._'
        assert entrada.etimología == '(Voz inglesa_, campo_).'
        assert len(entrada.acepciones) == 0
        assert len(entrada.expresiones) == 1
        want_expr = Expresión(
            índice='a. ǁ',
            texto_entrada='~** club.** m. _EU_, _Ni_, _PR_, _Ve_, _Ec_, _Ch_, _Py_. Club campestre de actividades deportivas, _especialmente de golf_.',
            texto_entrada_raw='~ club. m. EU, Ni, PR, Ve, Ec, Ch, Py. Club campestre de actividades deportivas, especialmente de golf.',
            subsignificados=[],
            marcador='■'
        )
        assert entrada.expresiones[0] == want_expr
        assert entrada.expresiones[0].expresión == '~ club'
        assert entrada.busca_expresión('~ club') == want_expr
        assert entrada.busca_expresión('~ dne') == None

    def test_dne(self, fetch_parsed_html):
        with pytest.raises(ExcepciónDNE) as excDNE:
            entradas = Buscador.parsear_resultados('asd', fetch_parsed_html('dne.html'))
        assert str(excDNE.value) == '''Aviso: La palabra **asd** no está en el Diccionario. Las entradas que se muestran a continuación podrían estar relacionadas:

[asa](https://www.asale.org/damer/damer/asa) (asa)
[así](https://www.asale.org/damer/damer/así) (así)'''

    def test_etymology_in_numerals(self, fetch_parsed_html):
        entradas = Buscador.parsear_resultados('cajeta', fetch_parsed_html('cajeta.html'))
        assert len(entradas) == 1
        entrada = entradas[0]
        assert entrada.encabezado == 'cajeta.'
        assert not entrada.etimología
        assert len(entrada.acepciones) == 15
        assert entrada.acepciones[0] == Acepción(
            índice_primario='I. (Del nahua _caxitl,_ escudilla).',
            índice_secundario='1.',
            texto_entrada='f. _Mx_, _Gu_, _Cu_, _RD_, _PR_, _Pe_;_ Ec,_ obsol;_ Ho_, pop. Caja en que se ponen o venden dulces, jalea o turrón de diversas formas, según el molde que se use.',
            texto_entrada_raw='f. Mx, Gu, Cu, RD, PR, Pe; Ec, obsol; Ho, pop. Caja en que se ponen o venden dulces, jalea o turrón de diversas formas, según el molde que se use.'
        )
        assert entrada.acepciones[1] == Acepción(
            índice_primario='',
            índice_secundario='2.',
            texto_entrada='_Mx_, _Gu_, _Pa_, _Pe_;_ Ho_, pop. Dulce de leche, _generalmente de cabra_, quemada con azúcar, y de consistencia similar al turrón.',
            texto_entrada_raw='Mx, Gu, Pa, Pe; Ho, pop. Dulce de leche, generalmente de cabra, quemada con azúcar, y de consistencia similar al turrón.'
        )
        # Con vínculo
        print(entrada.acepciones[4])
        assert entrada.acepciones[4] == Acepción(
            índice_primario='',
            índice_secundario='5.',
            texto_entrada='_Ni_, _CR._ Dulce similar al turrón, elaborado con [panela](https://www.asale.org/damer/panela), dulce de leche o leche en polvo; puede añadírsele algún fruto seco rallado, _especialmente_ _coco._',
            texto_entrada_raw='Ni, CR. Dulce similar al turrón, elaborado con panela, dulce de leche o leche en polvo; puede añadírsele algún fruto seco rallado, especialmente coco.'
        )
        assert entrada.acepciones[7] == Acepción(
            índice_primario='III.',
            índice_secundario='1.',
            texto_entrada='f. _Ve:O._ Caja pequeña, _generalmente con forma de cono truncado, hecha de cuerno de res o de otros materiales_, utilizada para guardar el chimó.',
            texto_entrada_raw=' f. Ve:O. Caja pequeña, generalmente con forma de cono truncado, hecha de cuerno de res o de otros materiales, utilizada para guardar el chimó.'
        )
        assert entrada.acepciones[14] == Acepción(
            índice_primario='VIII. (De la sigla _KGB_, policía secreta de la antigua Unión Soviética).',
            índice_secundario='1.',
            texto_entrada='f. _Ho._ Policía secreta de la antigua Unión Soviética. cult ^ fest.',
            texto_entrada_raw='f. Ho. Policía secreta de la antigua Unión Soviética. cult ^ fest.'
        )
        assert len(entrada.expresiones) == 3
        assert entrada.expresiones[0] == Expresión(
            índice='a. ǁ',
            texto_entrada='~** de Celaya.** loc. sust. _Mx._ Conciencia exagerada de la propia valía, complejo de superioridad.',
            texto_entrada_raw='~ de Celaya. loc. sust. Mx. Conciencia exagerada de la propia valía, complejo de superioridad.',
            subsignificados=[],
            marcador='□'
        )
        want_expr = Expresión(
            índice='b. ǁ',
            texto_entrada='**de **~**.** loc. adj. _RD._ _Referido a objeto_, nuevo, sin estrenar.',
            texto_entrada_raw='de ~. loc. adj. RD. Referido a objeto, nuevo, sin estrenar.',
            subsignificados=[],
            marcador=''
        )
        assert entrada.expresiones[1] == want_expr
        assert entrada.expresiones[2] == Expresión(
            índice='▶',
            texto_entrada='**chupar **~;** dar **~;** tener **~**, cuchillo y guaro**.',
            texto_entrada_raw='chupar ~; dar ~; tener ~, cuchillo y guaro.',
            subsignificados=[],
            marcador=''
        )
        assert entrada.busca_expresión('de ~') == want_expr

    def test_multi_entradas(self, fetch_parsed_html):
        entradas = Buscador.parsear_resultados('asopado', fetch_parsed_html('asopado.html'))
        assert len(entradas) == 2
        entrada1 = entradas[0]
        assert len(entrada1.expresiones) == 0
        assert len(entrada1.acepciones) == 1
        assert entrada1.encabezado == 'asopado.'
        assert entrada1.acepciones[0] == Acepción(
            índice_primario='I.',
            índice_secundario='1.',
            texto_entrada='m. _Pa._ Plato de arroz cocido con carne o pollo y algunas verduras, con la apariencia de una sopa espesa.',
            texto_entrada_raw='m. Pa. Plato de arroz cocido con carne o pollo y algunas verduras, con la apariencia de una sopa espesa.'
        )
        entrada2 = entradas[1]
        assert len(entrada2.expresiones) == 0
        assert len(entrada2.acepciones) == 1
        assert entrada2.encabezado == 'asopado, -a.'
        assert entrada2.acepciones[0] == Acepción(
            índice_primario='I.',
            índice_secundario='1.',
            texto_entrada='adj/sust. _Ch._ _Referido a persona_, escasa de entendimiento y lenta para reaccionar. pop + cult → espon ^ desp.',
            texto_entrada_raw='adj/sust. Ch. Referido a persona, escasa de entendimiento y lenta para reaccionar. pop + cult → espon ^ desp.'
        )

    def test_equivalencias(self, fetch_parsed_html):
        entradas = Buscador.parsear_resultados('yanchama', fetch_parsed_html('yanchama.html'))
        assert len(entradas) == 1
        entrada = entradas[0]
        assert len(entrada.acepciones) == 4
        assert len(entrada.expresiones) == 1
        assert entrada.acepciones[1] == Acepción(
            índice_primario='',
            índice_secundario='2.',
            texto_entrada='_Ec_, _Pe._ Árbol de hasta 30 m de altura, de tronco recto con la corteza exterior gris claro, copa redonda o irregular, poco densa, hojas simples, alternas, de borde enteros, flores amarillas, frutos globosos, con el extremo apical en forma de estrella, de color verde, tornándose amarillos al madurar. (Moraceae; _Poulsenia armata_). ([llanchama](https://www.asale.org/damer/llanchama)). ◆ **cucuá**; **ñumi**.',
            texto_entrada_raw='Ec, Pe. Árbol de hasta 30 m de altura, de tronco recto con la corteza exterior gris claro, copa redonda o irregular, poco densa, hojas simples, alternas, de borde enteros, flores amarillas, frutos globosos, con el extremo apical en forma de estrella, de color verde, tornándose amarillos al madurar. (Moraceae; Poulsenia armata). (llanchama). ◆ cucuá; ñumi.'
        )
        want_expr = Expresión(
            índice='a. ǁ',
            texto_entrada='~** ojé.** f. _Co._ Árbol de hasta 30 m de altura, de corteza exterior blanca o grisácea, hojas simples y alternas, de bordes enteros y frutos globosos; de su corteza se obtiene la tela para hacer la yanchama. (Moraceae; _Ficus glabrata_). ◆ **ojé**.',
            texto_entrada_raw='~ ojé. f. Co. Árbol de hasta 30 m de altura, de corteza exterior blanca o grisácea, hojas simples y alternas, de bordes enteros y frutos globosos; de su corteza se obtiene la tela para hacer la yanchama. (Moraceae; Ficus glabrata). ◆ ojé.',
            subsignificados=[],
            marcador='■'
        )
        assert entrada.expresiones[0] == want_expr
        assert entrada.busca_expresión('~ ojé') == want_expr