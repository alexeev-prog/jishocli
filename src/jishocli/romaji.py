"""Small dependency-free kana to Hepburn romanization helper."""

from __future__ import annotations

import re

_BASE = {
    "あ":"a","い":"i","う":"u","え":"e","お":"o","か":"ka","き":"ki","く":"ku","け":"ke","こ":"ko",
    "さ":"sa","し":"shi","す":"su","せ":"se","そ":"so","た":"ta","ち":"chi","つ":"tsu","て":"te","と":"to",
    "な":"na","に":"ni","ぬ":"nu","ね":"ne","の":"no","は":"ha","ひ":"hi","ふ":"fu","へ":"he","ほ":"ho",
    "ま":"ma","み":"mi","む":"mu","め":"me","も":"mo","や":"ya","ゆ":"yu","よ":"yo","ら":"ra","り":"ri","る":"ru","れ":"re","ろ":"ro",
    "わ":"wa","を":"wo","ん":"n","が":"ga","ぎ":"gi","ぐ":"gu","げ":"ge","ご":"go","ざ":"za","じ":"ji","ず":"zu","ぜ":"ze","ぞ":"zo",
    "だ":"da","ぢ":"ji","づ":"zu","で":"de","ど":"do","ば":"ba","び":"bi","ぶ":"bu","べ":"be","ぼ":"bo","ぱ":"pa","ぴ":"pi","ぷ":"pu","ぺ":"pe","ぽ":"po",
    "ぁ":"a","ぃ":"i","ぅ":"u","ぇ":"e","ぉ":"o","ゃ":"ya","ゅ":"yu","ょ":"yo","ゔ":"vu",
}
_COMBOS = {
    "きゃ":"kya","きゅ":"kyu","きょ":"kyo","しゃ":"sha","しゅ":"shu","しょ":"sho","ちゃ":"cha","ちゅ":"chu","ちょ":"cho",
    "にゃ":"nya","にゅ":"nyu","にょ":"nyo","ひゃ":"hya","ひゅ":"hyu","ひょ":"hyo","みゃ":"mya","みゅ":"myu","みょ":"myo",
    "りゃ":"rya","りゅ":"ryu","りょ":"ryo","ぎゃ":"gya","ぎゅ":"gyu","ぎょ":"gyo","じゃ":"ja","じゅ":"ju","じょ":"jo",
    "びゃ":"bya","びゅ":"byu","びょ":"byo","ぴゃ":"pya","ぴゅ":"pyu","ぴょ":"pyo","てぃ":"ti","でぃ":"di","ふぁ":"fa","ふぃ":"fi","ふぇ":"fe","ふぉ":"fo",
}


def _hiragana(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヴ" else c for c in text)


def romaji(text: str) -> str:
    """Convert kana while leaving kanji, Latin text and punctuation intact."""
    text = _hiragana(text)
    output: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "ー":
            if output and output[-1] and output[-1][-1] in "aiueo":
                output.append(output[-1][-1])
            i += 1
            continue
        if char == "っ":
            following = romaji(text[i + 1:i + 2]) if i + 1 < len(text) else ""
            output.append(following[:1] if following and following[0].isalpha() else "")
            i += 1
            continue
        pair = text[i:i + 2]
        if pair in _COMBOS:
            output.append(_COMBOS[pair]); i += 2; continue
        output.append(_BASE.get(char, char)); i += 1
    value = "".join(output)
    # Japanese particle は is pronounced wa in context; this is especially
    # useful for phrase study, while dictionary readings remain literal.
    value = re.sub(r"(?<=\s)ha(?=\s|$)", "wa", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def reading_romaji(reading: str) -> str:
    return romaji(reading).replace("wo", "o")


def phrase_romaji(text: str) -> str:
    """Romanize a sentence and add learner-friendly word boundaries."""
    try:
        from janome.tokenizer import Tokenizer
        pieces: list[tuple[str, str]] = []
        for token in Tokenizer().tokenize(text):
            if token.part_of_speech.startswith("記号"):
                pieces.append((token.surface, "記号"))
                continue
            reading = token.reading if token.reading != "*" else token.surface
            pieces.append((reading_romaji(reading), token.part_of_speech.split(",")[0]))
        rendered: list[str] = []
        previous_pos = ""
        for value, pos in pieces:
            # Japanese auxiliary verbs are written as one pronunciation unit:
            # ござい + ます -> gozaimasu, 食べ + ました -> tabemashita.
            if rendered and pos == "助動詞" and previous_pos != "感動詞":
                rendered[-1] += value
            else:
                rendered.append(value)
            previous_pos = pos
        value = " ".join(rendered)
        return re.sub(r"\s+([、。！？,.!?])", r"\1", value)
    except ImportError:
        return romaji(text)
