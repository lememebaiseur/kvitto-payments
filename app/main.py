from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import Base, SessionLocal, engine
from app.routers import router
from app.services import seed_tariffs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём таблицы в БД и заполняем тарифы при старте сервиса
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_tariffs(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Kvitto Payments API",
    description="Сервис приёма оплат курсов для онлайн-школы",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)