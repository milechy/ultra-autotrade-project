# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/flash_loan_service.py
"""自己清算保護（Flash Loan デレバレッジ）の executor サービス層（第2スライス）。

第1スライスの純計算層（``self_liquidation``）の上に、ライブの Aave アカウントデータ
（HF / 担保 / 債務 / liquidation_threshold）を**読み取り**、保護発動の要否を判定して
デレバレッジ見積りを算出する **orchestration** を提供する。

本スライスは ``dry_run=True`` のみ実装する。on-chain での Flash Loan ブロードキャスト
（USDC borrow → repay → withdraw → flash loan repay の実 tx 署名・送信）は、秘密鍵と
write 経路を伴うため別の HUMAN-REVIEW スライスに隔離する（``dry_run=False`` は
``NotImplementedError``）。

副作用は一切なし: ``get_account_data``（read-only）のみ呼び出し、deposit/withdraw/borrow/
repay 等の write 系メソッドは呼ばない。金融計算は Decimal のみ（Rule 11）。HF / 緊急停止
フラグ / HARD_STOP(1.6) は読み取りのみで変更しない（Asana 1215620828227794 第2スライス）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.aave.client import AaveClientBase, AccountData
from app.aave.self_liquidation import (
    DEFAULT_TARGET_HF,
    DEFAULT_TRIGGER_HF,
    DeleverageQuote,
    compute_deleverage_quote,
    should_protect,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelfLiquidationExecution:
    """自己清算保護の実行（または dry-run シミュレーション）結果。"""

    executed: bool
    """保護アクション（dry-run 含む）が実行されたか。発動不要・実行不能なら False。"""

    dry_run: bool
    """True の場合は tx を送信していない（シミュレーションのみ）。"""

    tx_hash: Optional[str]
    """送信した tx のハッシュ。dry-run / 未実行の場合は None。"""

    quote: Optional[DeleverageQuote]
    """算出したデレバレッジ見積り。算出前に終了した場合は None。"""

    before_health_factor: Optional[Decimal]
    """実行判定時点の HF（監査・ログ用）。"""

    reason: str
    """判定理由（監査・ログ用）。"""


class FlashLoanSelfLiquidator:
    """ライブ Aave アカウントを読み取り、自己清算デレバレッジを orchestration する。

    read-only な ``get_account_data`` のみを呼び出し、計算は第1スライスの純関数に委譲する。
    """

    def __init__(
        self,
        client: AaveClientBase,
        *,
        trigger_hf: Decimal = DEFAULT_TRIGGER_HF,
        target_hf: Decimal = DEFAULT_TARGET_HF,
    ) -> None:
        self._client = client
        self._trigger_hf = trigger_hf
        self._target_hf = target_hf

    def execute_self_liquidation(
        self, wallet_address: str, *, dry_run: bool = True
    ) -> SelfLiquidationExecution:
        """HF を読み取り、必要なら自己清算デレバレッジを実行（dry-run）する。

        :param wallet_address: 対象ウォレットアドレス。
        :param dry_run: True（既定）の場合は tx を送信せずシミュレーションのみ。
        :raises NotImplementedError: ``dry_run=False``（on-chain 実行は別 HUMAN-REVIEW スライス）。
        """
        acct: AccountData = self._client.get_account_data(wallet_address)

        # fail-closed: liquidation_threshold が無いと安全な見積りができない。
        if acct.liquidation_threshold is None:
            return SelfLiquidationExecution(
                executed=False,
                dry_run=dry_run,
                tx_hash=None,
                quote=None,
                before_health_factor=acct.health_factor,
                reason="liquidation_threshold unavailable",
            )

        # fail-closed: HF が読めない場合も判定不能。
        if acct.health_factor is None:
            return SelfLiquidationExecution(
                executed=False,
                dry_run=dry_run,
                tx_hash=None,
                quote=None,
                before_health_factor=None,
                reason="health_factor unavailable",
            )

        if not should_protect(acct.health_factor, self._trigger_hf):
            return SelfLiquidationExecution(
                executed=False,
                dry_run=dry_run,
                tx_hash=None,
                quote=None,
                before_health_factor=acct.health_factor,
                reason="HF above trigger — no protection needed",
            )

        quote = compute_deleverage_quote(
            collateral_usd=acct.total_collateral_usd,
            debt_usd=acct.total_debt_usd,
            liquidation_threshold=acct.liquidation_threshold,
            target_hf=self._target_hf,
        )

        if not quote.feasible:
            return SelfLiquidationExecution(
                executed=False,
                dry_run=dry_run,
                tx_hash=None,
                quote=quote,
                before_health_factor=acct.health_factor,
                reason=quote.reason,
            )

        if dry_run:
            logger.info(
                "FlashLoanSelfLiquidator dry-run: wallet=%s before_hf=%s "
                "repay_debt_usd=%s flash_loan_fee_usd=%s collateral_withdraw_usd=%s "
                "projected_hf=%s",
                wallet_address,
                str(acct.health_factor),
                str(quote.repay_debt_usd),
                str(quote.flash_loan_fee_usd),
                str(quote.collateral_withdraw_usd),
                str(quote.projected_hf),
            )
            return SelfLiquidationExecution(
                executed=True,
                dry_run=True,
                tx_hash=None,
                quote=quote,
                before_health_factor=acct.health_factor,
                reason="dry-run: flash loan deleverage simulated",
            )

        raise NotImplementedError(
            "on-chain flash loan execution is a separate HUMAN-REVIEW slice. dry_run=True only."
        )
