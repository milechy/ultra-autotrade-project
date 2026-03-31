# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/rebalance_config.py

"""
Aave リバランス設定値読み出しモジュール。

- 環境変数からリバランス戦略・安全パラメータを取得する
- デフォルトは shadow_mode=True（本番誤発注を防ぐ安全側）
"""

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.utils.config import get_env

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_SECRET = ""  # noqa: S105


@dataclass
class RebalanceSettings:
    """
    Aave リバランス運用に関する設定値のまとまり。

    NOTE:
    - shadow_mode=True のあいだは実際の on-chain 操作を行わず、
      ログ出力のみで動作確認できる。
    - confirmation_token_secret は本番では必ず強いランダム文字列に変更すること。
    """

    target_allocations: dict[str, Decimal]
    deviation_threshold_pct: Decimal
    max_rebalance_pct: Decimal
    min_health_factor_post: Decimal
    cooldown_seconds: int
    confirmation_token_ttl_seconds: int
    confirmation_token_secret: str
    check_interval_seconds: int
    shadow_mode: bool


def _get_env_int(name: str, default: int) -> int:
    """
    整数値の環境変数を取得するヘルパー。

    不正な値が入っていた場合は RuntimeError にする。
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        return default

    try:
        return int(raw)
    except ValueError as exc:  # noqa: TRY003
        raise RuntimeError(f"Invalid integer value for env var {name}: {raw!r}") from exc


def _get_env_decimal(name: str, default: str) -> Decimal:
    """
    Decimal 値の環境変数を取得するヘルパー。

    :param name: 環境変数名
    :param default: パースに失敗した場合や未設定時に使用する文字列表現
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        raw = default

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:  # noqa: TRY003
        raise RuntimeError(f"Invalid decimal value for env var {name}: {raw!r}") from exc


def _get_env_bool(name: str, default: bool) -> bool:
    """
    真偽値の環境変数を取得するヘルパー。

    "true"/"1"/"yes" → True、それ以外 → False として解釈する。
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        return default

    return raw.strip().lower() in ("true", "1", "yes")


def _parse_target_allocations(raw: str | None) -> dict[str, Decimal]:
    """
    JSON 文字列から target_allocations を解析する。

    値は Decimal に変換する。例:
        '{"USDC": "60", "WETH": "40"}' → {"USDC": Decimal("60"), "WETH": Decimal("40")}
    """
    default_json = '{"USDC": "60", "WETH": "40"}'

    if raw is None or raw.strip() == "":
        raw = default_json

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:  # noqa: TRY003
        raise RuntimeError(
            f"Invalid JSON for env var REBALANCE_TARGET_ALLOCATIONS: {raw!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"REBALANCE_TARGET_ALLOCATIONS must be a JSON object, got: {type(parsed).__name__}"
        )

    result: dict[str, Decimal] = {}
    for key, value in parsed.items():
        try:
            result[str(key)] = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:  # noqa: TRY003
            raise RuntimeError(
                f"Invalid decimal value for allocation key {key!r}: {value!r}"
            ) from exc

    return result


def get_rebalance_settings() -> RebalanceSettings:
    """
    RebalanceSettings を構築して返す。

    デフォルト値は「安全側（shadow_mode=True・閾値は保守的）」に設定している。
    """
    # ターゲット配分 (JSON)
    raw_allocations = get_env("REBALANCE_TARGET_ALLOCATIONS", required=False)
    target_allocations = _parse_target_allocations(raw_allocations)

    deviation_threshold_pct = _get_env_decimal(
        "REBALANCE_DEVIATION_THRESHOLD_PCT",
        default="5",  # 5% のズレでリバランスをトリガー
    )
    max_rebalance_pct = _get_env_decimal(
        "REBALANCE_MAX_PCT",
        default="10",  # 1回のリバランスで動かせる最大割合
    )
    min_health_factor_post = _get_env_decimal(
        "REBALANCE_MIN_HF_POST",
        default="1.8",  # リバランス後に維持すべき最低 Health Factor
    )
    cooldown_seconds = _get_env_int(
        "REBALANCE_COOLDOWN_SECONDS",
        default=3600,  # 1時間のクールダウン
    )
    confirmation_token_ttl_seconds = _get_env_int(
        "REBALANCE_TOKEN_TTL_SECONDS",
        default=300,  # 確認トークンの有効期限 5分
    )

    # 確認トークン署名秘密鍵 — デフォルト値のまま本番に出ないよう警告
    confirmation_token_secret = (
        get_env("REBALANCE_TOKEN_SECRET", required=False) or _DEFAULT_TOKEN_SECRET
    )
    if confirmation_token_secret == _DEFAULT_TOKEN_SECRET:
        logger.warning(
            "REBALANCE_TOKEN_SECRET is using the default insecure value. "
            "Set a strong random secret in production via the REBALANCE_TOKEN_SECRET env var."
        )

    check_interval_seconds = _get_env_int(
        "REBALANCE_CHECK_INTERVAL_SECONDS",
        default=14400,  # 4時間ごとにリバランスチェック
    )
    shadow_mode = _get_env_bool(
        "REBALANCE_SHADOW_MODE",
        default=True,  # 安全のためデフォルトは shadow (dry-run) モード
    )

    return RebalanceSettings(
        target_allocations=target_allocations,
        deviation_threshold_pct=deviation_threshold_pct,
        max_rebalance_pct=max_rebalance_pct,
        min_health_factor_post=min_health_factor_post,
        cooldown_seconds=cooldown_seconds,
        confirmation_token_ttl_seconds=confirmation_token_ttl_seconds,
        confirmation_token_secret=confirmation_token_secret,
        check_interval_seconds=check_interval_seconds,
        shadow_mode=shadow_mode,
    )
