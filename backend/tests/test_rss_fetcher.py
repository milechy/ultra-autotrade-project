# backend/tests/test_rss_fetcher.py

"""
RSS フェッチャーのユニットテスト。

全テストはモックを使用し、外部 HTTP 通信を行わない。
"""

from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.knowledge.service import KnowledgeService
from app.rss.fetcher import RSSFetcher
from app.rss.schemas import RSSFeedConfig


def _make_feed_entry(title: str = "Test Title", link: str = "https://example.com/1") -> MagicMock:
    """feedparser エントリの MagicMock を生成するヘルパー。"""
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.summary = "Test summary text"
    entry.published_parsed = None
    entry.published = None
    entry.updated_parsed = None
    return entry


def _make_feed_result(entries: list[MagicMock]) -> MagicMock:
    """feedparser.parse() の戻り値 MagicMock を生成するヘルパー。"""
    feed = MagicMock()
    feed.entries = entries
    return feed


class TestFetchAndRegisterNewEntries:
    """新規エントリを登録する正常系テスト。"""

    @patch("app.rss.fetcher.feedparser")
    def test_fetch_and_register_new_entries(self, mock_feedparser: MagicMock) -> None:
        """2件の新規エントリを登録できること。"""
        # feedparser.parse() が 2 件のエントリを返す
        entries = [
            _make_feed_entry("Title 1", "https://example.com/1"),
            _make_feed_entry("Title 2", "https://example.com/2"),
        ]
        mock_feedparser.parse.return_value = _make_feed_result(entries)

        # DB: 重複なし（first() が None を返す）
        db = MagicMock(spec=Session)
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = None

        # KnowledgeService モック
        knowledge_service = MagicMock(spec=KnowledgeService)
        knowledge_service.create_item.return_value = MagicMock()

        fetcher = RSSFetcher(
            knowledge_service=knowledge_service,
            feeds=[RSSFeedConfig(name="TestFeed", url="https://example.com/rss", enabled=True)],
        )
        results = fetcher.fetch_and_register(db)

        assert results == {"TestFeed": 2}
        assert knowledge_service.create_item.call_count == 2


class TestDuplicateUrlsSkipped:
    """重複 URL をスキップするテスト。"""

    @patch("app.rss.fetcher.feedparser")
    def test_duplicate_urls_skipped(self, mock_feedparser: MagicMock) -> None:
        """DB に既存のエントリは登録されないこと。"""
        entries = [
            _make_feed_entry("Title 1", "https://example.com/1"),
        ]
        mock_feedparser.parse.return_value = _make_feed_result(entries)

        # DB: 重複あり（first() が既存レコードの MagicMock を返す）
        db = MagicMock(spec=Session)
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = MagicMock()  # 既存レコードあり

        knowledge_service = MagicMock(spec=KnowledgeService)

        fetcher = RSSFetcher(
            knowledge_service=knowledge_service,
            feeds=[RSSFeedConfig(name="TestFeed", url="https://example.com/rss", enabled=True)],
        )
        results = fetcher.fetch_and_register(db)

        assert results == {"TestFeed": 0}
        knowledge_service.create_item.assert_not_called()


class TestDisabledFeedSkipped:
    """無効化されたフィードをスキップするテスト。"""

    @patch("app.rss.fetcher.feedparser")
    def test_disabled_feed_skipped(self, mock_feedparser: MagicMock) -> None:
        """enabled=False のフィードは処理されないこと。"""
        db = MagicMock(spec=Session)
        knowledge_service = MagicMock(spec=KnowledgeService)

        fetcher = RSSFetcher(
            knowledge_service=knowledge_service,
            feeds=[
                RSSFeedConfig(name="DisabledFeed", url="https://example.com/rss", enabled=False)
            ],
        )
        results = fetcher.fetch_and_register(db)

        # 無効フィードはスキップされるので results に含まれない
        assert "DisabledFeed" not in results
        mock_feedparser.parse.assert_not_called()
        knowledge_service.create_item.assert_not_called()


class TestFeedFetchErrorHandled:
    """フィード取得エラーのハンドリングテスト。"""

    @patch("app.rss.fetcher.feedparser")
    def test_feed_fetch_error_handled(self, mock_feedparser: MagicMock) -> None:
        """feedparser.parse() が例外を送出しても例外が伝播しないこと。"""
        mock_feedparser.parse.side_effect = Exception("Connection error")

        db = MagicMock(spec=Session)
        knowledge_service = MagicMock(spec=KnowledgeService)

        fetcher = RSSFetcher(
            knowledge_service=knowledge_service,
            feeds=[RSSFeedConfig(name="TestFeed", url="https://example.com/rss", enabled=True)],
        )

        # 例外が伝播しないこと
        results = fetcher.fetch_and_register(db)

        assert results == {"TestFeed": 0}
        knowledge_service.create_item.assert_not_called()


class TestEmptyFeedReturnsZero:
    """空フィードのテスト。"""

    @patch("app.rss.fetcher.feedparser")
    def test_empty_feed_returns_zero(self, mock_feedparser: MagicMock) -> None:
        """エントリが 0 件のフィードは 0 を返すこと。"""
        mock_feedparser.parse.return_value = _make_feed_result([])

        db = MagicMock(spec=Session)
        knowledge_service = MagicMock(spec=KnowledgeService)

        fetcher = RSSFetcher(
            knowledge_service=knowledge_service,
            feeds=[RSSFeedConfig(name="TestFeed", url="https://example.com/rss", enabled=True)],
        )
        results = fetcher.fetch_and_register(db)

        assert results == {"TestFeed": 0}
        knowledge_service.create_item.assert_not_called()
