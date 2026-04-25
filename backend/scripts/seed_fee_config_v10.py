#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""v10_default seed data 投入スクリプト (F-4)。

使い方 (staging-new):
    docker exec ultra-autotrade-backend-staging-new \\
      python /app/backend/scripts/seed_fee_config_v10.py

使い方 (本番):
    docs/48_fee_config_seed_runbook.md の 3 段プロンプト手順に従う。
    F-16 で実施する。

オプション:
    --dry-run : DB へ書き込まず、投入予定データだけ表示する

冪等性:
    config_name='v10_default' が is_active=True で既に存在する場合は何もしない (skip)。
    値変更時の更新手順は docs/48 §4 を参照。

設計:
    - F-3 の RISK_MODE_SUBSCRIPTION_RATES を直参照することで、spec 値が変わっても
      auth/models.py 1 箇所変更で seed 出力も自動追従する。
    - subscription_rates JSONB のキーは F-3 内部値 (conservative/balanced/aggressive)
      で固定。F-5 / F-6 / F-7 で同じキーを参照する前提。
    - tier_thresholds_jpy / tier_fee_rates / tier_monthly_yield_caps は v10 spec §1
      の固定値 (ここ以外には保存場所がないため inline 定義)。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# backend/ をパスに追加 (seed_test_data.py と同じパターン)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth.models import RISK_MODE_SUBSCRIPTION_RATES, RiskMode  # noqa: E402
from app.billing.v10_models import FeeConfigV10  # noqa: E402
from app.database import SessionLocal  # noqa: E402

logger = logging.getLogger(__name__)

#: JST タイムゾーン (effective_from 用)。
JST = timezone(timedelta(hours=9))

#: v10 default 設定のレコード名。冪等性チェックのキー。
V10_DEFAULT_CONFIG_NAME = "v10_default"

#: v10 default が有効になる時刻 (JST 2026-05-01 00:00:00)。
#: 過去日付に設定することで投入直後から有効になる。
V10_DEFAULT_EFFECTIVE_FROM = datetime(2026, 5, 1, 0, 0, 0, tzinfo=JST)


def build_v10_default_config() -> dict[str, object]:
    """v10 spec §1 の値を組み立てる。

    F-3 ``RISK_MODE_SUBSCRIPTION_RATES`` を直参照して整合保証。
    値が将来変わっても auth/models.py 1 箇所修正で本関数の出力も追従する。

    Returns:
        FeeConfigV10 コンストラクタに渡せる dict。
    """
    return {
        "config_name": V10_DEFAULT_CONFIG_NAME,
        "tier_thresholds_jpy": [1_000_000, 10_000_000],
        "tier_fee_rates": [0.30, 0.25, 0.20],
        "tier_monthly_yield_caps": [0.018, 0.023, 0.030],
        "subscription_rates": {
            mode.value: float(RISK_MODE_SUBSCRIPTION_RATES[mode]) for mode in RiskMode
        },
        # → {"conservative": 0.0, "balanced": 0.003, "aggressive": 0.01}
        "expense_markup_enabled": False,
        "expense_markup_rate": Decimal("0"),
        "affiliate_rate": Decimal("0.30"),
        "is_active": True,
        "effective_from": V10_DEFAULT_EFFECTIVE_FROM,
    }


def seed(db: Session, *, dry_run: bool = False) -> bool:
    """v10_default を投入する。冪等。

    Args:
        db: SQLAlchemy セッション。
        dry_run: True の場合 DB へ書き込まず、投入予定データを表示する。

    Returns:
        True  = 新規 INSERT を実行 (または dry_run で実行予定だった)
        False = 既存 active があったため skip
    """
    config_data = build_v10_default_config()

    # 既存の v10_default (active / inactive 問わず) があれば skip。
    # config_name に UNIQUE 制約があり、状態を問わず重複作成は失敗するため。
    # 値変更時は docs/48 §4 の手順 (新 config_name で投入後にスイッチ) を使う。
    stmt = select(FeeConfigV10).where(FeeConfigV10.config_name == V10_DEFAULT_CONFIG_NAME)
    existing = db.execute(stmt).scalar_one_or_none()

    if existing is not None:
        state = "active" if existing.is_active else "inactive"
        msg = f"[SKIP] {V10_DEFAULT_CONFIG_NAME} (id={existing.id}, {state}) already exists"
        logger.info(msg)
        print(msg)
        return False

    if dry_run:
        msg = f"[DRY-RUN] Would insert: {config_data}"
        logger.info(msg)
        print(msg)
        return True

    new_config = FeeConfigV10(**config_data)
    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    msg = f"[OK] Inserted {V10_DEFAULT_CONFIG_NAME} (id={new_config.id})"
    logger.info(msg)
    print(msg)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed v10_default FeeConfig")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted without writing to DB",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with SessionLocal() as db:
        seed(db, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
