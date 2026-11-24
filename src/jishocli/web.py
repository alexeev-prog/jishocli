"""Modern standard-library web UI: dictionary, courses, OCR, reader and study."""

from __future__ import annotations

import base64
import gzip
import html
import json
import logging
import random
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import kana, quiz as quiz_engine, exam as exam_engine, conversation as convo_engine
from .api import (ApiError, anilist_detail, cached_image, detect_language, fetch_bytes,
                  is_allowed_image_url, kanji_info, kanji_strokes, learn_vocab,
                  mangadex_chapters, mangadex_pages, mangadex_popular, mangadex_search,
                  search_jisho, search_media, search_topics, search_books, tts_audio, translate)
from .course import (COURSES, course_by_id, course_of_lesson, course_progress,
                     complete, get_lesson, lesson_neighbors)
from .quiz import daily_word
from .renderer import save_svg
from .romaji import phrase_romaji, reading_romaji
from .storage import Store

LOGGER = logging.getLogger("jishocli.web")

ICONS = {
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "volume": '<path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/>',
    "moon": '<path d="M21 12.8A8 8 0 1 1 11.2 3a6 6 0 0 0 9.8 9.8Z"/>',
    "palette": '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="10" r="1"/><circle cx="12" cy="8" r="1"/><circle cx="16" cy="10" r="1"/>',
    "book": '<path d="M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2V5Z"/><path d="M8 3v18"/>',
    "cards": '<rect x="3" y="6" width="14" height="14" rx="2"/><path d="M7 6V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2"/>',
    "quiz": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.8 2.1c-.8.5-1.3 1-1.3 1.9"/><path d="M12 17h.01"/>',
    "pen": '<path d="m4 20 4.5-1 10-10a2 2 0 0 0-3-3l-10 10L4 20Z"/><path d="m14 6 3 3"/>',
    "ocr": '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10M9 9v6M15 9v6"/>',
    "tv": '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="m8 3 4 3 4-3"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
    "reader": '<path d="M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Z"/><path d="M12 6v14"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3Z"/>',
    "download": '<path d="M12 3v12m0 0 4-4m-4 4-4-4M4 19h16"/>',
    "bookmark": '<path d="M6 3h12v18l-6-4-6 4V3Z"/>',
    "external": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "left": '<path d="m15 18-6-6 6-6"/>',
    "right": '<path d="m9 18 6-6-6-6"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    "language": '<path d="M3 5h11M8 3v2c0 5-2 8-5 10M6 9c2 4 5 6 9 7M13 20l4-10 4 10M15 16h4"/>',
    "sparkle": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l3 3M15 15l3 3M18 6l-3 3M9 15l-3 3"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "shuffle": '<path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>',
    "chat": '<path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z"/>',
    "headphones": '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="2" y="14" width="4" height="6" rx="2"/><rect x="18" y="14" width="4" height="6" rx="2"/>',
    "heart": '<path d="M20.8 8.6c0 4.2-8.8 9.6-8.8 9.6S3.2 12.8 3.2 8.6a4.6 4.6 0 0 1 8.8-1.8 4.6 4.6 0 0 1 8.8 1.8Z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
}


def icon(name: str, size: int = 16) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{ICONS.get(name, ICONS["info"])}</svg>')


CSS = """
:root{color-scheme:light;--accent:#c0392b;--accent-soft:rgba(192,57,43,.1);
--ink:#22201d;--muted:#7a7165;--line:#e8e2d7;--paper:#f6f3ec;--panel:#fffdf8;
--field:#fffdf8;--soft:#efe9de;--shadow:0 8px 30px rgba(60,45,25,.07);--radius:16px}
:root.dark{color-scheme:dark;--ink:#e8e8e8;--muted:#9d9d9d;--line:#333;
--paper:#141414;--panel:#1d1d1d;--field:#242424;--soft:#2a2a2a;--shadow:0 8px 30px rgba(0,0,0,.35)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;min-height:100vh;display:flex;flex-direction:column;background:var(--paper);color:var(--ink);
font:15px/1.7 system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
main{flex:1}a{color:var(--accent);text-decoration:none;transition:color .15s}a:hover{color:var(--accent);text-decoration:underline}
.wrap{width:min(1160px,100% - 48px);margin-inline:auto}
.site-header{position:sticky;top:0;z-index:40;background:color-mix(in srgb,var(--panel) 88%,transparent);
backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.header-inner{display:flex;align-items:center;gap:14px;padding:12px 0;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:9px;color:var(--ink);flex:0 0 auto}
.hanko{width:34px;height:34px;display:grid;place-items:center;border-radius:11px;background:var(--accent);
color:#fff;font:19px/1 Georgia,"Noto Serif JP",serif;box-shadow:0 4px 12px var(--accent-soft)}
.brand h1{margin:0;font:600 19px/1.1 Georgia,serif}.brand small{display:block;font:9px/1.5 system-ui;letter-spacing:.28em;color:var(--muted)}
.head-search{display:flex;gap:6px;flex:1 1 220px;max-width:330px}
.head-search input{width:100%;padding:8px 12px;border-radius:10px;font-size:13px}
.controls{display:flex;align-items:center;gap:7px;margin-left:auto}
.btn-icon,.burger{width:34px;height:34px;display:grid;place-items:center;border:1px solid var(--line);
border-radius:10px;background:var(--field);color:var(--ink);cursor:pointer;padding:0;transition:.15s}
.btn-icon:hover,.burger:hover{border-color:var(--accent);color:var(--accent);transform:translateY(-1px)}
.theme-toggle{display:flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--field);
color:var(--ink);padding:6px 9px;border-radius:10px;cursor:pointer;font-size:11px}
.theme-toggle input{position:absolute;opacity:0;width:1px;height:1px}
.switch{width:24px;height:14px;border-radius:99px;background:var(--muted);position:relative;transition:.2s}
.switch:after{content:"";position:absolute;top:2px;left:2px;width:10px;height:10px;border-radius:50%;background:var(--panel);transition:.2s}
.theme-toggle input:checked+.switch{background:var(--accent)}
.theme-toggle input:checked+.switch:after{left:12px}
.palette-wrap{position:relative}
.palette{display:none;position:absolute;right:0;top:40px;gap:7px;padding:9px;background:var(--panel);
border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);z-index:60}
.palette.open{display:flex;animation:fadeUp .18s ease both}
.palette button{width:22px;height:22px;border-radius:50%;border:2px solid var(--line);padding:0;cursor:pointer;transition:transform .15s}
.palette button:hover{transform:scale(1.2);color:#fff;font-weight:bold}
.btn:active{transform:translateY(0) scale(.98)}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,
summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.nav{display:flex;gap:2px;flex-wrap:wrap}
.navgroup{position:relative}.navgroup>summary{list-style:none;cursor:pointer;padding:6px 10px;color:var(--muted);
font-size:13px;border-radius:9px;white-space:nowrap}.navgroup>summary::-webkit-details-marker{display:none}
.navgroup>summary:hover,.navgroup.here>summary{color:var(--accent);background:var(--accent-soft)}
.navgroup .dropdown{display:none;position:absolute;top:34px;left:0;min-width:180px;flex-direction:column;
background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:6px;z-index:60}
.navgroup:hover .dropdown,.navgroup[open] .dropdown{display:flex;animation:fadeUp .16s ease both}
.navgroup .dropdown a{display:flex;gap:8px;align-items:center;padding:7px 9px;border-radius:8px;color:var(--muted);font-size:13px}
.navgroup .dropdown a:hover,.navgroup .dropdown a.active{background:var(--soft);color:var(--accent);text-decoration:none}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);opacity:0;visibility:hidden;
transition:opacity .22s,visibility .22s;z-index:90}
.overlay.open{opacity:1;visibility:visible}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(400px,92vw);background:var(--panel);
border-left:1px solid var(--line);transform:translateX(102%);visibility:hidden;
transition:transform .24s cubic-bezier(.4,0,.2,1),visibility .24s;z-index:100;
overflow-y:auto;overscroll-behavior:contain;box-shadow:-12px 0 40px rgba(0,0,0,.15)}
.drawer.open{transform:translateX(0);visibility:visible}
body.drawer-lock{overflow:hidden}
.drawer-head{position:sticky;top:0;background:var(--panel);display:flex;align-items:center;
justify-content:space-between;padding:16px 18px;border-bottom:1px solid var(--line);z-index:2}
.drawer-section{border-bottom:1px solid var(--line)}
.drawer-group{display:flex;align-items:center;justify-content:space-between;width:100%;padding:14px 18px;
border:0;background:transparent;color:var(--ink);font:16px Georgia,serif;cursor:pointer;text-align:left}
.drawer-group:hover{color:var(--accent)}
.drawer-group .chev{transition:transform .2s;color:var(--muted)}
.drawer-group[aria-expanded="true"] .chev{transform:rotate(90deg)}
.drawer-items{display:none;padding:2px 10px 12px}
.drawer-items.open{display:block;animation:fadeUp .18s ease both}
.drawer-items a{display:flex;align-items:center;gap:11px;padding:9px 12px;border-radius:9px;
color:var(--muted);font-size:14px}
.drawer-items a:hover,.drawer-items a.active{background:var(--soft);color:var(--accent);text-decoration:none}
.drawer-foot{padding:16px 18px;color:var(--muted);font-size:12px}
main{padding:0 0 80px}
.hero{position:relative;overflow:hidden;padding:66px 0 42px;text-align:center}
.hero:before{content:"";position:absolute;width:420px;height:420px;border-radius:50%;
background:radial-gradient(circle,var(--accent-soft),transparent 68%);top:-180px;left:50%;transform:translateX(-50%)}
.hero .kanji-bg{position:absolute;font:220px/1 Georgia,serif;color:var(--accent);opacity:.05;top:-40px;right:6%}
.hero h1{position:relative;font:400 clamp(40px,7vw,70px)/1.08 Georgia,serif;margin:0 0 14px;letter-spacing:-.03em}
.hero p{position:relative;color:var(--muted);max-width:60ch;margin:0 auto 24px}
.lead{max-width:780px;margin:0 auto 34px;text-align:center}
.lead h2{font:400 clamp(30px,5vw,50px)/1.12 Georgia,serif;margin:0 0 10px}
.lead p{color:var(--muted);max-width:64ch;margin:0 auto 18px}
.actions{display:flex;gap:9px;justify-content:center;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:1px solid var(--ink);
background:var(--ink);color:var(--paper);padding:10px 17px;border-radius:11px;font:inherit;cursor:pointer;
transition:transform .16s,background .16s,border-color .16s}
.btn:hover{background:var(--accent);border-color:var(--accent);color:#fff;text-decoration:none;transform:translateY(-2px)}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.btn.ghost:hover{border-color:var(--accent);color:var(--accent);background:transparent}
.btn.sm{padding:7px 12px;font-size:13px;border-radius:9px}
h2.section{font:400 26px/1.2 Georgia,serif;margin:44px 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.card{display:block;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:20px;
color:var(--ink);box-shadow:var(--shadow);transition:transform .18s,border-color .18s,box-shadow .18s;
animation:fadeUp .35s ease both}
.card:hover{transform:translateY(-4px);border-color:var(--accent);box-shadow:0 14px 34px var(--accent-soft);text-decoration:none}
.card .ico{color:var(--accent);margin-bottom:10px}
.card h3{margin:0 0 5px;font:20px/1.3 Georgia,serif}.card p{margin:0;color:var(--muted);font-size:14px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:22px;box-shadow:var(--shadow)}
.daily{max-width:720px;margin:0 auto 40px;text-align:center;border-left:4px solid var(--accent)}
.daily .jp{font-size:34px}
.result{max-width:860px;margin:0 auto;padding:20px 0;border-bottom:1px solid var(--line);animation:fadeUp .25s ease both}
.result h3{margin:0 0 4px;font-size:22px}
.jp{font-family:Georgia,"Noto Serif JP",serif}.roma{color:var(--accent);font-style:italic}.muted{color:var(--muted)}
.tag{font-size:11px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
form.search{display:flex;gap:8px;max-width:680px;margin:0 auto;flex-wrap:wrap}
input,select,textarea{font:inherit;border:1px solid var(--line);background:var(--field);color:var(--ink);
padding:10px 13px;border-radius:11px;outline:none;transition:border-color .15s,box-shadow .15s}
input:focus,select:focus,textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
form.search input{flex:1;min-width:140px}
.tabs{display:flex;gap:6px;justify-content:center;flex-wrap:wrap;margin:0 auto 22px}
.tabs a,.tabs button{padding:7px 13px;border-radius:99px;border:1px solid var(--line);color:var(--muted);font-size:13px;background:var(--panel)}
.tabs a.active,.tabs button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.chips{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;max-width:720px;margin:0 auto 14px}
.chips a,.chips button{display:inline-flex;align-items:center;gap:5px;padding:6px 10px;border:1px solid var(--line);
border-radius:9px;background:var(--panel);color:var(--ink);font-size:13px;cursor:pointer}
.chips a:hover,.chips a.active,.chips button:hover{border-color:var(--accent);color:var(--accent)}
.lesson{max-width:820px;margin:0 auto}
.lesson h2{font:400 clamp(30px,4.5vw,44px)/1.15 Georgia,serif;margin:8px 0 16px}
.lesson h3{font:19px Georgia,serif;margin:30px 0 8px;padding-bottom:7px;border-bottom:1px solid var(--line)}
.lesson p{max-width:76ch;white-space:pre-line}
.voice-line{display:inline}.speak{display:inline-grid;place-items:center;width:24px;height:24px;vertical-align:middle;
background:transparent;border:1px solid var(--line);color:var(--muted);border-radius:50%;cursor:pointer;margin-left:5px;transition:.15s}
.speak:hover{color:var(--accent);border-color:var(--accent);transform:scale(1.08)}
.speak.big{width:40px;height:40px;color:var(--accent);border-color:var(--accent)}
.trans-btn{display:inline-grid;place-items:center;padding:2px 7px;margin-left:4px;border:1px solid var(--line);
border-radius:7px;background:transparent;color:var(--muted);font-size:11px;cursor:pointer;transition:.15s}
.trans-btn:hover{border-color:var(--accent);color:var(--accent)}
practice{white-space:pre-line}
.practice{white-space:pre-line;background:var(--panel);border:1px solid var(--line);
border-left:4px solid var(--accent);border-radius:12px;padding:18px;margin:16px 0;box-shadow:var(--shadow)}
.progress{height:7px;background:var(--soft);border-radius:10px;overflow:hidden;margin:14px auto;max-width:460px}
.progress i{display:block;height:100%;background:var(--accent);border-radius:10px;transition:width .4s ease}
.kana-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin:14px 0 28px}
.kana-cell{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:12px;text-align:center;
cursor:pointer;box-shadow:var(--shadow);transition:.16s;animation:fadeUp .3s ease both}
.kana-cell:hover{border-color:var(--accent);transform:translateY(-3px)}
.kana-cell .big{font-size:30px;font-family:Georgia,"Noto Serif JP",serif}
.kana-cell .sub{color:var(--muted);font-size:13px}.kana-cell .r{color:var(--accent);font-style:italic}
.quiz-q{max-width:780px;margin:0 auto 16px;background:var(--panel);border:1px solid var(--line);
border-radius:var(--radius);padding:18px;box-shadow:var(--shadow);animation:fadeUp .3s ease both}
.quiz-q .opts{display:grid;gap:8px;margin-top:11px}
.quiz-q label{display:flex;gap:10px;align-items:center;border:1px solid var(--line);border-radius:9px;
padding:8px 11px;cursor:pointer;background:var(--field);transition:.15s}
.quiz-q label:hover{border-color:var(--accent)}
.quiz-q label.ok{border-color:#3d8b57;background:rgba(61,139,87,.13)}
.quiz-q label.bad{border-color:var(--accent);background:var(--accent-soft)}
.quiz-q .explain{display:none;margin-top:10px;color:var(--muted)}
.quiz-q.done .explain{display:block}
.recall-row{display:flex;gap:8px;margin-top:10px}.recall-row input{flex:1}
.score{position:sticky;top:66px;z-index:20;max-width:780px;margin:0 auto 16px;text-align:center;
background:var(--panel);border:1px solid var(--line);border-radius:99px;padding:8px;box-shadow:var(--shadow)}
.draw-wrap{position:relative;width:min(420px,100%);aspect-ratio:1;margin:18px auto;background:var(--panel);
border:1px solid var(--line);border-radius:16px;overflow:hidden;box-shadow:var(--shadow)}
.draw-guide{position:absolute;inset:0;display:grid;place-items:center}
.draw-guide svg{width:88%;height:88%}.draw-guide svg path{stroke:var(--muted);fill:none}
.draw-guide svg text{fill:var(--muted)}
.draw-wrap canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:crosshair}
.draw-wrap.compare .draw-guide svg path{stroke:var(--accent);opacity:.85}
.draw-wrap.compare #user-canvas{opacity:.65}
.draw-score{max-width:430px;margin:14px auto;text-align:center;background:var(--panel);border:1px solid var(--line);
border-radius:var(--radius);padding:16px;box-shadow:var(--shadow)}
.draw-score .num{font:36px/1.2 Georgia,serif;color:var(--accent)}
.media-img{float:right;width:100px;border-radius:10px;margin:0 0 10px 16px;border:1px solid var(--line)}
.detail-cover{width:190px;border-radius:14px;border:1px solid var(--line);float:left;margin:0 22px 14px 0}
.meta{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:16px 0}
.meta div{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:10px 12px}
.meta b{display:block;font-size:11px;color:var(--muted);font-weight:500;text-transform:uppercase}
.trailer{width:100%;max-width:620px;aspect-ratio:16/9;border:0;border-radius:14px;margin:16px 0}
.reader-shell{max-width:1080px;margin:0 auto}.reader-top{display:flex;gap:8px;justify-content:center;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.reader-stage{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px;text-align:center}
.reader-stage img{max-width:100%;height:auto;border-radius:6px;background:#fff;transition:transform .2s;transform-origin:top center}
.reader-stage img.wide{max-width:none;width:100%}
.reader-stage img.invert{filter:invert(1) hue-rotate(180deg)}
.reader-bar{height:5px;background:var(--soft);border-radius:9px;overflow:hidden;margin:12px 0}
.reader-bar i{display:block;height:100%;background:var(--accent);transition:width .3s}
.reader-tools{margin:16px auto 0;max-width:860px}
.ocr-drop{border:2px dashed var(--line);border-radius:var(--radius);padding:36px 18px;text-align:center;
background:var(--panel);cursor:pointer;transition:.18s}
.ocr-drop:hover,.ocr-drop.drag{border-color:var(--accent);background:var(--accent-soft)}
.ocr-preview{max-width:100%;max-height:360px;border-radius:12px;border:1px solid var(--line);display:block;margin:14px auto}
.ocr-text{white-space:pre-wrap;background:var(--field);border:1px solid var(--line);border-radius:12px;
padding:14px;max-height:280px;overflow:auto;font:15px/1.8 Georgia,"Noto Serif JP",serif}
.bookmarks{margin:0 auto 28px;max-width:860px}
.bookmark{display:flex;gap:10px;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--line);font-size:14px}
#trans-panel{position:fixed;right:22px;bottom:22px;width:min(420px,calc(100vw - 44px));max-width:420px;
max-height:min(72vh,560px);overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;
background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);
padding:14px 16px;z-index:90;transform:translateY(140%);opacity:0;transition:transform .25s,opacity .25s;
pointer-events:none;overflow-wrap:anywhere;word-break:break-word}
#trans-panel.open{transform:translateY(0);opacity:1;pointer-events:auto}
#trans-panel .jp{font-size:20px;line-height:1.5}
#trans-panel pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
#toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,20px);opacity:0;visibility:hidden;
background:var(--ink);color:var(--paper);padding:9px 16px;border-radius:99px;font-size:13px;z-index:120;
transition:opacity .2s,transform .2s,visibility .2s;pointer-events:none;max-width:calc(100vw - 32px);text-align:center}
#toast.show{opacity:1;visibility:visible;transform:translate(-50%,0)}
footer{border-top:1px solid var(--line);background:var(--panel);padding:38px 0 24px;margin-top:auto}
.footer-grid{display:grid;grid-template-columns:1.6fr repeat(3,1fr);gap:26px}
.footer-grid h4{margin:0 0 9px;font:15px Georgia,serif}.footer-grid a,.footer-grid p{display:block;color:var(--muted);font-size:13px;margin:5px 0}
.footer-bottom{border-top:1px solid var(--line);margin-top:22px;padding-top:16px;text-align:center;color:var(--muted);font-size:12px}
.view{display:none}.view.active{display:block;animation:fadeUp .22s ease both}
.word-menu{margin:8px 0}.word-menu summary{cursor:pointer;color:var(--accent);font-size:13px;list-style:none}
.word-menu summary::-webkit-details-marker{display:none}
.word-menu[open]{background:var(--soft);border-radius:10px;padding:8px 12px}
.word-menu .menu-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px}
.word-menu form{margin:6px 0 0}
.builder{margin:16px 0;padding:16px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.builder-tiles{display:flex;flex-wrap:wrap;gap:8px}.builder-tiles button{padding:8px 13px;border:1px solid var(--line);
border-radius:9px;background:var(--field);color:var(--ink);cursor:pointer}
.builder-tiles button:hover{border-color:var(--accent)}.builder-tiles button:disabled{opacity:.35;cursor:default}
.builder-target{min-height:34px;margin:12px 0;padding:7px 10px;border-bottom:2px dashed var(--accent);font:18px Georgia,serif}
.builder-result{color:var(--muted)}
.exam-timer{position:sticky;top:66px;z-index:25;display:flex;justify-content:center;gap:14px;align-items:center;
background:var(--panel);border:1px solid var(--line);border-radius:99px;padding:8px 16px;max-width:760px;
margin:0 auto 16px;box-shadow:var(--shadow);font:20px Georgia,serif}
.exam-head{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-bottom:14px}
body.focus-mode .site-header,body.focus-mode footer,body.focus-mode .reader-tools{display:none}
body.focus-mode main.wrap{width:100%;max-width:none;padding:0}
body.focus-mode .reader-stage{border:0;border-radius:0;background:var(--paper);padding:0;box-shadow:none}
body.focus-mode .reader-stage img{max-width:none;max-height:100vh;width:auto;display:block;margin:auto}
.reader-shell.theater{position:fixed;inset:0;z-index:80;background:var(--paper);padding:52px 16px 20px;overflow:auto}
.reader-shell.theater .reader-stage{max-width:none;border:0;border-radius:0;background:transparent;box-shadow:none;padding:0}
.reader-shell.theater .reader-stage img{max-height:calc(100vh - 96px);max-width:100%;width:auto}
.reader-shell.theater .reader-top{position:sticky;top:0;background:var(--paper);z-index:2;padding:8px 0}
#shortcuts{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%) scale(.96);opacity:0;visibility:hidden;
transition:.2s;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 22px;
box-shadow:var(--shadow);z-index:110;max-width:min(420px,90vw)}
#shortcuts.open{opacity:1;visibility:visible;transform:translate(-50%,-50%) scale(1)}
.book-frame-wrap{position:relative;max-width:1000px;margin:16px auto}
.book-frame{width:100%;height:76vh;border:1px solid var(--line);border-radius:12px;background:#fff}
.book-frame-wrap:fullscreen .book-frame{height:100vh;border:0;border-radius:0}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media(max-width:1180px){.nav{display:none}.header-inner{gap:10px}}
@media(max-width:820px){.head-search{display:none}.header-inner{padding:10px 0}}
@media(max-width:700px){.wrap{width:min(100% - 28px,1160px)}.hero{padding:40px 0 28px}
#trans-panel{left:12px;right:12px;bottom:12px;width:auto;max-width:none;max-height:62vh}
.header-inner{padding:9px 0}.controls{gap:5px}.theme-toggle{padding:6px}.theme-toggle span{display:none}
.grid{grid-template-columns:1fr 1fr;gap:12px}.footer-grid{grid-template-columns:1fr 1fr;gap:18px}
.detail-cover{float:none;margin:0 auto 12px;display:block}.reader-stage{padding:8px}
.card{padding:16px}.lead h2{font-size:clamp(26px,8vw,38px)}}
@media(max-width:460px){.grid{grid-template-columns:1fr}.kana-grid{grid-template-columns:repeat(auto-fill,minmax(104px,1fr))}
.footer-grid{grid-template-columns:1fr}.brand h1{font-size:16px}.hanko{width:30px;height:30px;font-size:17px}
.drawer-head{padding:12px 14px}.drawer-group{padding:12px 14px}.actions .btn{width:100%}}
@media(max-width:340px){.controls .theme-toggle{display:none}}
"""

JS = """
(function(){const dark=localStorage.getItem('jishocli-theme')==='dark';if(dark)document.documentElement.classList.add('dark');
const a=localStorage.getItem('jishocli-accent');if(a)document.documentElement.style.setProperty('--accent',a);
document.addEventListener('DOMContentLoaded',()=>{const x=document.getElementById('theme-dark');if(x)x.checked=dark;});})();
function theme(dark){document.documentElement.classList.toggle('dark',dark);localStorage.setItem('jishocli-theme',dark?'dark':'light');}
function setAccent(c){document.documentElement.style.setProperty('--accent',c);localStorage.setItem('jishocli-accent',c);
document.getElementById('palette')?.classList.remove('open');}
function togglePalette(){document.getElementById('palette')?.classList.toggle('open');}
function setDrawer(open){const d=document.getElementById('drawer'),o=document.getElementById('drawer-overlay');
if(!d||!o)return;d.classList.toggle('open',open);o.classList.toggle('open',open);
document.body.classList.toggle('drawer-lock',open);
document.querySelector('.burger')?.setAttribute('aria-expanded',String(open));
if(open){const first=d.querySelector('.drawer-group[data-active="true"]')||d.querySelector('.drawer-group');
if(first)toggleDrawerGroup(first,true);}}
function toggleDrawer(){const d=document.getElementById('drawer');setDrawer(!d?.classList.contains('open'));}
function closeDrawer(){setDrawer(false);}
function toggleDrawerGroup(btn,forceOpen){const box=btn.nextElementSibling,open=forceOpen===true||btn.getAttribute('aria-expanded')!=='true';
document.querySelectorAll('.drawer-group').forEach(b=>{b.setAttribute('aria-expanded','false');
if(b.nextElementSibling)b.nextElementSibling.classList.remove('open');});
btn.setAttribute('aria-expanded',String(open));if(open&&box)box.classList.add('open');}
document.addEventListener('click',e=>{if(e.target.closest('.drawer a'))closeDrawer();else if(e.target.closest('#drawer-overlay'))closeDrawer();
const panel=document.getElementById('trans-panel');if(panel?.classList.contains('open')&&
!e.target.closest('#trans-panel')&&!e.target.closest('.trans-btn'))closeTrans();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeDrawer();closeTrans();}});
window.addEventListener('resize',()=>{if(window.innerWidth>1180)closeDrawer();});
let ttsToken=0;
function speak(text,rate){const a=document.getElementById('tts-audio');if(!a||!text)return;
const token=++ttsToken;a.pause();a.src='/api/tts?q='+encodeURIComponent(text);a.load();
a.oncanplay=()=>{if(token!==ttsToken)return;a.playbackRate=rate||1;
a.play().catch(()=>toast('Не удалось воспроизвести озвучку'));};
a.onerror=()=>{if(token===ttsToken)toast('Озвучка временно недоступна');};}
function speakSlow(text){speak(text,.62);}
function toast(message){const el=document.getElementById('toast');if(!el)return;
el.textContent=message;el.classList.add('show');clearTimeout(window.toastTimer);
window.toastTimer=setTimeout(()=>el.classList.remove('show'),2600);}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function quickTranslate(btn){const text=btn.dataset.text,to=btn.dataset.to;
const p=document.getElementById('trans-panel'),b=document.getElementById('trans-body');if(!p||!b)return;
p.classList.add('open');b.innerHTML='Перевожу…';
try{const r=await fetch('/api/translate?q='+encodeURIComponent(text)+'&to='+to);const d=await r.json();
b.innerHTML=d.error?esc(d.error):'<span class="tag">'+esc(d.source)+' → '+esc(d.target)+'</span>'+
'<div class="jp">'+esc(d.result)+'</div>'+(d.romaji?'<div class="roma">'+esc(d.romaji)+'</div>':'')+
'<div class="actions" style="justify-content:flex-start;margin-top:8px;flex-wrap:wrap">'+
'<button class="btn ghost sm" onclick="speak(this.dataset.t)" data-t="'+esc(d.result)+'">Перевод</button>'+
'<button class="btn ghost sm" onclick="speakSlow(this.dataset.t)" data-t="'+esc(d.result)+'">Медленно</button>'+
'<button class="btn ghost sm" onclick="speak(this.dataset.t)" data-t="'+esc(text)+'">Оригинал</button>'+
'<button class="btn ghost sm" onclick="copyText(this.dataset.t)" data-t="'+esc(d.result)+'">Копировать</button></div>';}
catch(e){b.textContent='Перевод недоступен.';}}
function copyText(text){if(navigator.clipboard)navigator.clipboard.writeText(text).then(()=>toast('Скопировано')).catch(()=>toast('Не удалось скопировать'));
else toast('Копирование недоступно');}
function closeTrans(){document.getElementById('trans-panel')?.classList.remove('open');}
function switchView(name,btn){document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
document.querySelectorAll('.tab-view').forEach(b=>b.classList.remove('active'));
document.getElementById('view-'+name)?.classList.add('active');btn?.classList.add('active');}
function fillExample(word,reading,meaning){const f=document.getElementById('manual-word');if(!f)return;
f.value=word;document.getElementById('manual-reading').value=reading;document.getElementById('manual-meaning').value=meaning;
switchView('manual');f.scrollIntoView({behavior:'smooth',block:'center'});}
function buildWord(btn){const box=btn.closest('.builder'),target=box.querySelector('.builder-target');
target.textContent=(target.textContent?target.textContent+' ':'')+btn.dataset.word;btn.disabled=true;}
function resetBuilder(btn){const box=btn.closest('.builder');
box.querySelectorAll('button[data-word]').forEach(b=>b.disabled=false);
box.querySelector('.builder-target').textContent='';box.querySelector('.builder-result').textContent='';}
function checkBuilder(btn){const box=btn.closest('.builder'),got=box.querySelector('.builder-target').textContent.trim(),
ok=got===box.dataset.answer;const res=box.querySelector('.builder-result');
res.textContent=ok?'Верно.':'Правильно: '+box.dataset.answer;res.style.color=ok?'#3d8b57':'var(--accent)';}
function startExamTimer(seconds){const el=document.getElementById('exam-timer');if(!el)return;let left=seconds;
const tick=()=>{const m=String(Math.floor(left/60)).padStart(2,'0'),s=String(left%60).padStart(2,'0');
el.textContent=m+':'+s;if(left<=0){document.getElementById('exam-form')?.submit();return;}left--;};tick();setInterval(tick,1000);}
function toggleTheater(){document.querySelector('.reader-shell')?.classList.toggle('theater');}
function toggleFocus(){toggleTheater();}
function toggleShortcuts(){document.getElementById('shortcuts')?.classList.toggle('open');}
function toggleBookFullscreen(){const w=document.querySelector('.book-frame-wrap');
if(!document.fullscreenElement)w?.requestFullscreen?.();else document.exitFullscreen?.();}
const EKEY='jishocli:exam-history';
function saveExamResult(pct,grade,estimate){try{const list=JSON.parse(localStorage.getItem(EKEY)||'[]');
list.unshift({pct,grade,estimate,date:new Date().toLocaleDateString()});localStorage.setItem(EKEY,JSON.stringify(list.slice(0,10)));}catch(e){}}
function renderExamHistory(){const box=document.getElementById('exam-history');if(!box)return;
let list=[];try{list=JSON.parse(localStorage.getItem(EKEY)||'[]');}catch(e){}
if(!list.length){box.innerHTML='<p class="muted">Экзаменов пока не было.</p>';return;}
box.innerHTML=list.map(x=>'<div class="bookmark"><span>'+esc(x.date)+' · '+esc(x.grade)+' · '+esc(x.estimate)+'</span><b>'+esc(x.pct)+'%</b></div>').join('');}
function toggleFullscreen(){if(!document.fullscreenElement)document.documentElement.requestFullscreen?.();
else document.exitFullscreen?.();}
document.addEventListener('keydown',e=>{if(e.key.toLowerCase()==='f'&&!e.target.matches('input,textarea'))toggleFocus();});
function recordAnswer(q,chosen,ok){window.quizAnswers=(window.quizAnswers||[]).concat({prompt:q.dataset.prompt,
answer:q.dataset.answer,speak:q.dataset.speak||'',explain:q.dataset.explain||'',chosen:chosen,ok:ok});}
function recordAnswerUI(q,chosen,ok){recordAnswer(q,chosen,ok);updateQuizScore();}
document.addEventListener('change',e=>{const i=e.target;if(!i.matches('.quiz-q input[type=radio]'))return;
const q=i.closest('.quiz-q');if(q.classList.contains('done'))return;q.classList.add('done');
const answer=q.dataset.answer;q.querySelectorAll('label').forEach(l=>{if(l.querySelector('input').value===answer)l.classList.add('ok');});
if(i.value!==answer)i.closest('label').classList.add('bad');
recordAnswerUI(q,i.value,i.value===answer);q.querySelectorAll('input').forEach(x=>x.disabled=true);});
function checkRecall(btn){const q=btn.closest('.quiz-q');if(q.classList.contains('done'))return;
const val=(q.querySelector('.recall-input')?.value||'').trim();
const ok=val.toLowerCase()===q.dataset.answer.toLowerCase();q.classList.add('done');
q.querySelector('.explain').innerHTML=(ok?'Верно. ':'Неверно. ')+'Правильно: <b>'+esc(q.dataset.answer)+'</b>. '+esc(q.dataset.explain||'');
recordAnswerUI(q,val||'(пусто)',ok);}
function updateQuizScore(){const s=document.getElementById('quiz-score');if(!s)return;
const done=document.querySelectorAll('.quiz-q.done').length,answers=window.quizAnswers||[],
ok=answers.filter(a=>a.ok).length;
s.textContent='Отвечено: '+done+' / '+document.querySelectorAll('.quiz-q').length+' · верно: '+ok+' · ошибок: '+(answers.length-ok);}
function showQuizResult(){const box=document.getElementById('quiz-summary');if(!box)return;
const list=window.quizAnswers||[];if(!list.length){box.innerHTML='<p class="muted">Ответьте хотя бы на один вопрос.</p>';
box.scrollIntoView({behavior:'smooth'});return;}
const ok=list.filter(a=>a.ok).length,pct=Math.round(100*ok/list.length);
box.innerHTML='<h2 class="section">Результат: '+ok+' / '+list.length+' ('+pct+'%)</h2>'+
'<div class="progress"><i style="width:'+pct+'%"></i></div>'+
list.map((a,i)=>'<div class="result"><span class="tag">'+(i+1)+' · '+(a.ok?'верно':'ошибка')+'</span>'+
'<p>'+esc(a.prompt)+'</p>'+(a.speak?'<p>Аудио: '+esc(a.speak)+
' <button class="speak" onclick="speak(this.dataset.t)" data-t="'+esc(a.speak)+'">воспроизвести</button></p>':'')+
'<p>Ваш ответ: <b>'+esc(a.chosen)+'</b> · Верно: <b>'+esc(a.answer)+'</b>'+
' <button class="speak" onclick="speak(this.dataset.t)" data-t="'+esc(a.answer)+'">озвучить</button></p>'+
'<p class="muted">'+esc(a.explain)+'</p></div>').join('');
box.scrollIntoView({behavior:'smooth'});}
function initDraw(){const wrap=document.querySelector('.draw-wrap');if(!wrap)return;
const c=document.getElementById('user-canvas'),ctx=c.getContext('2d'),diff=document.getElementById('diff-canvas');
function ink(){ctx.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()||'#c0392b';}
function resize(){c.width=wrap.clientWidth;c.height=wrap.clientHeight;if(diff){diff.width=c.width;diff.height=c.height;}
ctx.lineWidth=Math.max(4,c.width/62);ctx.lineCap='round';ctx.lineJoin='round';ink();}
resize();window.addEventListener('resize',resize);let drawing=false;
const pos=e=>{const r=c.getBoundingClientRect();return[e.clientX-r.left,e.clientY-r.top];};
c.addEventListener('pointerdown',e=>{drawing=true;c.setPointerCapture(e.pointerId);ink();const[x,y]=pos(e);ctx.beginPath();ctx.moveTo(x,y);});
c.addEventListener('pointermove',e=>{if(!drawing)return;const[x,y]=pos(e);ctx.lineTo(x,y);ctx.stroke();});
c.addEventListener('pointerup',()=>drawing=false);
document.getElementById('draw-clear').onclick=()=>{ctx.clearRect(0,0,c.width,c.height);if(diff)diff.getContext('2d').clearRect(0,0,diff.width,diff.height);
document.getElementById('draw-result').innerHTML='';};
document.getElementById('draw-toggle').onclick=()=>{const g=wrap.querySelector('.draw-guide');g.style.display=g.style.display==='none'?'':'none';};
document.getElementById('draw-check').onclick=()=>{const guide=wrap.querySelector('.draw-guide svg'),out=document.getElementById('draw-result');
if(!guide){out.textContent='Образец недоступен';return;}
const w=c.width,h=c.height,off=document.createElement('canvas');off.width=w;off.height=h;
const o=off.getContext('2d'),vb=guide.viewBox.baseVal,s=Math.min(w/vb.width,h/vb.height)*.88;
o.translate((w-vb.width*s)/2,(h-vb.height*s)/2);o.scale(s,s);o.lineWidth=9;o.lineCap='round';o.lineJoin='round';o.strokeStyle='#000';
guide.querySelectorAll('path').forEach(p=>{try{o.stroke(new Path2D(p.getAttribute('d')));}catch(e){}});
const g=o.getImageData(0,0,w,h).data,u=ctx.getImageData(0,0,w,h).data;
let gt=0,gh=0,ut=0,uh=0;for(let i=3;i<g.length;i+=4){const gp=g[i]>40,up=u[i]>40;
if(gp){gt++;if(up)gh++;}if(up){ut++;if(gp)uh++;}}
if(!ut){out.innerHTML='Нарисуйте знак и нажмите «Проверить».';return;}
const cov=gt?gh/gt:0,pre=ut?uh/ut:0,f=2*cov*pre/Math.max(cov+pre,1e-6),pct=Math.round(f*100);
if(diff){const dctx=diff.getContext('2d');dctx.clearRect(0,0,w,h);const img=dctx.createImageData(w,h);
for(let i=0;i<g.length;i+=4){const gp=g[i+3]>40,up=u[i+3]>40;
if(gp&&up){img.data[i]=61;img.data[i+1]=139;img.data[i+2]=87;img.data[i+3]=110;}
else if(gp){img.data[i]=192;img.data[i+1]=57;img.data[i+2]=43;img.data[i+3]=110;}
else if(up){img.data[i]=59;img.data[i+1]=91;img.data[i+2]=219;img.data[i+3]=110;}}
dctx.putImageData(img,0,0);}
const msg=pct>=80?'Отлично, знак узнаваем.':pct>=55?'Хорошо, уточните пропорции.':'Попробуйте ещё раз по порядку черт.';
out.innerHTML='<div class="num">'+pct+'%</div><div class="muted">покрытие '+Math.round(cov*100)+'% · точность '+Math.round(pre*100)+'%</div><p>'+msg+'</p>';};}
function animateStrokes(){const svg=document.querySelector('.draw-guide svg');if(!svg)return;
const paths=[...svg.querySelectorAll('path')],guide=document.querySelector('.draw-guide');guide.style.display='';
paths.forEach(p=>{const len=p.getTotalLength();p.style.strokeDasharray=len;p.style.strokeDashoffset=len;p.style.transition='none';});
let i=0;const status=document.getElementById('stroke-status');
const step=()=>{if(i>=paths.length){if(status)status.textContent='Готово';return;}
const p=paths[i++];if(status)status.textContent='Черта '+i+' / '+paths.length;
p.style.transition='stroke-dashoffset .45s ease';requestAnimationFrame(()=>{p.style.strokeDashoffset='0';});setTimeout(step,620);};step();}
function toggleCompare(){document.querySelector('.draw-wrap')?.classList.toggle('compare');}
function toggleDiff(){const d=document.getElementById('diff-canvas');if(d)d.style.display=d.style.display==='none'?'':'block';}
function cleanOCR(t){return String(t||'').replace(/[ \\t]+/g,' ').replace(/\\n{3,}/g,'\\n\\n')
.replace(/(?<=[\\u3040-\\u30ff\\u4e00-\\u9fff]) (?=[\\u3040-\\u30ff\\u4e00-\\u9fff])/g,'').trim();}
async function runOCR(lang,idx){const img=document.getElementById(idx?'ocr-image-'+idx:'ocr-image'),
out=document.getElementById(idx?'ocr-result-'+idx:'ocr-result');if(!img||!out)return;
if(typeof Tesseract==='undefined'){out.textContent='OCR-библиотека не загружена.';return;}
out.innerHTML='<div class="progress"><i style="width:10%"></i></div><p>Загружаю модель…</p>';
try{const r=await Tesseract.recognize(img,lang,{langPath:'https://cdn.jsdelivr.net/npm/@tesseract.js-data/'+lang.split('+')[0]+'/4.0.0_best_int',
logger:m=>{if(m.status==='recognizing text'){const bar=out.querySelector('.progress i');if(bar)bar.style.width=Math.round(m.progress*100)+'%';}}});
const text=cleanOCR(r.data.text),conf=Math.round(r.data.confidence||0);const hidden=document.getElementById(idx?'ocr-vocab-'+idx:'ocr-vocab');if(hidden)hidden.value=text;
out.innerHTML='<span class="tag">уверенность '+conf+'%</span><pre class="ocr-text">'+esc(text||'(пусто)')+'</pre>'+
'<div class="actions" style="justify-content:flex-start"><button class="btn ghost sm" onclick="speak(this.dataset.t)" data-t="'+esc(text)+'">Озвучить</button>'+
'<button class="btn ghost sm" onclick="ocrDownload(this)" data-t="'+esc(text)+'">Скачать TXT</button>'+
transButtons(text)+'</div>';}
catch(e){out.textContent='OCR ошибка: '+e.message;}}
function ocrDownload(btn){const blob=new Blob([btn.dataset.t],{type:'text/plain;charset=utf-8'});
const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='ocr-text.txt';a.click();}
function transButtons(text){const t=esc(JSON.stringify(text));return ['ru','en','ja'].map(x=>
'<button class="trans-btn" data-text="'+t+'" data-to="'+x+'" onclick="quickTranslate(this)">'+x.toUpperCase()+'</button>').join('');}
function dropFiles(e){e.preventDefault();const zone=e.currentTarget;zone.classList.remove('drag');
const files=[...e.dataTransfer.files].filter(f=>f.type.startsWith('image/'));if(!files.length)return;
const box=document.getElementById('ocr-gallery');if(!box)return;
files.forEach((f,i)=>{const r=new FileReader();r.onload=()=>{const n=Date.now()+'-'+i;
const card=document.createElement('div');card.className='panel';card.style.margin='14px 0';
card.innerHTML='<img id="ocr-image-'+n+'" class="ocr-preview" src="'+r.result+'" alt=""><div class="actions" style="justify-content:flex-start">'+
'<button class="btn sm" onclick="runOCR(\\'jpn\\',\\''+n+'\\')">Распознать</button></div><div id="ocr-result-'+n+'"></div>'+
'<form method="post" action="/learn-text"><input type="hidden" name="text" id="ocr-vocab-'+n+'"><button class="btn ghost sm">Разобрать слова</button></form>';
box.appendChild(card);};r.readAsDataURL(f);});}
const BKEY='jishocli:bookmarks';
function getBookmarks(){try{return JSON.parse(localStorage.getItem(BKEY)||'[]');}catch(e){return[];}}
function saveBookmark(){const el=document.querySelector('[data-bookmark]');if(!el)return;
const d=JSON.parse(el.dataset.bookmark),list=getBookmarks().filter(x=>!(x.chapter===d.chapter&&x.page===d.page));
list.unshift({...d,ts:Date.now()});localStorage.setItem(BKEY,JSON.stringify(list.slice(0,30)));
const b=document.getElementById('bm-status');if(b)b.textContent='Сохранено';}
function renderBookmarks(){const box=document.getElementById('bookmarks-list');if(!box)return;
const list=getBookmarks();if(!list.length){box.innerHTML='<p class="muted">Закладок пока нет.</p>';return;}
box.innerHTML=list.map((b,i)=>'<div class="bookmark"><a href="/read?id='+encodeURIComponent(b.manga)+'&chapter='+encodeURIComponent(b.chapter)+'&page='+b.page+'">'+
esc(b.title||'Манга')+' · гл. '+esc(b.chapter)+' · стр. '+b.page+'</a><button class="btn-icon" onclick="removeBookmark('+i+')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div>').join('');}
function removeBookmark(i){const l=getBookmarks();l.splice(i,1);localStorage.setItem(BKEY,JSON.stringify(l));renderBookmarks();}
const FKEY='jishocli:favs';
function getFavs(){try{return JSON.parse(localStorage.getItem(FKEY)||'[]');}catch(e){return[];}}
function toggleFav(href,title){const list=getFavs(),exists=list.some(f=>f.href===href);
const next=exists?list.filter(f=>f.href!==href):[{href,title},...list];localStorage.setItem(FKEY,JSON.stringify(next));
const b=document.getElementById('fav-status');if(b)b.textContent=exists?'Удалено из избранного':'Добавлено в избранное';}
function renderFavs(id){const box=document.getElementById(id||'favs-list');if(!box)return;
const list=getFavs();if(!list.length){box.innerHTML='<p class="muted">Пока пусто.</p>';return;}
box.innerHTML=list.map(f=>'<div class="bookmark"><a href="'+esc(f.href)+'">'+esc(f.title)+'</a></div>').join('');}
function readerKeys(){const p=document.getElementById('page-prev'),n=document.getElementById('page-next');
if(!p&&!n)return;document.addEventListener('keydown',e=>{if(e.target.matches('input,textarea'))return;
if(e.key==='ArrowLeft'&&p)location.href=p.href;
if(e.key==='ArrowRight'&&n)location.href=n.href;
if(e.key==='f'||e.key==='F')toggleTheater();
if(e.key==='b'||e.key==='B')saveBookmark();
if(e.key==='o'||e.key==='O')ocrPage();
if(e.key==='t'||e.key==='T')document.getElementById('panel-text')?.focus();
if(e.key==='?')toggleShortcuts();});}
document.addEventListener('keydown',e=>{if(e.key==='?'&&!document.querySelector('.reader-shell'))toggleShortcuts();});
function readerToggle(cls){document.getElementById('reader-image')?.classList.toggle(cls);}
function readerZoom(delta){const img=document.getElementById('reader-image');if(!img)return;
const w=parseInt(img.style.width||img.clientWidth)+delta;img.style.width=Math.max(240,Math.min(2400,w))+'px';img.classList.remove('wide');}
async function translatePanel(){const i=document.getElementById('panel-text'),o=document.getElementById('panel-result');
if(!i||!o||!i.value.trim())return;o.textContent='Перевожу…';
try{const r=await fetch('/api/translate?q='+encodeURIComponent(i.value.trim()));const d=await r.json();
o.innerHTML=d.error?esc(d.error):'<div class="jp" style="overflow-wrap:anywhere">'+esc(d.result)+'</div>'+(d.romaji?'<div class="roma">'+esc(d.romaji)+'</div>':'')+
'<div class="actions" style="justify-content:flex-start;flex-wrap:wrap">'+transButtons(d.result)+
'<button class="btn ghost sm" onclick="speak(this.dataset.t)" data-t="'+esc(d.result)+'">Перевод</button>'+
'<button class="btn ghost sm" onclick="speakSlow(this.dataset.t)" data-t="'+esc(d.result)+'">Медленно</button>'+
'<button class="btn ghost sm" onclick="speak(this.dataset.t)" data-t="'+esc(i.value)+'">Оригинал</button>'+
'<button class="btn ghost sm" onclick="copyText(this.dataset.t)" data-t="'+esc(d.result)+'">Копировать</button></div>';}
catch(e){o.textContent='Ошибка перевода.';}}
async function ocrPage(){const url=document.getElementById('reader-image')?.dataset.ocr;if(!url)return;
const out=document.getElementById('panel-result');out.textContent='Загружаю страницу…';
const img=new Image();img.crossOrigin='anonymous';img.src=url;await img.decode().catch(()=>{});
if(typeof Tesseract==='undefined'){out.textContent='OCR-библиотека не загружена.';return;}
try{const r=await Tesseract.recognize(img,'jpn',{langPath:'https://cdn.jsdelivr.net/npm/@tesseract.js-data/jpn/4.0.0_best_int',
logger:m=>{if(m.status==='recognizing text')out.textContent='OCR: '+Math.round(m.progress*100)+'%';}});
const text=cleanOCR(r.data.text);document.getElementById('panel-text').value=text;
const v=document.getElementById('ocr-vocab-text');if(v)v.value=text;
out.innerHTML='<span class="tag">уверенность '+Math.round(r.data.confidence||0)+'%</span><pre class="ocr-text">'+esc(text||'(пусто)')+'</pre>';
translatePanel();}catch(e){out.textContent='OCR ошибка: '+e.message;}}
document.addEventListener('DOMContentLoaded',()=>{initDraw();renderBookmarks();renderFavs();renderExamHistory();readerKeys();
if(document.body.classList.contains('reader-init-theater'))toggleTheater();
const bm=document.querySelector('[data-bookmark]');if(bm){const d=JSON.parse(bm.dataset.bookmark);
if(!getBookmarks().some(x=>x.chapter===d.chapter))saveBookmark();}
const zone=document.getElementById('ocr-drop');if(zone){zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('drag');});
zone.addEventListener('dragleave',()=>zone.classList.remove('drag'));zone.addEventListener('drop',dropFiles);}});
"""

NAV_GROUPS = [
    ("Обучение", [("/learn", "Курсы", "book"), ("/exam", "Экзамен", "quiz"),
                  ("/quiz", "Тесты", "quiz"), ("/cards", "Карточки", "cards"), ("/study", "Повторение", "refresh"),
                  ("/stats", "Статистика", "chart")]),
    ("Практика", [("/conversation", "Общение", "chat"), ("/shadowing", "Аудирование", "headphones"),
                  ("/builder", "Конструктор", "sparkle"), ("/random", "Случайное слово", "shuffle"),
                  ("/flashcards", "Карточки+", "cards"), ("/favorites", "Избранное", "heart")]),
    ("Язык", [("/search", "Словарь", "search"), ("/words", "Слова N5", "book"),
              ("/translate", "Перевод", "language"), ("/hiragana", "Хирагана", "book"), ("/katakana", "Катакана", "book"),
              ("/kanji", "Кандзи", "pen"), ("/draw", "Письмо", "pen"), ("/ocr", "OCR", "ocr")]),
    ("Культура", [("/anime", "Аниме", "tv"), ("/manga", "Манга", "layers"),
                  ("/books", "Книги", "book"), ("/reader", "Читалка", "reader"), ("/facts", "Факты", "globe")]),
]

ACCENTS = [("#c0392b", "красный"), ("#3b5bdb", "индиго"), ("#5a7d4f", "матча"),
           ("#c76b8f", "сакура"), ("#b98a2f", "золото"), ("#7d4fc9", "фиолет")]
DRAW_SAMPLES = list("あいうえおかきくけこアイウエオカキクケコ") + list("日月火水木金土山川人大小中上学")
TESSERACT_SCRIPT = '<script src="https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/tesseract.min.js"></script>'
GENRES = ["Action", "Adventure", "Fantasy", "Drama", "Romance", "Comedy", "Sci-Fi",
          "Slice of Life", "Mystery", "Historical", "Supernatural"]


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def speak_btn(text: str, big: bool = False) -> str:
    arg = html.escape(json.dumps(str(text), ensure_ascii=False), quote=True)
    return (f' <button type="button" class="speak{" big" if big else ""}" '
            f'onclick="speak({arg})" title="Озвучить">{icon("volume", 18 if big else 14)}</button>')


def trans_buttons(text: str) -> str:
    arg = html.escape(json.dumps(str(text), ensure_ascii=False), quote=True)
    return "".join(f'<button class="trans-btn" data-text="{arg}" data-to="{code}" '
                   f'onclick="quickTranslate(this)">{label}</button>'
                   for code, label in (("en", "EN"), ("ru", "RU"), ("ja", "JA")))


def voice_text(text: str) -> str:
    """Wrap every line in a speakable span with translation controls."""
    chunks = [c.strip() for c in str(text).split("\n") if c.strip()]
    if not chunks:
        return ""
    return "".join(f'<span class="voice-line">{esc(c)}{speak_btn(c)}{trans_buttons(c)}</span><br>'
                   for c in chunks)


def link(url: str, label: str) -> str:
    return f'<a href="{esc(url)}" target="_blank" rel="noreferrer">{esc(label)} {icon("external", 13)}</a>'


def page(title: str, body: str, path: str = "", ocr: bool = False, focus: bool = False) -> bytes:
    def active(href: str) -> bool:
        if path.startswith("/lesson/") and href == "/learn":
            return True
        if path.startswith("/read") and href == "/reader":
            return True
        if path == "/vocab" and href == "/learn":
            return True
        return href == path

    groups = ""
    drawer = ""
    for label, items in NAV_GROUPS:
        links = "".join(f'<a href="{href}"{" class=active" if active(href) else ""}>'
                        f'{icon(ico, 15)}{text}</a>' for href, text, ico in items)
        here = " here" if any(active(h) for h, _, _ in items) else ""
        groups += (f'<details class="navgroup{here}"><summary>{label}</summary>'
                   f'<div class="dropdown">{links}</div></details>')
        is_here = any(active(h) for h, _, _ in items)
        drawer += (f'<div class="drawer-section">'
                   f'<button class="drawer-group" data-active="{str(is_here).lower()}" '
                   f'aria-expanded="false" onclick="toggleDrawerGroup(this)">{label}'
                   f'<span class="chev">{icon("right", 16)}</span></button>'
                   f'<div class="drawer-items">{links}</div></div>')
    swatches = ("<button style=\"background:#c0392b\" title=\"По умолчанию\" onclick=\"setAccent('#c0392b')\">·</button>" +
                "".join(f'<button style="background:{c}" title="{n}" aria-label="{n}" onclick="setAccent(\'{c}\')"></button>'
                        for c, n in ACCENTS))
    footer = f"""<footer><div class="wrap"><div class="footer-grid">
<div><h4>jishocli</h4><p>Японский словарь и учебник в терминале и браузере.</p>
<p>Словарь Jisho · Janome · AniList · MangaDex · KanjiVG.</p></div>
<div><h4>Обучение</h4><a href="/learn">Курсы с нуля</a><a href="/quiz">Тесты</a><a href="/draw">Письмо</a><a href="/cards?tab=generator">Генератор карточек</a><a href="/cards">Карточки</a></div>
<div><h4>Инструменты</h4><a href="/ocr">OCR текста</a><a href="/translate">Перевод</a><a href="/reader">Читалка</a><a href="/stats">Статистика</a></div>
<div><h4>Данные</h4><a href="/export.csv">Экспорт CSV</a><a href="/export.anki">Экспорт Anki</a>{link('https://www.jlpt.jp/e/', 'JLPT')}</div>
</div><div class="footer-bottom">Карточки и прогресс хранятся локально · KanjiVG: CC BY-SA 3.0</div></div></footer>"""
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)} · jishocli</title><style>{CSS}</style></head>'
            f'<body{" class=reader-init-theater" if focus else ""}>'
            f'<header class="site-header"><div class="wrap header-inner">'
            f'<button class="burger" onclick="toggleDrawer()" aria-label="Меню" aria-expanded="false">{icon("menu", 18)}</button>'
            f'<a class="brand" href="/"><span class="hanko">辞</span><h1>jishocli<small>日本語</small></h1></a>'
            f'<form class="head-search" action="/search"><input name="q" placeholder="Найти слово…"></form>'
            f'<nav class="nav">{groups}</nav><div class="controls">'
            f'<div class="palette-wrap"><button class="btn-icon" onclick="togglePalette()" title="Акцент">{icon("palette")}</button>'
            f'<div class="palette" id="palette">{swatches}</div></div>'
            f'<label class="theme-toggle"><input id="theme-dark" type="checkbox" onchange="theme(this.checked)">'
            f'<i class="switch"></i>тема</label></div></div></header>'
            f'<div class="overlay" id="drawer-overlay" onclick="toggleDrawer()"></div>'
            f'<aside class="drawer" id="drawer"><div class="drawer-head"><b>Навигация</b>'
            f'<button class="btn-icon" onclick="toggleDrawer()">{icon("close")}</button></div>{drawer}</aside>'
            f'<main class="wrap"><audio id="tts-audio" preload="none"></audio>{body}</main>{footer}'
            f'<div id="toast"></div>'
            f'<div id="shortcuts"><h3>Горячие клавиши</h3>'
            f'<p class="muted">← / → — страницы манги<br>F — театральный режим<br>B — закладка<br>'
            f'O — OCR страницы<br>T — перевод<br>? — эта справка<br>Esc — закрыть</p>'
            f'<p style="text-align:center"><button class="btn ghost sm" onclick="toggleShortcuts()">Закрыть</button></p></div>'
            f'<div id="trans-panel"><div style="display:flex;justify-content:space-between">'
            f'<b>Перевод</b><button class="btn-icon" onclick="closeTrans()">{icon("close",14)}</button></div>'
            f'<div id="trans-body"></div></div>'
            f'{TESSERACT_SCRIPT if ocr else ""}<script>{JS}</script></body></html>').encode()


def lead(title: str, subtitle: str = "", form: str = "") -> str:
    return f'<div class="lead"><h2>{title}</h2>' + (f'<p>{subtitle}</p>' if subtitle else "") + form + '</div>'


def search_form(action: str, value: str = "", placeholder: str = "слово или фраза", extra: str = "") -> str:
    return (f'<form class="search" action="{action}"><input name="q" value="{esc(value)}" '
            f'placeholder="{esc(placeholder)}">{extra}<button class="btn sm">{icon("search")} Найти</button></form>')


def vocab_html(rows: list[dict]) -> str:
    if not rows:
        return '<p class="muted">Не удалось выделить слова.</p>'
    out = ""
    for v in rows:
        out += f"""<div class="result"><h3>{esc(v['word'])} <span class="muted">{esc(v['reading'])}</span>{speak_btn(v['word'])}</h3>
<div class="roma">{esc(v['romaji'])} {trans_buttons(v['word'])}</div><p>{esc(v['pos'])} · {esc(v['meaning'] or '—')}</p>
<form method="post" action="/card"><input type="hidden" name="word" value="{esc(v['base'])}">
<input type="hidden" name="reading" value="{esc(v['reading'])}"><input type="hidden" name="meaning" value="{esc(v['meaning'])}">
<button class="btn ghost sm">{icon('plus')} В карточки</button></form></div>"""
    return out


def quiz_html(questions: list[dict]) -> str:
    out = f'<div class="score" id="quiz-score">Отвечено: 0 / {len(questions)} · ошибок: 0</div>'
    for i, q in enumerate(questions):
        speak = speak_btn(q["speak"], big=q["kind"] == "audio") if q["speak"] else ""
        if q.get("mode") == "recall":
            controls = (f'<div class="recall-row"><input class="recall-input" placeholder="Введите ответ">'
                        f'<button class="btn sm" onclick="checkRecall(this)">Проверить</button></div>')
        else:
            controls = '<div class="opts">' + "".join(
                f'<label><input type="radio" name="q{i}" value="{esc(o)}"><span>{esc(o)}</span></label>'
                for o in q["options"]) + '</div>'
        out += (f'<div class="quiz-q" data-answer="{esc(q["answer"])}" data-prompt="{esc(q["prompt"])}" '
                f'data-explain="{esc(q["explain"])}" data-speak="{esc(q.get("speak") or "")}">'
                f'<span class="tag">{i+1} · {q["kind"]}</span>{speak}'
                f'<p style="font-size:17px;margin:6px 0 0">{esc(q["prompt"])}</p>{controls}'
                f'<div class="explain"></div></div>')
    return out


def word_menu(word: str, reading: str = "", meaning: str = "") -> str:
    first_kanji = next((c for c in word if "\u4e00" <= c <= "\u9fff"), "")
    first_char = word[:1]
    actions = (f'<div class="menu-row">{speak_btn(word)}{trans_buttons(word)}'
               f'<a class="trans-btn" href="/quiz?type=vocab">тест</a>'
               + (f'<a class="trans-btn" href="/kanji?q={esc(first_kanji)}">кандзи</a>' if first_kanji else "")
               + f'<a class="trans-btn" href="/draw?q={esc(first_char)}">писать</a></div>'
               f'<form method="post" action="/card"><input type="hidden" name="word" value="{esc(word)}">'
               f'<input type="hidden" name="reading" value="{esc(reading)}">'
               f'<input type="hidden" name="meaning" value="{esc(meaning)}">'
               f'<button class="btn ghost sm">{icon("plus")} в карточки</button></form>')
    return f'<details class="word-menu"><summary>Действия со словом</summary>{actions}</details>'


class Handler(BaseHTTPRequestHandler):
    store = Store()

    def log_message(self, *_):
        return

    def send(self, content: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8",
             extra: dict | None = None):
        headers = dict(extra or {})
        if (len(content) > 1024 and "gzip" in self.headers.get("Accept-Encoding", "")
                and content_type.startswith(("text/", "application/json"))):
            content = gzip.compress(content)
            headers["Content-Encoding"] = "gzip"
            headers["Vary"] = "Accept-Encoding"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(content)

    def redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        path = urlparse(self.path).path
        LOGGER.info("POST %s", path)
        if path == "/ocr":
            return self.ocr_post(body)
        data = parse_qs(body.decode("utf-8", "replace"))
        if path == "/complete":
            complete(self.store, data.get("id", ["01"])[0])
            return self.redirect(f"/lesson/{data.get('id', ['01'])[0]}")
        if path == "/card":
            self.store.add({"word": data.get("word", [""])[0], "reading": data.get("reading", [""])[0],
                            "meaning": data.get("meaning", [""])[0], "source": "web"})
            tab = data.get("tab", [""])[0]
            if tab and tab in {"manual", "generator", "check", "data"}:
                return self.redirect(f"/cards?tab={tab}&saved=1")
            target = urlparse(self.headers.get("Referer", "")).path
            return self.redirect(target if target.startswith("/") else "/cards")
        if path == "/review":
            word = data.get("word", [""])[0]
            card = next((c for c in self.store.cards if c.get("word") == word), None)
            if card:
                self.store.review(card, int(data.get("quality", ["3"])[0]))
            return self.redirect("/study")
        if path == "/learn-text":
            return self.learn_page(text=data.get("text", [""])[0])
        if path == "/generate-cards":
            return self.generate_cards(data.get("text", [""])[0])
        if path == "/exam/start":
            level = data.get("level", ["MIXED"])[0]
            try:
                count = min(max(int(data.get("count", ["20"])[0]), 5), 40)
            except ValueError:
                count = 20
            return self.exam_page(questions=exam_engine.generate_exam(level, count))
        if path == "/conversation/check":
            scenario = convo_engine.get_scenario(data.get("scenario", [""])[0])
            if not scenario:
                return self.send(page("Ошибка", lead("Общение", "Сценарий не найден.")), 400)
            chosen = [data.get(f"a{i}", [""])[0] for i in range(len(scenario["turns"]))]
            return self.conversation_result(scenario, convo_engine.evaluate(scenario, chosen))
        if path == "/exam/submit":
            try:
                questions = json.loads(data.get("questions", ["[]"])[0])
                answers = {k[2:]: v[0] for k, v in data.items() if k.startswith("q") and k[2:].isdigit()}
                return self.exam_result(exam_engine.evaluate(questions, answers))
            except (ValueError, TypeError):
                return self.send(page("Ошибка", lead("Экзамен", "Не удалось проверить ответы.")), 400)
        if path == "/cards/bulk":
            saved = 0
            for raw in data.get("cards", []):
                try:
                    card = json.loads(raw)
                except ValueError:
                    continue
                if self.store.add({"word": card.get("word", ""), "reading": card.get("reading", ""),
                                   "meaning": card.get("meaning", ""),
                                   "romaji": card.get("romaji", ""), "source": "generator"}):
                    saved += 1
            return self.redirect(f"/cards?saved={saved}")
        if path == "/cards/import":
            try:
                added = self.store.import_json(data.get("data", [""])[0])
                return self.redirect(f"/cards?saved={added}")
            except (ValueError, TypeError) as exc:
                return self.send(page("Импорт", lead("Импорт", esc(exc))), 400)
        if path == "/goal":
            self.store.set_goal(int(data.get("goal", ["10"])[0] or 10))
            return self.redirect("/stats")
        return self.send(page("404", lead("Не найдено")), 404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path, q = parsed.path, parse_qs(parsed.query)
        LOGGER.info("GET %s", self.path)
        routes = {
            "/": lambda: self.home(),
            "/learn": lambda: self.courses(q),
            "/search": lambda: self.search(q),
            "/translate": lambda: self.translate_page(q.get("q", [""])[0], q.get("to", [""])[0]),
            "/kana": lambda: self.kana_index(),
            "/hiragana": lambda: self.kana_page("hira"),
            "/katakana": lambda: self.kana_page("kata"),
            "/kanji": lambda: self.kanji(q.get("q", [""])[0]),
            "/draw": lambda: self.draw(q.get("q", [""])[0]),
            "/exam": lambda: self.exam_page(),
            "/quiz": lambda: self.quiz_page(q),
            "/ocr": lambda: self.ocr_page(),
            "/anime": lambda: self.media("anime", q),
            "/manga": lambda: self.media("manga", q),
            "/title": lambda: self.title_detail(q.get("kind", ["anime"])[0], q.get("id", [""])[0]),
            "/books": lambda: self.books(q),
            "/book/read": lambda: self.book_read(q),
            "/reader": lambda: self.reader_search(q),
            "/read": lambda: self.read(q),
            "/vocab": lambda: self.learn_page(kind=q.get("kind", [""])[0],
                                              media_id=q.get("id", [""])[0], text=q.get("text", [""])[0]),
            "/words": lambda: self.words(q),
            "/cards": lambda: self.cards(q),
            "/study": lambda: self.study(),
            "/random": lambda: self.random_word_page(q),
            "/builder": lambda: self.builder_page(q),
            "/shadowing": lambda: self.shadowing_page(),
            "/conversation": lambda: self.conversation_page(q),
            "/flashcards": lambda: self.flashcards_page(),
            "/favorites": lambda: self.favorites_page(),
            "/stats": lambda: self.stats(),
            "/facts": lambda: self.facts(q.get("q", [""])[0]),
            "/api/translate": lambda: self.api_translate(q),
            "/api/tts": lambda: self.tts(q),
            "/image": lambda: self.image(q.get("url", [""])[0]),
            "/download": lambda: self.download(q),
        }
        try:
            if path.startswith("/lesson/"):
                return self.lesson_page(path.rsplit("/", 1)[1])
            if path == "/export.csv":
                return self.send(self.store.export_csv().encode(), content_type="text/csv; charset=utf-8",
                                 extra={"Content-Disposition": 'attachment; filename="jishocli-cards.csv"'})
            if path == "/export.anki":
                return self.send(self.store.export_anki().encode(), content_type="text/plain; charset=utf-8",
                                 extra={"Content-Disposition": 'attachment; filename="jishocli-cards.txt"'})
            if path == "/export.json":
                return self.send(self.store.export_json().encode(), content_type="application/json; charset=utf-8",
                                 extra={"Content-Disposition": 'attachment; filename="jishocli-cards.json"'})
            if path in routes:
                return routes[path]()
            self.send(page("404", lead("Страница не найдена", '<a href="/">На главную</a>')), 404)
        except Exception as exc:
            LOGGER.exception("Request failed: %s", self.path)
            self.send(page("Ошибка", lead("Не удалось загрузить", esc(exc))), 502)

    # --- main pages -----------------------------------------------------------

    def home(self):
        p = course_progress(self.store, "START")
        jp, reading, ru = daily_word()
        body = f"""<section class="hero"><span class="kanji-bg">学</span>
<h1>Японский,<br>понятно.</h1><p>Словарь, курсы с нуля, OCR, читалка манги и карточки в одном месте.</p>
<div class="actions"><a class="btn" href="/learn">{icon('book')} Начать обучение</a>
<a class="btn ghost" href="/ocr">{icon('ocr')} Распознать текст</a>
<a class="btn ghost" href="/quiz">{icon('quiz')} Проверить себя</a></div></section>"""
        body += f"""<div class="panel daily"><span class="tag">слово дня</span><div class="jp">{jp}{speak_btn(jp)}</div>
<div class="roma">{esc(reading_romaji(reading))} {trans_buttons(jp)}</div>
<p class="muted">{esc(reading)} · {esc(ru)}</p>
<form method="post" action="/card"><input type="hidden" name="word" value="{esc(jp)}">
<input type="hidden" name="reading" value="{esc(reading)}"><input type="hidden" name="meaning" value="{esc(ru)}">
<button class="btn ghost sm">{icon('plus')} В карточки</button></form></div>"""
        body += '<div class="bookmarks"><h2 class="section">Избранное</h2><div id="favs-list"></div></div>'
        body += '<h2 class="section">Что хотите сделать?</h2><div class="grid">'
        tiles = [("/learn", "book", "Курсы с нуля", f"{p['done']}/{p['total']} уроков START пройдено"),
                 ("/hiragana", "language", "Хирагана", "Все знаки с озвучкой"),
                 ("/katakana", "language", "Катакана", "Азбука заимствований"),
                 ("/ocr", "ocr", "OCR текста", "Распознать фото или страницу"),
                 ("/draw", "pen", "Письмо", "Кандзи и азбуки, оценка схожести"),
                 ("/reader", "reader", "Читалка манги", "Закладки, оригинал и переводы"),
                 ("/quiz?type=audio", "volume", "Аудио-тесты", "Слушайте и выбирайте"),
                 ("/study", "cards", "Повторение", f"{len(self.store.cards)} карточек, серия {self.store.streak()} дн.")]
        for href, ico, title, sub in tiles:
            body += (f'<a class="card" href="{href}"><div class="ico">{icon(ico, 24)}</div>'
                     f'<h3>{title}</h3><p>{sub}</p></a>')
        self.send(page("Главная", body + '</div>', "/"))

    def courses(self, q):
        course_id = q.get("course", ["START"])[0]
        course = course_by_id(course_id) or COURSES[0]
        tabs = "".join(f'<a class="{"active" if c["id"] == course["id"] else ""}" '
                       f'href="/learn?course={c["id"]}">{c["title"]}</a>' for c in COURSES)
        p = course_progress(self.store, course["id"])
        cards = ""
        for i, item in enumerate(course["lessons"], 1):
            done = (item["id"] if "-" in item["id"] else f"N5-{str(item['id']).zfill(2)}") in p["ids"]
            cards += (f'<a class="card" href="/lesson/{item["id"]}" style="animation-delay:{min(i*20,300)}ms">'
                      f'<span class="tag">{item["id"]} · {item["kind"]}</span><h3>{esc(item["title"])}</h3>'
                      f'<p>{"Пройдено" if done else "Открыть урок"}</p></a>')
        done_count, total_count = p["done"], p["total"]
        subtitle = f"{done_count} из {total_count} уроков курса {esc(course['title'])}"
        body = (lead("Курсы японского", subtitle) +
                f'<div class="progress"><i style="width:{100*done_count//max(total_count,1)}%"></i></div>'
                f'<div class="tabs">{tabs}</div><div class="grid">{cards}</div>')
        self.send(page("Курсы", body, "/learn"))

    def lesson_page(self, lesson_id):
        item = get_lesson(lesson_id)
        if not item:
            return self.send(page("404", lead("Урок не найден")), 404)
        nav = lesson_neighbors(lesson_id)
        course = nav["course"] if nav else COURSES[0]
        selector = "".join(f'<option value="{l["id"]}"{" selected" if l["id"] == item["id"] else ""}>'
                           f'{l["id"]} · {l["title"]}</option>' for l in course["lessons"])
        prev = (f'<a class="btn ghost sm" href="/lesson/{nav["prev"]}">{icon("left")} Назад</a>'
                if nav and nav["prev"] else '<span class="muted">Начало курса</span>')
        nxt = (f'<a class="btn sm" href="/lesson/{nav["next"]}">Далее {icon("right")}</a>'
               if nav and nav["next"] else '<span class="muted">Курс завершён</span>')
        course_tabs = "".join(f'<a class="{"active" if c["id"] == course["id"] else ""}" '
                              f'href="/learn?course={c["id"]}">{c["title"]}</a>' for c in COURSES)
        quiz_items = quiz_engine.from_lesson_quiz(item["quiz"], seed=7)
        links = "".join(link(url, name) for name, url in item["links"])
        order = item.get("word_order")
        if order:
            tiles = list(order["tokens"])
            random.Random(sum(ord(c) for c in item["id"])).shuffle(tiles)
            builder = (f'<div class="builder" data-answer="{esc(order["answer"])}"><h3>Соберите предложение</h3>'
                       f'<div class="builder-tiles">' + "".join(
                           f'<button type="button" data-word="{esc(t)}" onclick="buildWord(this)">{esc(t)}</button>'
                           for t in tiles) + '</div><div class="builder-target"></div>'
                       f'<div class="actions" style="justify-content:flex-start">'
                       f'<button class="btn sm" onclick="checkBuilder(this)">Проверить</button>'
                       f'<button class="btn ghost sm" onclick="resetBuilder(this)">Сбросить</button></div>'
                       f'<p class="builder-result"></p></div>')
        else:
            builder = ""
        from .language import analyze
        seen, word_rows = set(), ""
        dialogue_lines = ""
        for line in item["practice"].split("\n"):
            if not line.strip():
                continue
            dialogue_lines += (f'<div class="panel" style="margin:0 0 10px">{esc(line)}'
                               f'{speak_btn(line)}<button class="trans-btn" onclick="speakSlow(this.dataset.t)" '
                               f'data-t="{esc(line)}">медленно</button>{trans_buttons(line)}</div>')
        for token in analyze(item["practice"]):
            base = token["base"]
            if base in seen or len(base) < 2:
                continue
            seen.add(base)
            word_rows += (f'<div class="result"><h3>{esc(token["word"])} {speak_btn(token["word"])}</h3>'
                          f'<div class="roma">{esc(token["reading"])} · {esc(token["romaji"])}</div>'
                          f'<p class="muted">{esc(token["pos"])}</p>{word_menu(token["word"], token["reading"], "")}</div>')
            if len(seen) >= 10:
                break
        body = f"""<div class="tabs">{course_tabs}</div>
<div class="panel" style="max-width:820px;margin:0 auto 20px"><span class="tag">{course['title']}</span>
<h3 style="margin:4px 0 8px;font:22px Georgia,serif">Урок {nav['index']+1 if nav else 1} из {nav['total'] if nav else 1}</h3>
<div class="actions" style="justify-content:space-between">{prev}
<select onchange="if(this.value)location.href='/lesson/'+this.value" style="max-width:340px">{selector}</select>{nxt}</div></div>
<article class="lesson"><span class="tag">{item['id']} · {item['kind']}</span><h2>{esc(item['title'])}</h2>
<div class="tabs"><button class="tab-view active" onclick="switchView('lesson',this)">Урок</button>
<button class="tab-view" onclick="switchView('practice',this)">Практика</button>
<button class="tab-view" onclick="switchView('dialogue',this)">Диалог</button>
<button class="tab-view" onclick="switchView('audio',this)">Аудио</button>
<button class="tab-view" onclick="switchView('test',this)">Тест</button>
<button class="tab-view" onclick="switchView('words',this)">Слова</button></div>
<div class="view active" id="view-lesson">
<h3>Цель</h3><p>{voice_text(item['goal'])}</p>
<h3>Объяснение</h3><p>{voice_text(item['text'])}</p>
<h3>Грамматика</h3><p>{voice_text(item['grammar'])}</p>
<h3>Синтаксис</h3><p>{voice_text(item['syntax'])}</p>
<h3>Произношение</h3><p class="roma">{esc(item['pronunciation'])}{speak_btn(item['pronunciation'], big=True)}</p></div>
<div class="view" id="view-practice"><h3>Примеры</h3><div class="practice">{voice_text(item['practice'])}</div>{builder}</div>
<div class="view" id="view-dialogue"><h3>Диалог и реплики</h3>{dialogue_lines}</div>
<div class="view" id="view-audio"><h3>Аудиотренировка</h3>
<p class="muted">Слушайте в обычном и замедленном темпе, повторяйте вслух. Кнопки перевода помогут проверить смысл.</p>
<p class="roma">{esc(item['pronunciation'])}{speak_btn(item['pronunciation'], big=True)}</p>
{dialogue_lines}</div>
<div class="view" id="view-test"><h3>Тест урока</h3>{quiz_html(quiz_items)}
<div id="quiz-summary"></div>
<p><button class="btn ghost sm" onclick="showQuizResult()">{icon('check')} Показать результат</button>
<a href="/quiz?type=grammar" class="btn ghost sm">{icon('quiz')} Случайный тест</a></p></div>
<div class="view" id="view-words"><h3>Слова урока</h3>{word_rows or '<p class="muted">Слов не найдено.</p>'}</div>
<h3>Источники</h3><div>{links}</div>
<form method="post" action="/complete"><input type="hidden" name="id" value="{item['id']}">
<p><button class="btn sm">{icon('check')} Отметить пройденным</button></p></form></article>"""
        self.send(page(item["title"], body, "/learn"))

    def search(self, q):
        tab = q.get("tab", ["words"])[0]
        text = q.get("q", [""])[0]
        tabs = "".join(f'<a class="{"active" if t == tab else ""}" href="/search?tab={t}&q={esc(text)}">{label}</a>'
                       for t, label in (("words", "Слова"), ("anime", "Аниме"), ("manga", "Манга"), ("facts", "Факты")))
        actions = {"words": "/search", "anime": "/anime", "manga": "/manga", "facts": "/facts"}
        extra = f'<input type="hidden" name="tab" value="{tab}">' if tab in {"anime", "manga", "facts"} else ""
        body = lead("Поиск", "Слова, произведения и статьи о Японии.",
                    f'<form class="search" action="{actions.get(tab, "/search")}"><input name="q" '
                    f'value="{esc(text)}" placeholder="Что ищем?">{extra}'
                    f'<button class="btn sm">{icon("search")} Найти</button></form>')
        body += f'<div class="tabs">{tabs}</div>'
        if text:
            if tab == "words":
                for row in search_jisho(text)[:8]:
                    jp = row.get("japanese", [{}])[0]
                    word = jp.get("word") or jp.get("reading", "?")
                    reading = jp.get("reading", "")
                    gloss = "; ".join(m for s in row.get("senses", []) for m in s.get("english_definitions", []))
                    body += f"""<div class="result"><h3>{esc(word)} <span class="muted">{esc(reading)}</span>{speak_btn(word)}</h3>
<div class="roma">{esc(reading_romaji(reading or word))} {trans_buttons(word)}</div><p>{esc(gloss)}</p>
{word_menu(word, reading, gloss)}</div>"""
            elif tab == "facts":
                for row in search_topics(text, "ru", 5):
                    body += f'<div class="result"><h3>{esc(row.get("title", ""))}</h3><p>{esc(row.get("extract", ""))}</p>{link(row.get("fullurl", "#"), "Wikipedia")}</div>'
            else:
                for row in search_media(text, tab, 6):
                    body += f'<div class="result"><h3>{esc(row.get("title", "—"))}</h3><p>{esc((row.get("synopsis") or "")[:250])}</p></div>'
        self.send(page("Поиск", body, "/search"))

    def translate_page(self, text, target):
        extra = ('<select name="to"><option value="">авто</option><option value="ru">русский</option>'
                 '<option value="ja">японский</option><option value="en">английский</option></select>')
        body = lead("Перевод", "MyMemory + разбор Janome.",
                    search_form("/translate", text, "ありがとう / Спасибо", extra))
        if text:
            source = detect_language(text)
            dest = target or ("ru" if source == "ja" else "ja")
            result = translate(text, source, dest)
            body += f'<div class="result"><span class="tag">{source} → {dest}</span><h3>{esc(result)}'
            if dest == "ja":
                body += speak_btn(result, big=True)
            body += f' {trans_buttons(result)}</h3>'
            if dest == "ja":
                body += f'<div class="roma">{esc(phrase_romaji(result))}</div>'
            if source == "ja":
                from .language import analyze
                body += "<h3>Разбор</h3>" + "".join(
                    f'<p>{esc(r["word"])} · {esc(r["reading"])} · <span class="roma">{esc(r["romaji"])}</span>'
                    f' · {esc(r["pos"])}{speak_btn(r["word"])}{trans_buttons(r["word"])}</p>'
                    for r in analyze(text))
            body += '</div>'
        self.send(page("Перевод", body, "/translate"))

    def kana_index(self):
        body = lead("Азбуки", "Хирагана и катакана — отдельно, с произношением и рисованием.")
        body += f"""<div class="grid"><a class="card" href="/hiragana"><div class="ico">{icon('language',24)}</div><h3>Хирагана</h3><p>Основная азбука.</p></a>
<a class="card" href="/katakana"><div class="ico">{icon('language',24)}</div><h3>Катакана</h3><p>Заимствования и имена.</p></a>
<a class="card" href="/draw?q=%E3%81%82"><div class="ico">{icon('pen',24)}</div><h3>Рисование азбуки</h3><p>Порядок черт и оценка.</p></a></div>"""
        self.send(page("Азбуки", body, "/kana"))

    def kana_page(self, script):
        title = "Хирагана" if script == "hira" else "Катакана"
        body = lead(title, "Нажмите на знак, чтобы услышать произношение.")
        for name, table in (("Базовые знаки", kana.BASIC), ("Дакутэн и хандакутэн", kana.DAKUTEN), ("Ёон", kana.YOON)):
            cells = ""
            for h, k, r, hint in table:
                char = h if script == "hira" else k
                other = k if script == "hira" else h
                cells += (f'<div class="kana-cell" onclick="speak(\'{char}\')" title="{esc(hint)}">'
                          f'<div class="big">{char}</div><div class="sub">{other}</div><div class="r">{r}</div></div>')
            body += f'<h2 class="section">{name}</h2><div class="kana-grid">{cells}</div>'
        other = "/katakana" if script == "hira" else "/hiragana"
        body += (f'<div class="actions"><a class="btn ghost" href="{other}">Другая азбука</a>'
                 f'<a class="btn ghost" href="/draw?q={"あ" if script == "hira" else "ア"}">Рисовать</a>'
                 f'<a class="btn" href="/quiz?type=audio">Аудио-тест</a></div>')
        self.send(page(title, body, f"/{('hiragana' if script == 'hira' else 'katakana')}"))

    def kanji(self, character):
        body = lead("Кандзи", "Значения, чтения и порядок черт.", search_form("/kanji", character, "学"))
        if character:
            if len(character) != 1 or not ("一" <= character <= "龯"):
                raise ValueError("Введите один иероглиф")
            info = kanji_info(character)
            on = ", ".join(info.get("on_readings", [])); kun = ", ".join(info.get("kun_readings", []))
            path = save_svg(character, self.store.path.parent / f"{character}.svg")
            try:
                strokes = kanji_strokes(character)
                guide = f'<div class="draw-wrap"><div class="draw-guide">{strokes}</div></div>'
                count = strokes.count("<path")
            except ApiError:
                guide, count = "", "—"
            body += f"""<div class="result" style="text-align:center"><div class="jp" style="font-size:56px">{character}{speak_btn(character)}</div>
<div class="roma">{esc(reading_romaji(on + ' ' + kun))} {trans_buttons(character)}</div>
<p>{esc(', '.join(info.get('meanings', [])))}</p>
<p class="muted">Он: {esc(on)} · Кун: {esc(kun)} · JLPT: {esc(info.get('jlpt', '—'))} · черт: {count}</p>
{guide}<p><a class="btn ghost sm" href="/draw?q={esc(character)}">Потренироваться в письме</a></p>
<p class="muted">SVG сохранён: {esc(path)}</p></div>"""
        self.send(page("Кандзи", body, "/kanji"))

    def draw(self, character):
        chips = ""
        for group, chars in (("хирагана", DRAW_SAMPLES[:10]), ("катакана", DRAW_SAMPLES[10:20]), ("кандзи", DRAW_SAMPLES[20:])):
            items = "".join(f'<a href="/draw?q={c}"{" class=active" if c == character else ""}>{c}</a>' for c in chars)
            chips += f'<div class="chips"><span class="tag">{group}</span>{items}</div>'
        body = lead("Письмо", "Обведите знак, сравните с образцом и получите процент схожести.",
                    search_form("/draw", character, "学 / あ / ア"))
        body += chips
        if character:
            if len(character) != 1 or not ("一" <= character <= "龯" or
                                           "\u3041" <= character <= "\u3096" or
                                           "\u30a1" <= character <= "\u30fa"):
                raise ValueError("Введите один кандзи, кану или катакану")
            strokes = kanji_strokes(character)
            link_info = (f'<a href="/kanji?q={esc(character)}"><button class="btn ghost sm">О знаке</button></a>'
                         if "一" <= character <= "龯" else "")
            body += f"""<div class="draw-wrap"><div class="draw-guide">{strokes}</div>
<canvas id="user-canvas"></canvas><canvas id="diff-canvas" style="display:none"></canvas></div>
<div class="actions"><button class="btn sm" id="draw-check">{icon('check')} Проверить</button>
<button class="btn ghost sm" onclick="animateStrokes()">Порядок черт</button>
<button class="btn ghost sm" onclick="toggleCompare()">Сравнить</button>
<button class="btn ghost sm" onclick="toggleDiff()">Разница</button>
<button class="btn ghost sm" id="draw-clear">Очистить</button>
<button class="btn ghost sm" id="draw-toggle">Образец</button>{link_info}</div>
<p class="muted" id="stroke-status" style="text-align:center"></p>
<div class="draw-score" id="draw-result"></div>
<p class="muted" style="text-align:center">Черт: {strokes.count('<path')} · было нарисовано: {len([c for c in character if c])} символ · KanjiVG</p>"""
        self.send(page("Письмо", body, "/draw"))

    def exam_page(self, questions: list[dict] | None = None):
        if not questions:
            levels = "".join(f'<option value="{lv}">{lv}</option>' for lv in ["MIXED", *exam_engine.LEVELS])
            body = lead("Экзамен JLPT", "Демо-тест N5–N1: 20 вопросов, таймер, оценка и разбор слабых мест.")
            body += (f'<div class="panel" style="max-width:520px;margin:auto"><form method="post" action="/exam/start">'
                     f'<p><select name="level">{levels}</select></p>'
                     f'<p><input name="count" type="number" min="5" max="40" value="20"></p>'
                     f'<p class="muted">Вопросы перемешаны по уровням и навыкам. Время: 1 минута на 2 вопроса.</p>'
                     f'<p><button class="btn">{icon("quiz")} Начать экзамен</button></p></form></div>')
            return self.send(page("Экзамен", body, "/exam"))
        seconds = max(len(questions) * 30, 60)
        embedded = html.escape(json.dumps(questions, ensure_ascii=False), quote=True)
        body = lead("Экзамен JLPT", f"{len(questions)} вопросов · {seconds // 60} минут")
        body += f'<div class="exam-timer" id="exam-timer">{seconds // 60}:00</div>'
        body += (f'<form id="exam-form" method="post" action="/exam/submit" style="max-width:780px;margin:auto">'
                 f'<input type="hidden" name="questions" value="{embedded}">')
        for item in questions:
            opts = "".join(f'<label><input type="radio" name="q{item["number"]}" value="{esc(o)}"><span>{esc(o)}</span></label>'
                           for o in item["options"])
            speak = speak_btn(item["speak"]) if item["speak"] else ""
            body += (f'<div class="quiz-q"><span class="tag">{item["number"]} · {item["level"]} · '
                     f'{exam_engine.SKILLS[item["skill"]]}</span>{speak}'
                     f'<p style="font-size:17px;margin:6px 0 0">{esc(item["prompt"])}</p>'
                     f'<div class="opts">{opts}</div></div>')
        body += '<p style="text-align:center"><button class="btn">Завершить и увидеть результат</button></p></form>'
        body += f'<script>startExamTimer({seconds})</script>'
        self.send(page("Экзамен", body, "/exam"))

    def exam_result(self, result: dict):
        body = lead("Результат экзамена", f"Оценка {result['grade']} · ориентировочный уровень {result['estimate']}")
        body += (f'<div class="panel" style="max-width:780px;margin:0 auto"><div style="text-align:center">'
                 f'<div style="font:52px Georgia,serif;color:var(--accent)">{result["percent"]}%</div>'
                 f'<p class="muted">{result["correct"]} из {result["total"]}</p></div>'
                 f'<div class="progress"><i style="width:{result["percent"]}%"></i></div>')
        body += '<h3>По навыкам</h3><div class="meta">'
        for skill, pct in result["accuracy"].items():
            body += f'<div><b>{exam_engine.SKILLS[skill]}</b>{pct}%</div>'
        body += '</div><h3>По уровням</h3><div class="meta">'
        for level, pct in result["levels"].items():
            body += f'<div><b>{level}</b>{str(pct) + "%" if pct is not None else "—"}</div>'
        body += '</div>'
        body += ('<h3>Сильные стороны</h3><p>' +
                 ", ".join(exam_engine.SKILLS[s] for s, _ in result["strongest"]) + '</p>')
        body += ('<h3>Слабые стороны</h3><p>' +
                 ", ".join(exam_engine.SKILLS[s] for s, _ in result["weakest"]) + '</p>')
        body += '<h3>Что подучить</h3><ul>' + "".join(f'<li>{esc(t)}</li>' for t in result["recommendations"]) + '</ul>'
        body += '<p><a class="btn ghost" href="/learn">Перейти к урокам</a> <a class="btn ghost" href="/cards">Карточки</a></p></div>'
        body += '<h2 class="section">Разбор ответов</h2>'
        for item in result["details"]:
            speak = speak_btn(item["speak"]) if item["speak"] else ""
            body += (f'<div class="result"><span class="tag">{item["number"]} · {item["level"]} · '
                     f'{"верно" if item["ok"] else "ошибка"}</span><p>{esc(item["prompt"])} {speak}</p>'
                     f'<p>Ваш ответ: <b>{esc(item["chosen"] or "—")}</b> · Верно: <b>{esc(item["answer"])}</b>'
                     f'{speak_btn(item["answer"])}</p><p class="muted">{esc(item["explain"])}</p></div>')
        self.send(page("Результат экзамена", body +
                       f'<script>saveExamResult({result["percent"]},\'{result["grade"]}\',\'{result["estimate"]}\')</script>',
                       "/exam"))

    def quiz_page(self, q):
        kind = q.get("type", ["mixed"])[0]
        if kind not in quiz_engine.TYPES:
            kind = "mixed"
        mode = q.get("mode", ["choice"])[0]
        if mode not in {"choice", "recall"}:
            mode = "choice"
        try:
            count = min(max(int(q.get("count", ["10"])[0]), 1), 30)
        except ValueError:
            count = 10
        seed_raw = q.get("seed", [""])[0]
        seed = int(seed_raw) if seed_raw.isdigit() else random.randrange(10**9)
        types = "".join(f'<option value="{t}"{" selected" if t == kind else ""}>{t}</option>' for t in quiz_engine.TYPES)
        modes = "".join(f'<option value="{m}"{" selected" if m == mode else ""}>{label}</option>'
                        for m, label in (("choice", "выбор ответа"), ("recall", "ввод ответа")))
        form = (f'<form class="search" action="/quiz"><select name="type">{types}</select>'
                f'<select name="mode">{modes}</select><input name="count" type="number" min="1" max="30" '
                f'value="{count}" style="max-width:80px"><button class="btn sm">Новый тест</button></form>')
        body = lead("Тесты", "Кана, слова, частицы, грамматика, кандзи, фонетика, предложения и аудио.", form)
        questions = quiz_engine.generate(kind, count, seed, mode=mode)
        body += quiz_html(questions)
        body += (f'<div class="actions"><button class="btn ghost" onclick="showQuizResult()">'
                 f'{icon("chart")} Результат</button><a class="btn ghost" href="/quiz?type={kind}&mode={mode}&count={count}&seed={seed}">'
                 f'{icon("refresh")} Повторить</a></div><div style="max-width:780px;margin:20px auto" id="quiz-summary"></div>')
        self.send(page("Тесты", body, "/quiz"))

    # --- OCR ------------------------------------------------------------------

    def ocr_page(self, error=""):
        body = lead("Распознавание текста", "Загрузите изображения — OCR найдёт японский текст, переведёт и разберёт слова.")
        body += (f'<form class="search" action="/ocr" method="post" enctype="multipart/form-data">'
                 f'<input type="file" name="image" accept="image/*" multiple required>'
                 f'<select name="lang"><option value="jpn">японский</option>'
                 f'<option value="jpn+eng">японский + английский</option><option value="eng">английский</option></select>'
                 f'<button class="btn sm">{icon("ocr")} Распознать</button></form>')
        body += ('<div class="ocr-drop" id="ocr-drop" onclick="document.querySelector(\'input[type=file]\').click()" '
                 'style="margin-top:18px">Перетащите сюда изображения или нажмите для выбора</div>')
        body += ('<p class="muted" style="text-align:center">Или укажите URL изображения: '
                 '<form class="search" action="/ocr" method="post"><input name="url" placeholder="https://…">'
                 '<button class="btn ghost sm">Загрузить</button></form></p>')
        if error:
            body += f'<p style="text-align:center;color:var(--accent)">{esc(error)}</p>'
        self.send(page("OCR", body, "/ocr", ocr=True))

    def ocr_post(self, body: bytes):
        content_type = self.headers.get("Content-Type", "")
        images: list[str] = []
        lang = "jpn"
        if "multipart/form-data" in content_type:
            boundary = content_type.split("boundary=", 1)[-1].strip().strip('"').encode()
            for part in body.split(b"--" + boundary):
                if b"\r\n\r\n" not in part:
                    continue
                head, content = part.split(b"\r\n\r\n", 1)
                content = content.rstrip(b"\r\n")
                if b'name="lang"' in head:
                    lang = content.decode("utf-8", "replace").strip() or "jpn"
                if b'name="image"' not in head or not content:
                    continue
                mime = "image/png" if content[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
                images.append("data:" + mime + ";base64," + base64.b64encode(content).decode())
        else:
            data = parse_qs(body.decode("utf-8", "replace"))
            url = data.get("url", [""])[0]
            if url and not is_allowed_image_url(url):
                return self.ocr_page("Разрешены AniList, MangaDex и публичные CDN.")
            if url:
                images.append(url)
        if not images:
            return self.ocr_page("Выберите изображение или укажите URL.")
        cards = ""
        for i, src in enumerate(images, 1):
            cards += f"""<div class="panel" style="margin:16px 0"><img id="ocr-image-{i}" class="ocr-preview" src="{esc(src)}" alt="">
<div class="actions" style="justify-content:flex-start"><button class="btn sm" onclick="runOCR('{esc(lang)}',{i})">{icon('ocr')} Распознать</button></div>
<div id="ocr-result-{i}"></div><form method="post" action="/learn-text" style="margin-top:10px">
<input type="hidden" name="text" id="ocr-vocab-{i}"><button class="btn ghost sm">{icon('plus')} Разобрать слова</button></form></div>"""
        body = lead("Распознавание текста", "Текст → перевод, ромадзи и слова для карточек.") + \
            f'<div id="ocr-gallery">{cards}</div><p class="muted" style="text-align:center">Модель загружается с CDN при первом запуске.</p>'
        self.send(page("OCR", body, "/ocr", ocr=True))

    def image(self, url):
        if not is_allowed_image_url(url):
            raise ValueError("URL изображения не разрешён")
        self.send(cached_image(url), 200, "image/jpeg",
                  {"Cache-Control": "public, max-age=604800"})

    # --- media ----------------------------------------------------------------

    def media(self, kind, q):
        query = q.get("q", [""])[0]
        genre = q.get("genre", [""])[0] or None
        year = q.get("year", [""])[0] or None
        status = q.get("status", [""])[0] or None
        sort = q.get("sort", [""])[0] or None
        title = "Аниме" if kind == "anime" else "Манга"
        genre_opts = '<option value="">любой жанр</option>' + "".join(
            f'<option value="{g}"{" selected" if g == genre else ""}>{g}</option>' for g in GENRES)
        status_opts = '<option value="">любой статус</option>' + "".join(
            f'<option value="{s}"{" selected" if s == status else ""}>{s}</option>'
            for s in ("FINISHED", "RELEASING", "NOT_YET_RELEASED"))
        sort_opts = '<option value="">по релевантности</option>' + "".join(
            f'<option value="{s}"{" selected" if s == sort else ""}>{label}</option>'
            for s, label in (("SCORE_DESC", "по оценке"), ("POPULARITY_DESC", "по популярности"),
                             ("START_DATE_DESC", "по дате")))
        form = (f'<form class="search" action="/{kind}"><input name="q" value="{esc(query)}" placeholder="название">'
                f'<select name="genre">{genre_opts}</select><select name="year">'
                f'<option value="">любой год</option>' + "".join(
                    f'<option value="{y}"{" selected" if str(y) == year else ""}>{y}</option>'
                    for y in range(2026, 1989, -1)) + f'</select><select name="status">{status_opts}</select>'
                f'<select name="sort">{sort_opts}</select><button class="btn sm">{icon("search")} Найти</button></form>')
        body = lead(title, "AniList → Tenrai → Jikan с фильтрами и автопереключением.", form)
        if any((query, genre, year, status)):
            body += '<div class="chips">' + "".join(
                f'<span class="tag">фильтр: {esc(v)}</span>' for v in (query, genre, year, status) if v) + '</div>'
        if query or genre or year or status:
            rows = search_media(query or " ", kind, 9, genre, int(year) if year else None, status, sort)
            for row in rows:
                img = f'<img class="media-img" src="{esc(row["image"])}" alt="" loading="lazy">' if row.get("image") else ""
                detail = (f'<a class="btn ghost sm" href="/title?kind={kind}&id={row["anilist_id"]}">'
                          f'{icon("info")} Подробнее</a>' if row.get("anilist_id") else "")
                body += f"""<div class="result">{img}<h3>{esc(row.get('title', '—'))} {trans_buttons(row.get('title_japanese') or row.get('title', ''))}</h3>
<p class="muted">{esc(row.get('title_japanese') or '')}{speak_btn(row.get('title_japanese')) if row.get('title_japanese') else ''}</p>
<p>{esc(row.get('type') or '—')} · {esc(row.get('status') or '—')} · {icon('star',13)} {row.get('score') or '—'} · {row.get('year') or '—'}</p>
<p class="muted">{esc(', '.join(g['name'] for g in row.get('genres', [])))}</p>
<p>{esc((row.get('synopsis') or '')[:320])}</p><div class="actions" style="justify-content:flex-start">{detail}{link(row.get('url', '#'), 'Каталог')}</div></div>"""
            if not rows:
                body += '<p class="muted" style="text-align:center">Ничего не найдено.</p>'
        self.send(page(title, body, f"/{kind}"))

    def title_detail(self, kind, media_id):
        if kind not in {"anime", "manga"} or not media_id.isdigit():
            raise ValueError("Некорректное произведение")
        row = anilist_detail(int(media_id), kind)
        img = f'<img class="detail-cover" src="{esc(row["image"])}" alt="">' if row.get("image") else ""
        count = row.get("episodes") if kind == "anime" else row.get("chapters")
        unit = "серий" if kind == "anime" else "глав"
        meta = f"""<div class="meta"><div><b>Оценка</b>{row.get('score') or '—'}</div>
<div><b>Средняя</b>{row.get('mean_score') or '—'}</div><div><b>Формат</b>{esc(row.get('type') or '—')}</div>
<div><b>Статус</b>{esc(row.get('status') or '—')}</div><div><b>{unit}</b>{count or '—'}</div>
<div><b>Год</b>{row.get('year') or '—'}</div><div><b>Популярность</b>{row.get('popularity') or '—'}</div>
<div><b>Студии</b>{esc(', '.join(row.get('studios', [])) or '—')}</div></div>"""
        official = "".join(f'<a class="btn ghost sm" href="{esc(l["url"])}" target="_blank" rel="noreferrer">'
                           f'{esc(l["site"])} {icon("external",12)}</a>'
                           for l in row.get("links", []) if l.get("url"))
        trailer = (f'<iframe class="trailer" src="{esc(row["trailer"])}" allowfullscreen></iframe>'
                   if row.get("trailer") else "")
        relations = "".join(f'<a href="/title?kind={kind}&id={r["id"]}">{esc(r["title"])}</a> · '
                            for r in row.get("relations", []) if r.get("id")) or "—"
        actions = (f'<a class="btn sm" href="/vocab?kind={kind}&id={media_id}">{icon("book")} Учить слова</a> '
                   + (f'<a class="btn ghost sm" href="/reader?q={esc(row["title"])}">{icon("reader")} Читать</a> '
                      if kind == "manga" else "")
                   + (f'<a class="btn ghost sm" href="/download?url={esc(row["image"])}&name=cover.jpg">'
                      f'{icon("download")} Обложку</a>' if row.get("image") else "")
                   + link(row.get("url", "#"), "AniList")
                   + f'<button class="btn ghost sm" onclick="toggleFav(\'/title?kind={kind}&id={media_id}\',\'{esc(row["title"])}\')">'
                     f'{icon("star")} В избранное</button><span id="fav-status" class="muted"></span>')
        body = f"""<div class="result" style="border:0">{img}<span class="tag">{kind}</span>
<h2 style="font:34px Georgia,serif;margin:4px 0">{esc(row['title'])}</h2>
<p class="muted">{esc(row['title_japanese'])}{speak_btn(row['title_japanese']) if row['title_japanese'] else ''}
{trans_buttons(row.get('title_japanese') or row['title'])}</p>
<p class="muted">{esc(', '.join(g['name'] for g in row.get('genres', [])))}</p>{meta}
<div class="actions" style="justify-content:flex-start">{actions}</div>{trailer}
<h3>Описание</h3><p>{esc(row.get('synopsis') or '—')}</p>
<h3>Где смотреть</h3><div class="actions" style="justify-content:flex-start">{official or 'Ссылки отсутствуют'}</div>
<h3>Связанные</h3><p>{relations}</p></div>"""
        self.send(page(row["title"], body, f"/{kind}"))

    def random_word_page(self, q):
        seed = q.get("seed", [""])[0]
        rng = random.Random(int(seed)) if seed.isdigit() else random.Random()
        jp, reading, ru = rng.choice(quiz_engine.VOCAB)
        body = lead("Случайное слово", "Новое слово каждый раз — с произношением, переводом и карточкой.")
        body += (f'<div class="panel" style="max-width:640px;margin:auto;text-align:center">'
                 f'<div class="jp" style="font-size:52px">{jp}{speak_btn(jp, big=True)}</div>'
                 f'<div class="roma">{esc(reading_romaji(reading))}</div>'
                 f'<p class="muted">{esc(reading)}</p><h3>{esc(ru)}</h3>'
                 f'<div class="actions"><button class="btn ghost" onclick="speakSlow(this.dataset.t)" data-t="{esc(jp)}">медленно</button>'
                 f'{trans_buttons(jp)}</div>'
                 f'<form method="post" action="/card" style="margin-top:16px">'
                 f'<input type="hidden" name="word" value="{esc(jp)}"><input type="hidden" name="reading" value="{esc(reading)}">'
                 f'<input type="hidden" name="meaning" value="{esc(ru)}">'
                 f'<button class="btn">{icon("plus")} В карточки</button></form>'
                 f'<p style="margin-top:16px"><a class="btn ghost" href="/random">Ещё слово</a></p></div>')
        self.send(page("Случайное слово", body, "/random"))

    def builder_page(self, q):
        from .course import all_lessons
        items = [l for l in all_lessons() if l.get("word_order")]
        try:
            index = int(q.get("n", ["0"])[0]) % len(items)
        except ValueError:
            index = 0
        item = items[index]
        order = item["word_order"]
        tiles = list(order["tokens"])
        random.Random(index).shuffle(tiles)
        body = lead("Конструктор предложений", f"Соберите фразу из слов урока {item['id']}.")
        body += (f'<div class="builder" data-answer="{esc(order["answer"])}" style="max-width:760px;margin:auto">'
                 f'<div class="builder-tiles">' + "".join(
                     f'<button type="button" data-word="{esc(t)}" onclick="buildWord(this)">{esc(t)}</button>'
                     for t in tiles) + '</div><div class="builder-target"></div>'
                 f'<div class="actions"><button class="btn sm" onclick="checkBuilder(this)">Проверить</button>'
                 f'<button class="btn ghost sm" onclick="resetBuilder(this)">Сбросить</button>'
                 f'<button class="btn ghost sm" onclick="speak(this.dataset.t)" data-t="{esc(order["answer"])}">Озвучить</button></div>'
                 f'<p class="builder-result"></p></div>'
                 f'<p style="text-align:center"><a class="btn ghost" href="/builder?n={index+1}">Следующее предложение</a></p>')
        self.send(page("Конструктор", body, "/builder"))

    def shadowing_page(self):
        body = lead("Аудирование и шадоуинг", "Слушайте фразы в обычном и медленном темпе, повторяйте вслух.")
        for jp, reading, ru, _wrong in quiz_engine.SENTENCES:
            body += (f'<div class="panel" style="max-width:760px;margin:0 auto 12px">'
                     f'<div class="jp" style="font-size:20px">{esc(jp)}</div>'
                     f'<div class="roma">{esc(reading)}</div><p>{esc(ru)} {trans_buttons(jp)}</p>'
                     f'<div class="actions" style="justify-content:flex-start">'
                     f'<button class="btn ghost sm" onclick="speak(this.dataset.t)" data-t="{esc(jp)}">обычно</button>'
                     f'<button class="btn ghost sm" onclick="speakSlow(this.dataset.t)" data-t="{esc(jp)}">медленно</button>'
                     f'{speak_btn(jp)}</div></div>')
        self.send(page("Аудирование", body, "/shadowing"))

    def conversation_page(self, q):
        sid = q.get("scenario", [""])[0]
        scenario = convo_engine.get_scenario(sid) or convo_engine.SCENARIOS[0]
        cards = "".join(f'<a class="card" href="/conversation?scenario={s["id"]}">'
                        f'<span class="tag">{len(s["turns"])} реплики</span><h3>{s["title"]}</h3>'
                        f'<p>{esc(s["situation"])}</p></a>' for s in convo_engine.SCENARIOS)
        body = lead("Практика общения", scenario["situation"])
        body += (f'<div class="chips">' + "".join(
            f'<a class="{"active" if s["id"] == scenario["id"] else ""}" '
            f'href="/conversation?scenario={s["id"]}">{s["title"]}</a>' for s in convo_engine.SCENARIOS) + '</div>')
        body += f'<form method="post" action="/conversation/check" style="max-width:760px;margin:auto">'
        body += f'<input type="hidden" name="scenario" value="{scenario["id"]}">'
        for i, turn in enumerate(scenario["turns"]):
            body += (f'<div class="quiz-q"><span class="tag">реплика {i+1}</span>'
                     f'<p style="font-size:18px">{esc(turn["jp"])} {speak_btn(turn["jp"])}</p>'
                     f'<p class="muted">{esc(turn["ru"])} · подсказка: {esc(turn["hint"])}</p>'
                     + "".join(f'<label><input type="radio" name="a{i}" value="{esc(o)}"><span>{esc(o)}</span></label>'
                               for o in turn["options"]) + '</div>')
        body += '<p style="text-align:center"><button class="btn">Проверить диалог</button></p></form>'
        body += f'<h2 class="section">Все сценарии</h2><div class="grid">{cards}</div>'
        self.send(page("Общение", body, "/conversation"))

    def conversation_result(self, scenario, result):
        body = lead("Результат диалога", f"{scenario['title']} · {result['correct']}/{result['total']} ({result['percent']}%)")
        body += '<div class="progress" style="width:400px"><i style="width:' + str(result["percent"]) + '%"></i></div>'
        for d in result["details"]:
            body += (f'<div class="result"><span class="tag">{"верно" if d["ok"] else "ошибка"}</span>'
                     f'<p style="font-size:18px">{esc(d["jp"])} {speak_btn(d["jp"])}</p>'
                     f'<p>Ваш ответ: <b>{esc(d["chosen"] or "—")}</b> · Верно: <b>{esc(d["answer"])}</b> '
                     f'{speak_btn(d["answer"])}</p><p class="muted">{esc(d["hint"])}</p></div>')
        body += f'<p style="text-align:center"><a class="btn" href="/conversation?scenario={scenario["id"]}">Ещё раз</a></p>'
        self.send(page("Результат диалога", body, "/conversation"))

    def flashcards_page(self):
        due = self.store.due()
        rows = ""
        for c in due:
            rows += (f'<div class="result"><div class="jp" style="font-size:26px">{esc(c["word"])}{speak_btn(c["word"])}</div>'
                     f'<details><summary class="muted" style="cursor:pointer">Ответ</summary>'
                     f'<div class="roma">{esc(c.get("romaji") or reading_romaji(c.get("reading", "")))}</div>'
                     f'<p>{esc(c.get("meaning", ""))}</p></details>'
                     f'<form method="post" action="/review"><input type="hidden" name="word" value="{esc(c["word"])}">'
                     f'<button class="btn sm" name="quality" value="5">Знаю</button> '
                     f'<button class="btn ghost sm" name="quality" value="2">Повторить</button></form></div>')
        body = lead("Карточки+", f"Быстрый тренажёр: {len(due)} карточек на сегодня.")
        self.send(page("Карточки+", body + (rows or '<p class="muted">На сегодня всё.</p>'), "/flashcards"))

    def favorites_page(self):
        body = lead("Избранное", "Сохранённые произведения, закладки манги и история экзаменов.")
        body += ('<div class="bookmarks"><h2 class="section">Произведения</h2><div id="favs-list"></div></div>'
                 '<div class="bookmarks"><h2 class="section">Закладки манги</h2><div id="bookmarks-list"></div></div>'
                 '<div class="bookmarks"><h2 class="section">Экзамены</h2><div id="exam-history"></div></div>')
        self.send(page("Избранное", body, "/favorites"))

    def books(self, q):
        query = q.get("q", [""])[0] or "日本語"
        rows = search_books(query, 9)
        body = lead("Японские книги", "Поиск Open Library и чтение доступных сканов через Internet Archive.",
                    search_form("/books", query, "название · こころ / 日本"))
        if not rows:
            body += '<p class="muted" style="text-align:center">Ничего не найдено.</p>'
        for row in rows:
            cover = (f'<img class="media-img" src="https://covers.openlibrary.org/b/id/{row["cover"]}-M.jpg" alt="">'
                     if row.get("cover") else "")
            read = (f'<a class="btn sm" href="/book/read?ia={esc(row["ia"])}&title={esc(row["title"])}">'
                    f'{icon("reader")} Читать</a>' if row.get("ia") else "")
            body += (f'<div class="result">{cover}<h3>{esc(row["title"])}</h3>'
                     f'<p class="muted">{esc(row["author"])} · {row.get("year") or "—"}</p>'
                     f'<p class="muted">{esc(", ".join(row.get("language", [])))} · {esc(row.get("access", ""))}</p>'
                     f'<div class="actions" style="justify-content:flex-start">{read}'
                     f'{link("https://openlibrary.org" + row["key"], "Open Library") if row.get("key") else ""}</div></div>')
        self.send(page("Книги", body, "/books"))

    def book_read(self, q):
        ia = q.get("ia", [""])[0]
        title = q.get("title", ["Книга"])[0]
        if not ia or not re.fullmatch(r"[A-Za-z0-9_\-]+", ia):
            raise ValueError("Некорректный идентификатор книги")
        body = lead(title, "Онлайн-читалка Internet Archive. Управление страницами — внутри просмотрщика.")
        body += (f'<div class="actions"><button class="btn sm" onclick="toggleBookFullscreen()">{icon("external")} На весь экран</button>'
                 f'<a href="/books?q={esc(title)}" class="btn ghost sm">{icon("left")} К поиску</a></div>'
                 f'<div class="book-frame-wrap"><iframe class="book-frame" src="https://archive.org/embed/{esc(ia)}?ui=full" '
                 f'allowfullscreen loading="lazy"></iframe></div>'
                 f'<p class="muted" style="text-align:center">{link("https://archive.org/details/" + ia, "Открыть на archive.org")}</p>')
        self.send(page(title, body, "/books"))

    def reader_search(self, q):
        query = q.get("q", [""])[0]
        year = q.get("year", [""])[0] or None
        status = q.get("status", [""])[0] or None
        form = (f'<form class="search" action="/reader"><input name="q" value="{esc(query)}" placeholder="название">'
                f'<select name="year"><option value="">любой год</option>' + "".join(
                    f'<option value="{y}"{" selected" if str(y) == year else ""}>{y}</option>'
                    for y in range(2026, 1999, -1)) + '</select><select name="status">'
                '<option value="">любой статус</option>' + "".join(
                    f'<option value="{s}"{" selected" if s == status else ""}>{s}</option>'
                    for s in ("ONGOING", "COMPLETED", "HIATUS")) + '</select>'
                f'<button class="btn sm">{icon("search")} Найти</button></form>')
        body = lead("Читалка манги", "MangaDex: оригинал и переводы, закладки, OCR страниц.", form)
        body += f'<div class="bookmarks"><h2 class="section">Мои закладки</h2><div id="bookmarks-list"></div></div>'
        rows = mangadex_search(query, 8, int(year) if year else None, status)
        if not query:
            body += '<h2 class="section">Популярное</h2>'
        for row in rows:
            body += f"""<div class="result"><h3>{esc(row['title'])} {trans_buttons(row['title_japanese'] or row['title'])}</h3>
<p class="muted">{esc(row['title_japanese'])} · {esc(row['status'] or '—')} · {row['year'] or '—'}</p>
<p class="muted">{esc(', '.join(row.get('genres', [])))}</p><p>{esc((row['description'] or '')[:220])}</p>
<p><a class="btn ghost sm" href="/read?id={row['id']}">{icon('reader')} Главы</a></p></div>"""
        self.send(page("Читалка", body, "/reader"))

    def read(self, q):
        manga_id = q.get("id", [""])[0]
        chapter_id = q.get("chapter", [""])[0]
        if not manga_id:
            return self.redirect("/reader")
        lang = q.get("lang", ["en"])[0]
        if not chapter_id:
            chapters = mangadex_chapters(manga_id, lang)
            langs = "".join(f'<a class="{"active" if l == lang else ""}" href="/read?id={esc(manga_id)}&lang={l}">{label}</a>'
                            for l, label in (("ja", "оригинал"), ("en", "перевод EN"), ("ru", "перевод RU")))
            body = lead("Главы", "Выберите язык и главу.", search_form("/reader", "", "Найти другую мангу"))
            body += f'<div class="tabs">{langs}</div>'
            if not chapters:
                body += '<p class="muted" style="text-align:center">Нет глав на этом языке.</p>'
            for c in chapters[:120]:
                body += f"""<div class="result"><h3>Глава {esc(c['chapter'])}{(' · ' + esc(c['title'])) if c['title'] else ''}</h3>
<p class="muted">{c['pages'] or '?'} страниц · том {esc(c['volume'] or '—')}</p>
<p><a class="btn ghost sm" href="/read?id={esc(manga_id)}&chapter={esc(c['id'])}&lang={lang}">{icon('reader')} Читать</a></p></div>"""
            return self.send(page("Главы", body, "/reader"))
        pages = mangadex_pages(chapter_id)
        try:
            num = min(max(int(q.get("page", ["1"])[0]), 1), pages["count"])
        except ValueError:
            num = 1
        mode = q.get("mode", [""])[0]
        base = f"/read?id={esc(manga_id)}&chapter={esc(chapter_id)}&lang={lang}"
        current = pages["urls"][num - 1]
        bookmark = {"manga": manga_id, "title": f"Манга {manga_id}", "chapter": chapter_id, "page": num}
        jump = (f'<form class="search" style="margin:0" action="/read"><input type="hidden" name="id" value="{esc(manga_id)}">'
                f'<input type="hidden" name="chapter" value="{esc(chapter_id)}"><input type="hidden" name="lang" value="{lang}">'
                f'<input name="page" type="number" min="1" max="{pages["count"]}" value="{num}" style="max-width:80px">'
                f'<button class="btn ghost sm">К странице</button></form>')
        top = (f'<div class="reader-top"><a id="page-prev" href="{base}&page={num-1}">'
               f'<button class="btn ghost sm">{icon("left")} Назад</button></a><span class="muted">{num} / {pages["count"]}</span>'
               f'<a id="page-next" href="{base}&page={num+1}"><button class="btn ghost sm">Вперёд {icon("right")}</button></a>'
               f'{jump}<button class="btn ghost sm" onclick="readerZoom(-120)">−</button>'
               f'<button class="btn ghost sm" onclick="readerZoom(120)">+</button>'
               f'<button class="btn ghost sm" onclick="readerToggle(\'invert\')">Ночь</button>'
               f'<button class="btn sm" onclick="saveBookmark()">{icon("bookmark")} Закладка</button>'
               f'<button class="btn ghost sm" onclick="toggleTheater()">{icon("reader")} Театр (F)</button>'
               f'<button class="btn ghost sm" onclick="toggleShortcuts()">Клавиши (?)</button>'
               f'<button class="btn ghost sm" onclick="toggleFullscreen()">{icon("external")} Полный экран</button>'
               f'<span id="bm-status" class="muted"></span></div>'
               f'<div class="reader-bar"><i style="width:{100*num//max(pages["count"],1)}%"></i></div>')
        if mode == "strip":
            imgs = "".join(f'<img src="/image?url={esc(u)}" loading="lazy" alt="страница {i}">' for i, u in enumerate(pages["urls"], 1))
            stage = f'<div class="reader-stage">{imgs}</div><p><a href="{base}">Постранично</a></p>'
        else:
            stage = (f'<div class="reader-stage"><img id="reader-image" src="/image?url={esc(current)}" '
                     f'data-ocr="/image?url={esc(current)}" alt="страница {num}"></div>'
                     f'<div class="actions"><a href="{base}&mode=strip" class="btn ghost sm">Лентой</a>'
                     f'<a href="/download?url={esc(current)}&name=page-{num}.jpg" class="btn ghost sm">{icon("download")} Скачать</a>'
                     f'<button class="btn sm" onclick="ocrPage()">{icon("ocr")} OCR страницы</button></div>')
        panel = f"""<div class="panel reader-tools"><span class="tag">OCR и перевод</span>
<p class="muted">Распознайте страницу или введите фразу — получите перевод, ромадзи и разбор слов.</p>
<div class="search"><input id="panel-text" placeholder="Фраза со страницы"><button class="btn sm" onclick="translatePanel()">Перевести</button></div>
<div id="panel-result" style="margin-top:10px"></div>
<form method="post" action="/learn-text" style="margin-top:10px"><input type="hidden" name="text" id="ocr-vocab-text">
<button class="btn ghost sm">{icon('plus')} Разобрать слова</button></form></div>"""
        preload = []
        if num > 1:
            preload.append(f"/image?url={quote(pages['urls'][num-2], safe='')}")
        if num < pages["count"]:
            preload.append(f"/image?url={quote(pages['urls'][num], safe='')}")
        preload_js = ("<script>[" + ",".join(f"'{esc(u)}'" for u in preload) +
                      "].forEach(u=>{const i=new Image();i.src=u;});</script>") if preload else ""
        body = (f'<span data-bookmark=\'{html.escape(json.dumps(bookmark), quote=True)}\'></span>'
                f'<div class="reader-shell">{top}{stage}{top}{panel}{preload_js}</div>')
        self.send(page("Чтение", body, "/reader", ocr=True,
                       focus=q.get("focus", [""])[0] == "1"))

    def learn_page(self, kind="", media_id="", text=""):
        source = ""
        if kind and media_id and media_id.isdigit():
            row = anilist_detail(int(media_id), kind)
            text = row["title_japanese"] or row["title"]
            source = f"{row['title']} ({text})"
        body = lead("Обучение по тексту", "Морфологический разбор Janome и значения из Jisho.")
        if source:
            body += f'<p style="text-align:center" class="muted">Источник: {esc(source)}</p>'
        if text:
            body += vocab_html(learn_vocab(text, 10))
        body += """<div class="panel" style="max-width:760px;margin:24px auto"><h3>Свой текст</h3>
<p class="muted">Вставьте японский текст: диалог, субтитры, описание манги.</p>
<form method="post" action="/learn-text"><textarea name="text" rows="4" style="width:100%" placeholder="日本語のテキスト"></textarea>
<p><button class="btn sm">Разобрать</button></p></form></div>"""
        self.send(page("Обучение", body, "/vocab"))

    def cards(self, q=None):
        q = q or {}
        rows = "".join(
            f'<div class="result"><span class="jp">{esc(c["word"])}</span>{speak_btn(c["word"])}'
            f'<span class="roma"> {esc(c.get("romaji") or reading_romaji(c.get("reading", "")))}</span>'
            f'{trans_buttons(c["word"])}<br><span class="muted">{esc(c.get("reading", ""))} · {esc(c.get("meaning", ""))}</span>'
            f'<div class="menu-row">{speak_btn(c.get("meaning") or c["word"])}{trans_buttons(c.get("meaning") or c["word"])}</div>'
            f'{word_menu(c["word"], c.get("reading", ""), c.get("meaning", ""))}</div>'
            for c in self.store.cards)
        saved = q.get("saved", [""])[0]
        tab = q.get("tab", ["manual"])[0]
        if tab not in {"manual", "generator", "check", "data"}:
            tab = "manual"
        notice = f'<p class="muted">Сохранено карточек: {esc(saved)}</p>' if saved else ""
        due = self.store.due()
        check = "".join(
            f'<div class="result"><div class="jp" style="font-size:26px">{esc(c["word"])}{speak_btn(c["word"])}</div>'
            f'<details><summary class="muted" style="cursor:pointer">Показать ответ</summary>'
            f'<div class="roma">{esc(c.get("romaji") or reading_romaji(c.get("reading", "")))}</div>'
            f'<p>{esc(c.get("reading", ""))} · {esc(c.get("meaning", ""))}</p></details>'
            f'<form method="post" action="/review"><input type="hidden" name="word" value="{esc(c["word"])}">'
            f'<button class="btn sm" name="quality" value="5">Знаю</button> '
            f'<button class="btn ghost sm" name="quality" value="2">Повторить</button></form></div>'
            for c in due) or '<p class="muted">На сегодня всё.</p>'
        body = lead("Карточки", "Создавайте, сохраняйте и проверяйте слова.")
        body += (f'<div class="tabs">'
                 + "".join(f'<button class="tab-view{" active" if t == tab else ""}" '
                           f'onclick="switchView(\'{t}\',this)">{label}</button>'
                           for t, label in (("manual", "Мои карточки"), ("generator", "Генератор"),
                                            ("check", "Проверка"), ("data", "Данные"))) + '</div>')
        body += f'<div class="view{" active" if tab == "manual" else ""}" id="view-manual">{notice}' + (rows or '<p class="muted">Пока пусто.</p>') + '</div>'
        body += f"""<div class="view{" active" if tab == "generator" else ""}" id="view-generator"><div class="panel" style="max-width:760px;margin:auto">
<h3>Новая карточка</h3><form method="post" action="/card">
<input type="hidden" name="tab" value="generator">
<input id="manual-word" name="word" placeholder="слово · 日本語" required>
<input id="manual-reading" name="reading" placeholder="чтение · にほんご">
<input id="manual-meaning" name="meaning" placeholder="перевод · language">
<p><button class="btn sm">{icon('plus')} Сохранить</button></p></form>
<h3>Сгенерировать из текста</h3>
<p class="muted">Вставьте японский текст — система выделит слова, чтения и значения. Отметьте нужные и сохраните.</p>
<form method="post" action="/generate-cards"><textarea name="text" rows="4" style="width:100%" placeholder="私は日本語を勉強しています。"></textarea>
<p><button class="btn sm">{icon('sparkle')} Сгенерировать</button></p></form></div></div>"""
        body += f'<div class="view{" active" if tab == "check" else ""}" id="view-check"><h2 class="section">К повторению: {len(due)}</h2>{check}</div>'
        body += (f'<div class="view{" active" if tab == "data" else ""}" id="view-data"><div class="panel" style="max-width:640px;margin:auto">'
                 f'<h3>Экспорт и восстановление</h3><p><a href="/export.csv">CSV</a> · '
                 f'<a href="/export.anki">Anki</a> · <a href="/export.json">JSON</a></p>'
                 f'<p class="muted">Всего карточек: {len(self.store.cards)} · серия: {self.store.streak()} дн.</p>'
                 f'<form method="post" action="/cards/import"><textarea name="data" rows="5" style="width:100%" '
                 f'placeholder="Вставьте JSON, экспортированный ранее"></textarea>'
                 f'<p><button class="btn sm">{icon("plus")} Импортировать</button></p></form></div></div>')
        self.send(page("Карточки", body, "/cards"))

    def generate_cards(self, text: str):
        rows = learn_vocab(text, 10)
        if not rows:
            return self.send(page("Генератор карточек", lead("Генератор карточек", "Слова не найдены.") +
                                  '<p style="text-align:center"><a href="/cards?tab=generator">Назад в генератор</a></p>', "/cards"))
        fields = ""
        for row in rows:
            payload = html.escape(json.dumps(row, ensure_ascii=False), quote=True)
            fields += (f'<div class="result"><label style="display:flex;gap:10px;align-items:flex-start">'
                       f'<input type="checkbox" name="cards" value="{payload}" checked>'
                       f'<span><b>{esc(row["word"])}</b> {speak_btn(row["word"])} '
                       f'<span class="roma">{esc(row["romaji"])}</span><br>'
                       f'<span class="muted">{esc(row["reading"])} · {esc(row["pos"])} · {esc(row["meaning"] or "—")}</span></span></label></div>')
        body = lead("Генератор карточек", "Отметьте слова и сохраните их в коллекцию.")
        body += (f'<form method="post" action="/cards/bulk" style="max-width:780px;margin:auto">{fields}'
                 f'<p style="text-align:center"><button class="btn">{icon("check")} Сохранить выбранные</button> '
                 f'<a class="btn ghost" href="/cards">Отмена</a></p></form>')
        self.send(page("Генератор", body, "/cards"))

    def words(self, q):
        query = q.get("q", [""])[0]
        rows = [(jp, reading, ru) for jp, reading, ru in quiz_engine.VOCAB
                if not query or query.lower() in jp.lower() or query.lower() in ru.lower()]
        body = lead("Слова N5", "Базовый словарь с меню действий для каждого слова.",
                    search_form("/words", query, "найти слово"))
        body += "".join(
            f'<div class="result"><h3>{esc(jp)} <span class="muted">{esc(reading)}</span>{speak_btn(jp)}</h3>'
            f'<div class="roma">{esc(reading_romaji(reading))} {trans_buttons(jp)}</div>'
            f'<p>{esc(ru)}</p>{word_menu(jp, reading, ru)}</div>' for jp, reading, ru in rows)
        self.send(page("Слова", body, "/words"))

    def study(self):
        due = self.store.due()
        body = lead("Повторение", f"{len(due)} карточек на сегодня.")
        if not due:
            body += '<p class="muted" style="text-align:center">На сегодня всё.</p>'
        for c in due:
            body += f"""<div class="result"><div class="jp" style="font-size:28px">{esc(c['word'])}{speak_btn(c['word'])}</div>
<details><summary class="muted" style="cursor:pointer">Показать ответ</summary>
<div class="roma">{esc(c.get('romaji') or reading_romaji(c.get('reading', '')))}</div>
<p>{esc(c.get('reading', ''))} · {esc(c.get('meaning', ''))} {trans_buttons(c['word'])}</p></details>
<form method="post" action="/review"><input type="hidden" name="word" value="{esc(c['word'])}">
<button class="btn sm" name="quality" value="5">Знаю</button>
<button class="btn ghost sm" name="quality" value="2">Повторить</button></form></div>"""
        self.send(page("Повторение", body, "/study"))

    def stats(self):
        cards = self.store.cards
        body = lead("Статистика", "Ваш прогресс.")
        body += f"""<div class="grid"><div class="card"><div class="ico">{icon('cards',24)}</div><h3>{len(cards)}</h3><p>карточек всего</p></div>
<div class="card"><div class="ico">{icon('refresh',24)}</div><h3>{len(self.store.due())}</h3><p>на сегодня</p></div>
<div class="card"><div class="ico">{icon('check',24)}</div><h3>{sum(c.get('box',0)>=3 for c in cards)}</h3><p>выучено</p></div>
<div class="card"><div class="ico">{icon('star',24)}</div><h3>{self.store.streak()}</h3><p>дней подряд</p></div></div>
<div class="panel" style="max-width:640px;margin:24px auto"><h3>Цель на день</h3>
<p class="muted">Сегодня повторено: {self.store.today_count()} из {self.store.goal}</p>
<div class="progress"><i style="width:{min(100,100*self.store.today_count()//self.store.goal)}%"></i></div>
<form method="post" action="/goal" class="search"><input name="goal" type="number" min="1" max="100" value="{self.store.goal}">
<button class="btn sm">Изменить цель</button></form></div>
<div class="panel" style="max-width:640px;margin:20px auto"><h3>История экзаменов</h3><div id="exam-history"></div></div>"""
        self.send(page("Статистика", body, "/stats"))

    def facts(self, query=""):
        categories = [("Культура Японии", "культура"), ("Японская кухня", "еда"),
                      ("История Японии", "история"), ("География Японии", "география"),
                      ("Японский язык", "язык")]
        chips = "".join(f'<a class="{"active" if query == q else ""}" href="/facts?q={q}">{label}</a>'
                        for q, label in categories)
        body = lead("Япония", "Факты и статьи из Wikipedia.", search_form("/facts", query, "чайная церемония"))
        body += f'<div class="chips">{chips}</div>'
        if query:
            for row in search_topics(query, "ru", 6):
                body += (f'<div class="result"><h3>{esc(row.get("title", ""))}</h3>'
                         f'<p>{esc(row.get("extract", ""))}</p>{link(row.get("fullurl", "#"), "Wikipedia")}</div>')
        self.send(page("Япония", body, "/facts"))

    def tts(self, q):
        text = q.get("q", [""])[0].strip()
        try:
            data = tts_audio(text)
        except ApiError as exc:
            return self.send(json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), 502, "application/json")
        self.send(data, 200, "audio/mpeg", {"Cache-Control": "public, max-age=86400"})

    def api_translate(self, q):
        text = q.get("q", [""])[0].strip()
        if not text:
            return self.send(json.dumps({"error": "Пустой запрос"}).encode(), 400, "application/json")
        try:
            source = detect_language(text)
            target = q.get("to", ["ru" if source == "ja" else "ja"])[0]
            result = translate(text, source, target)
            payload = {"result": result, "source": source, "target": target,
                       "romaji": phrase_romaji(result) if target == "ja" else ""}
            self.send(json.dumps(payload, ensure_ascii=False).encode(), 200, "application/json")
        except ApiError as exc:
            self.send(json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), 502, "application/json")

    def download(self, q):
        url = q.get("url", [""])[0]
        if not is_allowed_image_url(url):
            raise ValueError("Скачивание только с AniList, MangaDex и публичных CDN")
        data = fetch_bytes(url)
        name = "".join(c for c in q.get("name", ["download.jpg"])[0] if c.isalnum() or c in "-_.")[:80] or "download.jpg"
        self.send(data, 200, "image/jpeg", {"Content-Disposition": f'attachment; filename="{name}"'})


def serve(host: str = "127.0.0.1", port: int = 8765):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    LOGGER.info("Starting web server on http://%s:%s", host, port)
    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    LOGGER.info("Web server stopped")
