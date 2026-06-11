# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""signal_adapter モジュールのテスト。

テスト対象:
- PendleSignalAdapter: adapter 注入・フォールバック・例外時
- LidoSignalAdapter: adapter 注入・フォールバック・例外時
- StrategyScorer: adapter 注入・risk_mode weight・後方互換
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.optimizer.schemas import Protocol
from app.ai.optimizer.signal_adapter import (
    _FALLBACK_LIDO_APY,
    _FALLBACK_PEG_DEVIATION,
    _FALLBACK_PENDLE_MATURITY_DAYS,
    _FALLBACK_PENDLE_PT_APY,
    _FALLBACK_PENDLE_YT_APY,
    LidoSignalAdapter,
    PendleSignalAdapter,
)
from app.ai.optimizer.strategy_scorer import _RISK_WEIGHT, StrategyScorer


# --------------------------------------------------------------------------- #
# ヘルパー: ダミー PendleMarketInfo
# --------------------------------------------------------------------------- #
def _make_pendle_market_info(
    implied_apy: Decimal = Decimal("6.0"),
    pt_price: Decimal = Decimal("0.94"),
    yt_price: Decimal = Decimal("0.06"),
    days_to_maturity: int = 45,
) -> MagicMock:
    """PendleMarketInfo ライクなオブジェクトを返す。"""
    info = MagicMock()
    info.implied_apy = implied_apy
    info.pt_price = pt_price
    info.yt_price = yt_price
    info.days_to_maturity = days_to_maturity
    return info


# --------------------------------------------------------------------------- #
# LidoSignalAdapter テスト
# --------------------------------------------------------------------------- #
class TestLidoSignalAdapter:
    """LidoSignalAdapter のテスト。"""

    @pytest.mark.asyncio
    async def test_get_staking_apy_no_client_returns_fallback(self) -> None:
        """client=None の場合はフォールバック値を返すこと。"""
        adapter = LidoSignalAdapter(client=None)
        result = await adapter.get_staking_apy()
        assert result == _FALLBACK_LIDO_APY
        assert isinstance(result, Decimal)

    @pytest.mark.asyncio
    async def test_get_staking_apy_with_client_returns_real_value(self) -> None:
        """client がある場合は get_staking_apr() の値を返すこと。"""
        mock_client = MagicMock()
        mock_client.get_staking_apr = AsyncMock(return_value=Decimal("4.2"))
        adapter = LidoSignalAdapter(client=mock_client)
        result = await adapter.get_staking_apy()
        assert result == Decimal("4.2")
        mock_client.get_staking_apr.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_staking_apy_client_exception_returns_fallback(self) -> None:
        """client が例外を発生させた場合はフォールバック値を返すこと（fail-open）。"""
        mock_client = MagicMock()
        mock_client.get_staking_apr = AsyncMock(side_effect=RuntimeError("network error"))
        adapter = LidoSignalAdapter(client=mock_client)
        result = await adapter.get_staking_apy()
        assert result == _FALLBACK_LIDO_APY

    @pytest.mark.asyncio
    async def test_get_peg_deviation_no_client_returns_zero(self) -> None:
        """client=None の場合はフォールバック（0）を返すこと。"""
        adapter = LidoSignalAdapter(client=None)
        result = await adapter.get_peg_deviation()
        assert result == _FALLBACK_PEG_DEVIATION
        assert isinstance(result, Decimal)

    @pytest.mark.asyncio
    async def test_get_peg_deviation_perfect_peg_returns_zero(self) -> None:
        """stETH/ETH = 1.0 の場合は乖離率 0 を返すこと。"""
        mock_client = MagicMock()
        mock_client.get_steth_eth_ratio = AsyncMock(return_value=Decimal("1.0"))
        adapter = LidoSignalAdapter(client=mock_client)
        result = await adapter.get_peg_deviation()
        assert result == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_peg_deviation_depeg_returns_positive(self) -> None:
        """stETH/ETH = 0.98 の場合は乖離率 2% を返すこと。"""
        mock_client = MagicMock()
        mock_client.get_steth_eth_ratio = AsyncMock(return_value=Decimal("0.98"))
        adapter = LidoSignalAdapter(client=mock_client)
        result = await adapter.get_peg_deviation()
        assert result == Decimal("2")  # |1 - 0.98| * 100 = 2%

    @pytest.mark.asyncio
    async def test_get_peg_deviation_exception_returns_fallback(self) -> None:
        """client が例外を発生させた場合はフォールバック値を返すこと。"""
        mock_client = MagicMock()
        mock_client.get_steth_eth_ratio = AsyncMock(side_effect=Exception("rpc error"))
        adapter = LidoSignalAdapter(client=mock_client)
        result = await adapter.get_peg_deviation()
        assert result == _FALLBACK_PEG_DEVIATION

    @pytest.mark.asyncio
    async def test_return_types_are_decimal(self) -> None:
        """全メソッドが Decimal 型を返すこと。"""
        adapter = LidoSignalAdapter(client=None)
        apy = await adapter.get_staking_apy()
        peg = await adapter.get_peg_deviation()
        assert isinstance(apy, Decimal)
        assert isinstance(peg, Decimal)


# --------------------------------------------------------------------------- #
# PendleSignalAdapter テスト
# --------------------------------------------------------------------------- #
class TestPendleSignalAdapter:
    """PendleSignalAdapter のテスト。"""

    @pytest.mark.asyncio
    async def test_get_pt_apy_no_client_returns_fallback(self) -> None:
        """client=None の場合はフォールバック PT APY を返すこと。"""
        adapter = PendleSignalAdapter(client=None)
        result = await adapter.get_pt_apy()
        assert result == _FALLBACK_PENDLE_PT_APY
        assert isinstance(result, Decimal)

    @pytest.mark.asyncio
    async def test_get_pt_apy_with_client_returns_real_value(self) -> None:
        """client がある場合は implied_apy を返すこと。"""
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(
            return_value=_make_pendle_market_info(implied_apy=Decimal("6.5"))
        )
        adapter = PendleSignalAdapter(client=mock_client, market_address="0x1234567890abcdef")
        result = await adapter.get_pt_apy()
        assert result == Decimal("6.5")

    @pytest.mark.asyncio
    async def test_get_pt_apy_client_exception_returns_fallback(self) -> None:
        """client が例外を発生させた場合はフォールバック値を返すこと（fail-open）。"""
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(side_effect=RuntimeError("api error"))
        adapter = PendleSignalAdapter(client=mock_client, market_address="0xabc")
        result = await adapter.get_pt_apy()
        assert result == _FALLBACK_PENDLE_PT_APY

    @pytest.mark.asyncio
    async def test_get_yt_apy_no_client_returns_fallback(self) -> None:
        """client=None の場合はフォールバック YT APY を返すこと。"""
        adapter = PendleSignalAdapter(client=None)
        result = await adapter.get_yt_apy()
        assert result == _FALLBACK_PENDLE_YT_APY
        assert isinstance(result, Decimal)

    @pytest.mark.asyncio
    async def test_get_yt_apy_with_client_calculates_from_price(self) -> None:
        """client がある場合は yt_price から YT APY を計算すること。

        implied_apy=6.0, yt_price=0.06 → yt_apy = 6.0 / 0.06 = 100 → cap 20
        """
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(
            return_value=_make_pendle_market_info(
                implied_apy=Decimal("6.0"),
                yt_price=Decimal("0.06"),
            )
        )
        adapter = PendleSignalAdapter(client=mock_client, market_address="0xabc")
        result = await adapter.get_yt_apy()
        # cap at 20%
        assert result == Decimal("20")

    @pytest.mark.asyncio
    async def test_get_yt_apy_capped_at_20(self) -> None:
        """YT APY は 20% を上限とすること。"""
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(
            return_value=_make_pendle_market_info(
                implied_apy=Decimal("10.0"),
                yt_price=Decimal("0.01"),  # extremely high leverage
            )
        )
        adapter = PendleSignalAdapter(client=mock_client, market_address="0xabc")
        result = await adapter.get_yt_apy()
        assert result <= Decimal("20")

    @pytest.mark.asyncio
    async def test_get_yt_apy_modest_leverage(self) -> None:
        """中程度のレバレッジ（yt_price=0.20）の場合は cap に達しないこと。

        implied_apy=5.0, yt_price=0.20 → yt_apy = 5.0 / 0.20 = 25 → cap 20
        """
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(
            return_value=_make_pendle_market_info(
                implied_apy=Decimal("5.0"),
                yt_price=Decimal("0.50"),  # low leverage
            )
        )
        adapter = PendleSignalAdapter(client=mock_client, market_address="0xabc")
        result = await adapter.get_yt_apy()
        # 5.0 / 0.50 = 10.0 → under cap
        assert result == Decimal("10")
        assert result < Decimal("20")

    @pytest.mark.asyncio
    async def test_get_yt_apy_exception_returns_fallback(self) -> None:
        """client が例外を発生させた場合はフォールバック値を返すこと。"""
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(side_effect=Exception("timeout"))
        adapter = PendleSignalAdapter(client=mock_client, market_address="0xabc")
        result = await adapter.get_yt_apy()
        assert result == _FALLBACK_PENDLE_YT_APY

    @pytest.mark.asyncio
    async def test_get_maturity_days_no_client_returns_fallback(self) -> None:
        """client=None の場合はフォールバック満期日数（30）を返すこと。"""
        adapter = PendleSignalAdapter(client=None)
        result = await adapter.get_maturity_days()
        assert result == _FALLBACK_PENDLE_MATURITY_DAYS
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_get_maturity_days_with_client(self) -> None:
        """client がある場合は days_to_maturity を返すこと。"""
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(
            return_value=_make_pendle_market_info(days_to_maturity=60)
        )
        adapter = PendleSignalAdapter(client=mock_client, market_address="0xabc")
        result = await adapter.get_maturity_days()
        assert result == 60

    @pytest.mark.asyncio
    async def test_get_maturity_days_exception_returns_fallback(self) -> None:
        """client が例外を発生させた場合はフォールバック値を返すこと。"""
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(side_effect=RuntimeError("rpc"))
        adapter = PendleSignalAdapter(client=mock_client, market_address="0xabc")
        result = await adapter.get_maturity_days()
        assert result == _FALLBACK_PENDLE_MATURITY_DAYS


# --------------------------------------------------------------------------- #
# StrategyScorer + adapter 注入テスト
# --------------------------------------------------------------------------- #
class TestStrategyScorerAdapterInjection:
    """StrategyScorer の adapter 注入・後方互換テスト。"""

    def test_no_adapter_backward_compatible(self) -> None:
        """adapter なしで生成した場合は従来通り動作すること（後方互換）。"""
        scorer = StrategyScorer()
        candidates = scorer.get_all_candidates()
        assert len(candidates) == 5
        # ダミー定数と同じ値
        lido = next(c for c in candidates if c.protocol == Protocol.LIDO)
        assert lido.expected_apy == Decimal("3.5")
        pendle_pt = next(c for c in candidates if c.protocol == Protocol.PENDLE_PT)
        assert pendle_pt.expected_apy == Decimal("5.2")

    @pytest.mark.asyncio
    async def test_lido_adapter_injection_uses_real_data(self) -> None:
        """Lido adapter 注入時は実データを使用すること。"""
        mock_client = MagicMock()
        mock_client.get_staking_apr = AsyncMock(return_value=Decimal("4.8"))
        mock_client.get_steth_eth_ratio = AsyncMock(return_value=Decimal("0.99"))

        adapter = LidoSignalAdapter(client=mock_client)
        scorer = StrategyScorer(lido_adapter=adapter)

        lido = await scorer.score_lido_async()
        assert lido.protocol == Protocol.LIDO
        assert lido.expected_apy == Decimal("4.8")
        # peg_deviation = |1 - 0.99| * 100 = 1%
        assert lido.peg_deviation == Decimal("1")

    @pytest.mark.asyncio
    async def test_pendle_adapter_injection_uses_real_data(self) -> None:
        """Pendle adapter 注入時は実データを使用すること。"""
        mock_client = MagicMock()
        mock_client.get_market_info = AsyncMock(
            return_value=_make_pendle_market_info(
                implied_apy=Decimal("7.0"),
                yt_price=Decimal("0.50"),
                days_to_maturity=45,
            )
        )
        adapter = PendleSignalAdapter(client=mock_client, market_address="0x1234")
        scorer = StrategyScorer(pendle_adapter=adapter)

        pt = await scorer.score_pendle_pt_async()
        assert pt.protocol == Protocol.PENDLE_PT
        assert pt.expected_apy == Decimal("7.0")
        assert pt.maturity_days == 45

    @pytest.mark.asyncio
    async def test_get_all_candidates_async_with_adapters(self) -> None:
        """get_all_candidates_async が adapter 経由で全候補を返すこと。"""
        lido_mock = MagicMock()
        lido_mock.get_staking_apr = AsyncMock(return_value=Decimal("4.0"))
        lido_mock.get_steth_eth_ratio = AsyncMock(return_value=Decimal("1.0"))

        pendle_mock = MagicMock()
        pendle_mock.get_market_info = AsyncMock(
            return_value=_make_pendle_market_info(implied_apy=Decimal("6.2"))
        )

        scorer = StrategyScorer(
            lido_adapter=LidoSignalAdapter(client=lido_mock),
            pendle_adapter=PendleSignalAdapter(client=pendle_mock, market_address="0x1234"),
        )
        candidates = await scorer.get_all_candidates_async()
        assert len(candidates) == 5
        protocols = {c.protocol for c in candidates}
        assert Protocol.AAVE in protocols
        assert Protocol.LIDO in protocols
        assert Protocol.LIDO_AAVE in protocols
        assert Protocol.PENDLE_PT in protocols
        assert Protocol.PENDLE_YT in protocols

    @pytest.mark.asyncio
    async def test_adapter_fallback_if_client_fails(self) -> None:
        """adapter client が失敗しても get_all_candidates_async が完走すること（fail-open）。"""
        lido_mock = MagicMock()
        lido_mock.get_staking_apr = AsyncMock(side_effect=RuntimeError("network"))
        lido_mock.get_steth_eth_ratio = AsyncMock(side_effect=RuntimeError("network"))

        pendle_mock = MagicMock()
        pendle_mock.get_market_info = AsyncMock(side_effect=Exception("timeout"))

        scorer = StrategyScorer(
            lido_adapter=LidoSignalAdapter(client=lido_mock),
            pendle_adapter=PendleSignalAdapter(client=pendle_mock, market_address="0xfail"),
        )
        # fail-open: 例外なく完走しフォールバック値を使用
        candidates = await scorer.get_all_candidates_async()
        assert len(candidates) == 5
        lido = next(c for c in candidates if c.protocol == Protocol.LIDO)
        assert lido.expected_apy == _FALLBACK_LIDO_APY


# --------------------------------------------------------------------------- #
# risk_mode weight テスト
# --------------------------------------------------------------------------- #
class TestRiskModeWeight:
    """risk_mode によるリスクペナルティ調整のテスト。"""

    def test_balanced_uses_base_penalty(self) -> None:
        """balanced モードではリスクペナルティに変更なし（×1.0）。"""
        scorer = StrategyScorer(risk_mode="balanced")
        lido = scorer.score_lido()
        # RISK_LIDO = 0.15, balanced=×1.0
        assert lido.risk_penalty == Decimal("0.15")

    def test_conservative_increases_penalty(self) -> None:
        """conservative モードではリスクペナルティが強くなること（×1.5）。"""
        scorer = StrategyScorer(risk_mode="conservative")
        lido = scorer.score_lido()
        # RISK_LIDO = 0.15, conservative=×1.5
        expected = Decimal("0.15") * Decimal("1.5")
        assert lido.risk_penalty == expected

    def test_aggressive_decreases_penalty(self) -> None:
        """aggressive モードではリスクペナルティが弱くなること（×0.7）。"""
        scorer = StrategyScorer(risk_mode="aggressive")
        lido = scorer.score_lido()
        # RISK_LIDO = 0.15, aggressive=×0.7
        expected = Decimal("0.15") * Decimal("0.7")
        assert lido.risk_penalty == expected

    def test_conservative_higher_than_aggressive(self) -> None:
        """conservative のリスクペナルティは aggressive より大きいこと。"""
        conservative_scorer = StrategyScorer(risk_mode="conservative")
        aggressive_scorer = StrategyScorer(risk_mode="aggressive")
        c_lido = conservative_scorer.score_lido()
        a_lido = aggressive_scorer.score_lido()
        assert c_lido.risk_penalty > a_lido.risk_penalty

    def test_risk_mode_affects_pendle_yt(self) -> None:
        """risk_mode が Pendle YT（高リスク）にも適用されること。"""
        conservative = StrategyScorer(risk_mode="conservative")
        aggressive = StrategyScorer(risk_mode="aggressive")
        c_yt = conservative.score_pendle_yt()
        a_yt = aggressive.score_pendle_yt()
        assert c_yt.risk_penalty > a_yt.risk_penalty

    def test_risk_penalty_capped_at_one(self) -> None:
        """リスクペナルティが 1.0 を超えないこと（conservative × 高ペナルティ）。"""
        # RISK_PENDLE_YT = 0.30, conservative=×1.5 → 0.45（上限以下）
        scorer = StrategyScorer(risk_mode="conservative")
        yt = scorer.score_pendle_yt()
        assert yt.risk_penalty <= Decimal("1")

    def test_unknown_risk_mode_uses_balanced(self) -> None:
        """未知の risk_mode はデフォルト（balanced 相当, ×1.0）にフォールバックすること。"""
        scorer = StrategyScorer(risk_mode="unknown_mode")
        lido = scorer.score_lido()
        # balanced と同じ値
        balanced_scorer = StrategyScorer(risk_mode="balanced")
        lido_balanced = balanced_scorer.score_lido()
        assert lido.risk_penalty == lido_balanced.risk_penalty

    def test_risk_mode_affects_all_protocols(self) -> None:
        """risk_mode が全プロトコルに一貫適用されること。"""
        conservative = StrategyScorer(risk_mode="conservative")
        aggressive = StrategyScorer(risk_mode="aggressive")
        c_candidates = conservative.get_all_candidates()
        a_candidates = aggressive.get_all_candidates()
        for c, a in zip(c_candidates, a_candidates):
            assert c.protocol == a.protocol
            assert c.risk_penalty >= a.risk_penalty, (
                f"{c.protocol}: conservative risk_penalty={c.risk_penalty} "
                f"should be >= aggressive={a.risk_penalty}"
            )

    def test_risk_mode_ranking_conservative_penalizes_high_risk(self) -> None:
        """conservative モードでは高リスク候補のペナルティが大きくなること。

        Pendle YT（RISK_PENDLE_YT=0.30）は conservative で 0.45、
        Aave（RISK_AAVE_USDC=0.05）は conservative で 0.075。
        差が広がること（0.375 vs balanced の 0.25）を確認。
        """
        balanced = StrategyScorer(risk_mode="balanced")
        conservative = StrategyScorer(risk_mode="conservative")

        b_yt = balanced.score_pendle_yt()
        c_yt = conservative.score_pendle_yt()
        b_aave = balanced.score_aave()
        c_aave = conservative.score_aave()

        # conservative で YT のペナルティ増分が AAVE より大きいこと（高リスク増幅）
        yt_diff = c_yt.risk_penalty - b_yt.risk_penalty
        aave_diff = c_aave.risk_penalty - b_aave.risk_penalty
        assert yt_diff > aave_diff

    @pytest.mark.asyncio
    async def test_risk_mode_applied_in_async_methods(self) -> None:
        """risk_mode が非同期スコアメソッドにも適用されること。"""
        conservative = StrategyScorer(risk_mode="conservative")
        aggressive = StrategyScorer(risk_mode="aggressive")

        c_lido = await conservative.score_lido_async()
        a_lido = await aggressive.score_lido_async()
        assert c_lido.risk_penalty > a_lido.risk_penalty

    @pytest.mark.asyncio
    async def test_risk_weight_constants_are_decimal(self) -> None:
        """_RISK_WEIGHT の各値が Decimal 型であること。"""
        for mode, weight in _RISK_WEIGHT.items():
            assert isinstance(weight, Decimal), f"risk_mode={mode}: weight is not Decimal"
