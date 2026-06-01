# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_non_custodial_f1f2.py
"""
non-custodial 方式2 F1/F2 テスト。

F1: AUTO_EXECUTION_ENABLED feature flag — approve_proposal が Aave 自動実行をスキップ
F2: submit_partner_tx の on-chain receipt 検証
"""

import os
import tempfile
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-f1f2")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "f1f2_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

VALID_TX_HASH = "0x" + "a" * 64
PARTNER_WALLET = "0x1234567890123456789012345678901234567890"
POOL_ADDRESS = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"  # Base Mainnet

SAMPLE_PROPOSAL = {
    "user_id": 1,
    "operation": "SUPPLY",
    "asset": "USDC",
    "amount": "500.000000000000000000",
    "amount_usd": "500.00",
    "reason": "non-custodial F1/F2 test",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "f1f2_admin@example.com")
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
    assert r.status_code == 201
    return r.json()["id"]


# ---------------------------------------------------------------------------
# F1: AUTO_EXECUTION_ENABLED feature flag
# ---------------------------------------------------------------------------


class TestF1AutoExecutionFlag:
    """approve_proposal に AUTO_EXECUTION_ENABLED=false で Aave 実行が行われないことを確認。"""

    def test_approve_with_flag_false_stays_approved(self, client: TestClient) -> None:
        """AUTO_EXECUTION_ENABLED=false では Aave 実行をスキップし status が approved のまま。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with patch.dict(os.environ, {"AUTO_EXECUTION_ENABLED": "false"}):
            r = client.post(
                f"/api/proposals/{proposal_id}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "approved"
        assert data["approved_at"] is not None

    def test_approve_default_env_stays_approved(self, client: TestClient) -> None:
        """AUTO_EXECUTION_ENABLED 未設定 (デフォルト false) でも approved のまま。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        env_without_flag = {k: v for k, v in os.environ.items() if k != "AUTO_EXECUTION_ENABLED"}
        with patch.dict(os.environ, env_without_flag, clear=True):
            r = client.post(
                f"/api/proposals/{proposal_id}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_approve_with_flag_true_attempts_aave_execution(self, client: TestClient) -> None:
        """AUTO_EXECUTION_ENABLED=true では Aave 実行を試みる (RPC 未設定で failed になる)。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with patch.dict(os.environ, {"AUTO_EXECUTION_ENABLED": "true"}):
            r = client.post(
                f"/api/proposals/{proposal_id}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200
        # Aave 実行を試みるが RPC 未設定のため executed か failed になる
        assert r.json()["status"] in ("executed", "failed")

    def test_submit_tx_works_regardless_of_auto_execution_flag(self, client: TestClient) -> None:
        """AUTO_EXECUTION_ENABLED=false でも submit_partner_tx は動作する。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with (
            patch.dict(os.environ, {"AUTO_EXECUTION_ENABLED": "false"}),
            patch(
                "app.proposals.router._verify_on_chain_receipt",
                return_value={"status": 1, "from": PARTNER_WALLET, "to": POOL_ADDRESS},
            ),
        ):
            r = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": VALID_TX_HASH, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "executed"
        assert data["tx_hash"] == VALID_TX_HASH


# ---------------------------------------------------------------------------
# F2: submit_partner_tx on-chain receipt 検証 (API レベル)
# ---------------------------------------------------------------------------


class TestF2SubmitTxReceiptVerification:
    """submit_partner_tx の on-chain receipt 検証テスト。"""

    def test_invalid_tx_hash_format_returns_422(self, client: TestClient) -> None:
        """形式不正の tx_hash は 422 を返す。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        for bad_hash in [
            "0x" + "g" * 64,  # 非16進文字
            "0x" + "a" * 63,  # 短すぎ
            "0x" + "a" * 65,  # 長すぎ
            "aa" * 32,  # 0x プレフィックスなし
        ]:
            r = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": bad_hash, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 422, f"expected 422 for hash={bad_hash!r}"

    def test_valid_receipt_executes_proposal(self, client: TestClient) -> None:
        """status=1 / from 一致 / to 一致の receipt → proposal が executed に遷移する。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with (
            patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "http://localhost:8545"}),
            patch(
                "app.proposals.router._verify_on_chain_receipt",
                return_value={"status": 1, "from": PARTNER_WALLET, "to": POOL_ADDRESS},
            ),
        ):
            r = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": VALID_TX_HASH, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "executed"
        assert data["tx_hash"] == VALID_TX_HASH
        assert data["executed_at"] is not None
        assert data["expected_from"] == PARTNER_WALLET
        assert data["expected_to"] == POOL_ADDRESS

    def test_reverted_tx_returns_400_and_stays_pending(self, client: TestClient) -> None:
        """status=0 (reverted) の receipt → 400 / proposal が pending のまま。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with (
            patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "http://localhost:8545"}),
            patch(
                "app.proposals.router._verify_on_chain_receipt",
                side_effect=ValueError("tx 0xaaaa... は reverted (status=0) です。"),
            ),
        ):
            r = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": VALID_TX_HASH, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 400
        assert "reverted" in r.json()["detail"]

        get_r = client.get(
            f"/api/proposals/{proposal_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_r.json()["status"] == "pending"

    def test_from_address_mismatch_returns_400(self, client: TestClient) -> None:
        """from アドレス不一致 → 400 を返す。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with (
            patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "http://localhost:8545"}),
            patch(
                "app.proposals.router._verify_on_chain_receipt",
                side_effect=ValueError(
                    "tx の from アドレスが一致しません: expected=0x123... actual=0x999..."
                ),
            ),
        ):
            r = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": VALID_TX_HASH, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 400
        assert "from" in r.json()["detail"]

    def test_pending_receipt_returns_400(self, client: TestClient) -> None:
        """receipt が pending (None) → 400 を返す。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with (
            patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "http://localhost:8545"}),
            patch(
                "app.proposals.router._verify_on_chain_receipt",
                side_effect=ValueError("tx 0xaaaa... は 60秒経過後も pending です。"),
            ),
        ):
            r = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": VALID_TX_HASH, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 400
        assert "pending" in r.json()["detail"]

    def test_rpc_unavailable_skips_verification_and_executes(self, client: TestClient) -> None:
        """RPC 未設定 (chain config エラー) → verification スキップして executed (fail-open)。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with patch(
            "app.aave.chains.get_rpc_url_for_chain",
            side_effect=ValueError("RPC URL が設定されていません"),
        ):
            r = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": VALID_TX_HASH, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "executed"

    def test_fake_tx_hash_does_not_execute_proposal(self, client: TestClient) -> None:
        """偽の tx_hash (receipt 検証失敗) → executed にならない。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        fake_hash = "0x" + "f" * 64

        # RPC URL を設定して検証パスを有効化し、_verify_on_chain_receipt が呼ばれることを確認
        with (
            patch.dict(os.environ, {"AAVE_RPC_URL_BASE": "http://localhost:8545"}),
            patch(
                "app.proposals.router._verify_on_chain_receipt",
                side_effect=ValueError("tx のステータスが invalid です。"),
            ),
        ):
            r = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": fake_hash, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 400

        get_r = client.get(
            f"/api/proposals/{proposal_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_r.json()["status"] != "executed"

    def test_double_submit_prevented(self, client: TestClient) -> None:
        """同一 proposal への 2 回目の submit-tx は 400 を返す。"""
        token = get_admin_token(client)
        proposal_id = create_proposal(client, token)

        with patch(
            "app.proposals.router._verify_on_chain_receipt",
            return_value={"status": 1, "from": PARTNER_WALLET, "to": POOL_ADDRESS},
        ):
            first = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": VALID_TX_HASH, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )
            second = client.post(
                f"/api/proposals/{proposal_id}/submit-tx",
                json={"tx_hash": VALID_TX_HASH, "wallet_address": PARTNER_WALLET},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert first.status_code == 200
        assert second.status_code == 400


# ---------------------------------------------------------------------------
# _verify_on_chain_receipt ユニットテスト (web3 モック)
# ---------------------------------------------------------------------------


class TestVerifyOnChainReceipt:
    """_verify_on_chain_receipt のユニットテスト。web3 モジュールを mock して外部通信なし。"""

    @staticmethod
    def _make_w3_mock(receipt_dict):
        """指定 receipt を返す Web3 インスタンスモックを生成する。"""
        mock_w3 = MagicMock()
        mock_w3.eth.get_transaction_receipt.return_value = receipt_dict
        return mock_w3

    def test_valid_receipt_returns_dict(self) -> None:
        from app.proposals.router import _verify_on_chain_receipt

        receipt = {"status": 1, "from": PARTNER_WALLET, "to": POOL_ADDRESS}

        with patch("web3.Web3") as MockWeb3:
            mock_w3 = self._make_w3_mock(receipt)
            MockWeb3.return_value = mock_w3
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_bytes = MagicMock(return_value=bytes.fromhex(VALID_TX_HASH[2:]))

            result = _verify_on_chain_receipt(
                tx_hash=VALID_TX_HASH,
                expected_from=PARTNER_WALLET,
                expected_to=POOL_ADDRESS,
                rpc_url="http://localhost:8545",
            )

        assert result["status"] == 1
        assert result["from"] == PARTNER_WALLET

    def test_reverted_receipt_raises_value_error(self) -> None:
        from app.proposals.router import _verify_on_chain_receipt

        receipt = {"status": 0, "from": PARTNER_WALLET, "to": POOL_ADDRESS}

        with (
            patch("web3.Web3") as MockWeb3,
            pytest.raises(ValueError, match="reverted"),
        ):
            mock_w3 = self._make_w3_mock(receipt)
            MockWeb3.return_value = mock_w3
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_bytes = MagicMock(return_value=bytes.fromhex(VALID_TX_HASH[2:]))
            _verify_on_chain_receipt(
                tx_hash=VALID_TX_HASH,
                expected_from=PARTNER_WALLET,
                expected_to=POOL_ADDRESS,
                rpc_url="http://localhost:8545",
            )

    def test_pending_receipt_raises_after_timeout(self) -> None:
        from app.proposals.router import _verify_on_chain_receipt

        with (
            patch("web3.Web3") as MockWeb3,
            patch("time.sleep"),  # sleep を skip して高速実行
            pytest.raises(ValueError, match="pending"),
        ):
            mock_w3 = self._make_w3_mock(None)  # pending: always None
            MockWeb3.return_value = mock_w3
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_bytes = MagicMock(return_value=bytes.fromhex(VALID_TX_HASH[2:]))
            _verify_on_chain_receipt(
                tx_hash=VALID_TX_HASH,
                expected_from=PARTNER_WALLET,
                expected_to=POOL_ADDRESS,
                rpc_url="http://localhost:8545",
                poll_interval=1.0,
                max_wait=2.0,
            )

    def test_from_mismatch_raises_value_error(self) -> None:
        from app.proposals.router import _verify_on_chain_receipt

        wrong_wallet = "0x" + "9" * 40
        receipt = {"status": 1, "from": wrong_wallet, "to": POOL_ADDRESS}

        with (
            patch("web3.Web3") as MockWeb3,
            pytest.raises(ValueError, match="from"),
        ):
            mock_w3 = self._make_w3_mock(receipt)
            MockWeb3.return_value = mock_w3
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_bytes = MagicMock(return_value=bytes.fromhex(VALID_TX_HASH[2:]))
            _verify_on_chain_receipt(
                tx_hash=VALID_TX_HASH,
                expected_from=PARTNER_WALLET,
                expected_to=POOL_ADDRESS,
                rpc_url="http://localhost:8545",
            )

    def test_to_mismatch_raises_value_error(self) -> None:
        from app.proposals.router import _verify_on_chain_receipt

        wrong_to = "0x" + "8" * 40
        receipt = {"status": 1, "from": PARTNER_WALLET, "to": wrong_to}

        with (
            patch("web3.Web3") as MockWeb3,
            pytest.raises(ValueError, match="to"),
        ):
            mock_w3 = self._make_w3_mock(receipt)
            MockWeb3.return_value = mock_w3
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_bytes = MagicMock(return_value=bytes.fromhex(VALID_TX_HASH[2:]))
            _verify_on_chain_receipt(
                tx_hash=VALID_TX_HASH,
                expected_from=PARTNER_WALLET,
                expected_to=POOL_ADDRESS,
                rpc_url="http://localhost:8545",
            )
