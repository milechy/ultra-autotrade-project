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
  生 SQL INSERT を try/except でガードし、失敗時はログ + persisted=False で 200。
- Tier-S `backend/app/main.py` には `include_router(actions_router)` を
  追記しない。登録は別 PR (router 連携 PR) で行う想定。

==============================================================================
TODO(P2-onramp follow-up): backend/app/main.py への router 登録指示
==============================================================================
別 PR にて main.py に下記の **2 行** を追加すること
(Tier-S 不触ルール下では本 PR では追加しない):

  1) import 行 (既存 `from app.users.settings_router import ...` の直後に追加):

        from app.users.actions_router import router as user_actions_router

  2) Router registration ブロック (既存 `app.include_router(users_router)`
     の直後、もしくは `app.include_router(user_settings_router)` の直後に追加):

        app.include_router(
            user_actions_router, prefix="/api", tags=["user-actions"]
        )  # User Actions API (P2-onramp / P0-6)

これにより frontend からの `POST /api/users/actions` が解決される
(本 router の prefix は `/users` なので、include 側で `/api` を被せる)。
==============================================================================
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db

logger = logging.getLogger(__name__)

# 入力サイズ上限
MAX_ACTION_TYPE_LEN = 64
MAX_TARGET_TYPE_LEN = 64
MAX_TARGET_ID_LEN = 256
MAX_SESSION_ID_LEN = 128
# context_json は JSON シリアライズ後で 1 MB 上限
MAX_CONTEXT_JSON_BYTES = 1 * 1024 * 1024

# 許可する action_type (足りなくなったらここに追加。
# 任意文字列を許すと観測性ノイズの温床になるので enum で絞る)。
AllowedActionType = Literal[
    "onramp_completed",
    "onramp_cancelled",
    "tier_upgrade_click",
    "dca_setup_click",
    "exchange_connect_click",
    "feedback_submit",
    "page_view",
    "cta_click",
]

# NOTE: prefix は `/api/users` ではなく `/users` にして、main.py で
# `include_router(actions_router, prefix="/api")` できるようにしておく
# (既存 users_router は `/users` prefix を持つので並列に置く)。
router = APIRouter(prefix="/users", tags=["user-actions"])


class ActionCreatePayload(BaseModel):
    """
    user_actions 行作成リクエスト (pydantic v2)。

    - action_type: 文字列 enum (許可リスト外は 422)
    - target_type / target_id / session_id: 長さ制限つき任意文字列
    - context_json: 任意 dict, JSON 化後 1 MB 上限
    """

    action_type: AllowedActionType = Field(
        ..., description="ユーザーアクション種別 (許可リストのみ)"
    )
    target_type: Optional[str] = Field(
        default=None, max_length=MAX_TARGET_TYPE_LEN
    )
    target_id: Optional[str] = Field(
        default=None, max_length=MAX_TARGET_ID_LEN
    )
    session_id: Optional[str] = Field(
        default=None, max_length=MAX_SESSION_ID_LEN
    )
    context_json: Optional[Dict[str, Any]] = Field(
        default=None,
        description="任意の文脈情報 (JSON化後 1MB 上限)",
    )

    @field_validator("context_json")
    @classmethod
    def _validate_context_size(
        cls, v: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if v is None:
            return None
        try:
            # ensure_ascii=False で実バイト数に近づける
            encoded = json.dumps(v, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"context_json must be JSON-serializable: {exc}")
        if len(encoded) > MAX_CONTEXT_JSON_BYTES:
            raise ValueError(
                "context_json too large "
                f"({len(encoded)} > {MAX_CONTEXT_JSON_BYTES} bytes)"
            )
        return v


class ActionCreateResponse(BaseModel):
    """作成結果。"""

    ok: bool
    persisted: bool
    # persisted=True のときのみ id / created_at が入る
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    detail: Optional[str] = None


@router.post(
    "/actions",
    response_model=ActionCreateResponse,
    summary="ユーザーアクション記録 (P2-onramp / P0-6 連携)",
)
def create_user_action(
    payload: ActionCreatePayload,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ActionCreateResponse:
    """
    user_actions テーブルへ 1 行 INSERT する。

    - 認証: require_active_user (既存 JWT / Privy session 両対応)
    - 入力検証: pydantic `ActionCreatePayload` (size / enum / 1MB 上限)
    - テーブル未作成時: ログのみ残して `persisted=False` で 200 を返す
      (frontend 側は失敗してもユーザー体験を壊さない設計)
    - 永続成功時: `id`, `created_at` を返す
    """
    # action_type は enum で既に検証済み (Literal)
    if (
        payload.action_type is None
        or len(str(payload.action_type)) > MAX_ACTION_TYPE_LEN
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="action_type invalid",
        )

    context_text = (
        json.dumps(payload.context_json, ensure_ascii=False)
        if payload.context_json
        else None
    )

    # RETURNING で id / created_at を取り戻す。
    # user_actions スキーマは P0-6 で
    #   id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW()
    # を持つ想定。
    sql = text(
        """
        INSERT INTO user_actions
            (user_id, action_type, target_type, target_id, session_id,
             context_json, created_at)
        VALUES
            (:user_id, :action_type, :target_type, :target_id, :session_id,
             CAST(:context_json AS JSONB), NOW())
        RETURNING id, created_at
        """
    )

    try:
        result = db.execute(
            sql,
            {
                "user_id": current_user.id,
                "action_type": payload.action_type,
                "target_type": payload.target_type,
                "target_id": payload.target_id,
                "session_id": payload.session_id,
                "context_json": context_text,
            },
        )
        row = result.fetchone()
        db.commit()
        inserted_id: Optional[int] = None
        inserted_at: Optional[datetime] = None
        if row is not None:
            inserted_id = int(row[0]) if row[0] is not None else None
            raw_created = row[1]
            if isinstance(raw_created, datetime):
                inserted_at = raw_created
            elif raw_created is not None:
                # 文字列で返る DB ドライバ向けフォールバック
                try:
                    inserted_at = datetime.fromisoformat(str(raw_created))
                except ValueError:
                    inserted_at = datetime.now(timezone.utc)
        logger.info(
            "user_action persisted: user_id=%s action_type=%s target=%s id=%s",
            current_user.id,
            payload.action_type,
            payload.target_type,
            inserted_id,
        )
        return ActionCreateResponse(
            ok=True,
            persisted=True,
            id=inserted_id,
            created_at=inserted_at,
        )
    except Exception as e:  # noqa: BLE001 - テーブル未作成も含めて握り潰す
        # rollback してから握る (オープン tx が残ると後続クエリが死ぬ)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning(
            "user_action skipped (table missing or DB error): "
            "user_id=%s action_type=%s err=%s",
            current_user.id,
            payload.action_type,
            e,
        )
        return ActionCreateResponse(
            ok=True,
            persisted=False,
            id=None,
            created_at=None,
            detail="user_actions table not yet migrated (P0-6 pending)",
        )
