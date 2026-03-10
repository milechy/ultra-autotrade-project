# backend/app/exchange/router.py

"""
Exchange（Bybit Sandbox）エンドポイント定義。

- POST /exchange/order : 取引注文の実行
- GET  /exchange/status: 取引所接続状態・本日の取引状況の確認
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from .client import BitFlyerClient, BybitSandboxClient, DummyExchangeClient
from .config import get_bitflyer_settings, get_exchange_settings
from .schemas import ExchangeStatusResponse, OrderRequest, OrderResult
from .service import ExchangeService

router = APIRouter(prefix="/exchange", tags=["exchange"])


@lru_cache()
def get_exchange_service() -> ExchangeService:
    """
    ExchangeService のシングルトンインスタンスを取得する。

    環境変数 EXCHANGE_CLIENT_TYPE で切り替え可能:
    - "dummy": DummyExchangeClient（テスト・開発用）
    - "bitflyer": BitFlyerClient（bitFlyer、sandbox なし・dry_run 強制）
    - それ以外（デフォルト）: BybitSandboxClient（サンドボックス環境）

    NOTE:
    - テストでは monkeypatch で環境変数をセットしてから呼び出す。
    - lru_cache により同一プロセス内でシングルトンとして動作する。
    - APP_ENV=prod の場合、Bybit は本番モード（sandbox=False）で動作する
    """
    settings = get_exchange_settings()

    client_type = os.getenv("EXCHANGE_CLIENT_TYPE", "sandbox")
    if client_type == "dummy":
        client: DummyExchangeClient | BybitSandboxClient | BitFlyerClient = DummyExchangeClient()
    elif client_type == "bitflyer":
        bitflyer_settings = get_bitflyer_settings()
        client = BitFlyerClient(settings=bitflyer_settings)
        return ExchangeService(client=client, settings=bitflyer_settings)
    else:
        # "sandbox" or "bybit" → BybitSandboxClient
        client = BybitSandboxClient(settings=settings)

    return ExchangeService(client=client, settings=settings)


@router.post(
    "/order",
    response_model=OrderResult,
    summary="取引注文の実行（Bybit Sandbox）",
)
def post_exchange_order(
    body: OrderRequest,
    service: ExchangeService = Depends(get_exchange_service),
) -> OrderResult:
    """
    AI 判定結果（BUY / SELL / HOLD）を受け取り、Bybit Sandbox に成行注文を送信する。

    - HOLD の場合は注文を送信せず SKIPPED を返す
    - ルールチェック（日次上限・クールダウン・最大金額）に引っかかった場合も SKIPPED を返す
    - 想定外の内部エラー → 500 Internal Server Error
    """
    try:
        return service.execute_trade(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while executing exchange order.",
        ) from exc


@router.get(
    "/status",
    response_model=ExchangeStatusResponse,
    summary="取引所の接続状態・本日の取引状況を確認",
)
def get_exchange_status(
    service: ExchangeService = Depends(get_exchange_service),
) -> ExchangeStatusResponse:
    """
    取引所への接続状態、残高、本日の取引件数などを返す。

    - 接続失敗時も例外にせず connected=False で返す（fail-safe）
    - 想定外の内部エラー → 500 Internal Server Error
    """
    try:
        return service.get_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching exchange status.",
        ) from exc
