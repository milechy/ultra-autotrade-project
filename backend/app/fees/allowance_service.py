# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/allowance_service.py
"""Fee allowance permit service (Asana 1215273755294098).

EIP-2612 permit で user→operator の aBasUSDC 上限付き allowance を設定する。
Privy session signer が user 側で permit typed data を sign し、
operator backend が on-chain で permit() を submit する。

既製解結論: Aave V3 AToken.sol は EIP-2612 permit() をネイティブサポート。
カスタム allowance 検証 / カストディアル保持は不要。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

try:
    from web3 import Web3
except ImportError:
    Web3 = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_ATOKEN_USDC_BASE_DEFAULT = "0x4e65fE4DbA92790696d040ac24Aa414708F5c0Ab"
_ATOKEN_USDC_BASE_SEPOLIA_DEFAULT = "0xab067c01df6C68BE84ac60FA1cF81Ad1E2261Bd5"

_ATOKEN_ABI_PERMIT = [
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "value", "type": "uint256"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            {"internalType": "uint8", "name": "v", "type": "uint8"},
            {"internalType": "bytes32", "name": "r", "type": "bytes32"},
            {"internalType": "bytes32", "name": "s", "type": "bytes32"},
        ],
        "name": "permit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "nonces",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "DOMAIN_SEPARATOR",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
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
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass(frozen=True)
class PermitTypedData:
    """EIP-712 typed data for permit (frontend → Privy 署名用)。"""

    domain: dict[str, Any]
    types: dict[str, Any]
    primary_type: str
    message: dict[str, Any]
    atoken_address: str
    chain_id: int


@dataclass(frozen=True)
class PermitSubmitResult:
    tx_hash: str
    user_address: str
    operator_address: str
    allowance_limit_usdc: Decimal
    deadline_ts: int


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


class AllowanceService:
    """EIP-2612 permit で aBasUSDC 上限付き allowance を管理する。"""

    def build_permit_typed_data(
        self,
        user_address: str,
        allowance_limit_usdc: Decimal,
        deadline_ts: int,
    ) -> PermitTypedData:
        """EIP-712 permit typed data を構築する。"""
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

        atoken = w3.eth.contract(address=cs_atoken, abi=_ATOKEN_ABI_PERMIT)
        decimals: int = atoken.functions.decimals().call()
        nonce: int = atoken.functions.nonces(cs_user).call()
        token_name: str = atoken.functions.name().call()
        chain_id: int = w3.eth.chain_id
        amount_raw = int(allowance_limit_usdc * Decimal(10**decimals))

        domain: dict[str, Any] = {
            "name": token_name,
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": cs_atoken,
        }
        types: dict[str, Any] = {
            "Permit": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ]
        }
        message: dict[str, Any] = {
            "owner": cs_user,
            "spender": operator_addr,
            "value": amount_raw,
            "nonce": nonce,
            "deadline": deadline_ts,
        }

        logger.info(
            "permit typed data 構築: user=%s operator=%s amount=%s USDC nonce=%d",
            cs_user,
            operator_addr,
            allowance_limit_usdc,
            nonce,
        )
        return PermitTypedData(
            domain=domain,
            types=types,
            primary_type="Permit",
            message=message,
            atoken_address=cs_atoken,
            chain_id=chain_id,
        )

    def submit_permit(
        self,
        user_address: str,
        allowance_limit_usdc: Decimal,
        deadline_ts: int,
        v: int,
        r: str,
        s: str,
    ) -> PermitSubmitResult:
        """署名済み permit を on-chain submit (operator が gas 負担)。"""
        if Web3 is None:
            raise RuntimeError("web3 が未インストールです。")

        private_key = os.getenv("AAVE_WALLET_PRIVATE_KEY", "")
        if not private_key:
            raise ValueError("AAVE_WALLET_PRIVATE_KEY が設定されていません。")

        rpc_url = _get_rpc_url()
        atoken_addr = _get_atoken_address()
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        cs_user = Web3.to_checksum_address(user_address)
        cs_atoken = Web3.to_checksum_address(atoken_addr)
        operator_account = w3.eth.account.from_key(private_key)

        atoken = w3.eth.contract(address=cs_atoken, abi=_ATOKEN_ABI_PERMIT)
        decimals: int = atoken.functions.decimals().call()
        amount_raw = int(allowance_limit_usdc * Decimal(10**decimals))

        r_bytes = bytes.fromhex(r.removeprefix("0x"))
        s_bytes = bytes.fromhex(s.removeprefix("0x"))

        nonce = w3.eth.get_transaction_count(operator_account.address, "pending")
        tx = atoken.functions.permit(
            cs_user,
            operator_account.address,
            amount_raw,
            deadline_ts,
            v,
            r_bytes,
            s_bytes,
        ).build_transaction(
            {
                "chainId": w3.eth.chain_id,
                "from": operator_account.address,
                "nonce": nonce,
                "gasPrice": w3.eth.gas_price,
                "gas": 100_000,
            }
        )
        signed = operator_account.sign_transaction(tx)
        tx_hash_bytes = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)

        tx_hash_hex = tx_hash_bytes.hex()
        if receipt["status"] != 1:
            raise RuntimeError(f"permit revert: tx={tx_hash_hex}")

        logger.info(
            "permit 完了: tx=%s user=%s operator=%s amount=%s USDC",
            tx_hash_hex,
            cs_user,
            operator_account.address,
            allowance_limit_usdc,
        )
        return PermitSubmitResult(
            tx_hash=tx_hash_hex,
            user_address=cs_user,
            operator_address=operator_account.address,
            allowance_limit_usdc=allowance_limit_usdc,
            deadline_ts=deadline_ts,
        )
