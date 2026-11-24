import unittest
from unittest.mock import patch

from jishocli import kana, quiz
from jishocli.api import ApiError, _media_anilist, kanji_strokes, search_media
from jishocli.romaji import romaji


class KanaTests(unittest.TestCase):
    def test_basic_table_complete(self):
        self.assertEqual(len(kana.BASIC), 46)
        self.assertEqual(len({r for _, _, r, _ in kana.BASIC}), 46)

    def test_every_char_has_hint_and_pair(self):
        for h, k, r, hint in kana.ALL:
            self.assertTrue(h and k and r and hint)

    def test_romaji_consistency(self):
        for h, k, r, _ in kana.BASIC:
            if r not in {"wo"}:  # を is romanized wo but pronounced o
                self.assertEqual(romaji(h), r)
                self.assertEqual(romaji(k), r)


class QuizTests(unittest.TestCase):
    def test_seeded_generation_is_reproducible(self):
        self.assertEqual(quiz.generate("mixed", 10, seed=42), quiz.generate("mixed", 10, seed=42))

    def test_answer_always_in_options(self):
        for kind in quiz.TYPES:
            for q in quiz.generate(kind, 15, seed=7):
                self.assertIn(q["answer"], q["options"])
                self.assertEqual(len(q["options"]), 4)

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):
            quiz.generate("nope")


class MediaEngineTests(unittest.TestCase):
    def test_anilist_normalization(self):
        payload = {"data": {"Page": {"media": [{
            "title": {"romaji": "ONE PIECE", "english": "One Piece", "native": "ONE PIECE"},
            "format": "MANGA", "status": "RELEASING", "averageScore": 91,
            "episodes": None, "chapters": None, "genres": ["Action"],
            "description": "Luffy<br>pirate", "siteUrl": "https://anilist.co/manga/30013",
            "coverImage": {"large": "https://img/1.jpg"}}]}}}
        with patch('jishocli.api._request', return_value=payload):
            rows = _media_anilist('One Piece', 'manga', 1)
        self.assertEqual(rows[0]['title'], 'One Piece')
        self.assertEqual(rows[0]['score'], 9.1)
        self.assertEqual(rows[0]['genres'], [{'name': 'Action'}])
        self.assertNotIn('<br>', rows[0]['synopsis'])

    def test_all_providers_fail_raises_combined_error(self):
        with patch('jishocli.api._media_anilist', side_effect=ApiError('a')), \
             patch('jishocli.api._media_tenrai', side_effect=ApiError('b')), \
             patch('jishocli.api._media_jikan', side_effect=ApiError('c')):
            with self.assertRaisesRegex(ApiError, 'AniList'):
                search_media('x', 'anime', 1)

    def test_kanji_strokes_url_uses_codepoint(self):
        with patch('jishocli.api._get_text', return_value='<svg/>') as fetch:
            self.assertEqual(kanji_strokes('学'), '<svg/>')
        self.assertIn('05b66.svg', fetch.call_args.args[0])


class ProxyFallbackTests(unittest.TestCase):
    def test_proxy_failure_falls_back_to_direct(self):
        import io
        import jishocli.api as api
        from unittest.mock import MagicMock
        opener = MagicMock()
        opener.open.side_effect = OSError('proxy refused')
        api._opener = opener
        api._proxy_url = 'http://127.0.0.1:8118'
        response = io.BytesIO(b'{"ok": true}')
        try:
            with patch('jishocli.api.urlopen', return_value=response) as direct:
                self.assertEqual(api._get('https://example.org/x'), {'ok': True})
            opener.open.assert_called_once()
            direct.assert_called_once()
        finally:
            api._opener = None
            api._proxy_url = None


class DailyExportStreakTests(unittest.TestCase):
    def test_daily_word_deterministic(self):
        from datetime import date
        from jishocli.quiz import daily_word
        day = date(2026, 11, 23)
        self.assertEqual(daily_word(day), daily_word(day))

    def test_export_formats(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from jishocli.storage import Store
        with TemporaryDirectory() as folder:
            store = Store(Path(folder) / "cards.json")
            store.add({"word": "猫", "reading": "ねこ", "meaning": "кот"})
            self.assertIn("猫", store.export_csv())
            self.assertIn("#separator:tab", store.export_anki())
            self.assertIn("猫", store.export_anki())

    def test_streak_counts_consecutive_days(self):
        from datetime import date, timedelta
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from jishocli.storage import Store
        with TemporaryDirectory() as folder:
            store = Store(Path(folder) / "cards.json")
            today = date.today()
            store.data["history"] = [(today - timedelta(days=i)).isoformat() for i in range(3)]
            self.assertEqual(store.streak(), 3)


class MangaDexTests(unittest.TestCase):
    def test_chapters_skip_external_and_unavailable(self):
        from jishocli.api import mangadex_chapters
        payload = {"data": [
            {"id": "a", "attributes": {"chapter": "1", "externalUrl": "https://x", "pages": 10}},
            {"id": "b", "attributes": {"chapter": "2", "isUnavailable": True, "pages": 10}},
            {"id": "c", "attributes": {"chapter": "3", "title": "T", "pages": 20}},
        ]}
        with patch('jishocli.api._get', return_value=payload):
            rows = mangadex_chapters('manga-id')
        self.assertEqual([r['id'] for r in rows], ['c'])

    def test_pages_build_urls(self):
        from jishocli.api import mangadex_pages
        payload = {"result": "ok", "baseUrl": "https://x.mangadex.network",
                   "chapter": {"hash": "h", "data": ["1.png", "2.png"]}}
        with patch('jishocli.api._get', return_value=payload):
            pages = mangadex_pages('c')
        self.assertEqual(pages['count'], 2)
        self.assertEqual(pages['urls'][0], 'https://x.mangadex.network/data/h/1.png')

    def test_learn_vocab_filters_and_looks_up(self):
        from jishocli.api import learn_vocab
        tokens = [
            {"word": "日本語", "base": "日本語", "reading": "にほんご", "romaji": "nihongo", "pos": "существительное"},
            {"word": "は", "base": "は", "reading": "は", "romaji": "ha", "pos": "частица"},
            {"word": "勉強", "base": "勉強", "reading": "べんきょう", "romaji": "benkyou", "pos": "существительное"},
        ]
        with patch('jishocli.language.analyze', return_value=tokens), \
             patch('jishocli.api.search_jisho', return_value=[{"senses": [{"english_definitions": ["Japanese"]}]}]):
            rows = learn_vocab('日本語は勉強', limit=5)
        self.assertEqual([r['base'] for r in rows], ['日本語', '勉強'])
        self.assertEqual(rows[0]['meaning'], 'Japanese')


class AudioQuizTests(unittest.TestCase):
    def test_audio_questions_have_speak(self):
        for q in quiz.generate('audio', 12, seed=3):
            self.assertTrue(q['speak'])
            self.assertIn(q['answer'], q['options'])


class TTSTests(unittest.TestCase):
    def test_tts_audio_caches_result(self):
        import io
        import os
        from tempfile import TemporaryDirectory
        import jishocli.api as api
        audio = b"\xff\xf3" + b"x" * 1000
        with TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home}), \
                 patch("jishocli.api._open", return_value=io.BytesIO(audio)) as opener:
                self.assertEqual(api.tts_audio("ありがとう"), audio)
                self.assertEqual(api.tts_audio("ありがとう"), audio)
            self.assertEqual(opener.call_count, 1)


class ExamTests(unittest.TestCase):
    def test_generate_and_evaluate(self):
        from jishocli import exam
        qs = exam.generate_exam("MIXED", 20, seed=4)
        self.assertEqual(len(qs), 20)
        self.assertEqual(len({q["level"] for q in qs}), 5)
        result = exam.evaluate(qs, {str(q["number"]): q["answer"] for q in qs})
        self.assertEqual(result["percent"], 100)
        self.assertEqual(result["grade"], "A")
        self.assertIn("estimate", result)
        self.assertEqual(len(result["details"]), 20)

    def test_weak_skills_detected(self):
        from jishocli import exam
        qs = exam.generate_exam("N5", 10, seed=1)
        result = exam.evaluate(qs, {})
        self.assertEqual(result["percent"], 0)
        self.assertTrue(result["weakest"])
        self.assertTrue(result["recommendations"])

    def test_invalid_level(self):
        from jishocli import exam
        with self.assertRaises(ValueError):
            exam.generate_exam("N0")


class StorageFeatureTests(unittest.TestCase):
    def test_json_import_and_goal(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from jishocli.storage import Store
        with TemporaryDirectory() as folder:
            store = Store(Path(folder) / "cards.json")
            payload = json.dumps({"cards": [{"word": "猫", "reading": "ねこ", "meaning": "кот"}]})
            self.assertEqual(store.import_json(payload), 1)
            self.assertIn("猫", store.export_json())
            store.set_goal(15)
            self.assertEqual(store.goal, 15)
            self.assertEqual(store.today_count(), 0)


    def test_book_search(self):
        from jishocli.api import search_books
        payload = {"docs": [{"key": "/works/OL1W", "title": "こころ", "author_name": ["夏目漱石"],
                             "ia": ["kokoro008800"], "cover_i": 123, "first_publish_year": 1914}]}
        with patch("jishocli.api._get", return_value=payload):
            rows = search_books("こころ")
        self.assertEqual(rows[0]["title"], "こころ")
        self.assertEqual(rows[0]["ia"], "kokoro008800")


class ImprovedQuizTests(unittest.TestCase):
    def test_recall_mode(self):
        qs = quiz.generate("vocab", 3, seed=5, mode="recall")
        self.assertTrue(all(q["mode"] == "recall" for q in qs))
        with self.assertRaises(ValueError):
            quiz.generate("vocab", 1, mode="unknown")

    def test_new_types(self):
        for kind in ("sentence", "kanji-reading", "audio"):
            qs = quiz.generate(kind, 4, seed=2)
            self.assertEqual(len(qs), 4)
            self.assertTrue(all(q["speak"] for q in qs))

    def test_lesson_quiz_generator(self):
        items = [("Как читается あ?", "a"), ("Как читается い?", "i")]
        qs = quiz.from_lesson_quiz(items, seed=1)
        self.assertEqual(len(qs), 2)
        self.assertTrue(all(q["answer"] in q["options"] for q in qs))


class FilterTests(unittest.TestCase):
    def test_media_filters_reach_anilist(self):
        from jishocli.api import search_media
        with patch("jishocli.api._media_anilist", return_value=[{"title": "X"}]) as provider:
            rows = search_media("x", "anime", 3, genre="Fantasy", year=2020,
                                status="RELEASING", sort="SCORE_DESC")
        self.assertEqual(rows[0]["title"], "X")
        self.assertEqual(provider.call_args.args[3:], ("Fantasy", 2020, "RELEASING", "SCORE_DESC"))

    def test_mangadex_popular_has_no_title(self):
        from jishocli.api import mangadex_popular
        with patch("jishocli.api._get", return_value={"data": []}) as get:
            mangadex_popular(5)
        self.assertNotIn("title=", get.call_args.args[0])


    def test_tts_chunking(self):
        import io
        import os
        from tempfile import TemporaryDirectory
        import jishocli.api as api
        audio = b"\xff\xf3" + b"x" * 1000
        with TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home}), \
                 patch("jishocli.api._open", side_effect=lambda *a, **k: io.BytesIO(audio)) as opener:
                result = api.tts_audio("これは長い文章です。" * 30)
            self.assertEqual(result, audio * opener.call_count)


class NewFeaturesTests(unittest.TestCase):
    def test_courses_have_lessons(self):
        from jishocli.course import COURSES, all_lessons, get_lesson
        self.assertEqual([c["id"] for c in COURSES],
                         ["START", "BASIC", "PHRASE", "KANJI", "DRILL", "N5", "N4", "N3", "KEIGO"])
        self.assertGreaterEqual(len(all_lessons()), 100)
        self.assertEqual(get_lesson("01")["id"], "01")
        self.assertEqual(get_lesson("N4-03")["id"], "N4-03")
        self.assertEqual(get_lesson("START-01")["id"], "START-01")
        required = {"goal", "text", "grammar", "syntax", "practice", "pronunciation", "quiz", "links"}
        for lesson in all_lessons():
            self.assertTrue(required.issubset(lesson), lesson["id"])

    def test_course_navigation(self):
        from jishocli.course import course_of_lesson, lesson_neighbors
        nav = lesson_neighbors("START-02")
        self.assertEqual(nav["course"]["id"], "START")
        self.assertEqual(nav["prev"], "START-01")
        self.assertEqual(nav["next"], "START-03")
        self.assertEqual(course_of_lesson("N4-01")["id"], "N4")

    def test_ocr_local_requires_tesseract(self):
        from jishocli.api import ocr_local
        with patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(ApiError, 'tesseract'):
                ocr_local('/tmp/x.png')

    def test_image_url_allowlist(self):
        from jishocli.api import is_allowed_image_url
        self.assertTrue(is_allowed_image_url('https://s4.anilist.co/file/x.jpg'))
        self.assertTrue(is_allowed_image_url('https://cmdxd98sb0x3yprd.mangadex.network/data/h/1.png'))
        self.assertFalse(is_allowed_image_url('http://127.0.0.1/admin'))
        self.assertFalse(is_allowed_image_url('https://evil.example/x.png'))

    def test_anilist_row_has_links_and_trailer(self):
        from jishocli.api import _anilist_row
        row = _anilist_row({"title": {"romaji": "X"}, "externalLinks": [{"site": "Crunchyroll", "url": "https://x"}],
                            "trailer": {"site": "youtube", "id": "abc"}})
        self.assertEqual(row["links"][0]["site"], "Crunchyroll")
        self.assertEqual(row["trailer"], "https://www.youtube.com/embed/abc")


if __name__ == '__main__':
    unittest.main()
