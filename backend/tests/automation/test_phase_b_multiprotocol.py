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
    import app.ai.optimizer.comparator as comp

    def _compare(self, **kwargs):
        if isinstance(protocol_or_exc, Exception):
            raise protocol_or_exc
        return _FakeComparison(protocol_or_exc)

    monkeypatch.setattr(comp.StrategyComparator, "compare", _compare)


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
            "PT-stETH",
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
            "PT-stETH",
            "pendle",
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
        """フラグ on で実 optimizer を通し、(operation, asset) が protocol と整合する。"""
        monkeypatch.setenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "true")
        op, asset, proto = _resolve_protocol_routing(
            _cv(TradeAction.BUY), "balanced", Decimal("1000")
        )
        assert proto in {"aave", "lido", "pendle"}
        expected = {
            "aave": ("SUPPLY", "USDC"),
            "lido": ("STAKE_ETH", "ETH"),
            "pendle": ("BUY_PT", "PT-stETH"),
        }
        assert (op, asset) == expected[proto]
