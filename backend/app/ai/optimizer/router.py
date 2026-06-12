# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""AI オプティマイザー FastAPI ルーター。

OptimizerRequest を受け取り、戦略比較 + ポートフォリオ配分推奨を返す。
main.py への登録は Tier S として別 PR で実施する。

risk_mode は comparator.compare_async(risk_mode=...) 経由で StrategyScorer に伝播し、
ランキング（risk_penalty 重み）へ反映される（レビュー M1 対応済）。

live 配線（#625 M2/M3 フォローアップ / Asana GID 1215620587799245）:
SignalAdapter（Pendle/Lido/Aave 実 client）を router で生成し StrategyScorer へ注入、
comparator.compare_async() → get_all_candidates_async() 経路で実 APY を live 化する。
client / config 生成失敗時は adapter を None にして fail-open（ダミー定数を継続）。
adapter は read-only な APY/価格取得のみ呼び、秘密鍵を要するメソッドは呼ばない。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .allocator import PortfolioAllocator
from .comparator import StrategyComparator
from .schemas import OptimizerRequest, OptimizerResponse
from .signal_adapter import AaveSignalAdapter, LidoSignalAdapter, PendleSignalAdapter
from .strategy_scorer import StrategyScorer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai/optimizer", tags=["ai-optimizer"])


def _build_live_scorer(risk_mode: str) -> StrategyScorer:
    """実 client から SignalAdapter を生成して注入した StrategyScorer を返す。

    各 adapter は独立して fail-open: config / client 生成に失敗した protocol は
    adapter=None（= ダミー定数継続）とし、他 protocol の live 化は維持する。
    risk_mode は comparator が必要に応じて再生成するため初期値として渡す。
    """
    pendle_adapter: PendleSignalAdapter | None = None
    lido_adapter: LidoSignalAdapter | None = None
    aave_adapter: AaveSignalAdapter | None = None

    try:
        from app.protocols.pendle.client import get_pendle_client  # noqa: PLC0415
        from app.protocols.pendle.config import get_pendle_config  # noqa: PLC0415

        pendle_adapter = PendleSignalAdapter(client=get_pendle_client(get_pendle_config()))
    except Exception as exc:
        logger.warning("Pendle adapter 生成失敗、ダミー定数継続 (fail-open): %s", exc)

    try:
        from app.protocols.lido.client import get_lido_client  # noqa: PLC0415
        from app.protocols.lido.config import get_lido_config  # noqa: PLC0415

        lido_adapter = LidoSignalAdapter(client=get_lido_client(get_lido_config()))
    except Exception as exc:
        logger.warning("Lido adapter 生成失敗、ダミー定数継続 (fail-open): %s", exc)

    try:
        # Aave は read-only な market data fetcher（秘密鍵不要）を adapter 内で遅延 import。
        aave_adapter = AaveSignalAdapter()
    except Exception as exc:
        logger.warning("Aave adapter 生成失敗、ダミー定数継続 (fail-open): %s", exc)

    return StrategyScorer(
        pendle_adapter=pendle_adapter,
        lido_adapter=lido_adapter,
        aave_adapter=aave_adapter,
        risk_mode=risk_mode,
    )


@router.post("/recommend", response_model=OptimizerResponse)
async def recommend_strategy(request: OptimizerRequest) -> OptimizerResponse:
    """戦略推奨エンドポイント。

    投資額・リスクモード・保有予定日数を受け取り、
    各プロトコルの期待ネット利益を比較して最適配分を推奨する。
    """
    try:
        scorer = _build_live_scorer(request.risk_mode)
        comparator = StrategyComparator(scorer=scorer)
        comparison = await comparator.compare_async(
            investment_usd=request.investment_usd,
            risk_mode=request.risk_mode,
            holding_days=request.holding_days,
        )
        allocator = PortfolioAllocator()
        allocation = await allocator.allocate(
            ranked_results=comparison.candidates,
            total_usd=request.investment_usd,
            risk_mode=request.risk_mode,
        )
        report = comparator.generate_report(comparison)
        return OptimizerResponse(comparison=comparison, allocation=allocation, report=report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("optimizer recommend 失敗")
        raise HTTPException(status_code=503, detail="オプティマイザー処理に失敗しました") from exc
