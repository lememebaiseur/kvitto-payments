from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from app.database import Base


class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    price = Column(Integer, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    status = Column(String, nullable=False, default="pending")
    tariff_id = Column(String, ForeignKey("tariffs.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    discount = Column(Integer, nullable=False, default=0)
    method = Column(String, nullable=False)
    installment_months = Column(Integer, nullable=True)
    schedule = Column(JSON, nullable=True)
    email = Column(String, nullable=False)
    idempotency_key = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )