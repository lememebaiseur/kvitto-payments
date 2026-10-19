from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Payment, Tariff
from app.schemas import (
    BankWebhookRequest,
    PaymentCreate,
    PaymentResponse,
    TariffResponse,
)
from app.services import (
    calculate_discount_and_amount,
    calculate_installment_schedule,
    is_valid_status_transition,
)

router = APIRouter()


@router.get("/tariffs", response_model=list[TariffResponse], status_code=status.HTTP_200_OK)
def get_tariffs(db: Session = Depends(get_db)):
    """Возвращает список доступных тарифов."""
    return db.query(Tariff).all()


@router.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    payload: PaymentCreate,
    response: Response,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    """
    Создаёт новый платёж (201).
    Если передан заголовок Idempotency-Key и платёж уже есть — возвращает его с кодом 200.
    """
    # 1. Проверка идемпотентности
    if idempotency_key:
        existing_payment = (
            db.query(Payment)
            .filter(Payment.idempotency_key == idempotency_key)
            .first()
        )
        if existing_payment:
            response.status_code = status.HTTP_200_OK
            return existing_payment

    # 2. Получаем тариф из БД
    tariff = db.query(Tariff).filter(Tariff.id == payload.tariff_id).first()
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tariff not found"
        )

    # 3. Считаем скидку, итоговую сумму в копейках и график рассрочки
    discount, final_amount = calculate_discount_and_amount(
        price=tariff.price, promo_code=payload.promo_code
    )
    schedule = calculate_installment_schedule(
        amount=final_amount, months=payload.installment_months
    )

    # 4. Сохраняем новый платёж со статусом pending
    new_payment = Payment(
        status="pending",
        tariff_id=tariff.id,
        amount=final_amount,
        discount=discount,
        method=payload.method,
        installment_months=payload.installment_months,
        schedule=schedule,
        email=payload.email,
        idempotency_key=idempotency_key,
    )
    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)

    return new_payment


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
)
def get_payment(payment_id: int, db: Session = Depends(get_db)):
    """Возвращает платёж по его ID или 404, если платёж не найден."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )
    return payment


@router.get(
    "/payments",
    response_model=list[PaymentResponse],
    status_code=status.HTTP_200_OK,
)
def get_payments_list(
    email: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Бонус: Получение списка платежей с фильтрацией по email и status."""
    query = db.query(Payment)
    if email:
        query = query.filter(Payment.email == email)
    if status_filter:
        query = query.filter(Payment.status == status_filter)
    return query.all()


@router.post("/webhooks/bank", status_code=status.HTTP_200_OK)
def bank_webhook(payload: BankWebhookRequest, db: Session = Depends(get_db)):
    """Обрабатывает уведомление от банка о смене статуса платежа."""
    payment = db.query(Payment).filter(Payment.id == payload.payment_id).first()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )

    # Проверяем, допустим ли переход статуса
    if not is_valid_status_transition(payment.status, payload.status):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "invalid_transition"},
        )

    payment.status = payload.status
    db.commit()
    return {"result": "ok"}