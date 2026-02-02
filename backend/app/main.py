# backend/app/main.py

"""
バックエンドアプリケーションのエントリーポイント。

Phase1 の主な責務:
- /notion/ingest エンドポイントを公開する

Phase2 で追加された責務:
- /ai/analyze エンドポイントを公開する

Phase5 で追加された責務:
- バックグラウンド監視タスクの起動・停止

Phase6 で追加された責務:
- 日次・週次レポートの自動生成スケジューラ

Phase12 で追加された責務:
- ユーザー認証・アカウント管理
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.router import router as ai_router
from app.automation.automation_router import router as automation_router
from app.bots.router import router as octobot_router
from app.notion.router import router as notion_router
from app.aave.router import router as aave_router
from app.api.automation_dashboard import router as automation_dashboard_router
from app.auth.router import router as auth_router
from app.users.router import router as users_router
from app.database import init_db

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ultra AutoTrade API",
        version="0.1.0",
    )

    # --- CORS 設定 ---
    # フロントエンドからのアクセスを許可
    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- ルーター登録 ---
    app.include_router(auth_router)     # Auth (Phase12)
    app.include_router(users_router)    # Users (Phase12)
    app.include_router(notion_router)   # Notion (Phase1)
    app.include_router(ai_router)       # AI (Phase2)
    app.include_router(octobot_router)  # OctoBot (Phase3)
    app.include_router(aave_router)     # Aave (Phase4)
    app.include_router(automation_router)  # Automation workflow
    app.include_router(
        automation_dashboard_router,
        prefix="/api/automation",
    )

    @app.get("/health", tags=["health"])
    def health_check() -> dict:
        return {"status": "ok"}

    # --- データベース初期化 (Phase12) ---
    @app.on_event("startup")
    async def startup_database():
        """
        アプリケーション起動時にデータベースを初期化する。
        """
        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as exc:
            logger.error("Failed to initialize database: %s", exc)

    # --- バックグラウンド監視タスク (Phase5) ---
    @app.on_event("startup")
    async def startup_event():
        """
        アプリケーション起動時にバックグラウンド監視を開始する。

        環境変数 ENABLE_BACKGROUND_MONITORING=1 で有効化。
        開発環境ではデフォルト無効。
        """
        enable_monitoring = os.getenv("ENABLE_BACKGROUND_MONITORING", "0") == "1"

        if not enable_monitoring:
            logger.info(
                "Background monitoring disabled "
                "(set ENABLE_BACKGROUND_MONITORING=1 to enable)"
            )
            return

        try:
            from app.automation.background_tasks import get_task_manager
            from app.automation.state import get_monitoring_service
            from app.aave.client import get_default_aave_client

            # サービスとクライアントの初期化（シングルトン）
            monitoring_service = get_monitoring_service()
            aave_client = get_default_aave_client()

            task_manager = get_task_manager()

            await task_manager.start_monitoring(
                get_health_factor_func=aave_client.get_health_factor,
                # HF=None も記録する（state.json の last_update を常に更新）
                # MonitoringService.record_health_factor() は None を正しく処理する
                on_health_factor=lambda hf: monitoring_service.record_health_factor(hf),
                interval_seconds=float(
                    os.getenv("MONITORING_INTERVAL_SECONDS", "60")
                ),
            )

            logger.info("Background monitoring started successfully")

        except Exception as exc:
            logger.error("Failed to start background monitoring: %s", exc)
            # 監視の起動失敗はアプリ起動をブロックしない（fail-safe）

    @app.on_event("shutdown")
    async def shutdown_event():
        """
        アプリケーション終了時にバックグラウンド監視を停止する。
        """
        try:
            from app.automation.background_tasks import get_task_manager

            task_manager = get_task_manager()

            if task_manager.is_running:
                await task_manager.stop_monitoring()
                logger.info("Background monitoring stopped")

        except Exception as exc:
            logger.error("Error during shutdown: %s", exc)

    # --- スケジュールタスク (Phase6) ---
    @app.on_event("startup")
    async def startup_scheduled_tasks():
        """
        アプリケーション起動時にスケジュールタスクを開始する。

        環境変数で制御:
            ENABLE_DAILY_REPORTS=1: 日次レポート有効化
            ENABLE_WEEKLY_REPORTS=1: 週次レポート有効化
        """
        enable_daily = os.getenv("ENABLE_DAILY_REPORTS", "0") == "1"
        enable_weekly = os.getenv("ENABLE_WEEKLY_REPORTS", "0") == "1"

        if not enable_daily and not enable_weekly:
            logger.info(
                "Scheduled reports disabled "
                "(set ENABLE_DAILY_REPORTS=1 or ENABLE_WEEKLY_REPORTS=1 to enable)"
            )
            return

        try:
            from app.automation.scheduled_tasks import get_scheduled_task_manager
            from app.notifications.config import get_notification_settings

            settings = get_notification_settings()
            scheduled_manager = get_scheduled_task_manager()

            if enable_daily:
                await scheduled_manager.start_daily_reports(
                    channel=settings.default_channel,
                )
                logger.info("Daily reports scheduled successfully")

            if enable_weekly:
                await scheduled_manager.start_weekly_reports(
                    channel=settings.default_channel,
                )
                logger.info("Weekly reports scheduled successfully")

        except Exception as exc:
            logger.error("Failed to start scheduled tasks: %s", exc)
            # スケジュールタスクの起動失敗はアプリ起動をブロックしない（fail-safe）

    @app.on_event("shutdown")
    async def shutdown_scheduled_tasks():
        """
        アプリケーション終了時にスケジュールタスクを停止する。
        """
        try:
            from app.automation.scheduled_tasks import get_scheduled_task_manager

            scheduled_manager = get_scheduled_task_manager()

            if scheduled_manager.is_daily_running or scheduled_manager.is_weekly_running:
                await scheduled_manager.stop_all()
                logger.info("Scheduled tasks stopped")

        except Exception as exc:
            logger.error("Error during scheduled tasks shutdown: %s", exc)

    return app


app = create_app()
