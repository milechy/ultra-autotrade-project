# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/dca/config.py

"""
DCA（ドルコスト平均法）モジュールの設定値読み出しモジュール。

環境変数から DCAConfig を生成する。
デフォルト値は「安全側（dry_run=True、enabled=False）」に倒す。
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Optional

from .schemas import DCAConfig, DCAFrequency

logger = logging.getLogger(__name__)

# グローバルキャッシュ
_dca_config: Optional[DCAConfig] = None


def load_dca_config() -> DCAConfig:
    """環境変数から DCAConfig を生成する。"""
    enabled = os.environ.get("DCA_ENABLED", "false").lower() in ("true", "1", "yes")
    symbol = os.environ.get("DCA_SYMBOL", "BTC/USDT")
    dry_run = os.environ.get("DCA_DRY_RUN", "true").lower() not in ("false", "0", "no")

    amount_str = os.environ.get("DCA_AMOUNT_USD", "10")
    try:
        amount_usd = Decimal(amount_str)
        if amount_usd <= 0:
            logger.warning("DCA_AMOUNT_USD must be positive, using default 10")
            amount_usd = Decimal("10")
    except InvalidOperation:
        logger.warning("Invalid DCA_AMOUNT_USD=%r, using default 10", amount_str)
        amount_usd = Decimal("10")

    freq_str = os.environ.get("DCA_FREQUENCY", "daily").lower()
    try:
        frequency = DCAFrequency(freq_str)
    except ValueError:
        logger.warning("Invalid DCA_FREQUENCY=%r, using default daily", freq_str)
        frequency = DCAFrequency.DAILY

    return DCAConfig(
        enabled=enabled,
        symbol=symbol,
        amount_usd=amount_usd,
        frequency=frequency,
        dry_run=dry_run,
    )


def get_dca_config() -> DCAConfig:
    """Cached DCAConfig を取得する。"""
    global _dca_config
    if _dca_config is None:
        _dca_config = load_dca_config()
    return _dca_config


def reset_dca_config() -> None:
    """DCA設定をリセットする（テスト用）。"""
    global _dca_config
    _dca_config = None
