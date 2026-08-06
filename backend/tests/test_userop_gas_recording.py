# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_userop_gas_recording.py
"""submit-tx (Smart Wallet/AA 経路) が bundler の UserOp receipt から実ガス代
(actualGasCost/actualGasUsed/paymaster) を取り出し Transaction に記録することの検証。

真因: verify_userop_receipt() の戻り値 (actualGasCost 等) が submit-tx 側で
捨てられており、実ガス代が1件も記録されていなかった (費目は $0.27/トレード固定値のみ)。
本テストは取得成功 / 取得失敗 (fail-open) / 値なし の3ケースを検証する。

設計: docs/privy-aa-paymaster-design.md §6.2。
"""

import os
import tempfile
from decimal import Decimal
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-userop-gas")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "userop_gas_admin@example.com")

from app.auth.models import User  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.proposals.router import _extract_userop_gas_fields  # noqa: E402
from app.transactions.models import Transaction  # noqa: E402

SCW_ADDRESS = "0x" + "5c" * 20
EOA_WALLET = "0x1234567890123456789012345678901234567890"
VALID_HASH = "0x" + "a" * 64
ZERO_ADDRESS = "0x" + "0" * 40
PAYMASTER_ADDRESS = "0x" + "9a" * 20

SAMPLE_PROPOSAL = {
    "user_id": 1,
    "operation": "SUPPLY",
    "asset": "USDC",
    "amount": "500.000000000000000000",
    "amount_usd": "500.00",
    "reason": "userop gas recording test",
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
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "userop_gas_admin@example.com")
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


def _submit_tx(client: TestClient, token: str, pid: int, userop_receipt: dict) -> object:
    with (
        patch.dict(os.environ, {"BUNDLER_RPC_URL": "http://bundler"}),
        patch(
            "app.proposals.userop_verify.verify_userop_receipt",
            return_value=userop_receipt,
        ),
    ):
        return client.post(
            f"/api/proposals/{pid}/submit-tx",
            json={"tx_hash": VALID_HASH, "wallet_address": EOA_WALLET},
            headers={"Authorization": f"Bearer {token}"},
        )


class TestSubmitTxRecordsActualGasCost:
    def test_gas_cost_recorded_when_receipt_has_actual_gas_fields(
        self, client: TestClient, test_db
    ) -> None:
        """actualGasUsed/actualGasCost/paymaster が揃っている場合、実ガス代が記録される。"""
        _, SessionLocal = test_db
        token = get_admin_token(client)
        pid = create_proposal(client, token)
        set_smart_wallet(SessionLocal, 1, SCW_ADDRESS)

        gas_used_units = 100_000
        price_gwei = Decimal(20)
        gas_cost_wei = int(gas_used_units * price_gwei * Decimal("1000000000"))

        r = _submit_tx(
            client,
            token,
            pid,
            {
                "success": True,
                "sender": SCW_ADDRESS,
                "actualGasUsed": hex(gas_used_units),
                "actualGasCost": hex(gas_cost_wei),
                "paymaster": ZERO_ADDRESS,
            },
        )

        assert r.status_code == 200, r.text
        db = SessionLocal()
        try:
            tx = db.query(Transaction).filter(Transaction.tx_hash == VALID_HASH).one()
            assert tx.gas_used == Decimal(gas_used_units)
            assert tx.gas_price_gwei == price_gwei
            # paymaster がゼロアドレス → スポンサーなし (ユーザー自己負担)
            assert tx.gas_sponsored is False
        finally:
            db.close()

    def test_gas_sponsored_true_when_paymaster_nonzero(self, client: TestClient, test_db) -> None:
        """paymaster が非ゼロアドレスなら gas_sponsored=True (スポンサー負担) と記録される。"""
        _, SessionLocal = test_db
        token = get_admin_token(client)
        pid = create_proposal(client, token)
        set_smart_wallet(SessionLocal, 1, SCW_ADDRESS)

        r = _submit_tx(
            client,
            token,
            pid,
            {
                "success": True,
                "sender": SCW_ADDRESS,
                "actualGasUsed": hex(50_000),
                "actualGasCost": hex(10**15),
                "paymaster": PAYMASTER_ADDRESS,
            },
        )

        assert r.status_code == 200, r.text
        db = SessionLocal()
        try:
            tx = db.query(Transaction).filter(Transaction.tx_hash == VALID_HASH).one()
            assert tx.gas_sponsored is True
        finally:
            db.close()

    def test_missing_gas_fields_is_fail_open_no_regression(
        self, client: TestClient, test_db
    ) -> None:
        """actualGasUsed/actualGasCost が receipt に無くても submit-tx は成功し続ける (fail-open)。"""
        _, SessionLocal = test_db
        token = get_admin_token(client)
        pid = create_proposal(client, token)
        set_smart_wallet(SessionLocal, 1, SCW_ADDRESS)

        r = _submit_tx(
            client,
            token,
            pid,
            {"success": True, "sender": SCW_ADDRESS},
        )

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "executed"
        db = SessionLocal()
        try:
            tx = db.query(Transaction).filter(Transaction.tx_hash == VALID_HASH).one()
            assert tx.gas_used is None
            assert tx.gas_price_gwei is None
            assert tx.gas_sponsored is None
        finally:
            db.close()


class TestExtractUseropGasFieldsUnit:
    """_extract_userop_gas_fields の単体テスト (取得成功 / 取得失敗 / 値なしの3ケース網羅)。"""

    def test_success_case_computes_gas_price_gwei(self) -> None:
        gas_used, gas_price_gwei, gas_sponsored = _extract_userop_gas_fields(
            {
                "actualGasUsed": hex(100_000),
                "actualGasCost": hex(int(100_000 * 20 * 1_000_000_000)),
                "paymaster": ZERO_ADDRESS,
            }
        )
        assert gas_used == Decimal(100_000)
        assert gas_price_gwei == Decimal(20)
        assert gas_sponsored is False

    def test_missing_fields_returns_all_none(self) -> None:
        assert _extract_userop_gas_fields({}) == (None, None, None)

    def test_malformed_hex_returns_all_none_fail_open(self) -> None:
        assert _extract_userop_gas_fields(
            {"actualGasUsed": "not-hex", "actualGasCost": hex(1)}
        ) == (None, None, None)

    def test_zero_gas_used_returns_all_none(self) -> None:
        assert _extract_userop_gas_fields({"actualGasUsed": hex(0), "actualGasCost": hex(0)}) == (
            None,
            None,
            None,
        )

    def test_paymaster_absent_gives_none_sponsored(self) -> None:
        _, _, gas_sponsored = _extract_userop_gas_fields(
            {"actualGasUsed": hex(1), "actualGasCost": hex(1)}
        )
        assert gas_sponsored is None
