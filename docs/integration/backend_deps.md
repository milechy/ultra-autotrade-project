# Backend Core File Change Log

凍結ファイル（`FROZEN_PATTERNS`）の変更申請記録。
変更前に PR レビューを通過させ、ここにエントリを追加すること。

---

## PR #775 (AI判定 WebSocket): ai_decisions_ws_router 配線 (2026-06-17)

### 変更: ai_decisions_ws_router を main.py に include_router
- **対象凍結ファイル**: `backend/app/main.py`
- **変更内容**:
  - `from app.ai.decisions_router import ... ws_router as ai_decisions_ws_router` を import 追加
  - `app.include_router(ai_decisions_ws_router)` を追加（prefix は router 側で `/api/ai/ws` 定義済み）
- **理由**: AI 判定 WebSocket リアルタイム配信エンドポイント (`GET /api/ai/ws/decisions`) を有効化するため。新規 `ws_router` を decisions_router.py に定義し、main.py への配線が必要。
- **影響範囲**: WebSocket ルーター登録のみ。既存 REST エンドポイント・スケジューラー・起動シーケンスへの影響なし。JWT クエリ認証で保護済み。
- **承認**: feat/ws-ai-decision-realtime-v2 → main の通常フロー経由（PR #775）

---

## PR #763 (yield optimizer 配線漏れ修正): yield_optimizer_router 配線 (2026-06-16)

### 変更: yield_optimizer_router を main.py に include_router
- **対象凍結ファイル**: `backend/app/main.py`
- **変更内容**:
  - `from app.yield_optimizer.router import router as yield_optimizer_router` を import 追加
  - `app.include_router(yield_optimizer_router)` を追加（自前 prefix `/api/yield-optimizer`、portfolio_router と同型）
- **理由**: #750（Privy Earn / Morpho yield optimizer）が router を追加したが main.py への include_router を忘れた孤立 router。`launch_gate` L5（wiring lint）が検知して本番デプロイを BLOCK していたため配線を補完する。
- **影響範囲**: ルーター登録のみ。起動シーケンス・既存エンドポイントへの影響なし。`/api/yield-optimizer/*` が有効化される。
- **承認**: fix/yield-optimizer-router-wiring → main の通常フロー経由（PR #763）

---

## PR #581 (admin users API): admin_users_router 配線 (2026-06-08)

### 変更: admin_users_router を main.py に include_router
- **対象凍結ファイル**: `backend/app/main.py`
- **変更内容**:
  - `from app.api.admin_users import router as admin_users_router` を import 追加
  - `app.include_router(admin_users_router)` を追加（`/admin/users` モック → 実 API 配線、`GET /api/admin/users`）
- **理由**: フロントエンド `/admin/users` のモックを実 API に置き換えるため、admin 向けユーザー一覧/操作エンドポイントを配線する。
- **影響範囲**: ルーター登録のみ。起動シーケンス・既存エンドポイントへの影響なし。エンドポイントは `require_admin` で RBAC ガード済み。
- **承認**: feature/admin-users-api-wiring-20260608 → main の通常フロー経由（PR #581）

---

## PR #563 (前提1): ENABLE_WITHDRAWALS flag で withdraw EP を default-off ガード (2026-06-06)

### 変更: include_router(user_withdrawals_router) を ENABLE_WITHDRAWALS フラグで条件化
- **対象凍結ファイル**: `backend/app/main.py`
- **変更内容**:
  - PR #560 で無条件配線された `app.include_router(user_withdrawals_router)` を
    `if os.getenv("ENABLE_WITHDRAWALS", "false").lower() in ("1", "true", "yes"):` で囲む（既定 false）。
  - import 行（副作用なし）は残し、include のみ条件化。通知 router(279/280) は無条件のまま不触。
- **理由**: money を動かす `/api/users/withdrawals` が無条件配線だったため、backend deploy で通知/名前保存/TAX 等を出す際に withdraw 経路を構造的に開かないよう default-off で配線ガードする（Asana 1215466937993772 前提1）。「閉じる」= route 未登録 = 404（shadow 的な登録するが実行しない、ではない）。
- **影響範囲**: ルーター登録の条件化のみ。withdraw ロジック・起動シーケンス・他エンドポイントへの影響なし。★#391 money gate（staging Sepolia 6 項目）を通すまで本番 `.env` で `ENABLE_WITHDRAWALS=true` にしないこと。
- **承認**: feat/enable-withdrawals-flag-20260606 → main の通常フロー経由（PR #563）

---

## PR #560 (P4): /api/users/withdrawals user_withdrawals_router 配線 (2026-06-06)

### 変更: user_withdrawals_router を main.py に include_router
- **対象凍結ファイル**: `backend/app/main.py`
- **変更内容**:
  - `from app.users.withdrawals_router import router as user_withdrawals_router` を import 追加
  - `app.include_router(user_withdrawals_router)` を追加（P4: 非カストディアル出金 `/api/users/withdrawals`）
- **理由**: P4 非カストディアル出金 money gate（DoD GID 1215444094888771 / §14a）の出金記録エンドポイント `/api/users/withdrawals` を配線するため。partner wallet（Privy 鍵）が署名し、サーバー鍵を経由せず出金した事実を backend に記録する。
- **影響範囲**: ルーター登録のみ。起動シーケンス・既存エンドポイントへの影響なし。
- **承認**: feat/pr391-withdraw-money-gate → main の通常フロー経由（PR #560）

---

## PR #556 (Lane C1): /api/referral/* referral_api_router 配線 (2026-06-05)

### 変更: referral_api_router を main.py に include_router
- **対象凍結ファイル**: `backend/app/main.py`
- **変更内容**:
  - `from app.referral.api_router import router as referral_api_router` を import 追加
  - `app.include_router(referral_api_router)` を追加（Lane C1: /api/referral/* 全 active user 向け）
- **理由**: Lane C1 の referral code 発行エンドポイント (`/api/referral/code`) を配線するため。既存の `referral_router`（RAS Lane 2）とは別エンドポイント群。
- **影響範囲**: ルーター登録のみ。起動シーケンス・既存エンドポイントへの影響なし。
- **承認**: feat/referral-code-ep → main の通常フロー経由（PR #556）

---

## PR #509 (Layer2 outcome labels): outcome_labeling_loop startup 追加 (2026-06-02)

### 変更: ENABLE_OUTCOME_LABELING フラグで outcome_labeling_loop を条件起動
- **対象凍結ファイル**: `backend/app/main.py`
- **変更内容**:
  - `ENABLE_OUTCOME_LABELING=1` の場合のみ `outcome_labeling_loop` を startup イベントで起動
  - `OUTCOME_LABELING_INTERVAL_HOURS` 環境変数でポーリング間隔を制御（デフォルト 6h）
  - 未設定時（`ENABLE_OUTCOME_LABELING` デフォルト `"0"`）は起動しない（安全デフォルト）
- **理由**: Layer2 outcome label 収集バッチ（realized_yield / regret_score / is_positive_example）を staging 24h 検証できるようにするための配線。フラグ OFF のまま本番デプロイしても既存動作に影響なし。
- **影響範囲**: startup シーケンスのみ。既存スケジューラー・エンドポイントへの影響なし。`ENABLE_OUTCOME_LABELING` 未設定時は何もしない。
- **承認**: feat/layer2-outcome-labels → main の通常フロー経由（PR #509）

---

## PR #373 (Stream 4): scheduler 二重起動防止 — Blue/Green color guard (2026-05-22)

### 変更: active color のみ ai_judgment_loop を起動
- **対象凍結ファイル**: `backend/app/main.py`, `docker-compose.production.yml`, `docker-compose.staging.yml`, `scripts/deploy_production.sh`, `scripts/deploy_staging.sh`
- **変更内容**:
  - `_is_scheduler_enabled()` に `BACKEND_COLOR` vs `ACTIVE_BACKEND_COLOR` 比較ガード追加（inactive color は scheduler skip + ログ出力）
  - compose (production/staging): backend-blue/green に `BACKEND_COLOR`(blue/green 固定) + `ACTIVE_BACKEND_COLOR: ${ACTIVE_BACKEND_COLOR:-}` を追加
  - deploy_production.sh / deploy_staging.sh: Blue/Green 切替時（upstream.conf 更新後）に `.env` の `ACTIVE_BACKEND_COLOR` を awk+tmpfile で更新
- **理由**: backend-blue/green の両方が ai_judgment_loop を起動し ai_decisions が 2倍生成される問題（2026-05-21 P0 / staging 観測で確認）の根本対策
- **影響範囲**: scheduler 起動判定のみ。`DISABLE_AI_JUDGMENT_SCHEDULER` ロジック・既存エンドポイント・トレード実行への影響なし。後方互換（`ACTIVE_BACKEND_COLOR` 未設定時は従来通り両起動）
- **承認**: claude.ai 明朝レビュー待ち（PR #373）。本番 deploy は HUMAN-REVIEW-REQUIRED

---

## backend/app/main.py

### 変更 #15: process_news_loop 起動を NEWS_AUTO_EXECUTE_ENABLED でガード (PR #814 / 2026-06-19)
- **コミット範囲**: `fix/cex-auto-execute-disable`
- **変更内容**: `process_news_loop` の `asyncio.create_task` 起動を
  `NEWS_AUTO_EXECUTE_ENABLED`（既定 false）の env フラグで条件分岐（13 行）。
  フラグ未設定時は起動せず info ログのみ。
- **理由**: CEX 自動発注の裏線封鎖（v4 完全おまかせ自動運用 Phase 0 / スライス0-F）。
  承認ゲートなしで 5 分毎に `exchange_service.execute_trade` を呼べた経路を安全側に倒す。
  多層防御の第1層（第2層=automation_router.py、第3層=scheduled_tasks.py は凍結対象外）。
- **影響範囲**: 既定で CEX 自動発注ループが起動しなくなるのみ。news/RAG/AI Judge/
  knowledge ・他 startup task への影響なし。
- **承認**: fix/cex-auto-execute-disable → main (PR #814)

### 変更 #14: chat_router include_router + ChatMessage table 登録 (PR #643 / 2026-06-12)
- **コミット範囲**: `feat/chat-history-persistence`
- **変更内容**: `app.include_router(chat_router, prefix="/api")` を追加 (3 行) +
  `from app.chat.models import ChatMessage  # noqa: F401` の table 登録用 import を追加 (2 行)。
- **理由**: チャット会話保存 + 履歴表示 (Asana GID: 1215648108179500)。
  LIFF チャットの会話を chat_messages テーブルに永続化し、`/api/chat/*` で
  履歴取得を提供する。`Base.metadata.create_all()` での table 自動作成のため
  models import が必要 (既存 tos_router / referral_api_router と同パターン)。
- **影響範囲**: include_router 登録 + noqa F401 import のみ。既存 endpoint・
  起動シーケンスへの影響なし。
- **承認**: feat/chat-history-persistence → main (PR #643)

### 変更 #13: 4軸コンセンサス weight startup validation 登録 (PR #630 / 2026-06-12)
- **コミット範囲**: `feat/consensus-config-prompts`
- **変更内容**: `startup_validate_consensus_weights` startup hook を追加 (12 行追加のみ)。
  `app.ai.agents` の `validate_agent_weights(MultiAgentContext.DEFAULT_WEIGHTS)` を
  起動時に実行し、不正な 4軸コンセンサス weight 設定を fail-fast で拒否する。
- **理由**: EPIC-1 1-5/1-8 — 4軸コンセンサス env 設定 (CONSENSUS_4AXIS_MODE 等) の
  導入に伴い、weight 合計不一致等の設定ミスを runtime ではなく起動時に検出する
  fail-closed 安全装置。既存の `startup_validate_model_config` /
  `startup_validate_oracle_staleness_env` と同パターン。
- **影響範囲**: 新規 startup hook 追加のみ。既存 endpoint・起動シーケンスへの影響なし
  (weight が正常なら no-op + INFO ログ 1 行)。
- **承認**: feat/consensus-config-prompts → main (PR #630)

### 変更 #12: ToS model import 名の変更 (UserAction → ToSUserAction) (PR #534 / 2026-06-04)
- **コミット範囲**: `fix/main-ci-tos-i001`
- **変更内容**: `from app.tos.models import (... UserAction ...)` の import を
  `ToSUserAction` にリネーム (table も user_actions → tos_user_actions)。
- **理由**: batch merge で ai/Hermes 版 user_actions (app/ai/models.py, MVP-P0-6) と
  tos 版が同名テーブル衝突し pytest 全 fail。ai 版を source of truth として不変とし、
  tos 側を tos_user_actions にリネーム。main.py は table 登録用 import 名の変更のみ
  (registration の noqa F401 import、ロジック影響なし)。
- **影響範囲**: import 名のみ。エンドポイント・起動シーケンス無変更。
- **承認**: fix/main-ci-tos-i001 → main (PR #534)

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

### 変更 #10: Lane P — monthly_line_report_loop 起動 (PR #499 / 2026-06-02)
- **コミット範囲**: `0320042` (feat/lane-p-line-monthly)
- **変更内容**:
  - `from app.automation.scheduled_tasks import monthly_line_report_loop` を動的 import として `startup_scheduled_tasks` 内に追加
  - `ENABLE_MONTHLY_LINE_REPORT=1` の場合のみ `asyncio.create_task(monthly_line_report_loop())` で起動
  - 未設定時は起動しない (opt-in)。計 5 行追加のみ。既存ループ・エンドポイントへの影響なし
- **理由**: Lane P (§18 通知導線) — `line_monthly_opt_in=True` かつ LINE 認証済みユーザーへ毎月1日 10:00 JST に月次損益 Flex Message を一括送信。LINE 審査前のロジック先行実装。
- **影響範囲**: startup シーケンスのみ。`ENABLE_MONTHLY_LINE_REPORT` 未設定時は何もしない。既存エンドポイント・スケジューラーへの影響なし。
- **承認**: feat/lane-p-line-monthly → main の通常フロー経由（PR #499）

### 変更 #9: Partner wallet balance KPI — wallet_balance_router 登録 (PR #440 / 2026-05-28)
- **コミット範囲**: `6713794` (feat/partner-wallet-balance-20260527)
- **変更内容**:
  - `from app.partner.wallet_balance_router import router as wallet_balance_router` を追加
  - `app.include_router(wallet_balance_router, prefix="/api/partner", tags=["partner"])` を `allocation_router` の直後に追加
  - 計 4 行追加のみ。既存 router・エンドポイント・ロジックへの変更なし
- **理由**: Asana 1215185901145482 / partner ダッシュボード — partner 自身のウォレット残高 (USDC + ETH on Base mainnet) を `/api/partner/wallet-balance` で取得し、`PerformanceSummaryKPI.tsx` に表示する。既存 `partner_router` / `allocation_router` と同パターンの新規 router 登録。
- **影響範囲**: 新規 router 追加のみ。既存 endpoint への影響なし。`backend/tests/partner/test_wallet_balance.py` で endpoint の存在と response shape を保証。
- **承認**: feat/partner-wallet-balance-20260527 → main の通常フロー経由（PR #440）

### 変更 #8: P0-2 Safety wiring — compound_risk_monitor startup 登録 (PR #240 / 2026-05-15)
- **コミット範囲**: `d6a4ed3` (feat/safety-wiring)
- **変更内容**:
  - `startup_scheduled_tasks` の `_loops` リストに `compound_risk_monitor` エントリを 1 件追加
  - `scheduled_manager.start_compound_risk_monitor(on_error=...)` を呼び出す tuple を追加（他の operational loops と完全に同一パターン）
  - 計 6 行追加のみ。既存 loop・エンドポイント・ロジックへの変更なし
- **理由**: P0-2 (Asana 1214822153727471) — 孤立コード状態だった `AutoEvacuator` / `CompoundRiskAssessor` の配線。
  `workflow.py` の AI 判断前に `CompoundRiskAssessor` pre-check を追加し、
  `scheduled_tasks.py` に `compound_risk_monitor_loop`（10分間隔でマルチプロトコル複合リスク評価 + AutoEvacuator dry_run）を追加。
  `main.py` への変更は startup_scheduled_tasks の `_loops` に同ループの登録を追加するのみ（既存 `SchedulerWatchdog` / `health_check` / `dca` と同パターン）。
- **影響範囲**: startup/shutdown シーケンスのみ。既存エンドポイント・ロジックへの影響なし。
  `compound_risk_monitor_loop` は 10 分ごとに dry_run=True で実行するため本番資産操作は発生しない。
- **承認**: claude.ai 判断 (2026-05-15 Pane 2 完了報告経由) / feat/safety-wiring → main (PR #240)

### 変更 #7: RAS Phase 1 cleanup — invitations_router 無効化 + referral prefix 修正 (PR #201 / 2026-05-09)
- **コミット範囲**: `e3210c8` + `95d51f3` (hotfix/ras-partner-referral-cleanup)
- **変更内容**:
  - `from app.invitations.router import router as invitations_router` をコメントアウト
  - `app.include_router(invitations_router)` をコメントアウト（Phase 2 物理削除予定）
  - 変更は計 2 行コメントアウト + ruff I001 自動修正のみ。新規ロジック追加なし
- **理由**: hkobayashi 判断 (A) 置換 (Asana 1214653767574265 / RAS F-17) /
  2026-05-09 UAT pre-check 中に発覚した以下の問題を一括修正:
  1. `APIRouter(prefix="/referral")` vs 仕様 `/partner/referral` の不一致
     — `referral/router.py` 側で prefix 変更 (main.py の include_router 行は変更なし)
  2. 旧 `/api/invitations` (Wave 2、16文字コード + 期限) と新 `/partner/referral` (RAS Phase 1、8文字) の二重化解消
  3. AppShell.tsx partner nav に「紹介プログラム」リンク未追加 → UI 側で追加
- **影響範囲**:
  - `/api/invitations/*` エンドポイントが全て 404 になる (Wave 2 招待フロー無効化)
  - `frontend/app/register/page.tsx` の旧招待コード登録フロー → 404 (非推奨フロー、UAT 影響なし)
  - production deploy 予定: **2026-05-15 Phase E** (staging 検証後)
  - staging には `ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(16) NULL` 適用済み前提
- **承認**: hkobayashi 判断 (A) 置換 / hotfix/ras-partner-referral-cleanup → main (PR #201)
- **関連**: Asana RAS Phase 1 GID 1214639261103650 / PR-H Asana GID 1214653767574265
- **ロールバック**:
  1. `git revert e3210c8` → invitations_router を再有効化、referral prefix を `/referral` に戻す
  2. staging: `docker compose -f docker-compose.staging.yml restart backend-blue`
  3. production (Phase E 後): `docker compose -f docker-compose.production.yml restart backend-blue`

### 変更 #9: ToS consent router 登録 (PR #425 / 2026-06-04)
- **コミット範囲**: worktree-lane-j-tos-consent
- **変更内容**:
  - `from app.tos.models import ToSConsent, UserAction` を追加 (Base.metadata 登録)
  - `from app.tos.router import router as tos_router` を追加
  - `app.include_router(tos_router)` を `referral_router` の直後に追加 (計 5 行追加のみ)
- **理由**: MVP-P0-14 — ToS active consent エンドポイント群を FastAPI app に登録。
  `app/tos/` 配下の router/models/service/schemas はこのブランチで新規追加。
  main.py への変更は include_router 登録のみ（既存 router と同パターン）。
- **影響範囲**: 新規 router 追加のみ。既存 endpoint への影響なし。
- **承認**: worktree-lane-j-tos-consent → main (PR #425)

## backend/app/database.py

変更なし（現時点）

## backend/conftest.py

変更なし（現時点）

## backend/requirements.txt

### 変更 #3: aiohttp<3.14 固定（vcrpy 非互換 / CI green 回復）(PR #529 / 2026-06-04)
- **コミット範囲**: `a300118` (fix/main-ci-green)
- **変更内容**: `aiohttp<3.14` を requirements.txt に追加
- **理由**: aiohttp 3.14.0 で `AsyncStreamReaderMixin` が削除され、vcrpy<=8.1.1 の cassette 再生が
  `ERROR` になり CI の `test_judge_with_rag_vcr` が2件 failing（upstream Issue #995 / PR #996 未リリース）。
  aiohttp は web3/ccxt 経由の transitive **runtime** dep のため requirements.txt 側で pin し、
  CI と prod で同一版（3.13.x）を保証。upstream が対応次第 (`vcrpy>8.1.1` + `aiohttp>=3.14`) に更新する。
- **影響範囲**: aiohttp の upper cap 追加のみ。web3 (`>=3.7.4`) / ccxt (`>=3.10.11`) との両立を
  `pip check` で確認済み。アプリケーションロジックへの影響なし。
- **承認**: fix/main-ci-green → main (PR #529)

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
