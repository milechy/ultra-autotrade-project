# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notion/service.py

"""
Notion クライアントと内部スキーマをつなぐサービス層。

- 未処理レコードの取得
- Notion API レスポンス → NotionNewsItem への変換
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .client import NotionClient
from .schemas import NotionNewsItem

logger = logging.getLogger(__name__)


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

    def update_item_with_ai_result(
        self,
        page_id: str,
        action: str,
        confidence: int,
        sentiment: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> None:
        """
        AI 判定結果を Notion ページに書き戻す。

        Args:
            page_id: Notion ページ ID
            action: BUY / SELL / HOLD
            confidence: 信頼度 (0-100)
            sentiment: センチメント (positive / negative / neutral)
            summary: 要約テキスト
        """
        properties: Dict[str, Any] = {
            "Action": {"select": {"name": action}},
            "Confidence": {"number": confidence},
            "Status": {"select": {"name": "処理済"}},
            "Timestamp": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        }

        if sentiment:
            properties["Sentiment"] = {"select": {"name": sentiment}}

        if summary:
            properties["Summary"] = {"rich_text": [{"text": {"content": summary[:2000]}}]}

        try:
            self.client.update_page_properties(page_id, properties)
            logger.info(
                "Updated Notion page: page_id=%s, action=%s, confidence=%d",
                page_id,
                action,
                confidence,
            )
        except Exception as exc:
            logger.error(
                "Failed to update Notion page: page_id=%s, error=%s",
                page_id,
                exc,
            )
            raise

    def update_item_with_error(
        self,
        page_id: str,
        error_message: str,
        action: Optional[str] = None,
        confidence: Optional[int] = None,
    ) -> None:
        """
        OctoBot 送信失敗時に Notion ページを「エラー」ステータスに更新する。

        次回の cron 実行時に再処理されるよう、Status を「エラー」に設定する。

        Args:
            page_id: Notion ページ ID
            error_message: エラーメッセージ（Summary に記録）
            action: AI 判定結果（記録用）
            confidence: 信頼度（記録用）
        """
        properties: Dict[str, Any] = {
            "Status": {"select": {"name": "エラー"}},
            "Timestamp": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
            "Summary": {"rich_text": [{"text": {"content": f"[ERROR] {error_message[:1900]}"}}]},
        }

        if action:
            properties["Action"] = {"select": {"name": action}}

        if confidence is not None:
            properties["Confidence"] = {"number": confidence}

        try:
            self.client.update_page_properties(page_id, properties)
            logger.warning(
                "Updated Notion page with error status: page_id=%s, error=%s",
                page_id,
                error_message,
            )
        except Exception as exc:
            logger.error(
                "Failed to update Notion page with error: page_id=%s, error=%s",
                page_id,
                exc,
            )
            raise
