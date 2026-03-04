# backend/app/database.py
"""
SQLAlchemy データベース設定。

Phase 12: ユーザー認証・アカウント管理用の SQLite データベース。
PoC Pivot: DATABASE_URL 環境変数で PostgreSQL (+ pgvector) に切り替え可能。
           未設定時は SQLite にフォールバック（既存テスト互換性を維持）。
"""

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """SQLAlchemy モデルの基底クラス。"""

    pass


def get_database_url() -> str:
    """
    データベース URL を取得する。

    環境変数 DATABASE_URL が設定されていればそれを使用、
    なければデフォルトの SQLite パスを使用。
    """
    default_path = Path(__file__).parent.parent / "data" / "users.db"
    return os.getenv("DATABASE_URL", f"sqlite:///{default_path}")


# データベースディレクトリを作成（SQLite の場合のみ）
db_url = get_database_url()
if db_url.startswith("sqlite:///"):
    db_path = Path(db_url.replace("sqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)

# connect_args は SQLite 専用 (check_same_thread)。PostgreSQL では不要。
_connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine = create_engine(
    db_url,
    connect_args=_connect_args,
    echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依存性注入用のデータベースセッション取得。

    Usage:
        @router.get("/users")
        def get_users(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    データベーステーブルを初期化する。

    アプリケーション起動時に呼び出す。
    PostgreSQL 使用時は pgvector 拡張を有効化する。
    """
    if db_url.startswith("postgresql"):
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

    Base.metadata.create_all(bind=engine)
