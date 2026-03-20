"""Reports Router — GET /api/reports/monthly

月次レポートを PDF (reportlab 利用可) または CSV でダウンロードする。
Admin または Editor ロールのみアクセス可。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth.dependencies import require_editor
from app.auth.models import User

from .monthly_report import MonthlyReportData, generate_monthly_report_pdf

router = APIRouter(tags=["reports"])


@router.get("/monthly")
def download_monthly_report(
    year: int | None = None,
    month: int | None = None,
    _user: User = Depends(require_editor),
) -> StreamingResponse:
    """月次レポートをダウンロードする。

    Query params:
        year:  対象年 (デフォルト: 今月)
        month: 対象月 (デフォルト: 今月)

    Auth:
        Bearer トークン必須 (Admin または Editor ロール)
    """
    now = datetime.now(timezone.utc)
    target_year = year if year is not None else now.year
    target_month = month if month is not None else now.month

    period = f"{target_year}年{target_month}月"

    # モックデータ（実運用では DB から集計する）
    data = MonthlyReportData(
        period=period,
        total_proposals=120,
        positive_results=84,
        win_rate=70.0,
        total_gain_jpy=345_000,
        avg_gain_per_trade_jpy=4_107,
        total_fees_jpy=12_500,
        annual_yield_pct=18.5,
    )

    content, content_type = generate_monthly_report_pdf(data)

    ext = "pdf" if content_type == "application/pdf" else "csv"
    filename = f"monthly_report_{target_year}_{target_month:02d}.{ext}"

    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
