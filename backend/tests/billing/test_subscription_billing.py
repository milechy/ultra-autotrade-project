# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/billing/test_subscription_billing.py
"""サブスク定期請求エンジン統合テスト (F-7 vendor-agnostic adapter)。

テスト対象:
- ``StubBillingAdapter`` の動作検証
- ``finalize_month_core`` へ vendor_adapter を渡したときの課金フロー
- サブスク保護 (subscription_protected=True → 課金スキップ)
- 月次利回りキャップ超過 → UATa 振替
- dry_run=True → vendor adapter 不呼出
- vendor adapter エラー → ログのみ (fail-open)

DB は SQLite テスト DB (in-memory)。
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-billing")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "billing_test@example.com")

from app.auth.models import InvestmentTier, RiskMode, User  # noqa: E402
from app.database import Base  # noqa: E402
from app.fees.billing_adapter import (  # noqa: E402
    BillingVendorAdapter,
    ChargeRequest,
    ChargeResult,
    StubBillingAdapter,
)
from app.fees.models import FeeConfigV10, FeeTransaction  # noqa: E402
from app.portfolio.models import PortfolioSnapshot  # noqa: E402
from tests.helpers.fee_config_factory import make_v10_default_config  # noqa: E402

_JST = timezone(timedelta(hours=9))
_MONTH = date(2026, 5, 1)
_NEXT_MONTH = date(2026, 6, 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """In-memory SQLite DB。各テストで独立。"""
    fd, path = tempfile.mkstemp(suffix=".billing_test.db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def active_config(db: Session) -> FeeConfigV10:
    cfg = make_v10_default_config()
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def _add_user(
    db: Session,
    *,
    user_id: int = 1,
    risk_mode: str = "balanced",
    tier: str = "LOWER",
    created_days_before_month: int = 60,
) -> User:
    """テスト用アクティブユーザーを作成して返す。

    created_at は「計算対象月 (_MONTH) の N 日前」に固定する。
    実時刻 (now) 基準にすると、now が _MONTH の created_days 日後に達した時点で
    created_at が _MONTH 内に入り is_first_month=True に化け、初月サブスク=0 で
    テストが日付依存に落ちる (2026-06-30 に created_days_ago=60 で発火した時限バグ)。
    _MONTH 基準の固定にして「計算月より前に作成済み = 初月でない」を常に保証する。
    """
    u = User(
        id=user_id,
        email=f"user{user_id}@test.com",
        username=f"user{user_id}",
        hashed_password="x",
        is_active=True,
        risk_mode=risk_mode,
        tier=tier,
        created_at=datetime(_MONTH.year, _MONTH.month, 1, tzinfo=timezone.utc)
        - timedelta(days=created_days_before_month),
    )
    db.add(u)
    db.flush()
    return u


def _add_snapshots(
    db: Session,
    user_id: int,
    *,
    start_usd: Decimal,
    end_usd: Decimal,
) -> None:
    """月初 / 月末スナップショットを追加。"""
    dt_start = datetime(_MONTH.year, _MONTH.month, 1, tzinfo=timezone.utc)
    dt_end = datetime(_NEXT_MONTH.year, _NEXT_MONTH.month, 1, tzinfo=timezone.utc) - timedelta(
        seconds=1
    )
    db.add(
        PortfolioSnapshot(
            user_id=user_id,
            total_value_usd=start_usd,
            total_supply_usd=start_usd,
            total_borrow_usd=Decimal("0"),
            recorded_at=dt_start,
        )
    )
    db.add(
        PortfolioSnapshot(
            user_id=user_id,
            total_value_usd=end_usd,
            total_supply_usd=end_usd,
            total_borrow_usd=Decimal("0"),
            recorded_at=dt_end,
        )
    )
    db.flush()


# ---------------------------------------------------------------------------
# Unit tests: StubBillingAdapter
# ---------------------------------------------------------------------------


class TestStubBillingAdapter:
    def test_returns_success(self) -> None:
        adapter = StubBillingAdapter()
        req = ChargeRequest(
            user_id=1,
            fee_transaction_id=42,
            subscription_amount_jpy=Decimal("300"),
            calculation_month=_MONTH,
        )
        result = adapter.charge_subscription(req)
        assert result.success is True
        assert result.vendor_reference_id is not None
        assert "stub" in result.vendor_reference_id
        assert result.error_message is None

    def test_vendor_ref_contains_month_and_user(self) -> None:
        adapter = StubBillingAdapter()
        req = ChargeRequest(
            user_id=7,
            fee_transaction_id=99,
            subscription_amount_jpy=Decimal("1000"),
            calculation_month=date(2026, 5, 1),
        )
        result = adapter.charge_subscription(req)
        assert "2026-05-01" in (result.vendor_reference_id or "")
        assert "u7" in (result.vendor_reference_id or "")

    def test_protocol_conformance(self) -> None:
        """StubBillingAdapter は BillingVendorAdapter プロトコルを満たす。"""
        adapter = StubBillingAdapter()
        assert isinstance(adapter, BillingVendorAdapter)

    def test_zero_amount_still_succeeds(self) -> None:
        adapter = StubBillingAdapter()
        req = ChargeRequest(
            user_id=1,
            fee_transaction_id=1,
            subscription_amount_jpy=Decimal("0"),
            calculation_month=_MONTH,
        )
        result = adapter.charge_subscription(req)
        assert result.success is True


# ---------------------------------------------------------------------------
# Integration tests: finalize_month_core + vendor_adapter
# ---------------------------------------------------------------------------


class TestFinalizeMonthWithVendorAdapter:
    def _import_core(self):  # type: ignore[no-untyped-def]
        from app.api.v1.fees import finalize_month_core  # noqa: PLC0415

        return finalize_month_core

    def test_stub_adapter_charges_balanced_user(
        self, db: Session, active_config: FeeConfigV10
    ) -> None:
        """balanced (0.3%) ユーザーは subscription_amount > 0 → stub が呼ばれる。"""
        _add_user(db, user_id=1, risk_mode="balanced", tier="LOWER")
        _add_snapshots(db, 1, start_usd=Decimal("1000"), end_usd=Decimal("1020"))
        db.commit()

        finalize_month_core = self._import_core()
        stub = StubBillingAdapter()

        resp = finalize_month_core(db, active_config, _MONTH, Decimal("150"), vendor_adapter=stub)
        assert resp.users_processed == 1
        assert resp.vendor_charges_attempted == 1
        assert resp.vendor_charges_succeeded == 1

        fee_tx = db.scalar(select(FeeTransaction).where(FeeTransaction.user_id == 1))
        assert fee_tx is not None
        assert fee_tx.vendor_reference_id is not None
        assert "stub" in fee_tx.vendor_reference_id
        assert fee_tx.charged_at is not None

    def test_conservative_user_no_charge(self, db: Session, active_config: FeeConfigV10) -> None:
        """conservative (0%) ユーザーは subscription_rate=0 → 課金不要 (attempts=0)。"""
        _add_user(db, user_id=2, risk_mode="conservative", tier="LOWER")
        _add_snapshots(db, 2, start_usd=Decimal("1000"), end_usd=Decimal("1020"))
        db.commit()

        finalize_month_core = self._import_core()
        stub = StubBillingAdapter()

        resp = finalize_month_core(db, active_config, _MONTH, Decimal("150"), vendor_adapter=stub)
        assert resp.users_processed == 1
        assert resp.vendor_charges_attempted == 0
        assert resp.vendor_charges_succeeded == 0

        fee_tx = db.scalar(select(FeeTransaction).where(FeeTransaction.user_id == 2))
        assert fee_tx is not None
        assert fee_tx.vendor_reference_id is None

    def test_subscription_protected_skips_vendor_charge(
        self, db: Session, active_config: FeeConfigV10
    ) -> None:
        """サブスク保護発動 (net_profit < subscription) → subscription_protected=True → 課金スキップ。

        balanced 0.3%: deposit=1,500,000 JPY → subscription=4,500 JPY/月
        gross_profit_jpy=0 → net_profit=0 < 4,500 → サブスク保護発動
        subscription_amount_jpy は DB に 0 として保存される (Step 3 early-return)。
        vendor adapter は呼ばれない。
        """
        _add_user(db, user_id=3, risk_mode="balanced", tier="LOWER")
        deposit_usd = Decimal("10000")  # 150万円
        _add_snapshots(db, 3, start_usd=deposit_usd, end_usd=deposit_usd)
        db.commit()

        finalize_month_core = self._import_core()
        stub = StubBillingAdapter()

        resp = finalize_month_core(db, active_config, _MONTH, Decimal("150"), vendor_adapter=stub)
        assert resp.users_processed == 1
        assert resp.vendor_charges_attempted == 0

        fee_tx = db.scalar(select(FeeTransaction).where(FeeTransaction.user_id == 3))
        assert fee_tx is not None
        assert fee_tx.subscription_protected is True
        assert fee_tx.vendor_reference_id is None

    def test_dry_run_skips_vendor_adapter(self, db: Session, active_config: FeeConfigV10) -> None:
        """dry_run=True のとき vendor adapter は呼ばれない。"""
        _add_user(db, user_id=4, risk_mode="balanced", tier="LOWER")
        _add_snapshots(db, 4, start_usd=Decimal("1000"), end_usd=Decimal("1050"))
        db.commit()

        called: list[ChargeRequest] = []

        class SpyAdapter:
            def charge_subscription(self, req: ChargeRequest) -> ChargeResult:
                called.append(req)
                return ChargeResult(
                    user_id=req.user_id,
                    fee_transaction_id=req.fee_transaction_id,
                    success=True,
                    vendor_reference_id="spy-ref",
                )

        finalize_month_core = self._import_core()
        resp = finalize_month_core(
            db, active_config, _MONTH, Decimal("150"), dry_run=True, vendor_adapter=SpyAdapter()
        )
        assert resp.dry_run is True
        assert len(called) == 0

    def test_vendor_charge_error_does_not_abort_batch(
        self, db: Session, active_config: FeeConfigV10
    ) -> None:
        """vendor adapter が例外を投げてもバッチ全体は fail-open で続行する。"""
        _add_user(db, user_id=5, risk_mode="balanced", tier="LOWER")
        _add_snapshots(db, 5, start_usd=Decimal("1000"), end_usd=Decimal("1030"))
        db.commit()

        class FailingAdapter:
            def charge_subscription(self, req: ChargeRequest) -> ChargeResult:
                raise RuntimeError("vendor API timeout")

        finalize_month_core = self._import_core()
        # 例外が外に伝播しないことを確認
        resp = finalize_month_core(
            db,
            active_config,
            _MONTH,
            Decimal("150"),
            vendor_adapter=FailingAdapter(),
        )
        assert resp.users_processed == 1
        assert resp.vendor_charges_attempted == 1
        assert resp.vendor_charges_succeeded == 0

    def test_no_vendor_adapter_leaves_vendor_ref_null(
        self, db: Session, active_config: FeeConfigV10
    ) -> None:
        """vendor_adapter=None (デフォルト) のとき vendor_reference_id は NULL。"""
        _add_user(db, user_id=6, risk_mode="aggressive", tier="MIDDLE")
        _add_snapshots(db, 6, start_usd=Decimal("2000"), end_usd=Decimal("2100"))
        db.commit()

        finalize_month_core = self._import_core()
        resp = finalize_month_core(db, active_config, _MONTH, Decimal("150"))
        assert resp.vendor_charges_attempted == 0

        fee_tx = db.scalar(select(FeeTransaction).where(FeeTransaction.user_id == 6))
        assert fee_tx is not None
        assert fee_tx.vendor_reference_id is None


# ---------------------------------------------------------------------------
# Unit: subscription protection boundary
# ---------------------------------------------------------------------------


class TestSubscriptionProtectionBoundary:
    """サブスク保護の境界値テスト (pure calculator 経由)。"""

    def test_mid_risk_sub_rate_is_0_3pct(self) -> None:
        """balanced (ミドルリスク) の subscription_rate = 0.003 (0.3%/月)。"""
        from app.fees import FeeCalculationInput, FeeCalculator  # noqa: PLC0415

        cfg = make_v10_default_config()
        calc = FeeCalculator(cfg)
        result = calc.calculate_monthly(
            FeeCalculationInput(
                user_id=1,
                calculation_month=_MONTH,
                deposit_jpy=Decimal("1000000"),
                gross_profit_jpy=Decimal("5000"),
                expense_jpy=Decimal("0"),
                user_tier=InvestmentTier.LOWER,
                user_risk_mode=RiskMode.BALANCED,
            )
        )
        # subscription = 1,000,000 * 0.003 = 3,000 JPY
        assert result.subscription_rate_applied == Decimal("0.003")
        assert result.subscription_amount_jpy == Decimal("3000")
        assert result.subscription_protected is False

    def test_high_risk_sub_rate_is_1_0pct(self) -> None:
        """aggressive (ハイリスク) の subscription_rate = 0.01 (1.0%/月)。"""
        from app.fees import FeeCalculationInput, FeeCalculator  # noqa: PLC0415

        cfg = make_v10_default_config()
        calc = FeeCalculator(cfg)
        result = calc.calculate_monthly(
            FeeCalculationInput(
                user_id=2,
                calculation_month=_MONTH,
                deposit_jpy=Decimal("1000000"),
                gross_profit_jpy=Decimal("20000"),
                expense_jpy=Decimal("0"),
                user_tier=InvestmentTier.LOWER,
                user_risk_mode=RiskMode.AGGRESSIVE,
            )
        )
        # subscription = 1,000,000 * 0.01 = 10,000 JPY
        assert result.subscription_rate_applied == Decimal("0.01")
        assert result.subscription_amount_jpy == Decimal("10000")

    def test_protection_triggers_when_net_lt_subscription(self) -> None:
        """net_profit < subscription → subscription_protected=True、profit 全額 UATa。"""
        from app.fees import FeeCalculationInput, FeeCalculator  # noqa: PLC0415

        cfg = make_v10_default_config()
        calc = FeeCalculator(cfg)
        # deposit=1,000,000、balanced → sub=3,000。gross=2,000 → net=2,000 < 3,000
        result = calc.calculate_monthly(
            FeeCalculationInput(
                user_id=3,
                calculation_month=_MONTH,
                deposit_jpy=Decimal("1000000"),
                gross_profit_jpy=Decimal("2000"),
                expense_jpy=Decimal("0"),
                user_tier=InvestmentTier.LOWER,
                user_risk_mode=RiskMode.BALANCED,
            )
        )
        assert result.subscription_protected is True
        assert result.subscription_amount_jpy == Decimal("0")
        assert result.fee_amount_jpy == Decimal("0")
        assert result.user_takehome_jpy == Decimal("0")
        # net_profit 全額が UATa (yield_excess_to_uata)
        assert result.yield_excess_to_uata_jpy == Decimal("2000")

    def test_first_month_no_subscription(self) -> None:
        """初月 (is_first_month=True) はサブスク料金 0。"""
        from app.fees import FeeCalculationInput, FeeCalculator  # noqa: PLC0415

        cfg = make_v10_default_config()
        calc = FeeCalculator(cfg)
        result = calc.calculate_monthly(
            FeeCalculationInput(
                user_id=4,
                calculation_month=_MONTH,
                deposit_jpy=Decimal("1000000"),
                gross_profit_jpy=Decimal("5000"),
                expense_jpy=Decimal("0"),
                user_tier=InvestmentTier.LOWER,
                user_risk_mode=RiskMode.BALANCED,
                is_first_month=True,
            )
        )
        assert result.subscription_amount_jpy == Decimal("0")
        assert result.subscription_rate_applied == Decimal("0")

    def test_yield_cap_excess_to_uata(self) -> None:
        """月次利回りキャップ超過分は UATa に振替される。

        LOWER tier: cap=1.8%/月。deposit=1,000,000 → cap=18,000 JPY
        net_profit=20,000 (cap 超)、sub=0 (conservative) → provisional=20,000 > 18,000
        → yield_excess = 2,000 → UATa
        """
        from app.fees import FeeCalculationInput, FeeCalculator  # noqa: PLC0415

        cfg = make_v10_default_config()
        calc = FeeCalculator(cfg)
        result = calc.calculate_monthly(
            FeeCalculationInput(
                user_id=5,
                calculation_month=_MONTH,
                deposit_jpy=Decimal("1000000"),
                gross_profit_jpy=Decimal("20000"),
                expense_jpy=Decimal("0"),
                user_tier=InvestmentTier.LOWER,
                user_risk_mode=RiskMode.CONSERVATIVE,
            )
        )
        # conservative → sub=0, fee_rate=0.30
        # net=20,000, fee=floor(20,000*0.30)=6,000
        # provisional_takehome = 20,000 - 0 - 6,000 = 14,000
        # cap = 1,000,000 * 0.018 = 18,000 → 14,000 <= 18,000 → no excess
        assert result.yield_excess_to_uata_jpy == Decimal("0")

        # cap 超えケース: gross=50,000 → net=50,000, fee=15,000, provisional=35,000 > 18,000
        result2 = calc.calculate_monthly(
            FeeCalculationInput(
                user_id=5,
                calculation_month=_MONTH,
                deposit_jpy=Decimal("1000000"),
                gross_profit_jpy=Decimal("50000"),
                expense_jpy=Decimal("0"),
                user_tier=InvestmentTier.LOWER,
                user_risk_mode=RiskMode.CONSERVATIVE,
            )
        )
        assert result2.yield_excess_to_uata_jpy == Decimal("17000")  # 35,000 - 18,000
        assert result2.user_takehome_jpy == Decimal("18000")


# ---------------------------------------------------------------------------
# Integration tests: finalize_month_core on-chain transfer fail-fast guard
# ---------------------------------------------------------------------------


class TestFinalizeMonthTransferGuard:
    """FEE_TRANSFER_ENABLED=true だが operator wallet 未設定時の fail-fast guard 検証。

    設計A (fee_transfer_service) の on-chain transfer phase は、operator address/key が
    未設定のまま loop に入ると全 fee_tx が transfer_status="failed" で汚染される。
    guard により phase 全体をスキップし 1 本の ERROR ログに集約する (2026-07-05, 設計B削除と同PR)。
    """

    def _import_core(self):  # type: ignore[no-untyped-def]
        from app.api.v1.fees import finalize_month_core  # noqa: PLC0415

        return finalize_month_core

    def test_operator_unset_skips_transfer_phase(
        self,
        db: Session,
        active_config: FeeConfigV10,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("FEE_TRANSFER_ENABLED", "true")
        monkeypatch.delenv("OPERATOR_FEE_WALLET_ADDRESS", raising=False)
        monkeypatch.delenv("OPERATOR_FEE_WALLET_KEY", raising=False)

        # conservative + 利益ありで seed (sub=0 → 保護発動せず fee_tx が確実に生成される)。
        _add_user(db, user_id=1, risk_mode="conservative", tier="LOWER")
        _add_snapshots(db, 1, start_usd=Decimal("1000"), end_usd=Decimal("1050"))
        db.commit()

        finalize_month_core = self._import_core()
        with caplog.at_level(logging.ERROR, logger="app.api.v1.fees"):
            resp = finalize_month_core(db, active_config, _MONTH, Decimal("150"))

        # phase 全体スキップ: 送金統計はすべて 0 (per-user failed 汚染なし)。
        assert resp.fee_transfer_enabled is True
        assert resp.transfer_sent == 0
        assert resp.transfer_skipped == 0
        assert resp.transfer_failed == 0

        # fee_tx は生成されるが transfer_status は None のまま。
        fee_tx = db.scalar(select(FeeTransaction).where(FeeTransaction.user_id == 1))
        assert fee_tx is not None
        assert fee_tx.transfer_status is None

        # 1 本の明示 ERROR ログに集約されている。
        assert any("fee_transfer phase skipped" in rec.getMessage() for rec in caplog.records), (
            f"guard ERROR ログが見つからない: {[r.getMessage() for r in caplog.records]}"
        )
