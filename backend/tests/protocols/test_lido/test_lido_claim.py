# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Lido claim フロー（service / client / DummyClient）のユニットテスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.protocols.base import TransactionResult
from app.protocols.lido.client import DummyLidoClient, LidoClient
from app.protocols.lido.config import LidoConfig
from app.protocols.lido.schemas import LidoClaimRequest
from app.protocols.lido.service import LidoService


@pytest.fixture
def config() -> LidoConfig:
    return LidoConfig(sandbox=True, peg_deviation_warn_pct=2.0)


@pytest.fixture
def dummy_client(config: LidoConfig) -> DummyLidoClient:
    return DummyLidoClient(config)


# ---------------------------------------------------------------------------
# LidoService.claim — service 層テスト
# ---------------------------------------------------------------------------


class TestLidoServiceClaim:
    """LidoService.claim のテスト。"""

    @pytest.mark.asyncio
    async def test_claim_dry_run_returns_no_tx_hash(self, config: LidoConfig) -> None:
        """dry_run=True（デフォルト）の場合 tx_hash=None が返ること。"""
        mock_client = AsyncMock()
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_id=1)

        response = await svc.claim(req)

        assert response.dry_run is True
        assert response.tx_hash is None
        assert response.operation == "CLAIM"
        assert response.request_id == 1
        mock_client.claim_withdrawal.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_dry_run_default_is_true(self, config: LidoConfig) -> None:
        """LidoClaimRequest の dry_run デフォルトが True であること。"""
        req = LidoClaimRequest(request_id=42)
        assert req.dry_run is True

    @pytest.mark.asyncio
    async def test_claim_real_success(self, config: LidoConfig) -> None:
        """dry_run=False で claim が正常に実行されること。"""
        mock_client = AsyncMock()
        mock_client.claim_withdrawal.return_value = TransactionResult(
            success=True,
            tx_hash="0x" + "ab" * 32,
            amount=Decimal("0"),
        )
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_id=5, dry_run=False)

        response = await svc.claim(req)

        assert response.dry_run is False
        assert response.tx_hash == "0x" + "ab" * 32
        assert response.operation == "CLAIM"
        assert response.request_id == 5
        mock_client.claim_withdrawal.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_claim_real_failure_raises_runtime_error(self, config: LidoConfig) -> None:
        """claim 失敗時に RuntimeError を発生させること。"""
        mock_client = AsyncMock()
        mock_client.claim_withdrawal.return_value = TransactionResult(
            success=False,
            tx_hash=None,
            amount=Decimal("0"),
            error="リクエストが finalized されていません",
        )
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_id=10, dry_run=False)

        with pytest.raises(RuntimeError, match="Lido クレーム失敗"):
            await svc.claim(req)

    @pytest.mark.asyncio
    async def test_claim_real_passes_request_id(self, config: LidoConfig) -> None:
        """claim が正しい request_id を client.claim_withdrawal に渡すこと。"""
        mock_client = AsyncMock()
        mock_client.claim_withdrawal.return_value = TransactionResult(
            success=True, tx_hash="0x" + "00" * 32, amount=Decimal("0")
        )
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_id=99, dry_run=False)

        await svc.claim(req)

        mock_client.claim_withdrawal.assert_awaited_once_with(99)


# ---------------------------------------------------------------------------
# DummyLidoClient.claim_withdrawal — スタブ動作確認
# ---------------------------------------------------------------------------


class TestDummyLidoClientClaim:
    """DummyLidoClient.claim_withdrawal / get_withdrawal_requests のテスト。"""

    @pytest.mark.asyncio
    async def test_claim_withdrawal_returns_success(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient.claim_withdrawal は成功を返すこと。"""
        result = await dummy_client.claim_withdrawal(request_id=1)
        assert result.success is True
        assert result.tx_hash is not None
        assert result.tx_hash.startswith("0x")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_claim_withdrawal_no_real_write(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient.claim_withdrawal は on-chain write を起こさないこと。"""
        # web3 の send_raw_transaction が呼ばれないことを確認
        with patch("web3.Web3") as mock_web3:
            result = await dummy_client.claim_withdrawal(request_id=1)
        mock_web3.assert_not_called()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_claim_withdrawal_tx_hash_format(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient の tx_hash が 0x プレフィックスを持つこと。"""
        result = await dummy_client.claim_withdrawal(request_id=7)
        assert result.tx_hash is not None
        assert result.tx_hash.startswith("0x")
        assert len(result.tx_hash) == 66  # 0x + 64 hex chars

    @pytest.mark.asyncio
    async def test_get_withdrawal_requests_returns_list(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """DummyLidoClient.get_withdrawal_requests は int のリストを返すこと。"""
        result = await dummy_client.get_withdrawal_requests("0x1234")
        assert isinstance(result, list)
        assert all(isinstance(r, int) for r in result)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_get_withdrawal_requests_no_real_call(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """DummyLidoClient.get_withdrawal_requests は on-chain call を起こさないこと。"""
        with patch("web3.Web3") as mock_web3:
            result = await dummy_client.get_withdrawal_requests("0x1234")
        mock_web3.assert_not_called()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# LidoClient.claim_withdrawal — web3 mock で実装テスト
# ---------------------------------------------------------------------------


class TestLidoClientClaimWithdrawal:
    """LidoClient.claim_withdrawal の web3 mock テスト。"""

    @pytest.fixture
    def real_client(self) -> LidoClient:
        return LidoClient(
            LidoConfig(
                sandbox=False,
                wallet_private_key="0x" + "aa" * 32,
                wallet_address="0x" + "bb" * 20,
            )
        )

    def _make_mock_w3(self, tx_status: int) -> MagicMock:
        """web3 モックを構築する。tx_status: 1=成功, 0=失敗。"""
        mock_w3 = MagicMock()
        mock_account = MagicMock()
        mock_account.address = "0x" + "bb" * 20
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 10_000_000_000
        mock_w3.eth.to_checksum_address = lambda x: x

        mock_signed = MagicMock()
        mock_signed.raw_transaction = b"\x00" * 32
        mock_w3.eth.account.sign_transaction.return_value = mock_signed

        fake_tx_hash = b"\xde\xad" + b"\x00" * 30
        mock_w3.eth.send_raw_transaction.return_value = fake_tx_hash
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": tx_status}

        mock_contract = MagicMock()
        mock_fn = MagicMock()
        mock_fn.build_transaction.return_value = {"from": mock_account.address}
        mock_contract.functions.claimWithdrawal.return_value = mock_fn
        mock_w3.eth.contract.return_value = mock_contract
        mock_w3.to_checksum_address = MagicMock(side_effect=lambda x: x)

        return mock_w3

    @pytest.mark.asyncio
    async def test_claim_withdrawal_status_1_returns_success(self, real_client: LidoClient) -> None:
        """status=1 のとき success=True を返すこと。"""
        mock_w3 = self._make_mock_w3(tx_status=1)
        real_client._w3 = mock_w3
        real_client._contract = MagicMock()
        real_client._initialized = True

        result = await real_client.claim_withdrawal(request_id=1)

        assert result.success is True
        assert result.tx_hash is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawal_status_0_returns_failure(self, real_client: LidoClient) -> None:
        """status=0 のとき success=False を返すこと。"""
        mock_w3 = self._make_mock_w3(tx_status=0)
        real_client._w3 = mock_w3
        real_client._contract = MagicMock()
        real_client._initialized = True

        result = await real_client.claim_withdrawal(request_id=2)

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawal_exception_fail_open(self, real_client: LidoClient) -> None:
        """例外発生時に fail-open（success=False）で返すこと。"""
        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.side_effect = Exception("接続エラー")
        real_client._w3 = mock_w3
        real_client._contract = MagicMock()
        real_client._initialized = True

        result = await real_client.claim_withdrawal(request_id=3)

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawal_no_private_key_returns_failure(
        self, config: LidoConfig
    ) -> None:
        """LIDO_WALLET_PRIVATE_KEY 未設定時に success=False を返すこと。"""
        client = LidoClient(LidoConfig(sandbox=False, wallet_private_key=""))
        client._initialized = True
        client._w3 = MagicMock()
        client._contract = MagicMock()

        result = await client.claim_withdrawal(request_id=1)

        assert result.success is False
        assert "LIDO_WALLET_PRIVATE_KEY" in (result.error or "")

    @pytest.mark.asyncio
    async def test_claim_withdrawal_uses_decimal_not_float(self, real_client: LidoClient) -> None:
        """TransactionResult.amount が Decimal 型であること（float 混入なし）。"""
        mock_w3 = self._make_mock_w3(tx_status=1)
        real_client._w3 = mock_w3
        real_client._contract = MagicMock()
        real_client._initialized = True

        result = await real_client.claim_withdrawal(request_id=1)

        assert type(result.amount) is Decimal
