# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Reports Router — GET /api/reports/monthly

月次レポートを PDF (reportlab 利用可) または CSV でダウンロードする。
- Admin: 全ユーザー集計、または ?user_id= で特定ユーザーの集計を取得可能。
- Viewer (一般ユーザー): 自分のデータのみ取得可能。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User, UserRole
from app.database import get_db

from .monthly_report import build_monthly_report_data, generate_monthly_report_pdf

router = APIRouter(tags=["reports"])


@router.get("/monthly")
def download_monthly_report(
    year: int | None = None,
    month: int | None = None,
    user_id: int | None = None,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """月次レポートをダウンロードする。

    Query params:
        year:    対象年 (デフォルト: 今月)
        month:   対象月 (デフォルト: 今月)
        user_id: Admin のみ有効。指定ユーザーのレポートを取得。
                 省略時は Admin なら全ユーザー集計、Viewer なら自分のみ。

    Auth:
        Bearer トークン必須 (全ロール)。
        Viewer が他ユーザーの user_id を指定すると 403。
    """
    now = datetime.now(timezone.utc)
    target_year = year if year is not None else now.year
    target_month = month if month is not None else now.month

    is_admin = current_user.role == UserRole.ADMIN.value

    if is_admin:
        # Admin: user_id 指定があればそのユーザー、なければ全ユーザー集計
        target_user_id = user_id
    else:
        # Viewer 系: 他ユーザーへのアクセスを拒否
        if user_id is not None and user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="他のユーザーのレポートにはアクセスできません。",
            )
        target_user_id = current_user.id

    data = build_monthly_report_data(db, target_year, target_month, target_user_id)
    content, content_type = generate_monthly_report_pdf(data)

    ext = "pdf" if content_type == "application/pdf" else "csv"
    filename = f"monthly_report_{target_year}_{target_month:02d}.{ext}"

    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
