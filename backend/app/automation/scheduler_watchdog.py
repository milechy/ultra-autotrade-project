# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/automation/scheduler_watchdog.py
"""スケジューラー Watchdog — overdue 検知と Slack 通知。

AI 判定スケジューラーの最後の正常実行時刻を 30 分ごとに確認し、
期待間隔（AI_JUDGMENT_INTERVAL_HOURS）の 2 倍を超えて実行されていなければ
Slack Webhook に警告を送信する。

設計方針:
- compute_scheduler_health() は pure function（テスト容易性）
- watchdog loop はスケジューラーループと独立したタイマー
- Slack 通知は check_interval ごとに最大 1 回（スパム防止）
- 通知自体の失敗でループが落ちないよう try-except で保護
"""

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.automation.ai_judgment_scheduler import get_scheduler_status

logger = logging.getLogger(__name__)

_DEFAULT_CHECK_INTERVAL_SECONDS = 1800  # 30 分


def compute_scheduler_health(
    last_run_iso: Optional[str],
    interval_hours: int,
) -> "dict[str, Any]":
    """スケジューラーの健全性を計算する（pure function）。

    Args:
        last_run_iso: get_scheduler_status() の "last_run" 値（ISO 8601 文字列 or None）。
        interval_hours: AI_JUDGMENT_INTERVAL_HOURS の値。

    Returns:
        {
            "healthy": bool,
            "overdue_hours": float | None,  # overdue の場合のみ
            "reason": str | None,
        }
    """
    if last_run_iso is None:
        # スケジューラーがまだ一度も正常実行されていない（起動直後等）— 楽観的に healthy
        return {"healthy": True, "overdue_hours": None, "reason": None}

    try:
        last_run = datetime.fromisoformat(last_run_iso)
    except ValueError:
        return {"healthy": True, "overdue_hours": None, "reason": None}

    age_hours = (datetime.now(timezone.utc) - last_run).total_seconds() / 3600
    threshold_hours = float(interval_hours * 2)

    if age_hours > threshold_hours:
        reason = (
            f"最後の正常実行から {age_hours:.1f} 時間経過"
            f"（期待間隔 {interval_hours}h × 2 = {threshold_hours:.0f}h を超過）"
        )
        return {
            "healthy": False,
            "overdue_hours": round(age_hours, 1),
            "reason": reason,
        }

    return {"healthy": True, "overdue_hours": None, "reason": None}


def _send_watchdog_slack(text: str) -> None:
    """Slack Webhook に watchdog 警告を送信する（失敗しても例外を投げない）。"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        data = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)  # noqa: S310
    except Exception as exc:
        logger.error("Watchdog Slack notification failed: %s", exc)


async def scheduler_watchdog_loop(
    check_interval_seconds: int = _DEFAULT_CHECK_INTERVAL_SECONDS,
    on_overdue: Optional[Callable[[str], None]] = None,
) -> None:
    """30 分ごとに AI 判定スケジューラーの健全性を確認するループ。

    Args:
        check_interval_seconds: チェック間隔（秒）。デフォルト 1800（30 分）。
        on_overdue: overdue 検知時に呼ぶ同期コールバック（テスト用）。
    """
    last_notified: Optional[datetime] = None

    while True:
        await asyncio.sleep(check_interval_seconds)
        try:
            status = get_scheduler_status()

            # スケジューラー自体が無効設定の場合はチェックをスキップ
            if not status.get("running"):
                continue

            interval_hours = int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS", "4"))
            health = compute_scheduler_health(status.get("last_run"), interval_hours)

            if not health["healthy"]:
                now = datetime.now(timezone.utc)
                # Slack スパム防止: 通知クールダウンはチェック間隔と同じ
                if (
                    last_notified is None
                    or (now - last_notified).total_seconds() >= check_interval_seconds
                ):
                    overdue_h = health.get("overdue_hours", "?")
                    last_run_str = status.get("last_run") or "不明"
                    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                    msg = (
                        f"⚠️ [Watchdog] AI判定スケジューラーが {overdue_h}時間以上実行されていません。\n"
                        f"最後の正常実行: {last_run_str}\n"
                        f"時刻: {ts}"
                    )
                    logger.warning("Scheduler overdue detected: %s", health["reason"])
                    _send_watchdog_slack(msg)
                    last_notified = now
                    if on_overdue:
                        try:
                            on_overdue(msg)
                        except Exception as cb_exc:
                            logger.error("on_overdue callback failed: %s", cb_exc)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Scheduler watchdog check failed: %s", exc)
