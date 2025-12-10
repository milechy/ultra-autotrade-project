# backend/app/automation/emergency_report_service.py
from __future__ import annotations

from datetime import datetime
from typing import List, Sequence

from pydantic import BaseModel, Field

from .schemas import AutomationReportSummary, MonitoringEvent, AlertLevel


class EmergencyReport(BaseModel):
    """
    緊急時に人間向けに提示するレポート。

    通知（LINE/Slack）の本文や、後続フェーズで Notion に保存する
    レポートテキストとして再利用できるよう、シンプルな構造にしている。
    """

    title: str = Field(..., description="レポートタイトル")
    body: str = Field(..., description="本文（プレーンテキスト）")


class EmergencyReportService:
    """
    AutomationReportSummary と MonitoringEvent の一覧から、
    緊急時の状況説明レポートを生成するサービス。
    """

    @staticmethod
    def _derive_severity_label(summary: AutomationReportSummary) -> str:
        # emergency > alert/critical > warning > info の順で判定
        if getattr(summary, "emergency_occurred", False) or getattr(summary, "emergency_count", 0) > 0:
            return "EMERGENCY"
        if getattr(summary, "alert_count", 0) > 0 or getattr(summary, "critical_count", 0) > 0:
            return "ALERT"
        if getattr(summary, "warning_count", 0) > 0:
            return "WARNING"
        return "INFO"

    @staticmethod
    def _format_period(summary: AutomationReportSummary) -> str:
        period = getattr(summary, "period", None)
        period_label = getattr(period, "value", str(period)) if period is not None else "unknown"

        from_ts: datetime = getattr(summary, "from_timestamp")
        to_ts: datetime = getattr(summary, "to_timestamp")

        return f"{period_label} {from_ts.isoformat()} – {to_ts.isoformat()}"

    @staticmethod
    def _select_notable_events(
        events: Sequence[MonitoringEvent],
        max_events: int,
    ) -> List[MonitoringEvent]:
        """
        重要度の高いイベントを優先して最大 max_events 件まで抽出する。
        """
        if not events:
            return []

        # EMERGENCY / CRITICAL / ALERT / WARNING / INFO の優先度
        level_priority = {
            AlertLevel.EMERGENCY: 4,
            AlertLevel.CRITICAL: 3,
            AlertLevel.ALERT: 2,
            AlertLevel.WARNING: 1,
            AlertLevel.INFO: 0,
        }

        sorted_events = sorted(
            events,
            key=lambda e: (level_priority.get(e.level, 0), e.timestamp),
            reverse=True,
        )

        return list(sorted_events[:max_events])

    def build_emergency_report(
        self,
        summary: AutomationReportSummary,
        events: Sequence[MonitoringEvent],
        *,
        max_events: int = 20,
    ) -> EmergencyReport:
        """
        サマリとイベント一覧から緊急時レポートを生成する。
        """
        severity_label = self._derive_severity_label(summary)
        period_str = self._format_period(summary)

        title = f"[{severity_label}] Automation emergency report ({period_str})"

        lines: List[str] = []
        lines.append(f"Severity: {severity_label}")
        lines.append(f"Period: {period_str}")

        # イベント件数の概要
        lines.append(
            "Event counts: "
            f"total={summary.total_events}, "
            f"info={summary.info_count}, "
            f"warning={summary.warning_count}, "
            f"alert={summary.alert_count}, "
            f"critical={summary.critical_count}, "
            f"emergency={summary.emergency_count}"
        )

        # ヘルスファクターの情報
        min_hf = getattr(summary, "min_health_factor", None)
        max_hf = getattr(summary, "max_health_factor", None)
        last_hf = getattr(summary, "last_health_factor", None)
        if any(v is not None for v in (min_hf, max_hf, last_hf)):
            lines.append(
                "Health factor: "
                f"min={min_hf}, max={max_hf}, last={last_hf}"
            )

        # 重要なイベント一覧
        notable_events = self._select_notable_events(events, max_events=max_events)
        if notable_events:
            lines.append("")
            lines.append("Recent notable events:")
            for ev in notable_events:
                lines.append(
                    f"- [{ev.level}] {ev.timestamp.isoformat()} "
                    f"{ev.component}: {ev.code} - {ev.message}"
                )
        else:
            lines.append("")
            lines.append("Recent notable events: (none)")

        # notes があれば末尾に追記
        notes = getattr(summary, "notes", None)
        if notes:
            lines.append("")
            lines.append("Notes:")
            lines.append(notes)

        body = "\n".join(lines)
        return EmergencyReport(title=title, body=body)
