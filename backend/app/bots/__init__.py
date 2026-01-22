"""
OctoBot 連携モジュール。

- config: OctoBot API の設定値（エンドポイント, APIキー, タイムアウト等）
- schemas: /octobot/signal 用の Pydantic モデル
- client: OctoBot 外部シグナル API への HTTP クライアント
- service: AIAnalysisResult からシグナルを生成・送信するビジネスロジック
- router: /octobot/signal エンドポイント
"""

from .config import OctoBotSettings, get_octobot_settings  # noqa: F401
from .service import OctoBotService  # noqa: F401
from .schemas import (  # noqa: F401
    OctoBotSignal,
    OctoBotSignalRequest,
    OctoBotSignalResponse,
)
