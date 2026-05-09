# Backend Core File Change Log

凍結ファイル（`FROZEN_PATTERNS`）の変更申請記録。
変更前に PR レビューを通過させ、ここにエントリを追加すること。

---

## backend/app/main.py

### 変更 #3: /health エンドポイントに AI モデル設定を追加 (PR #95 / 2026-04-20)
- **コミット範囲**: `408d3ad` (feature/remove-claude-model-hardcodes)
- **変更内容**:
  - `/health` レスポンスに `claude_model` / `claude_fallback_model` フィールド追加
  - `app.ai.config` から `DEFAULT_CLAUDE_MODEL` / `DEFAULT_FALLBACK_MODEL` をインポート
  - `AI_CLAUDE_MODEL` / `AI_FALLBACK_MODEL` 環境変数の実効値を確認できるようにする
- **理由**: AIモデル名のハードコード除去 (PR #95) の一環。デプロイ後に稼働中のモデル設定を `/health` で検証できるようにする。
- **影響範囲**: `/health` エンドポイントのレスポンスフィールド追加のみ。既存フィールド・ロジックへの影響なし。
- **承認**: feature/remove-claude-model-hardcodes → dev の通常フロー経由（PR #95）

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


### 変更 #4: F-8a v10 fees router 登録 (PR #127 / 2026-04-25)
- **コミット範囲**: `d55a53c` (feature/f8a-fees-api-readonly)
- **変更内容**:
  - `from app.api.v1 import fees as fees_v10_router` を追加
  - `app.include_router(fees_v10_router.router, prefix="/api/v1")` を `billing_router` の直後に追加
- **理由**: F-8a (Asana 1214120371503131) — v10 fees API endpoints (/api/v1/fees/*) を FastAPI app に登録。既存 /api/billing/* と /api/fees/calculate|schedule は無変更で併存維持 (F-8b GID 1214288467406433 で廃止予定)。
- **影響範囲**: 新規 router 追加のみ。既存 endpoint への影響なし。`TestCoexistenceWithLegacyEndpoints` (2件) で既存 endpoint の404でないことを保証。
- **承認**: feature/f8a-fees-api-readonly → main の通常フロー経由（PR #127）


### 変更 #5: process_news_loop 起動 (PR #157 / 2026-04-27)
- **コミット範囲**: `5ea9120` – `ce53ea9` (fix/production-401-unauthorized)
- **変更内容**:
  - `from app.automation.scheduled_tasks import process_news_loop` を `startup_data_feeds` 内で動的 import
  - `asyncio.create_task(process_news_loop(interval_seconds=pn_interval))` で起動
  - `PROCESS_NEWS_INTERVAL_SECONDS` 環境変数 (デフォルト 300秒 = 5分) で間隔を制御
- **理由**: production backend で 24h に 189件発生していた `/automation/process-news` 401 Unauthorized エラーを解消するため。ホスト cron (root crontab) の旧呼び出し方式を廃止し、アプリ内スケジューラーから X-Internal-Token ヘッダー付きで `/automation/process-news?dry_run=false` を叩く方式に統一。
- **影響範囲**: startup シーケンスのみ。`PROCESS_NEWS_INTERVAL_SECONDS` 未設定時は 300秒間隔で動作。既存の `/automation/process-news` エンドポイントは無変更で、内部から HTTP POST で叩く構造。
- **承認**: fix/production-401-unauthorized → main の通常フロー経由（PR #157）

### 変更 #6: RAS Phase 1 referral_router 登録 (PR #194 / 2026-05-08)
- **コミット範囲**: `72148ce` (feature/ras-l2-backend-api)
- **変更内容**:
  - `from app.referral.router import router as referral_router` を追加
  - `app.include_router(referral_router)` を register_routers() に 1 行追加
  - 計 2 行追加のみ
- **理由**: F-17 + RAS Phase 1 (Asana 1214629980953220) — 紹介機能 (Referral Attribution System Phase 1) の API 群 (POST /referral/code / GET /referral/list / GET /referral/users/{id}/transactions) を FastAPI app に登録。partner ロールが自身の紹介コードを発行・紹介済みユーザー一覧と取引履歴 (deposit/withdraw/borrow/repay のみ、wallet/tx_hash 非開示) を閲覧する Phase 1 機能。
- **影響範囲**: 新規 router 追加のみ。既存 endpoint への影響なし。tests/test_referral_router.py で既存 endpoint の404でないことを保証。
- **承認**: feature/ras-l2-backend-api → main の通常フロー経由（PR #194）

### 変更 #7: RAS Phase 1 cleanup — invitations_router 無効化 + referral prefix 修正 (PR #201 / 2026-05-09)
- **コミット範囲**: `e3210c8` (hotfix/ras-partner-referral-cleanup)
- **変更内容**:
  - `from app.invitations.router import router as invitations_router` をコメントアウト
  - `app.include_router(invitations_router)` をコメントアウト（Phase 2 物理削除予定）
  - `referral_router` の APIRouter prefix を `/referral` → `/partner/referral` に修正
    (PR #194 変更 #6 で mount 時の prefix 設定漏れを補完)
- **理由**: hkobayashi 判断 (A) 置換 / 2026-05-09 UAT pre-check 中に発覚した以下の問題を一括修正:
  1. `POST /referral/code` (backend) と `POST /partner/referral/code` (仕様) の prefix 不一致
  2. 旧 `/api/invitations` と新 `/partner/referral` の二重化 → invitations を Phase 2 まで disabled
  3. partner ナビゲーションに紹介プログラムリンクが未追加 (AppShell.tsx で追加)
  RAS Phase 1 教訓: PR description に API path 一覧を必須記載 (CLAUDE.md ルール 11 追加予定)
- **影響範囲**:
  - `/api/invitations/*` エンドポイントが全て 404 になる (既存 Wave 2 招待フローは無効化)
  - `POST /referral/code` → `POST /partner/referral/code` (既存の frontend も同時更新)
  - `register/page.tsx` が `/api/invitations/{code}` を呼ぶ旧登録フローは Phase 2 で移行予定
  - `frontend/app/register/page.tsx` の挙動変化: 旧招待コード登録 → 404 (UAT 影響なし / 旧フローは非推奨)
- **承認**: hkobayashi 判断 (A) 置換 / hotfix/ras-partner-referral-cleanup → main (PR #201)
- **ロールバック**: `git revert e3210c8` → invitations_router を再有効化 + prefix を `/referral` に戻す

## backend/app/database.py

変更なし（現時点）

## backend/conftest.py

変更なし（現時点）

## backend/requirements.txt

### 変更 #2: PyJWT[crypto] extra 追加（Privy ID Token 検証対応）(PR #155 / 2026-04-27)
- **コミット範囲**: `c88dfd2` – `41f77d7` (feature/privy-did-storage)
- **変更内容**: `PyJWT>=2.9.0` → `PyJWT[crypto]>=2.9.0`
- **理由**: Privy ID Token 検証 (PR #155) に RS256/ES256 アルゴリズムサポートが必要。
  `PyJWT` 単体では非対称鍵アルゴリズムを扱えず、`cryptography` ライブラリが必要。
  `[crypto]` extra を追加することで `cryptography` が自動的にインストールされる。
- **影響範囲**: `cryptography` ライブラリの追加のみ。既存認証ロジックへの影響なし。
  `pyjwt` は既存コードでも使用しており、API 互換変更（追加のみ）。
- **承認**: feature/privy-did-storage → main の通常フロー経由（PR #155）

### 変更 #1: wheel バージョン固定（CVE-2026-24049）
- **コミット**: `fd2b6a6` (dev ブランチ)
- **変更内容**: `wheel>=0.46.2` を追加
- **理由**: CVE-2026-24049 — 悪意のある wheel ファイルを unpack した際の任意コード実行。Trivy HIGH 脆弱性。修正版 0.46.2 以降に固定。
- **影響範囲**: ビルドツールのみ。アプリケーションロジックへの影響なし。
- **承認**: dev → staging → main の通常フロー経由

## backend/app/shared/

変更なし（現時点）
