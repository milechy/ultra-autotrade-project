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

from sqlalchemy.orm import Session

from app.aave.client import get_default_aave_client
from app.auth.models import User
from app.database import SessionLocal
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
    1. パートナーごとに user.wallet_address で Aave get_account_data() を呼び出す
    2. 各パートナーのテスターに均等按分して PortfolioSnapshot を保存
    3. テスターが存在しない場合は env AAVE_WALLET_ADDRESS を使って管理者に保存
    4. 日次 PortfolioHistory を作成または更新

    wallet_address が未設定のパートナーはスキップ（警告ログのみ）。

    Returns:
        dict: {"snapshots_created": int, ...}
    """
    _own_session = db is None
    if _own_session:
        db = SessionLocal()
    if db is None:
        raise RuntimeError("db is None after SessionLocal()")

    now = datetime.now(timezone.utc)
    snapshots_created = 0

    try:
        client = get_default_aave_client()

        # --- パートナーごとに wallet_address で Aave データを取得してテスターに保存 ---
        partner_rows = (
            db.query(User.invited_by)
            .filter(User.invited_by.isnot(None), User.is_active == True)  # noqa: E712
            .distinct()
            .all()
        )

        # 最後に取得したパートナーのデータ（ログ・fallback 用）
        _last_supply: Decimal = Decimal("0")
        _last_debt: Decimal = Decimal("0")
        _last_hf: Optional[Decimal] = None

        for (partner_id,) in partner_rows:
            testers = (
                db.query(User)
                .filter(User.invited_by == partner_id, User.is_active == True)  # noqa: E712
                .all()
            )
            if not testers:
                continue

            # partner の wallet_address を解決（未設定は env フォールバック）
            partner_user = db.get(User, partner_id)
            partner_wallet = (
                partner_user.wallet_address
                if partner_user and partner_user.wallet_address
                else None
            ) or os.getenv("AAVE_WALLET_ADDRESS", "")
            if not partner_wallet:
                logger.warning(
                    "portfolio_snapshot: partner %d has no wallet_address, skipping",
                    partner_id,
                )
                continue

            try:
                partner_data = client.get_account_data(partner_wallet)
            except Exception as exc:
                logger.warning(
                    "portfolio_snapshot: partner %d get_account_data failed: %s", partner_id, exc
                )
                return {"snapshots_created": 0, "skipped": True, "reason": str(exc)}

            partner_supply = Decimal(str(partner_data.total_collateral_usd))
            partner_debt = Decimal(str(partner_data.total_debt_usd))
            partner_hf = _normalize_hf(Decimal(str(partner_data.health_factor)))

            _last_supply = partner_supply
            _last_debt = partner_debt
            _last_hf = partner_hf

            # テスターに均等按分
            n_testers = Decimal(str(len(testers)))
            tester_supply = (partner_supply / n_testers).quantize(Decimal("0.000001"))
            tester_debt = (partner_debt / n_testers).quantize(Decimal("0.000001"))
            tester_net = tester_supply - tester_debt

            for tester in testers:
                _save_snapshot(
                    db, tester.id, tester_supply, tester_debt, tester_net, partner_hf, now
                )
                _upsert_daily_history(db, tester.id, tester_net, partner_hf, now)
                snapshots_created += 1

        # --- テスターが誰もいない場合は env wallet で管理者ユーザーに保存 ---
        if snapshots_created == 0:
            fallback_wallet = os.getenv("AAVE_WALLET_ADDRESS", "")
            try:
                fallback_data = client.get_account_data(fallback_wallet)
            except Exception as exc:
                logger.warning("portfolio_snapshot: admin fallback Aave failed, skipping: %s", exc)
                return {"snapshots_created": 0, "skipped": True, "reason": str(exc)}

            _last_supply = Decimal(str(fallback_data.total_collateral_usd))
            _last_debt = Decimal(str(fallback_data.total_debt_usd))
            fallback_net = _last_supply - _last_debt
            _last_hf = _normalize_hf(Decimal(str(fallback_data.health_factor)))

            admin = (
                db.query(User)
                .filter(User.role == "admin", User.is_active == True)  # noqa: E712
                .first()
            )
            if admin is not None:
                _save_snapshot(db, admin.id, _last_supply, _last_debt, fallback_net, _last_hf, now)
                _upsert_daily_history(db, admin.id, fallback_net, _last_hf, now)
                snapshots_created += 1

        db.commit()
        logger.info(
            "portfolio_snapshot completed: snapshots_created=%d, total_supply=%s, health_factor=%s",
            snapshots_created,
            _last_supply,
            _last_hf,
        )
        return {
            "snapshots_created": snapshots_created,
            "total_supply_usd": str(_last_supply),
            "total_debt_usd": str(_last_debt),
            "health_factor": str(_last_hf) if _last_hf is not None else None,
        }

    except Exception as exc:
        logger.error("portfolio_snapshot failed: %s", exc)
        try:
            db.rollback()
        except Exception as rollback_exc:  # noqa: BLE001
            logger.warning("rollback failed: %s", rollback_exc)
        raise
    finally:
        if _own_session:
            db.close()
