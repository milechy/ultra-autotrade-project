# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/monitor.py
"""
Aave V3 モニタリング — ヘルスファクタ・残高のリアルタイム取得。

- AAVE_CLIENT_TYPE=dummy → DummyAaveClient でモックデータを返す（後方互換）
- AAVE_CLIENT_TYPE=web3  → RPC 経由でリアルタイム取得

読み取り専用操作のみ。AAVE_WALLET_PRIVATE_KEY 不要。

環境変数:
    AAVE_CLIENT_TYPE    : "dummy" | "web3" (デフォルト: "dummy")
    AAVE_WALLET_ADDRESS : 監視対象のウォレットアドレス
    AAVE_RPC_URL        : RPC エンドポイント (web3 時必須)
    AAVE_POOL_ADDRESS   : Aave V3 Pool (Proxy) アドレス (web3 時必須)
    AAVE_USDC_ADDRESS   : USDC トークンアドレス (web3 残高取得時)
    AAVE_A_USDC_ADDRESS : aUSDC トークンアドレス (web3 残高取得時)
"""

import logging
import os
from decimal import Decimal
from typing import Optional

from .schemas import AaveBalanceInfo

logger = logging.getLogger(__name__)

_ERC20_BALANCE_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def _client_type() -> str:
    return os.getenv("AAVE_CLIENT_TYPE", "dummy")


def get_health_factor(wallet_address: Optional[str] = None) -> Optional[Decimal]:
    """Aave V3 Pool.getUserAccountData() から Health Factor を取得する。

    AAVE_CLIENT_TYPE=web3 の場合は RPC 経由、dummy の場合はモック値 2.5 を返す。
    失敗時は None を返す（呼び出し側が判定する）。

    Args:
        wallet_address: 監視対象のウォレットアドレス。
                        省略時は AAVE_WALLET_ADDRESS 環境変数を使用。

    Returns:
        Health Factor の Decimal 値。取得失敗、設定不足、またはポジションなし (Infinity) の場合は None。
    """
    addr = wallet_address or os.getenv("AAVE_WALLET_ADDRESS", "")
    if not addr:
        logger.warning("[monitor] AAVE_WALLET_ADDRESS not set; skipping HF fetch")
        return None

    ctype = _client_type()

    raw: Optional[Decimal] = None

    if ctype == "dummy":
        from .client import DummyAaveClient  # noqa: PLC0415

        raw = DummyAaveClient().get_health_factor(addr)

    elif ctype == "web3":
        rpc_url = os.getenv("AAVE_RPC_URL", "")
        pool_address = os.getenv("AAVE_POOL_ADDRESS", "")
        if not rpc_url:
            logger.warning("[monitor] AAVE_RPC_URL not set; skipping HF fetch")
            return None
        if not pool_address:
            logger.warning("[monitor] AAVE_POOL_ADDRESS not set; skipping HF fetch")
            return None
        try:
            from .client import Web3AaveClient  # noqa: PLC0415

            client = Web3AaveClient(rpc_url=rpc_url, pool_address=pool_address)
            raw = client.get_health_factor(addr)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[monitor] get_health_factor failed: %s", exc)
            return None

    else:
        logger.warning("[monitor] Unknown AAVE_CLIENT_TYPE=%r; returning None", ctype)
        return None

    # Decimal('Infinity') はポジションなし（借入ゼロ）を表す。
    # JSON シリアライズ不可のため None に正規化する。
    if raw is not None and not raw.is_finite():
        logger.info("[monitor] HF is Infinity (no borrow position); returning None")
        return None

    # HF < 1.8 で LINE Push 通知（fail-open: 通知失敗でも HF 返却を止めない）
    if raw is not None and raw < Decimal("1.8"):
        _notify_hf_warning(raw)

    return raw


def _notify_hf_warning(hf: Decimal) -> None:
    """HF 警告通知を LINE Push で送信する（fail-open）。

    templates.health_factor_warning でテキストを整形し、push_text で送信する。
    HF < 1.8 のとき呼ばれる。通知失敗時は例外を握りつぶしてログに残す。

    Args:
        hf: 現在の Health Factor 値。
    """
    try:
        from app.notifications.line_push import push_text  # noqa: PLC0415
        from app.notifications.templates import health_factor_warning  # noqa: PLC0415

        payload = health_factor_warning(hf)
        push_text("", payload.body)
        logger.warning("[monitor] HF warning 通知送信: hf=%s", hf)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[monitor] HF warning 通知送信失敗 (fail-open): %s", exc)


def get_aave_balance(wallet_address: Optional[str] = None) -> AaveBalanceInfo:
    """ウォレットの USDC + aUSDC 残高を取得する。

    AAVE_CLIENT_TYPE=web3 の場合は RPC 経由で ERC-20 balanceOf を呼ぶ。
    dummy またはアドレス未設定の場合はモック値を返す。

    Args:
        wallet_address: 監視対象のウォレットアドレス。
                        省略時は AAVE_WALLET_ADDRESS 環境変数を使用。

    Returns:
        AaveBalanceInfo (残高取得失敗時は 0 を返す)。
    """
    addr = wallet_address or os.getenv("AAVE_WALLET_ADDRESS", "")
    ctype = _client_type()

    if ctype != "web3" or not addr:
        return AaveBalanceInfo(
            wallet_address=addr,
            usdc_balance=Decimal("1000"),
            a_usdc_balance=Decimal("500"),
        )

    rpc_url = os.getenv("AAVE_RPC_URL", "")
    usdc_address = os.getenv("AAVE_USDC_ADDRESS", "")
    a_usdc_address = os.getenv("AAVE_A_USDC_ADDRESS", "")

    usdc_balance = Decimal("0")
    a_usdc_balance = Decimal("0")

    def _fetch_erc20_balance(token_addr: str) -> Decimal:
        """ERC-20 balanceOf を呼んで人間単位の残高を返す。"""
        from web3 import Web3  # noqa: PLC0415

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        checksum_wallet = Web3.to_checksum_address(addr)
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(token_addr),
            abi=_ERC20_BALANCE_ABI,
        )
        decimals: int = contract.functions.decimals().call()
        raw: int = contract.functions.balanceOf(checksum_wallet).call()
        return Decimal(raw) / Decimal(10**decimals)

    if rpc_url and usdc_address:
        try:
            usdc_balance = _fetch_erc20_balance(usdc_address)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[monitor] USDC balance fetch failed: %s", exc)

    if rpc_url and a_usdc_address:
        try:
            a_usdc_balance = _fetch_erc20_balance(a_usdc_address)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[monitor] aUSDC balance fetch failed: %s", exc)

    return AaveBalanceInfo(
        wallet_address=addr,
        usdc_balance=usdc_balance,
        a_usdc_balance=a_usdc_balance,
    )
