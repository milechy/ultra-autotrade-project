# backend/tests/test_workflow_service.py
"""
WorkflowService のユニットテスト。

Notion → AI → OctoBot → Notion書き戻し のフロー全体をテスト。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from app.ai.service import AIService
from app.automation.state import reset_state
from app.automation.workflow import WorkflowService
from app.notion.schemas import NotionNewsItem


@pytest.fixture(autouse=True)
def reset_monitoring_state() -> None:
    """各テスト前に MonitoringService の状態をリセット。"""
    reset_state()


class MockNotionService:
    """NotionService のモック。"""

    def __init__(self, items: List[NotionNewsItem] = None) -> None:
        self.items = items or []
        self.updated_pages: List[Dict[str, Any]] = []
        self.error_pages: List[Dict[str, Any]] = []

    def fetch_unprocessed_news(self) -> List[NotionNewsItem]:
        return self.items

    def update_item_with_ai_result(
        self,
        page_id: str,
        action: str,
        confidence: int,
        sentiment: str = None,
        summary: str = None,
    ) -> None:
        self.updated_pages.append(
            {
                "page_id": page_id,
                "action": action,
                "confidence": confidence,
                "sentiment": sentiment,
                "summary": summary,
                "status": "処理済",
            }
        )

    def update_item_with_error(
        self,
        page_id: str,
        error_message: str,
        action: str = None,
        confidence: int = None,
    ) -> None:
        self.error_pages.append(
            {
                "page_id": page_id,
                "error_message": error_message,
                "action": action,
                "confidence": confidence,
                "status": "エラー",
            }
        )


class MockOctoBotClient:
    """OctoBotClient のモック。"""

    def __init__(self) -> None:
        self.sent_payloads: List[Dict[str, Any]] = []

    def send_signal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.sent_payloads.append(payload)
        return {"status": "ok"}


class FailingOctoBotClient:
    """OctoBot 送信が失敗するモッククライアント。"""

    def __init__(self, fail_for_ids: List[str] = None) -> None:
        self.fail_for_ids = fail_for_ids or []
        self.sent_payloads: List[Dict[str, Any]] = []

    def send_signal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.sent_payloads.append(payload)
        # テスト用: 特定の ID または全てを失敗させる
        raise Exception("OctoBot API connection failed")


def test_workflow_no_news() -> None:
    """未処理ニュースがない場合のテスト。"""
    notion_service = MockNotionService(items=[])
    ai_service = AIService()

    octobot_client = MockOctoBotClient()
    from app.bots.service import OctoBotService

    octobot_service = OctoBotService(
        client=octobot_client,
        min_confidence=70,
        max_same_action_per_hour=10,
    )

    workflow = WorkflowService(
        notion_service=notion_service,
        ai_service=ai_service,
        octobot_service=octobot_service,
    )

    result = workflow.process_pending_news()

    assert result.fetched_count == 0
    assert result.analyzed_count == 0
    assert result.octobot_success_count == 0
    assert result.notion_updated_count == 0
    assert len(result.errors) == 0


def test_workflow_with_bullish_news() -> None:
    """ポジティブニュースの場合、BUY → OctoBot送信 → Notion更新。"""
    now = datetime.now(timezone.utc)

    # bullish キーワードを含むニュース
    items = [
        NotionNewsItem(
            id="page-001",
            url="https://example.com/bullish-news",
            summary="Record profit and bullish outlook for BTC",
            sentiment=None,
            action=None,
            confidence=None,
            status="未処理",
            timestamp=now,
        ),
    ]

    notion_service = MockNotionService(items=items)
    ai_service = AIService()

    octobot_client = MockOctoBotClient()
    from app.bots.service import OctoBotService

    octobot_service = OctoBotService(
        client=octobot_client,
        min_confidence=70,
        max_same_action_per_hour=10,
    )

    workflow = WorkflowService(
        notion_service=notion_service,
        ai_service=ai_service,
        octobot_service=octobot_service,
    )

    result = workflow.process_pending_news()

    # 1件取得、1件分析、1件OctoBot送信、1件Notion更新
    assert result.fetched_count == 1
    assert result.analyzed_count == 1
    assert result.octobot_success_count == 1
    assert result.notion_updated_count == 1
    assert len(result.errors) == 0

    # OctoBot に BUY シグナルが送信されたことを確認
    assert len(octobot_client.sent_payloads) == 1
    assert octobot_client.sent_payloads[0]["action"] == "BUY"

    # Notion に書き戻されたことを確認
    assert len(notion_service.updated_pages) == 1
    assert notion_service.updated_pages[0]["page_id"] == "page-001"
    assert notion_service.updated_pages[0]["action"] == "BUY"


def test_workflow_with_neutral_news() -> None:
    """中立ニュースの場合、HOLD → OctoBot送信なし → Notion更新のみ。"""
    now = datetime.now(timezone.utc)

    # 中立ニュース（ポジティブ/ネガティブキーワードなし）
    items = [
        NotionNewsItem(
            id="page-002",
            url="https://example.com/neutral-news",
            summary="Market remains stable today",
            sentiment=None,
            action=None,
            confidence=None,
            status="未処理",
            timestamp=now,
        ),
    ]

    notion_service = MockNotionService(items=items)
    ai_service = AIService()

    octobot_client = MockOctoBotClient()
    from app.bots.service import OctoBotService

    octobot_service = OctoBotService(
        client=octobot_client,
        min_confidence=70,
        max_same_action_per_hour=10,
    )

    workflow = WorkflowService(
        notion_service=notion_service,
        ai_service=ai_service,
        octobot_service=octobot_service,
    )

    result = workflow.process_pending_news()

    # 1件取得、1件分析、0件OctoBot送信（HOLDなので）、1件Notion更新
    assert result.fetched_count == 1
    assert result.analyzed_count == 1
    assert result.octobot_success_count == 0  # HOLD はシグナル送信しない
    assert result.notion_updated_count == 1
    assert len(result.errors) == 0

    # OctoBot には何も送信されない
    assert len(octobot_client.sent_payloads) == 0

    # Notion には HOLD として書き戻される
    assert len(notion_service.updated_pages) == 1
    assert notion_service.updated_pages[0]["action"] == "HOLD"


def test_workflow_with_multiple_news() -> None:
    """複数ニュースの処理テスト。"""
    now = datetime.now(timezone.utc)

    items = [
        NotionNewsItem(
            id="page-001",
            url="https://example.com/bullish",
            summary="Record profit announced",
            sentiment=None,
            action=None,
            confidence=None,
            status="未処理",
            timestamp=now,
        ),
        NotionNewsItem(
            id="page-002",
            url="https://example.com/bearish",
            summary="Fraud scandal reported",
            sentiment=None,
            action=None,
            confidence=None,
            status="未処理",
            timestamp=now,
        ),
        NotionNewsItem(
            id="page-003",
            url="https://example.com/neutral",
            summary="Regular market update",
            sentiment=None,
            action=None,
            confidence=None,
            status="未処理",
            timestamp=now,
        ),
    ]

    notion_service = MockNotionService(items=items)
    ai_service = AIService()

    octobot_client = MockOctoBotClient()
    from app.bots.service import OctoBotService

    octobot_service = OctoBotService(
        client=octobot_client,
        min_confidence=70,
        max_same_action_per_hour=10,
    )

    workflow = WorkflowService(
        notion_service=notion_service,
        ai_service=ai_service,
        octobot_service=octobot_service,
    )

    result = workflow.process_pending_news()

    # 3件取得、3件分析、2件OctoBot送信（BUY + SELL）、3件Notion更新
    assert result.fetched_count == 3
    assert result.analyzed_count == 3
    assert result.octobot_success_count == 2  # BUY + SELL
    assert result.notion_updated_count == 3
    assert len(result.errors) == 0

    # OctoBot に 2件送信 (BUY, SELL)
    assert len(octobot_client.sent_payloads) == 2
    actions = {p["action"] for p in octobot_client.sent_payloads}
    assert actions == {"BUY", "SELL"}

    # Notion には 3件更新
    assert len(notion_service.updated_pages) == 3


def test_workflow_octobot_failure_marks_notion_as_error() -> None:
    """OctoBot 送信失敗時、Notion ステータスが「エラー」になるテスト。"""
    now = datetime.now(timezone.utc)

    # bullish キーワードを含むニュース（BUY シグナルになる）
    items = [
        NotionNewsItem(
            id="page-fail-001",
            url="https://example.com/bullish-news",
            summary="Record profit and bullish outlook for BTC",
            sentiment=None,
            action=None,
            confidence=None,
            status="未処理",
            timestamp=now,
        ),
    ]

    notion_service = MockNotionService(items=items)
    ai_service = AIService()

    # 失敗するクライアントを使用
    failing_client = FailingOctoBotClient()
    from app.bots.service import OctoBotService

    octobot_service = OctoBotService(
        client=failing_client,
        min_confidence=70,
        max_same_action_per_hour=10,
    )

    workflow = WorkflowService(
        notion_service=notion_service,
        ai_service=ai_service,
        octobot_service=octobot_service,
    )

    result = workflow.process_pending_news()

    # 1件取得、1件分析、0件成功、1件失敗
    assert result.fetched_count == 1
    assert result.analyzed_count == 1
    assert result.octobot_success_count == 0
    assert result.octobot_failed_count == 1
    assert result.notion_updated_count == 1

    # Notion に「エラー」ステータスで書き戻されたことを確認
    assert len(notion_service.error_pages) == 1
    assert notion_service.error_pages[0]["page_id"] == "page-fail-001"
    assert notion_service.error_pages[0]["status"] == "エラー"
    assert notion_service.error_pages[0]["action"] == "BUY"

    # 通常の処理済更新は呼ばれない
    assert len(notion_service.updated_pages) == 0


def test_workflow_partial_octobot_failure() -> None:
    """OctoBot が一部失敗した場合、失敗分だけ「エラー」になるテスト。"""
    now = datetime.now(timezone.utc)

    items = [
        NotionNewsItem(
            id="page-001",
            url="https://example.com/bullish",
            summary="Record profit announced",
            sentiment=None,
            action=None,
            confidence=None,
            status="未処理",
            timestamp=now,
        ),
        NotionNewsItem(
            id="page-002",
            url="https://example.com/neutral",
            summary="Regular market update",  # HOLD になる
            sentiment=None,
            action=None,
            confidence=None,
            status="未処理",
            timestamp=now,
        ),
    ]

    notion_service = MockNotionService(items=items)
    ai_service = AIService()

    # 失敗するクライアントを使用（BUY シグナルのみ失敗）
    failing_client = FailingOctoBotClient()
    from app.bots.service import OctoBotService

    octobot_service = OctoBotService(
        client=failing_client,
        min_confidence=70,
        max_same_action_per_hour=10,
    )

    workflow = WorkflowService(
        notion_service=notion_service,
        ai_service=ai_service,
        octobot_service=octobot_service,
    )

    result = workflow.process_pending_news()

    # 2件取得、2件分析
    assert result.fetched_count == 2
    assert result.analyzed_count == 2

    # BUY シグナル（page-001）は失敗 → エラー
    # HOLD シグナル（page-002）は OctoBot 送信なし → 処理済
    assert result.octobot_failed_count == 1
    assert result.notion_updated_count == 2

    # page-001 はエラーステータス
    assert len(notion_service.error_pages) == 1
    assert notion_service.error_pages[0]["page_id"] == "page-001"
    assert notion_service.error_pages[0]["status"] == "エラー"

    # page-002 は処理済（HOLD は OctoBot 送信しないので失敗しない）
    assert len(notion_service.updated_pages) == 1
    assert notion_service.updated_pages[0]["page_id"] == "page-002"
    assert notion_service.updated_pages[0]["status"] == "処理済"
    assert notion_service.updated_pages[0]["action"] == "HOLD"
