---
name: ops-doc-loader
description: Load ops reference docs BEFORE writing any curl command to production/staging API, any ALTER TABLE / INSERT / UPDATE / DELETE SQL, or invoking deploy scripts. References docs/ops/01-03 to prevent guessed endpoints/columns/container names (2026-04-24 incident pattern).
---

# Ops Doc Loader Skill

## When to Use (Automatic Triggers)

このスキルは以下 4 トリガーで自動発火する想定:

1. **curl コマンドを書く前** (production / staging API)
2. **ALTER TABLE / INSERT / UPDATE / DELETE SQL を書く前**
3. **`deploy_production.sh` / `deploy_staging.sh` を呼ぶ前**
4. **`docker exec ... psql` コマンドを書く前**

CLAUDE.md `## 開発フェーズ別チェックポイント（2026-04-24追加）` の Phase 1 (調査) を強制発火させる位置付け。

## Required Reading (この順番で先読み)

### Before curl

```bash
# 必ず view する
docs/ops/01_api_endpoints.md
```

推測で curl パスを書くことは禁止。CLAUDE.md `## 開発フェーズ別チェックポイント（2026-04-24追加）` Phase 1 参照。

- HTTP method を必ず明示する (`curl -sI` は HEAD なので POST エンドポイントで 405 になる、CLAUDE.md `## 2026-05-13追加（5/12 終日 UAT ブロッカー 教訓 20 策...）` 策 6 参照)
- CF Access 保護下の staging API は `CF-Access-Client-Id` / `CF-Access-Client-Secret` ヘッダーが必要
- production SPA → API クロスオリジン fetch は `credentials: 'include'` 必須

### Before SQL (ALTER / INSERT / UPDATE / DELETE)

```bash
# 必ず view する
docs/ops/02_db_tables.md
```

- カラム名・型・NULL 可否を確認
- テーブル名から機能を推測しない (`ai_feedbacks` ≠ AI判定本体、`ai_decisions` が本体)
- 推測で ALTER TABLE を書くことは禁止 (CLAUDE.md `### 2026-04-15追加（本番DB操作ルール）` Step 1-3 参照)

事前確認 3 ステップ (本番 DB 操作前):

```bash
# Step 1: コンテナ名を取得
docker ps | grep postgres
# Step 2: DBユーザー名・DB名を取得
docker exec <container> env | grep POSTGRES
# Step 3: テーブル一覧を取得
docker exec <container> psql -U <user> -d <db> -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
```

### Before Deploy

```bash
# 必ず view する
docs/ops/03_deploy_procedures.md
```

- コンテナ名・ボリューム・障害対応の正本
- container_name は `*-production` suffix (CLAUDE.md `## 環境定義（2026-04-17 B案リネーム後）`)
- deploy 詳細は `ultra-deploy` skill を併用

## Production への INSERT / UPDATE / DELETE 適用ルール

production DB に対してデータ変更 SQL を実行する場合、**3 段プロンプト + 山本承認 + migration plan 参照を必須** とする。

CLAUDE.md `### 2026-05-02追加（テストデータ投入制限 — 本番DB cleanup インシデント GID 1214121103957100 再発防止）` および `### 2026-04-15追加（本番DB操作ルール）` に準拠:

### 必須手順

1. **Phase 1 (read-only 確認)**: 対象テーブルの現状を `SELECT` で確認
2. **Phase 2 (実装プラン + 承認待ち)**: 触る行・SQL 文面・ロールバック手順を文書化し、ユーザー承認を取る
3. **Phase 3 (実行 + 検証)**: バックアップ取得 → 実行 → 検証 → Slack 通知
4. **山本さん承認** (UAT に影響する場合)
5. **関連 migration plan 参照必須**:
   - `docs/45_fee_model_v10_migration_plan.md`
   - `docs/46_users_tier_migration_plan.md`
   - `docs/47_users_risk_mode_migration_plan.md`
   - `docs/48_fee_config_seed_runbook.md`

### 自動スクリプトからの直接 production DB 操作は禁止

Agent Teams / CI / 自動スクリプトから production DB へのデータ変更操作は**禁止**。
手動の 3 段プロンプト + 山本承認のみ許可。

テストデータ投入は staging コンテナのみ:
- 許可: `ultra-autotrade-postgres-staging` + DB `ultra_autotrade_staging`
- 禁止: `ultra-autotrade-postgres-production` + DB `ultra_autotrade`

## Anti-Patterns

以下のアンチパターンが過去のインシデントを引き起こした (CLAUDE.md `## 2026-04-21 教訓: ドキュメント更新でも E2E 先行と3層確認を徹底` 参照):

- ❌ memory から「Privy が動いている」と推論 (実装は別物だった)
- ❌ テーブル名から機能を推測 (`ai_feedbacks` ≠ AI判定本体)
- ❌ docker container 名を推測 (実際: `ultra-autotrade-postgres-production`)
- ❌ `curl -sI` で POST エンドポイント確認 (HEAD になり 405)
- ❌ E2E 未検証でドキュメント公開 (操作が機能しない手順書を main に上げる)

## Pre-Operation Protocol

CLAUDE.md `## 開発フェーズ別チェックポイント（2026-04-24追加）` Phase 1 (調査) を必ず通す:

1. `docs/ops/01-03` を view 済みか確認
2. 認証・権限系なら 3 層確認 (フロント UI / バックエンドエンドポイント / DB カラム)
3. production 操作なら Phase 1 (read-only) → Phase 2 (plan) → Phase 3 (実装) の 3 段
4. テスト → `./scripts/verify.sh` 一括検証 → 外形 healthcheck

## References

- `docs/ops/01_api_endpoints.md` — 全 API エンドポイント (パス・認証・curl 例)
- `docs/ops/02_db_tables.md` — 全 DB テーブル定義 (カラム・型・NULL 可否)
- `docs/ops/03_deploy_procedures.md` — デプロイ手順・コンテナ名・障害対応
- `docs/ops/04_frontend_route_map.md` — フロントエンドルートマップ
- `docs/ops/05_backend_modules_map.md` — バックエンドモジュールマップ
- `docs/45_fee_model_v10_migration_plan.md`
- `docs/46_users_tier_migration_plan.md`
- `docs/47_users_risk_mode_migration_plan.md`
- `docs/48_fee_config_seed_runbook.md`
- CLAUDE.md `## 開発フェーズ別チェックポイント（2026-04-24追加）`
- CLAUDE.md `## 2026-04-21 教訓: ドキュメント更新でも E2E 先行と3層確認を徹底`
- CLAUDE.md `### 2026-04-15追加（本番DB操作ルール）`
- CLAUDE.md `### 2026-05-02追加（テストデータ投入制限 — 本番DB cleanup インシデント）`
