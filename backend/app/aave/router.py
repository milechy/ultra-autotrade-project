# backend/app/aave/router.py

"""
Aave 操作用の FastAPI ルーター定義。

- POST /aave/rebalance
"""

from functools import lru_cache
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from .schemas import AaveRebalanceRequest, AaveRebalanceResponse
from .service import AaveService

router = APIRouter(prefix="/aave", tags=["aave"])


@lru_cache()
def get_aave_service() -> AaveService:
    """
    AaveService のシングルトンインスタンスを取得する。

    NOTE:
    - 内部で DummyAaveClient / get_aave_settings() を使用する。
    - 実運用時には DI や設定で差し替える想定。
    """
    return AaveService()


@router.post(
    "/rebalance",
    response_model=AaveRebalanceResponse,
    summary="BUY/SELL/HOLD に応じて Aave ポジションを調整する",
)
def rebalance(
    body: AaveRebalanceRequest,
    service: AaveService = Depends(get_aave_service),
) -> AaveRebalanceResponse:
    """
    BUY/SELL/HOLD に応じて deposit / withdraw / NOOP を実行する。

    - amount <= 0 の場合は 400
    - サービス層の想定外エラーは 500
    """
    try:
        result = service.execute_rebalance(
            action=body.action,
            amount=Decimal(body.amount),
            asset_symbol=body.asset_symbol,
            dry_run=body.dry_run,
        )
    except ValueError as exc:
        # バリデーションをすり抜けた異常値など
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while executing Aave rebalance.",
        ) from exc

    return AaveRebalanceResponse(result=result)
