import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services import seed_tariffs

# Создаём изолированную тестовую БД в оперативной памяти (in-memory SQLite)
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
    Фикстура создаёт чистую БД перед каждым тестом, заполняет тарифы
    и подменяет зависимость get_db через dependency_overrides.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_tariffs(db)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    # Та самая подмена зависимости Depends для тестов!
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    db.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


# 1. Тест: сумма с промокодом и без, в том числе промокод в нижнем регистре
def test_payment_amount_with_and_without_promo_code(client: TestClient):
    # Без промокода: тариф standard = 1990000 копеек
    res_no_promo = client.post(
        "/payments",
        json={"tariff_id": "standard", "email": "user@test.ru", "method": "card"},
    )
    assert res_no_promo.status_code == 201
    data_no_promo = res_no_promo.json()
    assert data_no_promo["amount"] == 1990000
    assert data_no_promo["discount"] == 0
    assert data_no_promo["schedule"] is None

    # С промокодом в верхнем регистре (KVITTO10 -> скидка 10% = 199000 копеек)
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

    # С промокодом в нижнем регистре (kvitto10 -> регистр не важен)
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

    # Неизвестный промокод должен возвращать ошибку валидации 422
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


# 2. Тест: график рассрочки — сумма графика равна сумме к оплате для 3, 6 и 12 месяцев
@pytest.mark.parametrize("months", [3, 6, 12])
def test_installment_schedule_sum(client: TestClient, months: int):
    # Тариф standard (1990000 копеек) не делится нацело ни на 3, ни на 6, ни на 12
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
    # Главная проверка: сумма всех платежей графика ровно равна сумме к оплате
    assert sum(schedule) == data["amount"] == 1990000

    # Дополнительная проверка точного распределения копеек на примере 3 месяцев из ТЗ
    if months == 3:
        assert schedule == [663334, 663333, 663333]


# 3. Тест: повторный запрос с тем же Idempotency-Key не создаёт второй платёж
def test_idempotency_key_prevents_duplicates(client: TestClient):
    headers = {"Idempotency-Key": "idem-key-12345"}
    payload = {"tariff_id": "premium", "email": "idem@test.ru", "method": "card"}

    # Первый запрос создаёт платёж и возвращает 201
    first_res = client.post("/payments", json=payload, headers=headers)
    assert first_res.status_code == 201
    first_data = first_res.json()

    # Повторный запрос с тем же ключом возвращает 200 и тот же самый ID платежа
    second_res = client.post("/payments", json=payload, headers=headers)
    assert second_res.status_code == 200
    second_data = second_res.json()

    assert second_data["id"] == first_data["id"]
    assert second_data["amount"] == first_data["amount"]


# 4. Тест: запрещённый переход статуса возвращает 409 и не меняет статус
def test_invalid_status_transition_returns_409_and_keeps_status(client: TestClient):
    # Создаём новый платёж (изначально в статусе "pending")
    create_res = client.post(
        "/payments",
        json={"tariff_id": "basic", "email": "status@test.ru", "method": "card"},
    )
    payment_id = create_res.json()["id"]

    # Пытаемся перевести из "pending" сразу в "refunded" (запрещённый переход)
    webhook_res = client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "refunded"},
    )
    assert webhook_res.status_code == 409
    assert webhook_res.json() == {"error": "invalid_transition"}

    # Проверяем через GET, что статус в базе действительно НЕ изменился и остался "pending"
    get_res = client.get(f"/payments/{payment_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "pending"


# 5. Тест: запрос несуществующего платежа возвращает 404
def test_get_nonexistent_payment_returns_404(client: TestClient):
    res_get = client.get("/payments/999999")
    assert res_get.status_code == 404

    res_webhook = client.post(
        "/webhooks/bank",
        json={"payment_id": 999999, "status": "succeeded"},
    )
    assert res_webhook.status_code == 404