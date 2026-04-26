# Backend Core File Change Log

凍結ファイル（`FROZEN_PATTERNS`）の変更申請記録。
変更前に PR レビューを通過させ、ここにエントリを追加すること。

---

## 凍結ファイル登録表

CI チェック (`.github/workflows/path-check.yml`) および pre-commit フック (`scripts/check_frozen_files.sh`) が参照する凍結ファイルの公式リスト。
新規ファイルを凍結する場合はこの表と `path-check.yml` の `FROZEN_PATTERNS` を同時に更新すること。

| # | パス | 凍結理由 | 解凍条件 |
|---|------|---------|---------|
| 1 | `backend/app/main.py` | FastAPI router 登録・startup イベント・health エンドポイントの中核。意図しない変更でスケジューラー・CORS・依存注入が壊れる（2026-04-02 インシデント参照） | アーキテクチャ変更 PR + Opus レビュー + backend_deps.md 申請 |
| 2 | `backend/app/database.py` | ORM セッション管理・トランザクション制御の中核。変更するとデータ不整合やデッドロックのリスクがある | DB 移行計画 PR + Opus レビュー + backend_deps.md 申請 |
| 3 | `backend/app/shared/` | 全モジュール共通の定数・型・ユーティリティ。1 ファイル変更が全モジュールに波及する | 変更範囲を tests/ でカバーした上で backend_deps.md 申請 |
| 4 | `backend/conftest.py` | pytest グローバルフィクスチャ。変更すると全テストの前提が崩れ、カバレッジゲートを突破するバグが混入する（2026-04-25 F-9 lint fail インシデント参照） | テストアーキテクチャ変更 PR + backend_deps.md 申請 |
| 5 | `backend/requirements.txt` | Python 依存バージョンの master。不用意な変更で CVE が混入する。pip-compile 管理外のため手動編集がデグレを起こしやすい（CVE-2026-24049 インシデント参照） | セキュリティパッチ or 機能追加 PR + backend_deps.md 申請 |
| 6 | `backend/alembic/versions/*.py` | DB マイグレーション履歴。一度 main にマージされたバージョンを編集すると本番 DB の alembic_version と矛盾して復旧不能になる | 変更禁止（ロールバックは新規マイグレーション作成） |
| 7 | `frontend/package-lock.json` | npm 依存ロック。CLAUDE.md で `npm install --legacy-peer-deps` に統一済み。手動編集すると Docker ビルド・CI が壊れる | `npm install --legacy-peer-deps` 実行後の自動更新のみ |
| 8 | `.github/workflows/path-check.yml` | 凍結ファイルガードの CI 本体。変更するとガードが無効化される恐れがある | ガード強化または機能拡張の場合は Opus レビュー必須 |
| 9 | `.github/workflows/env-separation-check.yml` | env 分離チェック CI（2026-04-18 インシデントの根本対策）。変更するとステージング/本番の誤混入を見落とす | セキュリティ観点のレビュー + Opus 承認必須 |
| 10 | `pyproject.toml` | ruff/mypy/pytest/coverage 設定。緩和方向の変更（coverage 閾値低下など）は全員への品質影響があるため原則禁止 | 品質向上目的のみ許可。緩和は Opus レビュー必須 |

### 凍結ファイル変更フロー

```
1. この表で凍結理由・解凍条件を確認
2. backend_deps.md に「変更 #N」エントリを追加（後述フォーマット参照）
3. feature ブランチで変更を実装
4. PR 作成 → path-check CI が自動検証（backend_deps.md 更新済みなら WARN 扱い）
5. Opus レビュー（解凍条件に「Opus レビュー」が含まれる場合）
6. main マージ
```

### 変更申請エントリ フォーマット（テンプレート）

```markdown
### 変更 #N: <変更タイトル> (PR #xxx / YYYY-MM-DD)
- **コミット範囲**: `<sha>` (<ブランチ名>)
- **変更内容**:
  - <箇条書き>
- **理由**: <凍結条件のどれに該当するか>
- **影響範囲**: <変更が波及するモジュール・テスト>
- **承認**: <レビュアー名 or PR番号>
```

---

## 変更ログ

### backend/app/main.py

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

## backend/app/database.py

変更なし（現時点）

### backend/conftest.py

変更なし（現時点）

### backend/requirements.txt

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

### backend/app/shared/

変更なし（現時点）
