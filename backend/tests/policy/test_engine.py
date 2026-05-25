# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/policy/test_engine.py
"""Tests for `app.policy.engine` (P0-7 MVP).

純粋関数の Policy Engine の rule 単位 + evaluate 集約挙動を網羅。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.policy import (
    DEFAULT_RULES,
    PolicyDecision,
    TransactionContext,
    Verdict,
    evaluate,
)
from app.policy.engine import (
    rule_amount_positive,
    rule_cooldown,
    rule_daily_cap,
    rule_emergency_stop,
    rule_health_factor,
    rule_oracle_freshness,
    rule_recipient_allowlist,
    rule_single_trade_cap,
)

_NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
_OK_RECIPIENT = "0xabc0000000000000000000000000000000000001"


def _ctx(**overrides) -> TransactionContext:
    """安全側 default を持つ context factory。

    overrides を渡さなければ全 rule が pass する。
    """
    base = dict(
        user_id=1,
        amount_usd=Decimal("100"),
        recipient_address=_OK_RECIPIENT,
        recipient_allowlist=frozenset({_OK_RECIPIENT}),
        health_factor=Decimal("2.0"),
        min_health_factor=Decimal("1.6"),
        daily_traded_usd=Decimal("0"),
        daily_cap_usd=Decimal("1000"),
        single_trade_cap_usd=Decimal("500"),
        cooldown_until=None,
        now=_NOW,
        oracle_updated_at=_NOW - timedelta(seconds=60),
        oracle_max_staleness_sec=300,
        emergency_stop=False,
    )
    base.update(overrides)
    return TransactionContext(**base)


# ──────────────────────────────────────────────────────────────
# rule 単体
# ──────────────────────────────────────────────────────────────


class TestRuleEmergencyStop:
    def test_off_returns_none(self) -> None:
        assert rule_emergency_stop(_ctx(emergency_stop=False)) is None

    def test_on_returns_deny(self) -> None:
        result = rule_emergency_stop(_ctx(emergency_stop=True))
        assert result is not None
        verdict, msg = result
        assert verdict is Verdict.DENY
        assert "emergency_stop" in msg


class TestRuleAmountPositive:
    def test_positive_pass(self) -> None:
        assert rule_amount_positive(_ctx(amount_usd=Decimal("1"))) is None

    def test_zero_denied(self) -> None:
        result = rule_amount_positive(_ctx(amount_usd=Decimal("0")))
        assert result is not None
        assert result[0] is Verdict.DENY

    def test_negative_denied(self) -> None:
        result = rule_amount_positive(_ctx(amount_usd=Decimal("-1")))
        assert result is not None
        assert result[0] is Verdict.DENY


class TestRuleHealthFactor:
    def test_above_min_passes(self) -> None:
        assert (
            rule_health_factor(_ctx(health_factor=Decimal("2.0"), min_health_factor=Decimal("1.6")))
            is None
        )

    def test_at_min_passes(self) -> None:
        # 等値はギリギリ pass (< のみ NG)
        assert (
            rule_health_factor(_ctx(health_factor=Decimal("1.6"), min_health_factor=Decimal("1.6")))
            is None
        )

    def test_below_min_denied(self) -> None:
        result = rule_health_factor(
            _ctx(health_factor=Decimal("1.5"), min_health_factor=Decimal("1.6"))
        )
        assert result is not None
        verdict, msg = result
        assert verdict is Verdict.DENY
        assert "1.5" in msg and "1.6" in msg


class TestRuleSingleTradeCap:
    def test_zero_cap_skipped(self) -> None:
        assert (
            rule_single_trade_cap(
                _ctx(amount_usd=Decimal("1000"), single_trade_cap_usd=Decimal("0"))
            )
            is None
        )

    def test_under_cap_passes(self) -> None:
        assert (
            rule_single_trade_cap(
                _ctx(amount_usd=Decimal("499"), single_trade_cap_usd=Decimal("500"))
            )
            is None
        )

    def test_at_cap_passes(self) -> None:
        assert (
            rule_single_trade_cap(
                _ctx(amount_usd=Decimal("500"), single_trade_cap_usd=Decimal("500"))
            )
            is None
        )

    def test_over_cap_denied(self) -> None:
        result = rule_single_trade_cap(
            _ctx(amount_usd=Decimal("501"), single_trade_cap_usd=Decimal("500"))
        )
        assert result is not None
        assert result[0] is Verdict.DENY


class TestRuleDailyCap:
    def test_zero_cap_skipped(self) -> None:
        assert (
            rule_daily_cap(
                _ctx(
                    amount_usd=Decimal("100000"),
                    daily_traded_usd=Decimal("100000"),
                    daily_cap_usd=Decimal("0"),
                )
            )
            is None
        )

    def test_projected_under_cap_passes(self) -> None:
        assert (
            rule_daily_cap(
                _ctx(
                    amount_usd=Decimal("100"),
                    daily_traded_usd=Decimal("800"),
                    daily_cap_usd=Decimal("1000"),
                )
            )
            is None
        )

    def test_projected_at_cap_passes(self) -> None:
        assert (
            rule_daily_cap(
                _ctx(
                    amount_usd=Decimal("200"),
                    daily_traded_usd=Decimal("800"),
                    daily_cap_usd=Decimal("1000"),
                )
            )
            is None
        )

    def test_projected_over_cap_denied(self) -> None:
        result = rule_daily_cap(
            _ctx(
                amount_usd=Decimal("201"),
                daily_traded_usd=Decimal("800"),
                daily_cap_usd=Decimal("1000"),
            )
        )
        assert result is not None
        assert result[0] is Verdict.DENY


class TestRuleCooldown:
    def test_none_passes(self) -> None:
        assert rule_cooldown(_ctx(cooldown_until=None)) is None

    def test_past_cooldown_passes(self) -> None:
        past = _NOW - timedelta(seconds=1)
        assert rule_cooldown(_ctx(cooldown_until=past)) is None

    def test_at_cooldown_passes(self) -> None:
        # now == cooldown_until は OK (< のみ NG)
        assert rule_cooldown(_ctx(cooldown_until=_NOW)) is None

    def test_active_cooldown_held(self) -> None:
        future = _NOW + timedelta(seconds=60)
        result = rule_cooldown(_ctx(cooldown_until=future))
        assert result is not None
        assert result[0] is Verdict.HOLD


class TestRuleOracleFreshness:
    def test_unknown_held(self) -> None:
        result = rule_oracle_freshness(_ctx(oracle_updated_at=None))
        assert result is not None
        assert result[0] is Verdict.HOLD

    def test_fresh_passes(self) -> None:
        fresh = _NOW - timedelta(seconds=100)
        assert (
            rule_oracle_freshness(_ctx(oracle_updated_at=fresh, oracle_max_staleness_sec=300))
            is None
        )

    def test_at_threshold_passes(self) -> None:
        at = _NOW - timedelta(seconds=300)
        assert (
            rule_oracle_freshness(_ctx(oracle_updated_at=at, oracle_max_staleness_sec=300)) is None
        )

    def test_stale_held(self) -> None:
        stale = _NOW - timedelta(seconds=301)
        result = rule_oracle_freshness(_ctx(oracle_updated_at=stale, oracle_max_staleness_sec=300))
        assert result is not None
        assert result[0] is Verdict.HOLD


class TestRuleRecipientAllowlist:
    def test_empty_allowlist_skipped(self) -> None:
        assert (
            rule_recipient_allowlist(
                _ctx(
                    recipient_address="0xdeadbeef",
                    recipient_allowlist=frozenset(),
                )
            )
            is None
        )

    def test_in_allowlist_passes(self) -> None:
        assert (
            rule_recipient_allowlist(
                _ctx(
                    recipient_address=_OK_RECIPIENT,
                    recipient_allowlist=frozenset({_OK_RECIPIENT}),
                )
            )
            is None
        )

    def test_case_insensitive_match(self) -> None:
        # ctx 側に upper-case で来ても allowlist (lower) と一致する
        assert (
            rule_recipient_allowlist(
                _ctx(
                    recipient_address=_OK_RECIPIENT.upper(),
                    recipient_allowlist=frozenset({_OK_RECIPIENT}),
                )
            )
            is None
        )

    def test_not_in_allowlist_denied(self) -> None:
        result = rule_recipient_allowlist(
            _ctx(
                recipient_address="0xbad0000000000000000000000000000000000002",
                recipient_allowlist=frozenset({_OK_RECIPIENT}),
            )
        )
        assert result is not None
        assert result[0] is Verdict.DENY


# ──────────────────────────────────────────────────────────────
# evaluate 集約
# ──────────────────────────────────────────────────────────────


class TestEvaluate:
    def test_all_pass_allows(self) -> None:
        decision = evaluate(_ctx())
        assert isinstance(decision, PolicyDecision)
        assert decision.verdict is Verdict.ALLOW
        assert decision.reasons == []
        assert decision.is_allowed() is True

    def test_single_deny_denies(self) -> None:
        decision = evaluate(_ctx(amount_usd=Decimal("0")))
        assert decision.verdict is Verdict.DENY
        assert decision.is_allowed() is False
        assert any(name == "rule_amount_positive" for name, _ in decision.reasons)

    def test_single_hold_holds(self) -> None:
        future = _NOW + timedelta(seconds=60)
        decision = evaluate(_ctx(cooldown_until=future))
        assert decision.verdict is Verdict.HOLD
        assert any(name == "rule_cooldown" for name, _ in decision.reasons)

    def test_deny_overrides_hold(self) -> None:
        # HOLD (cooldown) と DENY (amount<=0) が同居 → DENY 採用
        future = _NOW + timedelta(seconds=60)
        decision = evaluate(_ctx(amount_usd=Decimal("0"), cooldown_until=future))
        assert decision.verdict is Verdict.DENY
        # reasons には両方蓄積される (運用ログ用)
        rule_names = {name for name, _ in decision.reasons}
        assert "rule_amount_positive" in rule_names
        assert "rule_cooldown" in rule_names

    def test_emergency_stop_denies(self) -> None:
        # 他は全部 pass でも emergency_stop だけで DENY
        decision = evaluate(_ctx(emergency_stop=True))
        assert decision.verdict is Verdict.DENY
        assert decision.reasons[0][0] == "rule_emergency_stop"

    def test_multiple_denies_all_recorded(self) -> None:
        decision = evaluate(
            _ctx(
                amount_usd=Decimal("0"),
                health_factor=Decimal("1.0"),
                emergency_stop=True,
            )
        )
        assert decision.verdict is Verdict.DENY
        names = {name for name, _ in decision.reasons}
        # 全 3 rule が違反として記録されている
        assert "rule_emergency_stop" in names
        assert "rule_amount_positive" in names
        assert "rule_health_factor" in names

    def test_custom_rules_override_default(self) -> None:
        def always_hold(_ctx):
            return Verdict.HOLD, "manual hold"

        decision = evaluate(_ctx(), rules=[always_hold])
        assert decision.verdict is Verdict.HOLD
        assert decision.reasons == [("always_hold", "manual hold")]

    def test_empty_rules_allows(self) -> None:
        # rule リストが空なら必ず ALLOW (engine の仕様)
        decision = evaluate(_ctx(emergency_stop=True), rules=[])
        assert decision.verdict is Verdict.ALLOW

    def test_default_rules_includes_emergency_stop_first(self) -> None:
        # rule の登録順保証 (運用上 emergency_stop は最優先記録)
        assert DEFAULT_RULES[0] is rule_emergency_stop


# ──────────────────────────────────────────────────────────────
# 不正値 / 境界
# ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_decimal_precision_preserved(self) -> None:
        # float 混入バグ検出: 0.1+0.2 != 0.3 を Decimal で扱えるか
        ctx = _ctx(
            amount_usd=Decimal("0.1"),
            daily_traded_usd=Decimal("0.2"),
            daily_cap_usd=Decimal("0.3"),
        )
        decision = evaluate(ctx)
        assert decision.verdict is Verdict.ALLOW

    def test_decimal_precision_over_cap(self) -> None:
        ctx = _ctx(
            amount_usd=Decimal("0.10001"),
            daily_traded_usd=Decimal("0.2"),
            daily_cap_usd=Decimal("0.3"),
        )
        decision = evaluate(ctx)
        assert decision.verdict is Verdict.DENY

    @pytest.mark.parametrize(
        "hf,minhf,expected",
        [
            (Decimal("1.60"), Decimal("1.6"), Verdict.ALLOW),
            (Decimal("1.60001"), Decimal("1.6"), Verdict.ALLOW),
            (Decimal("1.59999"), Decimal("1.6"), Verdict.DENY),
        ],
    )
    def test_hf_boundary(self, hf: Decimal, minhf: Decimal, expected: Verdict) -> None:
        decision = evaluate(_ctx(health_factor=hf, min_health_factor=minhf))
        assert decision.verdict is expected
