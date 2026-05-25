# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/legal/test_models.py
"""Tests for app.legal.models.TosConsent (P0-14 schema)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.auth.models import User  # noqa: F401  (must be imported so users table exists)
from app.database import Base
from app.legal.models import TosConsent


def _make_engine_with_minimal_users() -> tuple[Engine, int]:
    """In-memory SQLite engine with only the columns this test needs.

    The real ``users`` table has many domain-specific NOT NULL columns whose
    requirements drift over time. To keep this schema test resilient, we use a
    minimal mock ``users`` table (id only) and rely on the FK shape of
    ``tos_consents`` rather than on the full User model.
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
    # Create only tos_consents from the metadata (skip the full ``users`` table).
    Base.metadata.tables["tos_consents"].create(engine)
    # Insert a stub user row to satisfy the FK in the assertions below.
    with engine.begin() as conn:
        result = conn.execute(text("INSERT INTO users DEFAULT VALUES"))
        user_id = int(result.lastrowid or 0)
    return engine, user_id


def test_table_metadata_present() -> None:
    """tos_consents table is registered on the shared metadata."""
    assert "tos_consents" in Base.metadata.tables
    table = Base.metadata.tables["tos_consents"]
    cols = {c.name for c in table.columns}
    assert {
        "id",
        "user_id",
        "tos_version",
        "consent_hash",
        "consented_at",
        "ip",
        "ua",
        "withdrawn_at",
    } <= cols


def test_unique_constraint_user_version_present() -> None:
    table = Base.metadata.tables["tos_consents"]
    uc_names = {c.name for c in table.constraints if c.name}
    assert "uq_tos_consents_user_version" in uc_names


def test_insert_and_query_in_sqlite() -> None:
    """Round-trip insert/query against an in-memory SQLite (no Postgres required)."""
    engine, user_id = _make_engine_with_minimal_users()

    with Session(engine) as session:
        consent = TosConsent(
            user_id=user_id,
            tos_version="2026-05-25",
            consent_hash="a" * 64,
            consented_at=datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc),
            ip="203.0.113.1",
            ua="Mozilla/5.0",
        )
        session.add(consent)
        session.commit()
        session.refresh(consent)

        assert consent.id is not None
        assert consent.user_id == user_id
        assert consent.withdrawn_at is None
        assert "TosConsent" in repr(consent)


def test_withdraw_flag_set_when_non_null() -> None:
    engine, user_id = _make_engine_with_minimal_users()

    with Session(engine) as session:
        consent = TosConsent(
            user_id=user_id,
            tos_version="2026-05-25",
            consent_hash="b" * 64,
            withdrawn_at=datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc),
        )
        session.add(consent)
        session.commit()
        session.refresh(consent)
        assert consent.withdrawn_at is not None
        # repr exposes the withdrawn=True flag
        assert "withdrawn=True" in repr(consent)
