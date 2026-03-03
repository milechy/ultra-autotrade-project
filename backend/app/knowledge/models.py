# backend/app/knowledge/models.py

"""
Knowledge Hub モジュールの SQLAlchemy モデル定義。

テーブル構成:
  knowledge_sources   : 登録されたナレッジアイテム（URL またはテキスト）のメタ情報
  knowledge_documents : ソースから取得した生テキスト本文
  knowledge_chunks    : チャンク分割された断片と pgvector 埋め込みベクトル
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class KnowledgeSource(Base):
    """
    登録されたナレッジアイテムのメタ情報テーブル。

    Attributes:
        id:         プライマリキー
        source_url: スクレイピング元 URL（URL 種別の場合）
        title:      アイテムのタイトル
        item_type:  入力種別 ("url" / "text")
        status:     処理状態 ("pending" / "analyzed" / "skipped" / "error")
        created_at: 作成日時
        updated_at: 更新日時
        documents:  関連する KnowledgeDocument のリスト
    """

    __tablename__ = "knowledge_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    documents: Mapped[List["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument",
        back_populates="source",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeSource(id={self.id}, item_type={self.item_type!r}, "
            f"status={self.status!r})>"
        )


class KnowledgeDocument(Base):
    """
    ソースから取得した生テキスト本文テーブル。

    Attributes:
        id:        プライマリキー
        source_id: 関連する KnowledgeSource の ID
        raw_text:  生テキスト全文
        created_at: 作成日時
        source:    関連する KnowledgeSource
        chunks:    関連する KnowledgeChunk のリスト
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("knowledge_sources.id"), nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    source: Mapped["KnowledgeSource"] = relationship(
        "KnowledgeSource",
        back_populates="documents",
    )
    chunks: Mapped[List["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocument(id={self.id}, source_id={self.source_id})>"


class KnowledgeChunk(Base):
    """
    チャンク分割された断片と pgvector 埋め込みベクトルのテーブル。

    Attributes:
        id:          プライマリキー
        document_id: 関連する KnowledgeDocument の ID
        content:     チャンクのテキスト内容
        chunk_index: ドキュメント内でのチャンク順序
        token_count: チャンクのトークン数
        embedding:   pgvector 埋め込みベクトル（1536 次元）
        created_at:  作成日時
        document:    関連する KnowledgeDocument
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("knowledge_documents.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # pgvector 埋め込みベクトル（PostgreSQL 専用。SQLite では None のまま）
    # 動的インポートで pgvector が利用可能な場合のみ Vector 型を使用する
    try:
        from pgvector.sqlalchemy import Vector as _Vector

        embedding: Mapped[Optional[List[float]]] = mapped_column(
            _Vector(1536), nullable=True
        )
    except ImportError:
        # SQLite などの非 PostgreSQL 環境では Text 型で代替（テスト用）
        embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # type: ignore[no-redef]

    # Relationships
    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeChunk(id={self.id}, document_id={self.document_id}, "
            f"chunk_index={self.chunk_index})>"
        )
