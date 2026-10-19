from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Допустимые значения по условиям предметной области
TariffId = Literal["basic", "standard", "premium"]
PaymentMethod = Literal["card", "sbp", "installment"]
InstallmentMonths = Literal[3, 6, 12]
PaymentStatus = Literal["pending", "succeeded", "failed", "refunded"]


class TariffResponse(BaseModel):
    """Схема ответа для GET /tariffs."""
    id: str
    title: str
    price: int

    # В Pydantic v2 заменяет старый orm_mode = True,
    # позволяя собирать схему напрямую из объекта SQLAlchemy
    model_config = ConfigDict(from_attributes=True)


class PaymentCreate(BaseModel):
    """Схема входных данных для POST /payments."""
    tariff_id: TariffId
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    method: PaymentMethod
    installment_months: Optional[InstallmentMonths] = None
    promo_code: Optional[str] = None

    @field_validator("promo_code")
    @classmethod
    def validate_promo_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # Регистр не важен: приводим к верхнему регистру
        normalized = v.strip().upper()
        if normalized != "KVITTO10":
            # Выброс ValueError в Pydantic автоматически дает ответ 422 в FastAPI
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

    model_config = ConfigDict(from_attributes=True)


class BankWebhookRequest(BaseModel):
    """Схема тела запроса для POST /webhooks/bank."""
    payment_id: int
    status: PaymentStatus