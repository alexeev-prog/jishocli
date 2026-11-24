"""Random quiz generator: kana, vocabulary, particles, grammar, kanji, phonetics, audio."""

from __future__ import annotations

import random

from . import kana

VOCAB = [
    ("猫", "ねこ", "кот"), ("犬", "いぬ", "собака"), ("水", "みず", "вода"),
    ("本", "ほん", "книга"), ("学校", "がっこう", "школа"), ("先生", "せんせい", "учитель"),
    ("学生", "がくせい", "студент"), ("友達", "ともだち", "друг"), ("食べる", "たべる", "есть"),
    ("飲む", "のむ", "пить"), ("見る", "みる", "смотреть"), ("行く", "いく", "идти"),
    ("大きい", "おおきい", "большой"), ("小さい", "ちいさい", "маленький"),
    ("新しい", "あたらしい", "новый"), ("古い", "ふるい", "старый"),
    ("今日", "きょう", "сегодня"), ("明日", "あした", "завтра"), ("昨日", "きのう", "вчера"),
    ("朝", "あさ", "утро"), ("夜", "よる", "ночь"), ("電車", "でんしゃ", "поезд"),
    ("駅", "えき", "станция"), ("部屋", "へや", "комната"), ("時間", "じかん", "время"),
    ("日本語", "にほんご", "японский язык"), ("日本", "にほん", "Япония"),
    ("山", "やま", "гора"), ("川", "かわ", "река"), ("花", "はな", "цветок"),
    ("空", "そら", "небо"), ("海", "うみ", "море"), ("雨", "あめ", "дождь"),
    ("雪", "ゆき", "снег"), ("風", "かぜ", "ветер"), ("星", "ほし", "звезда"),
    ("手", "て", "рука"), ("足", "あし", "нога"), ("目", "め", "глаз"),
    ("耳", "みみ", "ухо"), ("口", "くち", "рот"), ("心", "こころ", "сердце"),
    ("朝ご飯", "あさごはん", "завтрак"), ("昼", "ひる", "полдень"),
    ("仕事", "しごと", "работа"), ("電話", "でんわ", "телефон"),
    ("切符", "きっぷ", "билет"), ("荷物", "にもつ", "багаж"),
    ("楽しい", "たのしい", "весёлый"), ("難しい", "むずかしい", "сложный"),
    ("易しい", "やさしい", "лёгкий"), ("静か", "しずか", "тихий"),
    ("元気", "げんき", "здоровый"), ("好き", "すき", "любимый"),
]

PARTICLES = [
    ("私＿学生です。", "は", "тема высказывания", ["が", "を", "に"]),
    ("日本語＿勉強します。", "を", "прямой объект", ["は", "で", "の"]),
    ("学校＿行きます。", "に", "направление", ["を", "が", "と"]),
    ("図書館＿本を読みます。", "で", "место действия", ["に", "を", "へ"]),
    ("これ＿本です。", "は", "тема", ["を", "に", "で"]),
    ("友達＿映画を見ます。", "と", "совместность", ["で", "を", "が"]),
    ("七時＿起きます。", "に", "точное время", ["で", "を", "は"]),
    ("日本＿語", "の", "принадлежность", ["は", "に", "を"]),
    ("誰＿来ましたか。", "が", "подлежащее при вопросе", ["は", "を", "で"]),
    ("東京＿大阪まで新幹線で行きます。", "から", "отправная точка", ["まで", "に", "で"]),
]

GRAMMAR = [
    ("Отрицание 食べます:", "食べません", ["食べないです", "食べませんでした", "食べるません"]),
    ("Прошедшее время 行きます:", "行きました", ["行きますでした", "行ったます", "行きません"]),
    ("Вопрос к 学生です:", "学生ですか", ["学生です？か", "学生かです", "ですか学生"]),
    ("Форма て от 読む:", "読んで", ["読みて", "読むて", "読んて"]),
    ("Форма て от 食べる:", "食べて", ["食べって", "食べまして", "食べるて"]),
    ("Отрицание おいしい:", "おいしくない", ["おいしいない", "おいしくありませんか", "おいしいくない"]),
    ("Желание «хочу есть»:", "食べたいです", ["食べほしいです", "食べるたいです", "食べたいでした"]),
    ("Вежливая просьба «посмотрите»:", "見てください", ["見るください", "見てくだしい", "見ってくさい"]),
    ("«Могу плавать»:", "泳げます", ["泳ぎます", "泳べます", "泳きれます"]),
    ("Отрицание あります:", "ありません", ["ないます", "ありない", "ありませんでした"]),
]

KANJI = [
    ("日", "день / солнце", ["месяц", "огонь", "дерево"]),
    ("月", "месяц / луна", ["день", "вода", "гора"]),
    ("火", "огонь", ["вода", "земля", "металл"]),
    ("水", "вода", ["огонь", "дерево", "ветер"]),
    ("木", "дерево", ["камень", "трава", "лес"]),
    ("山", "гора", ["река", "поле", "остров"]),
    ("川", "река", ["гора", "море", "озеро"]),
    ("人", "человек", ["ребёнок", "женщина", "друг"]),
    ("大", "большой", ["маленький", "средний", "высокий"]),
    ("小", "маленький", ["большой", "короткий", "узкий"]),
    ("学", "учёба", ["школа", "книга", "знание"]),
    ("生", "жизнь", ["смерть", "учитель", "год"]),
    ("先", "впереди", ["сзади", "сейчас", "потом"]),
    ("何", "что", ["кто", "где", "когда"]),
    ("時", "время", ["минута", "день", "год"]),
]

KANJI_READINGS = [
    ("日", "にち / ひ", "день"), ("月", "げつ / つき", "месяц"),
    ("火", "か / ひ", "огонь"), ("水", "すい / みず", "вода"),
    ("木", "もく / き", "дерево"), ("金", "きん / かね", "металл"),
    ("土", "ど / つち", "земля"), ("人", "じん / ひと", "человек"),
    ("学", "がく / まなぶ", "учиться"), ("生", "せい / いきる", "жизнь"),
    ("食", "しょく / たべる", "еда"), ("飲", "いん / のむ", "питьё"),
]

PHONETICS = [
    ("Как читается частица は?", "wa", ["ha", "ba", "fa"]),
    ("Как читается частица を?", "o", ["wo", "u", "wa"]),
    ("Как читается частица へ?", "e", ["he", "be", "we"]),
    ("Что делает っ в がっこう?", "удваивает согласный", ["удлиняет гласный", "означает паузу", "меняет тон"]),
    ("Что делает ー в コーヒー?", "удлиняет гласную", ["удваивает согласный", "ставит ударение", "означает вопрос"]),
    ("Сколько мор в こんにちは?", "5", ["4", "3", "6"]),
    ("Как читается じ?", "ji", ["zi", "si", "di"]),
    ("Как читается つ?", "tsu", ["tu", "su", "cu"]),
    ("Как читается ふ?", "fu", ["hu", "pu", "bu"]),
    ("Разница ビール и ビル?", "долгая гласная", ["дакутэн", "тон", "нет разницы"]),
]

SENTENCES = [
    ("私は毎日日本語を勉強します。", "watashi wa mainichi nihongo o benkyou shimasu",
     "Я каждый день изучаю японский.", ["Я уже выучил японский.", "Я не люблю японский.", "Я читаю японские книги."]),
    ("明日は友達と映画を見ます。", "ashita wa tomodachi to eiga o mimasu",
     "Завтра я смотрю фильм с другом.", ["Вчера я смотрел фильм один.", "Завтра я иду в школу.", "Сегодня друг читает книгу."]),
    ("このケーキはおいしそうです。", "kono keeki wa oishisou desu",
     "Этот торт выглядит вкусным.", ["Этот торт уже съеден.", "Этот торт очень дорогой.", "Я не пробовал этот торт."]),
    ("駅はどこですか。", "eki wa doko desu ka",
     "Где находится станция?", ["Когда открыта станция?", "Как называется станция?", "Сколько стоит билет?"]),
    ("日本語が少し話せます。", "nihongo ga sukoshi hanasemasu",
     "Я немного говорю по-японски.", ["Я не понимаю по-японски.", "Я учу английский.", "Я пишу по-японски."]),
    ("図書館で本を読みました。", "toshokan de hon o yomimashita",
     "Я читал книгу в библиотеке.", ["Я купил книгу в магазине.", "Я писал письмо дома.", "Я потерял книгу в парке."]),
]

TYPES = ["kana", "romaji", "vocab", "particle", "grammar", "kanji",
         "kanji-reading", "phonetics", "sentence", "audio", "mixed"]


def _question(kind: str, prompt: str, answer: str, wrong: list[str], explain: str,
              rng: random.Random, speak: str = "") -> dict:
    options = wrong[:3] + [answer]
    while len(options) < 4:
        options.append("другой вариант")
    rng.shuffle(options)
    return {"kind": kind, "prompt": prompt, "options": options[:4], "answer": answer,
            "explain": explain, "speak": speak, "points": 1}


def _kana_question(rng: random.Random, reverse: bool = False) -> dict:
    h, k, r, hint = rng.choice(kana.ALL)
    use_kata = rng.random() < 0.5
    char = k if use_kata else h
    script = "катакана" if use_kata else "хирагана"
    if reverse:
        pool = [x for x in kana.ALL if x[2] != r]
        wrong = [(x[1] if use_kata else x[0]) for x in rng.sample(pool, 3)]
        return _question("romaji", f"Какой знак ({script}) читается «{r}»?", char, wrong, hint, rng, speak=char)
    pool = [x[2] for x in kana.ALL if x[2] != r]
    return _question("kana", f"Как читается {char} ({script})?", r, rng.sample(pool, 3), hint, rng, speak=char)


def daily_word(day=None):
    from datetime import date
    day = day or date.today()
    return VOCAB[day.toordinal() % len(VOCAB)]


def _make_question(pick: str, rng: random.Random) -> dict:
    if pick in {"kana", "romaji"}:
        return _kana_question(rng, reverse=pick == "romaji")
    if pick == "vocab":
        jp, reading, ru = rng.choice(VOCAB)
        wrong = [v[2] for v in rng.sample([v for v in VOCAB if v[2] != ru], 3)]
        return _question("vocab", f"Что значит {jp} ({reading})?", ru, wrong,
                         f"{jp} читается {reading}", rng, speak=jp)
    if pick == "particle":
        sentence, answer, why, wrong = rng.choice(PARTICLES)
        return _question("particle", sentence.replace("＿", "＿＿"), answer, wrong,
                         f"Частица {answer}: {why}", rng)
    if pick == "grammar":
        prompt, answer, wrong = rng.choice(GRAMMAR)
        return _question("grammar", prompt, answer, wrong, f"Правильно: {answer}", rng)
    if pick == "kanji":
        ch, meaning, wrong = rng.choice(KANJI)
        return _question("kanji", f"Что значит иероглиф {ch}?", meaning, wrong,
                         f"{ch} — {meaning}", rng, speak=ch)
    if pick == "kanji-reading":
        ch, reading, meaning = rng.choice(KANJI_READINGS)
        pool = [r[1] for r in KANJI_READINGS if r[0] != ch]
        return _question("kanji-reading", f"Как читается {ch} ({meaning})?", reading,
                         rng.sample(pool, 3), f"{ch} — {reading}", rng, speak=ch)
    if pick == "sentence":
        jp, reading, ru, wrong = rng.choice(SENTENCES)
        return _question("sentence", f"Переведите: {jp}", ru, wrong,
                         f"{jp} — {reading}", rng, speak=jp)
    if pick == "audio":
        if rng.random() < 0.5:
            h, k, r, hint = rng.choice(kana.ALL)
            char = k if rng.random() < 0.5 else h
            pool = [x[2] for x in kana.ALL if x[2] != r]
            return _question("audio", "Прослушайте и выберите чтение:", r,
                             rng.sample(pool, 3), hint, rng, speak=char)
        jp, reading, ru = rng.choice(VOCAB)
        wrong = [v[2] for v in rng.sample([v for v in VOCAB if v[2] != ru], 3)]
        return _question("audio", "Прослушайте и выберите перевод:", ru, wrong,
                         f"{jp} ({reading})", rng, speak=jp)
    prompt, answer, wrong = rng.choice(PHONETICS)
    return _question("phonetics", prompt, answer, wrong, f"Правильно: {answer}", rng)


def generate(kind: str = "mixed", count: int = 10, seed: int | None = None,
             mode: str = "choice") -> list[dict]:
    """Generate a quiz. mode='choice' uses options, mode='recall' expects typed answers."""
    if kind not in TYPES:
        raise ValueError(f"Неизвестный тип теста: {kind}. Доступны: {', '.join(TYPES)}")
    if mode not in {"choice", "recall"}:
        raise ValueError("mode должен быть choice или recall")
    rng = random.Random(seed)
    types = [t for t in TYPES if t != "mixed"]
    if kind == "mixed":
        rng.shuffle(types)
        plan = (types * ((count // len(types)) + 1))[:count]
    else:
        plan = [kind] * count
    questions: list[dict] = []
    used: set[tuple[str, str]] = set()
    for pick in plan:
        question = None
        for _ in range(12):
            candidate = _make_question(pick, rng)
            if (candidate["prompt"], candidate["answer"]) not in used:
                question = candidate
                break
        question = question or _make_question(pick, rng)
        used.add((question["prompt"], question["answer"]))
        question["mode"] = mode
        questions.append(question)
    return questions


def from_lesson_quiz(items: list[tuple[str, str]], seed: int | None = None) -> list[dict]:
    """Convert lesson questions into interactive quiz questions."""
    rng = random.Random(seed)
    answers = [a for _, a in items]
    extras = answers + ["не подходит", "зависит от контекста", "другой вариант"]
    questions = []
    for i, (question, answer) in enumerate(items, 1):
        pool = [a for a in extras if a != answer]
        wrong = rng.sample(pool, min(3, len(pool)))
        item = _question("lesson", question, answer, wrong, f"Правильно: {answer}", rng)
        item.update(mode="choice", number=i)
        questions.append(item)
    return questions
