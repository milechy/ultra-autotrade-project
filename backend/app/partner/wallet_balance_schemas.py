# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/partner/wallet_balance_schemas.py
"""Partner wallet balance API response schema.

GET /api/partner/wallet-balance のレスポンス定義。
USDC + ETH (native) on Base mainnet のみを集計。Aave supply 分は含まない。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class WalletBalanceResponse(BaseModel):
    """Partner 自身のウォレット内資産 (USDC + ETH on Base mainnet) のレスポンス。

    Aave supply 分は含まない (= ウォレットに「入っている」を文字通り)。
    """

    wallet_address: str
    chain: Literal["base"] = "base"
    eth_balance: Decimal  # wei → ether に変換済
    eth_usd_value: Decimal  # eth_balance * eth_usd_price
    eth_usd_price: Decimal  # 1 ETH = ? USD (Chainlink ETH/USD)
    usdc_balance: Decimal  # USDC を 10^6 で除した値
    usdc_usd_value: Decimal  # usdc_balance * 1.00 (1:1 simplification)
    total_usd: Decimal  # eth_usd_value + usdc_usd_value
    fetched_at: datetime
    cache_age_seconds: int  # 0 if fresh, else seconds since fetched
    fallback_used: bool  # true if RPC or price fallback was triggered
