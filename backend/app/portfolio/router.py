# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/portfolio/router.py
"""ポートフォリオ履歴API ルーター定義。"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import InvestmentTier, User, normalize_tier
from app.database import get_db
from app.fees.models import FeeConfigV10

from .aggregation import aggregate_portfolio
from .aggregation_schemas import SourceBalance, UnifiedPortfolioInput, UnifiedPortfolioView
from .models import PortfolioSnapshot
from .schemas import (
    PortfolioCurrentResponse,
    PortfolioHistoryResponse,
    PortfolioLiveResponse,
    PortfolioSnapshotCreate,
    PortfolioSnapshotResponse,
)

logger = logging.getLogger(__name__)

# 30秒インメモリキャッシュ: {cache_key: (timestamp, data)}
_live_cache: dict[str, tuple[float, PortfolioLiveResponse]] = {}
_CACHE_TTL_SECONDS = 30

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioLiveResponse, summary="ライブAaveポートフォリオデータ")
def get_live_portfolio(
    chain: str = Query(
        default="arbitrum_sepolia", description="チェーン名 (arbitrum_sepolia など)"
    ),
    current_user: User = Depends(require_viewer),
) -> PortfolioLiveResponse:
    """Aave getUserAccountData() をリアルタイム取得して返す（30秒キャッシュ）。"""
    from app.aave.client import get_default_aave_client  # noqa: PLC0415

    cache_key = chain
    now_ts = time.monotonic()
    cached = _live_cache.get(cache_key)
    if cached is not None:
        ts, data = cached
        if now_ts - ts < _CACHE_TTL_SECONDS:
            return data

    wallet_address = os.getenv("AAVE_WALLET_ADDRESS", "")

    try:
        client = get_default_aave_client()
        account_data = client.get_account_data(wallet_address)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Aaveデータの取得に失敗しました: {exc}",
        ) from exc

    hf = account_data.health_factor
    hf_result: Optional[Decimal] = None if hf == Decimal("inf") or str(hf) == "Infinity" else hf

    response = PortfolioLiveResponse(
        total_supply_usd=account_data.total_collateral_usd,
        total_borrow_usd=account_data.total_debt_usd,
        health_factor=hf_result,
        net_worth_usd=account_data.total_collateral_usd - account_data.total_debt_usd,
        positions=[],
        chain=chain,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )

    _live_cache[cache_key] = (now_ts, response)
    return response


def _calc_weighted_avg_apy(positions: Optional[list[Any]]) -> Decimal:
    """positions_json の apy_pct を value_usd で加重平均した APY (%) を返す。

    value_usd の合計が 0 (= ポジション無し) のときは "0.00"。
    金額計算は Decimal 型のみ (float 禁止)。
    """
    if not positions:
        return Decimal("0.00")
    total_value = sum((Decimal(str(p.get("value_usd", 0))) for p in positions), Decimal("0"))
    if total_value == Decimal("0"):
        return Decimal("0.00")
    weighted = sum(
        (
            Decimal(str(p.get("apy_pct", 0))) * Decimal(str(p.get("value_usd", 0)))
            for p in positions
        ),
        Decimal("0"),
    )
    return (weighted / total_value).quantize(Decimal("0.01"))


#: InvestmentTier → tier_monthly_yield_caps 配列の index。
#: app.fees.calculator._TIER_INDEX と同一セマンティクス。
_TIER_CAP_INDEX: dict[InvestmentTier, int] = {
    InvestmentTier.LOWER: 0,
    InvestmentTier.MIDDLE: 1,
    InvestmentTier.UPPER: 2,
}


def _cap_apy_for_display(raw_apy_pct: Decimal, user_tier: str, db: Session) -> Decimal:
    """表示用APYを、tier別月間利用上限 (tier_monthly_yield_caps) の年率換算値でクランプする。

    KPIの「平均利回り」がポジションの生APYをそのまま出すと、月次手数料バッチの
    monthly_yield_cap (超過分はUATaへ) 適用後の実際の手取りより大きく見え、
    ユーザーに不信感を与えうる。表示専用の安全策であり、料金計算そのものには
    影響しない (fail-open: アクティブな FeeConfig が無ければ raw をそのまま返す)。
    """
    config = db.scalars(
        select(FeeConfigV10)
        .where(FeeConfigV10.is_active.is_(True))
        .order_by(FeeConfigV10.effective_from.desc())
        .limit(1)
    ).first()
    if config is None:
        return raw_apy_pct
    idx = _TIER_CAP_INDEX.get(normalize_tier(user_tier), 0)
    caps = config.tier_monthly_yield_caps
    if idx >= len(caps):
        return raw_apy_pct
    annualized_cap_pct = Decimal(str(caps[idx])) * Decimal(12) * Decimal(100)
    return min(raw_apy_pct, annualized_cap_pct.quantize(Decimal("0.01")))


def _build_aave_source(wallet_address: str) -> Optional[SourceBalance]:
    """ユーザー wallet の Aave 純資産を SourceBalance にする（fail-open: 失敗時 None）。"""
    try:
        from app.aave.client import get_default_aave_client  # noqa: PLC0415

        data = get_default_aave_client().get_account_data(wallet_address)
        net = data.total_collateral_usd - data.total_debt_usd
        return SourceBalance(
            source="aave",
            total_usd=net,
            available=True,
            supply_usd=data.total_collateral_usd,
            borrow_usd=data.total_debt_usd,
            health_factor=data.health_factor,
        )
    except Exception:  # noqa: BLE001 — fail-open: 集約は欠落ソースを除外して継続
        logger.warning("unified portfolio: aave source fetch failed", exc_info=True)
        return None


async def _build_wallet_source(wallet_address: str) -> Optional[SourceBalance]:
    """ユーザー Privy wallet（Base ETH+USDC）残高を SourceBalance にする（fail-open）。"""
    try:
        from app.partner.wallet_balance_service import (
            fetch as fetch_wallet_balance,  # noqa: PLC0415
        )

        resp = await fetch_wallet_balance(wallet_address)
        # RPC フォールバック（balance=0）は available=False として grand_total から除外。
        return SourceBalance(
            source="wallet",
            total_usd=resp.total_usd,
            available=not resp.fallback_used,
        )
    except Exception:  # noqa: BLE001 — fail-open
        logger.warning("unified portfolio: wallet source fetch failed", exc_info=True)
        return None


@router.get(
    "/unified",
    response_model=UnifiedPortfolioView,
    summary="統合ポートフォリオ（消費者個人: Aave 純資産 + Privy Wallet 残高）",
)
async def get_unified_portfolio(
    current_user: User = Depends(require_viewer),
) -> UnifiedPortfolioView:
    """ログインユーザー個人の統合ポートフォリオを返す。

    対象は **自分の** Aave 純資産（自 wallet の getUserAccountData）と **自分の** Privy wallet
    残高（Base ETH+USDC）の 2 ソース。CEX(Bybit) は運用オペレータ口座のため対象外（cex=None）。
    各ソースは fail-open（取得失敗は None で除外し degraded=True で他ソースの表示を継続）。
    wallet 未設定ユーザーは全ソース欠落＝degraded な空ビュー（grand_total=0）。
    """
    wallet = current_user.smart_wallet_address or current_user.wallet_address or ""
    aave_src = _build_aave_source(wallet) if wallet else None
    wallet_src = await _build_wallet_source(wallet) if wallet else None
    return aggregate_portfolio(UnifiedPortfolioInput(aave=aave_src, wallet=wallet_src, cex=None))


def _get_since(period: str) -> Optional[datetime]:
    """期間文字列から開始datetimeを返す。"""
    now = datetime.now(timezone.utc)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "90d":
        return now - timedelta(days=90)
    return None  # "all"


@router.get("/current", response_model=PortfolioCurrentResponse, summary="現在のポートフォリオ")
def get_current_portfolio(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> PortfolioCurrentResponse:
    """最新のスナップショットを返す。データなし時は空レスポンス。"""
    stmt = (
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.user_id == current_user.id)
        .order_by(PortfolioSnapshot.recorded_at.desc())
        .limit(1)
    )
    snapshot = db.scalars(stmt).first()
    if snapshot is None:
        return PortfolioCurrentResponse(
            user_id=current_user.id,
            has_data=False,
            weighted_avg_apy=_cap_apy_for_display(
                _calc_weighted_avg_apy([]), current_user.tier, db
            ),
        )

    return PortfolioCurrentResponse(
        id=snapshot.id,
        user_id=snapshot.user_id,
        total_value_usd=snapshot.total_value_usd,
        total_supply_usd=snapshot.total_supply_usd,
        total_borrow_usd=snapshot.total_borrow_usd,
        health_factor=snapshot.health_factor,
        positions_json=snapshot.positions_json,
        recorded_at=snapshot.recorded_at,
        has_data=True,
        weighted_avg_apy=_cap_apy_for_display(
            _calc_weighted_avg_apy(snapshot.positions_json), current_user.tier, db
        ),
    )


@router.get("/history", response_model=PortfolioHistoryResponse, summary="資産推移履歴")
def get_portfolio_history(
    period: str = "30d",
    interval: str = "daily",
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> PortfolioHistoryResponse:
    """資産推移データを返す。period: 7d/30d/90d/all, interval: hourly/daily。"""
    if period not in ("7d", "30d", "90d", "all"):
        period = "30d"
    if interval not in ("hourly", "daily"):
        interval = "daily"
    since = _get_since(period)
    stmt = select(PortfolioSnapshot).where(PortfolioSnapshot.user_id == current_user.id)
    if since:
        stmt = stmt.where(PortfolioSnapshot.recorded_at >= since)
    stmt = stmt.order_by(PortfolioSnapshot.recorded_at.asc())
    items = db.scalars(stmt).all()
    return PortfolioHistoryResponse(
        items=[PortfolioSnapshotResponse.model_validate(s) for s in items],
        total=len(items),
        period=period,
        interval=interval,
    )


@router.post(
    "/snapshot",
    response_model=PortfolioSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="スナップショット記録",
)
def create_snapshot(
    request: PortfolioSnapshotCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortfolioSnapshotResponse:
    """ポートフォリオスナップショットを記録する（バッチジョブ用）。"""
    recorded_at = request.recorded_at or datetime.now(timezone.utc)
    snapshot = PortfolioSnapshot(
        user_id=request.user_id,
        total_value_usd=request.total_value_usd,
        total_supply_usd=request.total_supply_usd,
        total_borrow_usd=request.total_borrow_usd,
        health_factor=request.health_factor,
        positions_json=request.positions_json,
        recorded_at=recorded_at,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return PortfolioSnapshotResponse.model_validate(snapshot)
