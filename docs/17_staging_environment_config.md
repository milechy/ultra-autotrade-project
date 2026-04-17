# 17_staging_environment_config.md
Ultra AutoTrade – Staging 環境設定ガイド（2026-04-17 B案リネーム後）

> **2026-04-17 重要変更**: B案リネームにより旧stagingがProductionとして正式化。
> 本ドキュメントは「真のStaging」（Shadow Mode専用・Base Sepolia）の定義に更新済み。

本ドキュメントは、Ultra AutoTrade の **真のStaging環境** で使用する  
`.env.staging` の設定項目を整理したものです。

### 真のStaging環境の定義（2026-04-17以降）
- **URL**: staging.ultra-auto-trade.com / api-staging.ultra-auto-trade.com（Phase 4で設定予定）
- **compose**: `docker-compose.staging.yml`
- **env**: `.env.staging`
- **deploy**: `scripts/deploy_staging.sh`
- **ポート**: frontend 127.0.0.1:3001 / backend 127.0.0.1:8001 / postgres 127.0.0.1:5433
- **コンテナ名**: `*-staging-new` サフィックス
- **DB**: `ultra_autotrade_staging`（productionと完全独立）
- **Shadow Mode**: `AI_SHADOW_MODE=true` / `REBALANCE_SHADOW_MODE=true`（必須）

- ネットワークは **テストネット（Base Sepolia）**
- 資金はテスト用ウォレットに限定
- 本番用のキー / URL と混ざらないこと

を目的とします。

---

## 1. 環境ファイルの役割

- `.env.local`
  - ローカル開発用（個人マシン）
  - デバッグ・検証のための設定
- `.env.staging`
  - staging サーバ用
  - Aave テストネット / OctoBot ステージング / 検証用 Notion DB など
- `.env.production`
  - 本番サーバ用
  - 実運用の資金と本番サービスに接続

これらのファイルはすべて `.gitignore` 対象とし、  
サーバ上では `chmod 600` を推奨する。詳細は `13_security_design.md` を参照。

---

## 2. Aave（テストネット）関連の環境変数

Aave 設定は `backend/app/aave/config.py` から読み込まれる。

| 変数名                        | 必須 | 説明                                       | Staging 例                                   |
|------------------------------|------|--------------------------------------------|----------------------------------------------|
| `AAVE_NETWORK`               | 必須 | 利用するネットワーク名                     | `polygon-mumbai` などテストネット名         |
| `AAVE_RPC_URL`               | 必須 | 上記ネットワークの RPC エンドポイント     | `https://polygon-mumbai.infura.io/v3/...`    |
| `AAVE_DEFAULT_ASSET_SYMBOL`  | 任意 | デフォルト運用対象の資産シンボル          | `USDC`                                       |
| `AAVE_MAX_SINGLE_TRADE_USD`  | 任意 | 1 回のトレードで許容する最大 USD 相当額   | `5` など、極小値                             |
| `AAVE_MIN_HEALTH_FACTOR`     | 任意 | 最小許容 Health Factor                     | `1.6` など保守的な値                         |
| `AAVE_TRADE_COOLDOWN_SECONDS`| 任意 | 連続トレードのクールダウン時間（秒）      | `600`（10 分）など                           |

---

## 3. OctoBot（シグナル API）関連の環境変数

OctoBot 設定は `backend/app/bots/config.py` から読み込まれる。

| 変数名                   | 必須 | 説明                                  | Staging 例                                          |
|-------------------------|------|---------------------------------------|-----------------------------------------------------|
| `OCTOBOT_API_BASE_URL`  | 必須 | OctoBot 外部シグナル API のベース URL| `https://octobot-staging.example.com/api`          |
| `OCTOBOT_API_KEY`       | 必須 | シグナル送信用 API キー               | `octo_test_xxx`                                     |
| `OCTOBOT_TIMEOUT_SECONDS` | 任意 | HTTP タイムアウト秒数                 | `5`〜`10` 秒                                        |

- 本番用の OctoBot とは URL / API キーを明確に分ける
- テスト用インスタンスが落ちても資金リスクが無い構成にする

---

## 4. Notion 連携関連の環境変数

Notion 設定は `backend/app/notion/config.py` から読み込まれる。

| 変数名                  | 必須 | 説明                                      | Staging 例                           |
|------------------------|------|-------------------------------------------|--------------------------------------|
| `NOTION_API_KEY`       | 必須 | Notion API 用シークレットキー             | `secret_staging_xxx`                 |
| `NOTION_DATABASE_ID`   | 必須 | ニュース管理用の Notion Database ID       | `xxxx-yyyy-zzzz-...`                 |
| `NOTION_API_BASE_URL`  | 任意 | Notion API ベース URL                     | デフォルトのまま（通常は変更不要）   |
| `NOTION_API_VERSION`   | 任意 | Notion API バージョン                      | `2022-06-28` など                     |

- staging では **本番とは別の Database** を使用する
- 誤って本番 DB を参照しないよう、ID を明示的に分ける

---

## 5. その他（AI / 通知など）

AI クライアントや通知系クライアント（LINE / Slack 等）の環境変数は、  
各クライアント実装に従って `.env.staging` に追加する。

例（環境変数名は実装側に合わせて定義）:

- AI / LLM クライアント
  - LLM API 用のキー
  - モデル名、エンドポイント URL
- 通知系
  - LINE Notify トークン
  - Slack Webhook URL
  - その他通知チャネルのトークン / URL

これらも本番と staging で必ず分ける。

---

## 6. `.env.staging` サンプル

以下は、staging 環境用の `.env.staging` のイメージである。  
※ 値はすべてダミー。

```bash
# ===== Notion =====
NOTION_API_KEY=secret_staging_notion_xxx
NOTION_DATABASE_ID=1111-2222-3333-4444
NOTION_API_BASE_URL=https://api.notion.com
NOTION_API_VERSION=2022-06-28

# ===== OctoBot (staging) =====
OCTOBOT_API_BASE_URL=https://octobot-staging.example.com/api
OCTOBOT_API_KEY=octo_test_xxx
OCTOBOT_TIMEOUT_SECONDS=5

# ===== Aave (testnet) =====
AAVE_NETWORK=polygon-mumbai
AAVE_RPC_URL=https://polygon-mumbai.infura.io/v3/your_project_id
AAVE_DEFAULT_ASSET_SYMBOL=USDC
AAVE_MAX_SINGLE_TRADE_USD=5
AAVE_MIN_HEALTH_FACTOR=1.6
AAVE_TRADE_COOLDOWN_SECONDS=600

# ===== その他（AI / 通知など） =====
# AI / LLM クライアント用のキー
# 通知用トークン（LINE / Slack など）

## 6. 監視・自動化関連の環境変数

staging 環境でも、本番と同じ種類のメトリクスを取得できるよう、  
監視・自動化用の環境変数を定義しておく。

| 変数名                    | 必須 | 説明                                                   | Staging 例                                   |
|--------------------------|------|--------------------------------------------------------|----------------------------------------------|
| `MONITOR_HEALTHCHECK_URL`| 必須 | HTTP ヘルスチェック対象の URL                         | `http://localhost:8000/health`               |
| `MONITOR_WARN_MS`        | 任意 | レイテンシ警告しきい値（ミリ秒）                       | `1000`                                       |
| `MONITOR_ALERT_MS`       | 任意 | レイテンシアラートしきい値（ミリ秒）                   | `30000`                                      |
| `METRICS_LOG_DIR`        | 任意 | メトリクス用ログファイル配置ディレクトリ               | `/var/log/ultra`                             |
| `MONITOR_NOTIFY_CHANNEL` | 任意 | 監視アラート送信先（論理名。実際の通知先は通知設定に依存） | `staging-monitoring`                         |

- 具体的な利用方法は `docs/18_scheduler_and_cron.md` および  
  `scripts/monitor.sh` / `backend/app/automation/monitoring_service.py` の実装に従う。
- staging では本番と同じ項目を測ることを優先しつつ、  
  しきい値自体はやや緩めでもよい（例：テスト時の一時的高負荷を許容する）。

## 7. 本番環境への切り替え時の注意点（概要）
- .env.staging の内容をそのまま .env.production にコピーして使い回さない
- 少なくとも以下の項目は すべて本番用に差し替える必要がある：
 - Aave:
  - AAVE_NETWORK / AAVE_RPC_URL
  - 本番用ウォレット（別アドレス）と秘密鍵
 - OctoBot:
  - OCTOBOT_API_BASE_URL / OCTOBOT_API_KEY
 - Notion:
  - NOTION_API_KEY / NOTION_DATABASE_ID
 - その他通知 / AI 系キー
- 切り替え前に、15_rollback_procedures.md を参照し、
  ロールバック手順が機能することを staging で確認しておくこと

---

## Shadow Mode と .env.staging / .env.production の差分

### .env.staging（必須設定）
```
AI_SHADOW_MODE=true          # 判定記録のみ、実際のトレードは実行しない
APP_ENV=staging
EXCHANGE_SANDBOX=true
EXCHANGE_MAX_ORDER_USD=50    # Phase 1 上限
EXCHANGE_DAILY_TRADE_LIMIT=5
AI_CROSS_VALIDATION_ENABLED=false  # staging ではコスト節約のため無効
```

### .env.production（必須設定）
```
AI_SHADOW_MODE=false         # 実際のトレードを実行する
APP_ENV=prod
EXCHANGE_SANDBOX=false
EXCHANGE_MAX_ORDER_USD=100   # Phase 1 初期上限（段階的に引き上げ）
EXCHANGE_DAILY_TRADE_LIMIT=10
AI_CROSS_VALIDATION_ENABLED=true
```

### 重要な差分
| 項目 | staging | production |
|------|---------|------------|
| AI_SHADOW_MODE | true | false |
| APP_ENV | staging | prod |
| EXCHANGE_SANDBOX | true | false |
| EXCHANGE_MAX_ORDER_USD | 50 | 100〜 |
| APIキー | **物理的に異なるキーを使用** | **物理的に異なるキーを使用** |