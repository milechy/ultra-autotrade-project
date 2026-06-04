# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/policy/engine.py
"""
機械的 policy 検算層。LLM 出力をそのまま signer に渡さないための hard rule。
OPA/Cedar は Phase B 評価予定。ここは軽量 class 実装。
学習・AI 出力で上書き不可。
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---- Defaults (env vars で上書き可能だが、意味論的な安全境界は変わらない) ----
_DEFAULT_ALLOWED_ASSETS: frozenset[str] = frozenset({"USDC"})
_DEFAULT_ALLOWED_OPERATIONS: frozenset[str] = frozenset({"SUPPLY", "WITHDRAW"})
_DEFAULT_MAX_POSITION_USD = Decimal("10000")
_DEFAULT_DAILY_CAP_USD = Decimal("50000")
_DEFAULT_HOURLY_CAP_USD = Decimal("20000")
_DEFAULT_COOLDOWN_SECONDS = 600
_DEFAULT_HF_FLOOR = Decimal("1.5")


@dataclass(frozen=True)
class PolicyContext:
    """ポリシーチェック対象の提案属性。"""

    user_id: int
    asset: str
    operation: str
    amount_usd: Decimal
    expected_hf_after: Optional[Decimal] = None
    # 承認時のみ設定。DB クエリで自分自身を除外するために使う。
    proposal_id: Optional[int] = None


@dataclass
class PolicyResult:
    """ポリシーチェック結果。"""

    passed: bool
    violations: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return not self.passed


class PolicyEngine:
    """
    提案生成時・承認時に機械的ルールを適用する。

    Rule 1: asset whitelist (USDC のみ)
    Rule 2: allowed contracts (Aave のみ ≡ SUPPLY/WITHDRAW)
    Rule 3: max position size per user
    Rule 4: 日次 velocity cap
    Rule 5: 時間毎 velocity cap
    Rule 6: cooldown window
    Rule 7: HF floor
    """

    def __init__(self) -> None:
        self._allowed_assets = _parse_set("POLICY_ALLOWED_ASSETS", _DEFAULT_ALLOWED_ASSETS)
        self._allowed_operations = _parse_set(
            "POLICY_ALLOWED_OPERATIONS", _DEFAULT_ALLOWED_OPERATIONS
        )
        self._max_position_usd = _parse_decimal(
            "POLICY_MAX_POSITION_USD", _DEFAULT_MAX_POSITION_USD
        )
        self._daily_cap_usd = _parse_decimal(
            "POLICY_DAILY_VELOCITY_CAP_USD", _DEFAULT_DAILY_CAP_USD
        )
        self._hourly_cap_usd = _parse_decimal(
            "POLICY_HOURLY_VELOCITY_CAP_USD", _DEFAULT_HOURLY_CAP_USD
        )
        self._cooldown_seconds = _parse_int("POLICY_COOLDOWN_SECONDS", _DEFAULT_COOLDOWN_SECONDS)
        self._hf_floor = _parse_decimal("POLICY_HF_FLOOR", _DEFAULT_HF_FLOOR)

    def check(self, ctx: PolicyContext, db: Any) -> PolicyResult:
        """全ポリシールールを評価する。違反が 1 件でもあれば blocked=True。"""
        violations: list[str] = []

        # Rule 1: asset whitelist
        if ctx.asset.upper() not in self._allowed_assets:
            violations.append(
                f"asset '{ctx.asset}' not in whitelist {sorted(self._allowed_assets)}"
            )

        # Rule 2: allowed contracts (Aave only ≡ SUPPLY/WITHDRAW)
        if ctx.operation.upper() not in self._allowed_operations:
            violations.append(
                f"operation '{ctx.operation}' not in allowed set {sorted(self._allowed_operations)}"
            )

        # Rule 3: max position size
        if ctx.amount_usd > self._max_position_usd:
            violations.append(
                f"amount_usd {ctx.amount_usd} exceeds max_position {self._max_position_usd}"
            )

        # Rules 4/5/6: DB 参照が必要なチェック
        if db is not None:
            violations.extend(self._check_velocity(ctx, db))
            violations.extend(self._check_cooldown(ctx, db))

        # Rule 7: HF floor
        if ctx.expected_hf_after is not None and ctx.expected_hf_after < self._hf_floor:
            violations.append(
                f"expected_hf_after {ctx.expected_hf_after} below floor {self._hf_floor}"
            )

        passed = not violations
        if not passed:
            logger.warning(
                "policy: BLOCKED user_id=%d asset=%s op=%s amount_usd=%s — %s",
                ctx.user_id,
                ctx.asset,
                ctx.operation,
                ctx.amount_usd,
                "; ".join(violations),
            )
        return PolicyResult(passed=passed, violations=violations)

    def _check_velocity(self, ctx: PolicyContext, db: Any) -> list[str]:
        from sqlalchemy import func, select  # noqa: PLC0415

        from app.proposals.models import Proposal  # noqa: PLC0415

        violations: list[str] = []
        now = datetime.now(timezone.utc)

        base = select(func.sum(Proposal.amount_usd)).where(
            Proposal.user_id == ctx.user_id,
            Proposal.status.in_(["approved", "executed"]),
        )
        if ctx.proposal_id is not None:
            base = base.where(Proposal.id != ctx.proposal_id)

        # Rule 4: daily velocity cap
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        raw_daily = db.scalar(base.where(Proposal.approved_at >= day_start))
        daily_sum = Decimal(str(raw_daily)) if raw_daily is not None else Decimal("0")
        if daily_sum + ctx.amount_usd > self._daily_cap_usd:
            violations.append(
                f"daily velocity cap {self._daily_cap_usd} exceeded "
                f"(approved_today={daily_sum}, adding={ctx.amount_usd})"
            )

        # Rule 5: hourly velocity cap
        hour_start = now - timedelta(hours=1)
        raw_hourly = db.scalar(base.where(Proposal.approved_at >= hour_start))
        hourly_sum = Decimal(str(raw_hourly)) if raw_hourly is not None else Decimal("0")
        if hourly_sum + ctx.amount_usd > self._hourly_cap_usd:
            violations.append(
                f"hourly velocity cap {self._hourly_cap_usd} exceeded "
                f"(approved_1h={hourly_sum}, adding={ctx.amount_usd})"
            )

        return violations

    def _check_cooldown(self, ctx: PolicyContext, db: Any) -> list[str]:
        from sqlalchemy import select  # noqa: PLC0415

        from app.proposals.models import Proposal  # noqa: PLC0415

        stmt = select(Proposal.approved_at).where(
            Proposal.user_id == ctx.user_id,
            Proposal.status.in_(["approved", "executed"]),
        )
        if ctx.proposal_id is not None:
            stmt = stmt.where(Proposal.id != ctx.proposal_id)
        stmt = stmt.order_by(Proposal.approved_at.desc()).limit(1)

        last_approved_at = db.scalar(stmt)
        if last_approved_at is None:
            return []

        # SQLite は timezone-naive で返すため UTC 付与して統一する
        if last_approved_at.tzinfo is None:
            last_approved_at = last_approved_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_approved_at).total_seconds()
        if elapsed < self._cooldown_seconds:
            return [
                f"cooldown not elapsed ({elapsed:.0f}s since last approval, "
                f"required={self._cooldown_seconds}s)"
            ]
        return []


# ---- Module-level singleton ----

_engine_instance: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """キャッシュ済み PolicyEngine を返す。テストでは直接 PolicyEngine() を使うこと。"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = PolicyEngine()
    return _engine_instance


# ---- Private helpers ----


def _parse_set(env_key: str, default: frozenset[str]) -> frozenset[str]:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return default
    return frozenset(v.strip().upper() for v in raw.split(",") if v.strip())


def _parse_decimal(env_key: str, default: Decimal) -> Decimal:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return default
    try:
        return Decimal(raw)
    except InvalidOperation:
        logger.error("policy: invalid decimal %s=%r, using default %s", env_key, raw, default)
        return default


def _parse_int(env_key: str, default: int) -> int:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.error("policy: invalid int %s=%r, using default %d", env_key, raw, default)
        return default
