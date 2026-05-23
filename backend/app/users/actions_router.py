# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/actions_router.py
"""
user_actions API エンドポイント (P2-onramp 連携)。

frontend (Privy useFundWallet 完了など) からのユーザーアクションを
`user_actions` テーブルへ INSERT する雛形 router。

備考:
- `user_actions` テーブル本体は P0-6 PR で migration 追加予定。
- 本 PR の段階ではテーブル未作成でもエラーで UX を壊さないよう、
  生 SQL INSERT を try/except でガードし、失敗時はログのみ残す。
- Tier-S `backend/app/main.py` には `include_router(actions_router)` を
  追記しない。登録は別 PR (router 連携 PR) で行う想定 → 下記 TODO 参照。
"""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db

logger = logging.getLogger(__name__)

# NOTE: prefix は `/api/users` ではなく `/users` にして、main.py で
# `include_router(actions_router, prefix="/api")` できるようにしておく
# (既存 users_router は `/users` prefix を持つので並列に置く)。
# TODO(P2-onramp follow-up): main.py 側で
#   `app.include_router(user_actions_router, prefix="/api")` を追加する
#   フォローアップ PR を起票する。本 PR では Tier-S 不触のため未登録。
router = APIRouter(prefix="/users", tags=["user-actions"])


class UserActionRequest(BaseModel):
    """user_actions 行作成リクエスト。"""

    action_type: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    session_id: Optional[str] = None
    context_json: Optional[Dict[str, Any]] = None


class UserActionResponse(BaseModel):
    """作成結果。"""

    ok: bool
    persisted: bool
    detail: Optional[str] = None


@router.post(
    "/actions",
    response_model=UserActionResponse,
    summary="ユーザーアクション記録 (P2-onramp / P0-6 連携)",
)
def create_user_action(
    request: UserActionRequest,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> UserActionResponse:
    """
    user_actions テーブルへ 1 行 INSERT する。

    - 認証: require_active_user (既存 JWT / Privy session 両対応)
    - テーブル未作成時: ログのみ残して `persisted=False` で 200 を返す
      (frontend 側は失敗してもユーザー体験を壊さない設計)
    """
    context_text = json.dumps(request.context_json) if request.context_json else None

    sql = text(
        """
        INSERT INTO user_actions
            (user_id, action_type, target_type, target_id, session_id, context_json, created_at)
        VALUES
            (:user_id, :action_type, :target_type, :target_id, :session_id,
             CAST(:context_json AS JSONB), NOW())
        """
    )

    try:
        db.execute(
            sql,
            {
                "user_id": current_user.id,
                "action_type": request.action_type,
                "target_type": request.target_type,
                "target_id": request.target_id,
                "session_id": request.session_id,
                "context_json": context_text,
            },
        )
        db.commit()
        logger.info(
            "user_action persisted: user_id=%s action_type=%s target=%s",
            current_user.id,
            request.action_type,
            request.target_type,
        )
        return UserActionResponse(ok=True, persisted=True)
    except Exception as e:  # noqa: BLE001 - テーブル未作成も含めて握り潰す
        # rollback してから握る (オープン tx が残ると後続クエリが死ぬ)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning(
            "user_action skipped (table missing or DB error): user_id=%s action_type=%s err=%s",
            current_user.id,
            request.action_type,
            e,
        )
        return UserActionResponse(
            ok=True,
            persisted=False,
            detail="user_actions table not yet migrated (P0-6 pending)",
        )
