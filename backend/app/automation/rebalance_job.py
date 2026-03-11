# backend/app/automation/rebalance_job.py

"""4時間ごとにアロケーション乖離をチェックし、閾値超過時はSlack通知する。自動実行はしない。"""

import asyncio
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

REBALANCE_CHECK_INTERVAL_SECONDS = 14400  # 4 hours


async def rebalance_check_loop(
    *,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """
    4時間ごとにリバランスチェックを実行。

    - needs_rebalance == True → simulate() で提案生成 → Slack通知
    - Shadow Mode: 記録のみ
    - 自動実行は絶対にしない（提案のみ）

    Args:
        on_error: エラー発生時のコールバック

    Note:
        - このコルーチンは無限ループで動作する
        - 停止は asyncio.CancelledError で行う
        - エラー発生時もループは継続（fail-safe）
    """
    logger.info(
        "Starting rebalance check loop (interval: %ds)",
        REBALANCE_CHECK_INTERVAL_SECONDS,
    )

    while True:
        try:
            # インターバル待機
            logger.debug(
                "Waiting %ds until next rebalance check",
                REBALANCE_CHECK_INTERVAL_SECONDS,
            )
            await asyncio.sleep(REBALANCE_CHECK_INTERVAL_SECONDS)

            # リバランスチェック実行
            logger.info("Running rebalance check job")

            def _run_check() -> None:
                from app.aave.client import get_default_aave_client
                from app.aave.config import get_aave_settings
                from app.aave.rebalance_config import get_rebalance_settings
                from app.aave.rebalance_service import RebalanceService
                from app.aave.service import AaveService
                from app.aave.state_manager import get_default_state_manager
                from app.automation.state import get_monitoring_service
                from app.notifications.composite import (  # type: ignore[import-not-found]
                    CompositeNotificationService,
                )

                service = RebalanceService(
                    aave_client=get_default_aave_client(),
                    aave_service=AaveService(),
                    rebalance_settings=get_rebalance_settings(),
                    aave_settings=get_aave_settings(),
                    state_manager=get_default_state_manager(),
                    monitoring_service=get_monitoring_service(),
                )

                status = service.get_current_status()

                max_deviation = max(
                    (abs(a.deviation_pct) for a in status.current_allocations),
                    default=0,
                )

                if not status.needs_rebalance:
                    logger.info(
                        "Rebalance check: no rebalance needed (max_deviation=%.4f)",
                        float(max_deviation),
                    )
                    return

                logger.info(
                    "Rebalance check: needs_rebalance=True, max_deviation=%.4f — generating proposal",
                    float(max_deviation),
                )

                # Shadow Mode: 提案生成のみ、自動実行は絶対にしない
                proposal = service.simulate()

                logger.info(
                    "Rebalance proposal generated: proposal_id=%s, operations=%d",
                    proposal.proposal_id,
                    len(proposal.operations),
                )

                # Slack通知
                notification_service = CompositeNotificationService()
                message = (
                    f"*[Rebalance Check]* リバランスが必要です。\n"
                    f"最大乖離: {float(max_deviation):.2%}\n"
                    f"Proposal ID: `{proposal.proposal_id}`\n"
                    f"操作数: {len(proposal.operations)}\n"
                    f"※ Shadow Mode: 自動実行はしません。手動で確認してください。"
                )
                notification_service.notify(message)

            await asyncio.to_thread(_run_check)
            logger.info("Rebalance check job completed")

            # 重複実行防止のため少し待機
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("Rebalance check loop cancelled - shutting down")
            raise

        except Exception as exc:
            logger.error("Error in rebalance check loop: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as callback_exc:
                    logger.error("Error in on_error callback: %s", callback_exc)

            # エラー発生時は 10 分待機後に再試行
            await asyncio.sleep(600)
