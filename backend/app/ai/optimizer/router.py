# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""AI オプティマイザー FastAPI ルーター。

OptimizerRequest を受け取り、戦略比較 + ポートフォリオ配分推奨を返す。
main.py への登録は Tier S として別 PR で実施する。

risk_mode は comparator.compare(risk_mode=...) 経由で StrategyScorer に伝播し、
ランキング（risk_penalty 重み）へ反映される（レビュー M1 対応済）。

TODO(next-PR): SignalAdapter（Pendle/Lido 実 client）を comparator/router で
注入し get_all_candidates_async 経路へ live 化する。本 PR では adapter は
score_*_async / get_all_candidates_async 経由でのみ利用され、router の sync
compare() 経路（get_all_candidates）からは未配線。async 化 + Aave 側の実 APY 化
（M3: 現状 Aave のみダミー APY のため Lido/Pendle と非対称）はリスクが大きいため
別 PR とする。Asana GID 1215620587799245 のフォローアップで実施。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .allocator import PortfolioAllocator
from .comparator import StrategyComparator
from .schemas import OptimizerRequest, OptimizerResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai/optimizer", tags=["ai-optimizer"])


@router.post("/recommend", response_model=OptimizerResponse)
async def recommend_strategy(request: OptimizerRequest) -> OptimizerResponse:
    """戦略推奨エンドポイント。

    投資額・リスクモード・保有予定日数を受け取り、
    各プロトコルの期待ネット利益を比較して最適配分を推奨する。
    """
    try:
        comparator = StrategyComparator()
        comparison = comparator.compare(
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
