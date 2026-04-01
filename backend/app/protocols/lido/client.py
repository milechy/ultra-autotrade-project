# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance web3.py クライアント。"""

from __future__ import annotations

import logging
from abc import abstractmethod
from decimal import Decimal
from typing import Any

from app.protocols.base import (
    BaseProtocolClient,
    ProtocolHealthMetrics,
    ProtocolPosition,
    TransactionResult,
)

from .config import LidoConfig
from .schemas import TxResult

logger = logging.getLogger(__name__)

# Lido stETH ABI（最小限: submit, balanceOf, getPooledEthByShares）
_STETH_ABI: list[dict[str, Any]] = [
    {
        "name": "submit",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [{"name": "_referral", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "_account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getPooledEthByShares",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "_sharesAmount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getTotalPooledEther",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getTotalShares",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

_WEI_PER_ETH = Decimal("1000000000000000000")


class AbstractLidoClient(BaseProtocolClient):
    """Lido クライアントの抽象基底クラス。"""

    # --- BaseProtocolClient 実装 ---

    def get_protocol_name(self) -> str:
        """プロトコル名を返す。"""
        return "lido"

    def get_supported_assets(self) -> list[str]:
        """サポートするアセット一覧を返す。"""
        return ["ETH", "stETH"]

    async def get_current_apy(self) -> Decimal:
        """現在の APY を返す（staking APR と同値）。"""
        return await self.get_staking_apr()

    async def supply(self, amount: Decimal, asset: str) -> TransactionResult:
        """ETH を Lido にステーキングする（BaseProtocolClient インターフェース）。"""
        if asset not in ("ETH",):
            return TransactionResult(
                success=False,
                tx_hash=None,
                amount=amount,
                error=f"Lido は ETH のみサポートしています。指定アセット: {asset}",
            )
        amount_wei = int(amount * _WEI_PER_ETH)
        result = await self.stake_eth(amount_wei)
        return TransactionResult(
            success=result.success,
            tx_hash=result.tx_hash,
            amount=amount,
            error=result.error,
        )

    async def withdraw(self, amount: Decimal, asset: str) -> TransactionResult:
        """stETH の引き出し（Lido では withdraw は未サポート / PoC スタブ）。"""
        return TransactionResult(
            success=False,
            tx_hash=None,
            amount=amount,
            error="Lido の引き出しは現在サポートされていません（PoC）",
        )

    async def get_position(self) -> ProtocolPosition:
        """ポジション情報を返す（PoC: デフォルトアドレスの残高）。"""
        balance = Decimal("0")
        return ProtocolPosition(
            protocol_name=self.get_protocol_name(),
            asset="stETH",
            balance=balance,
            value_usd=balance,
        )

    async def get_health_metrics(self) -> ProtocolHealthMetrics:
        """ヘルスメトリクスを返す。"""
        try:
            apr = await self.get_staking_apr()
            ratio = await self.get_steth_eth_ratio()
            deviation_pct = abs(Decimal("1") - ratio) * Decimal("100")
            is_healthy = Decimal("0") <= apr <= Decimal("20") and deviation_pct <= Decimal("2")
            risk_score = min(deviation_pct / Decimal("10"), Decimal("1"))
            return ProtocolHealthMetrics(
                protocol_name=self.get_protocol_name(),
                is_healthy=is_healthy,
                risk_score=risk_score,
                details={"staking_apr": str(apr), "steth_eth_ratio": str(ratio)},
            )
        except Exception as exc:
            return ProtocolHealthMetrics(
                protocol_name=self.get_protocol_name(),
                is_healthy=False,
                risk_score=Decimal("1"),
                details={"error": str(exc)},
            )

    # --- Lido 固有の抽象メソッド ---

    @abstractmethod
    async def stake_eth(self, amount_wei: int) -> TxResult:
        """ETH → stETH ステーキング。"""
        ...

    @abstractmethod
    async def get_steth_balance(self, address: str) -> Decimal:
        """stETH 残高取得（ETH単位）。"""
        ...

    @abstractmethod
    async def get_staking_apr(self) -> Decimal:
        """現在の staking APR（%）。"""
        ...

    @abstractmethod
    async def get_steth_eth_ratio(self) -> Decimal:
        """stETH/ETH レート（1.0=完全ペグ）。"""
        ...


class LidoClient(AbstractLidoClient):
    """Lido Finance web3.py 接続クライアント（実ネットワーク用）。"""

    def __init__(self, config: LidoConfig) -> None:
        self._config = config
        self._w3: Any = None
        self._contract: Any = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        try:
            from web3 import Web3  # noqa: PLC0415

            self._w3 = Web3(Web3.HTTPProvider(self._config.rpc_url))
            self._contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(self._config.steth_contract_address),
                abi=_STETH_ABI,
            )
            self._initialized = True
            logger.info(
                "LidoClient initialized: chain=%s, contract=%s",
                self._config.chain,
                self._config.steth_contract_address[:10],
            )
        except ImportError:
            logger.warning("web3 パッケージが見つかりません。LidoClient は利用できません。")
            raise

    async def stake_eth(self, amount_wei: int) -> TxResult:
        """ETH → stETH ステーキング（Lido submit）。"""
        self._ensure_initialized()
        try:
            from web3 import Web3  # noqa: PLC0415

            if not self._config.wallet_private_key:
                return TxResult(success=False, error="LIDO_WALLET_PRIVATE_KEY が未設定")

            account = self._w3.eth.account.from_key(self._config.wallet_private_key)
            nonce = self._w3.eth.get_transaction_count(account.address)
            gas_price = self._w3.eth.gas_price

            tx = self._contract.functions.submit(
                Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
            ).build_transaction(
                {
                    "from": account.address,
                    "value": amount_wei,
                    "nonce": nonce,
                    "gasPrice": gas_price,
                    "gas": 200_000,
                }
            )
            signed = self._w3.eth.account.sign_transaction(tx, self._config.wallet_private_key)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt["status"] == 1:
                # submit は shares を返す。stETH はほぼ 1:1 なので amount_wei を近似値として使用
                return TxResult(
                    tx_hash=tx_hash.hex(),
                    success=True,
                    received_steth_wei=amount_wei,
                )
            return TxResult(
                tx_hash=tx_hash.hex(),
                success=False,
                error="トランザクション失敗（status=0）",
            )
        except Exception as exc:
            logger.exception("stake_eth 失敗: amount_wei=%d", amount_wei)
            return TxResult(success=False, error=str(exc))

    async def get_steth_balance(self, address: str) -> Decimal:
        """stETH 残高取得（ETH単位）。"""
        self._ensure_initialized()
        try:
            from web3 import Web3  # noqa: PLC0415

            balance_wei: int = self._contract.functions.balanceOf(
                Web3.to_checksum_address(address)
            ).call()
            return Decimal(balance_wei) / _WEI_PER_ETH
        except Exception as exc:
            logger.exception("get_steth_balance 失敗: address=%s", address[:10])
            raise RuntimeError(f"stETH 残高取得失敗: {exc}") from exc

    async def get_staking_apr(self) -> Decimal:
        """Lido staking APR を推定する（オンチェーンデータから計算）。

        PoC 実装: testnet では固定値を返す。
        本番では Lido API または イベントログから計算する。
        """
        self._ensure_initialized()
        # testnet / PoC: 推定値を返す（Lido mainnet APR の参考値 ~3.5%）
        logger.info("get_staking_apr: testnet のため推定値 3.5%% を返します")
        return Decimal("3.5")

    async def get_steth_eth_ratio(self) -> Decimal:
        """stETH/ETH レートを取得（getTotalPooledEther / getTotalShares）。"""
        self._ensure_initialized()
        try:
            total_pooled: int = self._contract.functions.getTotalPooledEther().call()
            total_shares: int = self._contract.functions.getTotalShares().call()
            if total_shares == 0:
                return Decimal("1")
            return Decimal(total_pooled) / Decimal(total_shares)
        except Exception as exc:
            logger.exception("get_steth_eth_ratio 失敗")
            raise RuntimeError(f"stETH/ETH レート取得失敗: {exc}") from exc


class DummyLidoClient(AbstractLidoClient):
    """テスト・サンドボックス用 Lido スタブクライアント。"""

    def __init__(self, config: LidoConfig) -> None:
        self._config = config
        logger.info("DummyLidoClient initialized（sandbox モード）")

    async def stake_eth(self, amount_wei: int) -> TxResult:
        """ETH → stETH ステーキングのシミュレーション。"""
        logger.info("DummyLidoClient.stake_eth: amount_wei=%d（シミュレーション）", amount_wei)
        return TxResult(
            tx_hash="0x" + "ab" * 32,
            success=True,
            received_steth_wei=amount_wei,  # 1:1 ratio
        )

    async def get_steth_balance(self, address: str) -> Decimal:
        """常に 1.0 stETH を返すスタブ。"""
        return Decimal("1.0")

    async def get_staking_apr(self) -> Decimal:
        """固定 APR 3.5% を返すスタブ。"""
        return Decimal("3.5")

    async def get_steth_eth_ratio(self) -> Decimal:
        """完全ペグ（1.0）を返すスタブ。"""
        return Decimal("1.0")


def get_lido_client(config: LidoConfig) -> AbstractLidoClient:
    """設定に基づいて適切な LidoClient を返す。"""
    import os  # noqa: PLC0415

    app_env = os.getenv("APP_ENV", "development")
    if app_env in ("staging", "production") and config.sandbox:
        logger.error("DummyClient is forbidden in %s environment", app_env)
        raise RuntimeError(f"DummyClient cannot be used in {app_env} environment")
    if config.sandbox:
        logger.warning("Using DummyClient — not for production")
        return DummyLidoClient(config)
    return LidoClient(config)
