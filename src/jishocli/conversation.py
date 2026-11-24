"""Scenario-based conversation practice with Japanese replies and feedback."""

from __future__ import annotations

SCENARIOS = [
    {"id": "greet", "title": "Знакомство", "situation": "Вы впервые встречаете японского коллегу.",
     "turns": [
         {"jp": "はじめまして。よろしくお願いします。", "ru": "Приятно познакомиться.",
          "options": ["こんにちは。よろしくお願いします。", "さようなら。", "おやすみなさい。"],
          "hint": "Отвечайте приветствием и вежливой формулой знакомства."},
         {"jp": "お名前は何ですか。", "ru": "Как вас зовут?",
          "options": ["私は田中です。", "はい、ありがとう。", "今日は月曜日です。"],
          "hint": "Назовите имя с 私は … です."},
     ]},
    {"id": "shop", "title": "Покупки", "situation": "Вы в магазине и хотите купить чай.",
     "turns": [
         {"jp": "いらっしゃいませ。", "ru": "Добро пожаловать.",
          "options": ["お茶をください。", "すみません、トイレはどこですか。", "おやすみなさい。"],
          "hint": "Сразу вежливо попросите нужный товар."},
         {"jp": "これでよろしいですか。", "ru": "Это подойдёт?",
          "options": ["はい、お願いします。", "いいえ、行きません。", "明日です。"],
          "hint": "Согласие: はい、お願いします."},
     ]},
    {"id": "cafe", "title": "Кафе", "situation": "Официант предлагает меню.",
     "turns": [
         {"jp": "ご注文はお決まりですか。", "ru": "Вы уже выбрали заказ?",
          "options": ["コーヒーを一杯ください。", "私は学生です。", "寒いですね。"],
          "hint": "Заказ: [напиток] を [счётное слово] ください."},
         {"jp": "お持ち帰りですか。", "ru": "На вынос?",
          "options": ["はい、お願いします。", "いいえ、月曜日です。", "ありがとう。"],
          "hint": "Подтвердите вежливым はい、お願いします."},
     ]},
    {"id": "station", "title": "Станция", "situation": "Вы ищете выход к станции.",
     "turns": [
         {"jp": "すみません、駅はどこですか。", "ru": "Простите, где станция?",
          "options": ["まっすぐ行ってください。", "私は駅です。", "お茶がほしいです。"],
          "hint": "Подсказка дороги: まっすぐ + てください."},
         {"jp": "ありがとうございます。", "ru": "Спасибо.",
          "options": ["どういたしまして。", "すみません。", "失礼します。"],
          "hint": "В ответ на благодарность — どういたしまして."},
     ]},
    {"id": "phone", "title": "Телефон", "situation": "Вы звоните коллеге.",
     "turns": [
         {"jp": "もしもし、田中さんはいらっしゃいますか。", "ru": "Алло, можно Танаку?",
          "options": ["少々お待ちください。", "こんにちは。", "さようなら。"],
          "hint": "Просьба подождать: 少々お待ちください."},
         {"jp": "折り返し電話をください。", "ru": "Перезвоните, пожалуйста.",
          "options": ["はい、承知しました。", "いいえ、食べません。", "明日は雨です。"],
          "hint": "Вежливое подтверждение: 承知しました."},
     ]},
    {"id": "health", "title": "Самочувствие", "situation": "Коллега спрашивает, как вы себя чувствуете.",
     "turns": [
         {"jp": "元気ですか。", "ru": "Как дела / вы здоровы?",
          "options": ["少し疲れました。", "私は本です。", "駅まで行きます。"],
          "hint": "Расскажите о самочувствии: 少し疲れました."},
         {"jp": "頭が痛いです。", "ru": "У меня болит голова.",
          "options": ["ゆっくり休んでください。", "おめでとうございます。", "コーヒーがほしい。"],
          "hint": "Совет: [ глагол ] てください."},
     ]},
]


def get_scenario(scenario_id: str) -> dict | None:
    return next((s for s in SCENARIOS if s["id"] == scenario_id), None)


def evaluate(scenario: dict, chosen: list[str]) -> dict:
    correct = 0
    details = []
    for i, turn in enumerate(scenario["turns"]):
        answer = chosen[i] if i < len(chosen) else ""
        ok = answer == turn["options"][0]
        correct += int(ok)
        details.append({"jp": turn["jp"], "ru": turn["ru"], "options": turn["options"],
                        "answer": turn["options"][0], "chosen": answer, "ok": ok,
                        "hint": turn["hint"]})
    return {"correct": correct, "total": len(scenario["turns"]),
            "percent": round(100 * correct / max(len(scenario["turns"]), 1)), "details": details}
