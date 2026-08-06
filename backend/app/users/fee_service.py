# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/fee_service.py
"""
tier 別手数料率サービス。

v10 (F-2 2026-04-25 〜) からは DB `fee_configs` (app.fees.models.FeeConfigV10) の
active レコードを唯一の真実源とする。旧ハードコード値 (3〜10% / 8〜18% / 15〜25%) は
2026-08-06 に撤去 (Asana 1217210615751197) — `/api/v1/fees/config` (v10 正本) が
返す値と食い違い、課金有効化時に提示料率と請求額が一致しないリスクがあったため。

fee_configs に active レコードがない場合 (未投入 / 取得失敗) は None を返す。
呼び出し元 (router.py) は 503 を返し、クライアント側は「料金プラン非表示」として
扱うこと (frontend/components/user/FeePlanSection.tsx の fail-open ハンドリングと同じ方針)。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import TypedDict

from app.fees.models import FeeConfigV10


class FeeRateRange(TypedDict):
    """手数料率レンジの型定義。"""

    tier: str
    label: str
    min_rate: str
    max_rate: str
    min_rate_pct: str
    max_rate_pct: str
    description: str


#: fee_configs.tier_fee_rates / tier_thresholds_jpy のインデックス順 (LOWER/MIDDLE/UPPER)。
_TIER_ORDER = ["LOWER", "MIDDLE", "UPPER"]
_TIER_LABELS = {"LOWER": "一般", "MIDDLE": "ミドル", "UPPER": "アッパー"}


def _active_config(db: Session) -> Optional[FeeConfigV10]:
    """現行 active な FeeConfigV10 を返す (なければ None)。"""
    stmt = (
        select(FeeConfigV10)
        .where(FeeConfigV10.is_active.is_(True))
        .order_by(FeeConfigV10.effective_from.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _tier_description(index: int, thresholds: list[int]) -> str:
    """tier_thresholds_jpy から tier の説明文を組み立てる (ハードコード金額禁止)。"""
    lower = 0 if index == 0 else thresholds[index - 1]
    if index == len(thresholds):
        return f"デポジット {lower:,} 円以上のティア"
    upper = thresholds[index]
    if lower == 0:
        return f"デポジット {upper:,} 円以下のティア"
    return f"デポジット {lower:,}〜{upper:,} 円のティア"


def _to_fee_rate_range(tier: str, config: FeeConfigV10) -> FeeRateRange:
    """FeeConfigV10 (v10: tier ごとの単一固定率) を FeeRateRange へ変換する。

    v10 は tier ごとに単一の固定率 (レンジではない) なので min_rate == max_rate。
    """
    index = _TIER_ORDER.index(tier)
    rate = Decimal(str(config.tier_fee_rates[index]))
    rate_pct = rate * 100
    return FeeRateRange(
        tier=tier,
        label=_TIER_LABELS[tier],
        min_rate=str(rate),
        max_rate=str(rate),
        min_rate_pct=str(rate_pct),
        max_rate_pct=str(rate_pct),
        description=_tier_description(index, list(config.tier_thresholds_jpy)),
    )


def get_fee_rate_range(tier: str, db: Session) -> Optional[FeeRateRange]:
    """ティア文字列から手数料率レンジを返す (fee_configs 由来、v10正本)。

    Args:
        tier: "LOWER" / "MIDDLE" / "UPPER"
        db: SQLAlchemy セッション

    Returns:
        FeeRateRange dict。fee_configs に active レコードがなければ None。

    Raises:
        ValueError: 不明なティアを指定した場合
    """
    if tier not in _TIER_ORDER:
        raise ValueError(f"Unknown tier: {tier!r}. Must be one of {_TIER_ORDER}")
    config = _active_config(db)
    if config is None:
        return None
    return _to_fee_rate_range(tier, config)


def get_full_fee_schedule(db: Session) -> Optional[list[FeeRateRange]]:
    """全ティアの手数料率レンジ一覧を返す (LOWER → MIDDLE → UPPER の順)。

    fee_configs に active レコードがなければ None。
    """
    config = _active_config(db)
    if config is None:
        return None
    return [_to_fee_rate_range(tier, config) for tier in _TIER_ORDER]
