# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_cryptact_csv.py
"""Cryptact CSV エンドポイントのテスト。"""

import csv
import io
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cryptact")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "csv_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db):
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture()
def client_with_proposals(test_db):
    override_get_db, engine = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    # executed 状態の提案を直接 DB に挿入
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    proposals = [
        Proposal(
            user_id=1,
            operation="SUPPLY",
            asset="USDC",
            amount=Decimal("1000.000000000000000000"),
            amount_usd=Decimal("1000.00"),
            reason="test supply",
            status="executed",
            fee_amount=Decimal("0.50"),
            executed_at=datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc),
        ),
        Proposal(
            user_id=1,
            operation="WITHDRAW",
            asset="USDC",
            amount=Decimal("500.000000000000000000"),
            amount_usd=Decimal("500.00"),
            reason="test withdraw",
            status="executed",
            fee_amount=None,
            executed_at=datetime(2026, 4, 20, 5, 30, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 4, 23, 5, 30, 0, tzinfo=timezone.utc),
        ),
        Proposal(
            user_id=1,
            operation="SUPPLY",
            asset="WBTC",
            amount=Decimal("0.01"),
            amount_usd=Decimal("600.00"),
            reason="pending proposal",
            status="pending",
            expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        ),
    ]
    for p in proposals:
        db.add(p)
    db.commit()
    db.close()

    return TestClient(app)


def _get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "csv_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "csv_admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


class TestCryptactCsvEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/proposals/tax/cryptact-csv")
        assert r.status_code == 401

    def test_returns_csv_content_type(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    def test_csv_header_row(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        content = r.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        assert reader.fieldnames == [
            "Timestamp",
            "Action",
            "Source",
            "Base",
            "Volume",
            "Price",
            "Counter",
            "Fee",
            "FeeCcy",
        ]

    def test_only_executed_proposals_included(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        content = r.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        # pending は含まれない
        assert len(rows) == 2

    def test_supply_maps_to_lending(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        content = r.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        supply_row = next(
            row for row in rows if row["Base"] == "USDC" and row["Action"] == "LENDING"
        )
        assert supply_row["Action"] == "LENDING"
        assert supply_row["Source"] == "AAVE_V3"
        assert supply_row["Counter"] == "USD"
        assert supply_row["Fee"] == "0.50"
        assert supply_row["FeeCcy"] == "USD"

    def test_withdraw_maps_to_unlending(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        content = r.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        withdraw_row = next(row for row in rows if row["Action"] == "UNLENDING")
        assert withdraw_row["Action"] == "UNLENDING"
        assert withdraw_row["Fee"] == "0"  # fee_amount=None → "0"

    def test_timestamp_format_jst(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        content = r.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        # UTC 10:00 → JST 19:00
        supply_row = next(row for row in rows if row["Action"] == "LENDING")
        assert supply_row["Timestamp"] == "2026/03/15 19:00:00"

    def test_year_filter(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv?year=2026",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        content = r.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 2

    def test_year_filter_no_match(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv?year=2025",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        content = r.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 0

    def test_content_disposition_header(self, client_with_proposals: TestClient) -> None:
        token = _get_admin_token(client_with_proposals)
        r = client_with_proposals.get(
            "/api/proposals/tax/cryptact-csv?year=2026",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert "attachment" in r.headers["content-disposition"]
        assert "cryptact_aave_2026.csv" in r.headers["content-disposition"]

    def test_empty_result_only_header(self, client: TestClient) -> None:
        token = _get_admin_token(client)
        r = client.get(
            "/api/proposals/tax/cryptact-csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        content = r.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert rows == []
