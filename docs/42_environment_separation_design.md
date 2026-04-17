# 42_environment_separation_design.md
Ultra AutoTrade – 環境分離設計記録（2026-04-17）

## 背景

2026-04-17の調査（Hetzner VPS調査）で判明した実態:

- Hetzner VPS上には `docker-compose.staging.yml` によって起動された `*-staging` コンテナのみ稼働
- この `*-staging` コンテナ群が `app.ultra-auto-trade.com` / `api.ultra-auto-trade.com` に実際にサービス提供
- `docker-compose.production.yml` は存在したが未起動（*-production コンテナは一切稼働していない）
- Cloudflare Tunnelのingressは `localhost:3000` / `localhost:8000` に直結 → stagingコンテナが本番URL配信
- **結論**: staging命名のコンテナが本番環境として稼働しており、環境分離が実質存在しなかった

## B案選択の理由

| 選択肢 | 内容 | 採用/却下 |
|--------|------|----------|
| A案: 現状維持 | stagingコンテナが本番URLを配信し続ける（リネームなし）| 却下: 混乱が恒久化する |
| **B案: リネーム** | 既存のstaging → production として正式化、新しいstagingを別途構築 | **採用** |
| C案: 完全再構築 | コンテナ名も含めて全面的にリネーム | 却下: Hetzner稼働中コンテナの停止が必要、テスター影響大 |

B案は稼働中コンテナに触れず、ファイル・スクリプトのリネームのみで環境を正式化できるため採用。

## 6つの設計判断（Q1-Q6）

| # | 質問 | 決定 |
|---|------|------|
| Q1 | 命名方針 | 現staging.yml → production.yml に統合 + 新staging.yml 作成 |
| Q2 | テストネット | Base Sepoliaテストネット流用 |
| Q3 | Staging動作モード | Shadow Mode専用（AI_SHADOW_MODE=true, REBALANCE_SHADOW_MODE=true）|
| Q4 | Staging URL保護 | Cloudflare Access + Google認証（Phase 4で実施）|
| Q5 | データ同期 | 完全独立・新規DB（ultra_autotrade_staging）|
| Q6 | Privy | Allowed Origins に https://staging.ultra-auto-trade.com 追加（Phase 4）|

## ファイル変更一覧

### リネーム
| 旧ファイル | 新ファイル | 内容 |
|-----------|-----------|------|
| `docker-compose.staging.yml` | `docker-compose.production.yml` | 旧stagingを本番として正式化 |
| `scripts/deploy_staging.sh` | `scripts/deploy_production.sh` | 本番デプロイスクリプト |
| `.env.staging`（Hetzner上）| `.env.production`（Hetzner上）| 本番環境変数（Phase 3で実施）|

### 新規作成
| ファイル | 内容 |
|---------|------|
| `docker-compose.staging.yml` | 真のStaging用（port 3001/8001/5433）|
| `scripts/deploy_staging.sh` | Staging専用デプロイ（Shadow Mode強制確認付き）|
| `.env.staging.example` | Staging環境変数テンプレート（更新）|
| `docs/42_environment_separation_design.md` | 本ドキュメント |

### アーカイブ
| ファイル | 内容 |
|---------|------|
| `docker-compose.production.yml.legacy` | 旧production.yml（未起動だったもの）|

## 2環境共存のためのポート/ボリューム/ネットワーク分離設計

| リソース | Production（稼働中） | Staging（新規構築予定）|
|---------|---------------------|----------------------|
| Frontend port | 0.0.0.0:3000 | 127.0.0.1:3001 |
| Backend port | 0.0.0.0:8000 | 127.0.0.1:8001 |
| Postgres port | 0.0.0.0:5432 | 127.0.0.1:5433 |
| Loki port | 0.0.0.0:3100 | 127.0.0.1:3101 |
| コンテナ名 | `*-staging`（既存維持）| `*-staging-new` |
| Docker project | `ultra-autotrade-project` | `ultra-autotrade-staging` |
| ネットワーク | `ultra-autotrade-project_default` | `ultra-autotrade-staging_default` |
| Postgres volume | `ultra-autotrade-project_postgres-data` | `ultra-autotrade-staging_postgres-data` |
| DB名 | `ultra_autotrade` | `ultra_autotrade_staging` |

## Phase別実施計画

| Phase | 内容 | 実施時期 |
|-------|------|---------|
| **Phase 1** | Hetzner VPS バックアップ（完了） | 2026-04-17 |
| **Phase 2** | ローカルでファイルリネーム + 新staging.yml作成（本ドキュメント）| 2026-04-17 |
| **Phase 3** | HetznerでファイルDeploy（.env.staging → .env.production リネーム）| 2026-04-17〜 |
| **Phase 4** | Cloudflare Tunnel Ingress に staging URL 追加 + Privy Allowed Origins 追加 | TBD |
| **Phase 5** | Staging環境初回デプロイ・DBセットアップ | TBD |

## コンテナ名 *-staging 維持の理由と将来対応

**現在**: productionコンテナ名が `*-staging` のまま（例: `ultra-autotrade-backend-staging`）

**理由**: Phase 2では稼働中コンテナへの影響ゼロが絶対条件。コンテナ名変更はdocker compose down/upが必要。

**将来対応**: メンテナンス時間帯を設けて以下を実施
1. `docker-compose.production.yml` のコンテナ名を `*-production` に変更
2. Hetznerで `docker compose up -d --remove-orphans` を実行
3. 旧 `*-staging` コンテナが自動的にorphanとして削除される

## セキュリティノート

- Staging環境の秘密鍵はProductionと物理的に分離することが必須（CLAUDE.md Security Rules 7）
- Shadow Mode（AI_SHADOW_MODE=true）はstagingのdeploy_staging.shで強制確認される
- Staging DB（ultra_autotrade_staging）はProductionとは別DBで完全独立
- TODO: Staging用ウォレット秘密鍵はBase Sepolia専用のものを生成すること
