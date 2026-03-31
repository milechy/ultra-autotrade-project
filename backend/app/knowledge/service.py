# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/knowledge/service.py

"""
Knowledge Hub service layer.

Main responsibilities:
- Ingest content via URL scraping or raw text
- Split text into chunks (using tiktoken)
- Generate embedding vectors via OpenAI API
- Vector search using cosine similarity with pgvector
- Manage KnowledgeSource / KnowledgeDocument / KnowledgeChunk in the DB
"""

import logging
import math
import re
from typing import List, Optional

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None  # type: ignore[assignment]

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[misc,assignment]

from .config import KnowledgeSettings, get_knowledge_settings
from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeSource
from .schemas import (
    KnowledgeCreateRequest,
    KnowledgeItem,
    KnowledgeItemStatus,
    KnowledgeItemType,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)

logger = logging.getLogger(__name__)


class KnowledgeServiceError(Exception):
    """Service-specific error for Knowledge Hub."""


class KnowledgeService:
    """
    Service class responsible for Knowledge Hub business logic.

    Instances can be created per API request or treated as singletons via dependency injection.
    """

    def __init__(self, *, settings: Optional[KnowledgeSettings] = None) -> None:
        self._settings = settings or get_knowledge_settings()
        self._openai = OpenAI(api_key=self._settings.openai_api_key)

        if tiktoken is not None:
            self._tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        else:
            self._tokenizer = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def create_item(self, db: Session, request: KnowledgeCreateRequest) -> KnowledgeItem:
        """
        Register a knowledge item.

        For URL type: scrape text from the URL.
        For text type: use raw_text as-is.
        Performs chunk splitting and embedding generation, then saves to DB.
        """
        # 1. Resolve raw text
        try:
            raw_text, title = self._resolve_raw_text(request)
        except KnowledgeServiceError:
            raise
        except Exception as exc:
            raise KnowledgeServiceError(f"Failed to resolve raw text: {exc}") from exc

        if not raw_text:
            raise KnowledgeServiceError(
                "No text content available. Provide raw_text or a valid source_url."
            )

        # Title: prefer request argument; fall back to scraped value
        effective_title = request.title or title

        # 2. Create KnowledgeSource row
        source = KnowledgeSource(
            source_url=request.source_url,
            title=effective_title,
            item_type=request.item_type.value,
            status=KnowledgeItemStatus.PENDING.value,
        )
        db.add(source)
        db.flush()  # Commit to obtain ID

        logger.info(
            "KnowledgeSource created",
            extra={
                "source_id": source.id,
                "item_type": source.item_type,
                "title": source.title,
            },
        )

        # 3. Create KnowledgeDocument row
        document = KnowledgeDocument(
            source_id=source.id,
            raw_text=raw_text,
        )
        db.add(document)
        db.flush()

        # 4. Split text into chunks
        chunks_text = self._chunk_text(raw_text)
        logger.info(
            "Text chunked",
            extra={"source_id": source.id, "chunk_count": len(chunks_text)},
        )

        # 5. Generate embeddings
        try:
            embeddings = self._embed_texts(chunks_text)
        except Exception as exc:
            # On embedding failure: update status to ERROR and commit (fail-closed)
            source.status = KnowledgeItemStatus.ERROR.value
            db.commit()
            raise KnowledgeServiceError(f"Embedding generation failed: {exc}") from exc

        # 6. Create KnowledgeChunk rows
        for idx, (chunk_text, embedding) in enumerate(zip(chunks_text, embeddings)):
            token_count = (
                len(self._tokenizer.encode(chunk_text))
                if self._tokenizer is not None
                else len(chunk_text.split())
            )
            chunk = KnowledgeChunk(
                document_id=document.id,
                content=chunk_text,
                chunk_index=idx,
                token_count=token_count,
                embedding=embedding,
            )
            db.add(chunk)

        # 7. Compute and set quality score
        source.quality_score = self._compute_quality_score(raw_text, len(chunks_text))

        # 8. Save chunks and embeddings, then commit (status remains PENDING)
        db.commit()
        db.refresh(source)

        logger.info(
            "KnowledgeItem created successfully",
            extra={
                "source_id": source.id,
                "status": source.status,
                "chunk_count": len(chunks_text),
                "quality_score": source.quality_score,
            },
        )

        return self._to_schema(source)

    def search(self, db: Session, request: KnowledgeSearchRequest) -> List[KnowledgeSearchResult]:
        """
        RAG search: embed the query and search by pgvector cosine similarity.
        """
        # 1. Embed the query
        try:
            query_embeddings = self._embed_texts([request.query])
        except Exception as exc:
            raise KnowledgeServiceError(f"Failed to embed search query: {exc}") from exc

        query_vector = query_embeddings[0]

        # 2. pgvector cosine distance SQL
        sql = text(
            """
            SELECT kc.id,
                   kc.document_id,
                   kc.content,
                   1 - (kc.embedding <=> :query_vec) AS similarity,
                   ks.source_url,
                   ks.title
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kc.document_id = kd.id
            JOIN knowledge_sources ks ON kd.source_id = ks.id
            WHERE kc.embedding IS NOT NULL
            ORDER BY kc.embedding <=> :query_vec
            LIMIT :top_k
            """
        )

        rows = db.execute(
            sql,
            {"query_vec": str(query_vector), "top_k": request.top_k},
        ).fetchall()

        results = [
            KnowledgeSearchResult(
                chunk_id=row[0],
                document_id=row[1],
                content=row[2],
                similarity=float(row[3]),
                source_url=row[4],
                title=row[5],
            )
            for row in rows
        ]

        logger.info(
            "Knowledge search completed",
            extra={"query": request.query, "result_count": len(results)},
        )

        return results

    def get_pending(self, db: Session) -> List[KnowledgeItem]:
        """Fetch all items with status='pending'."""
        return self.get_items(db, status=KnowledgeItemStatus.PENDING.value)

    def get_items(self, db: Session, *, status: Optional[str] = None) -> List[KnowledgeItem]:
        """
        Fetch all items. Filters by status if provided.
        """
        query = db.query(KnowledgeSource)
        if status is not None:
            query = query.filter(KnowledgeSource.status == status)

        sources = query.order_by(KnowledgeSource.created_at.desc()).all()
        return [self._to_schema(s) for s in sources]

    def update_status(
        self, db: Session, item_id: int, status: KnowledgeItemStatus
    ) -> KnowledgeItem:
        """
        Update the status of an item.

        Raises KnowledgeServiceError if item_id does not exist.
        """
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == item_id).first()

        if source is None:
            raise KnowledgeServiceError(f"KnowledgeSource not found: id={item_id}")

        source.status = status.value
        db.commit()
        db.refresh(source)

        logger.info(
            "KnowledgeSource status updated",
            extra={"source_id": item_id, "status": status.value},
        )

        return self._to_schema(source)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _resolve_raw_text(self, request: KnowledgeCreateRequest) -> tuple[str, Optional[str]]:
        """
        Return text content and estimated title based on request type.

        Returns:
            (raw_text, title): Body text and estimated title (None if unknown)
        """
        if request.item_type == KnowledgeItemType.URL:
            if not request.source_url:
                raise KnowledgeServiceError("source_url is required when item_type is 'url'.")
            raw_text = self._scrape_url(request.source_url)
            return raw_text, None

        # TEXT type
        if not request.raw_text:
            raise KnowledgeServiceError("raw_text is required when item_type is 'text'.")
        return request.raw_text, None

    def _scrape_url(self, url: str) -> str:
        """
        Scrape a URL and return clean text.

        Uses httpx (sync) + BeautifulSoup.
        Text extraction priority: <article> → <main> → <body>.
        """
        if httpx is None:
            raise KnowledgeServiceError(
                "httpx is not installed. Install it with: pip install httpx"
            )
        if BeautifulSoup is None:
            raise KnowledgeServiceError(
                "beautifulsoup4 is not installed. Install it with: pip install beautifulsoup4"
            )

        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(
                    url,
                    headers={"User-Agent": ("Mozilla/5.0 (compatible; UltraAutoTrade/1.0)")},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KnowledgeServiceError(
                f"HTTP error while scraping {url}: {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise KnowledgeServiceError(f"Network error while scraping {url}: {exc}") from exc

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove unwanted tags
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Text extraction priority: <article> → <main> → <body>
        target = soup.find("article") or soup.find("main") or soup.find("body") or soup

        raw_text = target.get_text(separator="\n", strip=True)

        # Compress blank lines and clean up
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        cleaned = "\n".join(lines)

        if not cleaned:
            raise KnowledgeServiceError(f"No text content extracted from URL: {url}")

        logger.info(
            "URL scraped successfully",
            extra={"url": url, "text_length": len(cleaned)},
        )

        return cleaned

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks.

        Uses tiktoken to split into ~chunk_size_tokens fragments
        with chunk_overlap_tokens overlap.
        """
        if self._tokenizer is None:
            # Fall back to character-based splitting when tiktoken is unavailable
            logger.warning("tiktoken not available, falling back to character-based chunking")
            chunk_size = self._settings.chunk_size_tokens * 4  # 1 token ≈ 4 chars
            overlap = self._settings.chunk_overlap_tokens * 4
            chunks: List[str] = []
            start = 0
            while start < len(text):
                end = start + chunk_size
                chunks.append(text[start:end])
                start += chunk_size - overlap
            return [c for c in chunks if c.strip()]

        token_ids = self._tokenizer.encode(text)
        chunk_size = self._settings.chunk_size_tokens
        overlap = self._settings.chunk_overlap_tokens

        chunks = []
        start = 0
        while start < len(token_ids):
            end = min(start + chunk_size, len(token_ids))
            chunk_ids = token_ids[start:end]
            chunk_text = self._tokenizer.decode(chunk_ids)
            if chunk_text.strip():
                chunks.append(chunk_text)
            if end >= len(token_ids):
                break
            start += chunk_size - overlap

        return chunks

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Batch-embed a list of texts using the OpenAI API.

        Returns:
            List of embedding vectors corresponding to each input text
        """
        if not texts:
            return []

        try:
            response = self._openai.embeddings.create(
                model=self._settings.embedding_model,
                input=texts,
            )
        except Exception as exc:
            raise KnowledgeServiceError(f"OpenAI embeddings API call failed: {exc}") from exc

        # Response is guaranteed to be in index order, but sort just in case
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [item.embedding for item in sorted_data]

    def _compute_quality_score(self, text: str, chunk_count: int) -> float:
        """
        Calculate a content quality score in the range 0–100.

        Score breakdown:
          - Text length (log scale): 0–40 points
          - Chunk count: 0–20 points
          - Content richness (numbers, sentences, vocabulary diversity): 0–40 points
        """
        score = 0.0

        # Text length score (log scale; full marks at 5000 characters)
        length = len(text)
        if length > 0:
            length_score = min(40.0, 40.0 * math.log10(max(1, length)) / math.log10(5000))
            score += length_score

        # Chunk count score (full marks at 5 chunks)
        score += min(20.0, chunk_count * 4.0)

        # Content richness score
        richness = 0.0

        # Number density (proxy for information density)
        numbers = len(re.findall(r"\d+\.?\d*", text))
        richness += min(15.0, numbers * 1.5)

        # Sentence count (sentences longer than 20 characters)
        sentences = [s.strip() for s in re.split(r"[.!?。！？]", text) if len(s.strip()) > 20]
        richness += min(15.0, float(len(sentences)))

        # Vocabulary diversity (unique words / total words)
        words = text.lower().split()
        if words:
            unique_ratio = len(set(words)) / len(words)
            richness += unique_ratio * 10.0

        score += richness

        return round(min(100.0, max(0.0, score)), 2)

    def _to_schema(self, source: KnowledgeSource) -> KnowledgeItem:
        """
        Convert a KnowledgeSource ORM object to a KnowledgeItem schema.
        """
        chunk_count = sum(len(doc.chunks) for doc in source.documents)
        raw_text = source.documents[0].raw_text if source.documents else None

        return KnowledgeItem(
            id=source.id,
            source_url=source.source_url,
            title=source.title,
            raw_text=raw_text,
            status=KnowledgeItemStatus(source.status),
            chunk_count=chunk_count,
            item_type=KnowledgeItemType(source.item_type),
            quality_score=source.quality_score,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
