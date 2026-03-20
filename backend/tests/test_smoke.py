# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
def test_smoke():
    assert 1 == 1


class TestCreateApp:
    """Tests for app.main.create_app() and health endpoint."""

    def test_create_app_returns_fastapi_instance(self):
        from fastapi import FastAPI

        from app.main import create_app

        app = create_app()
        assert isinstance(app, FastAPI)

    def test_create_app_has_correct_title(self):
        from app.main import create_app

        app = create_app()
        assert app.title == "Ultra AutoTrade API"

    def test_health_check_endpoint_returns_200(self):
        from fastapi.testclient import TestClient

        from app.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_returns_ok_status(self):
        from fastapi.testclient import TestClient

        from app.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"

    def test_cors_middleware_is_registered(self):
        """CORS middleware class is registered in the app middleware stack."""
        from starlette.middleware.cors import CORSMiddleware

        from app.main import create_app

        app = create_app()

        # user_middleware contains Middleware objects with cls attribute
        cors_registered = any(
            getattr(m, "cls", None) is CORSMiddleware for m in app.user_middleware
        )
        assert cors_registered, "CORSMiddleware should be registered"

    def test_module_level_app_is_created(self):
        """The module-level `app` is a valid FastAPI instance."""
        from fastapi import FastAPI

        from app import main

        assert isinstance(main.app, FastAPI)
