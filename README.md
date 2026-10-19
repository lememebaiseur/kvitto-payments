# Kvitto Payments API

Небольшой сервис на FastAPI для приёма оплаты курсов онлайн-школы (расчёт в копейках без потерь, промокоды, график рассрочки, идемпотентность и обработка банковских вебхуков).

## Стек
* Python 3.11+
* FastAPI + Pydantic v2
* SQLAlchemy 2.0 + SQLite (база создаётся автоматически в файле `kvitto.db`, стартовые тарифы инициализируются при запуске)
* `pytest` + `httpx`

## Быстрый запуск

1. Клонируйте репозиторий и перейдите в папку проекта:
   ```bash
   git clone https://github.com/lememebaiseur/kvitto-payments.git
   cd kvitto-payments
   
## Запуск через Docker Compose (Бонус)
```bash
docker compose up --build