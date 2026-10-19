from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Локальный файл базы данных SQLite в корне проекта
SQLALCHEMY_DATABASE_URL = "sqlite:///./kvitto.db"

# check_same_thread=False нужен только для SQLite, так как FastAPI может
# обращаться к сессии из разных потоков в рамках одного запроса
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Генератор сессии БД для внедрения через Depends(get_db)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()