# backend/app/main.py

"""
バックエンドアプリケーションのエントリーポイント。

Phase1 の主な責務:
- /notion/ingest エンドポイントを公開する

Phase2 で追加された責務:
- /ai/analyze エンドポイントを公開する
"""

from fastapi import FastAPI

# backend/app/main.py

from fastapi import FastAPI

from app.ai.router import router as ai_router
from app.notion.router import router as notion_router
from app.bots.router import router as octobot_router

def create_app() -> FastAPI:
    """
    FastAPI アプリケーションファクトリ。

    - Notion 連携エンドポイント (/notion/ingest)
    - AI 解析エンドポイント (/ai/analyze)
    - ヘルスチェックエンドポイント (/health)
    """
    app = FastAPI(title="Ultra AutoTrade Backend")

    # ルーター登録
    app.include_router(notion_router)
    app.include_router(ai_router)
    app.include_router(octobot_router)

    @app.get("/health", tags=["health"])
    def health_check() -> dict:
        """
        簡易ヘルスチェックエンドポイント。
        モニタリングや動作確認用。
        """
        return {"status": "ok"}

    return app


# uvicorn 実行時のエントリーポイント
app = create_app()

