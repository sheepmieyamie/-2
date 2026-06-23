from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


_CLIENT_ID_COLUMNS = (
    ("benchmark_accounts", "client_id"),
    ("chat_messages", "client_id"),
    ("chat_sessions", "client_id"),
    ("content_presets", "client_id"),
    ("reference_posts", "client_id"),
)


def migrate_client_id_columns() -> None:
    with engine.begin() as conn:
        for table, column in _CLIENT_ID_COLUMNS:
            try:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(64) DEFAULT ''")
                )
            except Exception:
                pass


def migrate_tenant_indexes() -> None:
    """不同客户可各自保存相同小红书 user_id 的独立副本。"""
    with engine.begin() as conn:
        for idx in (
            "ix_benchmark_accounts_user_id",
            "sqlite_autoindex_benchmark_accounts_1",
        ):
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))
            except Exception:
                pass
        try:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_benchmark_accounts_user_id "
                    "ON benchmark_accounts(user_id)"
                )
            )
        except Exception:
            pass
        try:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_benchmark_accounts_client_user "
                    "ON benchmark_accounts(client_id, user_id)"
                )
            )
        except Exception:
            pass
        try:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_reference_posts_client_note "
                    "ON reference_posts(client_id, note_id)"
                )
            )
        except Exception:
            pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
