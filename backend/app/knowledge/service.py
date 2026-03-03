# backend/app/knowledge/service.py

"""
Knowledge Hub サービス層。

主な責務:
- URL スクレイピングまたは生テキストの取り込み
- テキストのチャンク分割（tiktoken 使用）
- OpenAI API による埋め込みベクトル生成
- pgvector を利用したコサイン類似度ベクトル検索
- KnowledgeSource / KnowledgeDocument / KnowledgeChunk の DB 管理
"""

import logging
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
    BeautifulSoup = None  # type: ignore[assignment]

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
    """Knowledge Hub サービス固有のエラー。"""


class KnowledgeService:
    """
    Knowledge Hub のビジネスロジックを担うサービスクラス。

    インスタンスは API リクエストごとに生成するか、
    依存性注入でシングルトンとして扱う。
    """

    def __init__(self, *, settings: Optional[KnowledgeSettings] = None) -> None:
        self._settings = settings or get_knowledge_settings()
        self._openai = OpenAI(api_key=self._settings.openai_api_key)

        if tiktoken is not None:
            self._tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        else:
            self._tokenizer = None  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # 公開 API                                                             #
    # ------------------------------------------------------------------ #

    def create_item(
        self, db: Session, request: KnowledgeCreateRequest
    ) -> KnowledgeItem:
        """
        ナレッジアイテムを登録する。

        URL 種別の場合はスクレイピングでテキストを取得し、
        テキスト種別の場合は raw_text をそのまま使用する。
        チャンク分割・埋め込み生成を行い DB に保存する。
        """
        # 1. 生テキストの取得
        try:
            raw_text, title = self._resolve_raw_text(request)
        except KnowledgeServiceError:
            raise
        except Exception as exc:
            raise KnowledgeServiceError(
                f"Failed to resolve raw text: {exc}"
            ) from exc

        if not raw_text:
            raise KnowledgeServiceError(
                "No text content available. "
                "Provide raw_text or a valid source_url."
            )

        # タイトルは引数優先、フォールバックはスクレイピング由来
        effective_title = request.title or title

        # 2. KnowledgeSource 行の作成
        source = KnowledgeSource(
            source_url=request.source_url,
            title=effective_title,
            item_type=request.item_type.value,
            status=KnowledgeItemStatus.PENDING.value,
        )
        db.add(source)
        db.flush()  # ID を確定する

        logger.info(
            "KnowledgeSource created",
            extra={
                "source_id": source.id,
                "item_type": source.item_type,
                "title": source.title,
            },
        )

        # 3. KnowledgeDocument 行の作成
        document = KnowledgeDocument(
            source_id=source.id,
            raw_text=raw_text,
        )
        db.add(document)
        db.flush()

        # 4. テキストのチャンク分割
        chunks_text = self._chunk_text(raw_text)
        logger.info(
            "Text chunked",
            extra={"source_id": source.id, "chunk_count": len(chunks_text)},
        )

        # 5. 埋め込み生成
        try:
            embeddings = self._embed_texts(chunks_text)
        except Exception as exc:
            # 埋め込み失敗時はステータスを ERROR に更新してコミットする（fail-closed）
            source.status = KnowledgeItemStatus.ERROR.value
            db.commit()
            raise KnowledgeServiceError(
                f"Embedding generation failed: {exc}"
            ) from exc

        # 6. KnowledgeChunk 行の作成
        for idx, (chunk_text, embedding) in enumerate(
            zip(chunks_text, embeddings)
        ):
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

        # 7. ステータスを ANALYZED に更新してコミット
        source.status = KnowledgeItemStatus.ANALYZED.value
        db.commit()
        db.refresh(source)

        logger.info(
            "KnowledgeItem created successfully",
            extra={
                "source_id": source.id,
                "status": source.status,
                "chunk_count": len(chunks_text),
            },
        )

        return self._to_schema(source)

    def search(
        self, db: Session, request: KnowledgeSearchRequest
    ) -> List[KnowledgeSearchResult]:
        """
        RAG 検索: クエリを埋め込み化し、pgvector コサイン類似度で検索する。
        """
        # 1. クエリを埋め込み化
        try:
            query_embeddings = self._embed_texts([request.query])
        except Exception as exc:
            raise KnowledgeServiceError(
                f"Failed to embed search query: {exc}"
            ) from exc

        query_vector = query_embeddings[0]

        # 2. pgvector コサイン距離 SQL
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
        """status='pending' のアイテムを全件取得する。"""
        return self.get_items(db, status=KnowledgeItemStatus.PENDING.value)

    def get_items(
        self, db: Session, *, status: Optional[str] = None
    ) -> List[KnowledgeItem]:
        """
        アイテムを全件取得する。status を指定するとフィルタリングする。
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
        アイテムのステータスを更新する。

        item_id が存在しない場合は KnowledgeServiceError を送出する。
        """
        source = db.query(KnowledgeSource).filter(
            KnowledgeSource.id == item_id
        ).first()

        if source is None:
            raise KnowledgeServiceError(
                f"KnowledgeSource not found: id={item_id}"
            )

        source.status = status.value
        db.commit()
        db.refresh(source)

        logger.info(
            "KnowledgeSource status updated",
            extra={"source_id": item_id, "status": status.value},
        )

        return self._to_schema(source)

    # ------------------------------------------------------------------ #
    # 内部ヘルパー                                                         #
    # ------------------------------------------------------------------ #

    def _resolve_raw_text(
        self, request: KnowledgeCreateRequest
    ) -> tuple[str, Optional[str]]:
        """
        リクエストの種別に応じてテキストと推定タイトルを返す。

        Returns:
            (raw_text, title): テキスト本文と推定タイトル（不明の場合は None）
        """
        if request.item_type == KnowledgeItemType.URL:
            if not request.source_url:
                raise KnowledgeServiceError(
                    "source_url is required when item_type is 'url'."
                )
            raw_text = self._scrape_url(request.source_url)
            return raw_text, None

        # TEXT 種別
        if not request.raw_text:
            raise KnowledgeServiceError(
                "raw_text is required when item_type is 'text'."
            )
        return request.raw_text, None

    def _scrape_url(self, url: str) -> str:
        """
        URL をスクレイピングしてクリーンなテキストを返す。

        httpx (同期) + BeautifulSoup を使用する。
        <article> → <main> → <body> の優先順位でテキストを抽出する。
        """
        if httpx is None:
            raise KnowledgeServiceError(
                "httpx is not installed. Install it with: pip install httpx"
            )
        if BeautifulSoup is None:
            raise KnowledgeServiceError(
                "beautifulsoup4 is not installed. "
                "Install it with: pip install beautifulsoup4"
            )

        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (compatible; UltraAutoTrade/1.0)"
                        )
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise KnowledgeServiceError(
                f"HTTP error while scraping {url}: {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise KnowledgeServiceError(
                f"Network error while scraping {url}: {exc}"
            ) from exc

        soup = BeautifulSoup(response.text, "html.parser")

        # 不要なタグを除去する
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # テキスト抽出優先順位: <article> → <main> → <body>
        target = (
            soup.find("article")
            or soup.find("main")
            or soup.find("body")
            or soup
        )

        raw_text = target.get_text(separator="\n", strip=True)

        # 空行を圧縮してクリーンアップ
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        cleaned = "\n".join(lines)

        if not cleaned:
            raise KnowledgeServiceError(
                f"No text content extracted from URL: {url}"
            )

        logger.info(
            "URL scraped successfully",
            extra={"url": url, "text_length": len(cleaned)},
        )

        return cleaned

    def _chunk_text(self, text: str) -> List[str]:
        """
        テキストをチャンクに分割する。

        tiktoken を使用して ~chunk_size_tokens トークンの断片に分割し、
        chunk_overlap_tokens トークンのオーバーラップを持たせる。
        """
        if self._tokenizer is None:
            # tiktoken が利用できない場合は単純な文字数分割にフォールバック
            logger.warning(
                "tiktoken not available, falling back to character-based chunking"
            )
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
        テキストリストを OpenAI API でバッチ埋め込みする。

        Returns:
            各テキストに対応する埋め込みベクトルのリスト
        """
        if not texts:
            return []

        try:
            response = self._openai.embeddings.create(
                model=self._settings.embedding_model,
                input=texts,
            )
        except Exception as exc:
            raise KnowledgeServiceError(
                f"OpenAI embeddings API call failed: {exc}"
            ) from exc

        # レスポンスは index 順に並んでいることが保証されているが念のためソート
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [item.embedding for item in sorted_data]

    def _to_schema(self, source: KnowledgeSource) -> KnowledgeItem:
        """
        KnowledgeSource ORM オブジェクトを KnowledgeItem スキーマに変換する。
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
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
