"""Local, transparent study database and lightweight spaced repetition."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path


def default_path() -> Path:
    return Path.home() / ".jishocli" / "cards.json"


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {"cards": []}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, card: dict) -> bool:
        if any(c["word"] == card["word"] for c in self.data["cards"]):
            return False
        card = {"word": card["word"], "reading": card.get("reading", ""),
                "meaning": card.get("meaning", ""), "notes": card.get("notes", ""),
                "example": card.get("example", ""), "romaji": card.get("romaji", ""),
                "source": card.get("source", "manual"), "box": 0,
                "due": date.today().isoformat(), "reviews": 0, "created": date.today().isoformat()}
        self.data["cards"].append(card)
        self.save()
        return True

    def due(self) -> list[dict]:
        today = date.today().isoformat()
        return [c for c in self.data["cards"] if c.get("due", today) <= today]

    def review(self, card: dict, quality: int) -> None:
        quality = max(0, min(5, quality))
        if quality < 3:
            card["box"] = 0
            days = 1
        else:
            card["box"] = min(5, card.get("box", 0) + 1)
            days = (1, 2, 4, 8, 16, 30)[card["box"]]
        card["due"] = (date.today() + timedelta(days=days)).isoformat()
        card["reviews"] = card.get("reviews", 0) + 1
        history = self.data.setdefault("history", [])
        today = date.today().isoformat()
        if today not in history:
            history.append(today)
        daily = self.data.setdefault("daily", {})
        daily[today] = daily.get(today, 0) + 1
        self.save()

    def set_goal(self, value: int) -> None:
        self.data["goal"] = max(1, min(100, int(value)))
        self.save()

    @property
    def goal(self) -> int:
        return int(self.data.get("goal", 10))

    def today_count(self) -> int:
        return int(self.data.get("daily", {}).get(date.today().isoformat(), 0))

    def streak(self) -> int:
        days = set(self.data.get("history", []))
        if not days:
            return 0
        cursor = date.today()
        if cursor.isoformat() not in days:
            cursor -= timedelta(days=1)
        count = 0
        while cursor.isoformat() in days:
            count += 1
            cursor -= timedelta(days=1)
        return count

    def export_csv(self) -> str:
        import csv
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["word", "reading", "romaji", "meaning", "example", "box", "due", "reviews"])
        for c in self.cards:
            writer.writerow([c.get(k, "") for k in ("word", "reading", "romaji", "meaning", "example", "box", "due", "reviews")])
        return buf.getvalue()

    def export_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2)

    def import_json(self, text: str) -> int:
        data = json.loads(text)
        cards = data.get("cards") if isinstance(data, dict) else data
        if not isinstance(cards, list):
            raise ValueError("Ожидается список карточек")
        added = 0
        for card in cards:
            if not isinstance(card, dict) or not card.get("word"):
                continue
            if self.add(card):
                added += 1
        return added

    def export_anki(self) -> str:
        lines = ["#separator:tab", "#html:false",
                 "#columns:Front\tBack"]
        for c in self.cards:
            front = c["word"] + (f" ({c['reading']})" if c.get("reading") else "")
            back = c.get("meaning", "") + (f"\n{c['example']}" if c.get("example") else "")
            lines.append(front.replace("\t", " ") + "\t" + back.replace("\t", " ").replace("\n", "<br>"))
        return "\n".join(lines) + "\n"

    @property
    def cards(self) -> list[dict]:
        return self.data["cards"]
