# backend/app/ai/config.py

"""
AI 判定モジュール関連の設定値読み出しモジュール。

- 環境変数から LLM API キーやモデル名、判定パラメータを取得する
- 全キーはオプション（graceful degradation）—— キー未設定時は HOLD にフォールバック
"""

from dataclasses import dataclass
from typing import Optional

from app.utils.config import get_env


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


def get_ai_settings() -> AISettings:
    """
    AISettings を構築して返す。

    全キーはオプション（graceful degradation）:
      - ANTHROPIC_API_KEY（未設定時: None）
      - OPENAI_API_KEY（未設定時: None）
      - AI_CLAUDE_MODEL（デフォルト: claude-sonnet-4-20250514）
      - AI_OPENAI_MODEL（デフォルト: gpt-4o）
      - AI_MIN_CONFIDENCE_THRESHOLD（デフォルト: 40）
      - AI_CROSS_VALIDATION_ENABLED（デフォルト: True）
      - AI_PROMPT_VERSION（デフォルト: v1）
    """
    anthropic_api_key = get_env("ANTHROPIC_API_KEY", required=False)
    openai_api_key = get_env("OPENAI_API_KEY", required=False)

    claude_model = get_env("AI_CLAUDE_MODEL", required=False) or "claude-sonnet-4-20250514"
    openai_model = get_env("AI_OPENAI_MODEL", required=False) or "gpt-4o"
    ai_fallback_model = get_env("AI_FALLBACK_MODEL", required=False) or "claude-sonnet-4-20250514"

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
    )
