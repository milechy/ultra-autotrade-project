# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""月次レポート生成のユニットテスト。"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-monthly-report")

from app.database import Base  # noqa: E402
from app.reports.monthly_report import (  # noqa: E402
    MonthlyReportData,
    build_monthly_report_data,
    generate_monthly_report_pdf,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_data(**kwargs: object) -> MonthlyReportData:
    defaults: dict[str, object] = {
        "period": "2026年3月",
        "total_proposals": 100,
        "positive_results": 70,
        "win_rate": 70.0,
        "total_gain_jpy": 200_000,
        "avg_gain_per_trade_jpy": 2_857,
        "total_fees_jpy": 8_000,
        "annual_yield_pct": 15.0,
    }
    defaults.update(kwargs)
    return MonthlyReportData(**defaults)  # type: ignore[arg-type]


@pytest.fixture()
def sqlite_db():
    """テスト用の一時的な SQLite データベースを作成する。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


# ---------------------------------------------------------------------------
# 既存ユニットテスト (MonthlyReportData / generate_monthly_report_pdf)
# ---------------------------------------------------------------------------


def test_generate_report_returns_bytes() -> None:
    """レポート生成が bytes を返すことを確認する。"""
    data = _make_data()
    content, content_type = generate_monthly_report_pdf(data)

    assert isinstance(content, bytes)
    assert len(content) > 0
    assert content_type in ("application/pdf", "text/csv")


def test_report_contains_period_text() -> None:
    """レポートに対象期間の年が含まれることを確認する。"""
    data = _make_data(period="2026年3月")
    content, content_type = generate_monthly_report_pdf(data)

    assert b"2026" in content


def test_win_rate_calculation() -> None:
    """勝率の計算が正しいことをサニティチェックする。"""
    total = 50
    positive = 35
    expected_win_rate = positive / total * 100  # 70.0

    data = _make_data(
        total_proposals=total,
        positive_results=positive,
        win_rate=expected_win_rate,
    )
    assert data.win_rate == 70.0

    content, _ = generate_monthly_report_pdf(data)
    assert isinstance(content, bytes)
    assert len(content) > 0


# ---------------------------------------------------------------------------
# build_monthly_report_data テスト
# ---------------------------------------------------------------------------


class TestBuildMonthlyReportData:
    """build_monthly_report_data の DB 集計テスト。"""

    def test_empty_db_returns_zeros(self, sqlite_db) -> None:
        """データが存在しない場合はゼロ値が返る。"""
        result = build_monthly_report_data(sqlite_db, 2026, 3)

        assert result.period == "2026年3月"
        assert result.total_proposals == 0
        assert result.positive_results == 0
        assert result.win_rate == 0.0
        assert result.total_gain_jpy == 0
        assert result.total_fees_jpy == 0
        assert result.annual_yield_pct == 0.0

    def test_proposals_counted_in_month(self, sqlite_db) -> None:
        """対象月のプロポーザルが正しく集計される。"""

        _insert_proposal(sqlite_db, user_id=1, status="executed", year=2026, month=3)
        _insert_proposal(sqlite_db, user_id=1, status="rejected", year=2026, month=3)
        _insert_proposal(sqlite_db, user_id=1, status="executed", year=2026, month=4)

        result = build_monthly_report_data(sqlite_db, 2026, 3)

        assert result.total_proposals == 2
        assert result.positive_results == 1
        assert result.win_rate == 50.0

    def test_proposals_filtered_by_user_id(self, sqlite_db) -> None:
        """user_id 指定時は自ユーザーのデータのみ集計される。"""
        _insert_proposal(sqlite_db, user_id=1, status="executed", year=2026, month=3)
        _insert_proposal(sqlite_db, user_id=2, status="executed", year=2026, month=3)
        _insert_proposal(sqlite_db, user_id=2, status="executed", year=2026, month=3)

        result_user1 = build_monthly_report_data(sqlite_db, 2026, 3, user_id=1)
        result_user2 = build_monthly_report_data(sqlite_db, 2026, 3, user_id=2)

        assert result_user1.total_proposals == 1
        assert result_user2.total_proposals == 2

    def test_fee_transactions_aggregated(self, sqlite_db) -> None:
        """fee_transactions から JPY 金額が集計される。"""
        _insert_fee_tx(
            sqlite_db,
            user_id=1,
            year=2026,
            month=3,
            net_profit_jpy=Decimal("50000"),
            fee_amount_jpy=Decimal("5000"),
            deposit_amount_jpy=Decimal("1000000"),
        )
        _insert_fee_tx(
            sqlite_db,
            user_id=2,
            year=2026,
            month=3,
            net_profit_jpy=Decimal("30000"),
            fee_amount_jpy=Decimal("3000"),
            deposit_amount_jpy=Decimal("500000"),
        )

        # 全ユーザー集計
        result = build_monthly_report_data(sqlite_db, 2026, 3)
        assert result.total_gain_jpy == 80000
        assert result.total_fees_jpy == 8000

    def test_fee_transactions_filtered_by_user(self, sqlite_db) -> None:
        """user_id 指定時は該当ユーザーの fee_transactions のみ集計される。"""
        _insert_fee_tx(
            sqlite_db,
            user_id=1,
            year=2026,
            month=3,
            net_profit_jpy=Decimal("50000"),
            fee_amount_jpy=Decimal("5000"),
            deposit_amount_jpy=Decimal("1000000"),
        )
        _insert_fee_tx(
            sqlite_db,
            user_id=2,
            year=2026,
            month=3,
            net_profit_jpy=Decimal("30000"),
            fee_amount_jpy=Decimal("3000"),
            deposit_amount_jpy=Decimal("500000"),
        )

        result = build_monthly_report_data(sqlite_db, 2026, 3, user_id=1)
        assert result.total_gain_jpy == 50000
        assert result.total_fees_jpy == 5000

    def test_annual_yield_calculated_from_fee_tx(self, sqlite_db) -> None:
        """年率換算利回りが fee_transactions から計算される。"""
        # 月次利益 = 10,000円 / 元本 100万円 = 月次利率 1% → 年率 12%
        _insert_fee_tx(
            sqlite_db,
            user_id=1,
            year=2026,
            month=3,
            net_profit_jpy=Decimal("10000"),
            fee_amount_jpy=Decimal("1000"),
            deposit_amount_jpy=Decimal("1000000"),
        )

        result = build_monthly_report_data(sqlite_db, 2026, 3, user_id=1)
        assert result.annual_yield_pct == pytest.approx(12.0, rel=1e-3)

    def test_avg_gain_per_trade_calculated(self, sqlite_db) -> None:
        """平均損益/回が total_gain / total_proposals で計算される。"""
        _insert_proposal(sqlite_db, user_id=1, status="executed", year=2026, month=3)
        _insert_proposal(sqlite_db, user_id=1, status="executed", year=2026, month=3)
        _insert_fee_tx(
            sqlite_db,
            user_id=1,
            year=2026,
            month=3,
            net_profit_jpy=Decimal("10000"),
            fee_amount_jpy=Decimal("1000"),
            deposit_amount_jpy=Decimal("1000000"),
        )

        result = build_monthly_report_data(sqlite_db, 2026, 3, user_id=1)
        assert result.avg_gain_per_trade_jpy == 5000  # 10000 // 2

    def test_december_month_boundary(self, sqlite_db) -> None:
        """12月指定で翌1月にまたがる提案が含まれないことを確認する。"""
        _insert_proposal(sqlite_db, user_id=1, status="executed", year=2026, month=12)
        _insert_proposal(sqlite_db, user_id=1, status="executed", year=2027, month=1)

        result = build_monthly_report_data(sqlite_db, 2026, 12, user_id=1)
        assert result.total_proposals == 1


# ---------------------------------------------------------------------------
# ヘルパー: テストデータ挿入
# ---------------------------------------------------------------------------


def _insert_proposal(db, *, user_id: int, status: str, year: int, month: int) -> None:
    """テスト用プロポーザルを挿入する。"""
    from app.proposals.models import Proposal

    created_at = datetime(year, month, 15, 12, 0, 0, tzinfo=timezone.utc)
    expires_at = datetime(year, month, 16, 12, 0, 0, tzinfo=timezone.utc)
    p = Proposal(
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("100"),
        amount_usd=Decimal("100"),
        reason="test",
        status=status,
        expires_at=expires_at,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(p)
    db.commit()


def _insert_fee_tx(
    db,
    *,
    user_id: int,
    year: int,
    month: int,
    net_profit_jpy: Decimal,
    fee_amount_jpy: Decimal,
    deposit_amount_jpy: Decimal,
) -> None:
    """テスト用 fee_transaction を挿入する。"""
    import datetime as dt

    from app.fees.models import FeeTransaction

    ft = FeeTransaction(
        user_id=user_id,
        calculation_month=dt.date(year, month, 1),
        tier="LOWER",
        risk_mode="conservative",
        deposit_amount_jpy=deposit_amount_jpy,
        net_profit_jpy=net_profit_jpy,
        fee_amount_jpy=fee_amount_jpy,
        gross_profit_jpy=net_profit_jpy + fee_amount_jpy,
    )
    db.add(ft)
    db.commit()
