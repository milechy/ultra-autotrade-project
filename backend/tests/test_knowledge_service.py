# backend/tests/test_knowledge_service.py
"""Knowledge Hub service tests with mocked embeddings and HTTP."""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.knowledge.config import _get_env_int, get_knowledge_settings
from app.knowledge.schemas import (
    KnowledgeCreateRequest,
    KnowledgeItemStatus,
    KnowledgeItemType,
    KnowledgeSearchRequest,
)
from app.knowledge.service import KnowledgeService, KnowledgeServiceError

# Since pgvector requires PostgreSQL, these tests focus on the service logic
# with mocked DB interactions and mocked OpenAI embeddings.


class TestKnowledgeServiceChunking:
    """Test text chunking logic."""

    def test_chunk_text_splits_correctly(self):
        """Verify text is split into chunks of appropriate size."""
        with (
            patch("app.knowledge.service.OpenAI"),
            patch("app.knowledge.service.tiktoken") as mock_tiktoken,
        ):
            mock_enc = MagicMock()
            # Simulate 1000 tokens
            mock_enc.encode.return_value = list(range(1000))
            mock_enc.decode.side_effect = lambda tokens: f"chunk({len(tokens)} tokens)"
            mock_tiktoken.encoding_for_model.return_value = mock_enc

            settings = MagicMock()
            settings.openai_api_key = "test-key"
            settings.chunk_size_tokens = 500
            settings.chunk_overlap_tokens = 50

            service = KnowledgeService(settings=settings)
            chunks = service._chunk_text("A" * 5000)

            # Should produce multiple chunks
            assert len(chunks) >= 2
            # Each call to decode should get ~500 tokens (except possibly last)

    def test_chunk_text_single_small_text(self):
        """Small text should produce exactly one chunk."""
        with (
            patch("app.knowledge.service.OpenAI"),
            patch("app.knowledge.service.tiktoken") as mock_tiktoken,
        ):
            mock_enc = MagicMock()
            mock_enc.encode.return_value = list(range(100))  # 100 tokens
            mock_enc.decode.side_effect = lambda tokens: "short text"
            mock_tiktoken.encoding_for_model.return_value = mock_enc

            settings = MagicMock()
            settings.openai_api_key = "test-key"
            settings.chunk_size_tokens = 500
            settings.chunk_overlap_tokens = 50

            service = KnowledgeService(settings=settings)
            chunks = service._chunk_text("short text")

            assert len(chunks) == 1


class TestKnowledgeServiceEmbedding:
    """Test embedding logic."""

    def test_embed_texts_calls_openai(self):
        """Verify OpenAI embedding API is called correctly."""
        with patch("app.knowledge.service.tiktoken") as mock_tiktoken:
            mock_enc = MagicMock()
            mock_tiktoken.encoding_for_model.return_value = mock_enc

            mock_openai = MagicMock()
            mock_embedding_0 = MagicMock()
            mock_embedding_0.embedding = [0.1] * 1536
            mock_embedding_0.index = 0
            mock_embedding_1 = MagicMock()
            mock_embedding_1.embedding = [0.2] * 1536
            mock_embedding_1.index = 1
            mock_openai.embeddings.create.return_value = MagicMock(
                data=[mock_embedding_0, mock_embedding_1]
            )

            settings = MagicMock()
            settings.openai_api_key = "test-key"
            settings.embedding_model = "text-embedding-3-small"
            settings.embedding_dimensions = 1536

            with patch("app.knowledge.service.OpenAI", return_value=mock_openai):
                service = KnowledgeService(settings=settings)
                vectors = service._embed_texts(["hello", "world"])

            assert len(vectors) == 2
            assert len(vectors[0]) == 1536
            mock_openai.embeddings.create.assert_called_once()

    def test_embed_texts_empty_returns_empty(self):
        """Empty input should return empty list without calling API."""
        with (
            patch("app.knowledge.service.OpenAI") as mock_openai_cls,
            patch("app.knowledge.service.tiktoken") as mock_tiktoken,
        ):
            mock_tiktoken.encoding_for_model.return_value = MagicMock()
            mock_openai_instance = MagicMock()
            mock_openai_cls.return_value = mock_openai_instance

            settings = MagicMock()
            settings.openai_api_key = "test-key"

            service = KnowledgeService(settings=settings)
            result = service._embed_texts([])

            assert result == []
            mock_openai_instance.embeddings.create.assert_not_called()


class TestKnowledgeServiceScraping:
    """Test URL scraping."""

    def test_scrape_url_extracts_text(self):
        """Verify URL scraping extracts text content."""
        with (
            patch("app.knowledge.service.OpenAI"),
            patch("app.knowledge.service.tiktoken") as mock_tiktoken,
        ):
            mock_tiktoken.encoding_for_model.return_value = MagicMock()

            settings = MagicMock()
            settings.openai_api_key = "test-key"

            service = KnowledgeService(settings=settings)

            html = "<html><body><article><p>Bitcoin surges past 100k</p></article></body></html>"
            with patch("app.knowledge.service.httpx") as mock_httpx:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = html
                mock_response.raise_for_status = MagicMock()
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.get.return_value = mock_response
                mock_httpx.Client.return_value = mock_client

                text = service._scrape_url("https://example.com/news")
                assert "Bitcoin" in text or "bitcoin" in text.lower()

    def test_scrape_url_failure_raises(self):
        """URL scraping failure should raise KnowledgeServiceError."""
        with (
            patch("app.knowledge.service.OpenAI"),
            patch("app.knowledge.service.tiktoken") as mock_tiktoken,
        ):
            mock_tiktoken.encoding_for_model.return_value = MagicMock()

            settings = MagicMock()
            settings.openai_api_key = "test-key"

            service = KnowledgeService(settings=settings)

            import httpx as real_httpx

            with patch("app.knowledge.service.httpx") as mock_httpx:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                # Use the real httpx exception classes so the service's isinstance check works
                mock_httpx.RequestError = real_httpx.RequestError
                mock_httpx.HTTPStatusError = real_httpx.HTTPStatusError
                # Raise a RequestError (subclass of httpx.RequestError) to trigger the handler
                mock_client.get.side_effect = real_httpx.ConnectError("Connection refused")
                mock_httpx.Client.return_value = mock_client

                from app.knowledge.service import KnowledgeServiceError

                with pytest.raises(KnowledgeServiceError):
                    service._scrape_url("https://unreachable.example.com")


# ------------------------------------------------------------------ #
# Helper: build a KnowledgeService with all external deps mocked      #
# ------------------------------------------------------------------ #


def _make_service(settings=None):
    """Return a KnowledgeService with OpenAI and tiktoken mocked."""
    if settings is None:
        settings = MagicMock()
        settings.openai_api_key = "test-key"
        settings.embedding_model = "text-embedding-3-small"
        settings.embedding_dimensions = 1536
        settings.chunk_size_tokens = 500
        settings.chunk_overlap_tokens = 50
        settings.search_top_k = 5
    with (
        patch("app.knowledge.service.OpenAI"),
        patch("app.knowledge.service.tiktoken") as mock_tiktoken,
    ):
        mock_enc = MagicMock()
        mock_enc.encode.return_value = list(range(10))
        mock_enc.decode.side_effect = lambda ids: "chunk text"
        mock_tiktoken.encoding_for_model.return_value = mock_enc
        service = KnowledgeService(settings=settings)
    return service


def _fake_source(id_=1, status="analyzed", item_type="text", title="Test", raw_text="hello"):
    """Return a mock KnowledgeSource ORM object."""
    source = MagicMock()
    source.id = id_
    source.status = status
    source.item_type = item_type
    source.title = title
    source.source_url = None
    source.created_at = datetime.now(timezone.utc)
    source.updated_at = datetime.now(timezone.utc)
    doc = MagicMock()
    doc.raw_text = raw_text
    chunk = MagicMock()
    doc.chunks = [chunk]
    source.documents = [doc]
    return source


# ------------------------------------------------------------------ #
# TestKnowledgeServiceCRUD                                            #
# ------------------------------------------------------------------ #


class TestKnowledgeServiceCRUD:
    """Test create_item, get_pending, get_items, update_status with mocked DB."""

    def test_create_item_from_text(self):
        """create_item with raw_text should create source, document, chunks and return PENDING."""
        service = _make_service()

        request = KnowledgeCreateRequest(
            item_type=KnowledgeItemType.TEXT,
            raw_text="This is a test document.",
            title="Test Title",
        )

        fake_source = _fake_source(id_=42, status="pending")

        db = MagicMock()

        # After db.flush(), source.id is set by the mock already (MagicMock attribute)
        # We need to control what flush does to source.id by patching the constructor
        with (
            patch("app.knowledge.service.KnowledgeSource") as mock_source_cls,
            patch("app.knowledge.service.KnowledgeDocument"),
            patch("app.knowledge.service.KnowledgeChunk"),
            patch.object(service, "_chunk_text", return_value=["chunk1", "chunk2"]),
            patch.object(service, "_embed_texts", return_value=[[0.1] * 5, [0.2] * 5]),
        ):
            mock_source_cls.return_value = fake_source

            result = service.create_item(db, request)

        # db.add called for source and document + 2 chunks
        assert db.add.call_count >= 2
        db.commit.assert_called()
        db.refresh.assert_called_with(fake_source)
        assert result.id == 42

    def test_create_item_from_url(self):
        """create_item with source_url should scrape then store the item."""
        service = _make_service()

        request = KnowledgeCreateRequest(
            item_type=KnowledgeItemType.URL,
            source_url="https://example.com/article",
        )

        fake_source = _fake_source(id_=7, status="pending")

        db = MagicMock()

        with (
            patch("app.knowledge.service.KnowledgeSource") as mock_source_cls,
            patch("app.knowledge.service.KnowledgeDocument"),
            patch("app.knowledge.service.KnowledgeChunk"),
            patch.object(service, "_scrape_url", return_value="scraped body text"),
            patch.object(service, "_chunk_text", return_value=["scraped chunk"]),
            patch.object(service, "_embed_texts", return_value=[[0.3] * 5]),
        ):
            mock_source_cls.return_value = fake_source

            result = service.create_item(db, request)

        assert result.id == 7

    def test_create_item_url_without_source_url_raises(self):
        """create_item with item_type=URL and no source_url should raise KnowledgeServiceError."""
        service = _make_service()

        request = KnowledgeCreateRequest(
            item_type=KnowledgeItemType.URL,
            source_url=None,
        )

        db = MagicMock()

        with pytest.raises(KnowledgeServiceError, match="source_url is required"):
            service.create_item(db, request)

    def test_create_item_text_without_raw_text_raises(self):
        """create_item with item_type=TEXT and no raw_text should raise KnowledgeServiceError."""
        service = _make_service()

        request = KnowledgeCreateRequest(
            item_type=KnowledgeItemType.TEXT,
            raw_text=None,
        )

        db = MagicMock()

        with pytest.raises(KnowledgeServiceError, match="raw_text is required"):
            service.create_item(db, request)

    def test_create_item_embedding_failure_sets_error_status(self):
        """When embedding fails, source status should be set to ERROR before raising."""
        service = _make_service()

        request = KnowledgeCreateRequest(
            item_type=KnowledgeItemType.TEXT,
            raw_text="Some text content",
        )

        fake_source = _fake_source(id_=99, status="pending")

        db = MagicMock()

        with (
            patch("app.knowledge.service.KnowledgeSource") as mock_source_cls,
            patch("app.knowledge.service.KnowledgeDocument"),
            patch.object(service, "_chunk_text", return_value=["chunk"]),
            patch.object(service, "_embed_texts", side_effect=Exception("OpenAI down")),
        ):
            mock_source_cls.return_value = fake_source

            with pytest.raises(KnowledgeServiceError, match="Embedding generation failed"):
                service.create_item(db, request)

        assert fake_source.status == KnowledgeItemStatus.ERROR.value
        db.commit.assert_called()

    def test_get_pending_returns_pending_items(self):
        """get_pending should delegate to get_items with status='pending'."""
        service = _make_service()
        db = MagicMock()

        with patch.object(service, "get_items", return_value=[]) as mock_get_items:
            result = service.get_pending(db)

        mock_get_items.assert_called_once_with(db, status=KnowledgeItemStatus.PENDING.value)
        assert result == []

    def test_get_items_all(self):
        """get_items with no status filter returns all items."""
        service = _make_service()

        fake_source = _fake_source(id_=1, status="analyzed")
        db = MagicMock()

        # Mock the ORM query chain: db.query().filter().order_by().all()
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [fake_source]

        with patch.object(service, "_to_schema") as mock_to_schema:
            mock_to_schema.return_value = MagicMock(id=1)
            result = service.get_items(db)

        # filter should NOT have been called for unfiltered query
        mock_query.filter.assert_not_called()
        assert len(result) == 1

    def test_get_items_filtered_by_status(self):
        """get_items with status='pending' should filter the query."""
        service = _make_service()

        fake_source = _fake_source(id_=2, status="pending")
        db = MagicMock()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [fake_source]

        with patch.object(service, "_to_schema") as mock_to_schema:
            mock_to_schema.return_value = MagicMock(id=2)
            result = service.get_items(db, status="pending")

        mock_query.filter.assert_called_once()
        assert len(result) == 1

    def test_update_status_success(self):
        """update_status should change status and commit."""
        service = _make_service()

        fake_source = _fake_source(id_=5, status="pending")
        db = MagicMock()

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = fake_source

        with patch.object(service, "_to_schema") as mock_to_schema:
            mock_to_schema.return_value = MagicMock(id=5)
            _result = service.update_status(db, 5, KnowledgeItemStatus.ANALYZED)

        assert fake_source.status == KnowledgeItemStatus.ANALYZED.value
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(fake_source)

    def test_update_status_not_found_raises(self):
        """update_status with a nonexistent id should raise KnowledgeServiceError."""
        service = _make_service()

        db = MagicMock()
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(KnowledgeServiceError, match="KnowledgeSource not found"):
            service.update_status(db, 9999, KnowledgeItemStatus.SKIPPED)

    def test_search_returns_results(self):
        """search should embed query and return KnowledgeSearchResult objects."""
        service = _make_service()

        request = KnowledgeSearchRequest(query="bitcoin price", top_k=3)

        # Simulate one row returned by db.execute()
        fake_row = (
            10,
            20,
            "Bitcoin price is high",
            0.92,
            "https://news.example.com",
            "Crypto News",
        )

        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [fake_row]

        with patch.object(service, "_embed_texts", return_value=[[0.1] * 5]):
            results = service.search(db, request)

        assert len(results) == 1
        assert results[0].chunk_id == 10
        assert results[0].content == "Bitcoin price is high"
        assert results[0].similarity == pytest.approx(0.92)
        assert results[0].source_url == "https://news.example.com"

    def test_search_embedding_failure_raises(self):
        """search should raise KnowledgeServiceError if embedding fails."""
        service = _make_service()

        request = KnowledgeSearchRequest(query="test query")
        db = MagicMock()

        with patch.object(service, "_embed_texts", side_effect=Exception("API error")):
            with pytest.raises(KnowledgeServiceError, match="Failed to embed search query"):
                service.search(db, request)

    def test_to_schema_converts_correctly(self):
        """_to_schema should convert a KnowledgeSource ORM object to KnowledgeItem."""
        service = _make_service()

        fake_source = _fake_source(id_=3, status="analyzed", item_type="text", title="My Doc")

        result = service._to_schema(fake_source)

        assert result.id == 3
        assert result.status == KnowledgeItemStatus.ANALYZED
        assert result.item_type == KnowledgeItemType.TEXT
        assert result.title == "My Doc"
        assert result.chunk_count == 1  # _fake_source creates 1 doc with 1 chunk

    def test_to_schema_no_documents(self):
        """_to_schema should handle source with no documents (raw_text = None)."""
        service = _make_service()

        fake_source = _fake_source(id_=4, status="pending")
        fake_source.documents = []  # no documents

        result = service._to_schema(fake_source)

        assert result.raw_text is None
        assert result.chunk_count == 0


# ------------------------------------------------------------------ #
# TestKnowledgeConfig                                                  #
# ------------------------------------------------------------------ #


class TestKnowledgeConfig:
    """Test config.py: _get_env_int and get_knowledge_settings."""

    def test_get_env_int_uses_default_when_not_set(self):
        """_get_env_int returns default if env var is absent."""
        with patch.dict(os.environ, {}, clear=False):
            # Ensure the var is not set
            os.environ.pop("SOME_INT_VAR_999", None)
            result = _get_env_int("SOME_INT_VAR_999", default=42)
        assert result == 42

    def test_get_env_int_reads_valid_value(self):
        """_get_env_int returns parsed integer when env var is a valid int string."""
        with patch.dict(os.environ, {"SOME_INT_VAR_999": "123"}):
            result = _get_env_int("SOME_INT_VAR_999", default=0)
        assert result == 123

    def test_get_env_int_invalid_raises_runtime_error(self):
        """_get_env_int raises RuntimeError for non-integer env var values."""
        with patch.dict(os.environ, {"SOME_INT_VAR_999": "not-an-int"}):
            with pytest.raises(RuntimeError, match="Invalid integer value"):
                _get_env_int("SOME_INT_VAR_999", default=0)

    def test_get_knowledge_settings_defaults(self):
        """get_knowledge_settings returns defaults when optional vars are not set."""
        env_overrides = {
            "OPENAI_API_KEY": "sk-test-key",
        }
        # Remove optional vars to test defaults
        vars_to_remove = [
            "KNOWLEDGE_EMBEDDING_MODEL",
            "KNOWLEDGE_EMBEDDING_DIMENSIONS",
            "KNOWLEDGE_CHUNK_SIZE_TOKENS",
            "KNOWLEDGE_CHUNK_OVERLAP_TOKENS",
            "KNOWLEDGE_SEARCH_TOP_K",
        ]
        env_patch = {k: "" for k in vars_to_remove}
        env_patch.update(env_overrides)

        with patch.dict(os.environ, env_patch, clear=False):
            for var in vars_to_remove:
                os.environ.pop(var, None)
            settings = get_knowledge_settings()

        assert settings.openai_api_key == "sk-test-key"
        assert settings.embedding_model == "text-embedding-3-small"
        assert settings.embedding_dimensions == 1536
        assert settings.chunk_size_tokens == 500
        assert settings.chunk_overlap_tokens == 50
        assert settings.search_top_k == 5

    def test_get_knowledge_settings_custom_values(self):
        """get_knowledge_settings reads custom values from env vars."""
        env_overrides = {
            "OPENAI_API_KEY": "sk-custom",
            "KNOWLEDGE_EMBEDDING_MODEL": "text-embedding-ada-002",
            "KNOWLEDGE_EMBEDDING_DIMENSIONS": "768",
            "KNOWLEDGE_CHUNK_SIZE_TOKENS": "300",
            "KNOWLEDGE_CHUNK_OVERLAP_TOKENS": "30",
            "KNOWLEDGE_SEARCH_TOP_K": "10",
        }
        with patch.dict(os.environ, env_overrides):
            settings = get_knowledge_settings()

        assert settings.openai_api_key == "sk-custom"
        assert settings.embedding_model == "text-embedding-ada-002"
        assert settings.embedding_dimensions == 768
        assert settings.chunk_size_tokens == 300
        assert settings.chunk_overlap_tokens == 30
        assert settings.search_top_k == 10

    def test_get_knowledge_settings_missing_openai_key_returns_empty_string(self):
        """OPENAI_API_KEY absent results in an empty string (not required in config)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            settings = get_knowledge_settings()
        assert settings.openai_api_key == ""


# ------------------------------------------------------------------ #
# TestChunkTextFallback                                                #
# ------------------------------------------------------------------ #


class TestChunkTextFallback:
    """Test _chunk_text fallback when tiktoken is not available."""

    def test_chunk_text_without_tiktoken(self):
        """Without tiktoken, _chunk_text falls back to character-based splitting."""
        with (
            patch("app.knowledge.service.OpenAI"),
            patch("app.knowledge.service.tiktoken", None),
        ):
            settings = MagicMock()
            settings.openai_api_key = "test-key"
            settings.chunk_size_tokens = 10  # 10 * 4 = 40 chars per chunk
            settings.chunk_overlap_tokens = 2

            service = KnowledgeService(settings=settings)
            # 200 chars: will be split into chunks of 40 chars
            text = "A" * 200
            chunks = service._chunk_text(text)

        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.strip()  # no empty chunks
