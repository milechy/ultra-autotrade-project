# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_tier_fee_integration.py
"""
tier判定→動的手数料記録 統合テスト。

determine_tier_jpy(資産額JPY) → InvestmentTier → _lookup_fee_rate_for_user → fee_rate
の連続パスを1テストで検証する。

関連:
- backend/app/users/tier_service.py (determine_tier_jpy)
- backend/app/proposals/router.py (_lookup_fee_rate_for_user)
- backend/app/auth/models.py (InvestmentTier, TIER_BOUNDARY_*)
- Asana GID 1215470296814936
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-tier-fee-integration")

from app.api.v1.fees import finalize_month_core  # noqa: E402
from app.auth.models import (  # noqa: E402
    TIER_BOUNDARY_LOWER_JPY,
    TIER_BOUNDARY_UPPER_JPY,
    InvestmentTier,
    User,
)
from app.database import Base  # noqa: E402
from app.fees.models import FeeConfigV10, FeeTransaction  # noqa: E402
from app.portfolio.models import PortfolioSnapshot  # noqa: E402
from app.proposals.router import _lookup_fee_rate_for_user  # noqa: E402
from app.users.tier_service import determine_tier_jpy  # noqa: E402

_JST = timezone(timedelta(hours=9))

# tier_fee_rates のインデックスは _lookup_fee_rate_for_user 内の _TIER_INDEX に対応:
#   LOWER  → index 0
#   MIDDLE → index 1
#   UPPER  → index 2
_TIER_FEE_RATES = [Decimal("0.30"), Decimal("0.25"), Decimal("0.20")]


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """SQLite in-memory テスト DB セッション（test_proposals_fee_wiring.py のパターンを踏襲）。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)
    os.close(fd)
    os.unlink(path)


def _insert_user(db: Session, user_id: int, tier: str) -> User:
    user = User(
        id=user_id,
        email=f"user{user_id}@example.com",
        username=f"user{user_id}",
        hashed_password="x",
        tier=tier,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _insert_fee_config(db: Session, *, is_active: bool = True) -> FeeConfigV10:
    config = FeeConfigV10(
        config_name="v10_integration_test",
        tier_thresholds_jpy=[TIER_BOUNDARY_LOWER_JPY, TIER_BOUNDARY_UPPER_JPY],
        tier_fee_rates=[float(r) for r in _TIER_FEE_RATES],  # LOWER=0.30, MIDDLE=0.25, UPPER=0.20
        tier_monthly_yield_caps=[0.018, 0.023, 0.030],
        subscription_rates={"conservative": 0.0, "balanced": 0.003, "aggressive": 0.01},
        expense_markup_enabled=False,
        expense_markup_rate=Decimal("0"),
        affiliate_rate=Decimal("0.10"),
        is_active=is_active,
        effective_from=datetime(2026, 5, 1, tzinfo=_JST),
    )
    db.add(config)
    db.flush()
    return config


class TestTierFeeIntegration:
    """資産額→tier→fee_rate の統合パスを E2E で検証する。

    determine_tier_jpy で計算した tier を User.tier に反映し、
    _lookup_fee_rate_for_user が対応する fee_rate を返すことを Decimal 等価で検証する。
    """

    @pytest.mark.parametrize(
        "deposit_jpy,expected_tier,expected_fee_idx",
        [
            # --- LOWER 境界 ---
            # 境界以下: LOWER (index 0)
            (Decimal("1000000"), InvestmentTier.LOWER, 0),
            # ちょうど境界: LOWER (LOWER_JPY <= 1,000,000)
            (Decimal("999999"), InvestmentTier.LOWER, 0),
            # --- LOWER→MIDDLE 境界超え ---
            # 1,000,001 円: MIDDLE (index 1)
            (Decimal("1000001"), InvestmentTier.MIDDLE, 1),
            # 中間値: MIDDLE
            (Decimal("5000000"), InvestmentTier.MIDDLE, 1),
            # --- MIDDLE 上限 ---
            # ちょうど上限: MIDDLE (UPPER_JPY <= 10,000,000)
            (Decimal("10000000"), InvestmentTier.MIDDLE, 1),
            # --- MIDDLE→UPPER 境界超え ---
            # 10,000,001 円: UPPER (index 2)
            (Decimal("10000001"), InvestmentTier.UPPER, 2),
            # 大口: UPPER
            (Decimal("50000000"), InvestmentTier.UPPER, 2),
        ],
    )
    def test_asset_to_tier_to_fee_rate(
        self,
        deposit_jpy: Decimal,
        expected_tier: InvestmentTier,
        expected_fee_idx: int,
        db_session: Session,
    ) -> None:
        """資産変動 → tier変化 → fee_rate変化の連続パスを保証する。

        1. determine_tier_jpy で deposit_jpy から tier を決定する
        2. User の tier を設定して DB に保存する
        3. FeeConfigV10 (is_active=True) を挿入する
        4. _lookup_fee_rate_for_user を呼ぶ
        5. 返された fee_rate が tier_fee_rates[expected_fee_idx] と Decimal 等価であることを assert する
        """
        # Step 1: determine_tier_jpy で tier を決定する
        computed_tier = determine_tier_jpy(deposit_jpy)
        assert computed_tier == expected_tier, (
            f"deposit_jpy={deposit_jpy}: expected tier={expected_tier.value}, "
            f"got {computed_tier.value}"
        )

        # Step 2: User を DB に挿入する（computed_tier.value を tier 文字列として使用）
        _insert_user(db_session, user_id=1, tier=computed_tier.value)

        # Step 3: FeeConfigV10 を挿入する
        _insert_fee_config(db_session)
        db_session.commit()

        # Step 4: 連続パスの終端を呼ぶ
        actual_fee_rate = _lookup_fee_rate_for_user(db_session, user_id=1)

        # Step 5: Decimal 等価で assert する
        expected_fee_rate = _TIER_FEE_RATES[expected_fee_idx]
        assert actual_fee_rate == expected_fee_rate, (
            f"deposit_jpy={deposit_jpy}, tier={expected_tier.value}: "
            f"expected fee_rate={expected_fee_rate}, got {actual_fee_rate}"
        )

    def test_no_fee_config_returns_zero(self, db_session: Session) -> None:
        """FeeConfigV10 未設定時は Decimal('0') を返す（fail-open 設計の検証）。

        active な FeeConfigV10 が存在しない状態で _lookup_fee_rate_for_user を呼んだとき、
        例外を送出せず Decimal('0') を返すことを確認する。
        """
        _insert_user(db_session, user_id=2, tier=InvestmentTier.MIDDLE.value)
        db_session.commit()

        # FeeConfigV10 を挿入しない状態で呼ぶ
        actual_fee_rate = _lookup_fee_rate_for_user(db_session, user_id=2)

        assert actual_fee_rate == Decimal("0"), (
            f"FeeConfigV10 未設定時は Decimal('0') を期待したが got {actual_fee_rate}"
        )

    def test_inactive_fee_config_returns_zero(self, db_session: Session) -> None:
        """is_active=False の FeeConfigV10 のみ存在する場合も Decimal('0') を返す。

        active フラグの ON/OFF が fee_rate 選択に正しく反映されることを検証する。
        """
        _insert_user(db_session, user_id=3, tier=InvestmentTier.UPPER.value)
        _insert_fee_config(db_session, is_active=False)
        db_session.commit()

        actual_fee_rate = _lookup_fee_rate_for_user(db_session, user_id=3)

        assert actual_fee_rate == Decimal("0"), (
            f"is_active=False の config のみの場合は Decimal('0') を期待したが got {actual_fee_rate}"
        )


# 月次バッチ (finalize_month_core) 内で tier を deposit_jpy から都度判定・書き戻す配線の検証。
_MONTH_START = date(2026, 5, 1)


def _insert_snapshot(
    db: Session,
    user_id: int,
    total_supply_usd: Decimal,
    recorded_at: datetime,
) -> PortfolioSnapshot:
    snap = PortfolioSnapshot(
        user_id=user_id,
        total_value_usd=total_supply_usd,
        total_supply_usd=total_supply_usd,
        total_borrow_usd=Decimal("0"),
        recorded_at=recorded_at,
    )
    db.add(snap)
    db.flush()
    return snap


class TestFinalizeMonthTierWiring:
    """月次バッチが DB の stale な user.tier を読まず、deposit_jpy から都度判定することを検証する。

    usd_jpy_rate=1 で seed するため total_supply_usd がそのまま deposit_jpy になる。
    全ユーザーは DB デフォルト相当の tier="LOWER" で seed し、finalize 後に
    deposit_jpy に応じた tier へ書き戻されること・FeeTransaction に正しい tier /
    fee_rate_applied が記録されることを assert する。
    """

    @pytest.mark.parametrize(
        "deposit_jpy,expected_tier,expected_fee_rate",
        [
            # 境界: <= 1,000,000 は LOWER
            (Decimal("1000000"), "LOWER", Decimal("0.30")),
            # 1,000,001 は MIDDLE
            (Decimal("1000001"), "MIDDLE", Decimal("0.25")),
            # 10,000,001 は UPPER
            (Decimal("10000001"), "UPPER", Decimal("0.20")),
        ],
    )
    def test_tier_determined_from_deposit_and_written_back(
        self,
        deposit_jpy: Decimal,
        expected_tier: str,
        expected_fee_rate: Decimal,
        db_session: Session,
    ) -> None:
        """deposit_jpy から tier を判定し、FeeTransaction と user.tier の両方へ反映する。"""
        # 全ユーザーを stale な tier="LOWER" で seed する (DB デフォルト相当)。
        user = _insert_user(db_session, user_id=1, tier="LOWER")
        # 月初・月末スナップショット。deposit_jpy は月末 (last_snap) の supply で決まる。
        # 月初は profit を出すため deposit_jpy より低くする (conservative なので sub=0)。
        _insert_snapshot(
            db_session,
            user_id=1,
            total_supply_usd=deposit_jpy - Decimal("100000"),
            recorded_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        _insert_snapshot(
            db_session,
            user_id=1,
            total_supply_usd=deposit_jpy,
            recorded_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        )
        config = _insert_fee_config(db_session)
        db_session.commit()

        finalize_month_core(
            db_session,
            config,
            _MONTH_START,
            usd_jpy_rate=Decimal("1"),
            dry_run=False,
        )

        # user.tier が deposit_jpy 由来の tier へ書き戻されている。
        db_session.refresh(user)
        assert user.tier == expected_tier, (
            f"deposit_jpy={deposit_jpy}: user.tier expected {expected_tier}, got {user.tier}"
        )

        # FeeTransaction に正しい tier / fee_rate_applied が記録されている。
        fee_tx = db_session.scalar(
            select(FeeTransaction).where(
                FeeTransaction.user_id == 1,
                FeeTransaction.calculation_month == _MONTH_START,
            )
        )
        assert fee_tx is not None, "FeeTransaction が生成されていない"
        assert fee_tx.tier == expected_tier
        assert fee_tx.fee_rate_applied == expected_fee_rate, (
            f"fee_rate_applied expected {expected_fee_rate}, got {fee_tx.fee_rate_applied}"
        )

    def test_dry_run_does_not_write_back_tier(self, db_session: Session) -> None:
        """dry_run=True では user.tier を書き換えず FeeTransaction も生成しない。"""
        # deposit_jpy=5,000,000 → MIDDLE 相当だが tier="LOWER" のまま seed。
        user = _insert_user(db_session, user_id=1, tier="LOWER")
        _insert_snapshot(
            db_session,
            user_id=1,
            total_supply_usd=Decimal("4900000"),
            recorded_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        _insert_snapshot(
            db_session,
            user_id=1,
            total_supply_usd=Decimal("5000000"),
            recorded_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        )
        config = _insert_fee_config(db_session)
        db_session.commit()

        finalize_month_core(
            db_session,
            config,
            _MONTH_START,
            usd_jpy_rate=Decimal("1"),
            dry_run=True,
        )

        db_session.refresh(user)
        assert user.tier == "LOWER", f"dry_run=True では user.tier 不変を期待したが got {user.tier}"
        fee_tx = db_session.scalar(select(FeeTransaction).where(FeeTransaction.user_id == 1))
        assert fee_tx is None, "dry_run=True では FeeTransaction を生成してはならない"
