import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _default_db_url() -> str:
    # Default to a local SQLite file inside workspace or container
    db_dir = os.getenv("DB_DIR", os.path.join(os.getcwd(), "var", "lib", "routehelper"))
    os.makedirs(db_dir, exist_ok=True)
    return f"sqlite:///{os.path.join(db_dir, 'routehelper.db')}"


DATABASE_URL = os.getenv("DATABASE_URL", _default_db_url())

# SQLite needs check_same_thread=False for FastAPI multi-threaded default
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
