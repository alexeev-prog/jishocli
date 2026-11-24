"""Local morphological analysis; explanations are hints, not a syntax parser."""

from functools import lru_cache
from .romaji import reading_romaji

POS = {"名詞": "существительное", "動詞": "глагол", "形容詞": "прилагательное",
       "副詞": "наречие", "助詞": "частица", "助動詞": "вспомогательное слово",
       "連体詞": "определение", "接続詞": "союз", "感動詞": "междометие",
       "記号": "знак", "接頭詞": "приставка", "フィラー": "слово-паразит"}
PARTICLES = {"は": "тема высказывания (читается wa)", "が": "подлежащее / выделение",
             "を": "объект действия (читается o)", "に": "цель, время или место назначения",
             "で": "место действия или средство", "へ": "направление (читается e)",
             "の": "принадлежность / определение", "と": "связь, цитирование или совместность",
             "も": "также", "か": "вопрос / альтернатива", "ね": "ожидание согласия",
             "よ": "акцент на новой информации"}


@lru_cache(maxsize=1)
def _tokenizer():
    from janome.tokenizer import Tokenizer
    return Tokenizer()


def analyze(text: str) -> list[dict]:
    rows = []
    for token in _tokenizer().tokenize(text):
        pos = token.part_of_speech.split(",")[0]
        if pos == "記号" or not token.surface.strip():
            continue
        reading = token.reading if token.reading != "*" else ""
        reading = "".join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヴ' else c for c in reading)
        rows.append({"word": token.surface, "reading": reading,
                     "romaji": reading_romaji(reading),
                     "base": token.base_form if token.base_form != "*" else token.surface,
                     "pos": POS.get(pos, pos), "hint": PARTICLES.get(token.surface, "") if pos == "助詞" else "",
                     "form": token.infl_form if token.infl_form != "*" else ""})
    return rows
