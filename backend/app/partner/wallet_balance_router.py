# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/partner/wallet_balance_router.py
"""Partner wallet balance API ルーター定義。

GET /api/partner/wallet-balance — 認証済 partner 自身のウォレット (Base mainnet) の
USDC + ETH 残高を返す。Aave supply 分は含まない。60 秒 cache。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_partner
from app.auth.models import User
from app.partner import wallet_balance_service
from app.partner.wallet_balance_schemas import WalletBalanceResponse

router = APIRouter(tags=["partner"])


@router.get(
    "/wallet-balance",
    response_model=WalletBalanceResponse,
    summary="Partner 自身のウォレット残高 (USDC + ETH on Base mainnet)",
)
async def get_wallet_balance(
    current_user: User = Depends(require_partner),
) -> WalletBalanceResponse:
    """認証済 partner 自身の wallet (Base mainnet) の USDC + ETH 残高を返す。

    Aave supply 分は含まない (= ウォレットに「入っている」を文字通り)。
    60 秒 in-memory cache。RPC / price 失敗時は fallback_used=true で degrade。
    """
    if not current_user.wallet_address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="wallet_address が partner に未設定です",
        )
    return await wallet_balance_service.fetch(current_user.wallet_address)
