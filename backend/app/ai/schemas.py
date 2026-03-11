# backend/app/ai/schemas.py
"""
/ai/analyze 用の Pydantic スキーマ定義。

- Request: NotionNewsItem の配列をそのまま受け取り、解析対象とする
- Response: AI による判定結果（BUY/SELL/HOLD など）を返す
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.notion.schemas import NotionNewsItem


class TradeAction(str, Enum):
    """AI 判定で返すアクションの列挙型。"""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class AIAnalysisRequest(BaseModel):
    """
    /ai/analyze のリクエストボディ。

    Phase2 では `/notion/ingest` のレスポンス `items` をそのまま
    `items` に渡すことを想定している。
    """

    items: List[NotionNewsItem] = Field(
        ...,
        description="/notion/ingest から取得した NotionNewsItem の配列。",
    )


class AIAnalysisResult(BaseModel):
    """
    1件のニュースに対する AI 判定結果。
    """

    id: str = Field(..., description="Notion ページ ID（入力 NotionNewsItem.id を踏襲）")
    url: str = Field(..., description="ニュースの URL")
    action: TradeAction = Field(..., description="BUY / SELL / HOLD のいずれか")
    confidence: int = Field(
        ...,
        ge=0,
        le=100,
        description="AI 判定の信頼度スコア（0〜100）。安全弁ロジックで 40 未満は HOLD 優先。",
    )
    sentiment: Optional[str] = Field(
        None,
        description="ニュース全体のセンチメント（positive / negative / neutral などの自由テキスト）。",
    )
    summary: Optional[str] = Field(
        None,
        description="ニュース本文の要約。Notion の Summary プロパティに対応させる想定。",
    )
    reason: Optional[str] = Field(
        None,
        description="なぜこのアクションになったのかを説明する短い文章（OctoBot / レポート用）。",
    )
    timestamp: datetime = Field(
        ...,
        description="この判定を行った時刻（UTC）。ISO8601 文字列として入出力される。",
    )


class AIAnalysisResponse(BaseModel):
    """
    /ai/analyze のレスポンス全体。
    """

    results: List[AIAnalysisResult] = Field(
        ...,
        description="AI 判定結果の配列。入力 `items` と 1:1 に対応する。",
    )
    count: int = Field(..., description="results に含まれる件数。")


# ---------------------------------------------------------------------------
# Two-Phase Cross-Validation / RAG スキーマ（Step 4 追加分）
# ---------------------------------------------------------------------------


class LLMProvider(str, Enum):
    """LLM プロバイダーの列挙型。"""

    CLAUDE = "claude"
    OPENAI = "openai"
    RULE_BASED = "rule_based"
    CLAUDE_FALLBACK = "claude_fallback"  # Opus失敗時のSonnetフォールバック


class LLMDecision(BaseModel):
    """
    1 つの LLM プロバイダーによる判定結果。
    """

    provider: LLMProvider = Field(..., description="判定を行った LLM プロバイダー。")
    action: TradeAction = Field(..., description="BUY / SELL / HOLD のいずれか。")
    confidence: int = Field(..., ge=0, le=100, description="信頼度スコア（0〜100）。")
    reason: Optional[str] = Field(None, description="判定理由の短い説明。")
    raw_response: Optional[str] = Field(None, description="LLM からの生レスポンス文字列。")
    prompt_version: str = Field("v1", description="使用したプロンプトテンプレートのバージョン。")


class CrossValidationResult(BaseModel):
    """
    Two-Phase クロスバリデーション結果。
    primary（Claude）と secondary（OpenAI）の判定を照合し最終判定を返す。
    """

    primary: LLMDecision = Field(..., description="Phase 1: 主判定（Claude）。")
    secondary: Optional[LLMDecision] = Field(
        None,
        description="Phase 2: 副判定（OpenAI）。cross_validation_enabled=False または APIキー未設定時は None。",
    )
    agreed: bool = Field(..., description="primary と secondary が一致したかどうか。")
    final_action: TradeAction = Field(..., description="最終アクション（BUY / SELL / HOLD）。")
    final_confidence: int = Field(..., ge=0, le=100, description="最終信頼度スコア（0〜100）。")
    final_reason: Optional[str] = Field(None, description="最終判定理由。")
    prompt_version: str = Field("v1", description="使用したプロンプトテンプレートのバージョン。")
    shadow_mode: bool = Field(
        False, description="Shadow Modeで記録された判定かどうか。True=実行しない。"
    )


class ShadowModeLog(BaseModel):
    """Shadow Mode: 判定結果のログ記録（実行なし）"""

    item_id: str = Field(..., description="判定対象のID")
    action: TradeAction
    confidence: int = Field(..., ge=0, le=100)
    reason: Optional[str] = None
    timestamp: datetime
    prompt_version: str = Field("v1")
    shadow_mode: bool = Field(True, description="常にTrue（Shadow Modeで記録されたことを示す）")
    provider: Optional[str] = Field(None, description="判定に使ったLLMプロバイダー")


class RAGContext(BaseModel):
    """
    RAG（Retrieval-Augmented Generation）で取得したコンテキスト。
    """

    chunks: list[str] = Field(
        default_factory=list,
        description="Knowledge Hub から取得したテキストチャンクの一覧。",
    )
    query: str = Field(..., description="検索クエリ文字列。")
    source_count: int = Field(0, description="取得元ドキュメント数。")


# ---------------------------------------------------------------------------
# Trend / Analytics スキーマ（Stream S 追加分）
# ---------------------------------------------------------------------------


class ConfidenceDataPoint(BaseModel):
    """信頼度トレンドの1データポイント。"""

    timestamp: str = Field(..., description="ISO8601 日時文字列")
    action: TradeAction = Field(..., description="BUY / SELL / HOLD")
    confidence: float = Field(..., ge=0, le=100, description="信頼度 (0-100)")
    prompt_version: str = Field("v1", description="プロンプトバージョン")


class PromptVersionSummary(BaseModel):
    """プロンプトバージョン別の平均信頼度サマリー。"""

    version: str
    avg_confidence: float
    count: int


class ConfidenceTrendResponse(BaseModel):
    """GET /ai/trend/confidence のレスポンス。"""

    data_points: List[ConfidenceDataPoint]
    by_version: List[PromptVersionSummary]
    is_mock: bool = Field(False, description="モックデータを返しているか")
    total_count: int
