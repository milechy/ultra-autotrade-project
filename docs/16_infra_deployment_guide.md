# 16_infra_deployment_guide.md
Ultra AutoTrade – インフラデプロイガイド（staging 想定）

本ドキュメントは、Ultra AutoTrade のバックエンド（FastAPI）を  
Hetzner などの Linux サーバ上にデプロイし、**staging 環境** として安全に動かすための手順を示す。

---

## 1. 前提条件

- 対象環境
  - Debian / Ubuntu 系 Linux（例：Hetzner Cloud Ubuntu 22.04）
- 前提となるインストール
  - `git`
  - `docker` および `docker compose`（もしくは `docker-compose`）
- Ultra AutoTrade リポジトリが GitHub 上に存在し、  
  デプロイユーザが **SSH 鍵認証で clone 可能** であること
- セキュリティに関する前提
  - 本ドキュメントの内容は `13_security_design.md` に準拠する
  - staging では **本番資金を使わないウォレット** を利用する

---

## 2. デプロイ戦略の選択肢

本プロジェクトのバックエンドは、以下の 2 つの方法で常駐させることを想定する。

1. **Docker + docker-compose（推奨）**
   - `Dockerfile` ＋ `docker-compose.staging.yml` でコンテナとして起動
   - 環境変数は `.env.staging` を `env_file` として注入
2. **systemd + uvicorn（fallback）**
   - Python 仮想環境上で `uvicorn app.main:app` を起動
   - `infra/systemd/ultra-autotrade-backend.service` をテンプレートとして使用

本ガイドでは、**1. Docker + docker-compose** をメインパターンとして説明する。

---

## 3. staging 環境構築手順（Docker パターン）

### 3.1 サーバ初期設定

```bash
# パッケージ更新
sudo apt update && sudo apt upgrade -y

# docker / docker compose インストール（例：公式 convenience script）
curl -fsSL https://get.docker.com | sh

# デプロイ用ユーザに docker グループ権限を付与（例：ultra ユーザ）
sudo usermod -aG docker ultra

再ログイン後、docker ps が実行できることを確認する。

3.2 リポジトリ取得

# デプロイユーザでログイン（例）
ssh ultra@your-server

# 任意のディレクトリで clone
git clone git@github.com:your-org/ultra-autotrade.git
cd ultra-autotrade

以降、このディレクトリを project root と呼ぶ。

3.3 .env.staging の作成

project root 直下に .env.staging を作成し、
13_security_design.md のポリシーに従って必要な環境変数を定義する。

例（※値はダミー、実際は安全に管理する）：

# Notion
NOTION_API_TOKEN=secret_xxx
NOTION_DATABASE_ID=xxxxxxxx

# OctoBot
OCTOBOT_BASE_URL=https://octobot-staging.example.com
OCTOBOT_API_KEY=octo_yyy

# Aave / ネットワーク
AAVE_RPC_URL=https://polygon-mumbai.infura.io/v3/...
AAVE_NETWORK=polygon-mumbai
AAVE_WALLET_PRIVATE_KEY=0x...

# その他（AI, 通知など）
OPENAI_API_KEY=sk-...
LINE_NOTIFY_TOKEN=...
SLACK_WEBHOOK_URL=...

.env.staging は Git にコミットしない（.gitignore 対象）
サーバ上での権限は chmod 600 .env.staging を推奨

3.4 コンテナのビルドと起動

# project root にいる前提
docker compose -f docker-compose.staging.yml build
docker compose -f docker-compose.staging.yml up -d

起動状況確認：

docker compose -f docker-compose.staging.yml ps

---

4. systemd パターン（テンプレート利用）
Docker を利用できない環境向けの fallback パターン。

4.1 Python 仮想環境の作成

cd /opt/ultra-autotrade
python3 -m venv venv
source venv/bin/activate

# 必要なライブラリのインストール
pip install --upgrade pip
pip install fastapi "uvicorn[standard]" httpx

リポジトリは /opt/ultra-autotrade に clone 済みとする。

4.2 backend.env の作成

sudo mkdir -p /etc/ultra-autotrade
sudo touch /etc/ultra-autotrade/backend.env
sudo chmod 600 /etc/ultra-autotrade/backend.env
sudo chown root:root /etc/ultra-autotrade/backend.env

backend.env に staging 用の環境変数を定義する（内容は .env.staging 相当）。

4.3 systemd ユニットファイルの配置

infra/systemd/ultra-autotrade-backend.service を /etc/systemd/system/ にコピーし、
パスなどを実環境に合わせて修正する。

sudo cp infra/systemd/ultra-autotrade-backend.service \
  /etc/systemd/system/ultra-autotrade-backend.service

sudo systemctl daemon-reload
sudo systemctl enable ultra-autotrade-backend
sudo systemctl start ultra-autotrade-backend

---

5. ヘルスチェックと動作確認

5.1 HTTP ヘルスチェック
FastAPI 側で /health などのヘルスチェックエンドポイントが用意されている場合：

curl http://<server-ip>:8000/health
# 期待レスポンス例：
# {"status":"ok"}

これが成功すれば、staging backend が外部から到達可能 な状態である。

5.2 ログ確認
Docker パターン：

docker logs ultra-autotrade-backend-staging

systemd パターン：

sudo journalctl -u ultra-autotrade-backend -f

---

6. 更新・再デプロイ

6.1 scripts/deploy_staging_backend.sh の利用
staging サーバ上で、project root にて以下を実行することで

git pull（※任意）
イメージのビルド
コンテナの再起動

をまとめて行うことができる：

cd /path/to/ultra-autotrade
./scripts/deploy_staging_backend.sh

詳細は scripts/deploy_staging_backend.sh のコメントを参照。

---

7. 障害時の基本対応

状態確認
Docker：docker compose -f docker-compose.staging.yml ps
systemd：systemctl status ultra-autotrade-backend

ログ確認
Docker：docker logs ultra-autotrade-backend-staging
systemd：journalctl -u ultra-autotrade-backend -n 200

再起動
Docker：docker compose -f docker-compose.staging.yml restart backend
systemd：systemctl restart ultra-autotrade-backend

問題が解決しない場合は、15_rollback_procedures.md に従いロールバックを検討する。


---

## 4. `Dockerfile`（新規）

```dockerfile
# Ultra AutoTrade Backend 用 Dockerfile
# FastAPI + uvicorn を用いて backend/app/main.py の app を公開する

FROM python:3.11-slim

# システムレベルの依存パッケージ（必要最低限）
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリを project root に設定
WORKDIR /app

# backend ディレクトリのみをコンテナにコピー
# （docs や .git はデプロイに不要なため）
COPY backend ./backend

# Python ライブラリのインストール
# - FastAPI: Web フレームワーク
# - uvicorn[standard]: ASGI サーバ
# - httpx: 非同期 HTTP クライアント（OctoBot 連携など）
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    httpx

# 環境変数
ENV PYTHONUNBUFFERED=1

# アプリケーションポート
EXPOSE 8000

# backend ディレクトリをカレントにして起動
WORKDIR /app/backend

# uvicorn で FastAPI アプリを起動
# app.main:app は backend/app/main.py の app を指す
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

## X.Y 環境ファイルの準備（production）

production 環境では、アプリケーションの設定値・秘密情報を  
サーバ上の `.env.production` で管理する。

### 手順（概要）

1. リポジトリ内の `backend/.env.production.example` を参照し、必要な項目を確認する
2. デプロイ先サーバ上で `.env.production` ファイルを作成する
3. 各項目に本番用の値を設定する
   - Notion / OctoBot / Aave / 通知サービスのキー・URL は、  
     staging 用とは物理的に異なるものを使用する
4. ファイル権限を設定する
   - 所有ユーザ：デプロイユーザ（例：`ultra`）
   - パーミッション：`chmod 600 .env.production`

詳細な項目一覧や設定方針は `docs/21_production_environment_config.md` を参照すること。

## X.Z systemd / Docker と .env.production の扱い

- systemd の unit ファイル（例：`infra/systemd/ultra-autotrade-backend.service`）では、
  必要に応じて以下のいずれかの方式で環境変数を読み込む：

  - `EnvironmentFile=/path/to/.env.production` を指定する
  - または、必要な変数のみ unit ファイル内で `Environment=KEY=VALUE` として定義する

- Docker / docker-compose を利用する場合：

  - staging：`docker-compose.staging.yml` + `.env.staging`
  - production：将来的に `docker-compose.production.yml` + `.env.production` を使用する方針

- どの方式を採用する場合でも、
  `.env.production` 自体は Git にコミットせず、  
  サーバ上でのみ管理すること。

## 5. Production 環境への展開（概要）

本セクションでは、Ultra AutoTrade の **production（本番）環境** へのデプロイ方針をまとめる。

- staging 環境：
  - `docker-compose.staging.yml`
  - （必要に応じて）`infra/systemd/ultra-autotrade-backend.service`
  - `.env.staging`
- production 環境：
  - `docker-compose.production.yml`
  - （必要に応じて）`infra/systemd/ultra-autotrade-backend-production.service`
  - `.env.production`

各環境ごとの設定値については、次を参照すること：

- staging：`docs/17_staging_environment_config.md`
- production：`docs/21_production_environment_config.md`

### 5.1 環境ファイルの準備（production）

production 環境では、アプリケーションの設定値・秘密情報を  
サーバ上の `.env.production` で管理する。

#### 手順（概要）

1. リポジトリ内の `backend/.env.production.example` を参照し、必要な項目を確認する
2. デプロイ先サーバ上の backend ディレクトリ（例：`/opt/ultra-autotrade/backend`）に `.env.production` ファイルを作成する
3. 各項目に **本番用の値** を設定する
   - Notion / OctoBot / Aave / 通知サービスのキー・URL は、staging 用とは物理的に異なるものを使用する
4. ファイル権限を設定する
   - 所有ユーザ：デプロイユーザ（例：`ultra`）
   - パーミッション：`chmod 600 .env.production`

詳細な項目一覧や設定方針は `docs/21_production_environment_config.md` を参照すること。

### 5.2 デプロイスクリプト（production）

production 環境では、次のシェルスクリプトを用意しておくことで、  
デプロイ作業を標準化できる。

- スクリプト: `scripts/deploy_production_backend.sh`
- 想定パス:
  - リポジトリ: `/opt/ultra-autotrade`
  - backend: `/opt/ultra-autotrade/backend`
  - compose: `/opt/ultra-autotrade/docker-compose.production.yml`
  - env: `/opt/ultra-autotrade/backend/.env.production`

スクリプトは次のような流れで処理を行う：

1. Git リポジトリの存在確認 / `git pull --ff-only` による最新化
2. `docker-compose.production.yml` / `.env.production` の存在確認
3. `docker compose -f docker-compose.production.yml build backend`
4. `docker compose -f docker-compose.production.yml up -d backend`
5. `docker compose ... ps backend` による状態確認

環境に合わせてパスを変更した場合は、  
このドキュメントとスクリプト内のコメントも合わせて更新すること。

### 5.3 systemd との連携（production）

Docker を使わず、Linux ホスト上で直接 uvicorn を起動する場合は、  
production 用の systemd unit を用意する。

- ファイル例：`infra/systemd/ultra-autotrade-backend-production.service`
- 主な設定：
  - `WorkingDirectory=/opt/ultra-autotrade/backend`
  - `EnvironmentFile=/opt/ultra-autotrade/backend/.env.production`
  - `ExecStart=/opt/ultra-autotrade/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`

配置と有効化の例：

```bash
sudo cp infra/systemd/ultra-autotrade-backend-production.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ultra-autotrade-backend-production
sudo systemctl start ultra-autotrade-backend-production

staging 用 unit（ultra-autotrade-backend.service）とはファイル名を分け、
.env.staging / .env.production の取り違えを防ぐこと。