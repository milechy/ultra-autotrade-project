# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_slice3b_scw_routing.py
"""slice3b: Smart Wallet (AA) ユーザーの build-tx / submit-tx 経路分岐テスト。

- submit-tx: smart_wallet_address 設定済 → bundler の verify_userop_receipt 経路、
  未設定 → 従来 _verify_on_chain_receipt 経路。
- build-tx: smart_wallet_address 設定済 → onBehalfOf/to を SCW アドレスで構築。

設計: docs/privy-aa-paymaster-design.md §6.2 スライス3b。
"""

import os
import tempfile
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-slice3b")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "slice3b_admin@example.com")

from app.auth.models import User  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.proposals.userop_verify import UserOpVerificationError  # noqa: E402

SCW_ADDRESS = "0x" + "5c" * 20
EOA_WALLET = "0x1234567890123456789012345678901234567890"
VALID_HASH = "0x" + "a" * 64

SAMPLE_PROPOSAL = {
    "user_id": 1,
    "operation": "SUPPLY",
    "asset": "USDC",
    "amount": "500.000000000000000000",
    "amount_usd": "500.00",
    "reason": "slice3b routing test",
}


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

    yield override_get_db, SessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "slice3b_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


def create_proposal(client: TestClient, token: str) -> int:
    r = client.post(
        "/api/proposals",
        json=SAMPLE_PROPOSAL,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def set_smart_wallet(session_local, user_id: int, addr: str) -> None:
    db = session_local()
    try:
        db.execute(update(User).where(User.id == user_id).values(smart_wallet_address=addr))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# submit-tx 経路分岐
# ---------------------------------------------------------------------------


class TestSubmitTxScwRouting:
    def test_scw_user_routes_to_userop_verify(self, client: TestClient, test_db) -> None:
        """smart_wallet_address 設定済ユーザーは verify_userop_receipt(sender=SCW) で検証される。"""
        _, SessionLocal = test_db
        token = get_admin_token(client)
        pid = create_proposal(client, token)
        set_smart_wallet(SessionLocal, 1, SCW_ADDRESS)

        with (
            patch.dict(os.environ, {"BUNDLER_RPC_URL": "http://bundler"}),
            patch(
                "app.proposals.userop_verify.verify_userop_receipt",
                return_value={"success": True, "sender": SCW_ADDRESS},
            ) as m,
        ):
            r = client.post(
                f"/api/proposals/{pid}/submit-tx",
                json={"tx_hash": VALID_HASH, "wallet_address": EOA_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "executed"
        assert (data["expected_from"] or "").lower() == SCW_ADDRESS.lower()
        m.assert_called_once()
        assert m.call_args.kwargs["expected_sender"] == SCW_ADDRESS

    def test_scw_user_without_bundler_url_returns_503(self, client: TestClient, test_db) -> None:
        """smart_wallet ユーザーで BUNDLER_RPC_URL 未設定なら 503 (検証不可で fail-closed)。"""
        _, SessionLocal = test_db
        token = get_admin_token(client)
        pid = create_proposal(client, token)
        set_smart_wallet(SessionLocal, 1, SCW_ADDRESS)

        env_without = {k: v for k, v in os.environ.items() if k != "BUNDLER_RPC_URL"}
        with patch.dict(os.environ, env_without, clear=True):
            r = client.post(
                f"/api/proposals/{pid}/submit-tx",
                json={"tx_hash": VALID_HASH, "wallet_address": EOA_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 503, r.text

    def test_scw_user_userop_verify_failure_returns_400(self, client: TestClient, test_db) -> None:
        """verify_userop_receipt が失敗を投げたら 400 (fail-closed)。"""
        _, SessionLocal = test_db
        token = get_admin_token(client)
        pid = create_proposal(client, token)
        set_smart_wallet(SessionLocal, 1, SCW_ADDRESS)

        with (
            patch.dict(os.environ, {"BUNDLER_RPC_URL": "http://bundler"}),
            patch(
                "app.proposals.userop_verify.verify_userop_receipt",
                side_effect=UserOpVerificationError("sender mismatch"),
            ),
        ):
            r = client.post(
                f"/api/proposals/{pid}/submit-tx",
                json={"tx_hash": VALID_HASH, "wallet_address": EOA_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 400, r.text

    def test_eoa_user_does_not_use_userop_verify(self, client: TestClient) -> None:
        """smart_wallet_address 未設定 (EOA) は verify_userop_receipt を呼ばない。"""
        token = get_admin_token(client)
        pid = create_proposal(client, token)

        with (
            patch(
                "app.proposals.router._verify_on_chain_receipt",
                return_value={"status": 1, "from": EOA_WALLET, "to": EOA_WALLET},
            ),
            patch("app.proposals.userop_verify.verify_userop_receipt") as m_uop,
        ):
            r = client.post(
                f"/api/proposals/{pid}/submit-tx",
                json={"tx_hash": VALID_HASH, "wallet_address": EOA_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "executed"
        m_uop.assert_not_called()


# ---------------------------------------------------------------------------
# build-tx onBehalfOf → SCW
# ---------------------------------------------------------------------------


class TestBuildTxScwWallet:
    def test_build_tx_scw_uses_smart_wallet_address(self, client: TestClient, test_db) -> None:
        """smart_wallet 設定済ユーザーの build-tx は SCW アドレスで calldata を構築する。"""
        _, SessionLocal = test_db
        token = get_admin_token(client)
        pid = create_proposal(client, token)
        set_smart_wallet(SessionLocal, 1, SCW_ADDRESS)

        captured: dict[str, str] = {}

        def fake_build_deposit_txs(*, asset_symbol, amount, wallet_address):
            captured["wallet_address"] = wallet_address
            tx = {
                "to": EOA_WALLET,
                "data": "0x",
                "from": wallet_address,
                "chainId": 8453,
                "value": "0x0",
            }
            return {"approve_tx": tx, "supply_tx": tx}

        mock_client = MagicMock()
        mock_client.build_deposit_txs.side_effect = fake_build_deposit_txs
        mock_service = MagicMock()
        mock_service._client = mock_client
        mock_service._settings.default_asset_symbol = "USDC"
        mock_multi = MagicMock()
        mock_multi.get_service.return_value = mock_service

        with (
            patch("app.aave.service.MultiChainAaveService", return_value=mock_multi),
            patch("app.aave.client.verify_supply_onbehalf", return_value=True),
        ):
            r = client.get(
                f"/api/proposals/{pid}/build-tx",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200, r.text
        # build_deposit_txs に渡った wallet が SCW であること（onBehalfOf=SCW）。
        assert captured["wallet_address"].lower() == SCW_ADDRESS.lower()
        assert r.json()["wallet_address"].lower() == SCW_ADDRESS.lower()
