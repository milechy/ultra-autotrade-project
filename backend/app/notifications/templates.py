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


def _build_notification_message(
    title: str,
    body: str,
    severity: str,
    channel: NotificationChannel = NotificationChannel.LINE,
) -> NotificationMessage:
    """NotificationMessage を構築する。"""
    severity_map: dict[str, NotificationSeverity] = {
        "emergency": NotificationSeverity.EMERGENCY,
        "alert": NotificationSeverity.ALERT,
        "warning": NotificationSeverity.WARNING,
        "info": NotificationSeverity.INFO,
    }
    return NotificationMessage(
        channel=channel,
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


def execution_mode_downgraded_notification() -> NotificationPayload:
    """運用モードを「完全おまかせ」から「承認制」へ安全側降格したことの通知。

    受け入れ条件 A-6「権限失効時に安全側へ降格し、ユーザーに通知される」/
    A-E1「黙って承認待ちに落とさない」に対応する**ユーザー向け**通知
    (operational_alert_notification は運用者向け Slack なので別物)。

    要件定義 IV-2: 「無断で設定が変わった」と受け取られると機能不全を不信に
    変換するだけになるため、**何が起きたか・なぜか・どうすれば元に戻せるか**を
    本文に必ず含める。
    """
    title = "⚙️ 運用モードを「承認制」に変更しました"
    body = (
        "自動運用に必要な権限の設定が完了していなかったため、安全のため"
        "「承認制」に切り替えました。ご資産は影響を受けていません。"
        "今後の運用提案はアプリでご確認・承認いただくと実行されます。"
        "自動運用をご希望の場合は、設定画面から改めてお手続きください。"
    )
    return _build_payload(title, body, "warning")


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


def funding_requested_notification(
    operation: str,
    asset: str,
    required_usd: Decimal,
) -> NotificationPayload:
    """入金待ち化通知 (S2): 残高不足で承認したので「あと $X 入金してください」。"""
    op_label = _ACTION_LABEL_JA.get(operation, operation)
    title = "💰 入金待ち"
    body = (
        f"{op_label}（{asset}）の提案を入金待ちにしました。"
        f"必要額 ${required_usd} 分の USDC を Base ウォレットに入金すると署名できます。"
    )
    return _build_payload(title, body, "info")


def funding_detected_notification(
    operation: str,
    asset: str,
    required_usd: Decimal,
) -> NotificationPayload:
    """着金検知通知 (S2): 残高が必要額に到達したので署名可能になった。"""
    op_label = _ACTION_LABEL_JA.get(operation, operation)
    title = "✅ 入金を確認しました"
    body = f"{op_label}（{asset}・${required_usd}）の入金を確認しました。署名して実行できます。"
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


def expiry_reminder_notification(
    operation: str,
    asset: str,
    minutes_remaining: int,
) -> NotificationPayload:
    """期限切れ前リマインダー通知。

    Args:
        operation: "BUY" | "SELL" などの取引種別
        asset: アセット名（例: "USDC"）
        minutes_remaining: 期限まで残り分数
    """
    title = "⏳ 提案の期限が近づいています"
    body = (
        f"{operation} {asset} の提案が約 {minutes_remaining} 分後に期限切れになります。"
        "アプリで確認・承認してください。"
    )
    return _build_payload(title, body, "warning")


# --- LINE Push 能動的通知 5種 (GID 1215698091517000) ---


def health_factor_warning(hf: Decimal) -> NotificationPayload:
    """HF 警告通知（HF < 1.8 レベル）。

    配線先: backend/app/aave/monitor._notify_hf_warning() — HF<1.8 のとき自動呼び出し済み。

    Args:
        hf: 現在の Health Factor 値。

    Returns:
        NotificationPayload (severity=warning)
    """
    title = "⚠️ Health Factor 警告"
    body = (
        f"Health Factor が {hf:.3f} に低下しました。"
        "ポジションの確認を推奨します（警戒閾値: 1.800）。"
    )
    return _build_payload(title, body, "warning")


def trade_executed(action: str, amount: Decimal, token: str) -> NotificationPayload:
    """取引実行完了の能動的通知。

    配線先（未配線・フォローアップ）: 取引実行フロー（automation/workflow.py など）
    への配線は、取引実行 PR 着地時に別 PR で行う。

    Args:
        action: "BUY" | "SELL" などの取引種別
        amount: 取引金額 (Decimal)
        token: アセット名（例: "USDC"）

    Returns:
        NotificationPayload (severity=info)
    """
    op_label = _ACTION_LABEL_JA.get(action, action)
    title = "✅ 取引実行"
    body = f"{op_label} {amount} {token} を実行しました。"
    return _build_payload(title, body, "info")


def morpho_apy_alert(apy: Decimal) -> NotificationPayload:
    """Morpho APY アラート通知。

    配線先（未配線・フォローアップ）: W4-1 Morpho APY モニタリングフック着地時に配線。

    Args:
        apy: 現在の APY（例: Decimal("5.2") = 5.2%）

    Returns:
        NotificationPayload (severity=info)
    """
    title = "📈 Morpho APY 変動"
    body = f"Morpho の APY が {apy:.2f}% になりました。ポートフォリオを確認してください。"
    return _build_payload(title, body, "info")


def monthly_report(metrics: dict[str, Decimal | str | int]) -> NotificationPayload:
    """月次レポート通知（Flex Message 用ペイロード生成）。

    配線先（未配線・フォローアップ）: scheduled_tasks.py の月次 job（Tier S）への
    配線は別 PR で人間承認後に実施。

    Args:
        metrics: レポート指標 dict。期待キー:
            - period: str          対象月（例: "2026年6月"）
            - net_profit: Decimal  純損益 JPY（int/float も Decimal に自動変換）
            - fee_amount: Decimal  手数料合計 JPY（同上）
            - win_rate: Decimal    勝率 0〜100（同上）
            - total_trades: int    取引回数

    Returns:
        NotificationPayload (severity=info)
    """
    period = str(metrics.get("period", "---"))
    # int / float / str で来ても Decimal に変換してから整形（TypeError 防止）
    net_profit = Decimal(str(metrics.get("net_profit", 0)))
    fee_amount = Decimal(str(metrics.get("fee_amount", 0)))
    win_rate = Decimal(str(metrics.get("win_rate", 0)))
    total_trades = int(metrics.get("total_trades", 0))

    profit_sign = "+" if net_profit >= 0 else ""
    title = f"📊 月次レポート {period}"
    body = (
        f"純損益: {profit_sign}{net_profit} JPY\n"
        f"手数料: {fee_amount} JPY\n"
        f"勝率: {win_rate:.1f}% ({total_trades}回)"
    )
    return _build_payload(title, body, "info")


# --- 運営向けアラート ---


def operational_alert_notification(title: str, body: str) -> NotificationMessage:
    """運営(Slack)向け運用アラート通知。

    ユーザー向け通知ではないため NotificationMessage.user_id は設定しない
    （呼び出し側で必要なら user_id を text で body に含める）。

    配線先: automation/ai_judgment_scheduler.py の不変条件検査・連続期限切れ検知、
    proposals/auto_execute.py の委譲枠欠如・実行スキップ通知。
    """
    return _build_notification_message(title, body, "alert", channel=NotificationChannel.SLACK)


def oracle_alert(deviation_pct: Decimal) -> NotificationPayload:
    """オラクル価格乖離アラート通知。

    配線先（未配線・フォローアップ）: W1-1 オラクル監視フック着地時に配線。

    Args:
        deviation_pct: 価格乖離率 (例: Decimal("3.5") = 3.5%)

    Returns:
        NotificationPayload (severity=alert)
    """
    title = "🔔 オラクル価格乖離検知"
    body = (
        f"オラクル価格に {deviation_pct:.1f}% の乖離が検知されました。"
        "自動取引が一時停止される可能性があります。"
    )
    return _build_payload(title, body, "alert")
