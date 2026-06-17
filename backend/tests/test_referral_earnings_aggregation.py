# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_referral_earnings_aggregation.py
"""紹介報酬集計 (get_referral_earnings) の回帰テスト。

既存挙動のカバレッジのみ。新機能は追加しない。

検証範囲:
- referral_count: referrer_id == partner_id のユーザー数
- current_month_reward_jpy: 当月 (calculation_month == current_month) の affiliate_amount_jpy 合計
- total_payout_jpy: 全月の affiliate_amount_jpy 累計
- 他 partner 宛 (affiliate_id != partner) は集計に混入しない
- FeeTransaction が無い場合は "0" を返す
- campaign_rate: active FeeConfigV10 が無い場合の fallback "0.10"
- PL10: 開始待ち (pending) ウィンドウでも campaign_expires_month を埋め、campaign_status で区別
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-referral-earnings")

from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.fees.models import FeeTransaction, ReferralCampaign  # noqa: E402
from app.referral.service import _add_months, get_referral_earnings  # noqa: E402

PARTNER_ID = 1
OTHER_PARTNER_ID = 99


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        os.unlink(path)


def _make_user(db: Session, user_id: int, referrer_id: int | None = None) -> User:
    user = User(
        id=user_id,
        email=f"user{user_id}@example.com",
        username=f"user{user_id}",
        hashed_password="x",
        referrer_id=referrer_id,
    )
    db.add(user)
    return user


def _make_fee_tx(
    db: Session,
    *,
    user_id: int,
    affiliate_id: int | None,
    calculation_month: date,
    affiliate_amount_jpy: str,
) -> FeeTransaction:
    tx = FeeTransaction(
        user_id=user_id,
        calculation_month=calculation_month,
        tier="LOWER",
        risk_mode="conservative",
        deposit_amount_jpy=Decimal("100000.00"),
        affiliate_id=affiliate_id,
        affiliate_amount_jpy=Decimal(affiliate_amount_jpy),
    )
    db.add(tx)
    return tx


def _current_month() -> date:
    today = date.today()
    return date(today.year, today.month, 1)


def test_referral_count_counts_only_own_referrees(db: Session) -> None:
    """referral_count は referrer_id == partner_id のユーザーのみ数える。"""
    _make_user(db, PARTNER_ID)
    _make_user(db, 2, referrer_id=PARTNER_ID)
    _make_user(db, 3, referrer_id=PARTNER_ID)
    _make_user(db, 4, referrer_id=OTHER_PARTNER_ID)  # 別 partner 配下
    db.commit()

    result = get_referral_earnings(db, PARTNER_ID)
    assert result["referral_count"] == 2


def test_current_month_and_total_payout_aggregation(db: Session) -> None:
    """current_month は当月分、total_payout は全月累計を集計する。"""
    current = _current_month()
    last_month = _add_months(current, -1)

    _make_user(db, PARTNER_ID)
    referree = _make_user(db, 2, referrer_id=PARTNER_ID)
    db.commit()

    # 当月分: 1200 + 300 = 1500
    _make_fee_tx(
        db,
        user_id=referree.id,
        affiliate_id=PARTNER_ID,
        calculation_month=current,
        affiliate_amount_jpy="1200.00",
    )
    # 同じ partner の別ユーザー当月分 (user_id/month ユニーク制約を回避するため別 user)
    _make_user(db, 3, referrer_id=PARTNER_ID)
    db.commit()
    _make_fee_tx(
        db,
        user_id=3,
        affiliate_id=PARTNER_ID,
        calculation_month=current,
        affiliate_amount_jpy="300.00",
    )
    # 先月分: 500 (current には含まれないが total には含まれる)
    _make_fee_tx(
        db,
        user_id=referree.id,
        affiliate_id=PARTNER_ID,
        calculation_month=last_month,
        affiliate_amount_jpy="500.00",
    )
    db.commit()

    result = get_referral_earnings(db, PARTNER_ID)
    assert result["current_month_reward_jpy"] == "1500.00"
    assert result["total_payout_jpy"] == "2000.00"


def test_other_partner_amount_not_mixed_in(db: Session) -> None:
    """affiliate_id が別 partner の FeeTransaction は集計に混入しない。"""
    current = _current_month()
    _make_user(db, PARTNER_ID)
    _make_user(db, OTHER_PARTNER_ID)
    _make_user(db, 2, referrer_id=PARTNER_ID)
    db.commit()

    _make_fee_tx(
        db,
        user_id=2,
        affiliate_id=OTHER_PARTNER_ID,
        calculation_month=current,
        affiliate_amount_jpy="9999.00",
    )
    db.commit()

    result = get_referral_earnings(db, PARTNER_ID)
    assert result["current_month_reward_jpy"] == "0"
    assert result["total_payout_jpy"] == "0"


def test_no_fee_transactions_returns_zero(db: Session) -> None:
    """FeeTransaction が無い partner は "0" を返し、fallback rate は "0.10"。"""
    _make_user(db, PARTNER_ID)
    db.commit()

    result = get_referral_earnings(db, PARTNER_ID)
    assert result["referral_count"] == 0
    assert result["current_month_reward_jpy"] == "0"
    assert result["total_payout_jpy"] == "0"
    assert result["campaign_rate"] == "0.10"
    assert result["campaign_expires_month"] is None
    assert result["campaign_status"] is None


def test_active_campaign_window_reports_active(db: Session) -> None:
    """開始済みウィンドウは campaign_status='active' で expires を返す。"""
    current = _current_month()
    db.add(
        ReferralCampaign(
            partner_id=PARTNER_ID,
            referree_id=2,
            reward_start_month=_add_months(current, -1),  # 先月開始 (=開始済み)
            reward_expires_month=_add_months(current, 11),
        )
    )
    db.commit()

    result = get_referral_earnings(db, PARTNER_ID)
    assert result["campaign_status"] == "active"
    assert result["campaign_expires_month"] == str(_add_months(current, 11))


def test_pending_campaign_window_reports_pending_not_null(db: Session) -> None:
    """PL10 回帰: 翌月開始予定ウィンドウは null でなく pending + expires を返す。"""
    current = _current_month()
    # handle_new_referral 直後の状態: start = 翌月、expires = start + 12
    start = _add_months(current, 1)
    db.add(
        ReferralCampaign(
            partner_id=PARTNER_ID,
            referree_id=2,
            reward_start_month=start,
            reward_expires_month=_add_months(start, 12),
        )
    )
    db.commit()

    result = get_referral_earnings(db, PARTNER_ID)
    # 修正前は None だった (「キャンペーンなし」誤表示) — 今は expires を埋める
    assert result["campaign_expires_month"] == str(_add_months(start, 12))
    assert result["campaign_status"] == "pending"
