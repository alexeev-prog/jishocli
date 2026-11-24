"""HTTP engine and API clients: Jisho, MyMemory, AniList/Tenrai/Jikan, Wikipedia, KanjiVG."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import lru_cache
from hashlib import sha256
from html import unescape
from pathlib import Path
from datetime import timedelta
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen
from concurrent.futures import ThreadPoolExecutor

LOGGER = logging.getLogger("jishocli.api")
UA = {"User-Agent": "jishocli/0.3", "Accept": "application/json"}


class ApiError(RuntimeError):
    pass


_opener = None
_proxy_url: str | None = None


def configure_proxy(proxy: str | None = None) -> None:
    """Explicit proxy wins; otherwise HTTP(S)_PROXY env vars are respected."""
    global _opener, _proxy_url
    _proxy_url = (proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
                  or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
    if _proxy_url:
        _opener = build_opener(ProxyHandler({"http": _proxy_url, "https": _proxy_url}))
    else:
        _opener = None


def proxy_status() -> str:
    return (_proxy_url or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or "не используется")


def _open(request: Request, timeout: float):
    """Try the configured proxy first; on network failure fall back to direct.

    This fixes setups where a local proxy (e.g. privoxy on 8118) cannot
    reach a host but the direct connection works — and vice versa.
    """
    attempts = []
    if _opener is not None:
        attempts.append(("proxy", _opener.open))
    attempts.append(("direct", urlopen))
    last: Exception | None = None
    for label, open_ in attempts:
        try:
            return open_(request, timeout=timeout)
        except HTTPError:
            raise  # status errors are handled by the caller, not a network issue
        except Exception as exc:
            LOGGER.warning("%s connection failed: %s", label, exc)
            last = exc
    raise last if last else ApiError("нет доступного соединения")


def _friendly(exc: Exception | str) -> str:
    detail = str(exc)
    low = detail.lower()
    if "handshake" in low or "ssl" in low or "certificate" in low:
        return "TLS/SSL-соединение не установлено; проверьте сеть, прокси или сертификаты"
    if "timed out" in low or "timeout" in low:
        return "сервис не ответил вовремя"
    if "name or service not known" in low or "nodename" in low or "getaddrinfo" in low:
        return "DNS не разрешил имя сервиса; проверьте сеть"
    if "refused" in low:
        return "соединение отклонено (прокси или сервис не запущен)"
    return detail


def _request(url: str, payload: dict | None = None, timeout: float = 8, attempts: int = 2) -> dict:
    data = None
    headers = dict(UA)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last: Exception | None = None
    for attempt in range(attempts):
        request = Request(url, data=data, headers=headers)
        try:
            with _open(request, timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 429:
                last = ApiError("превышен лимит запросов сервиса (429); подождите минуту")
            else:
                try:
                    payload = json.loads(exc.read().decode("utf-8", "replace"))
                    if isinstance(payload, dict) and "errors" in payload:
                        return payload  # GraphQL errors are useful to the caller
                except Exception:
                    pass
                last = ApiError(f"сервис вернул HTTP {exc.code}")
        except ApiError:
            raise
        except Exception as exc:
            last = exc
        if attempt + 1 < attempts:
            time.sleep(0.3 * (attempt + 1))
    hint = f" Прокси: {proxy_status()}." if _proxy_url else " Можно задать --proxy URL или HTTPS_PROXY."
    raise ApiError(f"Сервис временно недоступен: {_friendly(last or 'неизвестная ошибка')}.{hint} Попробуйте ещё раз позже.") from last


def _get(url: str, timeout: float = 8) -> dict:
    return _request(url, timeout=timeout)


def _get_text(url: str, timeout: float = 10) -> str:
    request = Request(url, headers={"User-Agent": UA["User-Agent"]})
    try:
        with _open(request, timeout) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        raise ApiError(f"Не удалось загрузить {url.split('/')[2]}: {_friendly(exc)}") from exc


def cached_image(url: str, max_age_days: int = 30) -> bytes:
    """Disk cache for manga page images (proxy-friendly, offline re-read)."""
    cache = Path.home() / ".jishocli" / "cache" / "manga"
    path = cache / (sha256(url.encode("utf-8")).hexdigest() + ".jpg")
    if path.exists() and time.time() - path.stat().st_mtime < max_age_days * 86400:
        return path.read_bytes()
    data = fetch_bytes(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _tts_split(text: str, limit: int = 170) -> list[str]:
    parts, current = [], ""
    for piece in text.replace("\n", " ").split(" "):
        candidate = f"{current} {piece}".strip()
        if len(candidate) > limit and current:
            parts.append(current)
            current = piece
        else:
            current = candidate
    if current:
        parts.append(current)
    result = []
    for part in parts:
        while len(part) > limit:  # CJK text has no spaces
            result.append(part[:limit])
            part = part[limit:]
        if part:
            result.append(part)
    return result or [text]


def _tts_chunk(text: str, lang: str, cache: Path) -> bytes:
    key = sha256(f"v2:{lang}:{text}".encode("utf-8")).hexdigest()
    path = cache / f"{key}.mp3"
    if path.exists() and path.stat().st_size > 500:
        return path.read_bytes()
    variants = (
        {"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": text},
        {"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": text, "textlen": str(len(text))},
        {"ie": "UTF-8", "client": "translate-web", "tl": lang, "q": text},
    )
    last: Exception | None = None
    for params in variants:
        url = "https://translate.google.com/translate_tts?" + urlencode(params)
        request = Request(url, headers={"User-Agent": "Mozilla/5.0",
                                        "Referer": "https://translate.google.com/",
                                        "Accept-Language": "ja,en;q=0.8"})
        try:
            with _open(request, 12) as response:
                data = response.read()
        except Exception as exc:
            last = exc
            continue
        if len(data) > 500 and (data.startswith(b"\xff") or data.startswith(b"ID3")):
            path.write_bytes(data)
            return data
    if last:
        raise ApiError(f"Озвучка недоступна: {_friendly(last)}") from last
    raise ApiError("Сервис озвучки вернул пустой или неверный ответ.")


def tts_audio(text: str, lang: str = "ja") -> bytes:
    """Consistent Japanese TTS with a disk cache, provider retries and chunking."""
    text = " ".join(text.split())
    if not text:
        raise ApiError("Введите текст для озвучки.")
    cache = Path.home() / ".jishocli" / "tts"
    cache.mkdir(parents=True, exist_ok=True)
    return b"".join(_tts_chunk(chunk, lang, cache) for chunk in _tts_split(text))


def is_allowed_image_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    allowed = ("anilist.co", "mangadex.network", "mangadex.org", "wikimedia.org",
               "jsdelivr.net", "githubusercontent.com")
    return any(host == d or host.endswith("." + d) for d in allowed)


def ocr_local(image_path: str, languages: str = "jpn+eng") -> str:
    """Optional local OCR via the tesseract binary; the web UI uses Tesseract.js."""
    import shutil
    import subprocess
    from pathlib import Path
    binary = shutil.which("tesseract")
    if not binary:
        raise ApiError("Локальный tesseract не установлен. Используйте веб-режим (jishocli web → /ocr) "
                       "или установите tesseract-ocr с языками jpn и eng.")
    path = Path(image_path)
    if not path.is_file():
        raise ApiError(f"Файл не найден: {image_path}")
    try:
        result = subprocess.run([binary, str(path), "stdout", "-l", languages,
                                 "--psm", "6", "--dpi", "300"],
                                capture_output=True, text=True, timeout=120, check=True)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ApiError(f"OCR не удался: {exc}") from exc
    return result.stdout.strip()


def fetch_bytes(url: str, timeout: float = 20) -> bytes:
    request = Request(url, headers={"User-Agent": UA["User-Agent"]})
    try:
        with _open(request, timeout) as response:
            return response.read()
    except Exception as exc:
        raise ApiError(f"Не удалось скачать {url.split('/')[2]}: {_friendly(exc)}") from exc


def download_file(url: str, path) -> int:
    """Download binary content (cover image, manga page) with proxy fallback."""
    from pathlib import Path
    data = fetch_bytes(url)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def search_jisho(query: str) -> list[dict]:
    data = _get(f"https://jisho.org/api/v1/search/words?keyword={quote(query)}")
    return data.get("data", [])


@lru_cache(maxsize=512)
def kanji_info(character: str) -> dict:
    return _get(f"https://kanjiapi.dev/v1/kanji/{quote(character)}")


@lru_cache(maxsize=512)
def kanji_strokes(character: str) -> str:
    """Stroke-order SVG from KanjiVG (CC BY-SA 3.0, Ulrich Apel)."""
    return _get_text(f"https://raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/{ord(character):05x}.svg")


def detect_language(text: str) -> str:
    if any('\u3040' <= c <= '\u30ff' or '\u3400' <= c <= '\u9fff' for c in text):
        return "ja"
    if any('а' <= c.lower() <= 'я' or c.lower() == 'ё' for c in text):
        return "ru"
    return "en"


@lru_cache(maxsize=256)
def translate(text: str, source: str, target: str) -> str:
    if source == "auto":
        source = detect_language(text)
    if source == target:
        return text
    if not text.strip():
        raise ApiError("Введите текст для перевода.")
    if len(text.encode('utf-8')) > 500:
        raise ApiError("MyMemory принимает до 500 байт за запрос. Сократите текст.")
    data = _get("https://api.mymemory.translated.net/get?" + urlencode({
        "q": text, "langpair": f"{source}|{target}",
    }))
    if str(data.get("responseStatus")) != "200":
        raise ApiError(f"Перевод недоступен: {data.get('responseDetails') or 'ошибка сервиса'}")
    result = data.get("responseData", {}).get("translatedText")
    if not isinstance(result, str) or not result.strip():
        raise ApiError("Сервис вернул пустой перевод.")
    return unescape(result)


# --- anime / manga: provider chain AniList -> Tenrai -> Jikan ---------------

def _media_anilist(query: str, kind: str, limit: int, genre: str | None = None,
                   year: int | None = None, status: str | None = None,
                   sort: str | None = None) -> list[dict]:
    args = ["search:$s", "type:$t", "isAdult:false"]
    variables: dict = {"s": query, "t": kind.upper(), "n": limit}
    decl = ["$s:String", "$t:MediaType", "$n:Int"]
    if genre:
        args.append("genre_in:$g"); decl.append("$g:[String]"); variables["g"] = [genre]
    if year:
        args.append("startDate_greater:$y"); decl.append("$y:FuzzyDateInput")
        variables["y"] = {"year": int(year) - 1, "month": 12, "day": 31}
    if status and status.upper() in {"FINISHED", "RELEASING", "NOT_YET_RELEASED", "CANCELLED", "HIATUS"}:
        args.append("status:$st"); decl.append("$st:MediaStatus"); variables["st"] = status.upper()
    if sort and sort.upper() in {"SCORE_DESC", "POPULARITY_DESC", "START_DATE_DESC", "TITLE_ROMAJI"}:
        args.append("sort:$so"); decl.append("$so:[MediaSort]"); variables["so"] = [sort.upper()]
    gql = f"""
    query({','.join(decl)}) {{
      Page(perPage:$n) {{
        media({','.join(args)}) {{
          id
          title {{ romaji english native }}
          format status averageScore episodes chapters volumes
          genres description(asHtml:false) siteUrl
          coverImage {{ large }}
          startDate {{ year }}
          season seasonYear popularity favourites duration source
          studios(isMain:true) {{ nodes {{ name }} }}
          externalLinks {{ url site type language }}
          trailer {{ id site }}
        }}
      }}
    }}
    """
    data = _request("https://graphql.anilist.co", payload={"query": gql, "variables": variables})
    if data.get("errors"):
        raise ApiError("AniList: " + data["errors"][0].get("message", "ошибка запроса"))
    return [_anilist_row(m) for m in data.get("data", {}).get("Page", {}).get("media", [])]


def _anilist_row(m: dict) -> dict:
    title = m.get("title", {})
    score = m.get("averageScore")
    return {
        "anilist_id": m.get("id"),
        "title": title.get("english") or title.get("romaji") or "—",
        "title_japanese": title.get("native") or "",
        "type": m.get("format"), "status": m.get("status"),
        "score": round(score / 10, 1) if score else None,
        "episodes": m.get("episodes"), "chapters": m.get("chapters"), "volumes": m.get("volumes"),
        "genres": [{"name": g} for g in m.get("genres", [])],
        "synopsis": re.sub(r"<[^>]+>", "", m.get("description") or ""),
        "url": m.get("siteUrl") or "",
        "image": (m.get("coverImage") or {}).get("large"),
        "year": (m.get("startDate") or {}).get("year") or m.get("seasonYear"),
        "season": m.get("season"), "popularity": m.get("popularity"),
        "favourites": m.get("favourites"), "duration": m.get("duration"),
        "source": m.get("source"),
        "studios": [s["name"] for s in (m.get("studios") or {}).get("nodes", [])],
        "links": [{"site": l.get("site"), "url": l.get("url"), "type": l.get("type")}
                  for l in m.get("externalLinks", []) if l.get("url")],
        "trailer": ("https://www.youtube.com/embed/" + m["trailer"]["id"])
                   if (m.get("trailer") or {}).get("site") == "youtube" and (m.get("trailer") or {}).get("id") else None,
    }


def anilist_detail(media_id: int, kind: str) -> dict:
    gql = """
    query($id:Int,$t:MediaType) {
      Media(id:$id, type:$t) {
        id
        title { romaji english native }
        format status averageScore meanScore episodes chapters volumes
        genres description(asHtml:false) siteUrl
        coverImage { large }
        bannerImage
        startDate { year month day }
        endDate { year month day }
        season seasonYear popularity favourites duration source
        studios(isMain:true) { nodes { name } }
        tags { name rank }
        nextAiringEpisode { episode airingAt }
        externalLinks { url site type language }
        trailer { id site }
        relations { edges { relationType node { id title { romaji } } } }
      }
    }
    """
    data = _request("https://graphql.anilist.co", payload={
        "query": gql, "variables": {"id": media_id, "t": kind.upper()}})
    if data.get("errors") or not data.get("data", {}).get("Media"):
        raise ApiError("AniList: произведение не найдено")
    m = data["data"]["Media"]
    row = _anilist_row(m)
    row["banner"] = m.get("bannerImage")
    row["mean_score"] = round(m["meanScore"] / 10, 1) if m.get("meanScore") else None
    row["tags"] = [t["name"] for t in m.get("tags", []) if t.get("rank", 0) >= 60][:8]
    row["start_date"] = m.get("startDate")
    row["end_date"] = m.get("endDate")
    row["next_episode"] = m.get("nextAiringEpisode")
    row["relations"] = [{"relation": e.get("relationType"),
                         "title": (e.get("node") or {}).get("title", {}).get("romaji", ""),
                         "id": (e.get("node") or {}).get("id")}
                        for e in (m.get("relations") or {}).get("edges", [])]
    return row


def _media_tenrai(query: str, kind: str, limit: int) -> list[dict]:
    params = urlencode({"q": query, "limit": min(limit, 25), "sfw": "true"})
    return _get(f"https://api.tenrai.org/{kind}?{params}").get("data", [])


def _media_jikan(query: str, kind: str, limit: int) -> list[dict]:
    params = urlencode({"q": query, "limit": min(limit, 25), "sfw": "true"})
    return _get(f"https://api.jikan.moe/v4/{kind}?{params}").get("data", [])


def _filter_media(rows: list[dict], genre: str | None, year: int | None,
                  status: str | None) -> list[dict]:
    out = []
    for row in rows:
        if genre and not any(g.get("name", "").lower() == genre.lower() for g in row.get("genres", [])):
            continue
        if year and row.get("year") and int(row["year"]) < int(year):
            continue
        if status and status.lower() not in str(row.get("status", "")).lower():
            continue
        out.append(row)
    return out


def search_media(query: str, kind: str, limit: int, genre: str | None = None,
                 year: int | None = None, status: str | None = None,
                 sort: str | None = None) -> list[dict]:
    if kind not in {"anime", "manga"}:
        raise ApiError("Неизвестный тип каталога.")
    query = query.strip()
    limit = min(max(limit, 1), 25)
    errors = []
    providers = (
        ("AniList", lambda q, k, n: _media_anilist(q, k, n, genre, year, status, sort)),
        ("Tenrai", _media_tenrai), ("Jikan", _media_jikan),
    )
    for name, provider in providers:
        try:
            rows = provider(query, kind, limit)
            if name != "AniList":
                rows = _filter_media(rows, genre, year, status)
            LOGGER.info("media provider %s returned %d rows", name, len(rows))
            return rows
        except ApiError as exc:
            LOGGER.warning("media provider %s failed: %s", name, exc)
            errors.append(f"{name}: {exc}")
    raise ApiError("Каталоги аниме/манги недоступны.\n" + "\n".join(errors))


def search_topics(query: str, language: str, limit: int) -> list[dict]:
    if language not in {"ru", "en", "ja"}:
        raise ApiError("Для Wikipedia доступны ru, en и ja.")
    params = urlencode({"action": "query", "format": "json", "generator": "search",
                        "gsrsearch": query, "gsrlimit": min(limit, 20), "prop": "extracts|info",
                        "exintro": 1, "explaintext": 1, "inprop": "url", "exsentences": 3})
    data = _get(f"https://{language}.wikipedia.org/w/api.php?{params}")
    if "error" in data:
        raise ApiError("Wikipedia: " + data["error"].get("info", "ошибка запроса"))
    return sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))


def search_kanji(character: str) -> dict:
    data = _get(f"https://jisho.org/api/v1/search/words?keyword={quote(character)}")
    return {"character": character, "words": data.get("data", [])}


# --- MangaDex: legal scanlation reader --------------------------------------

_MD_RATINGS = [("contentRating[]", "safe"), ("contentRating[]", "suggestive")]


def mangadex_search(title: str, limit: int = 5, year: int | None = None,
                    status: str | None = None) -> list[dict]:
    params = [("limit", min(limit, 20))] + _MD_RATINGS
    if title:
        params.insert(0, ("title", title))
    else:
        params.append(("order[popularity]", "asc"))
    if year:
        params.append(("year", int(year)))
    if status and status.upper() in {"ONGOING", "COMPLETED", "HIATUS", "CANCELLED"}:
        params.append(("status[]", status.upper()))
    data = _get("https://api.mangadex.org/manga?" + urlencode(params))
    rows = []
    for m in data.get("data", []):
        attrs = m.get("attributes", {})
        titles = attrs.get("title", {})
        rows.append({"id": m["id"],
                     "title": titles.get("en") or titles.get("ja-ro") or next(iter(titles.values()), "—"),
                     "title_japanese": titles.get("ja") or "",
                     "status": attrs.get("status"), "year": attrs.get("year"),
                     "genres": [g["attributes"]["name"] for g in attrs.get("tags", [])
                                if "manga" in (g.get("attributes", {}).get("group") or "genre")][:4],
                     "description": (attrs.get("description") or {}).get("en", "")})
    return rows


def search_books(query: str, limit: int = 8) -> list[dict]:
    params = urlencode({"q": query, "limit": min(limit, 20),
                        "fields": "key,title,author_name,first_publish_year,cover_i,ia,ebook_access,language"})
    data = _get("https://openlibrary.org/search.json?" + params)
    rows = []
    for doc in data.get("docs", []):
        title = doc.get("title", "—")
        ia = (doc.get("ia") or [None])[0]
        rows.append({"key": doc.get("key", ""), "title": title,
                     "author": ", ".join((doc.get("author_name") or [])[:2]) or "—",
                     "year": doc.get("first_publish_year"), "cover": doc.get("cover_i"),
                     "ia": ia, "access": doc.get("ebook_access", ""),
                     "language": (doc.get("language") or [])[:3]})
    return rows


def mangadex_popular(limit: int = 8) -> list[dict]:
    return mangadex_search("", limit)


def mangadex_chapters(manga_id: str, language: str = "en", limit: int = 100) -> list[dict]:
    params = [("limit", min(limit, 500)), ("translatedLanguage[]", language),
              ("order[chapter]", "asc")] + _MD_RATINGS
    data = _get(f"https://api.mangadex.org/manga/{manga_id}/feed?" + urlencode(params))
    rows = []
    for c in data.get("data", []):
        a = c.get("attributes", {})
        if a.get("externalUrl") or a.get("isUnavailable"):
            continue  # official external chapters have no pages here
        rows.append({"id": c["id"], "chapter": a.get("chapter") or "—",
                     "volume": a.get("volume"), "title": a.get("title") or "",
                     "pages": a.get("pages"), "language": a.get("translatedLanguage")})
    return rows


def mangadex_pages(chapter_id: str) -> dict:
    data = _get(f"https://api.mangadex.org/at-home/server/{chapter_id}")
    if data.get("result") != "ok":
        raise ApiError("MangaDex: страницы главы недоступны")
    chapter = data["chapter"]
    base = data["baseUrl"]
    return {"urls": [f"{base}/data/{chapter['hash']}/{name}" for name in chapter["data"]],
            "count": len(chapter["data"])}


# --- learning from anime/manga or any Japanese text --------------------------

def learn_vocab(text: str, limit: int = 8) -> list[dict]:
    """Extract content words via Janome and look them up in Jisho."""
    from .language import analyze
    seen: set[str] = set()
    rows: list[dict] = []
    for token in analyze(text):
        base = token["base"]
        if token["pos"] not in {"существительное", "глагол", "прилагательное", "наречие"}:
            continue
        if base in seen or len(base) < 2 and not any('\u4e00' <= c <= '\u9fff' for c in base):
            continue
        seen.add(base)
        entry = {"word": token["word"], "base": base, "reading": token["reading"],
                 "romaji": token["romaji"], "pos": token["pos"], "meaning": ""}
        rows.append(entry)
        if len(rows) >= limit:
            break
    def lookup(entry: dict) -> dict:
        try:
            matches = search_jisho(entry["base"])
            if matches:
                senses = matches[0].get("senses", [])
                entry["meaning"] = "; ".join(senses[0].get("english_definitions", [])) if senses else ""
        except ApiError:
            pass
        return entry
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(rows)))) as pool:
        return list(pool.map(lookup, rows))


def translate_to_english(text: str, source: str) -> str | None:
    if source.lower() in {"en", "eng", "english", "ja", "jpn", "japanese"}:
        return text
    try:
        return translate(text, source, "en")
    except ApiError:
        return None


def translate_to_russian(text: str, source: str = "en") -> str | None:
    if not text:
        return None
    if source.lower() in {"ru", "rus", "russian"}:
        return text
    try:
        return translate(text, source, "ru")
    except ApiError:
        return None
