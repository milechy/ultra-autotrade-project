# backend/app/rss/fetcher.py

"""
RSS フェッチャー。

CoinPost / CoinTelegraph Japan などの RSS フィードを取得し、
Knowledge Hub に登録する。

- feedparser を使用して RSS/Atom フィードを解析する
- 重複チェック: KnowledgeSource.source_url の一致で確認する
- エラー発生時は fail-safe でログを残してスキップする
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, cast

from sqlalchemy.orm import Session

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None  # type: ignore[assignment,unused-ignore]

from app.knowledge.models import KnowledgeSource
from app.knowledge.schemas import KnowledgeCreateRequest, KnowledgeItemType
from app.knowledge.service import KnowledgeService
from app.rss.schemas import RSSFeedConfig

logger = logging.getLogger(__name__)

# デフォルト RSS フィード設定
DEFAULT_FEEDS: list[RSSFeedConfig] = [
    RSSFeedConfig(
        name="CoinPost",
        url="https://coinpost.jp/?feed=rss2",
        enabled=True,
    ),
    RSSFeedConfig(
        name="CoinTelegraph Japan",
        url="https://jp.cointelegraph.com/rss",
        enabled=True,
    ),
]


def _parse_published_at(entry: object) -> Optional[datetime]:
    """
    feedparser エントリから公開日時を取得する。

    published_parsed → published → updated_parsed の優先順位で試みる。
    失敗した場合は None を返す。
    """
    # published_parsed (time.struct_time)
    published_parsed = getattr(entry, "published_parsed", None)
    if published_parsed is not None:
        try:
            import calendar

            ts = calendar.timegm(published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass

    # published (RFC 2822 文字列)
    published = getattr(entry, "published", None)
    if published:
        try:
            return cast(datetime, parsedate_to_datetime(published))
        except Exception:
            pass

    # updated_parsed (time.struct_time)
    updated_parsed = getattr(entry, "updated_parsed", None)
    if updated_parsed is not None:
        try:
            import calendar

            ts = calendar.timegm(updated_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass

    return None


class RSSFetcher:
    """
    RSS フィードを取得して Knowledge Hub に登録するクラス。

    - feedparser で RSS/Atom を解析する
    - 重複 URL は app レイヤーでチェックしてスキップする
    - エラーは fail-safe: 警告ログを残して処理を継続する
    """

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        feeds: Optional[list[RSSFeedConfig]] = None,
    ) -> None:
        self._knowledge_service = knowledge_service
        self._feeds = feeds if feeds is not None else DEFAULT_FEEDS

    def fetch_and_register(self, db: Session, max_per_feed: int = 10) -> dict[str, int]:
        """
        全有効フィードを取得して Knowledge Hub に登録する。

        Args:
            db: SQLAlchemy セッション
            max_per_feed: フィードあたりの最大登録件数

        Returns:
            dict[str, int]: フィード名 → 登録件数のマッピング
        """
        results: dict[str, int] = {}

        for feed_config in self._feeds:
            if not feed_config.enabled:
                logger.debug("RSS feed disabled, skipping: %s", feed_config.name)
                continue

            count = self._process_feed(db, feed_config, max_per_feed)
            results[feed_config.name] = count

        total = sum(results.values())
        logger.info(
            "RSS fetch completed",
            extra={"results": results, "total": total},
        )

        return results

    def _process_feed(self, db: Session, feed_config: RSSFeedConfig, max_per_feed: int) -> int:
        """
        単一フィードを取得して Knowledge Hub に登録する。

        Args:
            db: SQLAlchemy セッション
            feed_config: フィード設定
            max_per_feed: 最大登録件数

        Returns:
            int: 登録した件数
        """
        if feedparser is None:  # pragma: no cover
            logger.warning("feedparser is not installed. Install it with: pip install feedparser")
            return 0

        try:
            feed = feedparser.parse(feed_config.url)
        except Exception as exc:
            logger.warning(
                "Failed to fetch RSS feed: %s — %s",
                feed_config.name,
                exc,
            )
            return 0

        entries = getattr(feed, "entries", [])
        if not entries:
            logger.debug("No entries found in feed: %s", feed_config.name)
            return 0

        registered = 0

        for entry in entries[:max_per_feed]:
            # URL を取得する（link → id の優先順）
            url: Optional[str] = getattr(entry, "link", None) or getattr(entry, "id", None)
            if not url:
                logger.debug("Skipping entry without URL in feed: %s", feed_config.name)
                continue

            # 重複チェック（app レイヤーで確認）
            existing = db.query(KnowledgeSource).filter_by(source_url=url).first()
            if existing is not None:
                logger.debug("Duplicate URL, skipping: %s", url)
                continue

            # タイトルと要約を取得する
            title: Optional[str] = getattr(entry, "title", None)
            summary: Optional[str] = getattr(entry, "summary", None) or getattr(
                entry, "description", None
            )

            # KnowledgeCreateRequest を構築する
            # URL 種別で登録するとスクレイピングが発生するため、
            # 要約がある場合は TEXT 種別で要約テキストを使用する
            if summary:
                request = KnowledgeCreateRequest(
                    title=title,
                    item_type=KnowledgeItemType.TEXT,
                    source_url=url,
                    raw_text=summary,
                )
            else:
                request = KnowledgeCreateRequest(
                    title=title,
                    item_type=KnowledgeItemType.URL,
                    source_url=url,
                )

            try:
                self._knowledge_service.create_item(db, request)
                registered += 1
                logger.debug("Registered RSS entry: %s", url)
            except Exception as exc:
                logger.debug(
                    "Failed to register RSS entry: %s — %s",
                    url,
                    exc,
                )
                continue

        logger.info(
            "RSS feed processed",
            extra={"feed": feed_config.name, "registered": registered},
        )

        return registered
