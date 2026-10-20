import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services import seed_tariffs

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def client():
    """
    Создаёт чистую in-memory БД перед каждым тестом.
    TestClient создаётся без контекстного менеджера `with`, чтобы не запускался
    lifespan приложения, который обращается к файловой БД kvitto.db.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_tariffs(db)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    test_client = TestClient(app)
    yield test_client

    db.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


# 1. Тест списка тарифов
def test_get_tariffs(client: TestClient):
    res = client.get("/tariffs")
    assert res.status_code == 200
    tariffs = res.json()
    assert len(tariffs) == 3
    assert {t["id"] for t in tariffs} == {"basic", "standard", "premium"}
    prices = {t["id"]: t["price"] for t in tariffs}
    assert prices == {"basic": 990000, "standard": 1990000, "premium": 2990000}


# 2. Тест: сумма с промокодом и без, в том числе промокод в нижнем регистре
def test_payment_amount_with_and_without_promo_code(client: TestClient):
    res_no_promo = client.post(
        "/payments",
        json={"tariff_id": "standard", "email": "user@test.ru", "method": "card"},
    )
    assert res_no_promo.status_code == 201
    data_no_promo = res_no_promo.json()
    assert data_no_promo["amount"] == 1990000
    assert data_no_promo["discount"] == 0
    assert data_no_promo["schedule"] is None
    assert data_no_promo["created_at"].endswith("Z") or "+00:00" in data_no_promo["created_at"]

    res_upper = client.post(
        "/payments",
        json={
            "tariff_id": "standard",
            "email": "user@test.ru",
            "method": "sbp",
            "promo_code": "KVITTO10",
        },
    )
    assert res_upper.status_code == 201
    data_upper = res_upper.json()
    assert data_upper["discount"] == 199000
    assert data_upper["amount"] == 1791000

    res_lower = client.post(
        "/payments",
        json={
            "tariff_id": "basic",
            "email": "user@test.ru",
            "method": "card",
            "promo_code": "kvitto10",
        },
    )
    assert res_lower.status_code == 201
    data_lower = res_lower.json()
    assert data_lower["discount"] == 99000
    assert data_lower["amount"] == 891000

    res_invalid = client.post(
        "/payments",
        json={
            "tariff_id": "basic",
            "email": "user@test.ru",
            "method": "card",
            "promo_code": "WRONG50",
        },
    )
    assert res_invalid.status_code == 422


# 3. Тест: график рассрочки — сумма графика равна сумме к оплате для 3, 6 и 12 месяцев
@pytest.mark.parametrize("months", [3, 6, 12])
def test_installment_schedule_sum(client: TestClient, months: int):
    response = client.post(
        "/payments",
        json={
            "tariff_id": "standard",
            "email": "student@test.ru",
            "method": "installment",
            "installment_months": months,
        },
    )
    assert response.status_code == 201
    data = response.json()

    schedule = data["schedule"]
    assert isinstance(schedule, list)
    assert len(schedule) == months
    assert sum(schedule) == data["amount"] == 1990000

    if months == 3:
        assert schedule == [663334, 663333, 663333]


# 4. Тест валидации рассрочки (installment без месяцев и card с месяцами -> 422)
def test_installment_validation_errors(client: TestClient):
    res_missing_months = client.post(
        "/payments",
        json={
            "tariff_id": "basic",
            "email": "student@test.ru",
            "method": "installment",
        },
    )
    assert res_missing_months.status_code == 422

    res_extra_months = client.post(
        "/payments",
        json={
            "tariff_id": "basic",
            "email": "student@test.ru",
            "method": "card",
            "installment_months": 6,
        },
    )
    assert res_extra_months.status_code == 422


# 5. Тест: повторный запрос с тем же Idempotency-Key не создаёт второй платёж
def test_idempotency_key_prevents_duplicates(client: TestClient):
    headers = {"Idempotency-Key": "idem-key-12345"}
    payload = {"tariff_id": "premium", "email": "idem@test.ru", "method": "card"}

    first_res = client.post("/payments", json=payload, headers=headers)
    assert first_res.status_code == 201
    first_data = first_res.json()

    second_res = client.post("/payments", json=payload, headers=headers)
    assert second_res.status_code == 200
    second_data = second_res.json()

    assert second_data["id"] == first_data["id"]
    assert second_data["amount"] == first_data["amount"]

    # Убеждаемся, что в БД физически существует ровно один платёж
    list_res = client.get("/payments")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1


# 6. Тест успешной смены статусов по вебхуку (цепочка pending -> succeeded -> refunded)
def test_valid_webhook_status_transitions(client: TestClient):
    create_res = client.post(
        "/payments",
        json={"tariff_id": "basic", "email": "ok@test.ru", "method": "card"},
    )
    payment_id = create_res.json()["id"]

    # pending -> succeeded
    res_suc = client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "succeeded"},
    )
    assert res_suc.status_code == 200
    assert res_suc.json() == {"result": "ok"}
    assert client.get(f"/payments/{payment_id}").json()["status"] == "succeeded"

    # succeeded -> refunded
    res_ref = client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "refunded"},
    )
    assert res_ref.status_code == 200
    assert client.get(f"/payments/{payment_id}").json()["status"] == "refunded"


# 7. Тест: запрещённый переход статуса возвращает 409 и не меняет статус
def test_invalid_status_transition_returns_409_and_keeps_status(client: TestClient):
    create_res = client.post(
        "/payments",
        json={"tariff_id": "basic", "email": "status@test.ru", "method": "card"},
    )
    payment_id = create_res.json()["id"]

    webhook_res = client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "refunded"},
    )
    assert webhook_res.status_code == 409
    assert webhook_res.json() == {"error": "invalid_transition"}

    get_res = client.get(f"/payments/{payment_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "pending"


# 8. Тест: запрос несуществующего платежа возвращает 404
def test_get_nonexistent_payment_returns_404(client: TestClient):
    res_get = client.get("/payments/999999")
    assert res_get.status_code == 404

    res_webhook = client.post(
        "/webhooks/bank",
        json={"payment_id": 999999, "status": "succeeded"},
    )
    assert res_webhook.status_code == 404


# 9. Тест бонусного эндпоинта GET /payments с фильтрами по email и status
def test_get_payments_filters(client: TestClient):
    p1 = client.post(
        "/payments",
        json={"tariff_id": "basic", "email": "a@test.ru", "method": "card"},
    ).json()
    client.post(
        "/payments",
        json={"tariff_id": "standard", "email": "b@test.ru", "method": "sbp"},
    )
    client.post(
        "/webhooks/bank",
        json={"payment_id": p1["id"], "status": "succeeded"},
    )

    res_email = client.get("/payments", params={"email": "a@test.ru"})
    assert len(res_email.json()) == 1
    assert res_email.json()[0]["email"] == "a@test.ru"

    res_status = client.get("/payments", params={"status": "pending"})
    assert len(res_status.json()) == 1
    assert res_status.json()[0]["email"] == "b@test.ru"