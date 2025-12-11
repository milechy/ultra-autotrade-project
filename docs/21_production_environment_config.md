# 21_production_environment_config.md
Ultra AutoTrade – Production 環境設定ガイド

本ドキュメントは、Ultra AutoTrade の **production（本番）環境** で使用する  
`.env.production` の設定項目と運用ポリシーを整理したものです。

- すべての資金が **リアル資産**
- 誤設定 = 直接的な資金リスク
- staging / 開発環境と **物理的に分離されたキー・ウォレット** を使用する

ことを目的とします。

---

## 1. 環境ファイルの役割

- 本番環境では、アプリケーションの設定値・秘密情報を **環境変数** で管理する
- サーバ上では、運用上の利便性のために `.env.production` ファイルを使用してもよいが、
  - `.env.production` 自体は **Git にコミットしない**
  - ファイル権限を最小限（例：`chmod 600`）に制限する

本ドキュメントは、`.env.production` に定義すべき主な項目と  
staging 環境（`docs/17_staging_environment_config.md`）との差分ポリシーを示す。

---

## 2. 本番環境の前提・ポリシー

- ネットワークは **本番ネットワーク**
  - 例：Aave の場合、`AAVE_NETWORK=polygon` など
- 資金は **本番用ウォレット** にのみ存在し、staging 用ウォレットとは完全に分離する
- Notion / OctoBot / Aave / 通知サービスは、それぞれ本番専用のキー・URL を使用する
- `.env.staging` の内容を **コピーして流用しない**
  - 各キー・秘密情報は、環境ごとに物理的に異なるものを用意する

---

## 3. `.env.production` の構造（項目一覧）

※ 以下は「変数名の一覧と役割」を示すものであり、  
　具体的な値や秘密情報は一切記載しないこと。

### 3.1 Core / 共通設定

- `APP_ENV`
  - 例：`production`
  - アプリケーションが現在どの環境で動作しているかを判定するためのフラグ

- （その他、backend 実装で既に使用している共通系の環境変数）
  - 例：タイムゾーン、ロギング設定、HTTP ポート番号など  
  - **新しい変数名を追加する場合は要件変更チャット経由で仕様に反映すること**

---

### 3.2 Notion 関連

- `NOTION_API_KEY`
  - 本番 Notion API へのアクセスキー
  - staging 用 `NOTION_API_KEY_DEV` / `NOTION_API_KEY_STAGING` などと混在させない

- `NOTION_DATABASE_ID`
  - 本番で運用する Notion データベースの ID
  - staging 用の DB ID とは必ず分離する

- `NOTION_API_BASE_URL`
  - 通常は `https://api.notion.com`
  - 特殊なルーティングを行う場合のみ変更

- `NOTION_API_VERSION`
  - 使用している Notion API のバージョン（例：`2022-06-28`）

---

### 3.3 OctoBot 関連

- `OCTOBOT_API_BASE_URL`
  - 本番 OctoBot インスタンスの Base URL
  - 例：`https://octobot.example.com/api`
  - staging 用（`https://octobot-staging.example.com/api` 等）と混同してはならない

- `OCTOBOT_API_KEY`
  - 本番 OctoBot に対してトレードシグナル等を送信するための API キー
  - 本番資金へのアクセス権限を持つため、厳格に管理する

- `OCTOBOT_TIMEOUT_SECONDS`
  - OctoBot API 呼び出しのタイムアウト秒数
  - 通信遅延を考慮しつつ、過度な待ち時間にならない範囲で設定

---

### 3.4 Aave / チェーン関連

- `AAVE_NETWORK`
  - 例：`polygon`
  - テストネット用の `polygon-mumbai` 等と異なる値になる

- `AAVE_RPC_URL`
  - 本番ネットワーク向け RPC エンドポイント URL
  - Infura / Alchemy 等の本番用プロジェクトを使用する

- `AAVE_DEFAULT_ASSET_SYMBOL`
  - デフォルトで運用対象とするアセット（例：`USDC`）

- `AAVE_MAX_SINGLE_TRADE_USD`
  - 1 回のトレードで許容される上限金額（USD 換算）
  - 本番では staging よりも慎重な値を設定することが多い

- `AAVE_MIN_HEALTH_FACTOR`
  - ヘルスファクターの下限値
  - これを下回る運用は行わない

- `AAVE_TRADE_COOLDOWN_SECONDS`
  - 連続トレードを防ぐためのクールダウン時間（秒）

- `AAVE_PRIVATE_KEY_PROD`
  - 本番用ウォレットの秘密鍵
  - **この値は決して Git / ログ / チャット等に貼り付けない**

---

### 3.5 通知・監視関連

- （例）LINE / Slack / Webhook などの通知先トークン・URL
  - 具体的な変数名は運用設計 / 既存実装に従う
  - staging 用トークンと共有せず、**本番用のチャネル** を利用する

---

### 3.6 AI / LLM 関連

- LLM クライアント用の API キーやモデル名等
  - 具体的な変数名は backend 実装・`05_ai_judgement_rules.md` で使用されているものに合わせる
  - 例として `OPENAI_API_KEY` 等が考えられるが、**実際の変数名はコード側を必ず確認すること**

### 3.7 メトリクス・監視しきい値関連

本番環境では、監視・アラートが直接資金リスクに影響するため、  
staging よりも慎重な値を設定する。

| 変数名                    | 必須 | 説明                                                   | Production 例                               |
|--------------------------|------|--------------------------------------------------------|--------------------------------------------|
| `MONITOR_HEALTHCHECK_URL`| 必須 | HTTP ヘルスチェック対象の URL                         | `https://backend.example.com/health`       |
| `MONITOR_WARN_MS`        | 任意 | レイテンシ警告しきい値（ミリ秒）                       | `1000`                                     |
| `MONITOR_ALERT_MS`       | 任意 | レイテンシアラートしきい値（ミリ秒）                   | `30000`                                    |
| `METRICS_LOG_DIR`        | 任意 | メトリクス用ログファイル配置ディレクトリ               | `/var/log/ultra`                           |
| `MONITOR_NOTIFY_CHANNEL` | 任意 | 監視アラート送信先（本番用通知チャネル名、または種別） | `production-monitoring`                    |

運用ポリシー：

- 本番通知チャネルは staging と共有せず、**本番運用専用のチャネル** を利用する。
- `docs/08_automation_rules.md` で定義された閾値と矛盾しない設定とすること。
- しきい値を変更する際は、`docs/19_operations_runbook.md` の  
  「10. メトリクスレビューと改善サイクル」に従い、理由と日時を記録する。

---

## 4. Staging との比較・差分ポリシー

- 詳細な staging 用設定は `docs/17_staging_environment_config.md` を参照
- `.env.staging` と `.env.production` の関係性：
  - ファイル名は似ているが、**中身は完全に別物** として扱う
  - 特に以下は **必ず本番用に差し替える**：
    - `AAVE_NETWORK` / `AAVE_RPC_URL` / `AAVE_PRIVATE_KEY_PROD`
    - `OCTOBOT_API_BASE_URL` / `OCTOBOT_API_KEY`
    - `NOTION_API_KEY` / `NOTION_DATABASE_ID`
    - 通知・AI 系キー全般
- 「staging の値をベースにして、一部だけ本番用に上書きする」運用は原則禁止
  - 誤ってテスト用 RPC / ウォレットを本番で使う、またはその逆のリスクがあるため

---

## 5. `.env.production` の管理・権限

- `.env.production` は次のルールで管理する：
  - Git 管理外（`.gitignore` に含める）
  - サーバ上の配置パスはインフラ設計に従うが、原則としてアプリケーションディレクトリ直下などに限定する
  - 所有ユーザ：デプロイユーザ（例：`ultra`）
  - パーミッション：`chmod 600`（所有者のみ読み取り・書き込み）

- ファイル配布の方針：
  - できる限り手入力または安全なチャンネル（暗号化チャネル）で共有する
  - SCP 等でのコピー時には、転送元・転送先の権限設定を必ず確認する

---

## 6. 運用チェックリスト（抜粋）

本番環境でのリリース・設定変更時には、少なくとも以下を確認する：

- [ ] `.env.production` がサーバ上に存在する
- [ ] ファイル権限が `600` になっている
- [ ] `APP_ENV=production` になっている
- [ ] Aave / OctoBot / Notion / 通知系の URL / キーが **本番用** になっている
- [ ] `AAVE_NETWORK` / `AAVE_RPC_URL` がテストネットではない
- [ ] `AAVE_PRIVATE_KEY_PROD` が staging / 開発用と異なるウォレットである
- [ ] 通知チャネル（LINE / Slack 等）が、本番運用用のチャネルに向いている
- [ ] 変更内容が `docs/13_security_design.md` / `docs/19_operations_runbook.md` 等と矛盾していない

本チェックリストは `19_operations_runbook.md` や `20_staging_release_checklist.md` と連携して  
必要に応じて拡張していく。
