# backend/app/main.py

"""
バックエンドアプリケーションのエントリーポイント。

Phase1 の主な責務:
- /notion/ingest エンドポイントを公開する

Phase2 で追加された責務:
- /ai/analyze エンドポイントを公開する
"""

# backend/app/main.py

from fastapi import FastAPI

from app.ai.router import router as ai_router
from app.bots.router import router as octobot_router
from app.notion.router import router as notion_router  # ★ 復活
from app.aave.router import router as aave_router      # ★ Phase4 で追加


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ultra AutoTrade API",
        version="0.1.0",
    )

    # --- ルーター登録 ---
    app.include_router(notion_router)   # Notion (Phase1)
    app.include_router(ai_router)       # AI (Phase2)
    app.include_router(octobot_router)  # OctoBot (Phase3)
    app.include_router(aave_router)     # Aave (Phase4)

    @app.get("/health", tags=["health"])
    def health_check() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
