# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_transactions_api.py
"""取引履歴APIのテスト。"""

import csv
import io
import os
import tempfile
from datetime import datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-transactions")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402


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
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={
            "email": email,
            "username": "admin",
            "password": "adminpassword123",
        },
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


SAMPLE_TX = {
    "user_id": 1,
    "operation": "SUPPLY",
    "asset": "USDC",
    "amount": "1000.000000000000000000",
    "amount_usd": "1000.00",
    "chain": "arbitrum_one",
    "status": "success",
}


class TestTransactionsAPI:
    def test_list_transactions_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/transactions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_list_transactions_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/transactions")
        assert r.status_code == 401

    def test_create_transaction_requires_admin(self, client: TestClient) -> None:
        admin_token = get_admin_token(client)
        client.post(
            "/users",
            json={
                "email": "viewer@test.com",
                "username": "viewer",
                "password": "viewerpassword123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        r = client.post(
            "/auth/login", json={"email": "viewer@test.com", "password": "viewerpassword123"}
        )
        viewer_token = r.json()["access_token"]
        r = client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403

    def test_create_transaction_success(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["operation"] == "SUPPLY"
        assert data["asset"] == "USDC"

    def test_list_transactions_after_create(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/transactions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_get_transaction_by_id(self, client: TestClient) -> None:
        token = get_admin_token(client)
        create_r = client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        tx_id = create_r.json()["id"]
        r = client.get(f"/api/transactions/{tx_id}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["id"] == tx_id

    def test_get_transaction_not_found(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/transactions/9999", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    def test_transaction_stats_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get("/api/transactions/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["total_count"] == 0
        assert data["success_count"] == 0

    def test_transaction_stats_with_data(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/transactions/stats", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["total_count"] == 1
        assert data["success_count"] == 1

    def test_admin_list_all_transactions(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/admin/transactions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_filter_by_operation(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/transactions?operation=SUPPLY",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert all(item["operation"] == "SUPPLY" for item in r.json()["items"])

    def test_filter_by_status(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/transactions?tx_status=success",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert all(item["status"] == "success" for item in r.json()["items"])

    def test_filter_by_chain(self, client: TestClient) -> None:
        token = get_admin_token(client)
        client.post(
            "/api/transactions",
            json=SAMPLE_TX,
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/transactions?chain=arbitrum_one",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert all(item["chain"] == "arbitrum_one" for item in r.json()["items"])


class TestTransactionsExportCSV:
    """GET /api/transactions/export のテスト。"""

    def _insert_executed_proposal(self, test_db, user_id: int, year: int = 2026) -> None:
        """テスト用の実行済み提案を DB に直接挿入する。"""
        from app.proposals.models import Proposal

        _, engine = test_db
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            proposal = Proposal(
                user_id=user_id,
                operation="SUPPLY",
                asset="USDC",
                amount="500.000000000000000000",
                amount_usd="500.00",
                reason="test export",
                status="executed",
                fee_amount="5.00",
                tx_hash="0xabcdef1234567890",
                executed_at=datetime(year, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
            )
            session.add(proposal)
            session.commit()

    def test_export_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/transactions/export")
        assert r.status_code == 401

    def test_export_empty(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get(
            "/api/transactions/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        rows = list(reader)
        assert rows == []

    def test_export_returns_csv_with_executed_proposals(self, client: TestClient, test_db) -> None:
        token = get_admin_token(client)
        self._insert_executed_proposal(test_db, user_id=1)
        r = client.get(
            "/api/transactions/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["操作"] == "SUPPLY"
        assert rows[0]["資産"] == "USDC"
        assert rows[0]["手数料(USD)"] == "5.00"
        assert rows[0]["TxHash"] == "0xabcdef1234567890"

    def test_export_year_filter_matches(self, client: TestClient, test_db) -> None:
        token = get_admin_token(client)
        self._insert_executed_proposal(test_db, user_id=1, year=2026)
        r = client.get(
            "/api/transactions/export?year=2026",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        assert len(list(reader)) == 1

    def test_export_year_filter_no_match(self, client: TestClient, test_db) -> None:
        token = get_admin_token(client)
        self._insert_executed_proposal(test_db, user_id=1, year=2026)
        r = client.get(
            "/api/transactions/export?year=2025",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        assert list(reader) == []

    def test_export_filename_includes_year(self, client: TestClient) -> None:
        token = get_admin_token(client)
        r = client.get(
            "/api/transactions/export?year=2026",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert 'filename="transactions_2026.csv"' in r.headers["content-disposition"]

    def test_export_does_not_include_other_user_proposals(
        self, client: TestClient, test_db
    ) -> None:
        token = get_admin_token(client)
        # user_id=99 (別ユーザー) の proposal を挿入
        self._insert_executed_proposal(test_db, user_id=99)
        r = client.get(
            "/api/transactions/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        assert list(reader) == []
