# backend/app/automation/shadow_mode_service.py

"""
Shadow Mode サービス: AI判定結果をログ記録するのみで、実際のトレードは実行しない。
本番運用前の安全テスト・精度検証に使用する。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.ai.schemas import CrossValidationResult, ShadowModeLog
from app.utils.config import get_env

logger = logging.getLogger(__name__)

# シングルトンインスタンスを保持する変数
_shadow_mode_service: ShadowModeService | None = None


class ShadowModeService:
    """
    Shadow Mode の記録・制御を担うサービスクラス。

    - record(): AI判定結果をログに出力し、ShadowModeLog として返す
    - is_enabled(): AI_SHADOW_MODE 環境変数を確認して有効/無効を返す
    """

    def record(self, result: CrossValidationResult, item_id: str) -> ShadowModeLog:
        """
        AI判定結果をログに記録して ShadowModeLog を返す。

        :param result: judge_with_rag から返された CrossValidationResult
        :param item_id: 判定対象のアイテムID
        :return: ログ記録済みの ShadowModeLog インスタンス
        """
        # プロバイダー名を primary の provider から取得する
        provider = result.primary.provider.value if result.primary.provider else None

        log = ShadowModeLog(
            item_id=item_id,
            action=result.final_action,
            confidence=result.final_confidence,
            reason=result.final_reason,
            timestamp=datetime.now(timezone.utc),
            prompt_version=result.prompt_version,
            shadow_mode=True,
            provider=provider,
        )

        logger.info(
            "SHADOW_MODE | item_id=%s action=%s confidence=%s reason=%s"
            " prompt_version=%s provider=%s",
            log.item_id,
            log.action.value,
            log.confidence,
            log.reason,
            log.prompt_version,
            log.provider,
        )

        return log

    def is_enabled(self) -> bool:
        """
        AI_SHADOW_MODE 環境変数を確認して Shadow Mode が有効かどうかを返す。

        :return: True=Shadow Mode有効（判定のみ・実行しない）、False=通常モード
        """
        raw = get_env("AI_SHADOW_MODE", required=False)
        if raw is None or raw == "":
            return False
        return raw.lower() in ("true", "1", "yes")


def get_shadow_mode_service() -> ShadowModeService:
    """
    ShadowModeService のシングルトンインスタンスを返す。

    :return: ShadowModeService インスタンス
    """
    global _shadow_mode_service
    if _shadow_mode_service is None:
        _shadow_mode_service = ShadowModeService()
    return _shadow_mode_service
