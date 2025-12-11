import pytest

from app.bots.client import (
    OctoBotClient,
    OctoBotClientError,
    OctoBotHTTPError,
)


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
