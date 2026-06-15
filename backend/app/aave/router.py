# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/router.py

"""
Aave 操作用の FastAPI ルーター定義。

- POST /aave/rebalance
"""

from decimal import Decimal
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import User

from .schemas import (
    AaveMonitorStatus,
    AaveRebalanceRequest,
    AaveRebalanceResponse,
    OracleStatusResponse,
    PoolDeficitInfoResponse,
    PoolHealthResponse,
    StressTestResponse,
    StressTestScenarioResponse,
)
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

    chain_name 未指定時は AAVE_ACTIVE_CHAINS の先頭チェーンを使用する（本番: base）。
    """
    import os  # noqa: PLC0415

    default_chain = os.getenv("AAVE_ACTIVE_CHAINS", "base").split(",")[0].strip()
    chain = body.chain_name or default_chain
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
    current_user: User = Depends(require_viewer),
    multi_service: MultiChainAaveService = Depends(get_multi_chain_aave_service),
) -> dict[str, dict[str, str | None]]:
    """全アクティブチェーンの Health Factor を一覧で返す。"""
    health_factors = multi_service.get_all_health_factors()
    return {
        "chains": {name: str(hf) if hf is not None else None for name, hf in health_factors.items()}
    }


@router.get(
    "/health-factor",
    summary="Aave V3 Health Factor をリアルタイム取得する",
)
def get_health_factor(
    current_user: User = Depends(require_viewer),
) -> dict[str, str | None]:
    """AAVE_CLIENT_TYPE に応じて HF をリアルタイム取得して返す。"""
    from .monitor import get_health_factor as _get_hf  # noqa: PLC0415

    hf = _get_hf()
    return {"health_factor": str(hf) if hf is not None else None}


@router.get(
    "/oracle-status",
    response_model=OracleStatusResponse,
    summary="Chainlink / Pyth / Uniswap V3 TWAP 三重 Oracle 検証結果を返す",
)
def get_oracle_status(
    current_user: User = Depends(require_viewer),
) -> OracleStatusResponse:
    """
    AAVE_ORACLE_ASSETS_JSON 環境変数で定義されたアセットごとに
    check_price_deviation() を実行し、乖離状況を返す。

    環境変数未設定時は空リストを返す（fail-open）。

    AAVE_ORACLE_ASSETS_JSON のフォーマット（JSON 配列）:
    [
      {
        "asset": "USDC",
        "chainlink_feed": "0x...",
        "rpc_url": "https://...",
        "pyth_api_url": "https://hermes.pyth.network",
        "pyth_price_id": "0x...",
        "uniswap_pool": "0x..."
      }
    ]
    """
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415

    from .oracle_checker import check_price_deviation  # noqa: PLC0415
    from .schemas import OracleAlert  # noqa: PLC0415

    raw = os.getenv("AAVE_ORACLE_ASSETS_JSON", "[]")
    try:
        assets_config = json.loads(raw)
    except json.JSONDecodeError:
        assets_config = []

    alerts: list[OracleAlert] = []
    for cfg in assets_config:
        result = check_price_deviation(
            asset=cfg.get("asset", "UNKNOWN"),
            chainlink_feed_address=cfg.get("chainlink_feed"),
            rpc_url=cfg.get("rpc_url"),
            pyth_api_url=cfg.get("pyth_api_url"),
            pyth_price_id=cfg.get("pyth_price_id"),
            uniswap_pool_address=cfg.get("uniswap_pool"),
            deviation_threshold_pct=Decimal(str(cfg.get("deviation_threshold_pct", "2"))),
        )
        alerts.append(
            OracleAlert(
                asset=result.asset,
                level=result.level,
                max_deviation_pct=(
                    str(result.max_deviation_pct) if result.max_deviation_pct is not None else None
                ),
                chainlink_price=(
                    str(result.chainlink_price) if result.chainlink_price is not None else None
                ),
                pyth_price=(str(result.pyth_price) if result.pyth_price is not None else None),
                twap_price=(str(result.twap_price) if result.twap_price is not None else None),
                detail=result.detail,
                checked_at=result.checked_at,
            )
        )

    return OracleStatusResponse(alerts=alerts)


@router.get(
    "/status",
    response_model=AaveMonitorStatus,
    summary="Aave ポジション状態（HF + 残高）をリアルタイム取得する",
)
def get_monitor_status(
    current_user: User = Depends(require_viewer),
) -> AaveMonitorStatus:
    """AAVE_CLIENT_TYPE に応じて HF + USDC/aUSDC 残高をリアルタイム取得して返す。"""
    import os  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from .monitor import get_aave_balance  # noqa: PLC0415
    from .monitor import get_health_factor as _get_hf  # noqa: PLC0415

    hf = _get_hf()
    balance = get_aave_balance()
    return AaveMonitorStatus(
        health_factor=hf,
        balance=balance,
        client_type=os.getenv("AAVE_CLIENT_TYPE", "dummy"),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/stress-test",
    response_model=StressTestResponse,
    summary="価格 -10%/-20% 時の Health Factor を事前計算する（清算リスクストレステスト）",
)
def get_stress_test(
    current_user: User = Depends(require_viewer),
) -> StressTestResponse:
    """
    AAVE_WALLET_ADDRESS のポジションに対して価格下落シナリオを適用し、
    HF シミュレーション結果を返す。

    - シナリオ 1: 担保価格 -10%
    - シナリオ 2: 担保価格 -20%

    金融計算はすべて Decimal で実行（float 禁止）。
    RPC 未設定時は DummyAaveClient のデータでシミュレーションする（fail-open）。
    """
    import os  # noqa: PLC0415

    from .liquidation_sentinel import get_stress_test as _get_stress_test  # noqa: PLC0415

    wallet = os.getenv("AAVE_WALLET_ADDRESS", "")
    if not wallet:
        return StressTestResponse(
            wallet_address="",
            current_hf=None,
            current_collateral_usd=None,
            current_debt_usd=None,
            liquidation_threshold=None,
            error="AAVE_WALLET_ADDRESS が設定されていません。",
        )

    result = _get_stress_test(wallet)

    from .liquidation_sentinel import _mask_address  # noqa: PLC0415

    # SECURITY: ウォレットアドレスを先頭6文字+末尾4文字にマスクしてからレスポンスに含める。
    # 生の wallet_address を API レスポンスで露出させない（docs/13_security_design.md Rule 8）。
    masked_wallet = _mask_address(result.wallet_address)

    scenarios = [
        StressTestScenarioResponse(
            price_drop_pct=str(sc.price_drop_pct),
            simulated_hf=str(sc.simulated_hf) if sc.simulated_hf is not None else None,
            collateral_after_usd=(
                str(sc.collateral_after_usd) if sc.collateral_after_usd is not None else None
            ),
        )
        for sc in result.scenarios
    ]

    return StressTestResponse(
        wallet_address=masked_wallet,
        current_hf=str(result.current_hf) if result.current_hf is not None else None,
        current_collateral_usd=(
            str(result.current_collateral_usd)
            if result.current_collateral_usd is not None
            else None
        ),
        current_debt_usd=(
            str(result.current_debt_usd) if result.current_debt_usd is not None else None
        ),
        liquidation_threshold=(
            str(result.liquidation_threshold) if result.liquidation_threshold is not None else None
        ),
        scenarios=scenarios,
        error=result.error,
    )


@router.get(
    "/pool-health",
    response_model=PoolHealthResponse,
    summary="Aave プール赤字蓄積を監視する（getReserveDeficit）",
)
def get_pool_health(
    current_user: User = Depends(require_viewer),
) -> PoolHealthResponse:
    """
    AAVE_ACTIVE_CHAINS の先頭チェーンに対して getReserveDeficit() を呼び出し、
    USDC/WETH/wstETH のプール赤字を返す。

    赤字が $10,000 を超えた場合は Slack アラートも発火する。
    AAVE_CLIENT_TYPE=dummy の場合は空レポートを返す（fail-open）。
    """
    import os  # noqa: PLC0415

    from .liquidation_sentinel import PoolHealthMonitor  # noqa: PLC0415

    chain_name = os.getenv("AAVE_ACTIVE_CHAINS", "base").split(",")[0].strip()
    monitor = PoolHealthMonitor()
    report = monitor.check_pool_deficits(chain_name=chain_name)

    deficits = [
        PoolDeficitInfoResponse(
            asset_symbol=d.asset_symbol,
            deficit_usd=str(d.deficit_usd),
            alert_triggered=d.alert_triggered,
        )
        for d in report.deficits
    ]

    return PoolHealthResponse(
        chain_name=report.chain_name,
        deficits=deficits,
        total_deficit_usd=str(report.total_deficit_usd),
        alert_triggered=report.alert_triggered,
        error=report.error,
    )


@router.get(
    "/rewards",
    summary="未請求 Aave リワードを取得する",
)
def get_rewards(
    current_user: User = Depends(require_viewer),
) -> dict[str, object]:
    """
    UiIncentiveDataProviderV3 から未請求リワード一覧と合計 USD を返す。

    AAVE_UI_INCENTIVE_PROVIDER_ADDRESS / AAVE_REWARDS_CONTROLLER_ADDRESS /
    AAVE_POOL_ADDRESSES_PROVIDER が未設定の場合は空リストを返す (fail-open)。
    """
    import os  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from .reward_claimer import make_reward_claimer_from_env  # noqa: PLC0415

    claimer = make_reward_claimer_from_env()
    wallet_address = os.getenv("AAVE_WALLET_ADDRESS", "")

    if claimer is None or not wallet_address:
        return {
            "rewards": [],
            "total_usd": "0",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "note": "AAVE_UI_INCENTIVE_PROVIDER_ADDRESS または AAVE_WALLET_ADDRESS が未設定",
        }

    raw_rewards = claimer.get_claimable_rewards(wallet_address)
    from decimal import Decimal  # noqa: PLC0415

    total_usd = sum((r["amount_usd"] for r in raw_rewards), Decimal("0"))

    serialized = [
        {
            "asset_name": r["asset_name"],
            "reward_token_address": r["reward_token_address"],
            "amount": str(r["amount"]),
            "amount_usd": str(r["amount_usd"]),
        }
        for r in raw_rewards
    ]

    return {
        "rewards": serialized,
        "total_usd": str(total_usd),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post(
    "/rewards/claim",
    summary="未請求 Aave リワードを手動 Claim する (admin のみ)",
)
def claim_rewards(
    current_user: User = Depends(require_admin),
) -> dict[str, object]:
    """
    未請求リワードを Claim し、閾値 ($5) 以上なら Aave に再供給する。

    HUMAN-REVIEW-REQUIRED: 本エンドポイントはオンチェーン tx を送信するため、
    本番での実行は人間承認後に AAVE_WALLET_PRIVATE_KEY が設定された状態で行うこと。
    """
    import os  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from .reward_claimer import make_reward_claimer_from_env  # noqa: PLC0415

    claimer = make_reward_claimer_from_env()
    wallet_address = os.getenv("AAVE_WALLET_ADDRESS", "")
    private_key = os.getenv("AAVE_WALLET_PRIVATE_KEY", "")

    if claimer is None or not wallet_address:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AAVE_UI_INCENTIVE_PROVIDER_ADDRESS または AAVE_WALLET_ADDRESS が未設定",
        )

    if not private_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AAVE_WALLET_PRIVATE_KEY が未設定 — 管理者設定が必要です",
        )

    result = claimer.auto_claim_if_worthy(
        wallet_address=wallet_address,
        private_key=private_key,
        dry_run=False,
    )

    serialized_rewards = [
        {
            "asset_name": r["asset_name"],
            "reward_token_address": r["reward_token_address"],
            "amount": str(r["amount"]),
            "amount_usd": str(r["amount_usd"]),
        }
        for r in result.get("rewards", [])
    ]

    return {
        "claimed": result["claimed"],
        "total_usd": result["total_usd"],
        "rewards": serialized_rewards,
        "supply_tx_hash": result.get("supply_tx_hash"),
        "skip_reason": result.get("skip_reason"),
        "error": result.get("error"),
        "claimed_at": datetime.now(timezone.utc).isoformat() if result["claimed"] else None,
    }
