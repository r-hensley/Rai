from cogs.damer import DamerDictionary


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
