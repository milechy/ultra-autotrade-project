# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Lido サービス層の withdraw 実行パステスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.lido.config import LidoConfig
from app.protocols.lido.schemas import LidoWithdrawRequest, TxResult
from app.protocols.lido.service import LidoService


@pytest.fixture
def config() -> LidoConfig:
    return LidoConfig(sandbox=True, peg_deviation_warn_pct=2.0)


class TestLidoServiceWithdrawRealExecution:
    """LidoService.withdraw の non-dry_run パスのテスト。"""

    @pytest.mark.asyncio
    async def test_real_withdraw_succeeds(self, config: LidoConfig) -> None:
        """dry_run=False で withdraw が正常に実行されること。"""
        mock_client = AsyncMock()
        mock_client.withdraw.return_value = TxResult(
            tx_hash="0x" + "cc" * 32,
            success=True,
        )
        svc = LidoService(client=mock_client, config=config)
        req = LidoWithdrawRequest(amount_steth=Decimal("0.5"), dry_run=False)

        response = await svc.withdraw(req)

        assert response.dry_run is False
        assert response.tx_hash is not None
        assert response.operation == "WITHDRAW_REQUEST"
        assert response.amount_steth == Decimal("0.5")
        mock_client.withdraw.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_real_withdraw_failure_raises_runtime_error(self, config: LidoConfig) -> None:
        """withdraw 失敗時に RuntimeError を発生させること。"""
        mock_client = AsyncMock()
        mock_client.withdraw.return_value = TxResult(success=False, error="引き出しキュー満杯")
        svc = LidoService(client=mock_client, config=config)
        req = LidoWithdrawRequest(amount_steth=Decimal("0.5"), dry_run=False)

        with pytest.raises(RuntimeError, match="Lido 引き出しリクエスト失敗"):
            await svc.withdraw(req)

    @pytest.mark.asyncio
    async def test_real_withdraw_passes_correct_asset(self, config: LidoConfig) -> None:
        """withdraw が 'stETH' アセットを渡すこと。"""
        mock_client = AsyncMock()
        mock_client.withdraw.return_value = TxResult(tx_hash="0x" + "dd" * 32, success=True)
        svc = LidoService(client=mock_client, config=config)
        req = LidoWithdrawRequest(amount_steth=Decimal("1.0"), dry_run=False)

        await svc.withdraw(req)

        call_args = mock_client.withdraw.call_args
        assert call_args[0][0] == Decimal("1.0")  # amount
        assert call_args[0][1] == "stETH"  # asset

    @pytest.mark.asyncio
    async def test_real_withdraw_tx_hash_preserved(self, config: LidoConfig) -> None:
        """withdraw の tx_hash がレスポンスに含まれること。"""
        expected_tx = "0x" + "ff" * 32
        mock_client = AsyncMock()
        mock_client.withdraw.return_value = TxResult(tx_hash=expected_tx, success=True)
        svc = LidoService(client=mock_client, config=config)
        req = LidoWithdrawRequest(amount_steth=Decimal("0.5"), dry_run=False)

        response = await svc.withdraw(req)

        assert response.tx_hash == expected_tx
