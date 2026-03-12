#!/usr/bin/env python3
"""
Staging 環境の初期ユーザー作成スクリプト。

Usage:
    cd backend
    python ../scripts/seed_staging_users.py

環境変数:
    DATABASE_URL (省略時: SQLite fallback)
"""
from __future__ import annotations

import sys
import os

# backend/ をパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import SessionLocal, init_db
from app.auth.models import UserRole
from app.auth.service import AuthService
from app.auth.schemas import UserCreateRequest

USERS = [
    {
        "email": "hkobayashi@ultra-autotrade.com",
        "username": "hkobayashi",
        "password": "#GJyd9@16H1$RTpZZins",
        "role": UserRole.ADMIN,
    },
    {
        "email": "partner@ultra-autotrade.com",
        "username": "partner",
        "password": "CRJBuG#54cO7TEHA4fYO",
        "role": UserRole.EDITOR,
    },
    {
        "email": "test@ultra-autotrade.com",
        "username": "testuser",
        "password": "NQcAKhk#WewCfX%^6htF",
        "role": UserRole.VIEWER,
    },
]


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        for u in USERS:
            existing = db.query(__import__("app.auth.models", fromlist=["User"]).User).filter_by(email=u["email"]).first()
            if existing:
                print(f"SKIP (already exists): {u['email']}")
                continue

            req = UserCreateRequest(
                email=u["email"],
                username=u["username"],
                password=u["password"],
                role=u["role"],
            )
            user = AuthService.create_user(db, req)
            print(f"CREATED: {user.email} role={user.role}")
        db.commit()
        print("\nDone.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
