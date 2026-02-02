# backend/app/automation/workflow.py
"""
Notion → AI → OctoBot → Notion書き戻し の自動フロー オーケストレーター。

責務:
- NotionService から未処理ニュースを取得
- AIService で判定
- OctoBotService でシグナル送信
- NotionService に結果を書き戻し
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.ai.schemas import AIAnalysisResult, TradeAction
from app.ai.service import AIService
from app.bots.schemas import (
    OctoBotSignal,
    OctoBotSignalRequest,
    OctoBotSignalResponse,
    OctoBotSignalStatus,
)
from app.bots.service import OctoBotService
from app.notion.service import NotionService

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """ワークフロー実行結果のサマリ。"""

    fetched_count: int
    analyzed_count: int
    octobot_success_count: int
    octobot_skipped_count: int
    octobot_failed_count: int
    notion_updated_count: int
    errors: List[str]


class WorkflowService:
    """
    Notion → AI → OctoBot → Notion書き戻しのオーケストレーター。

    各サービスをコンストラクタで受け取り、DI を可能にする。
    """

    def __init__(
        self,
        notion_service: NotionService,
        ai_service: AIService,
        octobot_service: OctoBotService,
    ) -> None:
        self._notion = notion_service
        self._ai = ai_service
        self._octobot = octobot_service

    def process_pending_news(self) -> WorkflowResult:
        """
        未処理ニュースを取得し、AI判定→OctoBot送信→Notion書き戻しを行う。

        Returns:
            WorkflowResult: 処理結果のサマリ
        """
        errors: List[str] = []
        fetched_count = 0
        analyzed_count = 0
        octobot_success = 0
        octobot_skipped = 0
        octobot_failed = 0
        notion_updated = 0

        # 1. Notion から未処理ニュースを取得
        logger.info("Workflow: fetching unprocessed news from Notion")
        try:
            news_items = self._notion.fetch_unprocessed_news()
            fetched_count = len(news_items)
            logger.info("Workflow: fetched %d unprocessed news items", fetched_count)
        except Exception as exc:
            error_msg = f"Failed to fetch news from Notion: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
            return WorkflowResult(
                fetched_count=0,
                analyzed_count=0,
                octobot_success_count=0,
                octobot_skipped_count=0,
                octobot_failed_count=0,
                notion_updated_count=0,
                errors=errors,
            )

        if fetched_count == 0:
            logger.info("Workflow: no unprocessed news to process")
            return WorkflowResult(
                fetched_count=0,
                analyzed_count=0,
                octobot_success_count=0,
                octobot_skipped_count=0,
                octobot_failed_count=0,
                notion_updated_count=0,
                errors=[],
            )

        # 2. AI で判定
        logger.info("Workflow: analyzing %d news items with AI", fetched_count)
        try:
            ai_results = self._ai.analyze_items(news_items)
            analyzed_count = len(ai_results)
            logger.info("Workflow: AI analyzed %d items", analyzed_count)
        except Exception as exc:
            error_msg = f"AI analysis failed: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
            return WorkflowResult(
                fetched_count=fetched_count,
                analyzed_count=0,
                octobot_success_count=0,
                octobot_skipped_count=0,
                octobot_failed_count=0,
                notion_updated_count=0,
                errors=errors,
            )

        # 3. OctoBot へシグナル送信
        # 失敗したシグナルの ID とエラーメッセージを追跡
        failed_signal_ids: dict[str, str] = {}
        response: Optional[OctoBotSignalResponse] = None

        signals = self._convert_to_octobot_signals(ai_results)
        if signals:
            logger.info("Workflow: sending %d signals to OctoBot", len(signals))
            try:
                request = OctoBotSignalRequest(signals=signals, count=len(signals))
                response = self._octobot.process_signals(request)
                octobot_success = response.success_count
                octobot_skipped = response.skipped_count
                octobot_failed = response.failed_count
                logger.info(
                    "Workflow: OctoBot result - sent=%d, skipped=%d, failed=%d",
                    octobot_success,
                    octobot_skipped,
                    octobot_failed,
                )

                # 失敗したシグナルの ID を記録
                for detail in response.details:
                    if detail.status == OctoBotSignalStatus.FAILED:
                        failed_signal_ids[detail.id] = detail.message or "OctoBot送信失敗"
                        logger.warning(
                            "OctoBot signal failed: id=%s, message=%s",
                            detail.id,
                            detail.message,
                        )
            except Exception as exc:
                error_msg = f"OctoBot signal processing failed: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)
                # 全シグナルを失敗として扱う
                octobot_failed = len(signals)
                for signal in signals:
                    failed_signal_ids[signal.id] = str(exc)
        else:
            logger.info("Workflow: no signals to send to OctoBot")

        # 4. Notion に結果を書き戻し
        # 失敗したシグナルは「エラー」ステータスに、成功・スキップは「処理済」に
        logger.info("Workflow: updating Notion with AI results")
        for result in ai_results:
            try:
                if result.id in failed_signal_ids:
                    # OctoBot 送信失敗 → 「エラー」ステータスで次回再処理
                    self._notion.update_item_with_error(
                        page_id=result.id,
                        error_message=failed_signal_ids[result.id],
                        action=result.action.value,
                        confidence=result.confidence,
                    )
                    logger.info(
                        "Notion page marked as error for retry: page_id=%s",
                        result.id,
                    )
                else:
                    # 成功 or スキップ or HOLD → 「処理済」
                    self._notion.update_item_with_ai_result(
                        page_id=result.id,
                        action=result.action.value,
                        confidence=result.confidence,
                        sentiment=result.sentiment,
                        summary=result.summary,
                    )
                notion_updated += 1
            except Exception as exc:
                error_msg = f"Failed to update Notion page {result.id}: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)

        logger.info(
            "Workflow: completed - fetched=%d, analyzed=%d, octobot_sent=%d, notion_updated=%d",
            fetched_count,
            analyzed_count,
            octobot_success,
            notion_updated,
        )

        return WorkflowResult(
            fetched_count=fetched_count,
            analyzed_count=analyzed_count,
            octobot_success_count=octobot_success,
            octobot_skipped_count=octobot_skipped,
            octobot_failed_count=octobot_failed,
            notion_updated_count=notion_updated,
            errors=errors,
        )

    def _convert_to_octobot_signals(
        self, ai_results: List[AIAnalysisResult]
    ) -> List[OctoBotSignal]:
        """
        AIAnalysisResult を OctoBotSignal に変換する。

        HOLD アクションはシグナル送信対象外とする。
        """
        signals: List[OctoBotSignal] = []

        for result in ai_results:
            # HOLD はシグナル送信対象外
            if result.action == TradeAction.HOLD:
                logger.debug(
                    "Skipping HOLD signal for id=%s", result.id
                )
                continue

            signal = OctoBotSignal(
                id=result.id,
                url=result.url,
                action=result.action,
                confidence=result.confidence,
                reason=result.reason or "AI判定によるシグナル",
                timestamp=result.timestamp,
            )
            signals.append(signal)

        return signals
