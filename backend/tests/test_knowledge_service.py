# backend/tests/test_knowledge_service.py
"""Knowledge Hub service tests with mocked embeddings and HTTP."""
import pytest
from unittest.mock import patch, MagicMock
from app.knowledge.service import KnowledgeService
from app.knowledge.schemas import KnowledgeCreateRequest, KnowledgeItemType


# Since pgvector requires PostgreSQL, these tests focus on the service logic
# with mocked DB interactions and mocked OpenAI embeddings.


class TestKnowledgeServiceChunking:
    """Test text chunking logic."""

    def test_chunk_text_splits_correctly(self):
        """Verify text is split into chunks of appropriate size."""
        with patch("app.knowledge.service.OpenAI"), \
             patch("app.knowledge.service.tiktoken") as mock_tiktoken:
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
        with patch("app.knowledge.service.OpenAI"), \
             patch("app.knowledge.service.tiktoken") as mock_tiktoken:
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
        with patch("app.knowledge.service.OpenAI") as mock_openai_cls, \
             patch("app.knowledge.service.tiktoken") as mock_tiktoken:
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
        with patch("app.knowledge.service.OpenAI"), \
             patch("app.knowledge.service.tiktoken") as mock_tiktoken:
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
        with patch("app.knowledge.service.OpenAI"), \
             patch("app.knowledge.service.tiktoken") as mock_tiktoken:
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
