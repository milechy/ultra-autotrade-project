# backend/app/utils/config.py

"""
環境変数読み取り用のユーティリティ。
Notion だけでなく、今後の AI / OctoBot / Aave でも共通利用できる想定。
"""

import os
from typing import Optional


class EnvVarMissingError(RuntimeError):
    """必須環境変数が設定されていない場合に投げる例外。"""

    def __init__(self, name: str) -> None:
        super().__init__(f"Required environment variable '{name}' is not set.")
        self.name = name


def get_env(
    name: str,
    default: Optional[str] = None,
    *,
    required: bool = True,
) -> str:
    """
    環境変数を取得するヘルパー。

    :param name: 環境変数名
    :param default: デフォルト値（required=False の場合のみ使用）
    :param required: True の場合、未設定なら例外を投げる
    :return: 文字列値
    """
    value = os.getenv(name)

    if value is None or value == "":
        if required:
            raise EnvVarMissingError(name)
        return default

    return value

