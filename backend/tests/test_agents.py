# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for multi-agent AI judgment system."""

from decimal import Decimal

import pytest

from app.ai.agents import (
    AgentSignal,
    Bias,
    MultiAgentContext,
    indicator_agent,
    macro_agent,
    pattern_agent,
    risk_agent,
    run_all_agents,
)
from app.ai.judgment_log import CognitiveState
from app.data_feeds.context import build_market_context
from app.data_feeds.finance_feed import FinanceFeedResult
from app.data_feeds.geopolitical import GeoRiskResult
from app.data_feeds.news_feed import NewsFeedResult


class TestIndicatorAgent:
    def test_low_hf_is_bearish(self) -> None:
        ctx = build_market_context(health_factor=Decimal("1.45"))
        signal = indicator_agent(ctx)
        assert signal.bias == Bias.BEARISH
        assert "critically low" in signal.reasoning.lower()

    def test_high_hf_is_bullish(self) -> None:
        ctx = build_market_context(health_factor=Decimal("2.5"))
        signal = indicator_agent(ctx)
        assert signal.bias == Bias.BULLISH
        assert "buffer" in signal.reasoning.lower()

    def test_no_data_is_neutral(self) -> None:
        ctx = build_market_context()
        signal = indicator_agent(ctx)
        assert signal.bias == Bias.NEUTRAL

    def test_high_utilization_is_bearish(self) -> None:
        ctx = build_market_context(
            health_factor=Decimal("1.9"),
            aave_utilization_rate=Decimal("92"),
        )
        signal = indicator_agent(ctx)
        assert "liquidity pressure" in signal.reasoning.lower()

    def test_attractive_supply_apy(self) -> None:
        ctx = build_market_context(
            health_factor=Decimal("2.1"),
            aave_supply_apy=Decimal("6.5"),
        )
        signal = indicator_agent(ctx)
        assert "attractive yield" in signal.reasoning.lower()

    # ------------------------------------------------------------------
    # Neutral-stuck mitigation tests (2026-05-27)
    # The v4/v5 AND-condition requires Indicator confidence ≥ 70 with a
    # directional bias. Pre-fix, the dominant "moderately good / moderately
    # tight" Aave market band produced NEUTRAL conf=50, which silently
    # blocked every SELL/BUY at the rule engine and pinned soak HOLD ~100%.
    # These tests pin the post-fix behaviour for that band.
    # ------------------------------------------------------------------

    def test_moderately_tight_market_yields_directional_signal(self) -> None:
        """Typical staging-soak shape: HF 1.7 / util 72 / APY 4 → was NEUTRAL/50.

        Must now produce a BEARISH bias with confidence high enough to clear
        the v4/v5 AND-condition (≥70). This is the headline regression guard.
        """
        ctx = build_market_context(
            health_factor=Decimal("1.7"),
            aave_utilization_rate=Decimal("72"),
            aave_supply_apy=Decimal("4.0"),
        )
        signal = indicator_agent(ctx)
        assert signal.bias == Bias.BEARISH
        assert signal.confidence >= 70

    def test_moderately_comfortable_market_yields_directional_signal(self) -> None:
        """Mirror case: HF 2.15 / util 40 / APY 4 → should clear BULLISH ≥70."""
        ctx = build_market_context(
            health_factor=Decimal("2.15"),
            aave_utilization_rate=Decimal("40"),
            aave_supply_apy=Decimal("4.0"),
        )
        signal = indicator_agent(ctx)
        assert signal.bias == Bias.BULLISH
        assert signal.confidence >= 70

    def test_hf_2_0_boundary_is_smooth(self) -> None:
        """HF 1.99 vs 2.00 must not produce a -25 step-function in score.

        Pre-fix: HF=1.99 → -10, HF=2.00 → +15 (Δ=25 on 0.01 input change),
        causing flapping between NEUTRAL and BULLISH at the boundary.
        Post-fix: both fall in the 1.9-2.1 band → identical contribution.
        """
        same_other = {
            "aave_utilization_rate": Decimal("65"),
            "aave_supply_apy": Decimal("3.0"),
        }
        sig_lo = indicator_agent(build_market_context(health_factor=Decimal("1.99"), **same_other))
        sig_hi = indicator_agent(build_market_context(health_factor=Decimal("2.00"), **same_other))
        assert sig_lo.bias == sig_hi.bias
        assert abs(sig_lo.confidence - sig_hi.confidence) <= 5

    def test_yield_compression_is_mildly_bearish(self) -> None:
        """Supply APY < 1% (yield compressed) contributes a mild bearish nudge."""
        ctx = build_market_context(
            health_factor=Decimal("2.05"),
            aave_supply_apy=Decimal("0.5"),
        )
        signal = indicator_agent(ctx)
        assert signal.key_data.get("supply_apy") == "0.5"
        assert "compressed" in signal.reasoning.lower() or "weak demand" in signal.reasoning.lower()

    # ------------------------------------------------------------------
    # HF=inf (借入なし) の伝播テスト (2026-05-29)
    # _fetch_health_factor が inf を None に潰していたバグ修正に対応。
    # inf → score+22 → BULLISH が通ることを確認する。
    # ------------------------------------------------------------------

    def test_inf_hf_no_borrowing_scores_ample_buffer(self) -> None:
        """HF=inf (借入なし=清算リスクゼロ) は score+22 で BULLISH を生成すること。

        修正前: _fetch_health_factor が Decimal("inf") を None に潰す
          → indicator_agent は hf=None として処理 → score に HF 寄与なし
          → util=50%/APY=3% の典型入力で NEUTRAL になり BUY ゲートを通過できない。
        修正後: inf がそのまま伝播 → MarketContext で 999.0 に変換
          → hf_float=999.0 >= 2.5 → else 分岐で score+22
          → 同入力で BULLISH → BUY 通過可。
        MarketContext.cap_infinity_hf が inf → 999.0 に変換するため、
        build_market_context(health_factor=Decimal("inf")) は ctx.health_factor=999.0 になる。
        """
        ctx = build_market_context(
            health_factor=Decimal("inf"),
            aave_utilization_rate=Decimal("50"),
            aave_supply_apy=Decimal("3.0"),
        )
        assert ctx.health_factor == Decimal("999.0"), (
            f"MarketContext は inf を 999.0 に変換するべき (got {ctx.health_factor})"
        )
        signal = indicator_agent(ctx)
        assert signal.bias == Bias.BULLISH, (
            f"HF=inf (借入なし) は BULLISH になるべき (got {signal.bias})"
        )
        assert signal.confidence >= 70, (
            f"HF=inf シナリオは confidence >= 70 が必要 (got {signal.confidence})"
        )
        assert "buffer" in signal.reasoning.lower(), (
            f"HF=999 の reasoning に 'buffer' が含まれるべき: {signal.reasoning}"
        )

    def test_inf_hf_is_distinct_from_none_hf(self) -> None:
        """HF=inf (借入なし) と HF=None (取得失敗) は異なる score を生成すること。

        None: score に HF 寄与なし → util/APY のみで判定
        inf (→999.0): score+22 → 同 util/APY でも BULLISH に傾く
        """
        same_other = {
            "aave_utilization_rate": Decimal("50"),
            "aave_supply_apy": Decimal("3.0"),
        }
        sig_inf = indicator_agent(build_market_context(health_factor=Decimal("inf"), **same_other))
        sig_none = indicator_agent(build_market_context(health_factor=None, **same_other))
        assert sig_inf.bias != sig_none.bias or sig_inf.confidence > sig_none.confidence, (
            "inf と None は異なるスコア/バイアスになるべき"
        )
        assert sig_inf.bias == Bias.BULLISH, (
            f"inf シナリオは BULLISH になるべき (got {sig_inf.bias})"
        )

    # ------------------------------------------------------------------
    # Technical (price momentum) signal (2026-07-06 — HOLD脱却プロジェクト A)
    # RSI+MAクロス(app.ai.prefilter.run_prefilter)由来。
    # kill switch AI_INDICATOR_MOMENTUM_ENABLED は既定OFF。
    # ------------------------------------------------------------------

    def test_technical_signal_disabled_by_default_is_a_noop(self) -> None:
        """flag未設定(既定false)なら technical_signal があってもスコアは不変であること。"""
        ctx_with_signal = build_market_context(
            health_factor=Decimal("2.6"),
            aave_utilization_rate=Decimal("75"),
            technical_signal="BUY_LEAN",
        )
        ctx_without_signal = build_market_context(
            health_factor=Decimal("2.6"),
            aave_utilization_rate=Decimal("75"),
        )
        sig_with = indicator_agent(ctx_with_signal)
        sig_without = indicator_agent(ctx_without_signal)
        assert sig_with.confidence == sig_without.confidence
        assert sig_with.bias == sig_without.bias
        assert "technical_signal" not in sig_with.key_data

    def test_technical_signal_noop_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """flag ONでも technical_signal=None(取得失敗)なら fail-open で不変であること。"""
        monkeypatch.setenv("AI_INDICATOR_MOMENTUM_ENABLED", "true")
        ctx = build_market_context(
            health_factor=Decimal("2.6"), aave_utilization_rate=Decimal("75")
        )
        signal = indicator_agent(ctx)
        assert "technical_signal" not in signal.key_data

    def test_buy_lean_pushes_stuck_confidence_over_70(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """本番実測(HF=2.6/util=75→score68/conf66%)がBUY_LEANで70超えを確認。

        docs記載の「あと2ptでHOLD固着」ケースを再現し、テクニカルシグナル追加で
        v4/v5 AND-conditionの閾値(confidence>=70)を実際に越えられることを検証する。
        """
        monkeypatch.setenv("AI_INDICATOR_MOMENTUM_ENABLED", "true")
        base_ctx = build_market_context(
            health_factor=Decimal("2.6"), aave_utilization_rate=Decimal("75")
        )
        boosted_ctx = build_market_context(
            health_factor=Decimal("2.6"),
            aave_utilization_rate=Decimal("75"),
            technical_signal="BUY_LEAN",
        )
        base_signal = indicator_agent(base_ctx)
        boosted_signal = indicator_agent(boosted_ctx)
        assert base_signal.confidence < 70, (
            f"前提が崩れている(シグナル無しで既に70超え): {base_signal.confidence}"
        )
        assert boosted_signal.bias == Bias.BULLISH
        assert boosted_signal.confidence >= 70
        assert boosted_signal.key_data["technical_signal"] == "BUY_LEAN"

    def test_sell_lean_flips_neutral_to_bearish(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """NEUTRAL(score40)がSELL_LEANでBEARISH/confidence>=70に転じることを確認。"""
        monkeypatch.setenv("AI_INDICATOR_MOMENTUM_ENABLED", "true")
        base_ctx = build_market_context(
            health_factor=Decimal("1.85"), aave_utilization_rate=Decimal("75")
        )
        boosted_ctx = build_market_context(
            health_factor=Decimal("1.85"),
            aave_utilization_rate=Decimal("75"),
            technical_signal="SELL_LEAN",
        )
        base_signal = indicator_agent(base_ctx)
        boosted_signal = indicator_agent(boosted_ctx)
        assert base_signal.bias == Bias.NEUTRAL
        assert boosted_signal.bias == Bias.BEARISH
        assert boosted_signal.confidence >= 70

    def test_insufficient_data_signal_is_a_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """technical_signal="INSUFFICIENT_DATA"(prefilterのfail-open値)はスコア不変であること。"""
        monkeypatch.setenv("AI_INDICATOR_MOMENTUM_ENABLED", "true")
        base_ctx = build_market_context(
            health_factor=Decimal("2.6"), aave_utilization_rate=Decimal("75")
        )
        ctx = build_market_context(
            health_factor=Decimal("2.6"),
            aave_utilization_rate=Decimal("75"),
            technical_signal="INSUFFICIENT_DATA",
        )
        assert indicator_agent(ctx).confidence == indicator_agent(base_ctx).confidence


class TestPatternAgent:
    def test_no_history_is_neutral(self) -> None:
        ctx = build_market_context(cognitive_state=CognitiveState())
        signal = pattern_agent(ctx)
        assert signal.bias == Bias.NEUTRAL
        assert signal.confidence <= 40

    def test_no_cognitive_state_is_neutral(self) -> None:
        ctx = build_market_context()
        signal = pattern_agent(ctx)
        assert signal.bias == Bias.NEUTRAL
        assert "No judgment history" in signal.reasoning

    def test_consecutive_holds_suggests_action(self) -> None:
        cs = CognitiveState(
            total_judgments=10,
            consecutive_holds=6,
            recent_actions=["HOLD", "HOLD", "HOLD", "HOLD", "HOLD"],
        )
        ctx = build_market_context(cognitive_state=cs)
        signal = pattern_agent(ctx)
        assert signal.bias == Bias.BULLISH
        assert "normalized" in signal.reasoning.lower()

    def test_flip_flop_detected(self) -> None:
        cs = CognitiveState(
            total_judgments=5,
            consecutive_holds=0,
            recent_actions=["BUY", "SELL", "HOLD"],
        )
        ctx = build_market_context(cognitive_state=cs)
        signal = pattern_agent(ctx)
        assert signal.bias == Bias.NEUTRAL
        assert "flip-flopping" in signal.reasoning.lower()

    def test_low_win_rate_increases_caution(self) -> None:
        cs = CognitiveState(
            total_judgments=20,
            consecutive_holds=1,
            win_rate=0.3,
            recent_actions=["HOLD"],
        )
        ctx = build_market_context(cognitive_state=cs)
        signal = pattern_agent(ctx)
        assert "below target" in signal.reasoning.lower()

    def test_high_win_rate_increases_confidence(self) -> None:
        cs = CognitiveState(
            total_judgments=20,
            consecutive_holds=0,
            win_rate=0.8,
            recent_actions=["BUY"],
        )
        ctx = build_market_context(cognitive_state=cs)
        signal = pattern_agent(ctx)
        assert "strong" in signal.reasoning.lower()


class TestRiskAgent:
    def test_high_geo_risk_is_bearish(self) -> None:
        geo = GeoRiskResult(geo_risk_score=85, summary="Major conflict in Middle East")
        ctx = build_market_context(geo_risk=geo)
        signal = risk_agent(ctx)
        assert signal.bias == Bias.BEARISH
        assert signal.confidence >= 50

    def test_low_risk_is_bullish(self) -> None:
        geo = GeoRiskResult(geo_risk_score=15, summary="Stable environment")
        fin = FinanceFeedResult(stablecoin_risk="low")
        ctx = build_market_context(geo_risk=geo, finance=fin)
        signal = risk_agent(ctx)
        assert signal.bias == Bias.BULLISH

    def test_compound_risk(self) -> None:
        geo = GeoRiskResult(geo_risk_score=75, summary="Elevated tensions")
        ctx = build_market_context(geo_risk=geo, health_factor=Decimal("1.65"))
        signal = risk_agent(ctx)
        assert signal.bias == Bias.BEARISH
        assert "compound risk" in signal.reasoning.lower()

    def test_high_stablecoin_risk(self) -> None:
        fin = FinanceFeedResult(stablecoin_risk="high")
        ctx = build_market_context(finance=fin)
        signal = risk_agent(ctx)
        assert "depeg" in signal.reasoning.lower()

    def test_stable_environment_is_bullish(self) -> None:
        geo = GeoRiskResult(geo_risk_score=20, summary="Calm markets")
        fin = FinanceFeedResult(stablecoin_risk="low")
        ctx = build_market_context(geo_risk=geo, finance=fin)
        signal = risk_agent(ctx)
        assert signal.bias == Bias.BULLISH


class TestMacroAgent:
    def test_dovish_fed_is_bullish(self) -> None:
        fin = FinanceFeedResult(
            fed_stance="dovish",
            macro_summary="FED cuts rates to support growth",
        )
        ctx = build_market_context(finance=fin)
        signal = macro_agent(ctx)
        assert signal.bias == Bias.BULLISH
        assert "dovish" in signal.reasoning.lower()

    def test_hawkish_fed_with_negative_news_is_bearish(self) -> None:
        fin = FinanceFeedResult(
            fed_stance="hawkish",
            macro_summary="FED raises rates to fight inflation",
        )
        news = NewsFeedResult(sentiment="negative", summary="Markets drop on rate hike fears")
        ctx = build_market_context(finance=fin, news=news)
        signal = macro_agent(ctx)
        assert signal.bias == Bias.BEARISH

    def test_positive_news_is_bullish(self) -> None:
        news = NewsFeedResult(
            sentiment="positive", summary="ETH rally continues amid institutional buying"
        )
        ctx = build_market_context(news=news)
        signal = macro_agent(ctx)
        assert "positive" in signal.reasoning.lower()

    def test_no_data_is_neutral(self) -> None:
        ctx = build_market_context()
        signal = macro_agent(ctx)
        assert signal.bias == Bias.NEUTRAL


class TestMultiAgentOrchestrator:
    def test_run_all_agents_returns_all_signals(self) -> None:
        geo = GeoRiskResult(geo_risk_score=40, summary="Moderate tensions")
        fin = FinanceFeedResult(fed_stance="neutral", stablecoin_risk="low")
        ctx = build_market_context(
            health_factor=Decimal("1.85"),
            geo_risk=geo,
            finance=fin,
        )
        result = run_all_agents(ctx)
        assert result.indicator_signal is not None
        assert result.pattern_signal is not None
        assert result.risk_signal is not None
        assert result.macro_signal is not None

    def test_consensus_bias_bullish(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=AgentSignal(
                agent_name="I", bias=Bias.BULLISH, confidence=70, reasoning=""
            ),
            pattern_signal=AgentSignal(
                agent_name="P", bias=Bias.BULLISH, confidence=60, reasoning=""
            ),
            risk_signal=AgentSignal(agent_name="R", bias=Bias.BULLISH, confidence=65, reasoning=""),
            macro_signal=AgentSignal(
                agent_name="M", bias=Bias.NEUTRAL, confidence=50, reasoning=""
            ),
        )
        assert mac.consensus_bias() == Bias.BULLISH

    def test_consensus_bias_bearish(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=AgentSignal(
                agent_name="I", bias=Bias.BEARISH, confidence=70, reasoning=""
            ),
            pattern_signal=AgentSignal(
                agent_name="P", bias=Bias.BEARISH, confidence=60, reasoning=""
            ),
            risk_signal=AgentSignal(agent_name="R", bias=Bias.NEUTRAL, confidence=50, reasoning=""),
            macro_signal=AgentSignal(
                agent_name="M", bias=Bias.BEARISH, confidence=50, reasoning=""
            ),
        )
        assert mac.consensus_bias() == Bias.BEARISH

    def test_consensus_bias_neutral_when_mixed(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=AgentSignal(
                agent_name="I", bias=Bias.BULLISH, confidence=70, reasoning=""
            ),
            macro_signal=AgentSignal(
                agent_name="M", bias=Bias.BEARISH, confidence=70, reasoning=""
            ),
        )
        assert mac.consensus_bias() == Bias.NEUTRAL

    def test_decision_prompt_format(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=AgentSignal(
                agent_name="Indicator Agent",
                bias=Bias.BULLISH,
                confidence=70,
                reasoning="HF is healthy",
                key_data={"health_factor": "1.85"},
            ),
            risk_signal=AgentSignal(
                agent_name="Risk Agent",
                bias=Bias.NEUTRAL,
                confidence=50,
                reasoning="Moderate risk",
            ),
        )
        prompt = mac.to_decision_prompt()
        assert "Indicator Agent" in prompt
        assert "Risk Agent" in prompt
        assert "bullish" in prompt
        assert "1.85" in prompt

    def test_average_confidence(self) -> None:
        mac = MultiAgentContext(
            indicator_signal=AgentSignal(
                agent_name="I", bias=Bias.BULLISH, confidence=80, reasoning=""
            ),
            risk_signal=AgentSignal(agent_name="R", bias=Bias.NEUTRAL, confidence=60, reasoning=""),
        )
        assert mac.average_confidence() == 70

    def test_empty_context_average_confidence(self) -> None:
        mac = MultiAgentContext()
        assert mac.average_confidence() == 50

    def test_cognitive_state_in_prompt(self) -> None:
        cs = CognitiveState(
            total_judgments=5,
            last_action="BUY",
            last_confidence=75,
        )
        mac = MultiAgentContext(
            indicator_signal=AgentSignal(
                agent_name="I", bias=Bias.BULLISH, confidence=70, reasoning="test"
            ),
            cognitive_state=cs,
        )
        prompt = mac.to_decision_prompt()
        assert "Decision History" in prompt


class TestV3PromptIntegration:
    """Test that multi-agent signals flow into the LLM prompt."""

    def test_decision_prompt_all_agents(self) -> None:
        geo = GeoRiskResult(geo_risk_score=45, summary="Moderate tensions")
        fin = FinanceFeedResult(fed_stance="dovish", stablecoin_risk="low")
        news = NewsFeedResult(sentiment="positive", summary="ETH rally continues")
        cs = CognitiveState(
            total_judgments=10,
            last_action="HOLD",
            last_confidence=40,
            consecutive_holds=3,
            recent_actions=["HOLD", "HOLD", "HOLD"],
        )
        ctx = build_market_context(
            health_factor=Decimal("1.85"),
            geo_risk=geo,
            finance=fin,
            news=news,
            cognitive_state=cs,
        )
        mac = run_all_agents(ctx)
        prompt = mac.to_decision_prompt()

        assert "Indicator Agent" in prompt
        assert "Pattern Agent" in prompt
        assert "Risk Agent" in prompt
        assert "Macro Agent" in prompt
        assert "dovish" in prompt

    def test_bearish_consensus_detected(self) -> None:
        geo = GeoRiskResult(geo_risk_score=85, summary="Major conflict")
        fin = FinanceFeedResult(fed_stance="hawkish", stablecoin_risk="high")
        news = NewsFeedResult(sentiment="negative", summary="Market crash fears")
        ctx = build_market_context(
            health_factor=Decimal("1.55"),
            geo_risk=geo,
            finance=fin,
            news=news,
        )
        mac = run_all_agents(ctx)
        assert mac.risk_signal is not None and mac.risk_signal.bias == Bias.BEARISH
        assert mac.indicator_signal is not None and mac.indicator_signal.bias == Bias.BEARISH
        assert mac.macro_signal is not None and mac.macro_signal.bias == Bias.BEARISH
        assert mac.consensus_bias() == Bias.BEARISH

    def test_bullish_consensus_detected(self) -> None:
        geo = GeoRiskResult(geo_risk_score=15, summary="Stable environment")
        fin = FinanceFeedResult(fed_stance="dovish", stablecoin_risk="low")
        news = NewsFeedResult(sentiment="positive", summary="Bull run confirmed")
        ctx = build_market_context(
            health_factor=Decimal("2.5"),
            geo_risk=geo,
            finance=fin,
            news=news,
        )
        mac = run_all_agents(ctx)
        assert mac.indicator_signal is not None and mac.indicator_signal.bias == Bias.BULLISH
        assert mac.macro_signal is not None and mac.macro_signal.bias == Bias.BULLISH
        assert mac.consensus_bias() == Bias.BULLISH
