# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/billing_adapter.py
"""課金ベンダー vendor-agnostic adapter (F-7)。

ベンダー未決定期間は ``StubBillingAdapter`` を使用し、ログのみ記録する。
課金ベンダー (Stripe / Paidy 等) が確定した時点で ``BillingVendorAdapter``
プロトコルを実装した adapter class を差し替えるだけで切り替え完了。

差込点: ``app.api.v1.fees.finalize_month_core(..., vendor_adapter=...)``

関連:
- ``app.fees.calculator`` (月次手数料計算エンジン、F-5)
- ``app.api.v1.fees.finalize_month_core`` (月次 finalize、F-7)
- ``docs/45_fee_model_v10_migration_plan.md`` §4 F-7 行
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChargeRequest:
    """課金リクエスト。``finalize_month_core`` から vendor adapter へ渡す。

    subscription_amount_jpy は Step 2 で確定した額。
    subscription_protected=True の月は ``finalize_month_core`` がリクエストを
    生成しないため、本 dataclass は subscription_protected=False のケースのみ受け取る。
    """

    user_id: int
    fee_transaction_id: int
    subscription_amount_jpy: Decimal
    calculation_month: date
    description: str = ""


@dataclass
class ChargeResult:
    """課金結果。vendor adapter から ``finalize_month_core`` へ返す。

    ``vendor_reference_id`` は DBに ``fee_transactions.vendor_reference_id`` として保存し、
    ベンダー側との突合に使う。
    """

    user_id: int
    fee_transaction_id: int
    success: bool
    vendor_reference_id: str | None = None
    error_message: str | None = None


@runtime_checkable
class BillingVendorAdapter(Protocol):
    """課金ベンダー抽象プロトコル (F-7 vendor-agnostic 差込点)。

    実装を swap するだけでベンダーを切り替えられる::

        finalize_month_core(..., vendor_adapter=StubBillingAdapter())
        finalize_month_core(..., vendor_adapter=StripeBillingAdapter(api_key=...))
        finalize_month_core(..., vendor_adapter=PaidyBillingAdapter(api_key=...))
    """

    def charge_subscription(self, request: ChargeRequest) -> ChargeResult:
        """サブスク月額料金を課金する。

        Args:
            request: 課金対象ユーザー・金額・月。

        Returns:
            成否 + ベンダー参照 ID (突合用)。
        """
        ...


class StubBillingAdapter:
    """ベンダー未定期間のスタブ実装。実課金は行わない (ログのみ)。

    課金ベンダーが確定した際は本クラスを本物の adapter に差し替える。
    差込点は ``finalize_month_core(..., vendor_adapter=StubBillingAdapter())``。
    """

    def charge_subscription(self, request: ChargeRequest) -> ChargeResult:
        logger.info(
            "BillingStub.charge_subscription: user_id=%d fee_tx_id=%d "
            "amount_jpy=%s month=%s [NO-OP: billing vendor not yet configured]",
            request.user_id,
            request.fee_transaction_id,
            request.subscription_amount_jpy,
            request.calculation_month,
        )
        return ChargeResult(
            user_id=request.user_id,
            fee_transaction_id=request.fee_transaction_id,
            success=True,
            vendor_reference_id=f"stub-{request.calculation_month}-u{request.user_id}",
        )
