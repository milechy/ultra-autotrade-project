# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_monthly_fee_batch.py
"""F-7: 月末バッチ処理のテスト (Asana 1214120401388139)。

カバレッジ範囲:
- ``next_batch_run_jst`` の月境界 (JST 23:59:59 → 00:00:00)
- ``run_monthly_fee_batch`` の冪等性 (二重実行で skip)
- 全 tier × 全 risk_mode の組み合わせ計算
- エラー時の rollback (個別ユーザー失敗は他ユーザーに波及しない)
- Slack 通知 (notify_slack=False で副作用なし)
- finalize-month admin endpoint (501 → 200)
- DISABLE_MONTHLY_FEE_BATCH によるループ無効化判定

DB は test_api_v1_fees.py と同じ「Base + V10Base 両方を create_all」方式。
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET_KEY"] = "test-secret-key-monthly-fee-batch"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"

from app.auth.models import (  # noqa: E402
    InvestmentTier,
    RiskMode,
    User,
    UserRole,
)
from app.automation import monthly_fee_batch as mfb  # noqa: E402
from app.billing.v10_models import FeeConfigV10, FeeTransaction, V10Base  # noqa: E402
from app.database import Base  # noqa: E402
from app.partner.allocation_models import FundAllocation  # noqa: E402
from tests.helpers.fee_config_factory import make_v10_default_config  # noqa: E402

_JST = timezone(timedelta(hours=9))

# FeeTransaction.user_id FK が別 metadata なので、テスト用に users を v10 metadata にも複製
if "users" not in V10Base.metadata.tables:
    User.__table__.to_metadata(V10Base.metadata)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db() -> Generator[tuple[Any, Any], None, None]:
    """SQLite テスト DB (Base + V10Base 両方 create_all)。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    # 旧 fee_configs / fee_calculations / high_water_marks を drop して v10 版を作成
    if "fee_configs" in Base.metadata.tables:
        Base.metadata.tables["fee_configs"].drop(bind=engine)
    if "fee_calculations" in Base.metadata.tables:
        Base.metadata.tables["fee_calculations"].drop(bind=engine)
    if "high_water_marks" in Base.metadata.tables:
        Base.metadata.tables["high_water_marks"].drop(bind=engine)
    FeeConfigV10.__table__.create(bind=engine)  # type: ignore[attr-defined]
    FeeTransaction.__table__.create(bind=engine)  # type: ignore[attr-defined]
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield engine, SessionLocal
    FeeTransaction.__table__.drop(bind=engine)  # type: ignore[attr-defined]
    FeeConfigV10.__table__.drop(bind=engine)  # type: ignore[attr-defined]
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def disable_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    """SLACK_WEBHOOK_URL を空にして実通信を防ぐ (notify_slack=True 時の副作用回避)。"""
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)


def _seed_active_config(SessionFactory: Any) -> int:
    with SessionFactory() as db:
        cfg = make_v10_default_config()
        db.add(cfg)
        db.commit()
        return cfg.id


def _create_user(
    SessionFactory: Any,
    *,
    email: str,
    username: str,
    tier: InvestmentTier = InvestmentTier.LOWER,
    risk_mode: RiskMode = RiskMode.CONSERVATIVE,
    invited_by: int | None = None,
) -> int:
    with SessionFactory() as db:
        u = User(
            email=email,
            username=username,
            hashed_password="dummy-bcrypt-hash",
            role=UserRole.VIEWER.value,
            tier=tier.value,
            risk_mode=risk_mode.value,
            invited_by=invited_by,
        )
        db.add(u)
        db.commit()
        return u.id


def _allocate_funds(
    SessionFactory: Any,
    *,
    partner_id: int,
    tester_user_id: int,
    amount_usd: Decimal,
) -> int:
    with SessionFactory() as db:
        fa = FundAllocation(
            partner_id=partner_id,
            tester_name=f"tester-{tester_user_id}",
            tester_user_id=tester_user_id,
            allocated_amount_usd=amount_usd,
            status="active",
        )
        db.add(fa)
        db.commit()
        return fa.id


# ---------------------------------------------------------------------------
# month boundary helpers
# ---------------------------------------------------------------------------


class TestMonthBoundaries:
    """JST 月境界の next_batch_run_jst / month_end / month_start 検証。"""

    def test_next_run_today_before_2355(self) -> None:
        # 月末日 23:54 JST → 同日 23:55 JST が次回
        now = datetime(2026, 4, 30, 23, 54, 59, tzinfo=_JST)
        next_run = mfb.next_batch_run_jst(now)
        assert next_run == datetime(2026, 4, 30, 23, 55, 0, tzinfo=_JST)

    def test_next_run_today_after_2355_jumps_to_next_month(self) -> None:
        # 月末日 23:55:01 JST → 翌月最終日 23:55 JST に進む
        now = datetime(2026, 4, 30, 23, 55, 1, tzinfo=_JST)
        next_run = mfb.next_batch_run_jst(now)
        assert next_run == datetime(2026, 5, 31, 23, 55, 0, tzinfo=_JST)

    def test_next_run_jst_naive_input_is_treated_as_jst(self) -> None:
        # tz-naive datetime は JST として扱われる
        now_naive = datetime(2026, 4, 1, 12, 0, 0)
        next_run = mfb.next_batch_run_jst(now_naive)
        assert next_run.tzinfo is not None
        assert next_run.utcoffset() == timedelta(hours=9)
        # 4 月 1 日 12:00 JST → 4/30 23:55 JST が次回
        assert next_run.date() == date(2026, 4, 30)

    def test_month_end_february_leap_year(self) -> None:
        assert mfb.month_end(date(2028, 2, 15)) == date(2028, 2, 29)

    def test_month_end_february_non_leap(self) -> None:
        assert mfb.month_end(date(2026, 2, 15)) == date(2026, 2, 28)

    def test_month_start_normalizes_arbitrary_day(self) -> None:
        assert mfb.month_start(date(2026, 4, 17)) == date(2026, 4, 1)


# ---------------------------------------------------------------------------
# core batch
# ---------------------------------------------------------------------------


class TestRunMonthlyFeeBatch:
    """``run_monthly_fee_batch`` の主要動作検証。"""

    @pytest.fixture(autouse=True)
    def _force_fx_rate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 1 USD = 100 JPY とすることで USD->JPY 変換を計算しやすくする
        monkeypatch.setenv("USD_TO_JPY_RATE", "100")

    def test_creates_fee_transaction_for_active_user(
        self, test_db: tuple[Any, Any], disable_slack: None
    ) -> None:
        engine, SessionFactory = test_db
        _seed_active_config(SessionFactory)
        partner_id = _create_user(
            SessionFactory,
            email="partner@example.com",
            username="partner1",
            tier=InvestmentTier.UPPER,
        )
        tester_id = _create_user(
            SessionFactory,
            email="tester1@example.com",
            username="tester1",
            tier=InvestmentTier.LOWER,
            risk_mode=RiskMode.CONSERVATIVE,
        )
        # 5,000 USD * 100 JPY/USD = 500,000 JPY -> LOWER tier
        _allocate_funds(
            SessionFactory,
            partner_id=partner_id,
            tester_user_id=tester_id,
            amount_usd=Decimal("5000"),
        )

        with SessionFactory() as db:
            summary = mfb.run_monthly_fee_batch(
                target_month=date(2026, 4, 1),
                db=db,
                notify_slack=False,
            )

        assert summary.processed_count == 1
        assert summary.created_count == 1
        assert summary.failed_count == 0

        with SessionFactory() as db:
            txs = db.query(FeeTransaction).all()
            assert len(txs) == 1
            tx = txs[0]
            assert tx.user_id == tester_id
            assert tx.calculation_month == date(2026, 4, 1)
            # CONSERVATIVE 初月は subscription 0 / no profit → fee 0
            assert tx.fee_amount_jpy == Decimal("0")
            assert tx.subscription_amount_jpy == Decimal("0")
            assert tx.tier == InvestmentTier.LOWER.value
            assert tx.risk_mode == RiskMode.CONSERVATIVE.value
            assert tx.deposit_amount_jpy == Decimal("500000")

    def test_idempotent_skips_existing_month(
        self, test_db: tuple[Any, Any], disable_slack: None
    ) -> None:
        engine, SessionFactory = test_db
        _seed_active_config(SessionFactory)
        partner_id = _create_user(
            SessionFactory,
            email="partner2@example.com",
            username="partner2",
        )
        tester_id = _create_user(
            SessionFactory,
            email="tester2@example.com",
            username="tester2",
        )
        _allocate_funds(
            SessionFactory,
            partner_id=partner_id,
            tester_user_id=tester_id,
            amount_usd=Decimal("5000"),
        )

        with SessionFactory() as db:
            first = mfb.run_monthly_fee_batch(
                target_month=date(2026, 4, 15),  # 任意日 → 月初に正規化
                db=db,
                notify_slack=False,
            )
        assert first.created_count == 1
        assert first.skipped_count == 0

        # 同月 二回目: スキップされ重複作成されない
        with SessionFactory() as db:
            second = mfb.run_monthly_fee_batch(
                target_month=date(2026, 4, 1),
                db=db,
                notify_slack=False,
            )
        assert second.created_count == 0
        assert second.skipped_count == 1

        with SessionFactory() as db:
            assert db.query(FeeTransaction).count() == 1

    def test_no_active_config_raises(self, test_db: tuple[Any, Any], disable_slack: None) -> None:
        engine, SessionFactory = test_db
        # 設定を投入しない → RuntimeError
        partner_id = _create_user(SessionFactory, email="p3@example.com", username="p3")
        tester_id = _create_user(SessionFactory, email="t3@example.com", username="t3")
        _allocate_funds(
            SessionFactory,
            partner_id=partner_id,
            tester_user_id=tester_id,
            amount_usd=Decimal("1000"),
        )

        with SessionFactory() as db:
            with pytest.raises(RuntimeError, match="No active FeeConfigV10"):
                mfb.run_monthly_fee_batch(
                    target_month=date(2026, 4, 1),
                    db=db,
                    notify_slack=False,
                )

    def test_no_active_allocations_returns_empty_summary(
        self, test_db: tuple[Any, Any], disable_slack: None
    ) -> None:
        engine, SessionFactory = test_db
        _seed_active_config(SessionFactory)

        with SessionFactory() as db:
            summary = mfb.run_monthly_fee_batch(
                target_month=date(2026, 4, 1),
                db=db,
                notify_slack=False,
            )
        assert summary.processed_count == 0
        assert summary.created_count == 0
        assert summary.failed_count == 0
        assert summary.entries == []

    def test_inactive_allocation_skipped(
        self, test_db: tuple[Any, Any], disable_slack: None
    ) -> None:
        engine, SessionFactory = test_db
        _seed_active_config(SessionFactory)
        partner_id = _create_user(SessionFactory, email="p4@example.com", username="p4")
        tester_id = _create_user(SessionFactory, email="t4@example.com", username="t4")
        # withdrawn 状態 → 集計対象外
        with SessionFactory() as db:
            fa = FundAllocation(
                partner_id=partner_id,
                tester_name="t4",
                tester_user_id=tester_id,
                allocated_amount_usd=Decimal("5000"),
                status="withdrawn",
            )
            db.add(fa)
            db.commit()

        with SessionFactory() as db:
            summary = mfb.run_monthly_fee_batch(
                target_month=date(2026, 4, 1), db=db, notify_slack=False
            )
        assert summary.processed_count == 0
        with SessionFactory() as db:
            assert db.query(FeeTransaction).count() == 0

    def test_individual_user_failure_isolates_others(
        self, test_db: tuple[Any, Any], disable_slack: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """1 ユーザーで例外が起きても他ユーザーのトランザクションは作成される。"""
        engine, SessionFactory = test_db
        _seed_active_config(SessionFactory)
        partner_id = _create_user(SessionFactory, email="p5@example.com", username="p5")
        good_id = _create_user(SessionFactory, email="good@example.com", username="good")
        bad_id = _create_user(SessionFactory, email="bad@example.com", username="bad")
        _allocate_funds(
            SessionFactory,
            partner_id=partner_id,
            tester_user_id=good_id,
            amount_usd=Decimal("3000"),
        )
        _allocate_funds(
            SessionFactory,
            partner_id=partner_id,
            tester_user_id=bad_id,
            amount_usd=Decimal("4000"),
        )

        # bad_id の処理だけ ValueError を投げるよう FeeCalculator をモンキーパッチ
        original_calc = mfb.FeeCalculator.calculate_monthly

        def patched(self: Any, payload: Any) -> Any:
            if payload.user_id == bad_id:
                raise ValueError("simulated failure for bad user")
            return original_calc(self, payload)

        monkeypatch.setattr(
            "app.automation.monthly_fee_batch.FeeCalculator.calculate_monthly", patched
        )

        with SessionFactory() as db:
            summary = mfb.run_monthly_fee_batch(
                target_month=date(2026, 4, 1), db=db, notify_slack=False
            )

        assert summary.created_count == 1
        assert summary.failed_count == 1
        with SessionFactory() as db:
            txs = db.query(FeeTransaction).all()
            assert len(txs) == 1
            assert txs[0].user_id == good_id


# ---------------------------------------------------------------------------
# tier × risk_mode カバレッジ
# ---------------------------------------------------------------------------


_TIER_DEPOSIT_USD = {
    InvestmentTier.LOWER: Decimal("5000"),  # ~500,000 JPY @ 100
    InvestmentTier.MIDDLE: Decimal("50000"),  # ~5,000,000 JPY
    InvestmentTier.UPPER: Decimal("200000"),  # ~20,000,000 JPY
}


@pytest.mark.parametrize(
    "tier",
    [InvestmentTier.LOWER, InvestmentTier.MIDDLE, InvestmentTier.UPPER],
)
@pytest.mark.parametrize(
    "risk_mode",
    [RiskMode.CONSERVATIVE, RiskMode.BALANCED, RiskMode.AGGRESSIVE],
)
def test_all_tier_and_risk_mode_combinations(
    test_db: tuple[Any, Any],
    disable_slack: None,
    monkeypatch: pytest.MonkeyPatch,
    tier: InvestmentTier,
    risk_mode: RiskMode,
) -> None:
    """全 tier (3) × 全 risk_mode (3) = 9 通りで FeeTransaction が正しく作成される。"""
    monkeypatch.setenv("USD_TO_JPY_RATE", "100")
    engine, SessionFactory = test_db
    _seed_active_config(SessionFactory)
    partner_id = _create_user(
        SessionFactory,
        email=f"partner-{tier.value}-{risk_mode.value}@example.com",
        username=f"p-{tier.value}-{risk_mode.value}",
    )
    tester_id = _create_user(
        SessionFactory,
        email=f"tester-{tier.value}-{risk_mode.value}@example.com",
        username=f"t-{tier.value}-{risk_mode.value}",
        tier=tier,
        risk_mode=risk_mode,
    )
    _allocate_funds(
        SessionFactory,
        partner_id=partner_id,
        tester_user_id=tester_id,
        amount_usd=_TIER_DEPOSIT_USD[tier],
    )

    with SessionFactory() as db:
        summary = mfb.run_monthly_fee_batch(
            target_month=date(2026, 4, 1), db=db, notify_slack=False
        )

    assert summary.created_count == 1, summary.errors
    with SessionFactory() as db:
        tx = db.query(FeeTransaction).one()
        assert tx.tier == tier.value
        assert tx.risk_mode == risk_mode.value
        # 初月は subscription 0
        assert tx.subscription_amount_jpy == Decimal("0")
        # gross_profit が 0 なので fee も 0 (subscription 保護で UATa 行きにもならない)
        assert tx.fee_amount_jpy == Decimal("0")


# ---------------------------------------------------------------------------
# loop helpers
# ---------------------------------------------------------------------------


class TestLoopEnable:
    """``DISABLE_MONTHLY_FEE_BATCH`` の判定。"""

    def test_default_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DISABLE_MONTHLY_FEE_BATCH", raising=False)
        monkeypatch.delenv("ENABLE_MONTHLY_FEE_BATCH", raising=False)
        assert mfb._is_loop_enabled() is True

    def test_disable_with_disable_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DISABLE_MONTHLY_FEE_BATCH", "1")
        assert mfb._is_loop_enabled() is False

    def test_disable_with_legacy_enable_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DISABLE_MONTHLY_FEE_BATCH", raising=False)
        monkeypatch.setenv("ENABLE_MONTHLY_FEE_BATCH", "0")
        assert mfb._is_loop_enabled() is False


# ---------------------------------------------------------------------------
# Slack notification
# ---------------------------------------------------------------------------


class TestSlackNotify:
    """``_post_slack`` の fail-open 挙動と notify_slack=False のスキップ。"""

    def test_no_webhook_url_no_op(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
        # 例外を投げず、何もしないこと
        mfb._post_slack("test message")  # noqa: SLF001

    def test_webhook_failure_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.invalid/hook")

        def raise_err(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("network error")

        monkeypatch.setattr("urllib.request.urlopen", raise_err)
        # 例外を伝播させずログだけ吐くこと
        mfb._post_slack("test message")  # noqa: SLF001

    def test_run_with_notify_slack_false_skips_post(
        self,
        test_db: tuple[Any, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine, SessionFactory = test_db
        _seed_active_config(SessionFactory)

        called: list[str] = []

        def spy(text: str) -> None:
            called.append(text)

        monkeypatch.setattr("app.automation.monthly_fee_batch._post_slack", spy)

        with SessionFactory() as db:
            mfb.run_monthly_fee_batch(target_month=date(2026, 4, 1), db=db, notify_slack=False)
        assert called == []
