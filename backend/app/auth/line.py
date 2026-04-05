# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/line.py
"""LINE LIFF認証サービス。

LINE idTokenを検証してユーザーを取得または作成する。
"""

import datetime
import logging
import os
import secrets
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from .models import User, UserRole

logger = logging.getLogger(__name__)

LINE_TOKEN_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"  # noqa: S105


class LineAuthError(Exception):
    """LINE認証エラー。"""


async def verify_line_id_token(id_token: str) -> dict[str, Any]:
    """
    LINE idTokenをLINE APIで検証する。

    Returns:
        dict: {"sub": line_user_id, "name": display_name, ...}
    Raises:
        LineAuthError: 検証失敗時
    """
    liff_id = os.getenv("NEXT_PUBLIC_LIFF_ID") or os.getenv("LIFF_ID")
    if not liff_id:
        raise LineAuthError("LIFF_ID環境変数が設定されていません")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            LINE_TOKEN_VERIFY_URL,
            data={"id_token": id_token, "client_id": liff_id},
        )

    if response.status_code != 200:
        logger.warning("LINE token verify failed: status=%d", response.status_code)
        raise LineAuthError("LINE idTokenの検証に失敗しました")

    payload = response.json()
    if "sub" not in payload:
        raise LineAuthError("LINE idTokenのペイロードが不正です")

    return payload  # type: ignore[no-any-return]


def get_or_create_line_user(db: Session, line_user_id: str, display_name: str) -> User:
    """
    LINE user_idでユーザーを取得または新規作成する。

    LINE userIdをemailの代替として使用（line_<userId>@line.local）。
    """
    # LINE ユーザー識別用の疑似メールアドレス
    pseudo_email = f"line_{line_user_id}@line.local"

    user: Optional[User] = db.query(User).filter(User.email == pseudo_email).first()
    if user is not None:
        return user

    # 新規ユーザー作成（パスワードなし — ランダムハッシュでログイン不可化）
    user = User(
        email=pseudo_email,
        username=f"line_{line_user_id[:8]}",  # 先頭8文字
        hashed_password=secrets.token_hex(32),  # ランダム（ログイン不可パスワード）
        role=UserRole.VIEWER.value,
        is_active=True,
        terms_version="2.0",
        terms_accepted_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created new LINE user: user_id=%d", user.id)
    return user
