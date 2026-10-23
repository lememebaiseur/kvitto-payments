#Payments API

Небольшой сервис на FastAPI для приёма оплаты :
три эндпоинта, уведомление от банка, расчёт в копейках без потерь, промокод,
график рассрочки и идемпотентность создания платежей.

## Стек

- Python 3.11+
- FastAPI + Pydantic v2
- SQLAlchemy 2.0 + SQLite 
- pytest + httpx

## Запуск

Нужен Python 3.11 или новее.

```bash
git clone https://github.com/lememebaiseur/sync_payments.git
cd sync_payments

python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\Activate.ps1     # Windows (PowerShell)

pip install -r requirements.txt
uvicorn app.main:app --reload
```

После запуска:

- API: http://127.0.0.1:8000
- Swagger UI (можно пробовать запросы в браузере): http://127.0.0.1:8000/docs

### Запуск через Docker Compose

```bash
docker compose up --build
```

Сервис будет доступен на http://localhost:8000.

## Тесты

```bash
pytest
```

Тесты работают на in-memory SQLite и не затрагивают файл `kvitto.db`.

## Правила предметной области

- Все суммы в API и в базе — целые числа в копейках (`19 900 ₽` → `1990000`), без `float`.
- Тарифы: `basic` — 990000, `standard` — 1990000, `premium` — 2990000.
- Промокод `10` даёт −10% от цены тарифа, регистр не важен. Неизвестный код — 422.
- Способ оплаты: `card`, `sbp` или `installment`. Для `installment` обязателен
  `installment_months`: 3, 6 или 12. Для остальных способов это поле передавать нельзя (422).
- График рассрочки: сумма к оплате делится на срок в копейках, лишние копейки идут
  в первые платежи. Сумма графика всегда равна сумме к оплате.
- Статусы: новый платёж — `pending`. Разрешены переходы
  `pending → succeeded`, `pending → failed`, `succeeded → refunded`. Остальные запрещены.

## Эндпоинты

| Метод и путь | Что делает |
|---|---|
| `GET /tariffs` | Список тарифов `[{id, title, price}]` |
| `POST /payments` | Создаёт платёж (201). С заголовком `Idempotency-Key` повторный запрос возвращает тот же платёж с кодом 200 |
| `GET /payments/{id}` | Платёж по id, 404 если не найден |
| `GET /payments?email=...&status=...` | Список платежей с фильтрами (бонус) |
| `POST /webhooks/bank` | Уведомление банка `{payment_id, status}`. 404 — платежа нет, 409 `{"error": "invalid_transition"}` — запрещённый переход, 200 `{"result": "ok"}` — успех |

Ошибки валидации — стандартный ответ FastAPI с кодом 422.

## Примеры запросов

Примеры для bash (Linux, macOS, Git Bash). В Windows PowerShell удобнее
использовать Swagger UI на `/docs`.

Список тарифов:

```bash
curl http://127.0.0.1:8000/tariffs
```

Рассрочка на 3 месяца без промокода (пример из ТЗ):

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-1001" \
  -d '{"tariff_id": "standard", "email": "student@example.com", "method": "installment", "installment_months": 3}'
```

Ответ (201): `amount` — `1990000`, `discount` — `0`, `schedule` — `[663334, 663333, 663333]`.
Тот же запрос с тем же `Idempotency-Key` вернёт 200 и тот же платёж, второй не создаётся.

Оплата картой с промокодом (регистр не важен):

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"tariff_id": "standard", "email": "student@example.com", "method": "card", "promo_code": "kvitto10"}'
```

Ответ (201): `discount` — `199000`, `amount` — `1791000`, `schedule` — `null`.

Получить платёж:

```bash
curl http://127.0.0.1:8000/payments/1
```

Уведомление от банка об успешной оплате:

```bash
curl -X POST http://127.0.0.1:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -d '{"payment_id": 1, "status": "succeeded"}'
```

Ответ (200): `{"result": "ok"}`. Повторная попытка перевести `succeeded` обратно в `pending`
вернёт 409 `{"error": "invalid_transition"}`, статус платежа не изменится.

Фильтры списка платежей:

```bash
curl "http://127.0.0.1:8000/payments?email=student@example.com&status=pending"
```
