"""
Консьерж заказов Даши — детерминированный движок цен и загрузки.

Это НЕ-AI слой системы (см. КАРТА_now_after.md): деньги и даты ведут
предсказуемые правила, а не языковая модель. AI-агент (промпт) отдаёт сюда
структурированный бриф, движок возвращает точную цену и проверку загрузки.

Запуск демо:  python3 price_engine.py
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# ПРАЙС-ПРАВИЛА (правит Даша, не AI). Валюта — ₽.
# ─────────────────────────────────────────────────────────────────────────────

BASE_BY_SERVINGS = [          # (макс. персон, базовая цена)
    (8,  2500),
    (15, 4000),
    (25, 6000),
    (40, 9000),
]
PRICE_PER_EXTRA_TIER = 2000   # за каждый ярус сверх первого
DECOR_SURCHARGE = {           # сложность декора
    "simple":  0,
    "medium":  1500,
    "complex": 3500,          # фигурки, ручная роспись, золочение
}
PREMIUM_FILLING_SURCHARGE = 500
DELIVERY_FEE = 800            # самовывоз = 0
RUSH_THRESHOLD_DAYS = 4       # заказ раньше этого срока = срочный
RUSH_MULTIPLIER = 0.30        # +30% к сумме

MAX_CAKES_PER_WEEK = 6        # физический лимит Даши


@dataclass
class Brief:
    """Структурированный бриф — то, что AI-агент собирает из DM."""
    servings: int
    event_date: date
    tiers: int = 1
    decor: str = "simple"                 # simple | medium | complex
    premium_filling: bool = False
    delivery: bool = False
    flavor: str = ""
    notes: str = ""


def _base_price(servings: int) -> int:
    for max_servings, price in BASE_BY_SERVINGS:
        if servings <= max_servings:
            return price
    # больше 40 персон — считаем пропорционально от верхней ступени
    top_servings, top_price = BASE_BY_SERVINGS[-1]
    return round(top_price * servings / top_servings)


def quote_price(brief: Brief, today: date | None = None) -> dict:
    """Возвращает разбивку цены. Полностью детерминирован и объясним."""
    today = today or date.today()
    days_until = (brief.event_date - today).days

    base = _base_price(brief.servings)
    tiers_extra = PRICE_PER_EXTRA_TIER * max(0, brief.tiers - 1)
    decor = DECOR_SURCHARGE.get(brief.decor, 0)
    filling = PREMIUM_FILLING_SURCHARGE if brief.premium_filling else 0
    delivery = DELIVERY_FEE if brief.delivery else 0

    subtotal = base + tiers_extra + decor + filling + delivery
    is_rush = days_until < RUSH_THRESHOLD_DAYS
    rush = round(subtotal * RUSH_MULTIPLIER) if is_rush else 0
    total = subtotal + rush

    return {
        "base": base,
        "tiers_extra": tiers_extra,
        "decor": decor,
        "premium_filling": filling,
        "delivery": delivery,
        "subtotal": subtotal,
        "is_rush": is_rush,
        "rush_fee": rush,
        "total": total,
        "days_until": days_until,
        "deposit": round(total * 0.5),   # предоплата 50%
    }


def check_capacity(event_date: date, booked_dates: list[date]) -> dict:
    """Сколько тортов уже занято на неделе события и есть ли место."""
    monday = event_date - timedelta(days=event_date.weekday())
    sunday = monday + timedelta(days=6)
    in_week = [d for d in booked_dates if monday <= d <= sunday]
    booked = len(in_week)
    return {
        "week": f"{monday.isoformat()} — {sunday.isoformat()}",
        "booked": booked,
        "capacity": MAX_CAKES_PER_WEEK,
        "has_room": booked < MAX_CAKES_PER_WEEK,
        "slots_left": max(0, MAX_CAKES_PER_WEEK - booked),
    }


def format_quote_lines(q: dict) -> str:
    """Человекочитаемая разбивка — попадает в черновик расценки Даше на аппрув."""
    lines = [f"База: {q['base']} ₽"]
    if q["tiers_extra"]:
        lines.append(f"Доп. ярусы: +{q['tiers_extra']} ₽")
    if q["decor"]:
        lines.append(f"Декор: +{q['decor']} ₽")
    if q["premium_filling"]:
        lines.append(f"Премиум-начинка: +{q['premium_filling']} ₽")
    if q["delivery"]:
        lines.append(f"Доставка: +{q['delivery']} ₽")
    if q["is_rush"]:
        lines.append(f"Срочность (+30%): +{q['rush_fee']} ₽")
    lines.append(f"ИТОГО: {q['total']} ₽ (предоплата {q['deposit']} ₽)")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# ДЕМО
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    today = date(2026, 7, 1)
    booked = [date(2026, 7, 10), date(2026, 7, 11), date(2026, 7, 12),
              date(2026, 7, 8), date(2026, 7, 9)]  # 5 тортов на неделе 6–12 июля

    print("=" * 60)
    print("ДЕМО 1: обычный заказ (есть место)")
    print("=" * 60)
    b1 = Brief(servings=12, event_date=date(2026, 7, 18), tiers=2,
               decor="medium", flavor="ваниль-малина", delivery=True)
    q1 = quote_price(b1, today)
    print(format_quote_lines(q1))
    cap1 = check_capacity(b1.event_date, booked)
    print(f"Загрузка недели {cap1['week']}: {cap1['booked']}/{cap1['capacity']} "
          f"→ мест: {cap1['slots_left']} → {'ОК' if cap1['has_room'] else 'ПОЛНО'}")

    print()
    print("=" * 60)
    print("ДЕМО 2: срочный сложный заказ (неделя ПОЛНАЯ)")
    print("=" * 60)
    booked_full = booked + [date(2026, 7, 7)]  # теперь 6/6
    b2 = Brief(servings=30, event_date=date(2026, 7, 3), tiers=3,
               decor="complex", premium_filling=True, delivery=True,
               flavor="шоколад-солёная карамель")
    q2 = quote_price(b2, today)
    print(format_quote_lines(q2))
    cap2 = check_capacity(b2.event_date, booked_full)
    print(f"Загрузка недели {cap2['week']}: {cap2['booked']}/{cap2['capacity']} "
          f"→ мест: {cap2['slots_left']} → {'ОК' if cap2['has_room'] else 'ПОЛНО → черновик отказа'}")
