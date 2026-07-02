"""
Консьерж заказов Даши — стандалон-симуляция полной петли.

  [клиент пишет в Instagram DM]  (симулируем текстом)
        -> AI разбирает свободный текст в бриф (Groq LLM; без ключа — регулярки)
        -> price_engine считает цену и загрузку (детерминированно)
        -> карточка Даше на аппрув
        -> Даша одобряет -> ИМИТАЦИЯ отправки ответа клиенту в Instagram

Настоящий AI бесплатно:
  1) Заведи бесплатный ключ на https://console.groq.com  (Sign up -> API Keys -> Create)
  2) export GROQ_API_KEY="gsk_..."
  3) python3 concierge_sim.py           # прогонит 3 сценария
     python3 concierge_sim.py "свой текст DM"   # разобрать своё сообщение

Без ключа скрипт всё равно работает — использует регулярки-заглушку и честно это пишет.
"""

import os
import sys
import json
import urllib.request
from datetime import date, datetime

from price_engine import Brief, quote_price, check_capacity, format_quote_lines
from telegram_bot import analyze_dm as regex_analyze  # запасной парсер без AI

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
BOOKED_DATES = [date(2026, 7, 14)]  # демо-загрузка (в проде — календарь Даши)

SYSTEM_PROMPT = (
    "Ты — ассистент пекарни кастомных тортов. Разбери сообщение клиента и верни ТОЛЬКО JSON "
    "без пояснений со схемой: "
    '{"message_type":"order|sensitive|smalltalk",'
    '"servings":int|null,"event_date":"YYYY-MM-DD"|null,"tiers":int,'
    '"decor":"simple|medium|complex","delivery":bool,"flavor":string|null,"theme":string|null}. '
    "message_type=sensitive для жалоб, конфликтов, тяжёлых тем (похороны, болезнь). "
    "decor=complex если фигурки/роспись/динозавр/золочение/лепка; medium если цвета/ягоды/надпись/тема; иначе simple. "
    "Текущий год 2026. Не выдумывай отсутствующие поля — ставь null."
)


def ai_analyze(text: str, today: date):
    """Возвращает (brief_dict, движок). Groq если есть ключ, иначе регулярки."""
    if not GROQ_KEY:
        return regex_analyze(text, today), "регулярки (нет GROQ_API_KEY)"

    body = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + GROQ_KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode())
        raw = resp["choices"][0]["message"]["content"]
        data = json.loads(raw)
    except Exception as e:
        # сеть/ключ/ответ подвели — не роняем демо, откатываемся на регулярки
        return regex_analyze(text, today), f"регулярки (Groq недоступен: {type(e).__name__})"

    # нормализуем к тому же виду, что и регулярки-парсер
    ev = data.get("event_date")
    ev_date = None
    if ev:
        try:
            ev_date = datetime.strptime(ev, "%Y-%m-%d").date()
        except ValueError:
            ev_date = None
    return {
        "message_type": data.get("message_type", "order"),
        "escalate_to_human": data.get("message_type") == "sensitive",
        "servings": data.get("servings"),
        "event_date": ev_date,
        "tiers": data.get("tiers") or 1,
        "decor": data.get("decor") or "simple",
        "delivery": bool(data.get("delivery")),
        "flavor": data.get("flavor"),
        "theme": data.get("theme"),
    }, f"Groq · {GROQ_MODEL}"


def build_card(a: dict, today: date) -> dict:
    """Карточка Даше + черновик клиенту. Тот же принцип, что в telegram_bot."""
    if a.get("message_type") == "sensitive":
        return {"kind": "sensitive",
                "card": "🙋 ТОЛЬКО ДЛЯ ТЕБЯ — не автоматизирую.\n"
                        "Чувствительное сообщение (жалоба/тяжёлая тема). Ответь лично.",
                "draft": None}

    if not a.get("servings") or not a.get("event_date"):
        need = []
        if not a.get("servings"): need.append("число персон")
        if not a.get("event_date"): need.append("дату")
        return {"kind": "clarify",
                "card": "🧐 Не хватает данных: " + ", ".join(need) +
                        ".\nЧерновик уточнения клиенту.",
                "draft": f"Обожаю такие заказы! Подскажи, пожалуйста, {' и '.join(need)}? 😊"}

    brief = Brief(servings=a["servings"], event_date=a["event_date"],
                  tiers=a.get("tiers", 1), decor=a.get("decor", "simple"),
                  delivery=a.get("delivery", False))
    q = quote_price(brief, today)
    cap = check_capacity(a["event_date"], BOOKED_DATES)

    if not cap["has_room"]:
        draft = ("Ой, спасибо, что подумали обо мне! 🙈 Но на эту неделю я уже вся расписана "
                 "и не хочу делать торт наспех. Могу в лист ожидания или к ближайшей свободной дате — как вам?")
        return {"kind": "decline",
                "card": f"⚠️ Неделя {cap['week']} — {cap['booked']}/{cap['capacity']} ПОЛНАЯ.\n"
                        f"Рекомендую отказ + вейтлист.\nЧерновик отказа готов.",
                "draft": draft}

    draft = (f"Обожаю такие заказы! 🎂 На {a['servings']} человек к {a['event_date']} сделаю — "
             f"выйдет {q['total']} ₽ (предоплата {q['deposit']} ₽ бронирует дату). Подтверждаем? 😊")
    tiers = brief.tiers
    max_sane = max(2, -(-a["servings"] // 8))  # ceil(servings/8)
    warn = (f"⚠️ ПРОВЕРЬ: {tiers} ярусов на {a['servings']} персон — похоже на ошибку/шутку.\n"
            if tiers > max_sane else "")
    card = (warn
            + f"🎂 НОВЫЙ ЗАКАЗ · {a['servings']} перс · {tiers} яр · {a['event_date']} · декор {a.get('decor')}\n"
            + format_quote_lines(q).replace("\n", "\n   ")
            + f"\nЗагрузка недели: {cap['booked']}/{cap['capacity']} — место есть ✅")
    return {"kind": "order", "card": card, "draft": draft}


def run_scenario(text: str, today: date):
    a, engine = ai_analyze(text, today)
    card = build_card(a, today)
    print("─" * 64)
    print(f"📩 [Instagram DM ← клиент]:\n   «{text}»")
    print(f"\n🧠 [AI-разбор · {engine}]:")
    shown = {k: (v.isoformat() if isinstance(v, date) else v)
             for k, v in a.items() if k in ("message_type", "servings", "event_date", "decor", "tiers", "delivery", "theme")}
    print("   " + json.dumps(shown, ensure_ascii=False))
    print(f"\n📋 [Карточка Даше на аппрув]:\n   " + card["card"].replace("\n", "\n   "))

    if card["kind"] == "sensitive":
        print("\n🚫 [Отправки НЕТ] — эскалация человеку. Даша отвечает лично.")
    elif card["draft"]:
        print("\n👆 [Даша нажимает ✅ Одобрить]")
        print("📤 [ИМИТАЦИЯ ОТПРАВКИ → клиенту в Instagram]:")
        print(f"   «{card['draft']}»")
    print()


def main():
    today = date(2026, 7, 1)
    if not GROQ_KEY:
        print("⚠️  GROQ_API_KEY не задан — работает регулярки-заглушка. "
              "Для настоящего AI: см. шапку файла.\n")

    if len(sys.argv) > 1:
        run_scenario(" ".join(sys.argv[1:]), today)
        return

    scenarios = [
        "привееет делаете тортики?? 🦕 нужен на др сына в сб 18 июля, он фанат динозавров, гостей человек 15, шоколадный можно?",
        "здравствуйте! очень нужен торт на 25 человек на эту пятницу 4 июля, двухъярусный, с доставкой. успеете??",
        "заказывала у вас торт на прошлой неделе, крем был кислый, гости заметили, очень расстроена...",
    ]
    for s in scenarios:
        run_scenario(s, today)


if __name__ == "__main__":
    main()
