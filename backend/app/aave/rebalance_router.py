from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import require_admin
from app.automation.state import get_monitoring_service

from .client import get_default_aave_client
from .config import get_aave_settings
from .rebalance_config import get_rebalance_settings
from .rebalance_schemas import (
    RebalanceExecuteRequest,
    RebalanceExecuteResponse,
    RebalanceHistoryEntry,
    RebalanceSimulateResponse,
    RebalanceStatusResponse,
)
from .rebalance_service import RebalanceService
from .service import AaveService
from .state_manager import get_default_state_manager

router = APIRouter(prefix="/aave/rebalance", tags=["aave-rebalance"])


@lru_cache()
def get_rebalance_service() -> RebalanceService:
    return RebalanceService(
        aave_client=get_default_aave_client(),
        aave_service=AaveService(),
        rebalance_settings=get_rebalance_settings(),
        aave_settings=get_aave_settings(),
        state_manager=get_default_state_manager(),
        monitoring_service=get_monitoring_service(),
    )


@router.get("/status", response_model=RebalanceStatusResponse)
def rebalance_status(
    service: RebalanceService = Depends(get_rebalance_service),
    current_user: Any = Depends(require_admin),
) -> RebalanceStatusResponse:
    try:
        return service.get_current_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/simulate", response_model=RebalanceSimulateResponse)
def rebalance_simulate(
    service: RebalanceService = Depends(get_rebalance_service),
    current_user: Any = Depends(require_admin),
) -> RebalanceSimulateResponse:
    try:
        proposal = service.simulate()
        return RebalanceSimulateResponse(proposal=proposal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/execute", response_model=RebalanceExecuteResponse)
def rebalance_execute(
    body: RebalanceExecuteRequest,
    service: RebalanceService = Depends(get_rebalance_service),
    current_user: Any = Depends(require_admin),
) -> RebalanceExecuteResponse:
    try:
        result = service.execute(body.proposal_id, body.confirmation_token)
        return RebalanceExecuteResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/history", response_model=list[RebalanceHistoryEntry])
def rebalance_history(
    limit: int = Query(20, ge=1, le=100),
    service: RebalanceService = Depends(get_rebalance_service),
    current_user: Any = Depends(require_admin),
) -> list[RebalanceHistoryEntry]:
    return service.get_history(limit=limit)
