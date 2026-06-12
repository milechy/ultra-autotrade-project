# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/ai/config.py

"""
AI 判定モジュール関連の設定値読み出しモジュール。

- 環境変数から LLM API キーやモデル名、判定パラメータを取得する
- 全キーはオプション（graceful degradation）—— キー未設定時は HOLD にフォールバック
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.utils.config import get_env

# ---------------------------------------------------------------------------
# 4 軸コンセンサス設定（EPIC-1 1-5）
# ---------------------------------------------------------------------------
# CONSENSUS_4AXIS_MODE の許可リスト（fail-closed: 範囲外は RuntimeError）
#   off     — 4 軸合議を使わず従来ロジックのみ
#   shadow  — 算出・記録のみ（実行系には影響させない）
#   a_b     — A/B 比較用（一部トラフィックに適用）
#   on      — 4 軸合議を本番経路に適用
VALID_CONSENSUS_4AXIS_MODES: frozenset[str] = frozenset({"off", "shadow", "a_b", "on"})

# ---------------------------------------------------------------------------
# モデル名許可リスト（Single source of truth）
# scripts/validate_anthropic_model.py と同期すること
# ---------------------------------------------------------------------------
VALID_CLAUDE_MODELS: list[str] = [
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
]

DEFAULT_CLAUDE_MODEL: str = "claude-sonnet-4-6"
DEFAULT_FALLBACK_MODEL: str = "claude-haiku-4-5-20251001"

# 非推奨モデル: 起動時検証でブロックされる
# claude-sonnet-4-20250514 was the cause of the 2026-04-18 production 502 incident
DEPRECATED_CLAUDE_MODELS: list[str] = [
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-latest",
    "claude-3-opus-20240229",
]


@dataclass
class AISettings:
    """
    AI 判定に関する設定値のまとまり。

    NOTE:
    - anthropic_api_key / openai_api_key はともにオプション。
      未設定の場合、対応する LLM 呼び出しは HOLD にフォールバックする。
    - cross_validation_enabled=True の場合、Phase 2 で OpenAI を使った
      クロスバリデーションを実施する。
    """

    anthropic_api_key: Optional[str]
    openai_api_key: Optional[str]
    claude_model: str
    openai_model: str
    min_confidence_threshold: int
    cross_validation_enabled: bool
    prompt_version: str
    shadow_mode: bool  # True=判定記録のみ、実行しない
    ai_fallback_model: str  # Opus失敗時のフォールバックモデル（環境変数: AI_FALLBACK_MODEL）
    # --- 4 軸コンセンサス設定（EPIC-1 1-5）---
    # デフォルト値は AISettings を直接構築する既存テストとの後方互換のため必須
    consensus_4axis_mode: str = (
        "shadow"  # CONSENSUS_4AXIS_MODE（許可リスト外は RuntimeError / fail-closed）
    )
    consensus_score_threshold: Decimal = Decimal(
        "0.40"
    )  # CONSENSUS_SCORE_THRESHOLD（weighted directional score 閾値 ±）
    consensus_conf_threshold: int = 65  # CONSENSUS_CONF_THRESHOLD（weighted confidence 閾値）


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
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer value for env var {name}: {raw!r}") from exc


def _get_env_bool(name: str, default: bool) -> bool:
    """
    真偽値の環境変数を取得するヘルパー。

    "true" / "1" / "yes" を True として扱い、それ以外は False とする。
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        return default

    return raw.lower() in ("true", "1", "yes")


def _get_env_decimal(name: str, default: Decimal) -> Decimal:
    """
    Decimal 値の環境変数を取得するヘルパー（金融閾値は Decimal 型のみ）。

    不正な値が入っていた場合は RuntimeError にする。
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        return default

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError(f"Invalid decimal value for env var {name}: {raw!r}") from exc


def _get_env_consensus_mode(name: str, default: str) -> str:
    """
    CONSENSUS_4AXIS_MODE を取得するヘルパー（fail-closed）。

    許可リスト VALID_CONSENSUS_4AXIS_MODES 外の値は RuntimeError にする。
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        return default

    if raw not in VALID_CONSENSUS_4AXIS_MODES:
        raise RuntimeError(
            f"Invalid value for env var {name}: {raw!r}. "
            f"Must be one of: {sorted(VALID_CONSENSUS_4AXIS_MODES)}"
        )
    return raw


def _validate_model_config() -> None:
    """起動時検証: VALID_CLAUDE_MODELS 許可リスト方式（deny-list ではなく allow-list）。

    許可リストにないモデル名は、非推奨でなくても起動を拒否する。
    これにより claude-sonnet-4-6-20250929 のような「存在しないが非推奨でもない」
    モデル名をブロックできる。
    """
    current = get_env("AI_CLAUDE_MODEL", required=False) or DEFAULT_CLAUDE_MODEL
    fallback = get_env("AI_FALLBACK_MODEL", required=False) or DEFAULT_FALLBACK_MODEL
    for name, value in [("AI_CLAUDE_MODEL", current), ("AI_FALLBACK_MODEL", fallback)]:
        if value not in VALID_CLAUDE_MODELS:
            raise ValueError(
                f"Invalid Claude model configured: {name}={value!r}. "
                f"Must be one of: {VALID_CLAUDE_MODELS}"
            )


def get_ai_settings() -> AISettings:
    """
    AISettings を構築して返す。

    全キーはオプション（graceful degradation）:
      - ANTHROPIC_API_KEY（未設定時: None）
      - OPENAI_API_KEY（未設定時: None）
      - AI_CLAUDE_MODEL（デフォルト: claude-sonnet-4-6）
      - AI_OPENAI_MODEL（デフォルト: gpt-4o）
      - AI_MIN_CONFIDENCE_THRESHOLD（デフォルト: 40）
      - AI_CROSS_VALIDATION_ENABLED（デフォルト: True）
      - AI_PROMPT_VERSION（デフォルト: v1）
      - CONSENSUS_4AXIS_MODE（デフォルト: shadow / 許可リスト外は RuntimeError）
      - CONSENSUS_SCORE_THRESHOLD（デフォルト: Decimal("0.40")）
      - CONSENSUS_CONF_THRESHOLD（デフォルト: 65）
    """
    anthropic_api_key = get_env("ANTHROPIC_API_KEY", required=False)
    openai_api_key = get_env("OPENAI_API_KEY", required=False)

    claude_model = get_env("AI_CLAUDE_MODEL", required=False) or DEFAULT_CLAUDE_MODEL
    openai_model = get_env("AI_OPENAI_MODEL", required=False) or "gpt-4o"
    ai_fallback_model = get_env("AI_FALLBACK_MODEL", required=False) or DEFAULT_FALLBACK_MODEL

    min_confidence_threshold = _get_env_int(
        "AI_MIN_CONFIDENCE_THRESHOLD",
        default=40,
    )
    cross_validation_enabled = _get_env_bool(
        "AI_CROSS_VALIDATION_ENABLED",
        default=True,
    )
    prompt_version = get_env("AI_PROMPT_VERSION", required=False) or "v1"
    shadow_mode = _get_env_bool("AI_SHADOW_MODE", default=False)

    consensus_4axis_mode = _get_env_consensus_mode(
        "CONSENSUS_4AXIS_MODE",
        default="shadow",
    )
    consensus_score_threshold = _get_env_decimal(
        "CONSENSUS_SCORE_THRESHOLD",
        default=Decimal("0.40"),
    )
    consensus_conf_threshold = _get_env_int(
        "CONSENSUS_CONF_THRESHOLD",
        default=65,
    )

    return AISettings(
        anthropic_api_key=anthropic_api_key,
        openai_api_key=openai_api_key,
        claude_model=claude_model,
        openai_model=openai_model,
        min_confidence_threshold=min_confidence_threshold,
        cross_validation_enabled=cross_validation_enabled,
        prompt_version=prompt_version,
        shadow_mode=shadow_mode,
        ai_fallback_model=ai_fallback_model,
        consensus_4axis_mode=consensus_4axis_mode,
        consensus_score_threshold=consensus_score_threshold,
        consensus_conf_threshold=consensus_conf_threshold,
    )
