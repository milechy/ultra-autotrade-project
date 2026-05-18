# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Twilio REST API を使った音声電話 / SMS 通知送信実装。

オンコール時間帯 (JST 9:00-22:00): 音声電話 → 失敗時 SMS フォールバック
オンコール時間外             : SMS のみ（best-effort）

環境変数:
    TWILIO_ACCOUNT_SID   : Twilio Account SID (AC...)
    TWILIO_AUTH_TOKEN    : Twilio Auth Token（ログ出力厳禁）
    TWILIO_FROM_NUMBER   : 発信元電話番号 (+1...)
    TWILIO_ONCALL_PHONE  : 着信先（オンコール担当者）電話番号 (+81...)
    ONCALL_START_HOUR    : オンコール開始時刻 JST (デフォルト: 9)
    ONCALL_END_HOUR      : オンコール終了時刻 JST (デフォルト: 22)
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from .schemas import NotificationMessage, NotificationSeverity

logger = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

# 音声通話用 TwiML テンプレート（Twilio が読み上げる文言）
_TWIML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="ja-JP" voice="Polly.Mizuki">
    {message}
    {message}
  </Say>
</Response>"""


class TwilioSender:
    """Twilio REST API 経由で音声電話または SMS を送信する Sender。

    - オンコール時間内 (ONCALL_START_HOUR〜ONCALL_END_HOUR JST): 音声電話 → SMS フォールバック
    - オンコール時間外: SMS のみ（best-effort）
    - 送信失敗時は例外を投げない（fail-open、ログのみ）
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_number: str,
        oncall_start_hour: int = 9,
        oncall_end_hour: int = 22,
        timeout_seconds: int = 15,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._to_number = to_number
        self._oncall_start_hour = oncall_start_hour
        self._oncall_end_hour = oncall_end_hour
        self._timeout = timeout_seconds
        # Basic 認証ヘッダー（SID + Token をログに出さない）
        credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        self._auth_header = f"Basic {credentials}"

    def _is_oncall_hours(self) -> bool:
        """現在時刻が JST オンコール時間帯内か判定する。"""
        now_jst = datetime.now(timezone.utc).astimezone(JST)
        return self._oncall_start_hour <= now_jst.hour < self._oncall_end_hour

    def send(self, message: NotificationMessage) -> None:
        """通知を送信する。EMERGENCY のみ電話/SMS 対象。それ以外はログのみ。"""
        if message.severity not in (
            NotificationSeverity.EMERGENCY,
            NotificationSeverity.ALERT,
        ):
            logger.debug(
                "TwilioSender: severity=%s は電話エスカレーション対象外。スキップ。",
                message.severity.value,
            )
            return

        text = f"{message.title}: {message.body}"

        if self._is_oncall_hours():
            # 音声電話試行 → 失敗時 SMS フォールバック
            if not self._make_call(text):
                logger.warning("TwilioSender: 音声電話失敗。SMS にフォールバック。")
                self._send_sms(text)
        else:
            # 時間外は SMS のみ
            logger.info(
                "TwilioSender: オンコール時間外 (JST %d:00-%d:00)。SMS のみ送信。",
                self._oncall_start_hour,
                self._oncall_end_hour,
            )
            self._send_sms(text)

    def _make_call(self, text: str) -> bool:
        """Twilio Voice API で音声電話を発信する。成功時 True を返す。"""
        twiml = _TWIML_TEMPLATE.format(message=_escape_xml(text[:200]))
        url = f"{TWILIO_API_BASE}/Accounts/{self._account_sid}/Calls.json"
        try:
            response = httpx.post(
                url,
                data={
                    "To": self._to_number,
                    "From": self._from_number,
                    "Twiml": twiml,
                },
                headers={"Authorization": self._auth_header},
                timeout=self._timeout,
            )
            response.raise_for_status()
            call_sid = response.json().get("sid", "unknown")
            logger.info("TwilioSender: 音声電話発信成功 sid=%s", call_sid[:8] + "...")
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "TwilioSender: 音声電話 HTTP エラー status=%d",
                exc.response.status_code,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("TwilioSender: 音声電話失敗 error=%s", type(exc).__name__)
        return False

    def _send_sms(self, text: str) -> bool:
        """Twilio Messaging API で SMS を送信する。成功時 True を返す。"""
        url = f"{TWILIO_API_BASE}/Accounts/{self._account_sid}/Messages.json"
        sms_body = text[:160]  # SMS 1 通上限
        try:
            response = httpx.post(
                url,
                data={
                    "To": self._to_number,
                    "From": self._from_number,
                    "Body": sms_body,
                },
                headers={"Authorization": self._auth_header},
                timeout=self._timeout,
            )
            response.raise_for_status()
            msg_sid = response.json().get("sid", "unknown")
            logger.info("TwilioSender: SMS 送信成功 sid=%s", msg_sid[:8] + "...")
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "TwilioSender: SMS HTTP エラー status=%d",
                exc.response.status_code,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("TwilioSender: SMS 送信失敗 error=%s", type(exc).__name__)
        return False


def _escape_xml(text: str) -> str:
    """TwiML に埋め込む文字列の XML 特殊文字をエスケープする。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
