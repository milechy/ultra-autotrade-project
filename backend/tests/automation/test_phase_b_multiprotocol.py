# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/automation/test_phase_b_multiprotocol.py
"""Phase-B: ai_judgment_scheduler のマルチプロトコルルーティング (_resolve_protocol_routing) のテスト。

デフォルト (フラグ無効) は Aave 既定経路を完全維持し、
AI_OPTIMIZER_MULTIPROTOCOL_ENABLED=true かつ BUY のときのみ optimizer 推奨に応じて
lido/pendle へルーティングする。on-chain 実行は行わない。
"""

from decimal import Decimal

from app.ai.optimizer.schemas import Protocol
from app.ai.schemas import CrossValidationResult, LLMDecision, LLMProvider, TradeAction
from app.automation.ai_judgment_scheduler import _resolve_protocol_routing


def _cv(action: TradeAction) -> CrossValidationResult:
    return CrossValidationResult(
        primary=LLMDecision(provider=LLMProvider.CLAUDE, action=action, confidence=80, reason="x"),
        secondary=None,
        agreed=True,
        final_action=action,
        final_confidence=80,
        final_reason="テスト判定理由",
    )


class _FakeComparison:
    def __init__(self, protocol: Protocol) -> None:
        self.recommended = type("R", (), {"protocol": protocol})()


def _patch_compare(monkeypatch, protocol_or_exc):
    """[D5b] routing は実 APY の compare_async を使うため、async 版を patch する。

    scorer/adapter は routing 内で構築されるが compare_async を差し替えるため
    get_market_info 等の外部呼び出しは走らない（hermetic）。
    """
    import app.ai.optimizer.comparator as comp

    async def _compare_async(self, **kwargs):
        if isinstance(protocol_or_exc, Exception):
            raise protocol_or_exc
        return _FakeComparison(protocol_or_exc)

    monkeypatch.setattr(comp.StrategyComparator, "compare_async", _compare_async)


class TestResolveProtocolRouting:
    def test_default_aave_buy_when_flag_off(self, monkeypatch) -> None:
        monkeypatch.delenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", raising=False)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "balanced", Decimal("1000")) == (
            "SUPPLY",
            "USDC",
            "aave",
        )

    def test_default_aave_sell_when_flag_off(self, monkeypatch) -> None:
        monkeypatch.delenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", raising=False)
        assert _resolve_protocol_routing(_cv(TradeAction.SELL), "balanced", Decimal("1000")) == (
            "WITHDRAW",
            "USDC",
            "aave",
        )

    def test_sell_stays_aave_even_with_flag_on(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.LIDO)
        op, asset, proto = _resolve_protocol_routing(
            _cv(TradeAction.SELL), "balanced", Decimal("1000")
        )
        assert (op, asset, proto) == ("WITHDRAW", "USDC", "aave")

    def test_routes_to_lido(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.LIDO)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "balanced", Decimal("1000")) == (
            "STAKE_ETH",
            "ETH",
            "lido",
        )

    def test_routes_to_pendle(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.PENDLE_PT)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "aggressive", Decimal("1000")) == (
            "BUY_PT",
            "PT-yoUSD",
            "pendle",
        )

    def test_routes_lido_aave_to_lido(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.LIDO_AAVE)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "balanced", Decimal("1000")) == (
            "STAKE_ETH",
            "ETH",
            "lido",
        )

    def test_routes_pendle_yt_to_pendle(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.PENDLE_YT)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "aggressive", Decimal("1000")) == (
            "BUY_PT",
            "PT-yoUSD",
            "pendle",
        )

    # [D5] risk_mode eligibility ゲート — optimizer が推奨しても risk_mode が許可しなければ aave。
    def test_pendle_gated_for_balanced(self, monkeypatch) -> None:
        """balanced は pendle 非適格 → optimizer が pendle 推奨でも aave にフォールバック。"""
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.PENDLE_PT)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "balanced", Decimal("1000")) == (
            "SUPPLY",
            "USDC",
            "aave",
        )

    def test_pendle_gated_for_conservative(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.PENDLE_PT)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "conservative", Decimal("1000")) == (
            "SUPPLY",
            "USDC",
            "aave",
        )

    def test_lido_gated_for_conservative(self, monkeypatch) -> None:
        """conservative は lido 非適格 → aave にフォールバック。"""
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.LIDO)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "conservative", Decimal("1000")) == (
            "SUPPLY",
            "USDC",
            "aave",
        )

    def test_unknown_risk_mode_defaults_to_aave_only(self, monkeypatch) -> None:
        """未知/None risk_mode は conservative 相当 = aave のみ。"""
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.PENDLE_PT)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), None, Decimal("1000")) == (
            "SUPPLY",
            "USDC",
            "aave",
        )

    def test_aave_recommendation_stays_aave(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, Protocol.AAVE)
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "conservative", Decimal("1000")) == (
            "SUPPLY",
            "USDC",
            "aave",
        )

    def test_optimizer_error_falls_back_to_aave(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        _patch_compare(monkeypatch, RuntimeError("optimizer down"))
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "balanced", Decimal("1000")) == (
            "SUPPLY",
            "USDC",
            "aave",
        )

    def test_real_optimizer_integration_returns_consistent_protocol(self, monkeypatch) -> None:
        """フラグ on で実 optimizer(compare_async + adapter)を通し、(operation, asset) が
        protocol と整合する。adapter の APY 取得は固定値に差し替えて hermetic にする。"""
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        import app.ai.optimizer.signal_adapter as sa

        async def _fixed_pt_apy(self):
            return Decimal("6.31")

        async def _fixed_supply_apy(self):
            return Decimal("4.5")

        monkeypatch.setattr(sa.PendleSignalAdapter, "get_pt_apy", _fixed_pt_apy)
        monkeypatch.setattr(sa.AaveSignalAdapter, "get_supply_apy", _fixed_supply_apy)

        op, asset, proto = _resolve_protocol_routing(
            _cv(TradeAction.BUY), "balanced", Decimal("1000")
        )
        assert proto in {"aave", "lido", "pendle"}
        expected = {
            "aave": ("SUPPLY", "USDC"),
            "lido": ("STAKE_ETH", "ETH"),
            "pendle": ("BUY_PT", "PT-yoUSD"),
        }
        assert (op, asset) == expected[proto]

    def test_routing_uses_async_realapy_path(self, monkeypatch) -> None:
        """[D5b] routing は sync compare() ではなく compare_async(実APY)を使う。"""
        import app.ai.optimizer.comparator as comp

        def _must_not_call_sync(self, **kwargs):
            raise AssertionError("routing は compare_async を使うべき (sync compare は禁止)")

        async def _compare_async(self, **kwargs):
            return _FakeComparison(Protocol.AAVE)

        monkeypatch.setattr(comp.StrategyComparator, "compare", _must_not_call_sync)
        monkeypatch.setattr(comp.StrategyComparator, "compare_async", _compare_async)
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        assert _resolve_protocol_routing(_cv(TradeAction.BUY), "conservative", Decimal("1000")) == (
            "SUPPLY",
            "USDC",
            "aave",
        )
