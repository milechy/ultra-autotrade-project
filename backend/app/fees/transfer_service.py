# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/transfer_service.py
"""On-chain fee transfer service (Asana 1215272587496967).

FEE_TRANSFER_ENABLED=false (default) のときは on-chain 送金を行わず None を返す。
法務 OK 後に FEE_TRANSFER_ENABLED=true にすることで本番送金が有効化される。

設計:
- aave/client.py とは完全に別ファイル (build-tx 経路 #500/#501 との衝突防止)
- aBasUSDC.transferFrom(user, recipient, amount) で fee を on-chain 送金
- 全金額計算は Decimal 型 (float 禁止)
- private key / wallet address は env のみ
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

try:
    from web3 import Web3
except ImportError:
    Web3 = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_ATOKEN_USDC_BASE_DEFAULT = "0x4e65fE4DbA92790696d040ac24Aa414708F5c0Ab"
_ATOKEN_USDC_BASE_SEPOLIA_DEFAULT = "0xab067c01df6C68BE84ac60FA1cF81Ad1E2261Bd5"

_ATOKEN_ABI_TRANSFER = [
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "transferFrom",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"},
        ],
        "name": "allowance",
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


@dataclass(frozen=True)
class FeeTransferResult:
    tx_hash: Optional[str]
    amount_usdc: Decimal
    from_address: str
    to_address: str
    enabled: bool
    dry_run: bool


def _is_transfer_enabled() -> bool:
    return os.getenv("FEE_TRANSFER_ENABLED", "false").lower() == "true"


def _get_atoken_address() -> str:
    network = os.getenv("AAVE_NETWORK", "base_sepolia").lower()
    if network == "base":
        return os.getenv("ATOKEN_USDC_BASE", _ATOKEN_USDC_BASE_DEFAULT)
    return os.getenv("ATOKEN_USDC_BASE_SEPOLIA", _ATOKEN_USDC_BASE_SEPOLIA_DEFAULT)


def _get_rpc_url() -> str:
    network = os.getenv("AAVE_NETWORK", "base_sepolia").lower()
    url = (
        os.getenv("AAVE_RPC_URL_BASE", "")
        if network == "base"
        else os.getenv("ALCHEMY_RPC_URL_BASE_SEPOLIA", "")
    )
    if not url:
        raise ValueError(f"RPC URL が設定されていません (AAVE_NETWORK={network!r})。")
    return url


class FeeTransferService:
    """On-chain fee transfer (FEE_TRANSFER_ENABLED gate)."""

    def transfer_fee(
        self,
        user_address: str,
        fee_amount_usdc: Decimal,
        fee_tx_db_id: int,
        *,
        dry_run: bool = False,
    ) -> FeeTransferResult:
        enabled = _is_transfer_enabled()
        if not enabled:
            logger.info("FEE_TRANSFER_ENABLED=false → no-op (fee_tx_id=%d)", fee_tx_db_id)
            return FeeTransferResult(
                tx_hash=None,
                amount_usdc=fee_amount_usdc,
                from_address=user_address,
                to_address="",
                enabled=False,
                dry_run=dry_run,
            )

        if Web3 is None:
            raise RuntimeError("web3 が未インストールです。")

        recipient = os.getenv("FEE_RECIPIENT_ADDRESS", "")
        if not recipient:
            raise ValueError("FEE_RECIPIENT_ADDRESS が設定されていません。")
        private_key = os.getenv("AAVE_WALLET_PRIVATE_KEY", "")
        if not private_key:
            raise ValueError("AAVE_WALLET_PRIVATE_KEY が設定されていません。")

        rpc_url = _get_rpc_url()
        atoken_addr = _get_atoken_address()
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        cs_user = Web3.to_checksum_address(user_address)
        cs_recipient = Web3.to_checksum_address(recipient)
        cs_atoken = Web3.to_checksum_address(atoken_addr)
        operator_account = w3.eth.account.from_key(private_key)

        atoken = w3.eth.contract(address=cs_atoken, abi=_ATOKEN_ABI_TRANSFER)
        decimals: int = atoken.functions.decimals().call()
        amount_raw = int(fee_amount_usdc * Decimal(10**decimals))

        current_allowance: int = atoken.functions.allowance(
            cs_user, operator_account.address
        ).call()
        if current_allowance < amount_raw:
            raise ValueError(
                f"allowance 不足: user={cs_user}, allowance={current_allowance}, "
                f"required={amount_raw}."
            )

        if dry_run:
            logger.info(
                "dry_run OK: user=%s amount=%s USDC fee_tx_id=%d",
                cs_user,
                fee_amount_usdc,
                fee_tx_db_id,
            )
            return FeeTransferResult(
                tx_hash=None,
                amount_usdc=fee_amount_usdc,
                from_address=cs_user,
                to_address=cs_recipient,
                enabled=True,
                dry_run=True,
            )

        nonce = w3.eth.get_transaction_count(operator_account.address, "pending")
        tx = atoken.functions.transferFrom(cs_user, cs_recipient, amount_raw).build_transaction(
            {
                "chainId": w3.eth.chain_id,
                "from": operator_account.address,
                "nonce": nonce,
                "gasPrice": w3.eth.gas_price,
                "gas": 150_000,
            }
        )
        signed = operator_account.sign_transaction(tx)
        tx_hash_bytes = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)

        tx_hash_hex = tx_hash_bytes.hex()
        if receipt["status"] != 1:
            raise RuntimeError(f"fee transfer revert: tx={tx_hash_hex} fee_tx_id={fee_tx_db_id}")

        logger.info(
            "fee transfer 完了: tx=%s user=%s amount=%s USDC",
            tx_hash_hex,
            cs_user,
            fee_amount_usdc,
        )
        return FeeTransferResult(
            tx_hash=tx_hash_hex,
            amount_usdc=fee_amount_usdc,
            from_address=cs_user,
            to_address=cs_recipient,
            enabled=True,
            dry_run=False,
        )

    def get_allowance(self, user_address: str) -> Decimal:
        if Web3 is None:
            raise RuntimeError("web3 が未インストールです。")
        private_key = os.getenv("AAVE_WALLET_PRIVATE_KEY", "")
        rpc_url = _get_rpc_url()
        atoken_addr = _get_atoken_address()
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        cs_user = Web3.to_checksum_address(user_address)
        cs_atoken = Web3.to_checksum_address(atoken_addr)
        if private_key:
            operator_addr = Web3.to_checksum_address(w3.eth.account.from_key(private_key).address)
        else:
            r = os.getenv("FEE_RECIPIENT_ADDRESS", "")
            if not r:
                raise ValueError(
                    "FEE_RECIPIENT_ADDRESS または AAVE_WALLET_PRIVATE_KEY が必要です。"
                )
            operator_addr = Web3.to_checksum_address(r)
        atoken = w3.eth.contract(address=cs_atoken, abi=_ATOKEN_ABI_TRANSFER)
        decimals: int = atoken.functions.decimals().call()
        raw: int = atoken.functions.allowance(cs_user, operator_addr).call()
        return Decimal(raw) / Decimal(10**decimals)
