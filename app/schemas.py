from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services import PROMO_CODE

TariffId = Literal["basic", "standard", "premium"]
PaymentMethod = Literal["card", "sbp", "installment"]
InstallmentMonths = Literal[3, 6, 12]
PaymentStatus = Literal["pending", "succeeded", "failed", "refunded"]


class TariffResponse(BaseModel):
    """Схема ответа для GET /tariffs."""
    id: str
    title: str
    price: int

    model_config = ConfigDict(from_attributes=True)


class PaymentCreate(BaseModel):
    """Схема входных данных для POST /payments."""
    tariff_id: TariffId
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    method: PaymentMethod
    installment_months: Optional[InstallmentMonths] = None
    promo_code: Optional[str] = None

    @field_validator("promo_code")
    def validate_promo_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalized = v.strip().upper()
        if normalized != PROMO_CODE:
            raise ValueError("Неизвестный промокод")
        return normalized

    @model_validator(mode="after")
    def validate_installment_rules(self) -> "PaymentCreate":
        if self.method == "installment" and self.installment_months is None:
            raise ValueError(
                "Для способа оплаты 'installment' поле installment_months обязательно (3, 6 или 12)"
            )
        if self.method != "installment" and self.installment_months is not None:
            raise ValueError(
                "Поле installment_months можно передавать только для способа оплаты 'installment'"
            )
        return self


class PaymentResponse(BaseModel):
    """Схема ответа с данными платежа."""
    id: int
    status: PaymentStatus
    tariff_id: str
    amount: int
    discount: int
    method: PaymentMethod
    installment_months: Optional[int] = None
    schedule: Optional[list[int]] = None
    email: str
    created_at: datetime

    @field_validator("created_at")
    def ensure_utc_timezone(cls, v: datetime) -> datetime:
        # SQLite возвращает naive datetime без tzinfo, явно указываем UTC
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    model_config = ConfigDict(from_attributes=True)


class BankWebhookRequest(BaseModel):
    """Схема тела запроса для POST /webhooks/bank."""
    payment_id: int
    status: PaymentStatus