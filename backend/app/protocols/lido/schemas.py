# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance Pydantic スキーマ定義。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LidoStakeRequest(BaseModel):
    """ステーキングリクエスト。"""

    amount_eth: Decimal = Field(..., gt=Decimal("0"), description="ステーキングするETH量")
    dry_run: bool = Field(True, description="Trueの場合シミュレーションのみ（デフォルト）")

    @field_validator("amount_eth", mode="before")
    @classmethod
    def validate_amount(cls, v: object) -> Decimal:
        return Decimal(str(v))


class LidoStakeResponse(BaseModel):
    """ステーキングレスポンス。"""

    operation: str = Field(..., description="'STAKE' or 'UNSTAKE'")
    amount_eth: Decimal
    received_steth: Decimal
    tx_hash: Optional[str] = None
    staking_apr: Decimal
    dry_run: bool


class LidoStatus(BaseModel):
    """Lido ステータス。"""

    steth_balance: Decimal
    staking_apr: Decimal
    steth_eth_ratio: Decimal = Field(..., description="stETH/ETH レート（1.0=完全ペグ）")
    peg_deviation_pct: Decimal = Field(..., description="ペグ乖離率（%）")
    chain: str
    sandbox: bool


class LidoAprResponse(BaseModel):
    """APR レスポンス。"""

    staking_apr: Decimal
    source: str


class TxResult(BaseModel):
    """トランザクション結果。"""

    tx_hash: Optional[str] = None
    success: bool
    received_steth_wei: int = 0
    error: Optional[str] = None


class LidoWithdrawRequest(BaseModel):
    """引き出しリクエスト（stETH → ETH 非同期引き出し）。"""

    amount_steth: Decimal = Field(..., gt=Decimal("0"), description="引き出す stETH 量")
    dry_run: bool = Field(True, description="True の場合シミュレーションのみ（デフォルト）")

    @field_validator("amount_steth", mode="before")
    @classmethod
    def validate_amount(cls, v: object) -> Decimal:
        return Decimal(str(v))


class LidoWithdrawResponse(BaseModel):
    """引き出しリクエスト送信結果。クレームは別途実行が必要。"""

    operation: str = Field("WITHDRAW_REQUEST", description="操作タイプ")
    amount_steth: Decimal
    tx_hash: Optional[str] = None
    dry_run: bool
    note: str = Field(
        default="引き出しリクエスト送信済み。クレームは待機期間（1〜5日）後に実行してください。",
        description="補足説明",
    )


class WithdrawalRequestResult(BaseModel):
    """withdrawal queue へのリクエスト送信結果。"""

    tx_hash: Optional[str] = None
    success: bool
    request_ids: list[int] = Field(default_factory=list, description="払い出しリクエストNFT ID一覧")
    error: Optional[str] = None


class WithdrawalStatus(BaseModel):
    """withdrawal request の状態。"""

    request_id: int
    amount_of_steth: Decimal = Field(..., description="引き出し対象 stETH 量（ETH単位）")
    amount_of_shares: Decimal = Field(..., description="対応するシェア量（ETH単位）")
    owner: str = Field(..., description="オーナーアドレス")
    timestamp: int = Field(..., description="リクエスト作成タイムスタンプ (Unix秒)")
    is_finalized: bool = Field(..., description="最終確定済みか")
    is_claimed: bool = Field(..., description="クレーム済みか")


class ClaimWithdrawalResult(BaseModel):
    """withdrawal claim 実行結果。"""

    tx_hash: Optional[str] = None
    success: bool
    claimed_request_ids: list[int] = Field(default_factory=list)
    error: Optional[str] = None


class LidoClaimRequest(BaseModel):
    """引き出しクレームリクエスト（finalized 済みリクエストに対して実行）。"""

    request_ids: list[int] = Field(
        ..., min_length=1, description="クレームする引き出しリクエスト ID 一覧"
    )
    dry_run: bool = Field(True, description="True の場合シミュレーションのみ（デフォルト）")


class LidoClaimResponse(BaseModel):
    """引き出しクレーム結果。"""

    operation: str = Field("CLAIM", description="操作タイプ")
    request_ids: list[int]
    tx_hash: Optional[str] = None
    dry_run: bool
    claimed_eth: Optional[Decimal] = Field(
        None, description="クレームした ETH 量の概算（dry_run 時は None）"
    )


class LidoWithdrawalStatusResponse(BaseModel):
    """withdrawal request ステータス一覧レスポンス。"""

    request_ids: list[int]
    statuses: list[WithdrawalStatus]


class LidoWithdrawalRequestsResponse(BaseModel):
    """引き出しリクエスト一覧レスポンス。"""

    address: str
    request_ids: list[int]


class CompoundYieldEstimate(BaseModel):
    """複合利回り推定値。"""

    lido_staking_apr: Decimal
    aave_supply_apr: Decimal
    compound_apr: Decimal
    amount_eth: Decimal
    estimated_annual_yield_eth: Decimal
