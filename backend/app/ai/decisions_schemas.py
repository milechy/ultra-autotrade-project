# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/ai/decisions_schemas.py
"""AI判定履歴APIのスキーマ定義。"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class AIDecisionCreate(BaseModel):
    user_id: Optional[int] = None
    query: str
    action: str
    confidence: int
    reason: Optional[str] = None
    primary_provider: str
    primary_action: str
    primary_confidence: int
    secondary_provider: Optional[str] = None
    secondary_action: Optional[str] = None
    secondary_confidence: Optional[int] = None
    agreed: bool = False
    rag_context_json: Optional[Any] = None


class AIDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int]
    query: str
    action: str
    confidence: int
    reason: Optional[str]
    primary_provider: str
    primary_action: str
    primary_confidence: int
    secondary_provider: Optional[str]
    secondary_action: Optional[str]
    secondary_confidence: Optional[int]
    agreed: bool
    rag_context_json: Optional[Any]
    created_at: datetime


class AIDecisionListResponse(BaseModel):
    items: List[AIDecisionResponse]
    total: int
    limit: int
    offset: int
