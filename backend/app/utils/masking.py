# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
APIキー・秘密情報のログマスクユーティリティ。

CLAUDE.md Security Rules #8:
  No tokens/keys in logs — mask to first 6 + last 4 chars
"""

from __future__ import annotations

import re

# 機密情報として扱う環境変数名のパターン
_SENSITIVE_PATTERNS = re.compile(
    r"(api[_-]?key|secret|private[_-]?key|password|token|webhook|credential)",
    re.IGNORECASE,
)


def mask_key(value: str, prefix_len: int = 6, suffix_len: int = 4) -> str:
    """
    APIキーをマスクする。先頭 prefix_len 文字 + "..." + 末尾 suffix_len 文字を残す。

    Args:
        value: マスク対象の文字列
        prefix_len: 先頭に残す文字数（デフォルト: 6）
        suffix_len: 末尾に残す文字数（デフォルト: 4）

    Returns:
        マスク済みの文字列。短すぎる場合は全マスク ("***") を返す。

    Examples:
        >>> mask_key("sk-abcdefg1234567890")
        'sk-abc...7890'
        >>> mask_key("short")
        '***'
    """
    if len(value) <= prefix_len + suffix_len:
        return "***"
    return value[:prefix_len] + "..." + value[-suffix_len:]


def is_sensitive_key(name: str) -> bool:
    """
    環境変数名が機密情報かどうかを判定する。

    Args:
        name: 環境変数名（例: "SLACK_WEBHOOK_URL"）

    Returns:
        機密情報とみなされる場合は True
    """
    return bool(_SENSITIVE_PATTERNS.search(name))


def mask_env_value(name: str, value: str) -> str:
    """
    環境変数名が機密情報の場合に値をマスクして返す。
    機密情報でない場合はそのまま返す。

    Args:
        name: 環境変数名
        value: 環境変数の値

    Returns:
        必要に応じてマスクされた値
    """
    if is_sensitive_key(name):
        return mask_key(value)
    return value
