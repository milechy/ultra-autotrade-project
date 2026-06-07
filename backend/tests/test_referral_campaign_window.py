# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_referral_campaign_window.py
"""紹介キャンペーン ウィンドウ (handle_new_referral) のユニットテスト。

仕様 (Asana 1215467015333283 / 2026-06-06 確定):
- 報酬ウィンドウ末 = 最後に紹介した月 + 13ヶ月 (= reward_start_month + 12)。
- シングルスロット・ローリング: 新規紹介で同一パートナーの旧ウィンドウを今月で打ち切り、
  最新友達ベースの新ウィンドウを開く。

handle_new_referral は users 行を参照せず partner_id / referree_id を整数として扱うため、
本テストは ReferralCampaign のみで完結する (sqlite, FK 未強制)。
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-referral-window")

from app.database import Base  # noqa: E402
from app.fees.models import ReferralCampaign  # noqa: E402
from app.referral.service import _add_months, handle_new_referral  # noqa: E402


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


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def test_window_end_is_referral_month_plus_13(db: Session) -> None:
    today = date.today()
    current_month = date(today.year, today.month, 1)

    campaign = handle_new_referral(db, partner_id=1, referree_id=2)
    db.commit()

    # 来月スタート
    assert campaign.reward_start_month == _add_months(current_month, 1)
    # 末 = start + 12ヶ月
    assert campaign.reward_expires_month == _add_months(campaign.reward_start_month, 12)
    assert _months_between(campaign.reward_start_month, campaign.reward_expires_month) == 12
    # = 最後に紹介した月 (current_month) + 13ヶ月
    assert _months_between(current_month, campaign.reward_expires_month) == 13
    assert campaign.ended_early_month is None


def test_new_referral_rolls_single_slot(db: Session) -> None:
    today = date.today()
    current_month = date(today.year, today.month, 1)

    first = handle_new_referral(db, partner_id=1, referree_id=2)
    db.commit()
    first_id = first.id

    # 同一パートナーが別の友達を新規紹介 → 旧ウィンドウは今月で打ち切り、新ウィンドウ開設
    second = handle_new_referral(db, partner_id=1, referree_id=3)
    db.commit()

    db.refresh(first)
    assert first.ended_early_month == current_month, "旧ウィンドウは今月で ended_early"
    assert second.id != first_id
    assert second.referree_id == 3
    assert second.ended_early_month is None
    # 新ウィンドウも +13ヶ月仕様
    assert _months_between(current_month, second.reward_expires_month) == 13

    # アクティブ (ended_early=None) は最新の1件のみ = シングルスロット
    active = (
        db.query(ReferralCampaign)
        .filter(
            ReferralCampaign.partner_id == 1,
            ReferralCampaign.ended_early_month.is_(None),
        )
        .all()
    )
    assert len(active) == 1
    assert active[0].referree_id == 3
