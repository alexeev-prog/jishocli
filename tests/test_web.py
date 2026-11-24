import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

from jishocli.web import Handler
from jishocli.web import page


class WebRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_exam_and_card_tools(self):
        from urllib.request import Request
        for path, expected in (("/exam", "Экзамен JLPT"), ("/export.json", '"cards"')):
            with urlopen(self.base + path, timeout=30) as response:
                self.assertIn(expected, response.read().decode())
        req = Request(self.base + "/generate-cards", data=b"text=", method="POST")
        with urlopen(req, timeout=10) as response:
            self.assertIn("Генератор карточек", response.read().decode())

    def test_new_pages(self):
        with patch("jishocli.web.search_books", return_value=[]):
            for path, expected in (("/cards?tab=generator", "Генератор"), ("/words", "Слова N5"),
                                   ("/lesson/DRILL-01", "Соберите предложение"),
                                   ("/lesson/START-02", "Диалог"), ("/books?q=%E3%81%93%E3%81%93%E3%82%8D", "Книги"),
                                   ("/conversation", "Общение"), ("/shadowing", "Аудирование"),
                                   ("/builder", "Конструктор"), ("/random", "Случайное слово"),
                                   ("/flashcards", "Карточки+"), ("/favorites", "Избранное")):
                with urlopen(self.base + path, timeout=30) as response:
                    self.assertIn(expected, response.read().decode())

    def test_learn_shows_courses_and_vocab_is_separate(self):
        with urlopen(self.base + "/learn", timeout=10) as response:
            courses = response.read().decode()
        self.assertIn("Курсы японского", courses)
        self.assertNotIn("Обучение по тексту", courses)
        with urlopen(self.base + "/vocab", timeout=10) as response:
            vocab = response.read().decode()
        self.assertIn("Обучение по тексту", vocab)


class WebDataTests(unittest.TestCase):
    def test_web_has_all_primary_sections(self):
        rendered = page("test", "") .decode()
        for route in ("/learn", "/search", "/translate", "/kanji", "/anime", "/manga", "/facts", "/cards", "/study", "/stats"):
            self.assertIn(f'href="{route}"', rendered)
        self.assertIn("--panel", rendered)
        self.assertIn("localStorage", rendered)
        self.assertIn("theme-dark", rendered)
        self.assertIn("theme-toggle", rendered)
        self.assertIn("tesseract.min.js", page("ocr", "", ocr=True).decode())
        self.assertIn('id="drawer"', rendered)
        self.assertIn('class="burger"', rendered)
        self.assertIn("quickTranslate", rendered)
        self.assertIn("id=\"trans-panel\"", rendered)
        for ch in rendered:
            self.assertFalse(0x1F300 <= ord(ch) <= 0x1FAFF)
        self.assertNotIn("speechSynthesis.speak", rendered)
        self.assertIn('id="toast"', rendered)
        self.assertIn("max-height:min(72vh,560px)", rendered)

    @patch("jishocli.web.kanji_info", return_value={"meanings": ["study"], "on_readings": ["ガク"], "kun_readings": ["まなぶ"], "jlpt": 5})
    @patch("jishocli.web.save_svg")
    def test_kanji_dependencies_are_available(self, save_svg, kanji_info):
        from jishocli.web import Handler
        self.assertTrue(callable(Handler))
        kanji_info("学")
        save_svg("学", "学.svg")
        kanji_info.assert_called_once_with("学")
        save_svg.assert_called_once()


if __name__ == "__main__":
    unittest.main()
