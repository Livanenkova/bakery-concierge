"""
Консьерж заказов Даши — живой Telegram-бот (пульт аппрува).

Поток:
  сырой DM клиента (пишем боту)
    → analyze_dm(): бриф + тип сообщения
    → price_engine: цена + загрузка недели
    → боту Даши прилетает КАРТОЧКА с кнопками [✅ Одобрить][✏️ Изменить][❌ Отклонить]
    → тап Даши = «отправка клиенту» (в демо бот подтверждает отправку)

Бесплатно: Telegram Bot API бесплатен. LLM-ключ НЕ нужен — умный разбор здесь
сделан детерминированным парсером (для живого демо). Место, где в прод встаёт
настоящий AI-агент из agent_concierge.md, помечено ниже как [AI-HOOK].

Запуск (никаких pip install не нужно — только стандартный Python):
  export BOT_TOKEN="токен от @BotFather"
  python3 telegram_bot.py
"""

import os
import re
import time
import json
import urllib.request
import urllib.parse
from datetime import date, timedelta

from price_engine import Brief, quote_price, check_capacity, format_quote_lines

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DASHA_CHAT_ID = os.environ.get("DASHA_CHAT_ID", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Демо-данные загрузки (в прод — из календаря Даши)
BOOKED_DATES = [date(2026, 7, 14)]

# Черновики, ждущие аппрува: callback_id -> {draft, chat}
PENDING = {}


# ─────────────────────────────────────────────────────────────────────────────
# РАЗБОР DM
# ─────────────────────────────────────────────────────────────────────────────
SENSITIVE_WORDS = ["жалоб", "кисл", "испорт", "ужасн", "верните", "возврат",
                   "похорон", "соболезн", "болезн", "расстроен", "недоволен"]
COMPLEX_WORDS = ["фигур", "динозавр", "роспис", "золот", "3d", "объёмн", "лепк"]
MEDIUM_WORDS = ["цвет", "ягод", "надпис", "декор", "тема"]
DELIVERY_WORDS = ["достав", "привез", "адрес"]

MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
          "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}


def _parse_date(text: str, today: date) -> date | None:
    m = re.search(r"(\d{1,2})[\.\s]+(январ|феврал|март|апрел|ма|июн|июл|август|сентябр|октябр|ноябр|декабр)", text)
    if m:
        day = int(m.group(1))
        month = MONTHS[m.group(2)]
        year = today.year if month >= today.month else today.year + 1
        try:
            return date(year, month, day)
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\.(\d{1,2})", text)
    if m:
        try:
            return date(today.year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def analyze_dm(text: str, today: date | None = None) -> dict:
    """
    [AI-HOOK] В проде здесь вызывается LLM по промпту agent_concierge.md.
    Для бесплатного живого демо — детерминированный парсер.
    """
    today = today or date.today()
    low = text.lower()

    if any(w in low for w in SENSITIVE_WORDS):
        return {"message_type": "sensitive", "escalate_to_human": True,
                "note": "Жалоба/чувствительное — пишет Даша лично."}

    servings = None
    m = re.search(r"(\d{1,3})\s*(человек|персон|гост|чел)", low)          # «15 человек»
    if not m:
        m = re.search(r"(?:человек|персон|гост|гостей|чел)\w*\s*(\d{1,3})", low)  # «человек 15»
    if m:
        servings = int(m.group(1))

    event_date = _parse_date(low, today)

    if any(w in low for w in COMPLEX_WORDS):
        decor = "complex"
    elif any(w in low for w in MEDIUM_WORDS):
        decor = "medium"
    else:
        decor = "simple"

    tiers = 2 if ("ярус" in low or "двухъярус" in low) else 1
    delivery = any(w in low for w in DELIVERY_WORDS)

    return {"message_type": "order", "escalate_to_human": False,
            "servings": servings, "event_date": event_date,
            "decor": decor, "tiers": tiers, "delivery": delivery}


# ─────────────────────────────────────────────────────────────────────────────
# КАРТОЧКА ДЛЯ ДАШИ
# ─────────────────────────────────────────────────────────────────────────────
def build_card(a: dict, today: date) -> dict:
    """Возвращает {text, buttons, draft_to_client}."""
    if a["message_type"] == "sensitive":
        return {
            "text": ("🙋 *Только для тебя — не автоматизирую*\n\n"
                     "Клиент прислал чувствительное сообщение (жалоба/тяжёлая тема).\n"
                     "Я не пишу черновик — ответ должен идти лично от тебя."),
            "buttons": [[{"text": "Открыть переписку", "callback_data": "open"}]],
            "draft_to_client": None,
        }

    if not a.get("servings") or not a.get("event_date"):
        missing = []
        if not a.get("servings"):
            missing.append("число персон")
        if not a.get("event_date"):
            missing.append("дату")
        return {
            "text": ("🧐 Не хватает данных для расчёта: " + ", ".join(missing) +
                     ".\nЧерновик уточняющего вопроса клиенту:\n"
                     "_«Обожаю такие заказы! Подскажи, пожалуйста, " + " и ".join(missing) + "? 😊»_"),
            "buttons": [[{"text": "✅ Отправить уточнение", "callback_data": "ask"},
                         {"text": "✏️ Изменить", "callback_data": "edit"}]],
            "draft_to_client": None,
        }

    brief = Brief(servings=a["servings"], event_date=a["event_date"],
                  tiers=a["tiers"], decor=a["decor"], delivery=a["delivery"])
    q = quote_price(brief, today)
    cap = check_capacity(a["event_date"], BOOKED_DATES)

    if not cap["has_room"]:
        draft = ("Ой, спасибо, что подумали обо мне! 🙈 Но на эту неделю я уже полностью "
                 "расписана и не хочу делать ваш торт наспех. Могу поставить в лист ожидания "
                 "или испечь к следующей свободной дате — как вам?")
        return {
            "text": (f"⚠️ *Неделя {cap['week']} — {cap['booked']}/{cap['capacity']} ПОЛНАЯ*\n\n"
                     f"Заказ: {a['servings']} перс. · {a['event_date']}\n"
                     f"Рекомендую: *отказ + вейтлист* (не бери наспех).\n\n"
                     f"Черновик отказа:\n_{draft}_"),
            "buttons": [[{"text": "✅ Отправить отказ", "callback_data": "decline"},
                         {"text": "📅 Другая дата", "callback_data": "reschedule"}]],
            "draft_to_client": draft,
        }

    draft = (f"Обожаю такие заказы! 🎂 На {a['servings']} человек к {a['event_date']} сделаю "
             f"— выйдет *{q['total']} ₽* (предоплата {q['deposit']} ₽ бронирует дату). Подтверждаем? 😊")
    lines = format_quote_lines(q).replace("\n", "\n· ")
    return {
        "text": (f"🎂 *Новый заказ*\n{a['servings']} перс. · {a['event_date']} · "
                 f"декор: {a['decor']} · {'доставка' if a['delivery'] else 'самовывоз'}\n\n"
                 f"· {lines}\n\n"
                 f"Неделя {cap['week']}: {cap['booked']}/{cap['capacity']} ✅\n\n"
                 f"Черновик ответа:\n_{draft}_"),
        "buttons": [[{"text": "✅ Одобрить и отправить", "callback_data": "approve"},
                     {"text": "✏️ Изменить", "callback_data": "edit"},
                     {"text": "❌ Отклонить", "callback_data": "reject"}]],
        "draft_to_client": draft,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM API
# ─────────────────────────────────────────────────────────────────────────────
def _call(method, params, timeout=40):
    """HTTP-запрос к Telegram Bot API на стандартной библиотеке (без requests)."""
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print("Ошибка запроса:", e)
        return {}


def send(chat_id, text, buttons=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    _call("sendMessage", payload, timeout=30)


def answer_callback(cb_id, text=""):
    _call("answerCallbackQuery", {"callback_query_id": cb_id, "text": text}, timeout=30)


def run():
    assert BOT_TOKEN, "Задай BOT_TOKEN (см. шапку файла)"
    today = date.today()
    print("Бот запущен. Пиши боту сырой DM клиента — карточка прилетит Даше.")
    offset = None
    while True:
        params = {"timeout": 30}
        if offset is not None:
            params["offset"] = offset
        r = _call("getUpdates", params, timeout=40)
        for upd in r.get("result", []):
            offset = upd["update_id"] + 1

            # входящее сообщение = сырой DM клиента
            if "message" in upd and "text" in upd["message"]:
                text = upd["message"]["text"]
                sender_chat = upd["message"]["chat"]["id"]
                # куда шлём карточку Даши: заданный чат, иначе — отправителю (соло-демо)
                dasha_chat = DASHA_CHAT_ID or sender_chat
                if text.startswith("/start"):
                    send(sender_chat,
                         "Привет! Пришли мне сообщение клиента — я подготовлю карточку Даше.")
                    continue
                a = analyze_dm(text, today)
                card = build_card(a, today)
                send(dasha_chat, card["text"], card["buttons"])
                PENDING[str(dasha_chat)] = card

            # тап по кнопке
            elif "callback_query" in upd:
                cb = upd["callback_query"]
                data = cb["data"]
                card = PENDING.get(str(cb["message"]["chat"]["id"]))
                if data == "approve" and card and card["draft_to_client"]:
                    answer_callback(cb["id"], "Отправлено клиенту ✅")
                    send(cb["message"]["chat"]["id"],
                         "✅ *Отправлено клиенту в Instagram:*\n" + card["draft_to_client"])
                elif data == "decline":
                    answer_callback(cb["id"], "Отказ отправлен")
                    send(cb["message"]["chat"]["id"], "✅ Тёплый отказ отправлен, дата свободна.")
                elif data == "reject":
                    answer_callback(cb["id"], "Отклонено")
                    send(cb["message"]["chat"]["id"], "❌ Заказ отклонён, клиенту ничего не ушло.")
                else:
                    answer_callback(cb["id"], "Ок")
                    send(cb["message"]["chat"]["id"], "✏️ Открой черновик, поправь и отправь вручную.")
        time.sleep(1)


if __name__ == "__main__":
    run()
