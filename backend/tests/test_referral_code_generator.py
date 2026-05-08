# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_referral_code_generator.py
"""RAS Lane 2: 紹介コード生成のユニットテスト。"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-referral-codegen")

from app.auth.models import User, UserRole  # noqa: E402
from app.database import Base  # noqa: E402
from app.referral import code_generator  # noqa: E402
from app.referral.code_generator import (  # noqa: E402
    MAX_RETRY,
    REFERRAL_CODE_LENGTH,
    generate_referral_code,
)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        os.unlink(path)


def _make_partner(db: Session, email: str, username: str, code: str | None = None) -> User:
    u = User(
        email=email,
        username=username,
        hashed_password="$dummy$",  # noqa: S106
        role=UserRole.PARTNER.value,
        referral_code=code,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_generate_referral_code_format(db: Session) -> None:
    code = generate_referral_code(db)
    assert len(code) == REFERRAL_CODE_LENGTH
    assert code.isalnum()
    # 混同しやすい I/O/0/1 を含まない
    assert all(ch not in code for ch in "IO01")


def test_generate_referral_code_uniqueness(db: Session) -> None:
    codes = {generate_referral_code(db) for _ in range(20)}
    # 20 個生成しても重複が極めて少ない (一意性は最大32^8≈10^12なので衝突確率ほぼ0)
    assert len(codes) >= 19


def test_generate_referral_code_retries_then_succeeds(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """最初は既存コードと衝突、リトライで成功することを確認。"""
    _make_partner(db, "p1@example.com", "p1user", code="COLLIDE1")
    _make_partner(db, "p2@example.com", "p2user", code="COLLIDE2")

    candidates = iter(["COLLIDE1", "COLLIDE2", "FRESHCOD"])
    monkeypatch.setattr(code_generator, "_random_code", lambda: next(candidates))

    code = generate_referral_code(db)
    assert code == "FRESHCOD"


def test_generate_referral_code_exhausts_retries(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5 回連続で衝突したら RuntimeError を投げる。"""
    _make_partner(db, "p1@example.com", "p1user", code="DUPLCODE")
    monkeypatch.setattr(code_generator, "_random_code", lambda: "DUPLCODE")

    with pytest.raises(RuntimeError):
        generate_referral_code(db)

    # MAX_RETRY 定数が想定どおり (テストの仕様確認)
    assert MAX_RETRY == 5
