# backend/app/aave/router.py

"""
Aave 操作用の FastAPI ルーター定義。

- POST /aave/rebalance
"""

from decimal import Decimal
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_admin
from app.auth.models import User

from .schemas import AaveRebalanceRequest, AaveRebalanceResponse
from .service import AaveService, MultiChainAaveService

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


@lru_cache()
def get_multi_chain_aave_service() -> MultiChainAaveService:
    """
    MultiChainAaveService のシングルトンインスタンスを取得する。
    """
    return MultiChainAaveService()


@router.post(
    "/rebalance",
    response_model=AaveRebalanceResponse,
    summary="BUY/SELL/HOLD に応じて Aave ポジションを調整する",
)
def rebalance(
    body: AaveRebalanceRequest,
    current_user: User = Depends(require_admin),
    multi_service: MultiChainAaveService = Depends(get_multi_chain_aave_service),
) -> AaveRebalanceResponse:
    """
    BUY/SELL/HOLD に応じて deposit / withdraw / NOOP を実行する。

    chain_name 未指定時はプライマリチェーン（arbitrum）を使用する。
    """
    chain = body.chain_name or "arbitrum"
    try:
        result = multi_service.execute_rebalance(
            chain_name=chain,
            action=body.action,
            amount=Decimal(body.amount),
            asset_symbol=body.asset_symbol,
            dry_run=body.dry_run,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
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


@router.get(
    "/chains/health",
    summary="全アクティブチェーンの Health Factor を取得する",
)
def get_chains_health(
    current_user: User = Depends(require_admin),
    multi_service: MultiChainAaveService = Depends(get_multi_chain_aave_service),
) -> dict[str, dict[str, str | None]]:
    """全アクティブチェーンの Health Factor を一覧で返す。"""
    health_factors = multi_service.get_all_health_factors()
    return {
        "chains": {name: str(hf) if hf is not None else None for name, hf in health_factors.items()}
    }
