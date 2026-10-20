from typing import Optional
from sqlalchemy.orm import Session
from app.models import Tariff

PROMO_CODE = "KVITTO10"
PROMO_DISCOUNT_PERCENT = 10

INITIAL_TARIFFS = [
    {"id": "basic", "title": "Basic", "price": 990000},       # 9 900 ₽
    {"id": "standard", "title": "Standard", "price": 1990000}, # 19 900 ₽
    {"id": "premium", "title": "Premium", "price": 2990000},   # 29 900 ₽
]

ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"succeeded", "failed"},
    "succeeded": {"refunded"},
    "failed": set(),
    "refunded": set(),
}


def seed_tariffs(db: Session) -> None:
    """Создаёт стартовые тарифы в БД при запуске, если их ещё нет."""
    for item in INITIAL_TARIFFS:
        exists = db.query(Tariff).filter(Tariff.id == item["id"]).first()
        if not exists:
            db.add(Tariff(**item))
    db.commit()


def calculate_discount_and_amount(
    price: int, promo_code: Optional[str]
) -> tuple[int, int]:
    """
    Считает скидку и итоговую сумму строго в целых копейках (без float).
    Возвращает кортеж: (discount, final_amount).
    """
    if promo_code and promo_code.upper() == PROMO_CODE:
        discount = (price * PROMO_DISCOUNT_PERCENT) // 100
    else:
        discount = 0

    final_amount = price - discount
    return discount, final_amount


def calculate_installment_schedule(
    amount: int, months: Optional[int]
) -> Optional[list[int]]:
    """
    Делит сумму к оплате на количество месяцев в копейках.
    Лишние копейки от остатка деления распределяются по первым платежам.
    """
    if months is None:
        return None

    base_payment, remainder = divmod(amount, months)
    return [
        base_payment + (1 if i < remainder else 0)
        for i in range(months)
    ]


def is_valid_status_transition(current_status: str, new_status: str) -> bool:
    """Проверяет, разрешён ли переход из текущего статуса в новый."""
    allowed_targets = ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
    return new_status in allowed_targets