from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from textwrap import shorten

from .api import (ApiError, anilist_detail, configure_proxy, download_file, fetch_bytes,
                  kanji_info, kanji_strokes, learn_vocab, mangadex_chapters, mangadex_pages,
                  mangadex_search, ocr_local, search_books, search_jisho, search_media,
                  tts_audio, translate_to_english, translate_to_russian)
from .renderer import save_svg
from .storage import Store
from .api import detect_language, translate, search_media, search_topics
from .language import analyze
from .romaji import phrase_romaji, reading_romaji
from .course import COURSES, course_by_id, course_progress, complete, get_lesson
from . import exam as exam_engine
from . import quiz as quiz_engine
from . import kana
from .quiz import daily_word
from .web import serve

BLUE, GREEN, YELLOW, DIM, RESET = "\033[36m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty() or "NO_COLOR" in os.environ:
    BLUE = GREEN = YELLOW = DIM = RESET = ""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jishocli", description="Японский словарь и тренажёр в терминале")
    p.add_argument("--proxy", help="HTTP(S) proxy для внешних API")
    sub = p.add_subparsers(dest="command")
    s = sub.add_parser("search", aliases=["s"], help="найти слово или выражение в Jisho")
    s.add_argument("query"); s.add_argument("--lang", default="auto", help="auto: русский, английский или японский; другие: de, fr…"); s.add_argument("-n", "--limit", type=int, default=8)
    s.add_argument("--details", action="store_true", help="показать сведения о кандзи")
    s.add_argument("--add", type=int, metavar="N", help="сохранить результат N в карточки")
    f = sub.add_parser("phrase", aliases=["translate", "tr"], help="перевести фразу и разобрать японский текст")
    f.add_argument("query", help="текст или - для чтения из stdin")
    f.add_argument("--lang", default="auto", help="язык исходного текста")
    f.add_argument("--to", choices=["ru", "ja", "en"], help="по умолчанию: японский → русский, остальные → японский")
    f.add_argument("--details", action="store_true", help="добавить словарные значения слов")
    f.add_argument("--add", action="store_true", help="сохранить японскую фразу в карточки")
    for kind in ("anime", "manga"):
        m = sub.add_parser(kind, help=f"поиск {kind} в MyAnimeList / Jikan")
        m.add_argument("query"); m.add_argument("-n", "--limit", type=int, default=3)
        m.add_argument("--details", action="store_true", help="показать полный синопсис")
        m.add_argument("--genre", help="жанр, например Action")
        m.add_argument("--year", type=int, help="не старше года")
        m.add_argument("--status", help="FINISHED / RELEASING")
        m.add_argument("--sort", help="SCORE_DESC / POPULARITY_DESC")
    topics = sub.add_parser("facts", aliases=["explore"], help="темы и факты о Японии из Wikipedia")
    topics.add_argument("query", nargs="?", default="Культура Японии")
    topics.add_argument("--lang", choices=["ru", "en", "ja"], default="ru")
    topics.add_argument("-n", "--limit", type=int, default=3)
    sub.add_parser("cards", help="все сохранённые слова и фразы")
    k = sub.add_parser("kanji", help="сохранить иероглиф как изображение SVG")
    k.add_argument("character"); k.add_argument("--save", metavar="FILE", required=True)
    k.add_argument("--strokes", action="store_true", help="SVG с порядком черт (KanjiVG)")
    q = sub.add_parser("quiz", aliases=["test"], help="случайный тест: кана, слова, частицы, грамматика")
    q.add_argument("--type", default="mixed", choices=quiz_engine.TYPES)
    q.add_argument("-n", "--count", type=int, default=10)
    q.add_argument("--seed", type=int, help="seed для повторяемого набора вопросов")
    q.add_argument("--mode", choices=["choice", "recall"], default="choice", help="выбор или ввод ответа")
    kn = sub.add_parser("kana", help="таблицы хираганы и катаканы")
    kn.add_argument("--script", choices=["hira", "kata", "both"], default="both")
    kn.add_argument("--row", choices=["basic", "dakuten", "yoon", "all"], default="all")
    sub.add_parser("daily", help="слово дня")
    ex = sub.add_parser("export", help="экспорт карточек (CSV или Anki)")
    ex.add_argument("--format", choices=["csv", "anki"], default="csv")
    ex.add_argument("--out", metavar="FILE", help="файл; без него вывод в stdout")
    lf = sub.add_parser("learn-from", help="учить слова из японского текста или аниме/манги")
    lf.add_argument("text", nargs="?", help="японский текст")
    lf.add_argument("--anime", metavar="QUERY"); lf.add_argument("--manga", metavar="QUERY")
    lf.add_argument("-n", "--limit", type=int, default=8)
    lf.add_argument("--add", action="store_true", help="сохранить слова в карточки")
    rd = sub.add_parser("read", help="читалка манги: главы и страницы (MangaDex)")
    rd.add_argument("query"); rd.add_argument("--chapter", help="номер главы")
    rd.add_argument("--lang", default="en", help="язык перевода главы")
    rd.add_argument("--download", metavar="DIR", help="скачать страницы главы в папку")
    a = sub.add_parser("add", help="добавить карточку вручную")
    a.add_argument("word"); a.add_argument("--reading", default=""); a.add_argument("--meaning", default="")
    sub.add_parser("study", aliases=["review"], help="сессия интервального повторения")
    sub.add_parser("due", help="показать карточки на сегодня")
    sub.add_parser("stats", help="статистика обучения")
    learn = sub.add_parser("learn", aliases=["course"], help="учебник японского")
    learn.add_argument("lesson", nargs="?", help="номер урока; без номера — список курса")
    learn.add_argument("--course", default="START", choices=[c["id"] for c in COURSES])
    learn.add_argument("--done", action="store_true", help="отметить урок завершённым")
    sub.add_parser("courses", help="список всех курсов и прогресс")
    bk = sub.add_parser("books", help="поиск японских книг (Open Library)")
    bk.add_argument("query"); bk.add_argument("-n", "--limit", type=int, default=5)
    ex = sub.add_parser("exam", help="демо-экзамен JLPT N5-N1 с аналитикой")
    ex.add_argument("--level", default="MIXED", choices=["MIXED", *exam_engine.LEVELS])
    ex.add_argument("-n", "--count", type=int, default=20)
    ex.add_argument("--seed", type=int)
    ocr = sub.add_parser("ocr", help="OCR изображения (нужен локальный tesseract)")
    ocr.add_argument("image"); ocr.add_argument("--lang", default="jpn+eng", help="языки tesseract")
    imp = sub.add_parser("import", help="восстановить карточки из JSON")
    imp.add_argument("file")
    goal = sub.add_parser("goal", help="дневная цель повторений")
    goal.add_argument("count", type=int, nargs="?")
    say = sub.add_parser("speak", help="сохранить японскую озвучку в MP3")
    say.add_argument("text"); say.add_argument("--out", default="speech.mp3")
    web = sub.add_parser("web", help="запустить веб-интерфейс")
    web.add_argument("--host", default="127.0.0.1"); web.add_argument("--port", type=int, default=8765)
    web.add_argument("--proxy", help="HTTP(S) proxy, например http://127.0.0.1:8080")
    return p


def _print_kanji_notes(text: str) -> None:
    seen: set[str] = set()
    for character in text:
        if character in seen or not ("一" <= character <= "龯"):
            continue
        seen.add(character)
        try:
            info = kanji_info(character)
        except ApiError:
            continue
        meanings = ", ".join(info.get("meanings", [])) or "—"
        on = ', '.join(info.get('on_readings', [])) or '—'
        kun = ', '.join(info.get('kun_readings', [])) or '—'
        print(f"    {BLUE}{character}{RESET}  {meanings} {DIM}({_ru(meanings)}){RESET}")
        print(f"       Он: {on} ({reading_romaji(on)})  |  Кун: {kun} ({reading_romaji(kun)})  |  JLPT: {info.get('jlpt', '—')}")


def _ru(text: str) -> str:
    return translate_to_russian(text) or "перевод недоступен"


def print_results(results: list[dict], translated: str | None = None, limit: int = 8, phrase: bool = False, details: bool = False) -> None:
    if translated and translated.lower() != "none":
        print(f"{DIM}Перевод запроса → {translated}{RESET}\n")
    if not results:
        print(f"{YELLOW}Ничего не найдено.{RESET}"); return
    for i, item in enumerate(results[:limit], 1):
        japanese = item.get("japanese", [{}])[0]
        word = japanese.get("word") or japanese.get("reading", "?")
        reading = japanese.get("reading", "")
        meanings = [m for sense in item.get("senses", []) for m in sense.get("english_definitions", [])]
        english = shorten("; ".join(meanings), width=100, placeholder="…") or "—"
        parts = [p for sense in item.get("senses", []) for p in sense.get("parts_of_speech", [])]
        tags = ", ".join(dict.fromkeys(item.get("tags", []) + item.get("jlpt", []) + parts))
        pronunciation = reading_romaji(reading) if reading else reading_romaji(word)
        print(f"{GREEN}{i}. {word}{RESET}  {reading if word != reading else ''}  [{pronunciation}]")
        print(f"   RU  {_ru(english)}\n   EN  {english}")
        if item.get('is_common'): tags = 'частое слово · ' + tags
        if tags: print(f"   {DIM}{tags}{RESET}")
        variants = [j.get('word') or j.get('reading', '') for j in item.get('japanese', [])[1:]]
        if details and variants: print(f"   Варианты: {', '.join(variants)}")
        if details: _print_kanji_notes(word)
        print()


def translate_phrase(args, store: Store) -> None:
    text = sys.stdin.read().strip() if args.query == "-" else args.query.strip()
    if not text:
        raise ApiError("Введите непустую фразу.")
    source = detect_language(text) if args.lang == "auto" else args.lang
    target = args.to or ("ru" if source == "ja" else "ja")
    result = translate(text, source, target)
    result_reading = phrase_romaji(result) if target == "ja" else ""
    print(f"{DIM}{source} → {target} · MyMemory{RESET}\n{GREEN}{result}{RESET}")
    if result_reading: print(f"{DIM}{result_reading}{RESET}")
    print()
    japanese = text if source == "ja" else result if target == "ja" else None
    if japanese:
        print("Разбор")
        for row in analyze(japanese):
            extra = f" · форма: {row['form']}" if args.details and row['form'] else ""
            print(f"  {row['word']}  {row['reading']}  [{row['romaji']}] · {row['pos']} · основа: {row['base']}{extra}")
            if row['hint']: print(f"    {row['hint']}")
            if args.details and row['pos'] in {'существительное', 'глагол', 'прилагательное', 'наречие'}:
                try:
                    matches = search_jisho(row['base'])
                    if matches:
                        senses = matches[0].get('senses', [])
                        gloss = '; '.join(senses[0].get('english_definitions', [])) if senses else ''
                        if gloss: print(f"    {_ru(gloss)} · {gloss}")
                except ApiError:
                    print("    Словарь временно недоступен.")
        print("\nМорфологический разбор Janome; подсказки частиц зависят от контекста.")
    if args.add:
        if not japanese:
            raise ApiError("Для карточки нужен японский исходный текст или перевод на японский.")
        meaning = result if source == "ja" else text
        print("Карточка сохранена." if store.add({'word': japanese, 'meaning': meaning}) else "Карточка уже существует.")


def discover(args) -> None:
    if args.limit < 1 or not args.query.strip():
        raise ApiError("Нужен непустой запрос и положительный --limit.")
    if args.command in {"anime", "manga"}:
        query = args.query
        if detect_language(query) == 'ru':
            query = translate(query, 'ru', 'en')
            print(f"{DIM}Поиск: {query}{RESET}\n")
        rows = search_media(query, args.command, args.limit,
                            genre=getattr(args, "genre", None), year=getattr(args, "year", None),
                            status=getattr(args, "status", None), sort=getattr(args, "sort", None))
        for i, row in enumerate(rows, 1):
            print(f"{GREEN}{i}. {row.get('title')}{RESET}")
            if row.get('title_japanese'): print(f"   {row['title_japanese']}")
            count = row.get('episodes') if args.command == 'anime' else row.get('chapters')
            unit = 'серий' if args.command == 'anime' else 'глав'
            print(f"   {row.get('type') or '—'} · {row.get('status') or '—'} · оценка {row.get('score') or '—'} · {count or '—'} {unit}")
            genres = ', '.join(g['name'] for g in row.get('genres', []))
            if genres: print(f"   {genres}")
            synopsis = row.get('synopsis') or 'Описание отсутствует.'
            print('   ' + (synopsis if args.details else shorten(synopsis, width=320, placeholder='…')))
            print(f"   {row.get('url', '')}\n")
        print("Источник: MyAnimeList через Jikan · фильтр SFW; названия переводятся приблизительно.")
    else:
        rows = search_topics(args.query, args.lang, args.limit)
        for i, row in enumerate(rows, 1):
            print(f"{GREEN}{i}. {row['title']}{RESET}\n{row.get('extract') or 'Краткое описание отсутствует.'}\n{row.get('fullurl', '')}\n")
        print("Источник: Wikipedia · энциклопедический поиск, проверяйте ссылки и источники статьи.")
    if not rows: print("Ничего не найдено. Попробуйте оригинальное название или другой запрос.")


def show_course(store: Store, course_id: str, lesson_number: str | None, mark_done: bool) -> None:
    course = course_by_id(course_id) or COURSES[0]
    progress = course_progress(store, course["id"])
    if not lesson_number:
        print(f"{course['title']} · {progress['done']}/{progress['total']} уроков завершено\n")
        for item in course["lessons"]:
            status = "+" if (item["id"] if "-" in item["id"] else f"N5-{str(item['id']).zfill(2)}") in progress["ids"] else "-"
            print(f"{status} {item['id']}  {item['title']}  [{item['kind']}]")
        print("\nОткрыть урок: jishocli learn 01 --course N5")
        return
    item = get_lesson(lesson_number if "-" in lesson_number else f"{course['id']}-{str(lesson_number).zfill(2)}")
    if not item or item["id"] not in {l["id"] for l in course["lessons"]}:
        raise ApiError(f"Урок {lesson_number} не найден в курсе {course['id']}.")
    print(f"УРОК {item['id']} · {item['title']}\nЦель: {item['goal']}\n\nОбъяснение\n{item['text']}\n\nГрамматика\n{item['grammar']}\n\nСинтаксис\n{item['syntax']}\n\nПроизношение\n{item['pronunciation']}\n\nПримеры и практика\n{item['practice']}\n\nМини-тест")
    for number, (question, answer) in enumerate(item["quiz"], 1):
        print(f"  {number}. {question}\n     Ответ: {answer}")
    print("\nИсточники:")
    for name, url in item["links"]:
        print(f"  {name}: {url}")
    if mark_done:
        complete(store, item["id"])
        print("\nУрок отмечен как завершённый.")
    else:
        print(f"\nОтметить: jishocli learn {item['id']} --done")


def run_books(query: str, limit: int) -> None:
    rows = search_books(query, limit)
    if not rows:
        print("Ничего не найдено.")
        return
    for i, row in enumerate(rows, 1):
        print(f"{i}. {row['title']} — {row['author']} ({row.get('year') or '—'})")
        if row.get("ia"):
            print(f"   читать: http://127.0.0.1:8765/book/read?ia={row['ia']}")
        print(f"   {('https://openlibrary.org' + row['key']) if row.get('key') else ''}")


def run_exam(level: str, count: int, seed: int | None) -> None:
    questions = exam_engine.generate_exam(level, count, seed)
    print(f"Демо-экзамен {level} · {len(questions)} вопросов. Вводите номер ответа (1-4), q — выход.\n")
    answers: dict[str, str] = {}
    for question in questions:
        print(f"{question['number']}. [{question['level']} · {exam_engine.SKILLS[question['skill']]}] {question['prompt']}")
        for i, option in enumerate(question["options"], 1):
            print(f"   {i}) {option}")
        while True:
            value = input("Ответ: ").strip()
            if value.lower() == "q":
                print("Экзамен прерван.")
                return
            if value.isdigit() and 1 <= int(value) <= 4:
                answers[str(question["number"])] = question["options"][int(value) - 1]
                break
            print("Введите число от 1 до 4.")
    result = exam_engine.evaluate(questions, answers)
    print(f"\nРезультат: {result['correct']}/{result['total']} ({result['percent']}%) · оценка {result['grade']}")
    print(f"Ориентировочный уровень: {result['estimate']}")
    print("\nПо навыкам:")
    for skill, pct in result["accuracy"].items():
        print(f"  {exam_engine.SKILLS[skill]}: {pct}%")
    print("\nСильные стороны: " + ", ".join(exam_engine.SKILLS[s] for s, _ in result["strongest"]))
    print("Слабые стороны: " + ", ".join(exam_engine.SKILLS[s] for s, _ in result["weakest"]))
    print("\nЧто подучить:")
    for line in result["recommendations"]:
        print(f"  - {line}")


def show_courses(store: Store) -> None:
    print("Курсы jishocli:\n")
    for course in COURSES:
        p = course_progress(store, course["id"])
        print(f"{course['id']}  {course['title']} · {p['done']}/{p['total']} уроков")
    print("\nВыбрать: jishocli learn --course N4 01")


def study(store: Store) -> None:
    due = store.due()
    if not due: print("На сегодня всё. Добавьте слова: jishocli add 日本語 --reading にほんご --meaning language"); return
    print(f"Карточек к повторению: {len(due)}  (Enter — показать ответ, 0–5 — оценка)\n")
    for card in due:
        print(f"\n{GREEN}{card['word']}{RESET}"); input("Enter — показать ответ: ")
        print(f"{card.get('reading', '')}  —  {card.get('meaning', '')}")
        while True:
            answer = input("Оценка 0–5 (0 забыл, 5 легко; q — выйти): ").strip()
            if answer.lower() == 'q': return
            if answer.isdigit() and 0 <= int(answer) <= 5: store.review(card, int(answer)); break
            print("Введите число от 0 до 5.")
    print("Сессия завершена. Отличная работа!")


def show_kana(script: str, row: str) -> None:
    tables = {"basic": kana.BASIC, "dakuten": kana.DAKUTEN, "yoon": kana.YOON}
    selected = list(tables.items()) if row == "all" else [(row, tables[row])]
    for name, table in selected:
        print(f"— {name} —")
        for h, k, r, hint in table:
            if script == "hira":
                print(f"{h}  {r:5} {hint}")
            elif script == "kata":
                print(f"{k}  {r:5} {hint}")
            else:
                print(f"{h} {k}  {r:5} {hint}")
        print()


def show_daily(store: Store) -> None:
    jp, reading, ru = daily_word()
    print(f"Слово дня: {jp}  {reading}  [{reading_romaji(reading)}]\n{ru}")


def run_export(store: Store, fmt: str, out: str | None) -> None:
    content = store.export_csv() if fmt == "csv" else store.export_anki()
    if out:
        Path(out).write_text(content, encoding="utf-8")
        print(f"Экспортировано {len(store.cards)} карточек → {out}")
    else:
        print(content, end="")


def run_learn_from(args, store: Store) -> None:
    text = args.text
    if args.anime or args.manga:
        kind = "anime" if args.anime else "manga"
        rows = search_media(args.anime or args.manga, kind, 1)
        if not rows:
            raise ApiError("Ничего не найдено.")
        text = rows[0].get("title_japanese") or rows[0]["title"]
        print(f"Произведение: {rows[0]['title']} ({text})\n")
    if not text:
        raise ApiError("Укажите японский текст или --anime/--manga.")
    vocab = learn_vocab(text, args.limit)
    if not vocab:
        print("Не удалось выделить слова.")
        return
    for v in vocab:
        print(f"{v['word']}  {v['reading']}  [{v['romaji']}] · {v['pos']}\n   {v['meaning'] or '—'}")
        if args.add:
            store.add({"word": v["base"], "reading": v["reading"], "romaji": v["romaji"],
                       "meaning": v["meaning"], "source": "learn-from"})
    if args.add:
        print("Слова сохранены в карточки.")


def run_read(args) -> None:
    results = mangadex_search(args.query, 3)
    if not results:
        raise ApiError("Манга не найдена на MangaDex.")
    manga = results[0]
    print(f"{manga['title']} ({manga['title_japanese']}) · {manga['status'] or '—'} · {manga['year'] or '—'}")
    chapters = mangadex_chapters(manga["id"], args.lang)
    if not chapters:
        raise ApiError(f"Нет доступных глав на языке {args.lang}. Попробуйте --lang ja или другой язык.")
    if not args.chapter:
        print(f"Глав: {len(chapters)} (первые 20):")
        for c in chapters[:20]:
            print(f"  гл. {c['chapter']}  {c['title']}  · {c['pages'] or '?'} стр.")
        print("Открыть: jishocli read 'название' --chapter 1 [--download DIR]")
        return
    chapter = next((c for c in chapters if str(c["chapter"]) == str(args.chapter)), None)
    if not chapter:
        raise ApiError(f"Глава {args.chapter} не найдена.")
    pages = mangadex_pages(chapter["id"])
    print(f"Глава {chapter['chapter']}: {pages['count']} страниц")
    if args.download:
        for i, url in enumerate(pages["urls"], 1):
            size = download_file(url, Path(args.download) / f"{i:03d}.jpg")
            print(f"  {i:03d}.jpg ({size // 1024} КБ)")
        print(f"Сохранено в {args.download}")
    else:
        for i, url in enumerate(pages["urls"], 1):
            print(f"{i:3}. {url}")


def run_quiz(kind: str, count: int, seed: int | None, mode: str = "choice") -> None:
    questions = quiz_engine.generate(kind, count, seed, mode=mode)
    print(f"Тест: {kind} · {mode} · {len(questions)} вопросов" + (f" · seed {seed}" if seed is not None else ""))
    print("q — выход.\n")
    score = 0
    mistakes = []
    for i, question in enumerate(questions, 1):
        prompt = question["prompt"]
        if question["kind"] == "audio" and question.get("speak"):
            prompt = f"Аудио: прочитайте вслух {question['speak']} — {prompt}"
        print(f"{i}. [{question['kind']}] {prompt}")
        if mode == "recall":
            answer = input("Ваш ответ: ").strip()
            chosen = answer
        else:
            for j, option in enumerate(question["options"], 1):
                print(f"   {j}) {option}")
            while True:
                answer = input("Номер ответа: ").strip()
                if answer.lower() == "q":
                    print(f"\nРезультат: {score}/{i - 1}")
                    return
                if answer.isdigit() and 1 <= int(answer) <= 4:
                    break
                print("Введите число от 1 до 4.")
            chosen = question["options"][int(answer) - 1]
        if chosen.lower() == question["answer"].lower():
            score += 1
            print(f"   Верно. {question['explain']}\n")
        else:
            mistakes.append((prompt, question["answer"], question.get("speak", "")))
            print(f"   Неверно. Правильно: {question['answer']}. {question['explain']}\n")
    print(f"Результат: {score}/{len(questions)}")
    if mistakes:
        print("\nОшибки для повторения:")
        for prompt, answer, spoken in mistakes:
            print(f"  {prompt} -> {answer}" + (f" (аудио: {spoken})" if spoken else ""))


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if not args.command: _parser().print_help(); return
    store = Store()
    try:
        if getattr(args, "proxy", None) and args.command != "web":
            configure_proxy(args.proxy)
        if args.command in {"phrase", "translate", "tr"}:
            translate_phrase(args, store)
        elif args.command in {"anime", "manga", "facts", "explore"}:
            discover(args)
        elif args.command == "cards":
            for i, c in enumerate(store.cards, 1):
                print(f"{i}. {c['word']}  {c['reading']}  [{c.get('romaji') or reading_romaji(c.get('reading', ''))}]\n   {c['meaning']} · box {c.get('box', 0)} · повтор {c['due']}")
                if c.get('example'): print(f"   Пример: {c['example']}")
            if not store.cards: print("Пока пусто. Используйте search --add N или phrase --add.")
        elif args.command in {"search", "s"}:
            if not args.query.strip() or args.limit < 1:
                raise ApiError("Запрос не должен быть пустым, а --limit должен быть больше нуля.")
            language = args.lang.lower()
            if language == "auto":
                language = detect_language(args.query)
            translated = None if language in {"en", "ja"} else translate_to_english(args.query, language)
            if language not in {"en", "ja"} and not translated:
                raise ApiError("Перевод запроса недоступен. Повторите позже или введите английский/японский запрос.")
            results = search_jisho(translated or args.query)
            print_results(results, translated, args.limit, details=args.details)
            if args.add is not None:
                if not 1 <= args.add <= min(len(results), args.limit):
                    raise ApiError("--add должен указывать номер показанного результата.")
                item = results[args.add - 1]
                japanese = item['japanese'][0]
                meaning = '; '.join(item.get('senses', [{}])[0].get('english_definitions', []))
                card = {'word': japanese.get('word') or japanese.get('reading'), 'reading': japanese.get('reading', ''), 'meaning': _ru(meaning) + ' · ' + meaning}
                print("Карточка сохранена." if store.add(card) else "Карточка уже существует.")
        elif args.command == "kanji":
            if len(args.character) != 1 or not ("一" <= args.character <= "龯"):
                raise ApiError("Укажите один иероглиф, например: kanji 学 --save gaku.svg")
            character = args.character
            if args.strokes:
                Path(args.save).write_text(kanji_strokes(character), encoding="utf-8")
                print(f"SVG с порядком черт сохранён: {args.save} (KanjiVG, CC BY-SA)")
            else:
                print(f"Изображение сохранено: {save_svg(character, args.save)}")
        elif args.command in {"quiz", "test"}:
            run_quiz(args.type, args.count, args.seed, args.mode)
        elif args.command == "kana":
            show_kana(args.script, args.row)
        elif args.command == "daily":
            show_daily(store)
        elif args.command == "export":
            run_export(store, args.format, args.out)
        elif args.command == "learn-from":
            run_learn_from(args, store)
        elif args.command == "read":
            run_read(args)
        elif args.command == "add": print("Добавлено." if store.add(vars(args)) else "Это слово уже есть в карточках.")
        elif args.command in {"study", "review"}: study(store)
        elif args.command == "due":
            due = store.due()
            for c in due: print(f"{c['word']}  {c['reading']} — {c['meaning']} (box {c['box']})")
            if not due: print("Нет карточек на сегодня.")
        elif args.command == "stats":
            cards = store.cards
            print(f"Всего карточек: {len(cards)}\nК повторению: {len(store.due())}\nВыучено (box 3+): {sum(c.get('box', 0) >= 3 for c in cards)}\nСерия дней: {store.streak()}")
        elif args.command in {"learn", "course"}:
            show_course(store, args.course, args.lesson, args.done)
        elif args.command == "courses":
            show_courses(store)
        elif args.command == "books":
            run_books(args.query, args.limit)
        elif args.command == "exam":
            run_exam(args.level, args.count, args.seed)
        elif args.command == "ocr":
            print(ocr_local(args.image, args.lang))
        elif args.command == "import":
            added = store.import_json(Path(args.file).read_text(encoding="utf-8"))
            print(f"Импортировано карточек: {added}")
        elif args.command == "goal":
            if args.count is None:
                print(f"Текущая цель: {store.goal} · сегодня повторено: {store.today_count()}")
            else:
                store.set_goal(args.count)
                print(f"Новая цель: {store.goal}")
        elif args.command == "speak":
            data = tts_audio(args.text)
            Path(args.out).write_bytes(data)
            print(f"Озвучка сохранена: {args.out} ({len(data) // 1024} КБ)")
        elif args.command == "web":
            configure_proxy(args.proxy)
            serve(args.host, args.port)
    except (ApiError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr); raise SystemExit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nЗавершено. Сохранённый прогресс не потерян.")
