# backend/app/automation/state.py

"""
MonitoringService のシンプルな状態管理モジュール。

- アプリ全体で共有する MonitoringService インスタンスを提供
- テスト時にリセットできるようにする

FastAPI の DI で使うことも、素朴なグローバル状態として使うことも可能。
"""

from __future__ import annotations

from typing import Optional

from .monitoring_service import MonitoringService

_monitoring_service: Optional[MonitoringService] = None


def get_monitoring_service() -> MonitoringService:
    """
    共有の MonitoringService インスタンスを返す。

    初回呼び出し時にのみ生成し、それ以降は同じインスタンスを返す。
    """
    global _monitoring_service
    if _monitoring_service is None:
        _monitoring_service = MonitoringService()
    return _monitoring_service


def reset_state() -> None:
    """
    テスト用に MonitoringService のシングルトン状態をリセットする。
    """
    global _monitoring_service
    _monitoring_service = None
