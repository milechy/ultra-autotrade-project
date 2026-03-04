# backend/app/ai/__init__.py
"""
AI 解析ロジック用パッケージ。

Phase2 では以下を提供することを目的とする：
- /ai/analyze エンドポイント用のスキーマ
- ニュースを BUY / SELL / HOLD に分類するサービスロジック
"""

from .schemas import (  # noqa: F401
    AIAnalysisRequest,
    AIAnalysisResponse,
    AIAnalysisResult,
    TradeAction,
)
from .service import AIService  # noqa: F401
