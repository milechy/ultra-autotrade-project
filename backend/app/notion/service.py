# backend/app/notion/service.py

"""
Notion クライアントと内部スキーマをつなぐサービス層。

- 未処理レコードの取得
- Notion API レスポンス → NotionNewsItem への変換
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .client import NotionClient
from .schemas import NotionNewsItem


def _extract_rich_text_text(prop: Dict[str, Any]) -> Optional[str]:
    """
    Notion の rich_text / title プロパティからプレーンテキストを抽出する。
    型の違いにそこそこ寛容になるように実装している。
    """
    if not prop:
        return None

    # URL 型の場合は 'url' キーに入っていることが多い
    if "url" in prop and isinstance(prop["url"], str):
        return prop["url"]

    for key in ("rich_text", "title"):
        if key in prop and isinstance(prop[key], list) and prop[key]:
            first = prop[key][0]
            if isinstance(first, dict):
                text = first.get("plain_text")
                if isinstance(text, str):
                    return text

    return None


def _extract_select_name(prop: Dict[str, Any]) -> Optional[str]:
    """
    Notion の select プロパティから name を抽出する。
    """
    select = prop.get("select")
    if isinstance(select, dict):
        name = select.get("name")
        if isinstance(name, str):
            return name
    return None


def _extract_number(prop: Dict[str, Any]) -> Optional[float]:
    """
    Notion の number プロパティから値を抽出する。
    """
    value = prop.get("number")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_date(prop: Dict[str, Any]) -> Optional[datetime]:
    """
    Notion の date プロパティから start 日時を抽出する。
    """
    date = prop.get("date")
    if not isinstance(date, dict):
        return None

    start = date.get("start")
    if not isinstance(start, str):
        return None

    try:
        # Notion は ISO8601 形式のことが多いのでそのまま datetime へ変換
        return datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        return None


class NotionService:
    """
    NotionClient を利用して、アプリケーション層に対して
    扱いやすいモデルを返すサービス。

    Phase1 の主な責務:
      - Status == 未処理 のレコードを取得し、NotionNewsItem に変換すること
    """

    def __init__(self, client: Optional[NotionClient] = None) -> None:
        self.client = client or NotionClient()

    def fetch_unprocessed_news(self) -> List[NotionNewsItem]:
        """
        Status が『未処理』のレコードを全件取得し、
        NotionNewsItem のリストとして返す。
        """
        raw_pages = self.client.query_unprocessed_entries()
        items: List[NotionNewsItem] = []

        for page in raw_pages:
            page_id = page.get("id", "")

            properties: Dict[str, Any] = page.get("properties", {}) or {}

            url = _extract_rich_text_text(properties.get("URL", {})) or ""
            summary = _extract_rich_text_text(properties.get("Summary", {}))
            sentiment = _extract_select_name(properties.get("Sentiment", {}))
            action = _extract_select_name(properties.get("Action", {}))
            confidence = _extract_number(properties.get("Confidence", {}))
            status = _extract_select_name(properties.get("Status", {}))
            timestamp = _extract_date(properties.get("Timestamp", {}))

            # URL はこのシステムのキー情報なので、空の場合はスキップする。
            if not url:
                # ログを入れる場合はここで logging.warning などを使う想定。
                continue

            item = NotionNewsItem(
                id=page_id,
                url=url,
                summary=summary,
                sentiment=sentiment,
                action=action,
                confidence=confidence,
                status=status,
                timestamp=timestamp,
            )
            items.append(item)

        return items

