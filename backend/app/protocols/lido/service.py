# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance サービス層（ビジネスロジック）。"""

from __future__ import annotations

import logging
from decimal import Decimal

from .client import AbstractLidoClient
from .config import LidoConfig
from .schemas import (
    LidoAprResponse,
    LidoClaimRequest,
    LidoClaimResponse,
    LidoStakeRequest,
    LidoStakeResponse,
    LidoStatus,
    LidoWithdrawalRequestsResponse,
    LidoWithdrawalStatusResponse,
    LidoWithdrawRequest,
    LidoWithdrawResponse,
)

logger = logging.getLogger(__name__)

_WEI_PER_ETH = Decimal("1000000000000000000")


class LidoService:
    """Lido ステーキングのビジネスロジック。"""

    def __init__(self, client: AbstractLidoClient, config: LidoConfig) -> None:
        self._client = client
        self._config = config

    async def stake(self, request: LidoStakeRequest) -> LidoStakeResponse:
        """ETH → stETH ステーキング実行。"""
        # 1. peg 乖離チェック
        ratio = await self._client.get_steth_eth_ratio()
        deviation_pct = abs(Decimal("1") - ratio) * Decimal("100")
        if deviation_pct > Decimal("2"):
            error_msg = (
                f"stETH/ETH peg deviation {deviation_pct}% exceeds "
                f"critical threshold (2%). Staking blocked."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        elif deviation_pct > Decimal(str(self._config.peg_deviation_warn_pct)):
            logger.warning(
                "stETH/ETH ペグ乖離警告: deviation=%.2f%% (閾値=%.2f%%)",
                float(deviation_pct),
                self._config.peg_deviation_warn_pct,
            )

        # 2. APR 取得
        staking_apr = await self._client.get_staking_apr()

        # 3. dry_run の場合はシミュレーションのみ
        if request.dry_run:
            logger.info(
                "LidoService.stake dry_run: amount_eth=%s, apr=%s%%",
                request.amount_eth,
                staking_apr,
            )
            return LidoStakeResponse(
                operation="STAKE",
                amount_eth=request.amount_eth,
                received_steth=request.amount_eth,  # 1:1 simulation
                tx_hash=None,
                staking_apr=staking_apr,
                dry_run=True,
            )

        # 4. 実行
        amount_wei = int(request.amount_eth * _WEI_PER_ETH)
        result = await self._client.stake_eth(amount_wei)

        if not result.success:
            logger.error("stake_eth 失敗: error=%s", result.error)
            raise RuntimeError(f"Lido ステーキング失敗: {result.error}")

        received_steth = Decimal(result.received_steth_wei) / _WEI_PER_ETH
        logger.info(
            "stake 成功: amount_eth=%s, received_steth=%s, tx=%s",
            request.amount_eth,
            received_steth,
            result.tx_hash,
        )
        return LidoStakeResponse(
            operation="STAKE",
            amount_eth=request.amount_eth,
            received_steth=received_steth,
            tx_hash=result.tx_hash,
            staking_apr=staking_apr,
            dry_run=False,
        )

    async def withdraw(self, request: LidoWithdrawRequest) -> LidoWithdrawResponse:
        """stETH 引き出しリクエスト送信。クレームは待機期間後に別途実行が必要。"""
        if request.dry_run:
            logger.info("LidoService.withdraw dry_run: amount_steth=%s", request.amount_steth)
            return LidoWithdrawResponse(
                operation="WITHDRAW_REQUEST",
                amount_steth=request.amount_steth,
                tx_hash=None,
                dry_run=True,
            )

        result = await self._client.withdraw(request.amount_steth, "stETH")
        if not result.success:
            logger.error("withdraw 失敗: error=%s", result.error)
            raise RuntimeError(f"Lido 引き出しリクエスト失敗: {result.error}")

        logger.info(
            "withdraw リクエスト成功: amount=%s, tx=%s",
            request.amount_steth,
            result.tx_hash,
        )
        return LidoWithdrawResponse(
            operation="WITHDRAW_REQUEST",
            amount_steth=request.amount_steth,
            tx_hash=result.tx_hash,
            dry_run=False,
        )

    async def claim(self, request: LidoClaimRequest) -> LidoClaimResponse:
        """引き出しクレーム実行（finalized 済みリクエストに対して呼ぶ）。

        checkpoint hints 方式: getLastCheckpointIndex → findCheckpointHints → claimWithdrawals。
        claimed_eth は get_withdrawal_status の amount_of_steth 合算から概算する（dry_run 時は None）。
        """
        if request.dry_run:
            logger.info("LidoService.claim dry_run: request_ids=%s", request.request_ids)
            return LidoClaimResponse(
                operation="CLAIM",
                request_ids=request.request_ids,
                tx_hash=None,
                dry_run=True,
                claimed_eth=None,
            )

        # claimed_eth の概算: クレーム前にステータスを取得して amountOfStETH を合算
        claimed_eth: Decimal | None = None
        try:
            statuses = await self._client.get_withdrawal_status(request.request_ids)
            claimed_eth = sum((s.amount_of_steth for s in statuses), Decimal("0"))
        except Exception as exc:
            logger.warning("claimed_eth 概算取得失敗（無視して続行）: %s", exc)

        result = await self._client.claim_withdrawals(request.request_ids)
        if not result.success:
            logger.error(
                "claim_withdrawals 失敗: request_ids=%s, error=%s",
                request.request_ids,
                result.error,
            )
            raise RuntimeError(f"Lido クレーム失敗: {result.error}")

        logger.info(
            "claim 成功: request_ids=%s, tx=%s, claimed_eth=%s",
            request.request_ids,
            result.tx_hash,
            claimed_eth,
        )
        return LidoClaimResponse(
            operation="CLAIM",
            request_ids=request.request_ids,
            tx_hash=result.tx_hash,
            dry_run=False,
            claimed_eth=claimed_eth,
        )

    async def get_withdrawal_status(self, request_ids: list[int]) -> LidoWithdrawalStatusResponse:
        """withdrawal request のステータス一覧を返す。"""
        statuses = await self._client.get_withdrawal_status(request_ids)
        return LidoWithdrawalStatusResponse(
            request_ids=request_ids,
            statuses=statuses,
        )

    async def get_withdrawal_requests(self, address: str) -> LidoWithdrawalRequestsResponse:
        """指定アドレスの未クレーム引き出しリクエスト ID 一覧を返す。"""
        request_ids = await self._client.get_withdrawal_requests(address)
        return LidoWithdrawalRequestsResponse(
            address=address,
            request_ids=request_ids,
        )

    async def get_status(self) -> LidoStatus:
        """Lido ステータス取得。"""
        wallet_address = self._config.wallet_address or "0x0000000000000000000000000000000000000000"

        steth_balance = await self._client.get_steth_balance(wallet_address)
        staking_apr = await self._client.get_staking_apr()
        ratio = await self._client.get_steth_eth_ratio()
        peg_deviation_pct = abs(Decimal("1") - ratio) * Decimal("100")

        return LidoStatus(
            steth_balance=steth_balance,
            staking_apr=staking_apr,
            steth_eth_ratio=ratio,
            peg_deviation_pct=peg_deviation_pct,
            chain=self._config.chain,
            sandbox=self._config.sandbox,
        )

    async def get_apr(self) -> LidoAprResponse:
        """現在の APR を返す。"""
        apr = await self._client.get_staking_apr()
        return LidoAprResponse(
            staking_apr=apr,
            source="lido_onchain" if not self._config.sandbox else "dummy",
        )
