# backend/tests/test_dca_router.py

"""
DCA ルーターのテスト。

FastAPI TestClient を使用してエンドポイントをテストする。
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dca.config import reset_dca_config
from app.dca.router import _get_dca_service
from app.dca.schemas import DCAExecutionResult, DCAFrequency
from app.dca.service import DCAService
from app.main import app


@pytest.fixture(autouse=True)
def _reset_config() -> None:  # type: ignore[return]
    """各テスト後に DCA 設定をリセットする。"""
    yield
    reset_dca_config()
    app.dependency_overrides.clear()


class TestPostDcaExecuteSuccess:
    """test_post_dca_execute_success: POST /dca/execute が成功する。"""

    def test_post_dca_execute_success(self) -> None:
        mock_result = DCAExecutionResult(
            executed=True,
            symbol="BTC/USDT",
            amount_usd=Decimal("10"),
            order_id="test-order-001",
            message="DCA executed",
        )

        mock_service = MagicMock(spec=DCAService)
        mock_service.execute.return_value = mock_result

        app.dependency_overrides[_get_dca_service] = lambda: mock_service

        client = TestClient(app)
        response = client.post("/dca/execute")

        assert response.status_code == 200
        data = response.json()
        assert data["executed"] is True
        assert data["order_id"] == "test-order-001"


class TestGetDcaConfig:
    """test_get_dca_config: GET /dca/config が正しい設定を返す。"""

    def test_get_dca_config(self) -> None:
        env_overrides = {
            "DCA_ENABLED": "true",
            "DCA_AMOUNT_USD": "25",
            "DCA_SYMBOL": "ETH/USDT",
            "DCA_FREQUENCY": "hourly",
            "DCA_DRY_RUN": "true",
        }

        with pytest.MonkeyPatch().context() as mp:
            for key, value in env_overrides.items():
                mp.setenv(key, value)

            reset_dca_config()
            client = TestClient(app)
            response = client.get("/dca/config")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["symbol"] == "ETH/USDT"
        assert Decimal(data["amount_usd"]) == Decimal("25")
        assert data["frequency"] == DCAFrequency.HOURLY.value
        assert data["dry_run"] is True


class TestPostDcaConfigUpdate:
    """test_post_dca_config_update: POST /dca/config で設定が更新される。"""

    def test_post_dca_config_update(self) -> None:
        reset_dca_config()
        client = TestClient(app)

        new_config = {
            "enabled": True,
            "symbol": "SOL/USDT",
            "amount_usd": "100",
            "frequency": "weekly",
            "dry_run": False,
        }

        post_response = client.post("/dca/config", json=new_config)
        assert post_response.status_code == 200
        post_data = post_response.json()
        assert post_data["symbol"] == "SOL/USDT"
        assert Decimal(post_data["amount_usd"]) == Decimal("100")
        assert post_data["frequency"] == "weekly"
        assert post_data["dry_run"] is False

        # GET で更新が反映されていることを確認
        get_response = client.get("/dca/config")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["symbol"] == "SOL/USDT"
        assert get_data["frequency"] == "weekly"
