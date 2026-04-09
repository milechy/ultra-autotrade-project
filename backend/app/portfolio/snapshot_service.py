# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/portfolio/snapshot_service.py
"""ポートフォリオスナップショット定期保存サービス。

スケジュールタスクから呼ばれ、Aave ポートフォリオデータを
PortfolioSnapshot / PortfolioHistory テーブルに記録する。
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.aave.client import get_default_aave_client
from app.auth.models import User
from app.database import SessionLocal
from app.partner.allocation_models import FundAllocation
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot

logger = logging.getLogger(__name__)


def _normalize_hf(hf: Decimal) -> Optional[Decimal]:
    """Infinity の HF を None に変換する（DB 格納用）。"""
    try:
        if not hf.is_finite():
            return None
    except Exception:
        return None
    return hf


def _save_snapshot(
    db: Session,
    user_id: int,
    total_supply: Decimal,
    total_debt: Decimal,
    net_worth: Decimal,
    health_factor: Optional[Decimal],
    recorded_at: datetime,
) -> None:
    """PortfolioSnapshot を DB に追加する。"""
    db.add(
        PortfolioSnapshot(
            user_id=user_id,
            total_value_usd=net_worth,
            total_supply_usd=total_supply,
            total_borrow_usd=total_debt,
            health_factor=health_factor,
            recorded_at=recorded_at,
        )
    )


def _upsert_daily_history(
    db: Session,
    user_id: int,
    net_worth: Decimal,
    health_factor: Optional[Decimal],
    now: datetime,
) -> None:
    """日次 PortfolioHistory を作成または更新する。

    - 当日レコードなし → open = close = current で新規作成
    - 当日レコードあり → close / high / low / pnl を更新
    """
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    existing = (
        db.query(PortfolioHistory)
        .filter(
            PortfolioHistory.user_id == user_id,
            PortfolioHistory.period_type == "daily",
            PortfolioHistory.period_start >= today_start,
            PortfolioHistory.period_start < tomorrow_start,
        )
        .first()
    )

    if existing is None:
        db.add(
            PortfolioHistory(
                user_id=user_id,
                period_type="daily",
                period_start=today_start,
                period_end=tomorrow_start,
                open_value_usd=net_worth,
                close_value_usd=net_worth,
                high_value_usd=net_worth,
                low_value_usd=net_worth,
                pnl_usd=Decimal("0"),
                pnl_pct=Decimal("0"),
                avg_health_factor=health_factor,
                snapshot_count=1,
            )
        )
    else:
        open_val = Decimal(str(existing.open_value_usd))
        existing.close_value_usd = net_worth
        existing.high_value_usd = max(Decimal(str(existing.high_value_usd)), net_worth)
        existing.low_value_usd = min(Decimal(str(existing.low_value_usd)), net_worth)
        existing.pnl_usd = (net_worth - open_val).quantize(Decimal("0.000001"))
        if open_val > Decimal("0"):
            existing.pnl_pct = ((net_worth - open_val) / open_val * Decimal("100")).quantize(
                Decimal("0.0001")
            )
        existing.avg_health_factor = health_factor
        existing.snapshot_count = (existing.snapshot_count or 0) + 1


def record_portfolio_snapshot(db: Optional[Session] = None) -> dict[str, Any]:
    """Aaveポートフォリオスナップショットを記録する（スケジュールタスク用）。

    処理フロー:
    1. Aave get_account_data() でポートフォリオ取得
    2. FundAllocation 比率に基づき、パートナーが招待したテスターに按分して
       PortfolioSnapshot を保存
    3. テスターが存在しない場合は管理者ユーザーに全体スナップショットを保存
    4. 日次 PortfolioHistory を作成または更新

    Aave 接続エラー時はログのみで早期リターン（fail-open）。

    Returns:
        dict: {"snapshots_created": int, "total_supply_usd": str, ...}
    """
    _own_session = db is None
    if _own_session:
        db = SessionLocal()
    if db is None:
        raise RuntimeError("db is None after SessionLocal()")

    now = datetime.now(timezone.utc)
    snapshots_created = 0

    try:
        # --- Aaveデータ取得（失敗時はスキップ） ---
        wallet_address = os.getenv("AAVE_WALLET_ADDRESS", "")
        try:
            client = get_default_aave_client()
            account_data = client.get_account_data(wallet_address)
        except Exception as exc:
            logger.warning("portfolio_snapshot: Aave get_account_data failed, skipping: %s", exc)
            return {"snapshots_created": 0, "skipped": True, "reason": str(exc)}

        total_supply = Decimal(str(account_data.total_collateral_usd))
        total_debt = Decimal(str(account_data.total_debt_usd))
        net_worth = total_supply - total_debt
        hf = _normalize_hf(Decimal(str(account_data.health_factor)))

        # --- グローバルFundAllocation合計（比率計算用） ---
        global_allocated_raw = (
            db.query(func.sum(FundAllocation.allocated_amount_usd))
            .filter(FundAllocation.status == "active")
            .scalar()
        )
        global_total = Decimal(str(global_allocated_raw)) if global_allocated_raw else Decimal("0")

        # --- パートナーごとにテスターへ按分して保存 ---
        partner_rows = (
            db.query(User.invited_by)
            .filter(User.invited_by.isnot(None), User.is_active == True)  # noqa: E712
            .distinct()
            .all()
        )
        n_partners = len(partner_rows) or 1

        for (partner_id,) in partner_rows:
            testers = (
                db.query(User)
                .filter(User.invited_by == partner_id, User.is_active == True)  # noqa: E712
                .all()
            )
            if not testers:
                continue

            # このパートナーのアクティブFundAllocation合計
            partner_allocated_raw = (
                db.query(func.sum(FundAllocation.allocated_amount_usd))
                .filter(
                    FundAllocation.partner_id == partner_id,
                    FundAllocation.status == "active",
                )
                .scalar()
            )
            partner_allocated = (
                Decimal(str(partner_allocated_raw)) if partner_allocated_raw else Decimal("0")
            )

            # パートナーの全体比率（FundAllocationがない場合はパートナー数で均等割り）
            if global_total > Decimal("0") and partner_allocated > Decimal("0"):
                partner_ratio = partner_allocated / global_total
            else:
                partner_ratio = Decimal("1") / Decimal(str(n_partners))

            partner_supply = (total_supply * partner_ratio).quantize(Decimal("0.000001"))
            partner_debt = (total_debt * partner_ratio).quantize(Decimal("0.000001"))

            # テスターに均等按分
            n_testers = Decimal(str(len(testers)))
            tester_supply = (partner_supply / n_testers).quantize(Decimal("0.000001"))
            tester_debt = (partner_debt / n_testers).quantize(Decimal("0.000001"))
            tester_net = tester_supply - tester_debt

            for tester in testers:
                _save_snapshot(db, tester.id, tester_supply, tester_debt, tester_net, hf, now)
                _upsert_daily_history(db, tester.id, tester_net, hf, now)
                snapshots_created += 1

        # --- テスターが誰もいない場合は管理者ユーザーに全体スナップショットを保存 ---
        if snapshots_created == 0:
            admin = (
                db.query(User)
                .filter(User.role == "admin", User.is_active == True)  # noqa: E712
                .first()
            )
            if admin is not None:
                _save_snapshot(db, admin.id, total_supply, total_debt, net_worth, hf, now)
                _upsert_daily_history(db, admin.id, net_worth, hf, now)
                snapshots_created += 1

        db.commit()
        logger.info(
            "portfolio_snapshot completed: snapshots_created=%d, total_supply=%s, health_factor=%s",
            snapshots_created,
            total_supply,
            hf,
        )
        return {
            "snapshots_created": snapshots_created,
            "total_supply_usd": str(total_supply),
            "total_debt_usd": str(total_debt),
            "health_factor": str(hf) if hf is not None else None,
        }

    except Exception as exc:
        logger.error("portfolio_snapshot failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        if _own_session:
            db.close()
