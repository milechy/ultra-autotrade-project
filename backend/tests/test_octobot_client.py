from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.bots.client import (
    OctoBotClient,
    OctoBotClientError,
    OctoBotConnectionError,
    OctoBotHTTPError,
)
from app.bots.config import OctoBotSettings


def _make_settings(**kwargs) -> OctoBotSettings:
    defaults = dict(
        base_url="http://octobot.local/signal",
        api_key="test-api-key",
        timeout_seconds=5,
    )
    defaults.update(kwargs)
    return OctoBotSettings(**defaults)


def test_octobot_http_error_is_client_error():
    """
    OctoBotHTTPError が OctoBotClientError のサブクラスであることだけ確認する簡易テスト。
    """
    assert issubclass(OctoBotHTTPError, OctoBotClientError)


def test_octobot_client_can_be_instantiated_with_dummy_settings(monkeypatch):
    """
    設定取得部分を monkeypatch して、OctoBotClient が初期化できることを確認する雛形。
    """
    from app.bots import config as bots_config

    def fake_get_env(name, default=None, required=False):
        if name == "OCTOBOT_API_BASE_URL":
            return "http://example.com/signal"
        if name == "OCTOBOT_API_KEY":
            return "dummy-key"
        if name == "OCTOBOT_TIMEOUT_SECONDS":
            return "5"
        return default

    monkeypatch.setattr("app.bots.config.get_env", fake_get_env)

    settings = bots_config.get_octobot_settings()
    client = OctoBotClient(settings=settings)

    assert client.base_url == "http://example.com/signal"
    assert client.api_key == "dummy-key"
    assert client.timeout == 5


# ---------------------------------------------------------------------------
# OctoBotHTTPError init
# ---------------------------------------------------------------------------


class TestOctoBotHTTPError:
    def test_stores_status_code_and_body(self):
        err = OctoBotHTTPError(status_code=422, body={"error": "invalid"})
        assert err.status_code == 422
        assert err.body == {"error": "invalid"}

    def test_body_defaults_to_none(self):
        err = OctoBotHTTPError(status_code=500)
        assert err.body is None

    def test_str_contains_status_code(self):
        err = OctoBotHTTPError(status_code=404)
        assert "404" in str(err)

    def test_is_subclass_of_octobot_client_error(self):
        assert issubclass(OctoBotHTTPError, OctoBotClientError)


# ---------------------------------------------------------------------------
# OctoBotClient._build_headers
# ---------------------------------------------------------------------------


class TestBuildHeaders:
    def test_returns_content_type_and_authorization(self):
        settings = _make_settings(api_key="my-secret-key")
        client = OctoBotClient(settings=settings)
        headers = client._build_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer my-secret-key"


# ---------------------------------------------------------------------------
# OctoBotClient.send_signal
# ---------------------------------------------------------------------------


class TestSendSignal:
    def test_send_signal_success_returns_json(self):
        settings = _make_settings()
        client = OctoBotClient(settings=settings)
        payload = {"action": "BUY", "confidence": 80}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        with patch("httpx.Client") as mock_httpx_cls:
            mock_httpx_client = MagicMock()
            mock_httpx_client.__enter__ = MagicMock(return_value=mock_httpx_client)
            mock_httpx_client.__exit__ = MagicMock(return_value=False)
            mock_httpx_client.post.return_value = mock_response
            mock_httpx_cls.return_value = mock_httpx_client

            result = client.send_signal(payload)

        assert result == {"status": "ok"}

    def test_send_signal_http_error_raises_octobot_http_error(self):
        settings = _make_settings()
        client = OctoBotClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {"detail": "bad request"}

        with patch("httpx.Client") as mock_httpx_cls:
            mock_httpx_client = MagicMock()
            mock_httpx_client.__enter__ = MagicMock(return_value=mock_httpx_client)
            mock_httpx_client.__exit__ = MagicMock(return_value=False)
            mock_httpx_client.post.return_value = mock_response
            mock_httpx_cls.return_value = mock_httpx_client

            with pytest.raises(OctoBotHTTPError) as exc_info:
                client.send_signal({"action": "BUY"})

        assert exc_info.value.status_code == 422

    def test_send_signal_http_error_non_json_body(self):
        """When response body is not JSON, body is stored as text."""
        settings = _make_settings()
        client = OctoBotClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "Internal Server Error"

        with patch("httpx.Client") as mock_httpx_cls:
            mock_httpx_client = MagicMock()
            mock_httpx_client.__enter__ = MagicMock(return_value=mock_httpx_client)
            mock_httpx_client.__exit__ = MagicMock(return_value=False)
            mock_httpx_client.post.return_value = mock_response
            mock_httpx_cls.return_value = mock_httpx_client

            with pytest.raises(OctoBotHTTPError) as exc_info:
                client.send_signal({"action": "SELL"})

        assert exc_info.value.body == "Internal Server Error"

    def test_send_signal_connection_error_raises_octobot_connection_error(self):
        settings = _make_settings()
        client = OctoBotClient(settings=settings)

        with patch("httpx.Client") as mock_httpx_cls:
            mock_httpx_client = MagicMock()
            mock_httpx_client.__enter__ = MagicMock(return_value=mock_httpx_client)
            mock_httpx_client.__exit__ = MagicMock(return_value=False)
            mock_httpx_client.post.side_effect = httpx.RequestError("connection refused")
            mock_httpx_cls.return_value = mock_httpx_client

            with pytest.raises(OctoBotConnectionError):
                client.send_signal({"action": "HOLD"})

    def test_send_signal_non_json_success_response_returns_raw(self):
        """200 response with non-JSON body returns {'raw': text}."""
        settings = _make_settings()
        client = OctoBotClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "OK"

        with patch("httpx.Client") as mock_httpx_cls:
            mock_httpx_client = MagicMock()
            mock_httpx_client.__enter__ = MagicMock(return_value=mock_httpx_client)
            mock_httpx_client.__exit__ = MagicMock(return_value=False)
            mock_httpx_client.post.return_value = mock_response
            mock_httpx_cls.return_value = mock_httpx_client

            result = client.send_signal({"action": "BUY"})

        assert result == {"raw": "OK"}
