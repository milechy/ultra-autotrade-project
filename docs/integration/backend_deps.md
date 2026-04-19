# Backend Core File Change Log

凍結ファイル（`FROZEN_PATTERNS`）の変更申請記録。
変更前に PR レビューを通過させ、ここにエントリを追加すること。

---

## backend/app/main.py

### 変更 #2: F-17a カスタムリミッター startup 通知 (PR #92 / 2026-04-19)
- **コミット範囲**: `52043f6` (dev ブランチ, feature/risk-limiter-env-toggle マージ)
- **変更内容**:
  - `startup_risk_limiter_notify()` startup イベント追加
  - `CUSTOM_LIMITER_ENABLED=true` の場合のみ Slack #ultra-auto-project に通知
  - 既存の startup イベント群・エンドポイント登録への影響なし
- **理由**: F-17a (Asana 1214120353855021) — カスタムリミッター有効時の startup 通知。設定ミスによる意図しない緩和状態の見落とし防止。
- **影響範囲**: startup シーケンスのみ。`CUSTOM_LIMITER_ENABLED` 未設定時は何もしない。
- **承認**: dev → main の通常フロー経由（PR #91）

### 変更 #1: スケジューラー デフォルト有効化 + Watchdog 統合
- **コミット範囲**: `4fe8725` – `5b98e78` (dev ブランチ)
- **変更内容**:
  - `_is_scheduler_enabled()` / `_is_background_monitoring_enabled()` 追加
    - デフォルト有効方式（`DISABLE_*=1` で無効化）に変更
    - 旧 `ENABLE_*` 方式を後方互換として維持
  - `_make_scheduler_error_handler()` 追加: スケジューラー失敗時の Slack 通知
  - `_notify_slack_warning()` 追加: 非同期 Slack 警告ユーティリティ
  - `/health` エンドポイントに `scheduler_healthy` / `warnings` フィールド追加
  - `SchedulerWatchdog` を startup イベントで起動（30分間隔監視）
  - AI 判定エンドポイント `/ai/judgment` を登録
- **理由**: CLAUDE.md 2026-04-02 追加事項 — スケジューラーが設定漏れで無音停止するバグを修正。`ENABLE_*=1` 方式はデフォルト無効のため設定漏れが発生しやすく、`DISABLE_*=1` 方式（デフォルト有効）に変更。
- **影響範囲**: 起動シーケンスのみ。既存エンドポイントへの影響なし。
- **承認**: dev → staging → main の通常フロー経由

---

## backend/app/database.py

変更なし（現時点）

## backend/conftest.py

変更なし（現時点）

## backend/requirements.txt

### 変更 #1: wheel バージョン固定（CVE-2026-24049）
- **コミット**: `fd2b6a6` (dev ブランチ)
- **変更内容**: `wheel>=0.46.2` を追加
- **理由**: CVE-2026-24049 — 悪意のある wheel ファイルを unpack した際の任意コード実行。Trivy HIGH 脆弱性。修正版 0.46.2 以降に固定。
- **影響範囲**: ビルドツールのみ。アプリケーションロジックへの影響なし。
- **承認**: dev → staging → main の通常フロー経由

## backend/app/shared/

変更なし（現時点）
