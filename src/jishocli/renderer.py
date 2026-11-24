"""Dependency-free image export for kanji."""

from pathlib import Path


def save_svg(character: str, path: str | Path) -> Path:
    path = Path(path)
    escaped = character.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
<rect width="100%" height="100%" fill="white"/><text x="256" y="370" text-anchor="middle"
font-size="330" font-family="serif" fill="black">{escaped}</text></svg>\n'''
    path.write_text(svg, encoding="utf-8")
    return path
