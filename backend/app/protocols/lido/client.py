# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance web3.py クライアント。"""

from __future__ import annotations

import logging
from abc import abstractmethod
from decimal import Decimal
from typing import Any

import httpx

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
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

# Lido WithdrawalQueueERC721 ABI（最小限: requestWithdrawals / claimWithdrawal / view）
_WITHDRAWAL_QUEUE_ABI: list[dict[str, Any]] = [
    {
        "name": "requestWithdrawals",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_amounts", "type": "uint256[]"},
            {"name": "_owner", "type": "address"},
        ],
        "outputs": [{"name": "requestIds", "type": "uint256[]"}],
    },
    {
        "name": "claimWithdrawal",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "_requestId", "type": "uint256"}],
        "outputs": [],
    },
    {
        "name": "getWithdrawalRequests",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "_owner", "type": "address"}],
        "outputs": [{"name": "requestsIds", "type": "uint256[]"}],
    },
    {
        "name": "getWithdrawalStatus",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "_requestIds", "type": "uint256[]"}],
        "outputs": [
            {
                "name": "statuses",
                "type": "tuple[]",
                "components": [
                    {"name": "amountOfStETH", "type": "uint256"},
                    {"name": "amountOfShares", "type": "uint256"},
                    {"name": "owner", "type": "address"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "isFinalized", "type": "bool"},
                    {"name": "isClaimed", "type": "bool"},
                ],
            }
        ],
    },
]

_WEI_PER_ETH = Decimal("1000000000000000000")


class AbstractLidoClient(BaseProtocolClient):
    """Lido クライアントの抽象基底クラス。"""

    _config: LidoConfig

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
        """ポジション情報を返す（設定ウォレットの stETH 残高）。

        value_usd は balance と同値の近似（stETH≈ETH 近似、USD 換算は将来課題）。
        wallet_address 未設定・残高取得失敗時は zero position を返す（fail-open）。
        """
        zero_position = ProtocolPosition(
            protocol_name=self.get_protocol_name(),
            asset="stETH",
            balance=Decimal("0"),
            value_usd=Decimal("0"),
        )
        wallet_address = self._config.wallet_address
        if not wallet_address:
            logger.warning("get_position: wallet_address 未設定のため zero position を返します")
            return zero_position
        try:
            balance = await self.get_steth_balance(wallet_address)
            return ProtocolPosition(
                protocol_name=self.get_protocol_name(),
                asset="stETH",
                balance=balance,
                value_usd=balance,
            )
        except Exception as exc:
            logger.warning(
                "get_position: 残高取得失敗のため zero position を返します (fail-open): %s",
                exc,
            )
            return zero_position

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

    @abstractmethod
    async def claim_withdrawal(self, request_id: int) -> TransactionResult:
        """WithdrawalQueue クレーム実行（待機完了後に呼ぶ）。"""
        ...

    @abstractmethod
    async def get_withdrawal_requests(self, address: str) -> list[int]:
        """指定アドレスの未クレーム引き出しリクエスト ID 一覧を返す。"""
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

    async def withdraw(self, amount: Decimal, asset: str) -> TransactionResult:
        """stETH → ETH 引き出しリクエスト（Lido WithdrawalQueue）。

        引き出しフロー:
        1. stETH.approve(withdrawalQueueAddress, amount_wei)
        2. WithdrawalQueueERC721.requestWithdrawals([amount_wei], owner)
        クレーム（claim）は待機期間後に別途実行が必要。
        """
        if asset not in ("ETH", "stETH"):
            return TransactionResult(
                success=False,
                tx_hash=None,
                amount=amount,
                error=f"Lido withdraw は ETH/stETH のみサポートしています。指定: {asset}",
            )
        self._ensure_initialized()
        try:
            from web3 import Web3  # noqa: PLC0415

            if not self._config.wallet_private_key:
                return TransactionResult(
                    success=False,
                    tx_hash=None,
                    amount=amount,
                    error="LIDO_WALLET_PRIVATE_KEY が未設定",
                )

            account = self._w3.eth.account.from_key(self._config.wallet_private_key)
            amount_wei = int(amount * _WEI_PER_ETH)
            queue_address = Web3.to_checksum_address(self._config.withdrawal_queue_address)
            gas_price = self._w3.eth.gas_price

            # Step 1: stETH.approve(withdrawalQueueAddress, amount_wei)
            nonce = self._w3.eth.get_transaction_count(account.address)
            approve_tx = self._contract.functions.approve(
                queue_address, amount_wei
            ).build_transaction(
                {
                    "from": account.address,
                    "nonce": nonce,
                    "gasPrice": gas_price,
                    "gas": 100_000,
                }
            )
            signed_approve = self._w3.eth.account.sign_transaction(
                approve_tx, self._config.wallet_private_key
            )
            self._w3.eth.send_raw_transaction(signed_approve.raw_transaction)
            logger.info("stETH approve 送信完了: amount_wei=%d", amount_wei)

            # Step 2: WithdrawalQueue.requestWithdrawals([amount_wei], owner)
            queue_contract = self._w3.eth.contract(address=queue_address, abi=_WITHDRAWAL_QUEUE_ABI)
            nonce2 = nonce + 1
            withdraw_tx = queue_contract.functions.requestWithdrawals(
                [amount_wei], account.address
            ).build_transaction(
                {
                    "from": account.address,
                    "nonce": nonce2,
                    "gasPrice": gas_price,
                    "gas": 200_000,
                }
            )
            signed_withdraw = self._w3.eth.account.sign_transaction(
                withdraw_tx, self._config.wallet_private_key
            )
            tx_hash = self._w3.eth.send_raw_transaction(signed_withdraw.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt["status"] == 1:
                logger.info(
                    "引き出しリクエスト成功: amount_wei=%d, tx=%s", amount_wei, tx_hash.hex()
                )
                return TransactionResult(
                    success=True,
                    tx_hash=tx_hash.hex(),
                    amount=amount,
                    error=None,
                )
            return TransactionResult(
                success=False,
                tx_hash=tx_hash.hex(),
                amount=amount,
                error="引き出しリクエスト失敗（status=0）",
            )
        except Exception as exc:
            logger.exception("withdraw 失敗: amount=%s", amount)
            return TransactionResult(success=False, tx_hash=None, amount=amount, error=str(exc))

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

    async def _fetch_apr_data(self) -> dict[str, Any]:
        """Lido 公式 API から stETH APR（SMA）データを取得する。"""
        url = f"{self._config.api_base_url}/v1/protocol/steth/apr/sma"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    async def get_staking_apr(self) -> Decimal:
        """Lido 公式 API から実 staking APR（%）を取得する。

        API 失敗・異常値（0 < apr <= 50 を外れる）の場合は参考値 3.5% に
        フォールバックし、例外は呼び出し元へ送出しない（fail-open 設計）。
        """
        try:
            data = await self._fetch_apr_data()
            apr = Decimal(str(data["data"]["smaApr"]))
            if Decimal("0") < apr <= Decimal("50"):
                return apr
            logger.warning(
                "get_staking_apr: 異常値 %s のためフォールバック値 3.5%% を返します", apr
            )
            return Decimal("3.5")
        except Exception as exc:
            logger.warning(
                "get_staking_apr: API 取得失敗のためフォールバック値 3.5%% を返します: %s", exc
            )
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

    async def claim_withdrawal(self, request_id: int) -> TransactionResult:
        """WithdrawalQueue のクレーム実行（requestId 指定）。

        引き出しリクエストが finalized 済みであることが前提。
        失敗時は TransactionResult(success=False, ...) を返す（fail-open）。
        """
        self._ensure_initialized()
        try:
            from web3 import Web3  # noqa: PLC0415

            if not self._config.wallet_private_key:
                return TransactionResult(
                    success=False,
                    tx_hash=None,
                    amount=Decimal("0"),
                    error="LIDO_WALLET_PRIVATE_KEY が未設定",
                )

            account = self._w3.eth.account.from_key(self._config.wallet_private_key)
            queue_address = Web3.to_checksum_address(self._config.withdrawal_queue_address)
            queue_contract = self._w3.eth.contract(address=queue_address, abi=_WITHDRAWAL_QUEUE_ABI)

            nonce = self._w3.eth.get_transaction_count(account.address)
            gas_price = self._w3.eth.gas_price

            tx = queue_contract.functions.claimWithdrawal(request_id).build_transaction(
                {
                    "from": account.address,
                    "nonce": nonce,
                    "gasPrice": gas_price,
                    "gas": 200_000,
                }
            )
            signed = self._w3.eth.account.sign_transaction(tx, self._config.wallet_private_key)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt["status"] == 1:
                logger.info(
                    "claim_withdrawal 成功: request_id=%d, tx=%s", request_id, tx_hash.hex()
                )
                return TransactionResult(
                    success=True,
                    tx_hash=tx_hash.hex(),
                    amount=Decimal("0"),
                    error=None,
                )
            return TransactionResult(
                success=False,
                tx_hash=tx_hash.hex(),
                amount=Decimal("0"),
                error="クレームトランザクション失敗（status=0）",
            )
        except Exception as exc:
            logger.exception("claim_withdrawal 失敗: request_id=%d", request_id)
            return TransactionResult(
                success=False, tx_hash=None, amount=Decimal("0"), error=str(exc)
            )

    async def get_withdrawal_requests(self, address: str) -> list[int]:
        """指定アドレスの未クレーム引き出しリクエスト ID 一覧を返す（view）。"""
        self._ensure_initialized()
        try:
            from web3 import Web3  # noqa: PLC0415

            queue_address = Web3.to_checksum_address(self._config.withdrawal_queue_address)
            queue_contract = self._w3.eth.contract(address=queue_address, abi=_WITHDRAWAL_QUEUE_ABI)
            request_ids: list[int] = queue_contract.functions.getWithdrawalRequests(
                Web3.to_checksum_address(address)
            ).call()
            return request_ids
        except Exception as exc:
            logger.exception("get_withdrawal_requests 失敗: address=%s", address[:10])
            raise RuntimeError(f"引き出しリクエスト一覧取得失敗: {exc}") from exc


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

    async def withdraw(self, amount: Decimal, asset: str) -> TransactionResult:
        """stETH 引き出しリクエストのシミュレーション。"""
        logger.info("DummyLidoClient.withdraw: amount=%s %s（シミュレーション）", amount, asset)
        return TransactionResult(
            success=True,
            tx_hash="0x" + "cd" * 32,
            amount=amount,
            error=None,
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

    async def claim_withdrawal(self, request_id: int) -> TransactionResult:
        """クレームのシミュレーション（実 on-chain write なし）。"""
        logger.info(
            "DummyLidoClient.claim_withdrawal: request_id=%d（シミュレーション）", request_id
        )
        return TransactionResult(
            success=True,
            tx_hash="0x" + "ef" * 32,
            amount=Decimal("0"),
            error=None,
        )

    async def get_withdrawal_requests(self, address: str) -> list[int]:
        """固定の requestId 一覧を返すスタブ。"""
        logger.info(
            "DummyLidoClient.get_withdrawal_requests: address=%s（シミュレーション）",
            address[:10] if address else "N/A",
        )
        return [1, 2, 3]


def get_lido_client(config: LidoConfig) -> AbstractLidoClient:
    """設定に基づいて適切な LidoClient を返す。"""
    import os  # noqa: PLC0415

    app_env = os.getenv("APP_ENV", "development")
    if app_env == "production" and config.sandbox:
        logger.error("DummyClient is forbidden in %s environment", app_env)
        raise RuntimeError(f"DummyClient cannot be used in {app_env} environment")
    if config.sandbox:
        logger.warning("Using DummyClient — not for production")
        return DummyLidoClient(config)
    return LidoClient(config)
