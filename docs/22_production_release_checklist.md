# 22_production_release_checklist.md
Ultra AutoTrade – Production リリース前チェックリスト

> 最終更新: 2026-03-31  
> 本ドキュメントは現在の実装状態（2026-03-31時点）を反映している。

---

## 0. 前提条件

- [ ] `20_staging_release_checklist.md` の全項目が完了している
- [ ] `14_test_strategy.md` に沿ったテストが実施され、staging で一定期間安定稼働している
- [ ] ロールバック手順（`15_rollback_procedures.md`）をリリース担当者が確認済み
- [ ] 関係者（PO / インフラ担当）にリリース日時を共有済み

---

## 1. 事前準備（法人・クラウド・ドメイン）

### 法人設立
- [ ] 法人登記完了（BVI / シンガポール / 国内法人 選択済み）
- [ ] 法人口座開設（Bybit / OKX 法人アカウント紐付け）
- [ ] AML/KYC 書類提出・承認済み

### AWS / クラウドアカウント
- [ ] AWS KMS キーを本番用に作成（キーポリシー: バックエンドサービスロールのみ許可）
- [ ] AWS Secrets Manager に秘密鍵を登録（`/ultra-autotrade/prod/` プレフィックス）
- [ ] IAM ロール（EC2 or ECS 用）に KMS DecryptOnly 権限のみ付与

### ドメイン・DNS
- [ ] `ultra-autotrade.com`（または選定ドメイン）の本番サブドメイン設定済み
  - API: `api.ultra-autotrade.com`
  - Frontend: `app.ultra-autotrade.com`
- [ ] Cloudflare DNS レコード設定済み（CNAME → Cloudflare Tunnel）
- [ ] SSL 証明書が有効（Cloudflare 自動発行 or Let's Encrypt）

---

## 2. インフラ（Docker / Tunnel / SSL）

### docker-compose.production.yml
- [ ] `docker-compose.production.yml` が本番設定で作成済み（`restart: always`, `logging` 等）
- [ ] イメージタグが `latest` ではなく SHA256 ダイジェスト or 固定バージョンタグ
- [ ] PostgreSQL データボリュームが名前付きボリューム（`pgdata_prod`）で永続化されている
- [ ] バックエンドコンテナのメモリ上限が設定されている（例: `memory: 2g`）

### Cloudflare Tunnel（Named Tunnel）
- [ ] Quick Tunnel（`trycloudflare.com`）から **Named Tunnel** に移行済み
  - Quick Tunnel はセッションごとにURLが変わるため本番不可
  - `cloudflared tunnel create ultra-autotrade-prod` で固定 UUID 取得
- [ ] `~/.cloudflared/config.yml` に本番設定を記載
- [ ] `systemd` サービスとして自動起動設定済み
- [ ] Tunnel 経由で `https://api.ultra-autotrade.com/docs` にアクセス確認済み

### ネットワーク
- [ ] バックエンドポート (8000) はローカルホストのみバインド（外部公開しない）
- [ ] Cloudflare Tunnel のみが外部アクセス経路
- [ ] UFW / iptables で不要なポートを閉鎖済み

---

## 3. セキュリティ（ABSOLUTE Rules 準拠）

### 秘密鍵管理
- [ ] **本番秘密鍵は AWS KMS / HashiCorp Vault に移行済み**（ファイル直置き禁止）
  - 未実施の場合は `.env.production` を `chmod 600` + root 専用 + バックアップ暗号化で代替
- [ ] `.env.staging` と `.env.production` で **物理的に異なる** ウォレットアドレスを使用
- [ ] 本番ウォレット秘密鍵を staging 環境のログ・モニタリングシステムに露出していないことを確認

### Gnosis Safe（マルチシグ）
- [ ] 本番ウォレットに Gnosis Safe マルチシグを設定（2-of-3 以上推奨）
- [ ] 初期資金は Gnosis Safe → hot wallet に最小限のみ移動するフローを確立

### Security Rules 再確認
- [ ] HF < 1.6 → HARD_STOP（`backend/app/aave/slippage_guard.py` + `rebalance_service.py`）
- [ ] Max single trade: 総資産の10%（`exchange/service.py`）
- [ ] Max daily trades: 総資産の30%（`exchange/service.py` + 実装済み: `df5f41a`）
- [ ] Cooldown: Aave 操作間10分（`aave/state_manager.py`）
- [ ] Emergency stop フラグ: OR ロジック（手動停止は上書き不可）
- [ ] LLM 出力は JSON Schema バリデーション必須（parse failure → HOLD）
- [ ] 金額計算: Decimal 型のみ（float 禁止）

---

## 4. バックエンド

### 環境変数（.env.production）
- [ ] `.env.production` のパーミッションが `600`
- [ ] `APP_ENV=production` 設定済み
- [ ] `CHAIN_ID` が本番チェーン ID に設定済み
  - staging: Base Sepolia (84532)
  - **production: Base (8453) または Arbitrum One (42161)**
- [ ] RPC URL が有料プランのエンドポイント（`docs/30_rpc_plan_requirements.md` 参照）
  - Alchemy / Infura / Chainstack の本番プラン URL
  - フェイルオーバー用のセカンダリ RPC も設定（`AAVE_RPC_URL_FALLBACK`）
- [ ] `BYBIT_API_KEY` / `BYBIT_API_SECRET` が本番 API キー（sandbox=False）
- [ ] `PRIVATE_KEY` が本番ウォレット秘密鍵（staging と完全に異なること）
- [ ] `SLACK_WEBHOOK_URL` が本番チャネル向け URL

### マイグレーション
- [ ] `alembic upgrade head` 実行済み（本番 DB）
- [ ] マイグレーション前にバックアップ取得済み

### ヘルスチェック
- [ ] `GET /health` が 200 を返すことを確認
- [ ] `GET /exchange/status` が接続中 (`connected: true`) を返すことを確認
- [ ] `GET /aave/status` が HF > 1.6 を返すことを確認

---

## 5. フロントエンド（Cloudflare Pages）

### 環境変数（Cloudflare Pages ダッシュボードで設定）
- [ ] `NEXT_PUBLIC_BACKEND_BASE_URL` = `https://api.ultra-autotrade.com`
  - **ビルド時に設定必須**（CSP `connect-src` にバックエンド URL が含まれるため）
  - 未設定だと管理者画面から `/exchange/status` 等のAPI呼び出しが失敗する
- [ ] `BACKEND_BASE_URL` = バックエンド内部 URL（Tunnel 経由または VPC 内部）
  - Next.js API Route プロキシが使用するサーバーサイド変数
- [ ] `NEXT_PUBLIC_CHAIN_ID` = 本番チェーン ID（8453 or 42161）
- [ ] `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID` = 本番 WalletConnect Project ID

### チェーン設定
- [ ] フロントエンドのチェーン設定が本番チェーンを含んでいる
  - staging: Base Sepolia (84532) のみ
  - **production: Base (8453) + Arbitrum One (42161) + Ethereum Mainnet (1)**
- [ ] testnet チェーン（Base Sepolia 等）が本番ビルドに残っていないことを確認

### ビルド確認
- [ ] `npm run build` がエラーなく完了する
- [ ] `npx tsc --noEmit` が型エラー 0
- [ ] Cloudflare Pages ビルドログにエラーなし

### CSP 確認（重要）
- [ ] `NEXT_PUBLIC_BACKEND_BASE_URL` をビルド時に設定したことで、
      `connect-src` にバックエンド URL が含まれていることをブラウザ DevTools で確認
- [ ] 管理者画面 (`/admin/exchange`, `/admin/settings/system`) で CSP エラーが出ないことを確認
- [ ] 管理者ダッシュボード (`/admin/dashboard`) で `/exchange/status` が正常取得できることを確認

---

## 6. AI / 自動化

### スケジューラー
- [ ] `POST /automation/process-news` スケジューラーが 4時間間隔で設定済み
- [ ] スケジューラーが staging で正常稼働実績あり（ログ確認）

### LLM API
- [ ] Claude Sonnet 4.6 API キーが本番用（レート制限を確認）
- [ ] GPT-4o API キーが本番用（Phase B クロス判定用）
- [ ] Perplexity API（使用する場合）の課金プラン確認済み

### GDELT / ニュース取得
- [ ] GDELT 等のニュースソースへのアクセスが本番環境から可能なことを確認
- [ ] Knowledge Hub（PostgreSQL + pgvector）の本番 DB が初期化済み

---

## 7. Aave（本番チェーン移行）

### コントラクト確認
- [ ] 本番チェーンの Aave V3 Pool アドレスが正しく設定済み（`backend/app/aave/chains.py`）
  - Base: `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`
  - Arbitrum: `0x794a61358D6845594F94dc1DB02A252b5b4814aD`
- [ ] USDC / USDT などのトークンアドレスが本番チェーン用に設定済み

### HF 監視
- [ ] HF 監視が本番チェーンを対象としている
- [ ] HF < 1.6 アラートが Slack 本番チャネルに飛ぶことを確認

### 安全機能（実装済みの確認）
- [ ] ガス代動的見積もり: `backend/app/aave/gas_estimator.py` ✅（実装済み）
- [ ] RPCフェイルオーバー: `backend/app/aave/rpc_provider.py` ✅（実装済み）
  - `docs/30_rpc_plan_requirements.md` のフェイルオーバー設定を本番 `.env` に反映
- [ ] スリッページ保護: `backend/app/aave/slippage_guard.py` ✅（実装済み）
- [ ] 日次取引上限30%: `backend/app/exchange/service.py` ✅（実装済み: commit `df5f41a`）

### Aave 本番運用開始前テスト
- [ ] Mainnet にデプロイ後、**少額（$100 相当）** でデポジット → ウィズドロー 1サイクルを手動実行
- [ ] トランザクションハッシュと HF の変化を記録
- [ ] 緊急停止 (`POST /automation/emergency-stop`) → 再開 (`POST /automation/emergency-stop/resume`) フローを確認

---

## 8. デプロイ手順

> ⚠️ **重要:** Hetzner上での直接的な `git merge` / `git commit` / ファイル編集は禁止。
> 正規フロー: ローカルMac → `git push origin main` → Hetzner `git pull origin main`。
> Hetznerには GitHub push 手段（SSH key / PAT）が設定されていないため、
> Hetzner上でコミットすると同期不能になる。

```bash
# 1. main ブランチを最新に同期
git checkout main && git pull origin main

# 2. 本番サーバーで docker-compose.production.yml を使用してデプロイ
ssh prod-server
cd /opt/ultra-autotrade
git pull origin main
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d

# 3. DB マイグレーション（手動方式）
# ⚠️ alembic は使用しない（未インストール、exit code 127 の原因）
# 新しいカラムが必要な場合は手動で ALTER TABLE を実行:
# docker exec <postgres-container> psql -U ultra -d ultra_autotrade -c \
#   "ALTER TABLE <table> ADD COLUMN IF NOT EXISTS <column> <type>;"

# 4. ヘルスチェック
curl https://api.ultra-autotrade.com/health

# 5. Cloudflare Pages に frontend をデプロイ
# (Cloudflare Pages は main ブランチへのプッシュで自動デプロイ)
```

---

## 9. ポストデプロイ確認

- [ ] `GET https://api.ultra-autotrade.com/health` → 200
- [ ] `GET https://api.ultra-autotrade.com/exchange/status` → `connected: true`
- [ ] 管理者画面にログインできる
- [ ] 管理者ダッシュボードで取引状況・HF が表示される
- [ ] Slack 本番チャネルにデプロイ完了通知が届いている
- [ ] リリース後 1〜2 時間、ログとアラートを継続監視
- [ ] 不審なトレード・シグナルがないことを確認

---

## 10. ロールバック手順

問題発生時:

```bash
# 前バージョンのイメージに戻す
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d --scale backend=0
# イメージタグを前バージョンに変更して再起動

# または git revert
git revert HEAD && git push origin main
```

詳細: `docs/15_rollback_procedures.md` 参照

---

## 11. 未完了・前提条件（本番移行ブロッカー）

以下は本番移行の前に完了が必要な項目:

| 項目 | 状態 | 担当 |
|------|------|------|
| AWS KMS / HashiCorp Vault 移行 | ❌ 未実施 | インフラ担当 |
| Cloudflare Named Tunnel 設定 | ❌ Quick Tunnel から移行必要 | インフラ担当 |
| 法人設立・AML/KYC | ❌ 未実施 | PO |
| Gnosis Safe マルチシグ設定 | ❌ 未実施 | PO |
| 有料 RPC プラン契約 | ❌ 未実施（`docs/30_rpc_plan_requirements.md` 参照） | インフラ担当 |
| docker-compose.production.yml 最終確認 | ⏳ Agent A が作成中 | |
