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
from .schemas import ClaimWithdrawalResult, TxResult, WithdrawalRequestResult, WithdrawalStatus

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

# Lido WithdrawalQueueERC721 ABI（requestWithdrawals / claimWithdrawals(hints方式) / view）
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
        "name": "claimWithdrawals",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_requestIds", "type": "uint256[]"},
            {"name": "_hints", "type": "uint256[]"},
        ],
        "outputs": [],
    },
    {
        "name": "findCheckpointHints",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "_requestIds", "type": "uint256[]"},
            {"name": "_firstIndex", "type": "uint256"},
            {"name": "_lastIndex", "type": "uint256"},
        ],
        "outputs": [{"name": "hintIds", "type": "uint256[]"}],
    },
    {
        "name": "getLastCheckpointIndex",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
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

# chain 名 → EVM chain_id。未署名 tx 構築時に RPC を叩かず chain_id を解決するためのマップ
# （tx builder で RPC ラウンドトリップ・ネットワーク失敗を避ける）。未知 chain は mainnet(1)。
_CHAIN_ID_MAP: dict[str, int] = {
    "mainnet": 1,
    "ethereum": 1,
    "holesky": 17000,
    "hoodi": 560048,
    "sepolia": 11155111,
}


def _resolve_chain_id(chain: str) -> int:
    """config の chain 名から chain_id を解決する。

    未署名 tx に焼き込む chainId を mainnet(1) へサイレント fallback すると、testnet/L2 上の
    partner に誤って mainnet ETH stake を署名させる事故になる。未知 chain 名は fail-closed で
    ValueError を送出し、誤ネットワークの tx を組ませない（呼び出し側で 500 に変換される）。
    """
    chain_id = _CHAIN_ID_MAP.get(chain.lower())
    if chain_id is None:
        raise ValueError(
            f"未知の LIDO_CHAIN '{chain}' です。chainId を解決できません "
            f"(対応: {sorted(_CHAIN_ID_MAP)})。誤ネットワーク署名を防ぐため fail-closed。"
        )
    return chain_id


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
        """stETH 引き出しリクエスト送信（WithdrawalQueue への委譲）。"""
        if asset not in ("ETH", "stETH"):
            return TransactionResult(
                success=False,
                tx_hash=None,
                amount=amount,
                error=f"Lido withdraw は ETH/stETH のみサポートしています。指定: {asset}",
            )
        amount_wei = int(amount * _WEI_PER_ETH)
        result = await self.request_withdrawals([amount_wei])
        return TransactionResult(
            success=result.success,
            tx_hash=result.tx_hash,
            amount=amount,
            error=result.error,
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
    def build_stake_tx(self, amount_wei: int, from_address: str) -> dict[str, Any]:
        """パートナー本人署名用: 未署名の stake (submit) トランザクションを構築して返す。

        サーバー鍵では署名・broadcast しない。フロントエンドが Privy sendTransaction()
        で本人署名・送信する非カストディアル経路。``stake_eth`` と異なり
        ``wallet_private_key`` を一切参照しない。

        Args:
            amount_wei: ステークする ETH 量（Wei 単位）。submit に ``value`` として添付する。
            from_address: 署名者（partner 本人）のウォレットアドレス。

        Returns:
            {"to", "data", "from", "chainId", "value"} 形式の未署名 tx dict。
            ``value`` は添付 ETH（amount_wei）を 16 進文字列で格納する。
        """
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
    async def request_withdrawals(self, amounts_wei: list[int]) -> WithdrawalRequestResult:
        """stETH 引き出しリクエストを WithdrawalQueue に送信する。

        Args:
            amounts_wei: 引き出すstETH量のリスト（Wei単位）。
                         事前に stETH.approve(withdrawalQueueAddress, sum(amounts_wei)) が必要。

        Returns:
            WithdrawalRequestResult: リクエスト結果（request_ids を含む）。
        """
        ...

    @abstractmethod
    async def claim_withdrawals(self, request_ids: list[int]) -> ClaimWithdrawalResult:
        """finalized した withdrawal request をクレームし ETH を受け取る（checkpoint hints 方式）。

        Args:
            request_ids: クレームする withdrawal request ID のリスト。
                         対象 request が isFinalized=True になっていること。

        Returns:
            ClaimWithdrawalResult: クレーム結果。
        """
        ...

    @abstractmethod
    async def get_withdrawal_status(self, request_ids: list[int]) -> list[WithdrawalStatus]:
        """withdrawal request の現在のステータスを取得する。

        Args:
            request_ids: 確認する request ID のリスト。

        Returns:
            list[WithdrawalStatus]: 各リクエストのステータス一覧。
        """
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

    def build_stake_tx(self, amount_wei: int, from_address: str) -> dict[str, Any]:
        """パートナー本人署名用の未署名 stake (submit) tx を構築して返す。

        ``stake_eth`` から ``sign_transaction`` / ``send_raw_transaction`` を取り除いた
        非カストディアル版。submit(referral=0) の calldata を encode し、添付 ETH は
        ``value`` に格納する。サーバー秘密鍵を一切参照しない。
        """
        self._ensure_initialized()
        from web3 import Web3  # noqa: PLC0415

        if not from_address:
            raise ValueError("from_address は必須です (partner 署名)")
        if amount_wei <= 0:
            raise ValueError("amount_wei は正の整数である必要があります")

        checksum_from = Web3.to_checksum_address(from_address)
        # chain_id は config の chain 名から解決する（RPC を叩かない）。
        chain_id = _resolve_chain_id(self._config.chain)
        # submit(_referral=0x0) の calldata を生成（web3.py v7: encode_abi）。
        submit_data = self._contract.encode_abi(
            "submit",
            args=[Web3.to_checksum_address("0x0000000000000000000000000000000000000000")],
        )
        return {
            "to": Web3.to_checksum_address(self._config.steth_contract_address),
            "data": submit_data,
            "from": checksum_from,
            "chainId": chain_id,
            # submit は payable。ステークする ETH を value として添付する。
            "value": hex(amount_wei),
        }

    async def request_withdrawals(self, amounts_wei: list[int]) -> WithdrawalRequestResult:
        """stETH 引き出しリクエストを WithdrawalQueue に送信する。

        引き出しフロー:
        1. stETH.approve(withdrawalQueueAddress, sum(amounts_wei)) + receipt 待ち
        2. WithdrawalQueueERC721.requestWithdrawals(amounts_wei, owner)

        Args:
            amounts_wei: 引き出すstETH量のリスト（Wei単位）。

        Returns:
            WithdrawalRequestResult: リクエスト結果（request_ids を含む）。
        """
        self._ensure_initialized()
        try:
            from web3 import Web3  # noqa: PLC0415

            if not self._config.wallet_private_key:
                return WithdrawalRequestResult(
                    success=False,
                    error="LIDO_WALLET_PRIVATE_KEY が未設定",
                )

            if not amounts_wei:
                return WithdrawalRequestResult(
                    success=False,
                    error="amounts_wei は空にできません",
                )

            account = self._w3.eth.account.from_key(self._config.wallet_private_key)
            total_amount_wei = sum(amounts_wei)
            queue_address = Web3.to_checksum_address(self._config.withdrawal_queue_address)
            gas_price = self._w3.eth.gas_price

            # Step 1: stETH.approve(withdrawalQueueAddress, total_amount_wei) + receipt 待ち
            nonce = self._w3.eth.get_transaction_count(account.address)
            approve_tx = self._contract.functions.approve(
                queue_address, total_amount_wei
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
            approve_tx_hash = self._w3.eth.send_raw_transaction(signed_approve.raw_transaction)
            self._w3.eth.wait_for_transaction_receipt(approve_tx_hash, timeout=120)
            logger.info("stETH approve 完了: total_amount_wei=%d", total_amount_wei)

            # Step 2: WithdrawalQueue.requestWithdrawals(amounts_wei, owner)
            queue_contract = self._w3.eth.contract(address=queue_address, abi=_WITHDRAWAL_QUEUE_ABI)
            nonce2 = nonce + 1
            withdraw_tx = queue_contract.functions.requestWithdrawals(
                amounts_wei, account.address
            ).build_transaction(
                {
                    "from": account.address,
                    "nonce": nonce2,
                    "gasPrice": gas_price,
                    "gas": 200_000 + 50_000 * len(amounts_wei),
                }
            )
            signed_withdraw = self._w3.eth.account.sign_transaction(
                withdraw_tx, self._config.wallet_private_key
            )
            tx_hash = self._w3.eth.send_raw_transaction(signed_withdraw.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt["status"] == 1:
                logger.info(
                    "引き出しリクエスト成功: amounts=%s, tx=%s",
                    amounts_wei,
                    tx_hash.hex(),
                )
                return WithdrawalRequestResult(
                    tx_hash=tx_hash.hex(),
                    success=True,
                    request_ids=[],  # event decode は別途実装
                )
            return WithdrawalRequestResult(
                tx_hash=tx_hash.hex(),
                success=False,
                error="引き出しリクエスト失敗（status=0）",
            )
        except Exception as exc:
            logger.exception("request_withdrawals 失敗: amounts_wei=%s", amounts_wei)
            return WithdrawalRequestResult(success=False, error=str(exc))

    async def claim_withdrawals(self, request_ids: list[int]) -> ClaimWithdrawalResult:
        """finalized した withdrawal request をクレームし ETH を受け取る（checkpoint hints 方式）。

        フロー:
        1. getLastCheckpointIndex()
        2. findCheckpointHints(request_ids, 1, lastCheckpointIndex)
        3. claimWithdrawals(request_ids, hints)

        Args:
            request_ids: クレームする withdrawal request ID のリスト。

        Returns:
            ClaimWithdrawalResult: クレーム結果。
        """
        self._ensure_initialized()
        try:
            from web3 import Web3  # noqa: PLC0415

            if not self._config.wallet_private_key:
                return ClaimWithdrawalResult(
                    success=False,
                    error="LIDO_WALLET_PRIVATE_KEY が未設定",
                )

            if not request_ids:
                return ClaimWithdrawalResult(
                    success=False,
                    error="request_ids は空にできません",
                )

            account = self._w3.eth.account.from_key(self._config.wallet_private_key)
            queue_address = Web3.to_checksum_address(self._config.withdrawal_queue_address)
            queue_contract = self._w3.eth.contract(address=queue_address, abi=_WITHDRAWAL_QUEUE_ABI)
            gas_price = self._w3.eth.gas_price

            # Step 1: checkpoint hints を取得
            last_checkpoint_index: int = queue_contract.functions.getLastCheckpointIndex().call()
            hints: list[int] = queue_contract.functions.findCheckpointHints(
                request_ids, 1, last_checkpoint_index
            ).call()

            # Step 2: claimWithdrawals(request_ids, hints)
            nonce = self._w3.eth.get_transaction_count(account.address)
            claim_tx = queue_contract.functions.claimWithdrawals(
                request_ids, hints
            ).build_transaction(
                {
                    "from": account.address,
                    "nonce": nonce,
                    "gasPrice": gas_price,
                    "gas": 150_000 + 50_000 * len(request_ids),
                }
            )
            signed_claim = self._w3.eth.account.sign_transaction(
                claim_tx, self._config.wallet_private_key
            )
            tx_hash = self._w3.eth.send_raw_transaction(signed_claim.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt["status"] == 1:
                logger.info(
                    "withdrawal claim 成功: request_ids=%s, tx=%s", request_ids, tx_hash.hex()
                )
                return ClaimWithdrawalResult(
                    tx_hash=tx_hash.hex(),
                    success=True,
                    claimed_request_ids=request_ids,
                )
            return ClaimWithdrawalResult(
                tx_hash=tx_hash.hex(),
                success=False,
                error="claim 失敗（status=0）",
            )
        except Exception as exc:
            logger.exception("claim_withdrawals 失敗: request_ids=%s", request_ids)
            return ClaimWithdrawalResult(success=False, error=str(exc))

    async def get_withdrawal_status(self, request_ids: list[int]) -> list[WithdrawalStatus]:
        """withdrawal request の現在のステータスを取得する。

        Args:
            request_ids: 確認する request ID のリスト。

        Returns:
            list[WithdrawalStatus]: 各リクエストのステータス一覧。
        """
        self._ensure_initialized()
        try:
            from web3 import Web3  # noqa: PLC0415

            queue_address = Web3.to_checksum_address(self._config.withdrawal_queue_address)
            queue_contract = self._w3.eth.contract(address=queue_address, abi=_WITHDRAWAL_QUEUE_ABI)

            raw_statuses: list[Any] = queue_contract.functions.getWithdrawalStatus(
                request_ids
            ).call()

            result: list[WithdrawalStatus] = []
            for req_id, raw in zip(request_ids, raw_statuses, strict=True):
                result.append(
                    WithdrawalStatus(
                        request_id=req_id,
                        amount_of_steth=Decimal(raw[0]) / _WEI_PER_ETH,
                        amount_of_shares=Decimal(raw[1]) / _WEI_PER_ETH,
                        owner=raw[2],
                        timestamp=int(raw[3]),
                        is_finalized=bool(raw[4]),
                        is_claimed=bool(raw[5]),
                    )
                )
            return result
        except Exception as exc:
            logger.exception("get_withdrawal_status 失敗: request_ids=%s", request_ids)
            raise RuntimeError(f"withdrawal ステータス取得失敗: {exc}") from exc

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

    def build_stake_tx(self, amount_wei: int, from_address: str) -> dict[str, Any]:
        """未署名 stake tx 構築のスタブ（web3 不要・秘密鍵不参照）。"""
        if not from_address:
            raise ValueError("from_address は必須です (partner 署名)")
        if amount_wei <= 0:
            raise ValueError("amount_wei は正の整数である必要があります")
        logger.info(
            "DummyLidoClient.build_stake_tx: amount_wei=%d, from=%s（シミュレーション）",
            amount_wei,
            from_address[:10],
        )
        return {
            "to": self._config.steth_contract_address,
            "data": "0x",
            "from": from_address,
            "chainId": _resolve_chain_id(self._config.chain),
            "value": hex(amount_wei),
        }

    async def get_steth_balance(self, address: str) -> Decimal:
        """常に 1.0 stETH を返すスタブ。"""
        return Decimal("1.0")

    async def get_staking_apr(self) -> Decimal:
        """固定 APR 3.5% を返すスタブ。"""
        return Decimal("3.5")

    async def get_steth_eth_ratio(self) -> Decimal:
        """完全ペグ（1.0）を返すスタブ。"""
        return Decimal("1.0")

    async def request_withdrawals(self, amounts_wei: list[int]) -> WithdrawalRequestResult:
        """引き出しリクエストのシミュレーション。"""
        logger.info(
            "DummyLidoClient.request_withdrawals: amounts_wei=%s（シミュレーション）", amounts_wei
        )
        if not amounts_wei:
            return WithdrawalRequestResult(
                success=False,
                error="amounts_wei は空にできません",
            )
        # ダミー request_ids（インデックス+1000 を使用）
        dummy_ids = list(range(1000, 1000 + len(amounts_wei)))
        return WithdrawalRequestResult(
            tx_hash="0x" + "cd" * 32,
            success=True,
            request_ids=dummy_ids,
        )

    async def claim_withdrawals(self, request_ids: list[int]) -> ClaimWithdrawalResult:
        """withdrawal claim のシミュレーション（実 on-chain write なし）。"""
        logger.info(
            "DummyLidoClient.claim_withdrawals: request_ids=%s（シミュレーション）", request_ids
        )
        if not request_ids:
            return ClaimWithdrawalResult(
                success=False,
                error="request_ids は空にできません",
            )
        return ClaimWithdrawalResult(
            tx_hash="0x" + "ef" * 32,
            success=True,
            claimed_request_ids=request_ids,
        )

    async def get_withdrawal_status(self, request_ids: list[int]) -> list[WithdrawalStatus]:
        """withdrawal ステータスのシミュレーション（全件 finalized 済みを返す）。"""
        logger.info(
            "DummyLidoClient.get_withdrawal_status: request_ids=%s（シミュレーション）",
            request_ids,
        )
        import time  # noqa: PLC0415

        return [
            WithdrawalStatus(
                request_id=req_id,
                amount_of_steth=Decimal("1.0"),
                amount_of_shares=Decimal("1.0"),
                owner="0x0000000000000000000000000000000000000001",
                timestamp=int(time.time()) - 86400,  # 1日前
                is_finalized=True,
                is_claimed=False,
            )
            for req_id in request_ids
        ]

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
