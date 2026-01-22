# 13_security_design.md  
Ultra AutoTrade – セキュリティ設計書（完全版）

本ドキュメントは、Notion → AI → OctoBot → Aave という自動運用システムにおいて  
「資金を失わない」「GPTの自動生成コードが安全に実行できる」ことを目的に作成する。

---

# 1. APIキー管理（Notion / AI / OctoBot / Aave）

## 1.1 APIキーの保存場所
- すべて「環境変数」で管理する  
- `.env` を使用する場合は **必ず .gitignore に追加**
- GitHub に push される形で保存してはならない

## 1.2 本番／開発キーの分離
- `NOTION_API_KEY_PROD`
- `NOTION_API_KEY_DEV`
- `AAVE_PRIVATE_KEY_PROD`
- `AAVE_PRIVATE_KEY_DEV`

誤用を防ぐため、環境切替フラグを導入：

```
APP_ENV=dev | prod
```
- 本番用のキー・秘密情報は **`.env.production` にのみ定義** する
  - ローカル開発用 `.env.local` や staging 用 `.env.staging` と混在させない
  - どの環境でどの .env が使われているかは、  
    staging 用は `docs/17_staging_environment_config.md`、  
    本番用は `docs/21_production_environment_config.md` に記録しておく

- `.env.staging` と `.env.production` の中身をコピーして使い回さない
  - 特に API キー・ウォレット関連は環境ごとに **物理的に異なるもの** を用意する

- 本番と開発（staging / local）の API キー・ウォレットは、必ず物理的に分離する
  - 同じ鍵・トークンを複数環境で使い回さない
- 本番用のキー・秘密情報は **`.env.production` にのみ定義** する
  - staging 用は `.env.staging`
  - ローカル開発用は `.env.local` など
  - 各環境ごとの .env ファイルを必ず分ける

- `.env` 系ファイルはすべて Git 管理外とし、`.gitignore` に含める
  - 誤って GitHub に push された場合は、即座にキーのローテーションを行う

- 環境ごとの .env に何を定義するかは、次のドキュメントで管理する
  - staging 環境：`docs/17_staging_environment_config.md`
  - production 環境：`docs/21_production_environment_config.md`


## 1.3 Aave 関連環境変数

- `AAVE_NETWORK`
- `AAVE_DEFAULT_ASSET_SYMBOL`
- `AAVE_MAX_SINGLE_TRADE_USD`
- `AAVE_MIN_HEALTH_FACTOR`
- `AAVE_TRADE_COOLDOWN_SECONDS`

### 方針

- すべて環境変数から読み取るが、Phase4 時点では **必須にはしない**
- 未設定の場合は Aave モジュール側で安全なデフォルト値を採用する：
  - `AAVE_NETWORK`: `"sepolia"`
  - `AAVE_DEFAULT_ASSET_SYMBOL`: `"USDC"`
  - `AAVE_MAX_SINGLE_TRADE_USD`: `"100.0"`
  - `AAVE_MIN_HEALTH_FACTOR`: `"1.6"`
  - `AAVE_TRADE_COOLDOWN_SECONDS`: `600`（10分）
- 本番環境では `.env` ではなくインフラ側のシークレット管理に移行すること

## 4.x Aave 機能のフェイルセーフ

- Aave 関連設定が不正値の場合、アプリケーション起動時に例外で気づけるようにする
- ランタイムエラー時は「ポジションを増やさない」挙動（NOOP or ERROR）を優先
- Aave 機能が無効でも、Notion / AI / OctoBot 部分は単体で動作できるように分離する

---

# 2. 秘密鍵の保護（Aave運用）

## 2.1 原則
- Aave運用に使用する秘密鍵は **最低限の金額のみ保持した専用ウォレット**  
- 運用額に応じてウォレットを分割（資産集中を避ける）

## 2.2 ハードウェアウォレットの推奨
本番環境では可能であれば **Ledger などの HW Wallet を使用**。

## 2.3 マルチシグ設定（任意）
- Gnosis Safe を利用し、運用の大きなアクションは multi-sig による承認を必要とする

---

# 3. 操作額制限（スマートコントラクト保護）

```
・1回の最大投資額：総資産の 10% 以内  
・1日最大投資額：総資産の 30% 以内  
・自動売買は 10分間に 1回まで  
```

---

# 4. 通信暗号化ポリシー

- すべて HTTPS / TLS
- API通信ログには資格情報を含めない
- Webhook / OctoBot API は IP 制限を設定（安全な IP のみ許可）

---

# 5. ログのサニタイズ（匿名化）

ログに以下を出してはならない：

- トークン
- APIキー
- 秘密鍵
- 生のウォレットアドレス（必要に応じて先頭6文字＋末尾4文字）

---

# 6. セキュリティ自動化

- エラー多発時に自動停止
- AI判定が異常値連続（例：BUY or SELL が5回連続）→ 停止
- Aaveヘルスファクター < 1.6 → 運用ストップ通知

---

# 7. 緊急停止（Emergency Stop）

```
・AI API エラー率 > 20%  
・OctoBot 応答なし 3回連続  
・Aave Gas エラー 2回連続  
・価格変動 > 20% / 1日  
```

該当したら自動的に：

- Aave から資金を引き出し
- 運用停止
- LINE / Slack へ通知

---

# 8. バージョン管理のセキュリティ

- GitHub Personal Token を使用（classic は禁止）
- SSH 認証必須
- main ブランチへの push は禁止（PR必須）

---

---

# 9. インフラデプロイ時の秘密情報管理

本番・staging 環境へのデプロイ時も、これまでのポリシー  
（API キーは環境変数管理 / Git に含めない）を一貫して守る。

## 9.1 環境ごとの .env / 環境変数方針

- 本番 / staging / 開発で、**環境ごとに値を分離** する
  - 例：
    - `.env.local`（ローカル開発マシン専用）
    - `.env.staging`（staging サーバ上にのみ配置）
    - `.env.production`（本番サーバ上にのみ配置）
- これらの `.env.*` ファイルは **必ず .gitignore に含める**
- ファイル権限
  - サーバ上では `chmod 600` を推奨
  - 所有ユーザはデプロイユーザ（例：`ultra`）のみ

## 9.2 Docker 運用時の秘密情報

- `docker-compose.staging.yml` などから `env_file: .env.staging` として読み込む
- `.env.staging` は **サーバ上のプロジェクトルート直下** にのみ配置し、Git には含めない
- Dockerfile には API キーや秘密情報を **絶対に書かない**
  - すべて `env_file` や `environment` 経由で注入する
- コンテナログに API キーやトークンを出さないよう、
  ログ出力時は値のマスク（先頭数文字のみなど）を徹底する

## 9.3 systemd 運用時の秘密情報

- Docker を使わない場合、systemd の `EnvironmentFile` 機能を利用する
  - 例：`/etc/ultra-autotrade/backend.env`
- `backend.env` の権限
  - `chmod 600 /etc/ultra-autotrade/backend.env`
  - 所有者：`root:root` または、専用デプロイユーザに限定
- `backend.env` 内のフォーマット例：
  ```ini
  NOTION_API_KEY=xxxxxxxx
  NOTION_DATABASE_ID=yyyyyyyy
  OCTOBOT_API_BASE_URL=https://octobot-staging.example.com/api
  OCTOBOT_API_KEY=octo_test_xxx
  AAVE_NETWORK=polygon-mumbai

  systemd ユニットファイルでは、次のように参照する：

  EnvironmentFile=/etc/ultra-autotrade/backend.env


## 9.4 デプロイユーザと権限管理
- サーバ上に、アプリケーション専用ユーザ（例：ultra）を用意する
このユーザのみがプロジェクトディレクトリに書き込み可能
- SSH ログインは公開鍵認証に限定し、パスワードログインは禁止
- sudo 権限は最小限にし、ultra ユーザでの sudo 実行は必要な場合のみに限定する

## 9.5 ログと秘密情報の取り扱い
- API レスポンスやリクエストをログに残す場合も、
アクセストークンやウォレットアドレスなどの機微情報は マスク or 削除 する
- ログファイルはサーバローカルか、セキュリティが担保されたストレージに保存し、
公開 S3 バケットなどには置かない
- ログローテーションを設定し、長期間のログがサーバ上に残りすぎないようにする

## 9.6 環境ごとの .env ファイルと接続先の分離
- 同じ変数名でも、環境ごとに接続先を必ず分離 する

 - 例：
  - AAVE_NETWORK / AAVE_RPC_URL：
   - staging: テストネット（例：polygon-mumbai）
   - production: 本番ネットワーク（例：polygon）

  - OCTOBOT_API_BASE_URL / OCTOBOT_API_KEY：
   - staging: ステージング OctoBot インスタンス
   - production: 本番 OctoBot インスタンス

  - NOTION_API_KEY / NOTION_DATABASE_ID：
   - staging: 検証用 Notion DB
   - production: 本番運用用 Notion DB

- .env.staging と .env.production の中身をコピーして使い回さない
  - 特に API キー・ウォレット関連は環境ごとに 物理的に異なるもの を用意する
- どの .env がどのサーバで使われているかを、ドキュメントとして明示する
  - staging 環境：`docs/17_staging_environment_config.md`
  - production 環境：`docs/21_production_environment_config.md`

- どの .env がどのサーバで使われているかを、ドキュメントとして明示する
  - staging 環境：`docs/17_staging_environment_config.md`
  - production 環境：`docs/21_production_environment_config.md`
- 新しい環境（例：検証用 sandbox 等）を追加する場合は、  
  専用の .env とドキュメントを作成し、既存環境のキーと混在させない

  # 10. バックアップ・リストア時のセキュリティ方針

## 10.1 バックアップの方針

- `.env.production` を含む設定ファイルは、以下の条件を満たす場合にのみバックアップする：
  - 暗号化されたストレージ（例：暗号化ボリューム、パスワード付きアーカイブ）に保存する
  - バックアップファイル自体も Git / 共有ストレージに無防備に置かない
  - アクセス権を最小限の運用メンバーに限定する

- バックアップ対象は次を想定する：
  - `.env.production`（もしくは同等の環境設定）
  - デプロイスクリプト / systemd unit / docker-compose ファイル
  - 運用ランブック（`docs/19_operations_runbook.md`） 等の手順書

- バックアップ作成時には、作成日時・作成者・対象環境（staging / production）を記録しておく。

## 10.2 リストア時のチェック

- バックアップから `.env.production` を復元する際は、必ず次を確認する：
  - 復元対象が **正しい環境（production）向けのファイル** であること
  - staging 用のキーやウォレット情報が混入していないこと
  - 期限切れのキー（API キー・トークン）が含まれていないこと

- 復元後に必ず実施するチェック：
  - `docs/21_production_environment_config.md` に記載の必須項目が埋まっている
  - `docs/22_production_release_checklist.md` の「前提条件チェック」を満たす

## 10.3 インシデント時のキー・秘密情報の扱い

- `.env.production` の内容が漏えいした疑いがある場合：
  - 直ちに該当する API キー・秘密鍵をローテーションする
  - Aave / OctoBot / Notion / 通知サービス側で、古いキーの無効化を行う
  - ログ・監査情報を確認し、不正アクセスや不正トレードがないかを調査する
  - 詳細な手順は `docs/19_operations_runbook.md` のインシデント対応セクションに従う
