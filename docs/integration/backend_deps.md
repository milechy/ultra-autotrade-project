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

### backend/app/database.py

変更なし（現時点）

### backend/conftest.py

変更なし（現時点）

### backend/requirements.txt

### 変更 #1: wheel バージョン固定（CVE-2026-24049）
- **コミット**: `fd2b6a6` (dev ブランチ)
- **変更内容**: `wheel>=0.46.2` を追加
- **理由**: CVE-2026-24049 — 悪意のある wheel ファイルを unpack した際の任意コード実行。Trivy HIGH 脆弱性。修正版 0.46.2 以降に固定。
- **影響範囲**: ビルドツールのみ。アプリケーションロジックへの影響なし。
- **承認**: dev → staging → main の通常フロー経由

### backend/app/shared/

変更なし（現時点）
