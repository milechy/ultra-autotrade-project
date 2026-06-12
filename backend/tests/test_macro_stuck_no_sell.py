# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Macro 軸単独 BEARISH 時の SELL 不発保証テスト (EPIC-1 1-13, docs/52 §4.4).

目的: SELL-spam #365 再発防止。
  Macro Agent が単独で強い BEARISH を示しても、4 軸 weighted score が
  SELL 閾値 -0.40 に届かないことを数値で保証する。
  加えて agreeing_count < 2 による降格ガードが Macro 軸優位シナリオでも
  正しく機能することを確認する。

Macro 軸の DEFAULT_WEIGHTS 重み = 0.20 (docs/52 §4.2):
  Macro 単独最大寄与 = 0.20 × 1.0 = 0.20 < 0.40 (SELL 閾値)
  → Macro 単独では閾値に到達不能（agreeing_count ガード到達前に HOLD）

カバレッジ:
  TC-1: Macro 単独 BEARISH 90 → score=-0.18 (閾値未満) → HOLD
  TC-2: TC-1 と同一入力の決定論性検証（複数呼出で同結果）
  TC-3: 対照系 — Risk + Macro が BEARISH 合意 (agreeing_count=2) → SELL 許可
  TC-4: Macro 重み 0.20 の物理的上限が SELL 閾値 0.40 未満であること
  TC-5: agreeing_count 降格ガードが Macro 軸優位カスタム重みでも動作すること
"""

from decimal import Decimal

from app.ai.agents import (
    AgentSignal,
    Bias,
    MultiAgentContext,
)
from app.ai.schemas import TradeAction

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _signal(name: str, bias: Bias, confidence: int) -> AgentSignal:
    return AgentSignal(
        agent_name=name,
        bias=bias,
        confidence=confidence,
        reasoning="test signal",
    )


def _make_ctx(
    indicator: tuple[Bias, int] | None = None,
    pattern: tuple[Bias, int] | None = None,
    risk: tuple[Bias, int] | None = None,
    macro: tuple[Bias, int] | None = None,
) -> MultiAgentContext:
    """(bias, confidence) タプルから MultiAgentContext を構築するヘルパー。"""
    return MultiAgentContext(
        indicator_signal=_signal("Indicator Agent", *indicator) if indicator else None,
        pattern_signal=_signal("Pattern Agent", *pattern) if pattern else None,
        risk_signal=_signal("Risk Agent", *risk) if risk else None,
        macro_signal=_signal("Macro Agent", *macro) if macro else None,
    )


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------


class TestMacroStuckNoSell:
    """Macro 軸単独 BEARISH で SELL が不発となることを保証するテスト群。

    SELL-spam #365 再発防止が目的 (docs/52 §4.4 single-agent runaway guard)。
    """

    def test_tc1_macro_only_bearish_does_not_sell(self) -> None:
        """TC-1: Macro 単独 BEARISH 90 は HOLD になること。

        score = 0.20 × (-1) × 0.90 = -0.180
        |-0.180| < score_threshold 0.40 → HOLD (閾値未達)。
        agreeing_count=1 だが降格ガード到達前に HOLD 決定済み。

        SELL-spam #365 が発生していたシナリオの直接的な再現: Macro Agent が
        連続して BEARISH を報告しているが他 3 軸は中立な局面。
        """
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 50),
            risk=(Bias.NEUTRAL, 50),
            macro=(Bias.BEARISH, 90),
        )
        verdict = ctx.evaluate_4axis_consensus()

        assert verdict.action == TradeAction.HOLD, (
            f"Macro 単独 BEARISH 90 では HOLD が期待されるが {verdict.action} が返った。"
            f" score={verdict.score}, agreeing_count={verdict.agreeing_count}"
        )
        assert verdict.score == Decimal("-0.1800"), f"score 期待値: -0.1800、実値: {verdict.score}"
        assert verdict.agreeing_count == 1, (
            f"Macro のみが agreeing すべきだが agreeing_count={verdict.agreeing_count}"
        )
        # SELL 閾値 0.40 に届いていないことを明示検証
        assert abs(verdict.score) < Decimal("0.40"), (
            f"Macro 単独の score 絶対値 {abs(verdict.score)} が SELL 閾値 0.40 以上。"
            " 重み設定に問題がある可能性あり。"
        )

    def test_tc2_macro_bearish_deterministic(self) -> None:
        """TC-2: 同一入力で evaluate_4axis_consensus を複数回呼んでも結果が一定であること。

        純関数であるため、同一入力からは常に同一の DeterministicVerdict を返す必要がある。
        非決定論的な挙動（乱数・外部呼出し依存など）がないことを確認する。
        """
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 50),
            risk=(Bias.NEUTRAL, 50),
            macro=(Bias.BEARISH, 90),
        )

        verdicts = [ctx.evaluate_4axis_consensus() for _ in range(5)]

        actions = {v.action for v in verdicts}
        scores = {v.score for v in verdicts}
        confs = {v.weighted_confidence for v in verdicts}
        counts = {v.agreeing_count for v in verdicts}

        assert actions == {TradeAction.HOLD}, f"複数回呼出で action が変動した: {actions}"
        assert len(scores) == 1, f"複数回呼出で score が変動した: {scores}"
        assert len(confs) == 1, f"複数回呼出で weighted_confidence が変動した: {confs}"
        assert len(counts) == 1, f"複数回呼出で agreeing_count が変動した: {counts}"

    def test_tc3_macro_plus_risk_bearish_allows_sell(self) -> None:
        """TC-3: 対照系 — Risk + Macro が BEARISH 合意のとき SELL が許可されること。

        agreeing_count >= 2 の場合に降格ガードが不作動であることを確認する。
        ガードが過剰適用されていないこと（SELL 経路が完全封鎖されていないこと）の保証。

        score = 0.40×(-1)×0.80 + 0.20×(-1)×0.80 = -0.32 - 0.16 = -0.4800
        conf = 0.40×80 + 0.20×80 + 0.25×50 + 0.15×50 = 32+16+12.5+7.5 = 68
        agreeing_count: Risk(conf=80>=50) + Macro(conf=80>=50) = 2
        score=-0.48 <= -0.40 and conf=68 >= 65 → SELL、agreeing_count=2 で降格なし。
        """
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 50),
            risk=(Bias.BEARISH, 80),
            macro=(Bias.BEARISH, 80),
        )
        verdict = ctx.evaluate_4axis_consensus()

        assert verdict.action == TradeAction.SELL, (
            f"Risk+Macro BEARISH 80 (agreeing_count=2) では SELL が期待されるが"
            f" {verdict.action} が返った。score={verdict.score}, conf={verdict.weighted_confidence},"
            f" agreeing_count={verdict.agreeing_count}"
        )
        assert verdict.score == Decimal("-0.4800"), f"score 期待値: -0.4800、実値: {verdict.score}"
        assert verdict.weighted_confidence == 68, (
            f"conf 期待値: 68、実値: {verdict.weighted_confidence}"
        )
        assert verdict.agreeing_count == 2, (
            f"Risk+Macro が合意するため agreeing_count=2 が期待されるが"
            f" agreeing_count={verdict.agreeing_count}"
        )
        assert "Demoted" not in verdict.reasoning, (
            "agreeing_count=2 では降格が発生すべきではないが Demoted が reasoning に含まれる"
        )

    def test_tc4_macro_weight_cannot_reach_sell_threshold(self) -> None:
        """TC-4: DEFAULT_WEIGHTS で Macro 単独の最大 score 寄与が SELL 閾値 0.40 未満であること。

        docs/52 §4.2: Macro 重み = 0.20
        最大寄与 = 0.20 × 1.0 × 1.0 = 0.20 < 0.40 (score_threshold)

        これは重みが変更されない限り Macro 単独 BEARISH では SELL になれないことの
        数学的保証。重み設定が意図通り維持されていることをテストとして固定する。
        """
        weights = MultiAgentContext.DEFAULT_WEIGHTS

        macro_weight = weights["macro"]
        # Macro 単独最大寄与: weight × 1.0 (direction) × 1.0 (conf=100%)
        macro_max_contribution = macro_weight * Decimal("1.0")

        default_score_threshold = Decimal("0.40")
        assert macro_max_contribution < default_score_threshold, (
            f"Macro 重み {macro_weight} の最大寄与 {macro_max_contribution} が"
            f" SELL 閾値 {default_score_threshold} 以上になっている。"
            " docs/52 §4.2 の重み設定が変更されたか確認すること。"
        )

        # conf=100 の場合も実際に HOLD になることを確認
        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 50),
            risk=(Bias.NEUTRAL, 50),
            macro=(Bias.BEARISH, 100),
        )
        verdict = ctx.evaluate_4axis_consensus()
        assert verdict.action == TradeAction.HOLD, (
            f"Macro BEARISH 100 (最大 confidence) でも HOLD が期待されるが {verdict.action}"
        )
        assert verdict.score == Decimal("-0.20"), (
            f"Macro BEARISH 100 の score 期待値: -0.20、実値: {verdict.score}"
        )

    def test_tc5_agreeing_count_demotion_with_macro_dominant_weights(self) -> None:
        """TC-5: Macro 軸優位カスタム重みで agreeing_count 降格ガードが動作すること。

        カスタム重み (risk=0.10, indicator=0.10, macro=0.60, pattern=0.20) を使用し、
        Macro BEARISH 80 が score 閾値を超えても agreeing_count=1 で HOLD に降格されること。

        score = 0.60 × (-1) × 0.80 = -0.4800  (<= -0.40 → 閾値超過)
        conf = 0.10×50 + 0.10×50 + 0.60×80 + 0.20×50 = 5+5+48+10 = 68  (>= 65)
        agreeing_count: Macro のみ (dir=-1, score=-0.48 < 0 → direction*score > 0, conf=80>=50) = 1
          → 他 3 軸は NEUTRAL (direction=0) → direction*score = 0 → not > 0
        agreeing_count=1 < 2 → HOLD 降格 (single-agent runaway guard)
        """
        custom_weights: dict[str, Decimal] = {
            "risk": Decimal("0.10"),
            "indicator": Decimal("0.10"),
            "macro": Decimal("0.60"),
            "pattern": Decimal("0.20"),
        }

        ctx = _make_ctx(
            indicator=(Bias.NEUTRAL, 50),
            pattern=(Bias.NEUTRAL, 50),
            risk=(Bias.NEUTRAL, 50),
            macro=(Bias.BEARISH, 80),
        )
        verdict = ctx.evaluate_4axis_consensus(weights=custom_weights)

        assert verdict.score == Decimal("-0.4800"), (
            f"カスタム重みでの score 期待値: -0.4800、実値: {verdict.score}"
        )
        assert verdict.weighted_confidence == 68, (
            f"カスタム重みでの conf 期待値: 68、実値: {verdict.weighted_confidence}"
        )
        assert verdict.agreeing_count == 1, (
            f"Macro のみ agreeing のため agreeing_count=1 が期待されるが {verdict.agreeing_count}"
        )
        assert verdict.action == TradeAction.HOLD, (
            f"agreeing_count=1 の降格ガードで HOLD が期待されるが {verdict.action}"
        )
        assert "Demoted" in verdict.reasoning, (
            "agreeing_count < 2 による降格が発生しているため reasoning に 'Demoted' が含まれるべき"
        )
        # per_agent_contribution が 4 軸全て含まれること
        assert set(verdict.per_agent_contribution.keys()) == {
            "risk",
            "indicator",
            "macro",
            "pattern",
        }
        macro_contrib = verdict.per_agent_contribution["macro"]
        assert macro_contrib.direction == -1
        assert macro_contrib.confidence == 80
        assert macro_contrib.weight == Decimal("0.60")
        assert macro_contrib.contribution == Decimal("-0.4800")
