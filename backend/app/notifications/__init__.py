# backend/app/notifications/__init__.py

"""
通知レイヤ用モジュール群。

Phase5 のスコープでは「通知のインターフェースと最小実装（ログ出力のみ）」を提供し、
実際の LINE / Slack / Email 連携は後続フェーズで差し込めるようにしておく。

構成イメージ:
- schemas: 通知メッセージの共通スキーマ
- service: 通知送信インターフェースと実装
- factory: アプリ全体で共有する NotificationService の生成
"""
