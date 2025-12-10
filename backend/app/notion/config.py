# backend/app/notion/config.py

"""
Notion 連携に必要な設定値をまとめるモジュール。
"""

from dataclasses import dataclass
from functools import lru_cache

from app.utils.config import get_env

@dataclass(frozen=True)
class NotionConfig:
    """Notion API 用の設定値コンテナ。"""

    api_key: str
    database_id: str
    api_base_url: str
    api_version: str


@lru_cache()
def get_notion_config() -> NotionConfig:
    """
    環境変数から Notion 設定を読み込む。

    必須:
      - NOTION_API_KEY
      - NOTION_DATABASE_ID

    任意:
      - NOTION_API_BASE_URL (デフォルト: https://api.notion.com/v1)
      - NOTION_API_VERSION   (デフォルト: 2022-06-28)
    """
    api_key = get_env("NOTION_API_KEY")
    database_id = get_env("NOTION_DATABASE_ID")

    api_base_url = get_env(
        "NOTION_API_BASE_URL",
        default="https://api.notion.com/v1",
        required=False,
    )
    api_version = get_env(
        "NOTION_API_VERSION",
        default="2022-06-28",
        required=False,
    )

    return NotionConfig(
        api_key=api_key,
        database_id=database_id,
        api_base_url=api_base_url,
        api_version=api_version,
    )

