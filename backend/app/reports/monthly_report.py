# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""月次レポート生成モジュール。

reportlab が利用可能な場合は PDF を、そうでない場合は CSV を返す。
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class MonthlyReportData:
    """月次レポートのデータ。"""

    period: str  # 例: "2026年3月"
    total_proposals: int
    positive_results: int
    win_rate: float
    total_gain_jpy: int
    avg_gain_per_trade_jpy: int
    total_fees_jpy: int
    annual_yield_pct: float


def build_monthly_report_data(
    db: Session,
    year: int,
    month: int,
    user_id: int | None = None,
) -> MonthlyReportData:
    """DB から実データを集計して MonthlyReportData を構築する。

    Args:
        db: SQLAlchemy セッション
        year: 対象年
        month: 対象月
        user_id: 集計対象ユーザー ID。None の場合は全ユーザー集計。
    """
    from app.fees.models import FeeTransaction
    from app.proposals.models import Proposal

    period_str = f"{year}年{month}月"

    start_dt = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end_dt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_dt = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    # --- proposals 集計 ---
    q = db.query(Proposal).filter(
        Proposal.created_at >= start_dt,
        Proposal.created_at < end_dt,
    )
    if user_id is not None:
        q = q.filter(Proposal.user_id == user_id)

    proposals = q.all()
    total_proposals = len(proposals)
    positive_results = sum(1 for p in proposals if p.status == "executed")
    win_rate = (positive_results / total_proposals * 100.0) if total_proposals > 0 else 0.0

    # --- fee_transactions 集計 (JPY ベース) ---
    calc_month = date(year, month, 1)
    ft_q = db.query(FeeTransaction).filter(FeeTransaction.calculation_month == calc_month)
    if user_id is not None:
        ft_q = ft_q.filter(FeeTransaction.user_id == user_id)

    fee_txs = ft_q.all()

    total_gain_jpy = int(sum(ft.net_profit_jpy for ft in fee_txs))
    total_fees_jpy = int(sum(ft.fee_amount_jpy for ft in fee_txs))
    avg_gain_per_trade_jpy = (total_gain_jpy // total_proposals) if total_proposals > 0 else 0

    # 年率換算: (月次利益 / 預け入れ元本) * 12 * 100
    deposit_total = sum(ft.deposit_amount_jpy for ft in fee_txs)
    annual_yield_pct = 0.0
    if deposit_total > 0:
        monthly_yield = Decimal(str(total_gain_jpy)) / deposit_total
        annual_yield_pct = round(float(monthly_yield) * 12 * 100, 2)

    return MonthlyReportData(
        period=period_str,
        total_proposals=total_proposals,
        positive_results=positive_results,
        win_rate=round(win_rate, 1),
        total_gain_jpy=total_gain_jpy,
        avg_gain_per_trade_jpy=avg_gain_per_trade_jpy,
        total_fees_jpy=total_fees_jpy,
        annual_yield_pct=annual_yield_pct,
    )


def _fmt_yen(amount: int) -> str:
    """円額を ¥1,234,567 形式にフォーマットする。"""
    return f"¥{amount:,}"


def _generate_pdf(data: MonthlyReportData) -> bytes:
    """reportlab で PDF バイトを生成する。"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # 日本語フォントの登録を試みる（なければデフォルトフォントにフォールバック）
    _FONT_NAME = "Helvetica"
    try:
        import os

        font_candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for fc in font_candidates:
            if os.path.exists(fc):
                pdfmetrics.registerFont(TTFont("JapaneseFont", fc))
                _FONT_NAME = "JapaneseFont"
                break
    except Exception as exc:
        logger.warning("Failed to register Japanese font for PDF: %s", exc)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm)
    styles = getSampleStyleSheet()
    story = []

    # タイトル
    title_style = styles["Title"]
    story.append(Paragraph(f"月次レポート - {data.period}", title_style))
    story.append(Spacer(1, 12))

    # 概要テーブル
    table_data = [
        ["項目", "値"],
        ["対象期間", data.period],
        ["提案回数", f"{data.total_proposals:,} 回"],
        ["プラス結果", f"{data.positive_results:,} 回"],
        ["勝率", f"{data.win_rate:.1f} %"],
        ["累計損益", _fmt_yen(data.total_gain_jpy)],
        ["平均損益 / 回", _fmt_yen(data.avg_gain_per_trade_jpy)],
        ["手数料合計", _fmt_yen(data.total_fees_jpy)],
        ["年率換算利回り", f"{data.annual_yield_pct:.2f} %"],
    ]

    table = Table(table_data, colWidths=[80 * mm, 80 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4ff")]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 16))

    # 注意書き
    note_style = styles["Normal"]
    story.append(
        Paragraph(
            "※ 実績は将来の結果を保証しません。本レポートは情報提供のみを目的としています。",
            note_style,
        )
    )

    doc.build(story)
    return buf.getvalue()


def _generate_csv(data: MonthlyReportData) -> bytes:
    """CSV バイトを生成する（reportlab 非インストール時のフォールバック）。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["月次レポート", data.period])
    writer.writerow([])
    writer.writerow(["項目", "値"])
    writer.writerow(["対象期間", data.period])
    writer.writerow(["提案回数", f"{data.total_proposals:,} 回"])
    writer.writerow(["プラス結果", f"{data.positive_results:,} 回"])
    writer.writerow(["勝率", f"{data.win_rate:.1f} %"])
    writer.writerow(["累計損益", _fmt_yen(data.total_gain_jpy)])
    writer.writerow(["平均損益 / 回", _fmt_yen(data.avg_gain_per_trade_jpy)])
    writer.writerow(["手数料合計", _fmt_yen(data.total_fees_jpy)])
    writer.writerow(["年率換算利回り", f"{data.annual_yield_pct:.2f} %"])
    writer.writerow([])
    writer.writerow(["※ 実績は将来の結果を保証しません。"])
    return buf.getvalue().encode("utf-8-sig")  # BOM 付き UTF-8 (Excel 対応)


def generate_monthly_report_pdf(data: MonthlyReportData) -> tuple[bytes, str]:
    """月次レポートを生成する。

    reportlab が利用可能なら PDF (content-type: application/pdf)、
    そうでなければ CSV (content-type: text/csv) を返す。

    Returns:
        (bytes, content_type) のタプル
    """
    try:
        import reportlab  # noqa: F401

        return _generate_pdf(data), "application/pdf"
    except ImportError:
        return _generate_csv(data), "text/csv"
