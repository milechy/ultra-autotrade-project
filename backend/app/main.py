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

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

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
from app.ai.feedback_router import router as ai_feedback_router
from app.ai.optimizer.router import router as ai_optimizer_router
from app.ai.router import router as ai_router
from app.api.alias_router import router as alias_router
from app.api.automation_dashboard import router as automation_dashboard_router
from app.api.v1.fee_transfer import router as fee_transfer_router
from app.api.v1.fees import router as fees_v10_router
from app.auth.router import router as auth_router
from app.auth.service import AuthService
from app.automation.automation_router import router as automation_router
from app.automation.howl_review import start_howl_background_task
from app.bots.router import router as octobot_router
from app.data_feeds.finance_feed import start_finance_background_task
from app.data_feeds.geopolitical import start_geo_risk_background_task
from app.data_feeds.mmt_feed import start_mmt_background_task
from app.data_feeds.news_feed import start_news_background_task
from app.data_feeds.router import router as data_feeds_router
from app.database import init_db
from app.dca.router import router as dca_router
from app.error_handlers import register_error_handlers
from app.exchange.router import router as exchange_router
from app.health.detail_router import router as health_detail_router
from app.hooks.router import router as hooks_router
from app.knowledge.router import router as knowledge_router
from app.notifications.models import (
    NotificationLog,  # noqa: F401 — ensure table registered with Base.metadata
)
from app.notifications.router import api_router as notification_api_router
from app.notifications.router import router as notification_router
from app.partner.allocation_router import router as allocation_router
from app.partner.router import router as partner_router
from app.partner.wallet_balance_router import router as wallet_balance_router
from app.portfolio.router import router as portfolio_router
from app.proposals.router import router as proposals_router
from app.protocols.lido.router import router as lido_router
from app.protocols.pendle.router import router as pendle_router
from app.protocols.risk.router import router as protocol_health_router
from app.referral.api_router import router as referral_api_router
from app.referral.router import router as referral_router
from app.reports.router import router as reports_router
from app.rss.router import router as rss_router
from app.tos.models import (
    ToSConsent,  # noqa: F401 — ensure table registered with Base.metadata
    ToSUserAction,  # noqa: F401 — ensure table registered with Base.metadata
)
from app.tos.router import router as tos_router
from app.transactions.router import admin_router as admin_transactions_router
from app.transactions.router import router as transactions_router
from app.users.models import (
    UserSettings,  # noqa: F401 — ensure table registered with Base.metadata
)
from app.users.router import router as users_router
from app.users.settings_router import router as user_settings_router
from app.users.withdrawals_router import router as user_withdrawals_router
from app.webhook.router import router as webhook_router

logger = logging.getLogger(__name__)
# Ensure app.* loggers output at INFO level regardless of root logger config
logging.getLogger("app").setLevel(logging.INFO)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True
)


def _is_inactive_color_skip() -> bool:
    """Blue/Green color ガードによる scheduler skip 判定。

    BACKEND_COLOR と ACTIVE_BACKEND_COLOR の両方が設定されており、
    かつ値が異なる場合 → True（inactive color: 正常 skip）。
    どちらか一方でも未設定の場合 → False（後方互換で有効）。
    """
    backend_color = os.getenv("BACKEND_COLOR", "").strip().lower()
    active_backend_color = os.getenv("ACTIVE_BACKEND_COLOR", "").strip().lower()
    return bool(backend_color and active_backend_color and backend_color != active_backend_color)


def _is_scheduler_enabled() -> bool:
    """AIスケジューラーの有効/無効判定。デフォルト有効。

    判定ロジック:
    - DISABLE_AI_JUDGMENT_SCHEDULER=1 → 無効（新方式）
    - ENABLE_AI_JUDGMENT_SCHEDULER=0  → 無効（旧方式後方互換）
    - Blue/Green color ガード (Stream 4 P0 対策):
        BACKEND_COLOR と ACTIVE_BACKEND_COLOR の両方が設定されており、
        かつ値が異なる場合 → 無効（inactive color: scheduler skip）
        どちらか一方でも未設定の場合 → 後方互換で有効（従来動作を維持）
    - それ以外 → 有効
    """
    if os.getenv("DISABLE_AI_JUDGMENT_SCHEDULER", "0") == "1":
        return False
    if os.getenv("ENABLE_AI_JUDGMENT_SCHEDULER") == "0":
        return False
    if _is_inactive_color_skip():
        return False
    return True


def _is_background_monitoring_enabled() -> bool:
    """バックグラウンド監視の有効/無効判定。デフォルト有効。

    判定ロジック:
    - DISABLE_BACKGROUND_MONITORING=1 → 無効（新方式）
    - ENABLE_BACKGROUND_MONITORING=0  → 無効（旧方式後方互換）
    - それ以外 → 有効
    """
    if os.getenv("DISABLE_BACKGROUND_MONITORING", "0") == "1":
        return False
    if os.getenv("ENABLE_BACKGROUND_MONITORING") == "0":
        return False
    return True


def _make_scheduler_error_handler(name: str) -> Callable[[Exception], None]:
    """スケジューラー失敗時の同期 Slack 通知コールバックを生成する。

    on_error コールバックとして各スケジューラーに渡す。
    通知自体が失敗してもスケジューラーは継続する。
    """

    def handler(exc: Exception) -> None:
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return
        try:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            text = f"⚠️ [Scheduler] {name}実行失敗\n原因: {type(exc).__name__}: {exc}\n時刻: {ts}"
            data = json.dumps({"text": text}).encode()
            req = urllib.request.Request(  # noqa: S310
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)  # noqa: S310
        except Exception as notify_exc:
            logger.error("Scheduler Slack notification failed: %s", notify_exc)

    return handler


async def _notify_slack_warning(text: str) -> None:
    """Slack webhook に警告メッセージを送る（失敗しても起動は継続）。"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        import asyncio as _asyncio

        import httpx

        loop = _asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: httpx.post(webhook_url, json={"text": text}, timeout=5),
        )
    except Exception as exc:
        logger.error("Slack warning notification failed: %s", exc)


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
    # Store allowed origins so exception handlers can attach CORS headers to 500 responses.
    # FastAPI does not run CORSMiddleware for unhandled exceptions, so handlers must do it manually.
    app.state.cors_origins = cors_origins

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
    app.include_router(partner_router)  # Partner stats (Wave 2)
    app.include_router(
        allocation_router, prefix="/api/partner", tags=["partner-allocations"]
    )  # Fund allocations
    app.include_router(
        wallet_balance_router, prefix="/api/partner", tags=["partner"]
    )  # Partner wallet balance (USDC + ETH on Base mainnet)
    app.include_router(users_router)  # Users (Phase12)
    app.include_router(ai_router, prefix="/api")  # AI (Phase2)
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
    app.include_router(fees_v10_router, prefix="/api/v1")  # Fee Model v10 API (/api/v1/fees/*)
    app.include_router(fee_transfer_router, prefix="/api/v1")  # Fee Transfer & Allowance (Lane R)
    app.include_router(ai_decisions_router)  # AI Decisions API
    app.include_router(ai_feedback_router)  # AI Feedback API (Layer 4)
    app.include_router(ai_optimizer_router)  # AI Optimizer (Phase 2 / ENB)
    app.include_router(transactions_router)  # Transactions API
    app.include_router(admin_transactions_router)  # Admin Transactions API
    app.include_router(proposals_router)  # Proposals API
    app.include_router(portfolio_router)  # Portfolio History API
    app.include_router(user_settings_router)  # User Settings API
    # P4 withdraw EP は money を動かす経路のため default-off で配線ガードする。
    # ENABLE_WITHDRAWALS=1/true のときのみ route 登録。未登録時 POST /api/users/withdrawals=404
    # （shadow 的な「登録するが実行しない」ではなく route 自体を出さない）。
    # ★#391 money gate (staging Sepolia 6項目) を通すまで本番 .env で true にしないこと。
    if os.getenv("ENABLE_WITHDRAWALS", "false").lower() in ("1", "true", "yes"):
        app.include_router(user_withdrawals_router)  # P4: user withdrawals (non-custodial)
    app.include_router(alias_router)  # API aliases (/api/safety-score etc.)
    app.include_router(notification_router)  # Notifications (Phase PWA)
    app.include_router(notification_api_router)  # Notifications /api/* alias (Phase PWA)
    app.include_router(lido_router)  # Lido Finance (Phase 2)
    app.include_router(pendle_router)  # Pendle Finance (Phase 2)
    app.include_router(protocol_health_router)  # Protocol Health Monitor (Phase 2)
    app.include_router(referral_router)  # RAS Lane 2 (Referral / Partner Affiliate System)
    app.include_router(referral_api_router)  # Lane C1: /api/referral/* (全 active user)
    app.include_router(tos_router)  # ToS active consent (MVP-P0-14)
    app.include_router(health_detail_router)  # /health/detail (admin, 5/14 DoD #6)

    # Register global error handlers (production safety)
    register_error_handlers(app)

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, Any]:
        from app.ai.config import DEFAULT_CLAUDE_MODEL, DEFAULT_FALLBACK_MODEL
        from app.automation.ai_judgment_scheduler import get_scheduler_status
        from app.automation.scheduler_watchdog import compute_scheduler_health

        scheduler = get_scheduler_status()
        status = "ok" if scheduler["running"] else "degraded"

        interval_hours = int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS", "4"))
        health = compute_scheduler_health(scheduler.get("last_run"), interval_hours)
        warnings: list[str] = []
        if not health["healthy"]:
            warnings.append("scheduler_overdue")

        return {
            "status": status,
            "env": os.getenv("APP_ENV", "dev"),
            "scheduler": scheduler["running"],
            "scheduler_healthy": health["healthy"],
            "last_judgment": scheduler.get("last_run"),
            "next_judgment": scheduler.get("next_run"),
            "scheduler_last_error": scheduler.get("last_error"),
            "warnings": warnings,
            "claude_model": os.getenv("AI_CLAUDE_MODEL") or DEFAULT_CLAUDE_MODEL,
            "claude_fallback_model": os.getenv("AI_FALLBACK_MODEL") or DEFAULT_FALLBACK_MODEL,
        }

    # --- AI model config validation (fail-fast: must be first startup event) ---
    @app.on_event("startup")
    async def startup_validate_model_config() -> None:
        """Fail-fast: reject deprecated Claude model names before any task starts."""
        from app.ai.config import _validate_model_config  # noqa: PLC0415

        _validate_model_config()
        logger.info("AI model config validation passed")

    # --- Aave Oracle staleness threshold env validation (fail-fast) ---
    @app.on_event("startup")
    async def startup_validate_oracle_staleness_env() -> None:
        """Fail-fast: reject invalid AAVE_ORACLE_STALENESS_THRESHOLD_SECONDS at boot.

        Long-heartbeat feeds (Base Sepolia / Base mainnet USDC/USD ≈ 24h) must
        configure this env to avoid spurious HOLD; default 3600s is unsafe there.
        """
        from app.aave.oracle_checker import validate_staleness_threshold_env  # noqa: PLC0415

        threshold = validate_staleness_threshold_env()
        logger.info(
            "Aave oracle staleness threshold validated: %ds "
            "(env=AAVE_ORACLE_STALENESS_THRESHOLD_SECONDS)",
            threshold,
        )

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

    # --- Risk limiter startup notification (F-17a) ---
    @app.on_event("startup")
    async def startup_risk_limiter_notify() -> None:
        """Notify Slack when custom risk limits are active (F-17a)."""
        try:
            from app.aave.risk_limiter import (  # noqa: PLC0415
                get_effective_limits,
                notify_slack_if_custom,
            )

            limits = get_effective_limits()
            notify_slack_if_custom(limits)
        except Exception as exc:  # noqa: BLE001
            logger.warning("risk_limiter startup notification failed: %s", exc)

        # Validate JWT secret key strength (rejects weak keys in staging/production)
        try:
            AuthService.validate_secret_key()
        except Exception as exc:
            logger.error("JWT secret key validation failed: %s", exc)

    @app.on_event("startup")
    async def startup_judgment_logger() -> None:
        """Initialize AI judgment logger (JSONL + cognitive state)."""
        try:
            from app.ai.judgment_log import get_judgment_logger

            await get_judgment_logger().initialize()
            logger.info("JudgmentLogger initialized")
        except BaseException as exc:
            logger.error("Failed to initialize JudgmentLogger: %s", exc)

    # --- Background monitoring tasks (Phase5) ---
    @app.on_event("startup")
    async def startup_event() -> None:
        """
        Start background monitoring on application startup.

        Default: enabled. Set DISABLE_BACKGROUND_MONITORING=1 to disable.
        Legacy: ENABLE_BACKGROUND_MONITORING=0 also disables.
        """
        if not _is_background_monitoring_enabled():
            logger.info("Background monitoring disabled")
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

        except BaseException as exc:
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

        try:
            geo_interval = int(os.getenv("GEO_RISK_INTERVAL_MINUTES", "30"))
            news_interval = int(os.getenv("NEWS_INTERVAL_MINUTES", "15"))
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
            from app.automation.scheduled_tasks import learning_loop  # noqa: PLC0415

            learning_interval = int(os.getenv("LEARNING_INTERVAL_HOURS", "6")) * 3600
            asyncio.create_task(learning_loop(interval_seconds=learning_interval))
            logger.info("AI learning background task started (interval=%ds)", learning_interval)
            if os.getenv("ENABLE_OUTCOME_LABELING", "0") == "1":
                from app.automation.scheduled_tasks import outcome_labeling_loop  # noqa: PLC0415

                labeling_interval = int(os.getenv("OUTCOME_LABELING_INTERVAL_HOURS", "6")) * 3600
                asyncio.create_task(outcome_labeling_loop(interval_seconds=labeling_interval))
                logger.info("outcome_labeling_loop started (interval=%ds)", labeling_interval)
            mmt_enabled = os.getenv("MMT_API_ENABLED", "false").lower() in ("true", "1", "yes")
            if mmt_enabled:
                mmt_interval = int(os.getenv("MMT_UPDATE_INTERVAL", "1800")) // 60
                asyncio.create_task(start_mmt_background_task(interval_minutes=mmt_interval))
                logger.info("MMT data feed started (interval: %ds)", mmt_interval * 60)
            from app.automation.scheduled_tasks import process_news_loop  # noqa: PLC0415

            pn_interval = int(os.getenv("PROCESS_NEWS_INTERVAL_SECONDS", "300"))
            asyncio.create_task(process_news_loop(interval_seconds=pn_interval))
            logger.info("process_news_loop started (interval=%ds)", pn_interval)
        except BaseException as exc:
            logger.error("Failed to start data feed background tasks: %s", exc)

    # --- Scheduled tasks (Phase6) ---
    @app.on_event("startup")
    async def startup_scheduled_tasks() -> None:
        """
        Start scheduled tasks on application startup.

        Controlled by environment variables:
            ENABLE_DAILY_REPORTS=1: enable daily reports
            ENABLE_WEEKLY_REPORTS=1: enable weekly reports
            DISABLE_BACKGROUND_MONITORING=1: disable all 7 operational loops

        7 operational loops (always-on unless DISABLE_BACKGROUND_MONITORING=1):
            proposal_timeout / rebalance_check / price_monitor / health_check /
            latency_monitor / rss_fetch / dca
        """
        from app.automation.scheduled_tasks import get_scheduled_task_manager  # noqa: PLC0415
        from app.notifications.config import get_notification_settings  # noqa: PLC0415

        enable_daily = os.getenv("ENABLE_DAILY_REPORTS", "0") == "1"
        enable_weekly = os.getenv("ENABLE_WEEKLY_REPORTS", "0") == "1"

        settings = get_notification_settings()
        scheduled_manager = get_scheduled_task_manager()

        # --- Optional report tasks ---
        if not enable_daily and not enable_weekly:
            logger.info(
                "Scheduled reports disabled "
                "(set ENABLE_DAILY_REPORTS=1 or ENABLE_WEEKLY_REPORTS=1 to enable)"
            )
        else:
            try:
                if enable_daily:
                    await scheduled_manager.start_daily_reports(
                        channel=settings.default_channel,
                        on_error=_make_scheduler_error_handler("日次レポートスケジューラー"),
                    )
                    logger.info("Daily reports scheduled successfully")

                if enable_weekly:
                    await scheduled_manager.start_weekly_reports(
                        channel=settings.default_channel,
                        on_error=_make_scheduler_error_handler("週次レポートスケジューラー"),
                    )
                    logger.info("Weekly reports scheduled successfully")
            except BaseException as exc:
                logger.error("Failed to start report tasks: %s", exc)

        # --- 7 operational loops (always-on, fail-safe each) ---
        if not _is_background_monitoring_enabled():
            logger.info("Operational loops disabled (DISABLE_BACKGROUND_MONITORING=1)")
            return

        _loops: list[tuple[str, object]] = [
            (
                "proposal_timeout",
                scheduled_manager.start_proposal_timeout(
                    on_error=_make_scheduler_error_handler("proposal_timeout_loop"),
                ),
            ),
            (
                "rebalance_check",
                scheduled_manager.start_rebalance_check(
                    on_error=_make_scheduler_error_handler("rebalance_check_loop"),
                ),
            ),
            (
                "price_monitor",
                scheduled_manager.start_price_monitor(
                    on_error=_make_scheduler_error_handler("price_monitor_loop"),
                ),
            ),
            (
                "health_check",
                scheduled_manager.start_health_check(
                    on_error=_make_scheduler_error_handler("health_check_loop"),
                ),
            ),
            (
                "latency_monitor",
                scheduled_manager.start_latency_monitor(
                    on_error=_make_scheduler_error_handler("latency_monitor_loop"),
                ),
            ),
            (
                "rss_fetch",
                scheduled_manager.start_rss_fetch(
                    on_error=_make_scheduler_error_handler("rss_fetch_loop"),
                ),
            ),
            (
                "dca",
                scheduled_manager.start_dca(
                    on_error=_make_scheduler_error_handler("dca_loop"),
                ),
            ),
            (
                "compound_risk_monitor",
                scheduled_manager.start_compound_risk_monitor(
                    on_error=_make_scheduler_error_handler("compound_risk_monitor_loop"),
                ),
            ),
        ]
        for name, coro in _loops:
            try:
                await coro  # type: ignore[misc]
                logger.info("Operational loop started: %s", name)
            except BaseException as exc:
                logger.error("Failed to start loop %s: %s", name, exc)

        # --- 月次手数料バッチ (opt-in: ENABLE_MONTHLY_FEE_BATCH=1) ---
        if os.getenv("ENABLE_MONTHLY_FEE_BATCH", "0") == "1":
            try:
                from decimal import Decimal as _Decimal  # noqa: PLC0415

                usd_jpy_rate = _Decimal(os.getenv("USD_TO_JPY_RATE", "150"))
                await scheduled_manager.start_monthly_fee_batch(
                    usd_jpy_rate=usd_jpy_rate,
                    on_error=_make_scheduler_error_handler("monthly_fee_batch_loop"),
                )
                logger.info("Monthly fee batch scheduled (rate=%s)", usd_jpy_rate)
            except BaseException as exc:
                logger.error("Failed to start monthly fee batch: %s", exc)

        # --- 月次 LINE レポート (opt-in: ENABLE_MONTHLY_LINE_REPORT=1) ---
        if os.getenv("ENABLE_MONTHLY_LINE_REPORT", "0") == "1":
            try:
                await scheduled_manager.start_monthly_line_report(
                    on_error=_make_scheduler_error_handler("monthly_line_report_loop"),
                )
                logger.info("Monthly LINE report scheduled")
            except BaseException as exc:
                logger.error("Failed to start monthly LINE report: %s", exc)

    @app.on_event("startup")
    async def startup_health_probes() -> None:
        """Start background probes for /health/detail (OpenAI / Perplexity / Aave safety)."""
        import asyncio  # noqa: PLC0415

        try:
            from app.health.probes import (  # noqa: PLC0415
                aave_safety_probe_loop,
                openai_probe_loop,
                perplexity_probe_loop,
            )

            asyncio.create_task(openai_probe_loop())
            asyncio.create_task(perplexity_probe_loop())
            asyncio.create_task(aave_safety_probe_loop())
            logger.info("Health detail probe loops started (openai/perplexity/aave-safety)")
        except BaseException as exc:
            logger.error("Failed to start health detail probe loops: %s", exc)

    @app.on_event("startup")
    async def startup_ai_judgment_scheduler() -> None:
        """4時間ごとのAI判定スケジューラーを開始する。デフォルト有効。"""
        import asyncio

        # color ガード専用 early return: inactive color による正常 skip は
        # Slack 通知不要（Blue/Green 切替時の非 active 側コンテナの期待動作）。
        if _is_inactive_color_skip():
            logger.info(
                "inactive color: scheduler skip (BACKEND_COLOR=%s, ACTIVE_BACKEND_COLOR=%s)",
                os.getenv("BACKEND_COLOR", "").strip().lower(),
                os.getenv("ACTIVE_BACKEND_COLOR", "").strip().lower(),
            )
            return

        if not _is_scheduler_enabled():
            logger.error(
                "AI judgment scheduler is DISABLED. "
                "Set DISABLE_AI_JUDGMENT_SCHEDULER=1 intentionally, or check env vars."
            )
            await _notify_slack_warning(
                "⚠️ [Ultra AutoTrade] AIスケジューラーが無効状態で起動しました。\n"
                "AI判定が実行されません。DISABLE_AI_JUDGMENT_SCHEDULER=1 が設定されているか確認してください。"
            )
            return
        try:
            from app.automation.ai_judgment_scheduler import ai_judgment_loop
            from app.automation.scheduler_watchdog import scheduler_watchdog_loop

            interval = int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS", "4"))
            asyncio.create_task(
                ai_judgment_loop(
                    interval_hours=interval,
                    on_error=_make_scheduler_error_handler("AI判定スケジューラー"),
                )
            )
            logger.info("AI judgment scheduler started (interval=%dh)", interval)
            asyncio.create_task(scheduler_watchdog_loop())
            logger.info("Scheduler watchdog started (check interval=30min)")
        except BaseException as exc:
            logger.error("Failed to start AI judgment scheduler: %s", exc)

    @app.on_event("shutdown")
    async def shutdown_scheduled_tasks() -> None:
        """
        Stop scheduled tasks on application shutdown.
        """
        try:
            from app.automation.scheduled_tasks import get_scheduled_task_manager

            scheduled_manager = get_scheduled_task_manager()

            await scheduled_manager.stop_all()
            logger.info("Scheduled tasks stopped")

        except Exception as exc:
            logger.error("Error during scheduled tasks shutdown: %s", exc)

    return app


limiter = Limiter(key_func=get_remote_address)
app = create_app()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
