# backend/app/database.py
"""
SQLAlchemy データベース設定。

Phase 12: ユーザー認証・アカウント管理用の SQLite データベース。
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase


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


# データベースディレクトリを作成
db_url = get_database_url()
if db_url.startswith("sqlite:///"):
    db_path = Path(db_url.replace("sqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    db_url,
    connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
    echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
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


def init_db():
    """
    データベーステーブルを初期化する。

    アプリケーション起動時に呼び出す。
    """
    Base.metadata.create_all(bind=engine)
