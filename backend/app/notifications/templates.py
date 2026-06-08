# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/templates.py
"""通知テンプレート定義（7種）。LINE Flex Message + Web Push 両形式。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .schemas import NotificationChannel, NotificationMessage, NotificationSeverity

# action 文字列 → ユーザー向け日本語ラベル
_ACTION_LABEL_JA: dict[str, str] = {
    "BUY": "購入する",
    "SELL": "売る",
}

# severity 文字列 → LINE Flex ヘッダー色
_SEVERITY_COLOR: dict[str, str] = {
    "emergency": "#FF0000",
    "alert": "#FF6B00",
    "warning": "#FFA500",
    "info": "#00B900",
}


@dataclass
class NotificationPayload:
    """通知ペイロード（LINE Flex + Web Push 両形式を保持）。"""

    title: str
    body: str
    severity: str  # "emergency" | "alert" | "warning" | "info"
    notification_message: NotificationMessage  # ロギング用
    web_push_payload: dict[str, Any]  # Web Push 用ペイロード
    line_flex_color: str  # LINE Flex ヘッダー背景色 (#RRGGBB)


def _build_web_push_payload(title: str, body: str, severity: str) -> dict[str, Any]:
    """Web Push ペイロードを構築する。"""
    return {
        "title": title,
        "body": body,
        "icon": "/icon-192.png",
        "badge": "/badge.png",
        "tag": f"ultra-{severity}-{int(time.time())}",
        "requireInteraction": severity in ("emergency", "alert"),
    }


def _build_notification_message(title: str, body: str, severity: str) -> NotificationMessage:
    """NotificationMessage を構築する。"""
    severity_map: dict[str, NotificationSeverity] = {
        "emergency": NotificationSeverity.EMERGENCY,
        "alert": NotificationSeverity.ALERT,
        "warning": NotificationSeverity.WARNING,
        "info": NotificationSeverity.INFO,
    }
    return NotificationMessage(
        channel=NotificationChannel.LINE,
        severity=severity_map.get(severity, NotificationSeverity.INFO),
        title=title,
        body=body,
    )


def _build_payload(title: str, body: str, severity: str) -> NotificationPayload:
    """NotificationPayload を構築するヘルパー。"""
    color = _SEVERITY_COLOR.get(severity, "#00B900")
    return NotificationPayload(
        title=title,
        body=body,
        severity=severity,
        notification_message=_build_notification_message(title, body, severity),
        web_push_payload=_build_web_push_payload(title, body, severity),
        line_flex_color=color,
    )


# --- 緊急3種 ---


def hf_danger_alert(
    hf: Decimal,
    threshold: Decimal = Decimal("1.3"),
) -> NotificationPayload:
    """HF危険アラート（HF < 1.3）。"""
    title = "⚠️ Health Factor 危険域"
    body = (
        f"Health Factor が {hf:.3f} に低下しました"
        f"（危険閾値: {threshold}）。即座に対応してください。"
    )
    return _build_payload(title, body, "emergency")


def emergency_stop_notification(reason: str) -> NotificationPayload:
    """緊急停止通知。"""
    title = "🆘 緊急停止実行"
    body = f"緊急停止が実行されました。理由: {reason}"
    return _build_payload(title, body, "emergency")


def auto_safety_action_notification(
    operation: str,
    asset: str,
    amount: Decimal,
    apy: Decimal,
) -> NotificationPayload:
    """自動安全操作実行通知。

    Args:
        operation: "SUPPLY" | "WITHDRAW"
        asset: アセット名（例: "USDC"）
        amount: 操作金額（Decimal）
        apy: 現在の APY（Decimal）
    """
    action_label = "供給" if operation == "SUPPLY" else "引き出し"
    title = "🤖 自動安全操作実行"
    body = f"AIが {amount} {asset} を{action_label}しました。APY: {apy:.2f}%"
    return _build_payload(title, body, "alert")


# --- 取引4種 ---


def ai_proposal_notification(
    operation: str,
    asset: str,
    amount: Decimal,
    confidence: int,
) -> NotificationPayload:
    """AI取引提案通知。"""
    op_label = _ACTION_LABEL_JA.get(operation, operation)
    title = "💡 新しいAI取引提案"
    body = f"{op_label} {amount} {asset}（信頼度: {confidence}%）。アプリで確認・承認してください。"
    return _build_payload(title, body, "warning")


def trade_executed_notification(
    operation: str,
    asset: str,
    amount: Decimal,
    tx_hash: str,
) -> NotificationPayload:
    """取引実行完了通知。"""
    op_label = _ACTION_LABEL_JA.get(operation, operation)
    title = "✅ 取引実行完了"
    body = f"{op_label} {amount} {asset} が完了しました。Tx: {tx_hash[:10]}..."
    return _build_payload(title, body, "info")


def trade_failed_notification(
    operation: str,
    asset: str,
    amount: Decimal,
    error: str,
) -> NotificationPayload:
    """取引失敗通知。"""
    op_label = _ACTION_LABEL_JA.get(operation, operation)
    title = "❌ 取引失敗"
    body = f"{op_label} {amount} {asset} が失敗しました。エラー: {error[:100]}"
    return _build_payload(title, body, "alert")


def approval_timeout_notification(
    operation: str,
    asset: str,
    timeout_minutes: int = 60,
) -> NotificationPayload:
    """承認タイムアウト通知。"""
    op_label = _ACTION_LABEL_JA.get(operation, operation)
    title = "⏰ 承認タイムアウト"
    body = f"{op_label} {asset} の提案が {timeout_minutes} 分以内に承認されず、キャンセルしました。"
    return _build_payload(title, body, "info")
