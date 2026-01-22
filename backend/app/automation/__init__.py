# backend/app/automation/__init__.py

"""
Phase5: 自動化・監視・レポート用モジュール群。

- schemas: 監視イベント / ステータスの Pydantic モデル
- monitoring_service: 監視・緊急停止ロジック本体
- state: MonitoringService の共有インスタンス管理
"""
