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


def _get_wallet_address(user: User) -> str:
    """ユーザー（partner / admin）の Aave ウォレットアドレスを取得する。

    users.wallet_address が設定されていれば優先、なければ
    AAVE_WALLET_ADDRESS 環境変数にフォールバックする。

    app.partner.allocation_service._get_wallet_address と同一セマンティクス。
    """
    if user.wallet_address:
        return user.wallet_address
    return os.getenv("AAVE_WALLET_ADDRESS", "")


def _self_directed_wallet(user: User) -> str:
    """セルフディレクト（非カストディアル消費者）ユーザー自身の運用ウォレットを返す。

    v4 の委譲運用では資金は各ユーザーの Smart Wallet (ERC-4337) に置かれるため、
    `smart_wallet_address` を優先し、無ければ EOA `wallet_address` にフォールバックする。
    **env `AAVE_WALLET_ADDRESS` へのフォールバックは決して行わない**
    （partner ループと同様、他人／運用者のウォレット残高を当該ユーザーの残高として
    記録してしまう #996 型の混線を防ぐ）。どちらも無ければ空文字を返す。
    """
    return user.smart_wallet_address or user.wallet_address or ""


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

    処理フロー（wallet_address 伝播版 / Lane 14）:
    1. パートナーごとに `_get_wallet_address(partner)` で対象ウォレットを決定
       (users.wallet_address 優先 / 未設定なら AAVE_WALLET_ADDRESS env)
    2. パートナー単位で Aave get_account_data() を取得
    3. パートナーが招待したテスターに均等按分して PortfolioSnapshot を保存
    4. テスターが存在しないパートナーはスキップ
    5. 招待関係のテスターが 1 件も無い場合は管理者ユーザーに
       admin.wallet_address ベースのスナップショットを保存（fallback）
    6. 日次 PortfolioHistory を作成または更新

    各パートナーの Aave 接続エラーはログのみで当該パートナーをスキップ（fail-open）。

    Returns:
        dict: {"snapshots_created": int, "partners_processed": int, ...}
    """
    _own_session = db is None
    if _own_session:
        db = SessionLocal()
    if db is None:
        raise RuntimeError("db is None after SessionLocal()")

    now = datetime.now(timezone.utc)
    snapshots_created = 0
    partners_processed = 0
    partners_skipped = 0
    last_total_supply: Optional[Decimal] = None
    last_total_debt: Optional[Decimal] = None
    last_hf: Optional[Decimal] = None

    try:
        try:
            client = get_default_aave_client()
        except Exception as exc:
            logger.warning("portfolio_snapshot: Aave client init failed, skipping: %s", exc)
            return {"snapshots_created": 0, "skipped": True, "reason": str(exc)}

        # --- パートナーごとに対象テスターを持つ partner_id を列挙 ---
        partner_rows = (
            db.query(User.invited_by)
            .filter(User.invited_by.isnot(None), User.is_active == True)  # noqa: E712
            .distinct()
            .all()
        )

        for (partner_id,) in partner_rows:
            partner = db.query(User).filter(User.id == partner_id).first()
            if partner is None:
                continue

            testers = (
                db.query(User)
                .filter(User.invited_by == partner_id, User.is_active == True)  # noqa: E712
                .all()
            )
            if not testers:
                continue

            # NULL wallet ガード: partner は wallet_address 明示設定のみ使用。
            # env AAVE_WALLET_ADDRESS へのフォールバックは partner ウォレット汚染防止のため禁止。
            wallet_addr = partner.wallet_address or ""
            if not wallet_addr:
                logger.warning(
                    "portfolio_snapshot: partner_id=%d has no wallet_address; skipping"
                    " (env fallback disabled for partner loop)",
                    partner_id,
                )
                partners_skipped += 1
                continue

            try:
                account_data = client.get_account_data(wallet_addr)
            except Exception as exc:
                logger.warning(
                    "portfolio_snapshot: Aave get_account_data failed for"
                    " partner_id=%d (wallet=%s...): %s",
                    partner_id,
                    wallet_addr[:10] if wallet_addr else "<empty>",
                    exc,
                )
                partners_skipped += 1
                continue

            partner_supply = Decimal(str(account_data.total_collateral_usd))
            partner_debt = Decimal(str(account_data.total_debt_usd))
            partner_hf = _normalize_hf(Decimal(str(account_data.health_factor)))

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

            partners_processed += 1
            last_total_supply = partner_supply
            last_total_debt = partner_debt
            last_hf = partner_hf
            logger.info(
                "portfolio_snapshot: partner_id=%d processed, testers=%d,"
                " supply=%s, debt=%s, hf=%s",
                partner_id,
                len(testers),
                partner_supply,
                partner_debt,
                partner_hf,
            )

        # --- セルフディレクト（非カストディアル消費者）ユーザー: 各自のウォレット残高を記録 ---
        # 背景 (2026-07-23): 従来の snapshot は「partner が招待したテスターに按分」する旧モデル
        # 専用で、v4 の LIFF から自己登録した消費者（role=viewer / invited_by IS NULL / 自分の
        # Smart Wallet を持つ）はどの経路にも乗らず snapshot が 1 行も作られなかった。結果、
        # 「運用残高 / 平均利回り」が実データでは永久に空になっていた。ここで各ユーザー自身の
        # ウォレットを読んで per-user snapshot を作る。partner ループ対象（invited_by あり）とは
        # 排他なので二重計上しない。
        self_directed = (
            db.query(User)
            .filter(
                User.invited_by.is_(None),
                User.is_active == True,  # noqa: E712
                User.role == "viewer",
            )
            .all()
        )
        for user in self_directed:
            wallet_addr = _self_directed_wallet(user)
            if not wallet_addr:
                # ウォレット未設定のユーザーは env フォールバックせずスキップ（残高混線防止）。
                continue
            try:
                account_data = client.get_account_data(wallet_addr)
                u_supply = Decimal(str(account_data.total_collateral_usd))
                u_debt = Decimal(str(account_data.total_debt_usd))
                u_hf = _normalize_hf(Decimal(str(account_data.health_factor)))
            except Exception as exc:
                # get_account_data の失敗も Decimal 変換の失敗も当該ユーザーのみ skip し、
                # 既に作成済みの他ユーザー snapshot（partner 分含む）を巻き添え rollback しない。
                logger.warning(
                    "portfolio_snapshot: get_account_data failed for user_id=%d (wallet=%s...): %s",
                    user.id,
                    wallet_addr[:10],
                    exc,
                )
                continue
            u_net = u_supply - u_debt

            # ゼロ残高（Aave ポジション無し）の無限行増殖ガード:
            # ウォレット紐付けだけ済ませて一度も供給していない消費者は毎 tick 全ゼロ行を
            # 生むため、現在ゼロ かつ 直近 snapshot も実質ゼロ なら記録しない。
            # 資金→ゼロ（全額出金）の遷移だけは 1 行残す（直近が非ゼロなら書く）。
            if u_supply == 0 and u_debt == 0:
                last = (
                    db.query(PortfolioSnapshot)
                    .filter(PortfolioSnapshot.user_id == user.id)
                    .order_by(PortfolioSnapshot.recorded_at.desc())
                    .first()
                )
                if last is None or (
                    Decimal(str(last.total_supply_usd)) == 0
                    and Decimal(str(last.total_borrow_usd)) == 0
                ):
                    continue

            _save_snapshot(db, user.id, u_supply, u_debt, u_net, u_hf, now)
            _upsert_daily_history(db, user.id, u_net, u_hf, now)
            snapshots_created += 1
            last_total_supply = u_supply
            last_total_debt = u_debt
            last_hf = u_hf

        # --- 招待関係下のテスターが居ない場合: 管理者ユーザーに admin.wallet_address ベースで保存 ---
        if snapshots_created == 0 and partners_skipped == 0:
            admin = (
                db.query(User)
                .filter(User.role == "admin", User.is_active == True)  # noqa: E712
                .first()
            )
            if admin is not None:
                admin_wallet = _get_wallet_address(admin)
                if not admin_wallet:
                    logger.warning(
                        "portfolio_snapshot: admin has no wallet_address and"
                        " AAVE_WALLET_ADDRESS is unset; skipping"
                    )
                else:
                    try:
                        account_data = client.get_account_data(admin_wallet)
                    except Exception as exc:
                        logger.warning(
                            "portfolio_snapshot: Aave get_account_data failed for admin: %s",
                            exc,
                        )
                        return {"snapshots_created": 0, "skipped": True, "reason": str(exc)}
                    admin_supply = Decimal(str(account_data.total_collateral_usd))
                    admin_debt = Decimal(str(account_data.total_debt_usd))
                    admin_net = admin_supply - admin_debt
                    admin_hf = _normalize_hf(Decimal(str(account_data.health_factor)))
                    _save_snapshot(db, admin.id, admin_supply, admin_debt, admin_net, admin_hf, now)
                    _upsert_daily_history(db, admin.id, admin_net, admin_hf, now)
                    snapshots_created += 1
                    last_total_supply = admin_supply
                    last_total_debt = admin_debt
                    last_hf = admin_hf

        db.commit()
        logger.info(
            "portfolio_snapshot completed: snapshots_created=%d,"
            " partners_processed=%d, partners_skipped=%d",
            snapshots_created,
            partners_processed,
            partners_skipped,
        )
        return {
            "snapshots_created": snapshots_created,
            "partners_processed": partners_processed,
            "partners_skipped": partners_skipped,
            "total_supply_usd": str(last_total_supply) if last_total_supply is not None else None,
            "total_debt_usd": str(last_total_debt) if last_total_debt is not None else None,
            "health_factor": str(last_hf) if last_hf is not None else None,
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
