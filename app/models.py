from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from app.database import Base


class Tariff(Base):
    __tablename__ = "tariffs"

    # Строковый ID: "basic", "standard", "premium"
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    # Цена строго в копейках (целое число, никаких float)
    price = Column(Integer, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    # Новый платёж всегда создаётся со статусом "pending"
    status = Column(String, nullable=False, default="pending", index=True)
    tariff_id = Column(String, ForeignKey("tariffs.id"), nullable=False)

    # Итоговая сумма к оплате и размер скидки — строго в копейках (Integer)
    amount = Column(Integer, nullable=False)
    discount = Column(Integer, nullable=False, default=0)

    # Способ оплаты: "card", "sbp" или "installment"
    method = Column(String, nullable=False)
    # Для рассрочки: 3, 6 или 12; для остальных способов — None (null)
    installment_months = Column(Integer, nullable=True)
    # График рассрочки: список целых чисел [663334, 663333, 663333] или None (null)
    schedule = Column(JSON, nullable=True)

    email = Column(String, nullable=False, index=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Уникальный ключ идемпотентности из заголовка Idempotency-Key
    idempotency_key = Column(String, unique=True, index=True, nullable=True)