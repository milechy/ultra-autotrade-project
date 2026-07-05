# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/api/v1/fees.py
"""F-8a: v10 fees API endpoints (read-only 中心 + simulate)。

旧 ``/api/billing/*`` (billing/router.py) と ``/api/fees/calculate|schedule``
(aave/fee_router.py) は **本タスクでは無変更**。F-8b で廃止 + フロント差し替え予定。

新規 endpoints:
- GET  /api/v1/fees/config              認証済み: 現行 active fee_config 取得
- GET  /api/v1/fees/my-summary          自分のみ: 累計手数料サマリ
- GET  /api/v1/fees/my-history          自分のみ: 月別履歴 (最新 N 件)
- POST /api/v1/fees/simulate            認証済み: F-5 calculator 直呼び (DB 書込なし)
- GET  /api/v1/fees/affiliate-earnings  自分のみ: アフィリエイト報酬履歴
- GET  /api/v1/fees/all-users           admin: 全ユーザー手数料一覧
- POST /api/v1/fees/finalize-month      admin: 501 (F-7 で本実装)
- GET  /api/v1/fees/uata-income         admin: UATa 収入集計

設計:
- プロジェクトは sync (SessionLocal) のため、async ではなく sync handler を使用
- Decimal は Pydantic で str に直列化 (フロントは ``Number(str).toFixed()`` で受ける、
  CLAUDE.md "Decimal型 → Number() ラップ" メモリ準拠)
- Pydantic レスポンスは Pydantic v2 の ``model_config = ConfigDict(from_attributes=True)``

関連:
- F-5 ``app.fees.calculator`` (純粋関数エンジン)
- F-1 ``app.billing.v10_models`` (FeeConfigV10 / FeeTransaction)
- F-3 ``app.auth.models`` (RiskMode / InvestmentTier)
- docs/45_fee_model_v10_migration_plan.md §4 F-8 行
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user, require_admin
from app.auth.models import InvestmentTier, RiskMode, User
from app.database import get_db
from app.fees import FeeCalculationInput, FeeCalculator
from app.fees.billing_adapter import BillingVendorAdapter, ChargeRequest
from app.fees.fee_transfer_service import (
    FeeTransferConfig,
    FeeTransferService,
    is_fee_transfer_enabled,
)
from app.fees.models import FeeConfigV10, FeeTransaction, ReferralCampaign, UatWalletLedger
from app.portfolio.models import PortfolioSnapshot
from app.transactions.models import Transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fees", tags=["fees-v10"])

# ===== current month 起点 =====
_FIRST_DAY_OF_MONTH = 1


def _today_month_start() -> date:
    today = date.today()
    return today.replace(day=_FIRST_DAY_OF_MONTH)


# ===========================================================================
# Pydantic schemas
# ===========================================================================


class AllowanceInfoResponse(BaseModel):
    """fee aToken allowance 承認に必要な情報。フロントエンドが approve tx を構築するために使用。"""

    operator_address: str
    usdc_address: str
    data_provider_address: str
    chain_id: int
    recommended_allowance_usdc: str  # Decimal str (6 decimals), e.g. "10.000000"
    configured: bool  # OPERATOR_FEE_WALLET_ADDRESS が設定済みか


class FeeConfigResponse(BaseModel):
    """現行 active fee_config (v10_default 等)。"""

    config_name: str
    tier_thresholds_jpy: list[int]
    tier_fee_rates: list[float]
    tier_monthly_yield_caps: list[float]
    subscription_rates: dict[str, float]
    expense_markup_enabled: bool
    expense_markup_rate: str  # Decimal → str
    affiliate_rate: str
    is_active: bool
    effective_from: datetime


class FeeSummaryResponse(BaseModel):
    """ユーザー単位の累計サマリ。"""

    user_id: int
    total_fee_paid_jpy: str
    total_subscription_paid_jpy: str
    total_user_takehome_jpy: str
    total_yield_excess_to_uata_jpy: str
    months_count: int


class FeeHistoryItemResponse(BaseModel):
    """月次履歴の 1 行。"""

    model_config = ConfigDict(from_attributes=False)

    calculation_month: date
    tier: str
    risk_mode: str
    deposit_jpy: str
    net_profit_jpy: str
    fee_amount_jpy: str
    subscription_amount_jpy: str
    user_takehome_jpy: str
    finalized_at: datetime | None = None


class AffiliateEarningItemResponse(BaseModel):
    """アフィリエイト報酬の 1 行 (自分が affiliate_id として記録された月)。"""

    calculation_month: date
    invitee_user_id: int
    invitee_subscription_amount_jpy: str
    affiliate_amount_jpy: str
    finalized_at: datetime | None = None


class AllUsersFeeItemResponse(BaseModel):
    """admin 用全ユーザー手数料一覧の 1 行。"""

    user_id: int
    calculation_month: date
    tier: str
    risk_mode: str
    deposit_jpy: str
    net_profit_jpy: str
    fee_amount_jpy: str
    subscription_amount_jpy: str
    user_takehome_jpy: str
    affiliate_id: int | None
    affiliate_amount_jpy: str
    finalized_at: datetime | None


class SimulateRequest(BaseModel):
    """v10 計算シミュレーション入力。DB 書込なし。"""

    deposit_jpy: Decimal = Field(ge=0)
    gross_profit_jpy: Decimal
    expense_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    user_tier: InvestmentTier
    user_risk_mode: RiskMode
    is_first_month: bool = False
    affiliate_id: int | None = None


class SimulateResponse(BaseModel):
    """``FeeCalculationResult`` の API 露出版 (Decimal → str)。"""

    raw_expense_jpy: str  # 実費 (マークアップ前, F-9)
    expense_markup_rate_applied: str  # 適用マークアップ率 (0 なら無効, F-9)
    expense_markup_amount_jpy: str  # マークアップ加算分 (F-9)
    net_profit_jpy: str
    fee_rate_applied: str
    fee_amount_jpy: str
    subscription_rate_applied: str
    subscription_amount_jpy: str
    subscription_protected: bool
    monthly_yield_cap_applied: str
    yield_excess_to_uata_jpy: str
    user_takehome_jpy: str
    affiliate_amount_jpy: str


class UataIncomeResponse(BaseModel):
    """admin 用 UATa 収入集計レスポンス。"""

    month_from: date
    month_to: date
    subscription_total: str
    fee_total: str
    yield_excess_total: str
    affiliate_payout_total: str
    uata_income_total: str  # subscription + fee + yield_excess - affiliate


class FinalizeMonthResponse(BaseModel):
    """月次 finalize バッチの実行結果サマリ (F-7 + F-S6)。"""

    calculation_month: date
    usd_jpy_rate: str
    dry_run: bool
    users_processed: int
    users_skipped_no_snapshot: int
    users_skipped_already_finalized: int
    total_fee_jpy: str
    total_subscription_jpy: str
    total_user_takehome_jpy: str
    # F-S6: on-chain transfer 統計
    fee_transfer_enabled: bool = False
    transfer_sent: int = 0
    transfer_skipped: int = 0
    transfer_failed: int = 0
    #: vendor adapter 経由で課金を試みたユーザー数 (subscription_amount > 0)
    vendor_charges_attempted: int = 0
    #: vendor adapter が success=True を返したユーザー数
    vendor_charges_succeeded: int = 0


# ===========================================================================
# Helpers
# ===========================================================================


def _get_active_fee_config(db: Session = Depends(get_db)) -> FeeConfigV10:
    """現行 active な FeeConfigV10 を返す。なければ 503。"""
    stmt = (
        select(FeeConfigV10)
        .where(FeeConfigV10.is_active.is_(True))
        .order_by(FeeConfigV10.effective_from.desc())
        .limit(1)
    )
    config = db.execute(stmt).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fee config not initialized. Run scripts/seed_fee_config_v10.py.",
        )
    return config


def _decimal_str(value: Decimal | int | float | None) -> str:
    """Decimal/None を str に直列化 (None → '0')。"""
    if value is None:
        return "0"
    return str(value if isinstance(value, Decimal) else Decimal(str(value)))


def _next_month_start(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _get_active_campaign_partner_id(db: Session, referree_id: int, month: date) -> int | None:
    """指定月に有効な紹介キャンペーン ウィンドウのパートナー ID を返す。

    有効条件:
        reward_start_month <= month <= reward_expires_month
        AND (ended_early_month IS NULL OR ended_early_month >= month)
    """
    from sqlalchemy import or_

    campaign = db.scalar(
        select(ReferralCampaign).where(
            ReferralCampaign.referree_id == referree_id,
            ReferralCampaign.reward_start_month <= month,
            ReferralCampaign.reward_expires_month >= month,
            or_(
                ReferralCampaign.ended_early_month.is_(None),
                ReferralCampaign.ended_early_month >= month,
            ),
        )
    )
    return campaign.partner_id if campaign else None


def finalize_month_core(
    db: Session,
    config: FeeConfigV10,
    month_start: date,
    usd_jpy_rate: Decimal,
    *,
    dry_run: bool = False,
    vendor_adapter: BillingVendorAdapter | None = None,
) -> FinalizeMonthResponse:
    """月次手数料バッチのコアロジック (API endpoint / 定期実行タスク 共通)。

    各ユーザーの portfolio_snapshots から月次損益を算出し、
    FeeCalculator で手数料を計算して fee_transactions に書き込む。
    dry_run=True の場合は計算のみ行い DB 書込はしない。
    expense_jpy は当月の完了トレード件数 × TRADE_FIXED_COST_USD × usd_jpy_rate で算出 (F-9)。

    vendor_adapter が指定された場合、サブスク課金額 > 0 かつ subscription_protected=False の
    ユーザーに対して charge_subscription() を呼び出す (課金ベンダー差込点)。
    dry_run=True のとき vendor_adapter は呼ばれない。
    """
    next_month = _next_month_start(month_start)
    dt_from = datetime(month_start.year, month_start.month, 1, tzinfo=timezone.utc)
    dt_to = datetime(next_month.year, next_month.month, 1, tzinfo=timezone.utc)

    calculator = FeeCalculator(config)
    active_users = db.execute(select(User).where(User.is_active.is_(True))).scalars().all()

    processed = 0
    skipped_no_snapshot = 0
    skipped_finalized = 0
    total_fee = Decimal("0")
    total_sub = Decimal("0")
    total_takehome = Decimal("0")
    vendor_charges_attempted = 0
    vendor_charges_succeeded = 0

    for user in active_users:
        first_snap = db.scalar(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.user_id == user.id)
            .where(PortfolioSnapshot.recorded_at >= dt_from)
            .where(PortfolioSnapshot.recorded_at < dt_to)
            .order_by(PortfolioSnapshot.recorded_at.asc())
            .limit(1)
        )
        if first_snap is None:
            skipped_no_snapshot += 1
            continue

        last_snap = db.scalar(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.user_id == user.id)
            .where(PortfolioSnapshot.recorded_at >= dt_from)
            .where(PortfolioSnapshot.recorded_at < dt_to)
            .order_by(PortfolioSnapshot.recorded_at.desc())
            .limit(1)
        )
        assert last_snap is not None  # noqa: S101

        existing = db.scalar(
            select(FeeTransaction)
            .where(FeeTransaction.user_id == user.id)
            .where(FeeTransaction.calculation_month == month_start)
        )
        if existing is not None and existing.finalized_at is not None:
            skipped_finalized += 1
            continue

        deposit_jpy = (last_snap.total_supply_usd * usd_jpy_rate).quantize(Decimal("1"))
        gross_profit_jpy = (
            (last_snap.total_supply_usd - first_snap.total_supply_usd) * usd_jpy_rate
        ).quantize(Decimal("1"))

        user_tier = InvestmentTier(user.tier) if user.tier else InvestmentTier.LOWER
        user_risk_mode = RiskMode(user.risk_mode) if user.risk_mode else RiskMode.CONSERVATIVE

        user_created_date = user.created_at.date() if user.created_at else None
        is_first_month = (
            user_created_date is not None and month_start <= user_created_date < next_month
        )

        fixed_cost_usd = Decimal(os.getenv("TRADE_FIXED_COST_USD", "0.27"))
        trade_count = (
            db.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.user_id == user.id,
                    Transaction.status == "completed",
                    Transaction.is_dry_run.is_(False),
                    Transaction.created_at >= dt_from,
                    Transaction.created_at < dt_to,
                )
            )
            or 0
        )
        expense_jpy = (fixed_cost_usd * trade_count * usd_jpy_rate).quantize(Decimal("1"))

        campaign_partner_id = _get_active_campaign_partner_id(db, user.id, month_start)

        payload = FeeCalculationInput(
            user_id=user.id,
            calculation_month=month_start,
            deposit_jpy=deposit_jpy,
            gross_profit_jpy=gross_profit_jpy,
            expense_jpy=expense_jpy,
            user_tier=user_tier,
            user_risk_mode=user_risk_mode,
            affiliate_id=campaign_partner_id,
            is_first_month=is_first_month,
        )

        result = calculator.calculate_monthly(payload)

        if not dry_run:
            if existing is None:
                db.add(
                    FeeTransaction(
                        user_id=result.user_id,
                        calculation_month=result.calculation_month,
                        tier=result.tier,
                        risk_mode=result.risk_mode,
                        deposit_amount_jpy=result.deposit_jpy,
                        gross_profit_jpy=result.gross_profit_jpy,
                        expense_jpy=result.expense_jpy,
                        net_profit_jpy=result.net_profit_jpy,
                        fee_rate_applied=result.fee_rate_applied,
                        fee_amount_jpy=result.fee_amount_jpy,
                        subscription_rate_applied=result.subscription_rate_applied,
                        subscription_amount_jpy=result.subscription_amount_jpy,
                        subscription_protected=result.subscription_protected,
                        monthly_yield_cap_applied=result.monthly_yield_cap_applied,
                        yield_excess_to_uata_jpy=result.yield_excess_to_uata_jpy,
                        user_takehome_jpy=result.user_takehome_jpy,
                        affiliate_id=result.affiliate_id,
                        affiliate_amount_jpy=result.affiliate_amount_jpy,
                        usd_jpy_rate=usd_jpy_rate,
                    )
                )
            else:
                existing.tier = result.tier
                existing.risk_mode = result.risk_mode
                existing.deposit_amount_jpy = result.deposit_jpy
                existing.gross_profit_jpy = result.gross_profit_jpy
                existing.expense_jpy = result.expense_jpy
                existing.net_profit_jpy = result.net_profit_jpy
                existing.fee_rate_applied = result.fee_rate_applied
                existing.fee_amount_jpy = result.fee_amount_jpy
                existing.subscription_rate_applied = result.subscription_rate_applied
                existing.subscription_amount_jpy = result.subscription_amount_jpy
                existing.subscription_protected = result.subscription_protected
                existing.monthly_yield_cap_applied = result.monthly_yield_cap_applied
                existing.yield_excess_to_uata_jpy = result.yield_excess_to_uata_jpy
                existing.user_takehome_jpy = result.user_takehome_jpy
                existing.affiliate_id = result.affiliate_id
                existing.affiliate_amount_jpy = result.affiliate_amount_jpy
                existing.usd_jpy_rate = usd_jpy_rate

        total_fee += result.fee_amount_jpy
        total_sub += result.subscription_amount_jpy
        total_takehome += result.user_takehome_jpy
        processed += 1

    if not dry_run:
        db.commit()

        # --- UAT ウォレット台帳 記録 (冪等: 同月再実行でも重複しない) ---
        fee_txs_this_month = (
            db.execute(
                select(FeeTransaction).where(FeeTransaction.calculation_month == month_start)
            )
            .scalars()
            .all()
        )
        wallet_entries_added = 0
        for fee_tx in fee_txs_this_month:
            uat_income = (
                (fee_tx.subscription_amount_jpy or Decimal("0"))
                + (fee_tx.fee_amount_jpy or Decimal("0"))
                + (fee_tx.yield_excess_to_uata_jpy or Decimal("0"))
            )
            if uat_income > Decimal("0"):
                already = db.scalar(
                    select(UatWalletLedger).where(
                        UatWalletLedger.reference_fee_tx_id == fee_tx.id,
                        UatWalletLedger.entry_type == "credit",
                        UatWalletLedger.reason == "uat_monthly_income",
                    )
                )
                if already is None:
                    db.add(
                        UatWalletLedger(
                            entry_type="credit",
                            amount_jpy=uat_income,
                            reason="uat_monthly_income",
                            reference_fee_tx_id=fee_tx.id,
                            month=month_start,
                        )
                    )
                    wallet_entries_added += 1

            affiliate_amt = fee_tx.affiliate_amount_jpy or Decimal("0")
            if affiliate_amt > Decimal("0"):
                already_debit = db.scalar(
                    select(UatWalletLedger).where(
                        UatWalletLedger.reference_fee_tx_id == fee_tx.id,
                        UatWalletLedger.entry_type == "debit",
                        UatWalletLedger.reason == "referral_campaign",
                    )
                )
                if already_debit is None:
                    db.add(
                        UatWalletLedger(
                            entry_type="debit",
                            amount_jpy=affiliate_amt,
                            reason="referral_campaign",
                            reference_fee_tx_id=fee_tx.id,
                            month=month_start,
                        )
                    )
                    wallet_entries_added += 1

        if wallet_entries_added:
            db.commit()
            logger.info(
                "uat_wallet_ledger: month=%s entries_added=%d",
                month_start,
                wallet_entries_added,
            )

        # --- 課金ベンダー差込点 (vendor_adapter が指定された場合のみ実行) ---
        # subscription_amount_jpy > 0 かつ subscription_protected=False のユーザーに対し
        # サブスク課金を実行する。DB への vendor_reference_id 書込後に再 commit。
        if vendor_adapter is not None:
            written_ids: list[int] = []
            stmt_uncharged = select(FeeTransaction).where(
                FeeTransaction.calculation_month == month_start,
                FeeTransaction.subscription_amount_jpy > Decimal("0"),
                FeeTransaction.subscription_protected.is_(False),
                FeeTransaction.vendor_reference_id.is_(None),
            )
            pending_txs = db.execute(stmt_uncharged).scalars().all()
            for fee_tx in pending_txs:
                vendor_charges_attempted += 1
                try:
                    charge_req = ChargeRequest(
                        user_id=fee_tx.user_id,
                        fee_transaction_id=fee_tx.id,
                        subscription_amount_jpy=Decimal(str(fee_tx.subscription_amount_jpy)),
                        calculation_month=fee_tx.calculation_month,
                        description=f"サブスク月額 {fee_tx.calculation_month}",
                    )
                    charge_res = vendor_adapter.charge_subscription(charge_req)
                    if charge_res.success:
                        fee_tx.vendor_reference_id = charge_res.vendor_reference_id
                        fee_tx.charged_at = datetime.now(timezone.utc)
                        vendor_charges_succeeded += 1
                        written_ids.append(fee_tx.id)
                    else:
                        logger.warning(
                            "vendor charge failed: user_id=%d fee_tx_id=%d err=%s",
                            fee_tx.user_id,
                            fee_tx.id,
                            charge_res.error_message,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "vendor charge exception: user_id=%d fee_tx_id=%d exc=%s",
                        fee_tx.user_id,
                        fee_tx.id,
                        exc,
                    )
            if written_ids:
                db.commit()
                logger.info(
                    "finalize_month vendor charges: month=%s attempted=%d succeeded=%d ids=%s",
                    month_start,
                    vendor_charges_attempted,
                    vendor_charges_succeeded,
                    written_ids,
                )

    logger.info(
        "finalize_month: month=%s processed=%d skipped_no_snap=%d skipped_finalized=%d"
        " total_fee=%s vendor_charges=%d/%d dry_run=%s",
        month_start,
        processed,
        skipped_no_snapshot,
        skipped_finalized,
        total_fee,
        vendor_charges_succeeded,
        vendor_charges_attempted,
        dry_run,
    )

    # --- F-S6: on-chain fee transfer (FEE_TRANSFER_ENABLED=true の場合のみ) ---
    # FEE_TRANSFER_ENABLED=false (default) → DB 記録のみ、送金しない (現状維持)
    # FEE_TRANSFER_ENABLED=true  → operator wallet が aToken.transferFrom を実行
    # non-custodial §14a: operator wallet は自身の鍵 (OPERATOR_FEE_WALLET_KEY) を使用。
    # ユーザーの秘密鍵は不要。ユーザーが事前に aToken の allowance を operator に付与。
    transfer_sent = 0
    transfer_skipped = 0
    transfer_failed = 0
    fee_transfer_enabled = is_fee_transfer_enabled()

    if not dry_run and fee_transfer_enabled:
        transfer_cfg = FeeTransferConfig.from_env()
        if not transfer_cfg.operator_wallet_address or not transfer_cfg.operator_wallet_key:
            # fail-fast: FEE_TRANSFER_ENABLED=true だが operator wallet 未設定。
            # このまま loop に入ると全 fee_tx が transfer_status="failed" で汚染される
            # (fee_transfer_service.transfer_fee が per-user で "failed" を返すため)。
            # phase 全体をスキップし、per-user の失敗 N 行を 1 本の明示 ERROR に集約する。
            logger.error(
                "fee_transfer phase skipped: FEE_TRANSFER_ENABLED=true だが "
                "OPERATOR_FEE_WALLET_ADDRESS / OPERATOR_FEE_WALLET_KEY が未設定 (month=%s)",
                month_start,
            )
        else:
            transfer_svc = FeeTransferService(transfer_cfg)

            fee_txs_to_transfer = (
                db.execute(
                    select(FeeTransaction).where(
                        FeeTransaction.calculation_month == month_start,
                        FeeTransaction.finalized_at.is_(None),
                        FeeTransaction.transfer_status.is_(None),
                    )
                )
                .scalars()
                .all()
            )

            for fee_tx in fee_txs_to_transfer:
                fee_user = db.get(User, fee_tx.user_id)
                user_wallet = fee_user.wallet_address if fee_user else None
                t_result = transfer_svc.transfer_fee(
                    user_id=fee_tx.user_id,
                    user_wallet=user_wallet or "",
                    fee_amount_jpy=fee_tx.fee_amount_jpy or Decimal("0"),
                    subscription_amount_jpy=fee_tx.subscription_amount_jpy or Decimal("0"),
                    yield_excess_jpy=fee_tx.yield_excess_to_uata_jpy or Decimal("0"),
                    usd_jpy_rate=usd_jpy_rate,
                )
                fee_tx.transfer_status = t_result.status
                fee_tx.transfer_tx_hash = t_result.tx_hash
                if t_result.status == "sent":
                    fee_tx.finalized_at = datetime.now(timezone.utc)
                    transfer_sent += 1
                    logger.info(
                        "fee_transfer sent: user_id=%d tx=%s fee_usd=%s",
                        fee_tx.user_id,
                        t_result.tx_hash,
                        t_result.fee_usd,
                    )
                elif t_result.status in ("skipped", "low_fee"):
                    transfer_skipped += 1
                else:
                    transfer_failed += 1
                    logger.warning(
                        "fee_transfer %s: user_id=%d error=%s",
                        t_result.status,
                        fee_tx.user_id,
                        t_result.error,
                    )

            db.commit()
            logger.info(
                "fee_transfer phase done: sent=%d skipped=%d failed=%d",
                transfer_sent,
                transfer_skipped,
                transfer_failed,
            )

    return FinalizeMonthResponse(
        calculation_month=month_start,
        usd_jpy_rate=str(usd_jpy_rate),
        dry_run=dry_run,
        users_processed=processed,
        users_skipped_no_snapshot=skipped_no_snapshot,
        users_skipped_already_finalized=skipped_finalized,
        total_fee_jpy=str(total_fee),
        total_subscription_jpy=str(total_sub),
        total_user_takehome_jpy=str(total_takehome),
        fee_transfer_enabled=fee_transfer_enabled,
        transfer_sent=transfer_sent,
        transfer_skipped=transfer_skipped,
        transfer_failed=transfer_failed,
        vendor_charges_attempted=vendor_charges_attempted,
        vendor_charges_succeeded=vendor_charges_succeeded,
    )


# ===========================================================================
# Endpoints
# ===========================================================================


@router.get("/config", response_model=FeeConfigResponse, summary="現行 active fee_config 取得")
def get_fee_config(
    _user: User = Depends(require_active_user),
    config: FeeConfigV10 = Depends(_get_active_fee_config),
) -> FeeConfigResponse:
    return FeeConfigResponse(
        config_name=config.config_name,
        tier_thresholds_jpy=list(config.tier_thresholds_jpy),
        tier_fee_rates=[float(r) for r in config.tier_fee_rates],
        tier_monthly_yield_caps=[float(c) for c in config.tier_monthly_yield_caps],
        subscription_rates={k: float(v) for k, v in config.subscription_rates.items()},
        expense_markup_enabled=config.expense_markup_enabled,
        expense_markup_rate=_decimal_str(config.expense_markup_rate),
        affiliate_rate=_decimal_str(config.affiliate_rate),
        is_active=config.is_active,
        effective_from=config.effective_from,
    )


@router.get(
    "/my-summary",
    response_model=FeeSummaryResponse,
    summary="自分の累計手数料サマリ",
)
def get_my_fee_summary(
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> FeeSummaryResponse:
    stmt = select(
        func.count(FeeTransaction.id).label("months_count"),
        func.coalesce(func.sum(FeeTransaction.fee_amount_jpy), 0).label("total_fee"),
        func.coalesce(func.sum(FeeTransaction.subscription_amount_jpy), 0).label("total_sub"),
        func.coalesce(func.sum(FeeTransaction.user_takehome_jpy), 0).label("total_takehome"),
        func.coalesce(func.sum(FeeTransaction.yield_excess_to_uata_jpy), 0).label("total_excess"),
    ).where(FeeTransaction.user_id == user.id)
    row = db.execute(stmt).one()
    return FeeSummaryResponse(
        user_id=user.id,
        total_fee_paid_jpy=_decimal_str(row.total_fee),
        total_subscription_paid_jpy=_decimal_str(row.total_sub),
        total_user_takehome_jpy=_decimal_str(row.total_takehome),
        total_yield_excess_to_uata_jpy=_decimal_str(row.total_excess),
        months_count=int(row.months_count or 0),
    )


@router.get(
    "/my-history",
    response_model=list[FeeHistoryItemResponse],
    summary="自分の月別履歴 (最新 N 件)",
)
def get_my_fee_history(
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=24, ge=1, le=120),
) -> list[FeeHistoryItemResponse]:
    stmt = (
        select(FeeTransaction)
        .where(FeeTransaction.user_id == user.id)
        .order_by(FeeTransaction.calculation_month.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        FeeHistoryItemResponse(
            calculation_month=r.calculation_month,
            tier=r.tier,
            risk_mode=r.risk_mode,
            deposit_jpy=_decimal_str(r.deposit_amount_jpy),
            net_profit_jpy=_decimal_str(r.net_profit_jpy),
            fee_amount_jpy=_decimal_str(r.fee_amount_jpy),
            subscription_amount_jpy=_decimal_str(r.subscription_amount_jpy),
            user_takehome_jpy=_decimal_str(r.user_takehome_jpy),
            finalized_at=r.finalized_at,
        )
        for r in rows
    ]


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    summary="v10 計算シミュレーション (DB 書込なし)",
)
def simulate_fee(
    payload: SimulateRequest,
    user: User = Depends(require_active_user),
    config: FeeConfigV10 = Depends(_get_active_fee_config),
) -> SimulateResponse:
    calculator = FeeCalculator(config)
    result = calculator.calculate_monthly(
        FeeCalculationInput(
            user_id=user.id,
            calculation_month=_today_month_start(),
            deposit_jpy=payload.deposit_jpy,
            gross_profit_jpy=payload.gross_profit_jpy,
            expense_jpy=payload.expense_jpy,
            user_tier=payload.user_tier,
            user_risk_mode=payload.user_risk_mode,
            affiliate_id=payload.affiliate_id,
            is_first_month=payload.is_first_month,
        )
    )
    return SimulateResponse(
        raw_expense_jpy=_decimal_str(result.raw_expense_jpy),
        expense_markup_rate_applied=_decimal_str(result.expense_markup_rate_applied),
        expense_markup_amount_jpy=_decimal_str(result.expense_markup_amount_jpy),
        net_profit_jpy=_decimal_str(result.net_profit_jpy),
        fee_rate_applied=_decimal_str(result.fee_rate_applied),
        fee_amount_jpy=_decimal_str(result.fee_amount_jpy),
        subscription_rate_applied=_decimal_str(result.subscription_rate_applied),
        subscription_amount_jpy=_decimal_str(result.subscription_amount_jpy),
        subscription_protected=result.subscription_protected,
        monthly_yield_cap_applied=_decimal_str(result.monthly_yield_cap_applied),
        yield_excess_to_uata_jpy=_decimal_str(result.yield_excess_to_uata_jpy),
        user_takehome_jpy=_decimal_str(result.user_takehome_jpy),
        affiliate_amount_jpy=_decimal_str(result.affiliate_amount_jpy),
    )


@router.get(
    "/affiliate-earnings",
    response_model=list[AffiliateEarningItemResponse],
    summary="自分が招待者として記録された月別 affiliate 報酬",
)
def get_my_affiliate_earnings(
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=24, ge=1, le=120),
) -> list[AffiliateEarningItemResponse]:
    stmt = (
        select(FeeTransaction)
        .where(FeeTransaction.affiliate_id == user.id)
        .order_by(FeeTransaction.calculation_month.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        AffiliateEarningItemResponse(
            calculation_month=r.calculation_month,
            invitee_user_id=r.user_id,
            invitee_subscription_amount_jpy=_decimal_str(r.subscription_amount_jpy),
            affiliate_amount_jpy=_decimal_str(r.affiliate_amount_jpy),
            finalized_at=r.finalized_at,
        )
        for r in rows
    ]


@router.get(
    "/all-users",
    response_model=list[AllUsersFeeItemResponse],
    summary="全ユーザー手数料一覧 (admin)",
    dependencies=[Depends(require_admin)],
)
def list_all_users_fees(
    db: Session = Depends(get_db),
    month: date | None = Query(
        default=None,
        description="YYYY-MM-DD (月初日)。省略時は今月。",
    ),
) -> list[AllUsersFeeItemResponse]:
    target_month = month or _today_month_start()
    stmt = (
        select(FeeTransaction)
        .where(FeeTransaction.calculation_month == target_month)
        .order_by(FeeTransaction.user_id)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        AllUsersFeeItemResponse(
            user_id=r.user_id,
            calculation_month=r.calculation_month,
            tier=r.tier,
            risk_mode=r.risk_mode,
            deposit_jpy=_decimal_str(r.deposit_amount_jpy),
            net_profit_jpy=_decimal_str(r.net_profit_jpy),
            fee_amount_jpy=_decimal_str(r.fee_amount_jpy),
            subscription_amount_jpy=_decimal_str(r.subscription_amount_jpy),
            user_takehome_jpy=_decimal_str(r.user_takehome_jpy),
            affiliate_id=r.affiliate_id,
            affiliate_amount_jpy=_decimal_str(r.affiliate_amount_jpy),
            finalized_at=r.finalized_at,
        )
        for r in rows
    ]


@router.post(
    "/finalize-month",
    response_model=FinalizeMonthResponse,
    summary="月次 finalize バッチ実行 (F-7 / Asana 1214120401388139)",
    dependencies=[Depends(require_admin)],
)
def finalize_month(
    month: date,
    usd_jpy_rate: Decimal = Query(
        default=Decimal("150"),
        gt=0,
        description="USD/JPY 換算レート (デフォルト 150)",
    ),
    dry_run: bool = Query(
        default=False,
        description="True の場合は計算のみ行い DB 書込をしない",
    ),
    db: Session = Depends(get_db),
    config: FeeConfigV10 = Depends(_get_active_fee_config),
) -> FinalizeMonthResponse:
    """各ユーザーの portfolio_snapshots から月次損益を算出し fee_transactions に書き込む。

    - month: 対象月の月初日 (例: 2026-05-01)
    - usd_jpy_rate: 計算に使う USD/JPY レート (省略時 150)
    - dry_run: True の場合は DB 書込なしで結果のみ返す
    - expense_jpy: 当月の完了トレード件数 × TRADE_FIXED_COST_USD × usd_jpy_rate (F-9)
    """
    return finalize_month_core(db, config, month.replace(day=1), usd_jpy_rate, dry_run=dry_run)


@router.get(
    "/uata-income",
    response_model=UataIncomeResponse,
    summary="UATa 収入集計 (admin)",
    dependencies=[Depends(require_admin)],
)
def get_uata_income(
    db: Session = Depends(get_db),
    month_from: date = Query(..., description="開始月初日 (inclusive)"),
    month_to: date = Query(..., description="終了月初日 (inclusive)"),
) -> UataIncomeResponse:
    if month_from > month_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month_from must be <= month_to",
        )
    stmt = select(
        func.coalesce(func.sum(FeeTransaction.subscription_amount_jpy), 0).label("subscription"),
        func.coalesce(func.sum(FeeTransaction.fee_amount_jpy), 0).label("fee"),
        func.coalesce(func.sum(FeeTransaction.yield_excess_to_uata_jpy), 0).label("yield_excess"),
        func.coalesce(func.sum(FeeTransaction.affiliate_amount_jpy), 0).label("affiliate"),
    ).where(
        FeeTransaction.calculation_month >= month_from,
        FeeTransaction.calculation_month <= month_to,
    )
    row = db.execute(stmt).one()
    sub_d = Decimal(str(row.subscription))
    fee_d = Decimal(str(row.fee))
    excess_d = Decimal(str(row.yield_excess))
    aff_d = Decimal(str(row.affiliate))
    uata = sub_d + fee_d + excess_d - aff_d
    return UataIncomeResponse(
        month_from=month_from,
        month_to=month_to,
        subscription_total=_decimal_str(sub_d),
        fee_total=_decimal_str(fee_d),
        yield_excess_total=_decimal_str(excess_d),
        affiliate_payout_total=_decimal_str(aff_d),
        uata_income_total=_decimal_str(uata),
    )


@router.get(
    "/allowance-info",
    response_model=AllowanceInfoResponse,
    summary="fee aToken allowance 承認情報 (authenticated user)",
)
def get_allowance_info(
    _user: User = Depends(require_active_user),
) -> AllowanceInfoResponse:
    """フロントエンドが aToken.approve(operator, amount) を構築するための情報を返す。

    - operator_address: OPERATOR_FEE_WALLET_ADDRESS env var から取得
    - usdc_address / data_provider_address: チェーン設定から取得
    - recommended_allowance_usdc: 上限付き approve を推奨 (MaxUint256 禁止)
      デフォルト 10 USDC (月額手数料の余裕を持つ上限)
    - configured: operator アドレスが環境変数に設定されているか
    """
    from app.aave.chains import get_active_chains  # noqa: PLC0415

    operator_address = os.getenv("OPERATOR_FEE_WALLET_ADDRESS", "")

    active_chains = get_active_chains()
    chain = active_chains[0] if active_chains else None
    if chain is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="chain configuration unavailable",
        )

    usdc_address = chain.tokens.get("USDC", "")
    data_provider = chain.data_provider_address or ""

    # 上限付き approve 推奨額 (MaxUint256 禁止): 10 USDC
    # 月額手数料の見積もりに余裕を持たせる。不足時はユーザーが再承認可能。
    recommended = Decimal("10.000000")

    return AllowanceInfoResponse(
        operator_address=operator_address,
        usdc_address=usdc_address,
        data_provider_address=data_provider,
        chain_id=chain.chain_id,
        recommended_allowance_usdc=str(recommended),
        configured=bool(operator_address),
    )
