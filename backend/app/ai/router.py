# backend/app/ai/router.py
"""
AI 解析用の FastAPI ルーター定義。

- /ai/analyze
- /ai/trend/confidence
"""

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_editor
from app.auth.models import User

from .schemas import (
    AIAnalysisRequest,
    AIAnalysisResponse,
    ConfidenceDataPoint,
    ConfidenceTrendResponse,
    PromptVersionSummary,
    TradeAction,
)
from .service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])

# アプリケーション全体で共有する AIService インスタンス
_service = AIService()


@router.post(
    "/analyze",
    response_model=AIAnalysisResponse,
    summary="ニュースの AI 解析",
    description=(
        "/notion/ingest で取得した NotionNewsItem の配列を受け取り、"
        "各ニュースに対する BUY/SELL/HOLD 判定を返す。"
    ),
)
def analyze_news(
    request: AIAnalysisRequest,
    current_user: User = Depends(require_editor),
) -> AIAnalysisResponse:
    """
    ニュース配列を受け取り、AI 判定結果を返すエンドポイント。

    - docs/05_ai_judgement_rules.md のルールに従い、HOLD 優先で安全側の判定を行う
    - 予期しない例外発生時は 500 エラーとして扱う
    """
    try:
        results = _service.analyze_items(request.items)
    except Exception as exc:  # noqa: BLE001
        # 予期しない例外は 500 番台として扱う（詳細はログ側に残す）
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI analysis failed unexpectedly.",
        ) from exc

    return AIAnalysisResponse(results=results, count=len(results))


@router.get(
    "/trend/confidence",
    response_model=ConfidenceTrendResponse,
    summary="信頼度トレンド取得",
    description="AI判定の信頼度トレンドデータを返す。データ不足時はモックデータにフォールバック。",
)
def get_confidence_trend(
    days: int = 7,
    current_user: User = Depends(require_editor),
) -> ConfidenceTrendResponse:
    """
    信頼度トレンドデータを返す。
    - 実データが存在しない場合はモックデータを返す（is_mock=True）
    - days パラメータで期間指定（7/30/90）
    """
    # 実データ取得を試みる（将来的にDB連携）
    real_data: list[ConfidenceDataPoint] = []

    if real_data:
        by_version = _aggregate_by_version(real_data)
        return ConfidenceTrendResponse(
            data_points=real_data,
            by_version=by_version,
            is_mock=False,
            total_count=len(real_data),
        )

    # モックデータフォールバック
    mock_data = _generate_mock_trend(days)
    by_version = _aggregate_by_version(mock_data)
    return ConfidenceTrendResponse(
        data_points=mock_data,
        by_version=by_version,
        is_mock=True,
        total_count=len(mock_data),
    )


def _generate_mock_trend(days: int) -> list[ConfidenceDataPoint]:
    """モックトレンドデータ生成（決定論的）。"""
    rng = random.Random(42)
    actions = [TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD]
    versions = ["v1", "v2"]
    now = datetime.now(timezone.utc)
    data: list[ConfidenceDataPoint] = []
    for i in range(days * 3):
        ts = now - timedelta(hours=i * 8)
        action = actions[i % 3]
        version = versions[i % 2]
        base = 75.0 if action == TradeAction.BUY else 65.0 if action == TradeAction.SELL else 55.0
        confidence = max(30.0, min(95.0, base + rng.gauss(0, 8)))
        data.append(
            ConfidenceDataPoint(
                timestamp=ts.isoformat(),
                action=action,
                confidence=round(confidence, 1),
                prompt_version=version,
            )
        )
    return list(reversed(data))


def _aggregate_by_version(data: list[ConfidenceDataPoint]) -> list[PromptVersionSummary]:
    """バージョン別平均信頼度を集計。"""
    buckets: dict[str, list[float]] = defaultdict(list)
    for dp in data:
        buckets[dp.prompt_version].append(dp.confidence)
    return [
        PromptVersionSummary(
            version=v,
            avg_confidence=round(sum(vals) / len(vals), 1),
            count=len(vals),
        )
        for v, vals in sorted(buckets.items())
    ]
