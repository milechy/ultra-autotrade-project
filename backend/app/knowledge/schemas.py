# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/knowledge/schemas.py

"""
Knowledge Hub モジュールで扱うスキーマ定義。

API リクエスト／レスポンスおよび内部データ転送オブジェクトを定義する。
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeItemStatus(str, Enum):
    """
    ナレッジアイテムの処理状態。

    - PENDING:  登録済み・embedding生成済み・AI判定未実施
    - ANALYZED: AI判定・取引処理完了
    - SKIPPED:  ルールエンジンにより取引スキップ / HOLD判定
    - ERROR:    処理中にエラー発生
    """

    PENDING = "pending"
    ANALYZED = "analyzed"
    SKIPPED = "skipped"
    ERROR = "error"


class KnowledgeItemType(str, Enum):
    """
    ナレッジアイテムの入力種別。

    - URL:  URL を指定してスクレイピングで本文を取得
    - TEXT: 生テキストを直接入力
    """

    URL = "url"
    TEXT = "text"


class KnowledgeCreateRequest(BaseModel):
    """
    ナレッジアイテム登録リクエスト。

    item_type が URL の場合は source_url が必須。
    item_type が TEXT の場合は raw_text が必須。
    """

    title: Optional[str] = Field(None, description="アイテムのタイトル（任意）")
    item_type: KnowledgeItemType = Field(..., description="入力種別: url または text")
    source_url: Optional[str] = Field(
        None, description="スクレイピング対象の URL（item_type=url の場合に使用）"
    )
    raw_text: Optional[str] = Field(
        None, description="登録するテキスト（item_type=text の場合に使用）"
    )


class KnowledgeItem(BaseModel):
    """
    ナレッジアイテムのレスポンスモデル。

    ORM モデル（KnowledgeSource）から直接生成できるよう
    from_attributes=True を有効化している。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="アイテム ID")
    source_url: Optional[str] = Field(None, description="ソース URL")
    title: Optional[str] = Field(None, description="タイトル")
    raw_text: Optional[str] = Field(None, description="生テキスト")
    status: KnowledgeItemStatus = Field(..., description="処理状態")
    chunk_count: int = Field(..., description="チャンク数")
    item_type: KnowledgeItemType = Field(..., description="入力種別")
    quality_score: Optional[float] = Field(None, description="コンテンツ品質スコア（0〜100）")
    created_at: datetime = Field(..., description="作成日時")
    updated_at: datetime = Field(..., description="更新日時")


class KnowledgeSearchRequest(BaseModel):
    """
    ベクトル検索リクエスト。
    """

    query: str = Field(..., min_length=1, description="検索クエリ文字列")
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="返却する検索結果の最大件数（1〜20）",
    )


class KnowledgeSearchResult(BaseModel):
    """
    ベクトル検索の単一結果。
    """

    chunk_id: int = Field(..., description="チャンク ID")
    document_id: int = Field(..., description="ドキュメント ID")
    content: str = Field(..., description="チャンクのテキスト内容")
    similarity: float = Field(..., description="コサイン類似度スコア（0〜1）")
    source_url: Optional[str] = Field(None, description="ソース URL")
    title: Optional[str] = Field(None, description="ソースのタイトル")


class KnowledgeSearchResponse(BaseModel):
    """
    ベクトル検索レスポンス全体。
    """

    results: List[KnowledgeSearchResult] = Field(default_factory=list, description="検索結果リスト")
    count: int = Field(..., description="返却件数")
    query: str = Field(..., description="実行した検索クエリ")
