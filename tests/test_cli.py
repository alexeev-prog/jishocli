import io
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from jishocli.api import ApiError, detect_language, translate, configure_proxy, proxy_status
from jishocli.cli import _parser, main, print_results, translate_phrase
from jishocli.language import analyze
from jishocli.romaji import phrase_romaji, romaji, reading_romaji
from jishocli.storage import Store


class LanguageTests(unittest.TestCase):
    def test_romaji(self):
        self.assertEqual(phrase_romaji('ありがとうございます'), 'arigatou gozaimasu')
        self.assertEqual(romaji('がっこう'), 'gakkou')
        self.assertEqual(reading_romaji('ネコ'), 'neko')
        self.assertEqual(romaji('フリー'), 'furii')
        self.assertEqual(romaji('コーヒー'), 'koohii')

    def tearDown(self):
        translate.cache_clear()

    def test_detection(self):
        for text, language in [('猫です', 'ja'), ('привет', 'ru'), ('hello', 'en')]:
            self.assertEqual(detect_language(text), language)

    def test_translation_validates_provider_status(self):
        with patch('jishocli.api._get', return_value={'responseStatus': 429, 'responseDetails': 'quota'}):
            with self.assertRaisesRegex(ApiError, 'quota'):
                translate('hello', 'en', 'ja')

    def test_network_error_is_actionable(self):
        with patch('jishocli.api.urlopen', side_effect=TimeoutError('timed out')):
            with self.assertRaisesRegex(ApiError, 'Сервис временно недоступен'):
                from jishocli.api import search_jisho
                search_jisho('猫')

    def test_proxy_configuration(self):
        import jishocli.api as api
        configure_proxy('http://127.0.0.1:8899')
        self.assertEqual(proxy_status(), 'http://127.0.0.1:8899')
        api._opener = None
        api._proxy_url = None

    def test_translation_decodes_entities(self):
        with patch('jishocli.api._get', return_value={'responseStatus': 200, 'responseData': {'translatedText': 'cats &amp; dogs'}}):
            self.assertEqual(translate('猫と犬', 'ja', 'en'), 'cats & dogs')

    def test_translation_byte_limit(self):
        with self.assertRaisesRegex(ApiError, '500'):
            translate('猫' * 200, 'ja', 'ru')

    def test_analysis(self):
        rows = analyze('私は学校で食べました。')
        verb = next(row for row in rows if row['word'] == '食べ')
        self.assertEqual(verb['base'], '食べる')
        self.assertEqual(verb['reading'], 'たべ')
        self.assertEqual(verb['romaji'], 'tabe')
        self.assertEqual(verb['pos'], 'глагол')
        self.assertTrue(next(row for row in rows if row['word'] == 'は')['hint'])


class CliTests(unittest.TestCase):
    def test_image_path_required(self):
        with redirect_stdout(io.StringIO()), patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                _parser().parse_args(['kanji', '学'])

    def test_minimal_output_and_parts_of_speech(self):
        result = {'japanese': [{'word': '猫', 'reading': 'ねこ'}],
                  'senses': [{'english_definitions': ['cat'], 'parts_of_speech': ['Noun']}],
                  'is_common': True}
        output = io.StringIO()
        with patch('jishocli.cli._ru', return_value='кот'), redirect_stdout(output):
            print_results([result])
        text = output.getvalue()
        self.assertIn('кот', text)
        self.assertIn('Noun', text)
        self.assertNotIn('│', text)
        self.assertNotIn('╭', text)

    def test_translate_and_save(self):
        with TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'cards.json')
            args = Namespace(query='Я ем', lang='auto', to=None, details=False, add=True)
            with patch('jishocli.cli.translate', return_value='食べます'), redirect_stdout(io.StringIO()):
                translate_phrase(args, store)
            self.assertEqual(store.cards[0]['word'], '食べます')
            self.assertEqual(store.cards[0]['meaning'], 'Я ем')

    def test_media_no_results(self):
        with patch('jishocli.cli.search_media', return_value=[]), redirect_stdout(io.StringIO()) as output:
            main(['anime', 'missing'])
        self.assertIn('Ничего не найдено', output.getvalue())

    def test_manga_search_falls_back_between_providers(self):
        from jishocli.api import search_media
        with patch('jishocli.api._media_anilist', side_effect=ApiError('down')), \
             patch('jishocli.api._media_tenrai', return_value=[{'title': 'One Piece'}]) as tenrai:
            self.assertEqual(search_media('One Piece', 'manga', 3)[0]['title'], 'One Piece')
        tenrai.assert_called_once()

    def test_manga_search_uses_jikan_last(self):
        from jishocli.api import search_media
        with patch('jishocli.api._media_anilist', side_effect=ApiError('down')), \
             patch('jishocli.api._media_tenrai', side_effect=ApiError('down')), \
             patch('jishocli.api._get', return_value={'data': [{'title': 'One Piece'}]}) as request:
            self.assertEqual(search_media('One Piece', 'manga', 3)[0]['title'], 'One Piece')
        self.assertIn('/manga?', request.call_args.args[0])

    def test_media_provider_error_is_not_reported_as_empty(self):
        from jishocli.api import search_media
        with patch('jishocli.api._media_anilist', side_effect=ApiError('network')), \
             patch('jishocli.api._media_tenrai', side_effect=ApiError('network')), \
             patch('jishocli.api._media_jikan', side_effect=ApiError('network')):
            with self.assertRaisesRegex(ApiError, 'network'):
                search_media('One Piece', 'manga', 3)

    def test_media_metadata(self):
        row = {'title': 'Frieren', 'title_japanese': '葬送のフリーレン', 'type': 'TV',
               'status': 'Finished Airing', 'score': 9.1, 'episodes': 28,
               'genres': [{'name': 'Adventure'}], 'synopsis': 'A journey.',
               'url': 'https://myanimelist.net/anime/52991/'}
        with patch('jishocli.cli.search_media', return_value=[row]), redirect_stdout(io.StringIO()) as output:
            main(['anime', 'Frieren'])
        for expected in ('葬送のフリーレン', '28 серий', 'Adventure', 'A journey.', 'myanimelist.net'):
            self.assertIn(expected, output.getvalue())

    def test_japanese_translation_default_target(self):
        with TemporaryDirectory() as folder:
            args = Namespace(query='猫です', lang='auto', to=None, details=False, add=False)
            with patch('jishocli.cli.translate', return_value='Это кот.') as translator, redirect_stdout(io.StringIO()):
                translate_phrase(args, Store(Path(folder) / 'cards.json'))
            translator.assert_called_once_with('猫です', 'ja', 'ru')

    def test_topic_alias(self):
        with patch('jishocli.cli.search_topics', return_value=[]), redirect_stdout(io.StringIO()) as output:
            main(['explore', 'Япония'])
        self.assertIn('Wikipedia', output.getvalue())


if __name__ == '__main__':
    unittest.main()
