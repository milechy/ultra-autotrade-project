# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/policy/engine.py
"""Transaction Policy Engine (P0-7 MVP)。

承認時 (proposal → approval) に署名前のルール検査を行う。
Pure functions: I/O / DB アクセス / on-chain call なし。呼出し側が
``TransactionContext`` を組み立てて ``evaluate`` に渡す。

Verdict (allow / hold / deny) で返却。``hold`` は人手判断を促し
proposal を pending のまま留め、``deny`` は明確に拒否する。

設計原則 (CLAUDE.md security と整合):
- 値は Decimal (float 禁止)
- 危険な方向 (拒否) に倒れるべき; 不明値は hold
- emergency_stop は OR 論理で必ず deny を返す

呼出し方:
    >>> from app.policy import TransactionContext, evaluate
    >>> ctx = TransactionContext(...)
    >>> decision = evaluate(ctx)
    >>> if decision.verdict is Verdict.ALLOW: ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Callable, Optional


class Verdict(str, Enum):
    """ポリシー判定結果。"""

    ALLOW = "allow"  # 全 rule pass → 署名へ進む
    HOLD = "hold"  # 1 つ以上 rule で「人手判断が必要」 → proposal を pending に
    DENY = "deny"  # 1 つ以上 rule で明確 violation → tx を破棄


@dataclass(frozen=True)
class TransactionContext:
    """ポリシー評価対象の context。

    呼出し側が DB / on-chain / env から組み立てる。Engine は dataclass の値しか見ない。

    Attributes:
        user_id: 対象 user id。
        amount_usd: 今回の tx 金額 (USD)。
        recipient_address: 送金先 EVM address (lowercase 0x... 想定)。
        recipient_allowlist: 許可された recipient 集合 (lower-case)。
        health_factor: Aave HF。HF<min_hf で hold/deny。
        min_health_factor: HF の最小許容値 (default 1.6)。
        daily_traded_usd: 当日累計 tx 額。
        daily_cap_usd: 当日 cap (default 30% of total assets)。
        single_trade_cap_usd: 単発 tx cap (default 10% of total assets)。
        cooldown_until: 次回 tx 許可時刻 (None = cooldown 無し)。
        now: 現在時刻 (tz aware、default: ``datetime.now(timezone.utc)``)。
        oracle_updated_at: Aave Oracle 最新更新時刻 (tz aware)。
        oracle_max_staleness_sec: Oracle 鮮度上限 (default 300s)。
        emergency_stop: True なら全て deny (OR 論理)。
    """

    user_id: int
    amount_usd: Decimal
    recipient_address: str
    recipient_allowlist: frozenset[str]
    health_factor: Decimal
    min_health_factor: Decimal = Decimal("1.6")
    daily_traded_usd: Decimal = Decimal("0")
    daily_cap_usd: Decimal = Decimal("0")
    single_trade_cap_usd: Decimal = Decimal("0")
    cooldown_until: Optional[datetime] = None
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    oracle_updated_at: Optional[datetime] = None
    oracle_max_staleness_sec: int = 300
    emergency_stop: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    """Engine の評価結果。

    Attributes:
        verdict: ALLOW / HOLD / DENY。
        reasons: 違反した rule 名と理由メッセージのリスト (allow なら空)。
    """

    verdict: Verdict
    reasons: list[tuple[str, str]] = field(default_factory=list)

    def is_allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW


#: 1 rule = ``(ctx) -> Optional[tuple[Verdict, str]]`` の callable。
#: None を返すと「pass」。
Rule = Callable[[TransactionContext], Optional[tuple[Verdict, str]]]


# ──────────────────────────────────────────────────────────────
# 個別 rule (純粋関数)
# ──────────────────────────────────────────────────────────────


def rule_emergency_stop(ctx: TransactionContext) -> Optional[tuple[Verdict, str]]:
    """emergency_stop が True なら DENY (OR 論理、最優先)。"""
    if ctx.emergency_stop:
        return Verdict.DENY, "emergency_stop is ON"
    return None


def rule_amount_positive(ctx: TransactionContext) -> Optional[tuple[Verdict, str]]:
    """tx 金額が 0 以下なら DENY。"""
    if ctx.amount_usd <= 0:
        return Verdict.DENY, f"amount must be > 0 (got {ctx.amount_usd})"
    return None


def rule_health_factor(ctx: TransactionContext) -> Optional[tuple[Verdict, str]]:
    """Aave HF が下限未満なら DENY (HARD_STOP 連動)。"""
    if ctx.health_factor < ctx.min_health_factor:
        return (
            Verdict.DENY,
            f"health_factor {ctx.health_factor} < min {ctx.min_health_factor}",
        )
    return None


def rule_single_trade_cap(ctx: TransactionContext) -> Optional[tuple[Verdict, str]]:
    """単発 tx が cap を超えるなら DENY。cap=0 はチェックスキップ。"""
    if ctx.single_trade_cap_usd > 0 and ctx.amount_usd > ctx.single_trade_cap_usd:
        return (
            Verdict.DENY,
            f"single_trade {ctx.amount_usd} > cap {ctx.single_trade_cap_usd}",
        )
    return None


def rule_daily_cap(ctx: TransactionContext) -> Optional[tuple[Verdict, str]]:
    """当日累計 + 今回額が cap を超えるなら DENY。cap=0 はスキップ。"""
    if ctx.daily_cap_usd <= 0:
        return None
    projected = ctx.daily_traded_usd + ctx.amount_usd
    if projected > ctx.daily_cap_usd:
        return (
            Verdict.DENY,
            f"daily total {projected} > cap {ctx.daily_cap_usd}",
        )
    return None


def rule_cooldown(ctx: TransactionContext) -> Optional[tuple[Verdict, str]]:
    """cooldown_until を未過ぎていれば HOLD (DENY ではない、後続 retry 想定)。"""
    if ctx.cooldown_until is None:
        return None
    if ctx.now < ctx.cooldown_until:
        return (
            Verdict.HOLD,
            f"cooldown active until {ctx.cooldown_until.isoformat()}",
        )
    return None


def rule_oracle_freshness(ctx: TransactionContext) -> Optional[tuple[Verdict, str]]:
    """Oracle 最終更新が staleness を超えていれば HOLD。

    未設定 (None) なら HOLD (不明=安全側)。
    """
    if ctx.oracle_updated_at is None:
        return Verdict.HOLD, "oracle_updated_at is unknown"
    age = (ctx.now - ctx.oracle_updated_at).total_seconds()
    if age > ctx.oracle_max_staleness_sec:
        return (
            Verdict.HOLD,
            f"oracle stale: {age:.0f}s > {ctx.oracle_max_staleness_sec}s",
        )
    return None


def rule_recipient_allowlist(ctx: TransactionContext) -> Optional[tuple[Verdict, str]]:
    """recipient が allowlist にあるか確認。空の allowlist はスキップ。"""
    if not ctx.recipient_allowlist:
        return None
    if ctx.recipient_address.lower() not in ctx.recipient_allowlist:
        return (
            Verdict.DENY,
            f"recipient {ctx.recipient_address} not in allowlist",
        )
    return None


#: Default ルール順序。emergency_stop は必ず先頭。
DEFAULT_RULES: list[Rule] = [
    rule_emergency_stop,
    rule_amount_positive,
    rule_health_factor,
    rule_single_trade_cap,
    rule_daily_cap,
    rule_cooldown,
    rule_oracle_freshness,
    rule_recipient_allowlist,
]


# ──────────────────────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────────────────────


def evaluate(
    ctx: TransactionContext,
    rules: Optional[list[Rule]] = None,
) -> PolicyDecision:
    """全 rule を順に評価し、最終 Verdict を返す。

    集約ロジック:
    - DENY が 1 つでもあれば DENY (危険側優先、emergency_stop は最優先で短絡しない)
    - HOLD が 1 つ以上 / DENY なし → HOLD
    - 全て None → ALLOW

    全 rule の結果を蓄積するため、複数違反を 1 度に返せる (運用ログで便利)。
    """
    rules = rules if rules is not None else DEFAULT_RULES
    reasons: list[tuple[str, str]] = []
    has_deny = False
    has_hold = False

    for rule in rules:
        result = rule(ctx)
        if result is None:
            continue
        verdict, msg = result
        reasons.append((rule.__name__, msg))
        if verdict is Verdict.DENY:
            has_deny = True
        elif verdict is Verdict.HOLD:
            has_hold = True

    if has_deny:
        return PolicyDecision(verdict=Verdict.DENY, reasons=reasons)
    if has_hold:
        return PolicyDecision(verdict=Verdict.HOLD, reasons=reasons)
    return PolicyDecision(verdict=Verdict.ALLOW, reasons=[])
