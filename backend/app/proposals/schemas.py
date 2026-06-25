# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/schemas.py
"""提案APIのスキーマ定義。"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProposalCreate(BaseModel):
    user_id: int
    ai_decision_id: Optional[int] = None
    operation: str
    asset: str
    amount: Decimal
    amount_usd: Decimal
    reason: str
    expected_hf_after: Optional[Decimal] = None
    estimated_gas_usd: Optional[Decimal] = None
    fee_rate: Optional[Decimal] = None
    fee_amount: Optional[Decimal] = None
    expires_at: Optional[datetime] = None
    # P0-2: 執行経路 (cex / onchain_aave)。未指定時は on-chain Aave (後方互換)。
    # 作成時のみ指定可、以後 immutable。
    execution_route: Optional[str] = None


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    ai_decision_id: Optional[int]
    operation: str
    asset: str
    # 提案元プロトコル ("aave" / "lido" / "pendle")。model/DB には存在するが
    # 従来 response schema 未露出のため、フロントの protocol バッジ・lido 注記・
    # operation 別表示が機能しなかった (NULL=従来 Aave 既定フロー)。
    protocol: Optional[str] = None
    amount: Decimal
    amount_usd: Decimal
    reason: str
    expected_hf_after: Optional[Decimal]
    estimated_gas_usd: Optional[Decimal]
    fee_rate: Optional[Decimal]
    fee_amount: Optional[Decimal]
    status: str
    execution_attempts: int = 0
    approved_at: Optional[datetime]
    rejected_at: Optional[datetime]
    executed_at: Optional[datetime]
    tx_hash: Optional[str]
    expected_from: Optional[str] = None
    expected_to: Optional[str] = None
    # P0-2: 執行経路 + CEX 経路の証跡 (on-chain 経路では NULL)。
    execution_route: str = "onchain_aave"
    cex_order_id: Optional[str] = None
    cex_response: Optional[str] = None
    error_message: Optional[str] = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ProposalListResponse(BaseModel):
    items: List[ProposalResponse]
    total: int


class AdminProposalItem(ProposalResponse):
    """管理者向け提案レスポンス（ユーザー名付き）。"""

    username: Optional[str] = None
    email: Optional[str] = None


class AdminProposalListResponse(BaseModel):
    items: List[AdminProposalItem]
    total: int
    page: int
    limit: int


class AdminProposalStats(BaseModel):
    """KPIカード用の提案統計。DB集計値なのでページネーションに依存しない。"""

    pending: int
    today_approved: int
    today_rejected: int
    expired: int


class UnsignedTx(BaseModel):
    """Privy経由でpartnerが署名する未署名トランザクション。"""

    to: str
    data: str
    from_address: str = Field(alias="from")
    chain_id: int = Field(alias="chainId")
    value: str = "0x0"

    model_config = ConfigDict(populate_by_name=True)


class PartnerUnsignedTxs(BaseModel):
    """build-tx エンドポイントのレスポンス。"""

    proposal_id: int
    operation: str  # "SUPPLY" / "WITHDRAW" / "STAKE_ETH" / "BUY_PT"
    wallet_address: str
    approve_tx: Optional[UnsignedTx] = None  # SUPPLY のみ
    supply_tx: Optional[UnsignedTx] = None  # SUPPLY のみ
    withdraw_tx: Optional[UnsignedTx] = None  # WITHDRAW のみ
    # 非カストディアル化 (Lido/Pendle)。サーバー鍵で署名・broadcast せず、
    # partner が Privy 本人署名する未署名 tx を返す。
    stake_tx: Optional[UnsignedTx] = None  # STAKE_ETH (Lido) のみ
    buy_pt_tx: Optional[UnsignedTx] = None  # BUY_PT (Pendle) のみ


class SubmitTxRequest(BaseModel):
    """submit-tx エンドポイントのリクエスト。"""

    tx_hash: str
    wallet_address: str
