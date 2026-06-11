# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Lido claim フロー（service / client / DummyClient）のユニットテスト。

#621 checkpoint-hints 方式統合後の複数形 claim_withdrawals / get_withdrawal_status テスト。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.protocols.lido.client import DummyLidoClient, LidoClient
from app.protocols.lido.config import LidoConfig
from app.protocols.lido.schemas import ClaimWithdrawalResult, LidoClaimRequest, WithdrawalStatus
from app.protocols.lido.service import LidoService


@pytest.fixture
def config() -> LidoConfig:
    return LidoConfig(sandbox=True, peg_deviation_warn_pct=2.0)


@pytest.fixture
def dummy_client(config: LidoConfig) -> DummyLidoClient:
    return DummyLidoClient(config)


# ---------------------------------------------------------------------------
# LidoService.claim — service 層テスト（複数形 request_ids / hints 方式）
# ---------------------------------------------------------------------------


class TestLidoServiceClaim:
    """LidoService.claim のテスト。"""

    @pytest.mark.asyncio
    async def test_claim_dry_run_returns_no_tx_hash(self, config: LidoConfig) -> None:
        """dry_run=True（デフォルト）の場合 tx_hash=None が返ること。"""
        mock_client = AsyncMock()
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[1, 2])

        response = await svc.claim(req)

        assert response.dry_run is True
        assert response.tx_hash is None
        assert response.operation == "CLAIM"
        assert response.request_ids == [1, 2]
        mock_client.claim_withdrawals.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_dry_run_default_is_true(self, config: LidoConfig) -> None:
        """LidoClaimRequest の dry_run デフォルトが True であること。"""
        req = LidoClaimRequest(request_ids=[42])
        assert req.dry_run is True

    @pytest.mark.asyncio
    async def test_claim_real_success(self, config: LidoConfig) -> None:
        """dry_run=False で claim が正常に実行されること。"""
        mock_client = AsyncMock()
        mock_client.claim_withdrawals.return_value = ClaimWithdrawalResult(
            success=True,
            tx_hash="0x" + "ab" * 32,
            claimed_request_ids=[5, 6],
        )
        mock_client.get_withdrawal_status.return_value = [
            WithdrawalStatus(
                request_id=5,
                amount_of_steth=Decimal("1.0"),
                amount_of_shares=Decimal("1.0"),
                owner="0x1234",
                timestamp=1000,
                is_finalized=True,
                is_claimed=False,
            ),
            WithdrawalStatus(
                request_id=6,
                amount_of_steth=Decimal("0.5"),
                amount_of_shares=Decimal("0.5"),
                owner="0x1234",
                timestamp=1000,
                is_finalized=True,
                is_claimed=False,
            ),
        ]
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[5, 6], dry_run=False)

        response = await svc.claim(req)

        assert response.dry_run is False
        assert response.tx_hash == "0x" + "ab" * 32
        assert response.operation == "CLAIM"
        assert response.request_ids == [5, 6]
        mock_client.claim_withdrawals.assert_awaited_once_with([5, 6])

    @pytest.mark.asyncio
    async def test_claim_real_claimed_eth_is_sum_of_steth(self, config: LidoConfig) -> None:
        """claimed_eth が get_withdrawal_status の amount_of_steth 合算であること。"""
        mock_client = AsyncMock()
        mock_client.claim_withdrawals.return_value = ClaimWithdrawalResult(
            success=True,
            tx_hash="0x" + "ab" * 32,
            claimed_request_ids=[1, 2],
        )
        mock_client.get_withdrawal_status.return_value = [
            WithdrawalStatus(
                request_id=1,
                amount_of_steth=Decimal("1.0"),
                amount_of_shares=Decimal("1.0"),
                owner="0x1234",
                timestamp=1000,
                is_finalized=True,
                is_claimed=False,
            ),
            WithdrawalStatus(
                request_id=2,
                amount_of_steth=Decimal("2.5"),
                amount_of_shares=Decimal("2.5"),
                owner="0x1234",
                timestamp=1000,
                is_finalized=True,
                is_claimed=False,
            ),
        ]
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[1, 2], dry_run=False)

        response = await svc.claim(req)

        assert response.claimed_eth == Decimal("3.5")
        assert type(response.claimed_eth) is Decimal

    @pytest.mark.asyncio
    async def test_claim_real_failure_raises_runtime_error(self, config: LidoConfig) -> None:
        """claim 失敗時に RuntimeError を発生させること。"""
        mock_client = AsyncMock()
        mock_client.get_withdrawal_status.return_value = [
            WithdrawalStatus(
                request_id=10,
                amount_of_steth=Decimal("1.0"),
                amount_of_shares=Decimal("1.0"),
                owner="0x1234",
                timestamp=1000,
                is_finalized=True,
                is_claimed=False,
            ),
        ]
        mock_client.claim_withdrawals.return_value = ClaimWithdrawalResult(
            success=False,
            tx_hash=None,
            error="リクエストが finalized されていません",
        )
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[10], dry_run=False)

        with pytest.raises(RuntimeError, match="Lido クレーム失敗"):
            await svc.claim(req)

    @pytest.mark.asyncio
    async def test_claim_real_passes_request_ids(self, config: LidoConfig) -> None:
        """claim が正しい request_ids を client.claim_withdrawals に渡すこと。"""
        mock_client = AsyncMock()
        mock_client.get_withdrawal_status.return_value = [
            WithdrawalStatus(
                request_id=99,
                amount_of_steth=Decimal("1.0"),
                amount_of_shares=Decimal("1.0"),
                owner="0x1234",
                timestamp=1000,
                is_finalized=True,
                is_claimed=False,
            ),
            WithdrawalStatus(
                request_id=100,
                amount_of_steth=Decimal("1.0"),
                amount_of_shares=Decimal("1.0"),
                owner="0x1234",
                timestamp=1000,
                is_finalized=True,
                is_claimed=False,
            ),
        ]
        mock_client.claim_withdrawals.return_value = ClaimWithdrawalResult(
            success=True, tx_hash="0x" + "00" * 32, claimed_request_ids=[99, 100]
        )
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[99, 100], dry_run=False)

        await svc.claim(req)

        mock_client.claim_withdrawals.assert_awaited_once_with([99, 100])

    @pytest.mark.asyncio
    async def test_claim_dry_run_claimed_eth_is_none(self, config: LidoConfig) -> None:
        """dry_run=True の場合 claimed_eth=None であること。"""
        mock_client = AsyncMock()
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[1], dry_run=True)

        response = await svc.claim(req)

        assert response.claimed_eth is None


# ---------------------------------------------------------------------------
# LidoService.claim — claim 前 precheck（fail-closed / レビュー C2-(b)）
# ---------------------------------------------------------------------------


def _status(
    request_id: int,
    *,
    is_finalized: bool,
    is_claimed: bool,
    amount: str = "1.0",
) -> WithdrawalStatus:
    return WithdrawalStatus(
        request_id=request_id,
        amount_of_steth=Decimal(amount),
        amount_of_shares=Decimal(amount),
        owner="0x1234",
        timestamp=1000,
        is_finalized=is_finalized,
        is_claimed=is_claimed,
    )


class TestLidoServiceClaimPrecheck:
    """claim 前 finalization precheck（fail-closed）のテスト。"""

    @pytest.mark.asyncio
    async def test_claim_not_finalized_raises_and_no_tx(self, config: LidoConfig) -> None:
        """未 finalize の request は ClaimNotReadyError + tx 未送信。"""
        from app.protocols.lido.service import ClaimNotReadyError

        mock_client = AsyncMock()
        mock_client.get_withdrawal_status.return_value = [
            _status(7, is_finalized=False, is_claimed=False),
        ]
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[7], dry_run=False)

        with pytest.raises(ClaimNotReadyError, match="finalize"):
            await svc.claim(req)

        mock_client.claim_withdrawals.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_already_claimed_raises_and_no_tx(self, config: LidoConfig) -> None:
        """claim 済みの request は ClaimNotReadyError + tx 未送信。"""
        from app.protocols.lido.service import ClaimNotReadyError

        mock_client = AsyncMock()
        mock_client.get_withdrawal_status.return_value = [
            _status(8, is_finalized=True, is_claimed=True),
        ]
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[8], dry_run=False)

        with pytest.raises(ClaimNotReadyError, match="claim 済み"):
            await svc.claim(req)

        mock_client.claim_withdrawals.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_unknown_id_raises_and_no_tx(self, config: LidoConfig) -> None:
        """ステータス取得不可（未知ID）は ClaimNotReadyError + tx 未送信。"""
        from app.protocols.lido.service import ClaimNotReadyError

        mock_client = AsyncMock()
        mock_client.get_withdrawal_status.return_value = []
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[99], dry_run=False)

        with pytest.raises(ClaimNotReadyError, match="未知のID"):
            await svc.claim(req)

        mock_client.claim_withdrawals.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_partial_not_ready_blocks_entire_batch(self, config: LidoConfig) -> None:
        """1件でも未 ready なら batch 全体を拒否し tx 未送信。"""
        from app.protocols.lido.service import ClaimNotReadyError

        mock_client = AsyncMock()
        mock_client.get_withdrawal_status.return_value = [
            _status(1, is_finalized=True, is_claimed=False),
            _status(2, is_finalized=False, is_claimed=False),
        ]
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[1, 2], dry_run=False)

        with pytest.raises(ClaimNotReadyError):
            await svc.claim(req)

        mock_client.claim_withdrawals.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_all_ready_proceeds_to_tx(self, config: LidoConfig) -> None:
        """全件 finalized && not claimed なら tx を送信する。"""
        mock_client = AsyncMock()
        mock_client.get_withdrawal_status.return_value = [
            _status(1, is_finalized=True, is_claimed=False),
            _status(2, is_finalized=True, is_claimed=False),
        ]
        mock_client.claim_withdrawals.return_value = ClaimWithdrawalResult(
            success=True, tx_hash="0x" + "ab" * 32, claimed_request_ids=[1, 2]
        )
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[1, 2], dry_run=False)

        response = await svc.claim(req)

        assert response.tx_hash == "0x" + "ab" * 32
        mock_client.claim_withdrawals.assert_awaited_once_with([1, 2])

    @pytest.mark.asyncio
    async def test_claim_dry_run_skips_precheck(self, config: LidoConfig) -> None:
        """dry_run=True は precheck も tx もスキップする。"""
        mock_client = AsyncMock()
        svc = LidoService(client=mock_client, config=config)
        req = LidoClaimRequest(request_ids=[1], dry_run=True)

        response = await svc.claim(req)

        assert response.dry_run is True
        mock_client.get_withdrawal_status.assert_not_called()
        mock_client.claim_withdrawals.assert_not_called()


# ---------------------------------------------------------------------------
# DummyLidoClient.claim_withdrawals — スタブ動作確認
# ---------------------------------------------------------------------------


class TestDummyLidoClientClaim:
    """DummyLidoClient.claim_withdrawals / get_withdrawal_requests のテスト。"""

    @pytest.mark.asyncio
    async def test_claim_withdrawals_returns_success(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient.claim_withdrawals は成功を返すこと。"""
        result = await dummy_client.claim_withdrawals(request_ids=[1, 2])
        assert result.success is True
        assert result.tx_hash is not None
        assert result.tx_hash.startswith("0x")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_claim_withdrawals_preserves_request_ids(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """claim_withdrawals が claimed_request_ids を返すこと。"""
        request_ids = [1001, 1002, 1003]
        result = await dummy_client.claim_withdrawals(request_ids)
        assert result.claimed_request_ids == request_ids

    @pytest.mark.asyncio
    async def test_claim_withdrawals_no_real_write(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient.claim_withdrawals は on-chain write を起こさないこと。"""
        with patch("web3.Web3") as mock_web3:
            result = await dummy_client.claim_withdrawals(request_ids=[1])
        mock_web3.assert_not_called()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_claim_withdrawals_empty_ids_fails(self, dummy_client: DummyLidoClient) -> None:
        """request_ids が空のとき失敗を返すこと。"""
        result = await dummy_client.claim_withdrawals([])
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawals_tx_hash_format(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient の tx_hash が 0x プレフィックスを持つこと。"""
        result = await dummy_client.claim_withdrawals(request_ids=[7])
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
# LidoClient.claim_withdrawals — web3 mock で実装テスト（checkpoint hints 方式）
# ---------------------------------------------------------------------------


class TestLidoClientClaimWithdrawals:
    """LidoClient.claim_withdrawals の web3 mock テスト（checkpoint hints 方式）。"""

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
        """web3 モックを構築する（checkpoint hints 方式）。"""
        mock_w3 = MagicMock()
        mock_account = MagicMock()
        mock_account.address = "0x" + "bb" * 20
        mock_w3.eth.account.from_key.return_value = mock_account
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 10_000_000_000

        mock_signed = MagicMock()
        mock_signed.raw_transaction = b"\x00" * 32
        mock_w3.eth.account.sign_transaction.return_value = mock_signed

        fake_tx_hash = b"\xde\xad" + b"\x00" * 30
        mock_w3.eth.send_raw_transaction.return_value = fake_tx_hash
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": tx_status}

        mock_contract = MagicMock()
        # getLastCheckpointIndex
        mock_contract.functions.getLastCheckpointIndex.return_value.call.return_value = 100
        # findCheckpointHints
        mock_contract.functions.findCheckpointHints.return_value.call.return_value = [1]
        # claimWithdrawals
        mock_fn = MagicMock()
        mock_fn.build_transaction.return_value = {"from": mock_account.address}
        mock_contract.functions.claimWithdrawals.return_value = mock_fn
        mock_w3.eth.contract.return_value = mock_contract
        mock_w3.to_checksum_address = MagicMock(side_effect=lambda x: x)

        return mock_w3

    @pytest.mark.asyncio
    async def test_claim_withdrawals_status_1_returns_success(
        self, real_client: LidoClient
    ) -> None:
        """status=1 のとき success=True を返すこと。"""
        mock_w3 = self._make_mock_w3(tx_status=1)
        real_client._w3 = mock_w3
        real_client._contract = MagicMock()
        real_client._initialized = True

        with patch("web3.Web3.to_checksum_address", side_effect=lambda x: x):
            result = await real_client.claim_withdrawals(request_ids=[1])

        assert result.success is True
        assert result.tx_hash is not None
        assert result.claimed_request_ids == [1]

    @pytest.mark.asyncio
    async def test_claim_withdrawals_status_0_returns_failure(
        self, real_client: LidoClient
    ) -> None:
        """status=0 のとき success=False を返すこと。"""
        mock_w3 = self._make_mock_w3(tx_status=0)
        real_client._w3 = mock_w3
        real_client._contract = MagicMock()
        real_client._initialized = True

        with patch("web3.Web3.to_checksum_address", side_effect=lambda x: x):
            result = await real_client.claim_withdrawals(request_ids=[2])

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawals_exception_fail_open(self, real_client: LidoClient) -> None:
        """例外発生時に fail-open（success=False）で返すこと。"""
        mock_w3 = MagicMock()
        mock_w3.eth.account.from_key.side_effect = Exception("接続エラー")
        real_client._w3 = mock_w3
        real_client._contract = MagicMock()
        real_client._initialized = True

        result = await real_client.claim_withdrawals(request_ids=[3])

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawals_no_private_key_returns_failure(self) -> None:
        """LIDO_WALLET_PRIVATE_KEY 未設定時に success=False を返すこと。"""
        client = LidoClient(LidoConfig(sandbox=False, wallet_private_key=""))
        client._initialized = True
        client._w3 = MagicMock()
        client._contract = MagicMock()

        result = await client.claim_withdrawals(request_ids=[1])

        assert result.success is False
        assert "LIDO_WALLET_PRIVATE_KEY" in (result.error or "")

    @pytest.mark.asyncio
    async def test_claim_withdrawals_empty_ids_fails(self, real_client: LidoClient) -> None:
        """request_ids が空のとき success=False を返すこと。"""
        real_client._initialized = True
        real_client._w3 = MagicMock()
        real_client._contract = MagicMock()

        result = await real_client.claim_withdrawals(request_ids=[])

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_claim_withdrawals_uses_checkpoint_hints(self, real_client: LidoClient) -> None:
        """claimWithdrawals が getLastCheckpointIndex と findCheckpointHints を呼ぶこと。"""
        mock_w3 = self._make_mock_w3(tx_status=1)
        real_client._w3 = mock_w3
        real_client._contract = MagicMock()
        real_client._initialized = True

        with patch("web3.Web3.to_checksum_address", side_effect=lambda x: x):
            await real_client.claim_withdrawals(request_ids=[1])

        queue_contract = mock_w3.eth.contract.return_value
        queue_contract.functions.getLastCheckpointIndex.assert_called_once()
        queue_contract.functions.findCheckpointHints.assert_called_once()


# ---------------------------------------------------------------------------
# LidoClient.get_withdrawal_status — web3 mock テスト（checkpoint hints 統合）
# ---------------------------------------------------------------------------


class TestLidoClientGetWithdrawalStatus:
    """LidoClient.get_withdrawal_status のモックテスト（チェーン接続なし）。"""

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_parses_response(self) -> None:
        """get_withdrawal_status がコントラクトレスポンスを正しくパースすること。"""
        import time  # noqa: PLC0415

        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        now = int(time.time())
        mock_raw_statuses = [
            (
                500_000_000_000_000_000,  # amountOfStETH (0.5 ETH in Wei)
                490_000_000_000_000_000,  # amountOfShares
                "0x0000000000000000000000000000000000000001",  # owner
                now - 3600,  # timestamp
                True,  # isFinalized
                False,  # isClaimed
            )
        ]

        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.getWithdrawalStatus.return_value.call.return_value = (
            mock_raw_statuses
        )

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_queue_contract
        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        with patch(
            "web3.Web3.to_checksum_address",
            return_value="0x889edC2eDab5f40e902b864aD4d7AdE8E412F9B1",
        ):
            statuses = await client.get_withdrawal_status([1001])

        assert len(statuses) == 1
        status = statuses[0]
        assert status.request_id == 1001
        assert type(status.amount_of_steth) is Decimal
        assert status.amount_of_steth == Decimal("500000000000000000") / Decimal(
            "1000000000000000000"
        )
        assert status.is_finalized is True
        assert status.is_claimed is False

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_raises_on_web3_error(self) -> None:
        """web3 呼び出しで例外が出たとき RuntimeError を raise すること。"""
        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.getWithdrawalStatus.side_effect = RuntimeError("RPC error")

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_queue_contract
        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        with (
            patch("web3.Web3.to_checksum_address", return_value="0xAddress"),
            pytest.raises(RuntimeError, match="withdrawal ステータス取得失敗"),
        ):
            await client.get_withdrawal_status([1001])

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_decimal_conversion(self) -> None:
        """amount_of_steth が Decimal 型に変換されること（float 禁止）。"""
        config = LidoConfig(sandbox=False)
        client = LidoClient(config)

        mock_raw_statuses = [
            (
                1_000_000_000_000_000_000,  # 1 ETH
                1_000_000_000_000_000_000,
                "0x0000000000000000000000000000000000000001",
                1000,
                True,
                False,
            )
        ]
        mock_queue_contract = MagicMock()
        mock_queue_contract.functions.getWithdrawalStatus.return_value.call.return_value = (
            mock_raw_statuses
        )
        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_queue_contract
        client._w3 = mock_w3
        client._contract = MagicMock()
        client._initialized = True

        with patch("web3.Web3.to_checksum_address", return_value="0xAddress"):
            statuses = await client.get_withdrawal_status([1])

        status = statuses[0]
        assert type(status.amount_of_steth) is Decimal
        assert type(status.amount_of_shares) is Decimal
        assert status.amount_of_steth == Decimal("1")


# ---------------------------------------------------------------------------
# DummyLidoClient.get_withdrawal_status テスト
# ---------------------------------------------------------------------------


class TestDummyLidoClientWithdrawalStatus:
    """DummyLidoClient.get_withdrawal_status のテスト。"""

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_returns_list(self, dummy_client: DummyLidoClient) -> None:
        """get_withdrawal_status がリストを返すこと。"""
        statuses = await dummy_client.get_withdrawal_status([1001, 1002])
        assert isinstance(statuses, list)
        assert len(statuses) == 2

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_correct_fields(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """get_withdrawal_status の各フィールドが正しい型であること。"""
        statuses = await dummy_client.get_withdrawal_status([1001])
        status = statuses[0]
        assert isinstance(status, WithdrawalStatus)
        assert status.request_id == 1001
        assert isinstance(status.amount_of_steth, Decimal)
        assert isinstance(status.amount_of_shares, Decimal)
        assert isinstance(status.is_finalized, bool)
        assert isinstance(status.is_claimed, bool)
        assert isinstance(status.timestamp, int)

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_no_float(self, dummy_client: DummyLidoClient) -> None:
        """withdrawal status の金額フィールドが Decimal であること（float 禁止）。"""
        statuses = await dummy_client.get_withdrawal_status([1001])
        status = statuses[0]
        assert type(status.amount_of_steth) is Decimal
        assert type(status.amount_of_shares) is Decimal

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_dummy_is_finalized(
        self, dummy_client: DummyLidoClient
    ) -> None:
        """DummyLidoClient の withdrawal status は is_finalized=True を返すこと。"""
        statuses = await dummy_client.get_withdrawal_status([1001])
        assert statuses[0].is_finalized is True

    @pytest.mark.asyncio
    async def test_get_withdrawal_status_no_real_call(self, dummy_client: DummyLidoClient) -> None:
        """DummyLidoClient.get_withdrawal_status は on-chain call を起こさないこと。"""
        with patch("web3.Web3") as mock_web3:
            statuses = await dummy_client.get_withdrawal_status([1001])
        mock_web3.assert_not_called()
        assert len(statuses) == 1
