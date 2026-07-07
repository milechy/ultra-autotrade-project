# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/fee_transfer_service.py
"""F-S6: On-chain fee transfer service (月次手数料 on-chain 徴収).

Non-custodial design (§14a):
  FROM:  user.wallet_address — Aave aToken がユーザー自身の wallet に存在
  TO:    OPERATOR_FEE_WALLET_ADDRESS env var — operator 自身の wallet
  HOW:   operator wallet が aToken.transferFrom(user, operator, amount) を実行
  KEY:   OPERATOR_FEE_WALLET_KEY = operator **自身の** 秘密鍵 (ユーザー鍵 ≠)
  GATE:  FEE_TRANSFER_ENABLED=false → DB 記録のみ (デフォルト)、true → 実送金

non-custodial 保護ロジック:
  - サーバーはユーザーの秘密鍵を持たない (今日直した custodial 問題 §14a 再発防止)
  - ユーザーは供給時に aToken の operator wallet への allowance を事前承認
  - Operator は承認された分だけ引き出し可能。ユーザーはいつでも revoke 可能
  - Operator wallet は自身の資金のみコントロール — ユーザー資産を代理管理しない

参考:
  - docs/45_fee_model_v10_migration_plan.md §4 F-S6
  - /home/uata/handoffs/2026-06-01_fee_collection_method.md
  - backend/app/proposals/router.py — AUTO_EXECUTION_ENABLED フラグと同型
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ABI (最小限)
# ---------------------------------------------------------------------------

#: ERC-20 最小 ABI: allowance, transferFrom
_ERC20_ABI_MINIMAL: list[dict[str, object]] = [
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "transferFrom",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]

#: Aave Pool Data Provider ABI: getReserveTokensAddresses
_DATA_PROVIDER_ABI_MINIMAL: list[dict[str, object]] = [
    {
        "name": "getReserveTokensAddresses",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [
            {"name": "aTokenAddress", "type": "address"},
            {"name": "stableDebtTokenAddress", "type": "address"},
            {"name": "variableDebtTokenAddress", "type": "address"},
        ],
    },
]

# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeeTransferConfig:
    """on-chain fee transfer の設定。環境変数から組み立て。

    signing_mode:
      - ``"raw_key"``(既定・後方互換): operator_wallet_key(生鍵)を使い
        `w3.eth.account.sign_transaction` で署名・送信する旧式。
      - ``"privy"``: operator wallet を Privy Server Wallet 化し、生鍵を env に
        置かず Privy REST(`eth_sendTransaction`, TEE 内署名)で送信する。env に残る
        秘密は P-256 authorization 鍵のみ(= ブロックチェーン鍵ではない・policy 制約下)。
    """

    enabled: bool
    operator_wallet_address: str
    operator_wallet_key: str
    rpc_url: str
    data_provider_address: str
    usdc_address: str
    chain_id: int
    signing_mode: str = "raw_key"
    operator_privy_wallet_id: str = ""
    chain_name: str = "base_sepolia"

    @classmethod
    def from_env(cls, chain_name: str = "base_sepolia") -> "FeeTransferConfig":
        """環境変数から設定を読み込む。

        FEE_TRANSFER_ENABLED=false の場合、他の変数は空でも構わない。
        """
        from app.aave.chains import get_chain_config  # noqa: PLC0415

        enabled = os.getenv("FEE_TRANSFER_ENABLED", "false").lower() == "true"
        op_address = os.getenv("OPERATOR_FEE_WALLET_ADDRESS", "")
        op_key = os.getenv("OPERATOR_FEE_WALLET_KEY", "")
        # 署名モード: 既定 raw_key(後方互換)。privy 指定時は Privy Server Wallet 経路。
        signing_mode = os.getenv("FEE_SIGNING_MODE", "raw_key").strip().lower()
        if signing_mode not in ("raw_key", "privy"):
            signing_mode = "raw_key"
        operator_privy_wallet_id = os.getenv("OPERATOR_FEE_PRIVY_WALLET_ID", "").strip()
        active_chain = os.getenv("AAVE_ACTIVE_CHAINS", chain_name).split(",")[0].strip()
        chain_cfg = get_chain_config(active_chain)
        rpc_url = os.getenv(chain_cfg.rpc_url_env_var, "") if chain_cfg.rpc_url_env_var else ""
        return cls(
            enabled=enabled,
            operator_wallet_address=op_address,
            operator_wallet_key=op_key,
            rpc_url=rpc_url,
            data_provider_address=chain_cfg.data_provider_address or "",
            usdc_address=chain_cfg.tokens.get("USDC", ""),
            chain_id=chain_cfg.chain_id,
            signing_mode=signing_mode,
            operator_privy_wallet_id=operator_privy_wallet_id,
            chain_name=active_chain,
        )


@dataclass(frozen=True)
class FeeTransferResult:
    """1 ユーザー分の on-chain 手数料送金結果。"""

    user_id: int
    user_wallet: str
    fee_usd: Decimal
    atoken_units: int  # aUSDC raw units (6 decimals)
    tx_hash: Optional[str] = None
    status: str = "skipped"  # 'sent' | 'skipped' | 'failed' | 'low_fee' | 'no_allowance'
    error: Optional[str] = None
    debug_log: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# サービス
# ---------------------------------------------------------------------------


class FeeTransferService:
    """月次手数料 on-chain 徴収サービス。

    FEE_TRANSFER_ENABLED=false の間は何もしない (dry run と同等)。
    true になった時点で operator wallet が aToken.transferFrom を実行する。
    """

    #: 1 件の fee_transfer が処理対象とみなす最低 USD 金額
    MIN_FEE_USD: Decimal = Decimal("0.01")

    def __init__(self, config: FeeTransferConfig) -> None:
        self.config = config
        self._w3: Optional[Any] = None  # lazy init

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transfer_fee(
        self,
        user_id: int,
        user_wallet: str,
        fee_amount_jpy: Decimal,
        subscription_amount_jpy: Decimal,
        yield_excess_jpy: Decimal,
        usd_jpy_rate: Decimal,
    ) -> FeeTransferResult:
        """1 ユーザー分の月次手数料を on-chain で送金する。

        FEE_TRANSFER_ENABLED=false → status='skipped' を返す (送金しない)。

        Args:
            user_id: 手数料対象ユーザー ID (logging 用)
            user_wallet: ユーザーの on-chain wallet address
            fee_amount_jpy: 成功報酬 (JPY)
            subscription_amount_jpy: サブスク手数料 (JPY)
            yield_excess_jpy: yield cap 超過分 (JPY)
            usd_jpy_rate: 計算時の USD/JPY レート
        """
        debug: list[str] = []

        # Gate 1: flag
        if not self.config.enabled:
            debug.append("FEE_TRANSFER_ENABLED=false → skipped")
            return FeeTransferResult(
                user_id=user_id,
                user_wallet=user_wallet,
                fee_usd=Decimal("0"),
                atoken_units=0,
                status="skipped",
                debug_log=debug,
            )

        # Gate 2: operator wallet 設定 (署名モード別)
        #   raw_key: address + key(生鍵) が必要
        #   privy:   address(allowance 確認 + transferFrom 宛先) + Privy wallet ID が必要
        #            (生鍵 operator_wallet_key は不要・env に置かない)
        if not self.config.operator_wallet_address:
            msg = "OPERATOR_FEE_WALLET_ADDRESS not configured"
            logger.error("fee_transfer user_id=%d: %s", user_id, msg)
            return FeeTransferResult(
                user_id=user_id,
                user_wallet=user_wallet,
                fee_usd=Decimal("0"),
                atoken_units=0,
                status="failed",
                error=msg,
                debug_log=debug,
            )
        if self.config.signing_mode == "privy":
            if not self.config.operator_privy_wallet_id:
                msg = "FEE_SIGNING_MODE=privy but OPERATOR_FEE_PRIVY_WALLET_ID not configured"
                logger.error("fee_transfer user_id=%d: %s", user_id, msg)
                return FeeTransferResult(
                    user_id=user_id,
                    user_wallet=user_wallet,
                    fee_usd=Decimal("0"),
                    atoken_units=0,
                    status="failed",
                    error=msg,
                    debug_log=debug,
                )
        elif not self.config.operator_wallet_key:
            msg = "OPERATOR_FEE_WALLET_KEY not configured (raw_key mode)"
            logger.error("fee_transfer user_id=%d: %s", user_id, msg)
            return FeeTransferResult(
                user_id=user_id,
                user_wallet=user_wallet,
                fee_usd=Decimal("0"),
                atoken_units=0,
                status="failed",
                error=msg,
                debug_log=debug,
            )

        # Gate 3: user wallet
        if not user_wallet:
            msg = f"user_id={user_id} has no wallet_address"
            logger.warning("fee_transfer: %s", msg)
            return FeeTransferResult(
                user_id=user_id,
                user_wallet="",
                fee_usd=Decimal("0"),
                atoken_units=0,
                status="skipped",
                error=msg,
                debug_log=debug,
            )

        # 手数料 JPY → USD 変換
        total_operator_jpy = fee_amount_jpy + subscription_amount_jpy + yield_excess_jpy
        if usd_jpy_rate <= Decimal("0"):
            return FeeTransferResult(
                user_id=user_id,
                user_wallet=user_wallet,
                fee_usd=Decimal("0"),
                atoken_units=0,
                status="failed",
                error=f"invalid usd_jpy_rate={usd_jpy_rate}",
                debug_log=debug,
            )
        fee_usd = (total_operator_jpy / usd_jpy_rate).quantize(Decimal("0.000001"))
        debug.append(
            f"total_operator_jpy={total_operator_jpy} / rate={usd_jpy_rate} = fee_usd={fee_usd}"
        )

        # Gate 4: 最低金額チェック (dust 防止)
        if fee_usd < self.MIN_FEE_USD:
            debug.append(f"fee_usd={fee_usd} < MIN_FEE_USD={self.MIN_FEE_USD} → low_fee")
            return FeeTransferResult(
                user_id=user_id,
                user_wallet=user_wallet,
                fee_usd=fee_usd,
                atoken_units=0,
                status="low_fee",
                debug_log=debug,
            )

        # on-chain 実行
        return self._execute_transfer(user_id, user_wallet, fee_usd, debug)

    def check_allowance(self, user_wallet: str) -> Decimal:
        """ユーザーが operator wallet に付与した aToken allowance を USD 換算で返す。

        FEE_TRANSFER_ENABLED=false の場合でも呼び出し可能 (diagnostic 用)。

        Returns:
            Decimal allowance in USD (0 if not configured or RPC error)
        """
        if not self.config.rpc_url or not self.config.operator_wallet_address:
            return Decimal("0")
        try:
            w3 = self._get_w3()
            atoken = self._get_atoken_address(w3)
            if not atoken:
                return Decimal("0")
            atoken_contract = w3.eth.contract(
                address=w3.to_checksum_address(atoken),
                abi=_ERC20_ABI_MINIMAL,
            )
            raw_allowance = atoken_contract.functions.allowance(
                w3.to_checksum_address(user_wallet),
                w3.to_checksum_address(self.config.operator_wallet_address),
            ).call()
            decimals = atoken_contract.functions.decimals().call()
            allowance_usd = Decimal(raw_allowance) / Decimal(10**decimals)
            return allowance_usd
        except Exception as exc:  # noqa: BLE001
            logger.warning("check_allowance error: %s", exc)
            return Decimal("0")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_w3(self) -> Any:
        """Web3 インスタンスをlazy initで返す。"""
        if self._w3 is None:
            from web3 import Web3  # noqa: PLC0415

            self._w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
        return self._w3

    def _get_atoken_address(self, w3: Any) -> Optional[str]:
        """Pool Data Provider から aUSDC の address を取得する。"""
        if not self.config.data_provider_address or not self.config.usdc_address:
            return None
        try:
            dp = w3.eth.contract(
                address=w3.to_checksum_address(self.config.data_provider_address),
                abi=_DATA_PROVIDER_ABI_MINIMAL,
            )
            result = dp.functions.getReserveTokensAddresses(
                w3.to_checksum_address(self.config.usdc_address)
            ).call()
            atoken_addr: str = result[0]
            logger.debug("aUSDC address: %s", atoken_addr)
            return atoken_addr
        except Exception as exc:  # noqa: BLE001
            logger.error("_get_atoken_address error: %s", exc)
            return None

    def _submit_transferfrom_raw_key(
        self,
        w3: Any,
        atoken_contract: Any,
        user_addr_cs: str,
        op_addr_cs: str,
        atoken_units: int,
    ) -> tuple[str, int]:
        """raw_key モード: 生鍵で transferFrom を署名・送信し (tx_hash_hex, status) を返す。

        旧式(後方互換)。operator_wallet_key を使い web3 でローカル署名する。
        """
        account = w3.eth.account.from_key(self.config.operator_wallet_key)
        nonce = w3.eth.get_transaction_count(account.address, "pending")
        tx = atoken_contract.functions.transferFrom(
            user_addr_cs,
            op_addr_cs,
            atoken_units,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": self.config.chain_id,
                "gas": 100000,
                "gasPrice": w3.eth.gas_price,
            }
        )
        signed = w3.eth.account.sign_transaction(tx, private_key=self.config.operator_wallet_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        return tx_hash.hex(), int(receipt.status)

    def _submit_transferfrom_privy(
        self,
        w3: Any,
        atoken_contract: Any,
        atoken_addr: str,
        user_addr_cs: str,
        op_addr_cs: str,
        atoken_units: int,
        debug: list[str],
    ) -> tuple[str, int]:
        """privy モード: Privy Server Wallet(TEE 内署名)で transferFrom を送信する。

        生鍵を env に置かず、Privy REST `eth_sendTransaction` に calldata を渡す。
        gas/nonce は Privy 側が補完。返却 tx_hash を web3 で receipt 待ちして status を確認。
        """
        from app.privy.rest_client import PrivyRestClient, PrivyRestError  # noqa: PLC0415
        from app.proposals.scw_executor import caip2_for_chain  # noqa: PLC0415

        # transferFrom calldata を encode (web3.py v7: encode_abi 位置引数)
        data = atoken_contract.encode_abi(
            "transferFrom", args=[user_addr_cs, op_addr_cs, atoken_units]
        )
        caip2 = caip2_for_chain(self.config.chain_name)
        transaction = {
            "to": w3.to_checksum_address(atoken_addr),
            "data": data,
            "value": "0x0",
        }
        try:
            resp = PrivyRestClient().send_transaction(
                self.config.operator_privy_wallet_id,
                caip2=caip2,
                transaction=transaction,
            )
        except PrivyRestError as exc:
            # 秘密鍵・署名はログに出さない (status のみ)
            logger.warning("fee_transfer Privy send_transaction failed: status=%s", exc.status_code)
            raise

        # Privy レスポンスから tx hash を取り出す (キー名の揺れに defensive)
        tx_hash_hex = str(
            resp.get("transaction_hash")
            or resp.get("hash")
            or (resp.get("data") or {}).get("transaction_hash", "")
        ).strip()
        if not tx_hash_hex:
            raise RuntimeError(f"Privy returned no tx hash: keys={list(resp.keys())}")
        debug.append(f"privy_tx_hash={tx_hash_hex}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash_hex, timeout=120)
        return tx_hash_hex, int(receipt.status)

    def _execute_transfer(
        self,
        user_id: int,
        user_wallet: str,
        fee_usd: Decimal,
        debug: list[str],
    ) -> FeeTransferResult:
        """aToken.transferFrom を実行する。

        operator wallet が user_wallet から operator_wallet_address へ fee を引き出す。
        """
        try:
            w3 = self._get_w3()

            # aToken アドレス取得
            atoken_addr = self._get_atoken_address(w3)
            if not atoken_addr:
                return FeeTransferResult(
                    user_id=user_id,
                    user_wallet=user_wallet,
                    fee_usd=fee_usd,
                    atoken_units=0,
                    status="failed",
                    error="aToken address unavailable",
                    debug_log=debug,
                )

            atoken_contract = w3.eth.contract(
                address=w3.to_checksum_address(atoken_addr),
                abi=_ERC20_ABI_MINIMAL,
            )
            decimals = atoken_contract.functions.decimals().call()
            atoken_units = int(fee_usd * Decimal(10**decimals))
            debug.append(f"atoken_addr={atoken_addr} decimals={decimals} units={atoken_units}")

            # Allowance チェック
            op_addr_cs = w3.to_checksum_address(self.config.operator_wallet_address)
            user_addr_cs = w3.to_checksum_address(user_wallet)
            raw_allowance = atoken_contract.functions.allowance(user_addr_cs, op_addr_cs).call()
            if raw_allowance < atoken_units:
                msg = f"insufficient allowance: allowed={raw_allowance} < required={atoken_units}"
                logger.warning("fee_transfer user_id=%d: %s", user_id, msg)
                debug.append(msg)
                return FeeTransferResult(
                    user_id=user_id,
                    user_wallet=user_wallet,
                    fee_usd=fee_usd,
                    atoken_units=atoken_units,
                    status="no_allowance",
                    error=msg,
                    debug_log=debug,
                )

            # 署名モード別に transferFrom を送信し (tx_hash_hex, receipt_status) を得る。
            #   raw_key: 生鍵で sign_transaction → send_raw_transaction (旧式)
            #   privy:   Privy REST(eth_sendTransaction, TEE 内署名) で送信 (生鍵不要)
            if self.config.signing_mode == "privy":
                tx_hash_hex, receipt_status = self._submit_transferfrom_privy(
                    w3, atoken_contract, atoken_addr, user_addr_cs, op_addr_cs, atoken_units, debug
                )
            else:
                tx_hash_hex, receipt_status = self._submit_transferfrom_raw_key(
                    w3, atoken_contract, user_addr_cs, op_addr_cs, atoken_units
                )

            if receipt_status != 1:
                msg = f"tx reverted: {tx_hash_hex}"
                logger.error("fee_transfer user_id=%d: %s", user_id, msg)
                return FeeTransferResult(
                    user_id=user_id,
                    user_wallet=user_wallet,
                    fee_usd=fee_usd,
                    atoken_units=atoken_units,
                    tx_hash=tx_hash_hex,
                    status="failed",
                    error=msg,
                    debug_log=debug,
                )

            logger.info(
                "fee_transfer sent: user_id=%d wallet=%s...%s fee_usd=%s tx=%s",
                user_id,
                user_wallet[:6],
                user_wallet[-4:],
                fee_usd,
                tx_hash_hex,
            )
            debug.append(f"tx_hash={tx_hash_hex} status=1")
            return FeeTransferResult(
                user_id=user_id,
                user_wallet=user_wallet,
                fee_usd=fee_usd,
                atoken_units=atoken_units,
                tx_hash=tx_hash_hex,
                status="sent",
                debug_log=debug,
            )

        except Exception as exc:  # noqa: BLE001
            msg = f"transfer exception: {exc}"
            logger.error("fee_transfer user_id=%d: %s", user_id, msg)
            return FeeTransferResult(
                user_id=user_id,
                user_wallet=user_wallet,
                fee_usd=fee_usd,
                atoken_units=0,
                status="failed",
                error=msg,
                debug_log=debug,
            )


# ---------------------------------------------------------------------------
# Helpers (module-level)
# ---------------------------------------------------------------------------


def is_fee_transfer_enabled() -> bool:
    """FEE_TRANSFER_ENABLED=true かどうかを返す。"""
    return os.getenv("FEE_TRANSFER_ENABLED", "false").lower() == "true"


def get_fee_transfer_datetime() -> datetime:
    """現在時刻 (UTC, timezone-aware)。テストでモック可能なように分離。"""
    return datetime.now(timezone.utc)
