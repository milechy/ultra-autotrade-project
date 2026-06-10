# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/dependencies.py
"""
認証依存性注入。

FastAPI の Depends で使用する認証関連の依存関数。
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db

from .models import User, UserRole
from .service import AuthService

# Bearer トークン認証スキーム
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    query_token: Optional[str] = Query(None, alias="token", include_in_schema=False),
) -> User:
    """
    現在のユーザーを取得する。

    Authorization: Bearer ヘッダーを優先し、なければ ?token= クエリパラメータを
    フォールバックとして受け付ける（ファイルダウンロード用）。

    Args:
        credentials: Bearer トークン (Authorization ヘッダー)
        db: データベースセッション
        query_token: ?token= クエリパラメータ (ファイルDL時フォールバック)

    Returns:
        認証済みユーザー

    Raises:
        HTTPException: 認証失敗時
    """
    if credentials is not None:
        raw_token = credentials.credentials
    elif query_token is not None:
        raw_token = query_token
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = AuthService.decode_token(raw_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = AuthService.get_user_by_id(db, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    現在のユーザーを取得する（任意）。

    認証されていない場合は None を返す。
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def require_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """
    アクティブなユーザーを要求する。

    Args:
        user: 認証済みユーザー

    Returns:
        アクティブなユーザー

    Raises:
        HTTPException: ユーザーが非アクティブな場合
    """
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    return user


async def require_admin(
    user: User = Depends(require_active_user),
) -> User:
    """
    管理者権限を要求する。

    Args:
        user: アクティブなユーザー

    Returns:
        管理者ユーザー

    Raises:
        HTTPException: ユーザーが管理者でない場合
    """
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_editor(
    user: User = Depends(require_active_user),
) -> User:
    """
    Editor 以上（Editor または Admin）を要求する。

    Args:
        user: アクティブなユーザー

    Returns:
        Editor 以上のユーザー

    Raises:
        HTTPException: ユーザーが Editor 以上でない場合
    """
    if user.role not in (UserRole.ADMIN.value, UserRole.EDITOR.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editor access required",
        )
    return user


async def require_partner(
    user: User = Depends(require_active_user),
) -> User:
    """
    Partner 以上（Partner または Admin）を要求する。

    Args:
        user: アクティブなユーザー

    Returns:
        Partner 以上のユーザー

    Raises:
        HTTPException: ユーザーが Partner 以上でない場合
    """
    if user.role not in (UserRole.ADMIN.value, UserRole.PARTNER.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Partner access required",
        )
    return user


async def require_viewer(
    user: User = Depends(require_active_user),
) -> User:
    """
    Viewer 以上（全ロール）を要求する。

    require_active_user で認証済み = Viewer 以上。

    Args:
        user: アクティブなユーザー

    Returns:
        認証済みユーザー
    """
    return user


def verify_internal_token(
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """内部スケジューラー用APIキー認証。INTERNAL_API_TOKEN 環境変数と照合する。"""
    import os  # noqa: PLC0415

    token = os.getenv("INTERNAL_API_TOKEN", "")
    if not token or x_internal_token != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid X-Internal-Token header required",
        )
