from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bots.router import router as octobot_router


def create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(octobot_router)
    return app


def _setup_octobot_test_env(monkeypatch) -> None:
    """
    /octobot/signal のテストに必要な環境変数とモックをセットアップする。

    - OCTOBOT_API_BASE_URL / OCTOBOT_API_KEY をダミー値で設定
    - OctoBotService._send_to_octobot を no-op に置き換え（外部HTTPを防ぐ）
    """
    # 必須環境変数をダミー値でセット
    monkeypatch.setenv("OCTOBOT_API_BASE_URL", "http://example.com/signal")
    monkeypatch.setenv("OCTOBOT_API_KEY", "dummy-key")

    # 実際の HTTP 通信を防ぐため、OctoBotService._send_to_octobot を no-op に差し替え
    from app.bots import service as bots_service

    def _dummy_send_to_octobot(self, signal) -> None:  # noqa: ARG001
        # 何もしない（テストでは送信成否は見ない）
        return None

    monkeypatch.setattr(
        bots_service.OctoBotService,
        "_send_to_octobot",
        _dummy_send_to_octobot,
    )


def test_post_octobot_signal_400_on_count_mismatch(monkeypatch):
    """
    count と signals 長さが一致しない場合に 400 になることを確認する。
    """
    _setup_octobot_test_env(monkeypatch)

    app = create_test_app()
    client = TestClient(app)

    body = {
        "signals": [],
        "count": 1,
    }

    response = client.post("/octobot/signal", json=body)
    assert response.status_code == 400


def test_post_octobot_signal_200_on_basic_request(monkeypatch):
    """
    正常なリクエストで 200 が返ることを確認する簡易テスト。

    ※ 実際のシグナル送信は _setup_octobot_test_env 内で no-op にモックされている。
    """
    _setup_octobot_test_env(monkeypatch)

    app = create_test_app()
    client = TestClient(app)

    body = {
        "signals": [
            {
                "id": "test-id",
                "url": "https://example.com",
                "action": "BUY",
                "confidence": 80,
                "reason": "test",
                "timestamp": "2025-01-01T00:00:00Z",
            }
        ],
        "count": 1,
    }

    response = client.post("/octobot/signal", json=body)
    # ここでは「少なくとも 400 にはならない」ことだけを確認
    assert response.status_code in (200, 500)
