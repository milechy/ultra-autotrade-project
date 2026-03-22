# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/main.py

"""
Backend application entry point.

Responsibilities added in Phase 2:
- Expose /ai/analyze endpoint

Responsibilities added in Phase 5:
- Start and stop background monitoring tasks

Responsibilities added in Phase 6:
- Scheduler for automatic daily/weekly report generation

Responsibilities added in Phase 12:
- User authentication and account management
"""

import logging
import os
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.aave.fee_router import router as fee_router
from app.aave.rebalance_router import router as rebalance_router
from app.aave.router import router as aave_router
from app.aave.transparency_router import router as transparency_router
from app.ai.decisions_router import router as ai_decisions_router
from app.ai.router import router as ai_router
from app.api.automation_dashboard import router as automation_dashboard_router
from app.auth.router import router as auth_router
from app.auth.service import AuthService
from app.automation.automation_router import router as automation_router
from app.automation.howl_review import start_howl_background_task
from app.billing.router import router as billing_router
from app.bots.router import router as octobot_router
from app.data_feeds.finance_feed import start_finance_background_task
from app.data_feeds.geopolitical import start_geo_risk_background_task
from app.data_feeds.news_feed import start_news_background_task
from app.data_feeds.router import router as data_feeds_router
from app.database import init_db
from app.dca.router import router as dca_router
from app.error_handlers import register_error_handlers
from app.exchange.router import router as exchange_router
from app.hooks.router import router as hooks_router
from app.knowledge.router import router as knowledge_router
from app.portfolio.router import router as portfolio_router
from app.proposals.router import router as proposals_router
from app.reports.router import router as reports_router
from app.rss.router import router as rss_router
from app.transactions.router import admin_router as admin_transactions_router
from app.transactions.router import router as transactions_router
from app.users.router import router as users_router
from app.users.settings_router import router as user_settings_router
from app.webhook.router import router as webhook_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    _is_dev = os.getenv("APP_ENV", "development") == "development"
    app = FastAPI(
        title="Ultra AutoTrade API",
        version="0.1.0",
        docs_url="/docs" if _is_dev else None,
        redoc_url="/redoc" if _is_dev else None,
        openapi_url="/openapi.json" if _is_dev else None,
    )

    # --- CORS configuration ---
    # Allow access from frontend origins.
    # CORS_ORIGINS env var accepts comma-separated origins (whitespace is auto-trimmed).
    _default_origins = "http://localhost:3000"
    cors_origins = [
        o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Remove server info headers in production
    @app.middleware("http")
    async def remove_server_header(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response: Response = await call_next(request)
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]
        return response

    # --- Router registration ---
    app.include_router(auth_router)  # Auth (Phase12)
    app.include_router(users_router)  # Users (Phase12)
    app.include_router(ai_router)  # AI (Phase2)
    app.include_router(octobot_router)  # OctoBot (Phase3)
    app.include_router(aave_router, prefix="/api")  # Aave (Phase4)
    app.include_router(rebalance_router, prefix="/api")  # Aave Rebalance (Stream-T)
    app.include_router(knowledge_router)  # Knowledge Hub (PoC Pivot Step 2)
    app.include_router(dca_router)  # DCA Bot
    app.include_router(exchange_router)  # Exchange (PoC Pivot Step 3)
    app.include_router(rss_router)  # RSS auto-fetch
    app.include_router(webhook_router)  # Webhook receiver
    app.include_router(hooks_router)  # Slack approval gate (Claude Code hooks)
    app.include_router(automation_router)  # Automation workflow
    app.include_router(transparency_router)  # Transparency (Wave 2)
    app.include_router(fee_router)  # Fee calculation (CSV)
    app.include_router(
        automation_dashboard_router,
        prefix="/api/automation",
    )
    app.include_router(data_feeds_router)  # External data feeds (Phase 2)
    app.include_router(reports_router, prefix="/api/reports")  # Monthly reports
    app.include_router(billing_router)
    app.include_router(ai_decisions_router)  # AI Decisions API
    app.include_router(transactions_router)  # Transactions API
    app.include_router(admin_transactions_router)  # Admin Transactions API
    app.include_router(proposals_router)  # Proposals API
    app.include_router(portfolio_router)  # Portfolio History API
    app.include_router(user_settings_router)  # User Settings API

    # Register global error handlers (production safety)
    register_error_handlers(app)

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "env": os.getenv("APP_ENV", "dev")}

    # --- Database initialization (Phase12) ---
    @app.on_event("startup")
    async def startup_database() -> None:
        """
        Initialize the database on application startup.
        """
        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as exc:
            logger.error("Failed to initialize database: %s", exc)

        # Validate JWT secret key strength (rejects weak keys in staging/production)
        AuthService.validate_secret_key()

    @app.on_event("startup")
    async def startup_judgment_logger() -> None:
        """Initialize AI judgment logger (JSONL + cognitive state)."""
        try:
            from app.ai.judgment_log import get_judgment_logger

            await get_judgment_logger().initialize()
            logger.info("JudgmentLogger initialized")
        except Exception as exc:
            logger.error("Failed to initialize JudgmentLogger: %s", exc)

    # --- Background monitoring tasks (Phase5) ---
    @app.on_event("startup")
    async def startup_event() -> None:
        """
        Start background monitoring on application startup.

        Enabled by setting ENABLE_BACKGROUND_MONITORING=1.
        Disabled by default in development.
        """
        enable_monitoring = os.getenv("ENABLE_BACKGROUND_MONITORING", "0") == "1"

        if not enable_monitoring:
            logger.info(
                "Background monitoring disabled (set ENABLE_BACKGROUND_MONITORING=1 to enable)"
            )
            return

        try:
            from app.aave.client import get_default_aave_client
            from app.automation.background_tasks import get_task_manager
            from app.automation.state import get_monitoring_service

            # Initialize services and clients (singleton pattern)
            monitoring_service = get_monitoring_service()
            aave_client = get_default_aave_client()

            task_manager = get_task_manager()

            await task_manager.start_monitoring(
                get_health_factor_func=aave_client.get_health_factor,
                # Record HF=None as well (always update last_update in state.json)
                # MonitoringService.record_health_factor() handles None correctly
                on_health_factor=lambda hf: (monitoring_service.record_health_factor(hf), None)[-1],
                interval_seconds=float(os.getenv("MONITORING_INTERVAL_SECONDS", "60")),
            )

            logger.info("Background monitoring started successfully")

        except Exception as exc:
            logger.error("Failed to start background monitoring: %s", exc)
            # Monitoring startup failure does not block app startup (fail-safe)

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """
        Stop background monitoring on application shutdown.
        """
        try:
            from app.automation.background_tasks import get_task_manager

            task_manager = get_task_manager()

            if task_manager.is_running:
                await task_manager.stop_monitoring()
                logger.info("Background monitoring stopped")

        except Exception as exc:
            logger.error("Error during shutdown: %s", exc)

    # --- External data feed background tasks (Phase 2 Data Intelligence) ---
    @app.on_event("startup")
    async def startup_data_feeds() -> None:
        """Start data feed background tasks (geo-risk + news)."""
        import asyncio

        geo_interval = int(os.getenv("GEO_RISK_INTERVAL_MINUTES", "30"))
        news_interval = int(os.getenv("NEWS_INTERVAL_MINUTES", "15"))
        try:
            asyncio.create_task(start_geo_risk_background_task(interval_minutes=geo_interval))
            logger.info("GeoRisk background task started (interval=%dmin)", geo_interval)
            asyncio.create_task(start_news_background_task(interval_minutes=news_interval))
            logger.info("News background task started (interval=%dmin)", news_interval)
            finance_interval = int(os.getenv("FINANCE_INTERVAL_MINUTES", "60"))
            asyncio.create_task(start_finance_background_task(interval_minutes=finance_interval))
            logger.info("Finance background task started (interval=%dmin)", finance_interval)
            howl_interval = int(os.getenv("HOWL_INTERVAL_HOURS", "6"))
            asyncio.create_task(start_howl_background_task(interval_hours=howl_interval))
            logger.info("HOWL review background task started (interval=%dh)", howl_interval)
        except Exception as exc:
            logger.error("Failed to start data feed background tasks: %s", exc)

    # --- Scheduled tasks (Phase6) ---
    @app.on_event("startup")
    async def startup_scheduled_tasks() -> None:
        """
        Start scheduled tasks on application startup.

        Controlled by environment variables:
            ENABLE_DAILY_REPORTS=1: enable daily reports
            ENABLE_WEEKLY_REPORTS=1: enable weekly reports
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
            # Scheduled task startup failure does not block app startup (fail-safe)

    @app.on_event("shutdown")
    async def shutdown_scheduled_tasks() -> None:
        """
        Stop scheduled tasks on application shutdown.
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


limiter = Limiter(key_func=get_remote_address)
app = create_app()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
