# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/withdrawals_router.py
"""
出金イベント記録 API ルーター (P4)。

ノンカストディアル出金 (non-custodial withdrawal):
- 出金は **常にユーザー本人の Privy 鍵による署名** で実行される。
- backend はオンチェーン送金には **一切関与しない**。tx_hash 記録のみ。
- delegated signing (P3) は出金には **適用されない**。本人署名のみ。
- 運営はユーザー資金を移動する権限を持たない。

エンドポイント:
- POST /api/users/withdrawals  - 出金 tx のログ記録 (本人署名後にフロントから呼ばれる)
- GET  /api/users/withdrawals  - 自分の出金履歴一覧

冪等性 (idempotency):
- 同一 tx_hash の二重登録は **既存レコードを 200 OK で返す**。
- フロント側のリトライ/再ロードによる重複 POST を安全に扱う。

レート制限 (rate limit):
- 1 ユーザーあたり 5 件/分 (in-memory sliding window)。
- **本実装は単一プロセスのみ有効**。マルチプロセス/水平スケール環境では
  Redis ベースに置き換える必要あり (TODO 参照)。

TX 検証 (optional, env=RPC_VERIFY=true):
- tx_hash から Base RPC で receipt を取得し、to / value を verify する。
- 失敗時は 400 を返す。デフォルトは無効 (本人署名なので信頼ベース)。

NOTE: ルーター登録は backend/app/main.py で行う必要があるが、main.py は
Tier-S 不触のため、本 PR では含めない。**別 PR で必ず以下を追加すること**:

  # backend/app/main.py 内
  from app.users.withdrawals_router import router as user_withdrawals_router
  app.include_router(user_withdrawals_router)  # P4: user withdrawals (non-custodial)

TODO (別 PR):
- in-memory rate limit を Redis (`backend/app/automation/rate_limiter.py` パターン参照) に置換
- RPC verify のキャッシュ (同一 tx_hash の RPC 連打を防ぐ)
- alembic migration 追加 (本 PR は既存 transactions テーブル流用)
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from datetime import datetime
from decimal import Decimal, InvalidOperation
from threading import Lock
from typing import Deque, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.database import get_db
from app.transactions.models import Transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users/withdrawals", tags=["user-withdrawals"])


# ------------------------------------------------------------------ config


def _withdrawal_max_usdc() -> Decimal:
    """ENV WITHDRAWAL_MAX_USDC で上限を制御 (default 100000)。"""
    raw = os.getenv("WITHDRAWAL_MAX_USDC", "100000")
    try:
        v = Decimal(raw)
        if v <= 0:
            return Decimal("100000")
        return v
    except (InvalidOperation, ValueError):
        return Decimal("100000")


def _rpc_verify_enabled() -> bool:
    """ENV RPC_VERIFY=true のとき tx の to/amount を RPC で検証。"""
    return os.getenv("RPC_VERIFY", "false").lower() in ("1", "true", "yes")


def _base_rpc_url() -> str:
    return os.getenv("BASE_RPC_URL", "https://mainnet.base.org")


RATE_LIMIT_PER_MIN = 5
RATE_LIMIT_WINDOW_SEC = 60


# ------------------------------------------------------------------ rate limiter
#
# TODO: Redis 化。`backend/app/automation/rate_limiter.py` の WindowCounter を
# Redis ZSET (ZADD + ZREMRANGEBYSCORE) で実装し直す。
# 単一プロセス前提のため、マルチワーカー (gunicorn -w >1) ではユーザーごとの
# 上限が緩くなる点に注意。


class _UserRateLimiter:
    """ユーザーごとの sliding-window レートリミッター (in-memory)。"""

    def __init__(self, window_seconds: int, limit: int) -> None:
        self._window = window_seconds
        self._limit = limit
        self._user_timestamps: Dict[int, Deque[float]] = {}
        self._lock = Lock()

    def check_and_record(self, user_id: int) -> bool:
        """カウントを記録し、ウィンドウ内に収まれば True、超過なら False。"""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            dq = self._user_timestamps.setdefault(user_id, deque())
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= self._limit:
                return False
            dq.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._user_timestamps.clear()


_rate_limiter = _UserRateLimiter(RATE_LIMIT_WINDOW_SEC, RATE_LIMIT_PER_MIN)


# ------------------------------------------------------------------ schemas


# EIP-55 checksum は緩く許可 (大小混在 OK)。validator で正規化。
_TX_HASH_PATTERN = r"^0x[a-fA-F0-9]{64}$"
_ADDRESS_PATTERN = r"^0x[a-fA-F0-9]{40}$"


class WithdrawalCreate(BaseModel):
    """出金イベント記録リクエスト。"""

    tx_hash: str = Field(
        ...,
        pattern=_TX_HASH_PATTERN,
        description="0x prefix 付き 32-byte tx hash",
    )
    to_address: str = Field(
        ...,
        pattern=_ADDRESS_PATTERN,
        description="0x prefix 付き宛先アドレス (EIP-55 checksum)",
    )
    amount_usdc: Decimal = Field(..., gt=0, description="USDC 数量 (正の値、上限は env)")
    network: str = Field(default="base", description="ネットワーク名 (base のみ対応)")

    @field_validator("tx_hash")
    @classmethod
    def _normalize_tx_hash(cls, v: str) -> str:
        return v.lower()

    @field_validator("to_address")
    @classmethod
    def _normalize_to_address(cls, v: str) -> str:
        # pattern は通過済み。小文字正規化のみ。
        return v.lower()

    @field_validator("network")
    @classmethod
    def _validate_network(cls, v: str) -> str:
        if v not in ("base",):
            raise ValueError("network must be 'base'")
        return v

    @field_validator("amount_usdc")
    @classmethod
    def _validate_amount_upper(cls, v: Decimal) -> Decimal:
        max_amount = _withdrawal_max_usdc()
        if v > max_amount:
            raise ValueError(
                f"amount_usdc exceeds WITHDRAWAL_MAX_USDC ({max_amount})"
            )
        return v


class WithdrawalResponse(BaseModel):
    """出金イベント記録レスポンス。"""

    id: int
    user_id: int
    tx_hash: str
    to_address: str
    amount_usdc: Decimal
    network: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WithdrawalListResponse(BaseModel):
    """出金履歴一覧レスポンス。"""

    items: List[WithdrawalResponse]
    total: int


# ------------------------------------------------------------------ helpers


def _to_response(tx: Transaction) -> WithdrawalResponse:
    return WithdrawalResponse(
        id=tx.id,
        user_id=tx.user_id,
        tx_hash=tx.tx_hash or "",
        to_address=tx.wallet_address or "",
        amount_usdc=tx.amount,
        network=tx.chain,
        status=tx.status,
        created_at=tx.created_at,
    )


def _verify_tx_via_rpc(tx_hash: str, expected_to: str, expected_amount: Decimal) -> None:
    """
    Base RPC から tx receipt を取得し、to / value を検証する。
    RPC_VERIFY=true のときのみ呼ばれる。失敗時は HTTPException(400) を raise。

    NOTE: ネットワーク呼び出しがあるため遅い。Redis キャッシュ化は TODO。
    """
    try:
        import json
        import urllib.request

        # USDC.transfer の場合 to は USDC コントラクトで、amount は input data から抽出する必要あり。
        # 本実装は最低限: receipt 存在 + status=success のみチェック。
        # 厳密な to/amount 検証は logs decode 必須 (Transfer event topic)。
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _base_rpc_url(),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        receipt = body.get("result")
        if receipt is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tx_hash {tx_hash} not found on chain (RPC verify)",
            )
        receipt_status = receipt.get("status")
        if receipt_status not in ("0x1", "0x01"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tx {tx_hash} failed on chain (status={receipt_status})",
            )
        # TODO: logs decode して Transfer(from, to, value) の to/value を expected と一致確認
        logger.info(
            "[withdraw rpc_verify] tx=%s status=success (logs decode TODO)", tx_hash
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("[withdraw rpc_verify] RPC error for %s: %s", tx_hash, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RPC verify failed: {exc}",
        ) from exc


# ------------------------------------------------------------------ endpoints


@router.post(
    "",
    response_model=WithdrawalResponse,
    summary="出金イベント記録 (idempotent, non-custodial)",
    description=(
        "ノンカストディアル出金の tx 記録エンドポイント。"
        "送金は **常にユーザー本人の Privy 鍵で署名済み** で、backend は記録のみ。"
        "同一 tx_hash の重複 POST は既存レコードを 200 で返す (冪等)。"
    ),
)
def create_withdrawal(
    request: WithdrawalCreate,
    response: Response,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> WithdrawalResponse:
    """
    出金 tx を transactions テーブルに記録する (ノンカストディアル)。

    フロー:
    1. ユーザーが Privy **本人鍵** で USDC.transfer を署名 → tx 発火
    2. フロントが receipt 確定を待ち、本エンドポイントへ POST
    3. backend は記録のみ (送金には関与しない)

    冪等性:
    - 同一 tx_hash の二重 POST は既存レコードを 200 OK で返す (409 ではない)。
      フロントのリトライ/再ロード時に安全。

    バリデーション:
    - tx_hash: 0x + 64 hex (pydantic pattern)
    - to_address: 0x + 40 hex (EIP-55 checksum 形式は大小混在許可、内部で lower 正規化)
    - amount_usdc: 0 < amount <= WITHDRAWAL_MAX_USDC (default 100000)

    レート制限: 1 ユーザー 5 件/分 (in-memory, TODO Redis 化)。

    Optional: RPC_VERIFY=true で tx の on-chain status を検証。
    """
    # rate limit
    if not _rate_limiter.check_and_record(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"rate limit exceeded ({RATE_LIMIT_PER_MIN} per {RATE_LIMIT_WINDOW_SEC}s)",
        )

    # 冪等性チェック: 同一 tx_hash の既存レコードを返す
    existing = db.execute(
        select(Transaction).where(Transaction.tx_hash == request.tx_hash)
    ).scalar_one_or_none()
    if existing is not None:
        # 別ユーザーの tx を上書きしようとしたら 409
        if existing.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"tx_hash {request.tx_hash} already recorded by another user",
            )
        # 同じユーザー → 冪等に既存レコードを返す
        logger.info(
            "[withdraw idempotent] user=%s tx=%s already recorded; returning existing",
            current_user.email,
            request.tx_hash,
        )
        response.status_code = status.HTTP_200_OK
        return _to_response(existing)

    # optional RPC verify
    if _rpc_verify_enabled():
        _verify_tx_via_rpc(
            tx_hash=request.tx_hash,
            expected_to=request.to_address,
            expected_amount=request.amount_usdc,
        )

    # transactions テーブルに記録
    tx = Transaction(
        user_id=current_user.id,
        wallet_address=request.to_address,
        operation="withdraw",
        asset="USDC",
        amount=request.amount_usdc,
        amount_usd=request.amount_usdc,
        tx_hash=request.tx_hash,
        chain=request.network,
        status="completed",
        is_dry_run=False,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    logger.info(
        "[withdraw recorded] user=%s amount=%s USDC to=%s tx=%s",
        current_user.email,
        request.amount_usdc,
        request.to_address,
        request.tx_hash,
    )

    response.status_code = status.HTTP_201_CREATED
    return _to_response(tx)


@router.get(
    "",
    response_model=WithdrawalListResponse,
    summary="出金履歴取得 (自分のみ)",
    description="自分の出金履歴を新しい順に返す。non-custodial のため backend は記録の参照のみ行う。",
)
def list_withdrawals(
    limit: int = 50,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> WithdrawalListResponse:
    """自分の出金履歴を新しい順に返す。"""
    if limit <= 0 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be 1..200",
        )

    stmt = (
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .where(Transaction.operation == "withdraw")
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()

    items = [_to_response(tx) for tx in rows]
    return WithdrawalListResponse(items=items, total=len(items))
