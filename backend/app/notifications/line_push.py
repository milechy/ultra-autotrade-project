# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/line_push.py
"""LINE Messaging API Push 送信ユーティリティ関数。

既存 LINEFlexMessageSender / LINENotificationSender を薄くラップし、
環境変数ベースで手軽に呼び出せる push_text / push_flex を提供する。

環境変数:
    LINE_CHANNEL_ACCESS_TOKEN : LINE Messaging API チャンネルアクセストークン
    LINE_USER_ID              : 送信先ユーザーの LINE user_id (U xxxxxxxx...)

セキュリティ:
    トークンはログ出力禁止（CLAUDE.md Security Rule #8 準拠）。
    失敗時は例外を投げず False を返す（fail-open 設計）。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _get_line_credentials() -> tuple[str, str]:
    """env からチャンネルアクセストークンとユーザー ID を返す。

    Returns:
        (channel_access_token, user_id) のタプル。未設定の場合は空文字列を返す。
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    user_id = os.getenv("LINE_USER_ID", "")
    return token, user_id


def push_text(user_line_id: str, message: str) -> bool:
    """指定 user_line_id に LINE テキストメッセージを送信する。

    Args:
        user_line_id: 送信先の LINE user_id （"U" で始まる文字列）。
                      空文字の場合は環境変数 LINE_USER_ID をフォールバックとして使用する。
        message: 送信するテキスト。

    Returns:
        送信成功なら True、失敗/設定欠如なら False。
    """
    from .line_messaging import LINEFlexMessageSender  # noqa: PLC0415

    token, env_user_id = _get_line_credentials()
    target = user_line_id or env_user_id

    if not token or not target:
        logger.warning(
            "[line_push] LINE_CHANNEL_ACCESS_TOKEN または LINE_USER_ID が未設定。送信スキップ。"
        )
        return False

    # マスクログ（トークン先頭6 + 末尾4のみ）
    masked = token[:6] + "****" + token[-4:] if len(token) > 10 else "****"
    logger.debug("[line_push] push_text: target=%s..., token=%s", target[:8], masked)

    sender = LINEFlexMessageSender(
        channel_access_token=token,
        user_id=target,
    )
    return sender.send_text(message)


def push_flex(user_line_id: str, flex_content: dict[str, Any]) -> bool:
    """指定 user_line_id に LINE Flex Message を送信する。

    Args:
        user_line_id: 送信先の LINE user_id。
                      空文字の場合は環境変数 LINE_USER_ID をフォールバックとして使用する。
        flex_content: LINE Flex Message の dict（build_*_flex_bubble の戻り値）。

    Returns:
        送信成功なら True、失敗/設定欠如なら False。
    """
    from .line_messaging import LINEFlexMessageSender  # noqa: PLC0415

    token, env_user_id = _get_line_credentials()
    target = user_line_id or env_user_id

    if not token or not target:
        logger.warning(
            "[line_push] LINE_CHANNEL_ACCESS_TOKEN または LINE_USER_ID が未設定。送信スキップ。"
        )
        return False

    sender = LINEFlexMessageSender(
        channel_access_token=token,
        user_id=target,
    )
    return sender.push_flex_message(flex_content)
