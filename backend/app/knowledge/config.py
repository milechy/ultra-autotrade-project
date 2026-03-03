# backend/app/knowledge/config.py

"""
Knowledge Hub 関連の設定値読み出しモジュール。

- 環境変数から OpenAI API キーや埋め込みモデルのパラメータを取得する
- デフォルト値は実用的かつ安全な値に設定する
"""

from dataclasses import dataclass
from typing import Optional

from app.utils.config import get_env


@dataclass
class KnowledgeSettings:
    """
    Knowledge Hub 運用に関する設定値のまとまり。

    NOTE:
    - openai_api_key は OPENAI_API_KEY 環境変数から取得する。
    - 埋め込みモデルは text-embedding-3-small をデフォルトとする（コスト効率優先）。
    - chunk_size_tokens / chunk_overlap_tokens は RAG の検索精度に影響する。
    """

    openai_api_key: str
    embedding_model: str      # default: text-embedding-3-small
    embedding_dimensions: int  # default: 1536
    chunk_size_tokens: int    # default: 500
    chunk_overlap_tokens: int  # default: 50
    search_top_k: int         # default: 5


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
        raise RuntimeError(
            f"Invalid integer value for env var {name}: {raw!r}"
        ) from exc


def get_knowledge_settings() -> KnowledgeSettings:
    """
    KnowledgeSettings を構築して返す。

    OPENAI_API_KEY は必須。その他は省略可能でデフォルト値を使用。
    """
    openai_api_key = get_env("OPENAI_API_KEY", required=False) or ""

    embedding_model = (
        get_env("KNOWLEDGE_EMBEDDING_MODEL", required=False)
        or "text-embedding-3-small"
    )

    embedding_dimensions = _get_env_int(
        "KNOWLEDGE_EMBEDDING_DIMENSIONS",
        default=1536,
    )

    chunk_size_tokens = _get_env_int(
        "KNOWLEDGE_CHUNK_SIZE_TOKENS",
        default=500,
    )

    chunk_overlap_tokens = _get_env_int(
        "KNOWLEDGE_CHUNK_OVERLAP_TOKENS",
        default=50,
    )

    search_top_k = _get_env_int(
        "KNOWLEDGE_SEARCH_TOP_K",
        default=5,
    )

    return KnowledgeSettings(
        openai_api_key=openai_api_key,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
        search_top_k=search_top_k,
    )
