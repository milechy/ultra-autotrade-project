# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/limits.py
"""資金上限ゲート (P0-3.1) — MVP launch 前の漏洩許容額を constants 化。

Asana P0-3.1 (claude.ai 担当の雛形)。P0-3 (資金上限の運用合意) で
最終値を確定する想定。本モジュールは合意のたたき台 + 実装側のシングル
ソース・オブ・トゥルース。

設計:
- 値は全て ``Decimal`` (float 禁止、CLAUDE.md security #11)
- ``DEFAULTS`` を持ち、環境変数で上書き可能 (本番値は ``.env.production`` で固定)
- ``check_deposit_allowed`` がゲート関数 — backend 側の deposit API から呼ぶ
- 透明性のため判定理由を ``DepositDecision.reason`` に日本語で詰める
  (ToS 表示・user 向けエラーメッセージに直接使う想定)

関連:
- Asana P0-3 / P0-3.1
- docs/legal/tos_limits_draft.md (本 PR で同時追加する ToS 文言ドラフト)
- backend/app/fees/trade_gate.py (既存のトレード経済性ゲート、別レイヤ)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "PER_USER_MAX_DEPOSIT_USD",
    "TVL_CAP_USD",
    "ALERT_THRESHOLD_RATIO",
    "INITIAL_USER_COUNT",
    "DepositDecision",
    "check_deposit_allowed",
    "tvl_alert_should_fire",
]


def _env_decimal(key: str, default: Decimal) -> Decimal:
    """環境変数を Decimal で取得、未設定 or 不正なら ``default``。

    float 経由は厳禁 (精度欠落)。文字列を直接 Decimal に渡す。
    """
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = Decimal(raw.strip())
    except (ValueError, ArithmeticError):
        return default
    return value


# ──────────────────────────────────────────────────────────────
# 定数 (P0-3 合意のたたき台)
# ──────────────────────────────────────────────────────────────

#: per-user の入金上限 (USD)。
#: 初期は 1 人あたり $200 を漏洩許容額として握る。
PER_USER_MAX_DEPOSIT_USD: Decimal = _env_decimal("PER_USER_MAX_DEPOSIT_USD", Decimal("200"))

#: 初期人数想定。``PER_USER_MAX_DEPOSIT_USD * INITIAL_USER_COUNT`` が TVL 上限の根拠。
INITIAL_USER_COUNT: int = int(os.environ.get("INITIAL_USER_COUNT", "25"))

#: プロトコル全体の TVL 上限 (USD)。
#: 既定値は ``PER_USER_MAX_DEPOSIT_USD * INITIAL_USER_COUNT``。
#: P0-3 で別途確定する場合は環境変数で上書き。
TVL_CAP_USD: Decimal = _env_decimal(
    "TVL_CAP_USD", PER_USER_MAX_DEPOSIT_USD * Decimal(INITIAL_USER_COUNT)
)

#: TVL 上限の何割を超えたら alert を発火するか。
#: 0.80 = 80%。閾値超過で Slack #ops に通知する設計 (実装は別レイヤ)。
ALERT_THRESHOLD_RATIO: Decimal = _env_decimal("ALERT_THRESHOLD_RATIO", Decimal("0.80"))


# ──────────────────────────────────────────────────────────────
# 判定結果
# ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DepositDecision:
    """入金可否の判定結果。

    user 向けメッセージとログに同じ値を使えるよう、``reason`` は日本語。
    """

    allowed: bool
    reason: str
    user_remaining_usd: Decimal
    tvl_headroom_usd: Decimal


# ──────────────────────────────────────────────────────────────
# ゲート関数
# ──────────────────────────────────────────────────────────────


def check_deposit_allowed(
    *,
    requested_amount_usd: Decimal,
    user_current_deposit_usd: Decimal,
    current_tvl_usd: Decimal,
    per_user_cap_usd: Decimal = PER_USER_MAX_DEPOSIT_USD,
    tvl_cap_usd: Decimal = TVL_CAP_USD,
) -> DepositDecision:
    """入金リクエストが per-user cap / TVL cap の両方を満たすかを判定する。

    Args:
        requested_amount_usd: 今回入金しようとしている額 (USD)。
        user_current_deposit_usd: 当該 user の現在の累計入金額 (USD)。
        current_tvl_usd: プロトコル全体の現在の TVL (USD)。
        per_user_cap_usd: per-user 上限 (default: ``PER_USER_MAX_DEPOSIT_USD``)。
        tvl_cap_usd: TVL 上限 (default: ``TVL_CAP_USD``)。

    Returns:
        ``DepositDecision``。両方の cap を満たしたときのみ ``allowed=True``。
        ``user_remaining_usd`` / ``tvl_headroom_usd`` は **入金前**の残り余地。
    """
    if requested_amount_usd <= 0:
        return DepositDecision(
            allowed=False,
            reason="入金額は 0 より大きい値を指定してください。",
            user_remaining_usd=max(per_user_cap_usd - user_current_deposit_usd, Decimal("0")),
            tvl_headroom_usd=max(tvl_cap_usd - current_tvl_usd, Decimal("0")),
        )

    user_remaining = per_user_cap_usd - user_current_deposit_usd
    tvl_headroom = tvl_cap_usd - current_tvl_usd

    if requested_amount_usd > user_remaining:
        return DepositDecision(
            allowed=False,
            reason=(
                f"1 人あたりの入金上限 ${per_user_cap_usd} を超えます "
                f"(現在 ${user_current_deposit_usd} / 残り ${max(user_remaining, Decimal('0'))})。"
            ),
            user_remaining_usd=max(user_remaining, Decimal("0")),
            tvl_headroom_usd=max(tvl_headroom, Decimal("0")),
        )

    if requested_amount_usd > tvl_headroom:
        return DepositDecision(
            allowed=False,
            reason=(
                f"プロトコル全体の TVL 上限 ${tvl_cap_usd} に達したため、現在新規入金を停止しています。"
            ),
            user_remaining_usd=max(user_remaining, Decimal("0")),
            tvl_headroom_usd=max(tvl_headroom, Decimal("0")),
        )

    return DepositDecision(
        allowed=True,
        reason="入金可能です。",
        user_remaining_usd=user_remaining,
        tvl_headroom_usd=tvl_headroom,
    )


def tvl_alert_should_fire(
    *,
    current_tvl_usd: Decimal,
    tvl_cap_usd: Decimal = TVL_CAP_USD,
    threshold_ratio: Decimal = ALERT_THRESHOLD_RATIO,
) -> bool:
    """TVL が cap の閾値 (default 80%) を超えたら True。

    overflow を抑止するため Decimal で比較する。
    """
    if tvl_cap_usd <= 0:
        return False
    return current_tvl_usd >= tvl_cap_usd * threshold_ratio
