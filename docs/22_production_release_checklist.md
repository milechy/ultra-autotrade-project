# 22_production_release_checklist.md
Ultra AutoTrade – Production リリース前チェックリスト

> 最終更新: 2026-04-17  
> 2026-04-17: B案リネームに伴いデプロイスクリプト・composeファイル名を更新。

### 環境とスクリプトの対応（2026-04-17以降）
| 環境 | compose | env | deploy script |
|------|---------|-----|---------------|
| production | `docker-compose.production.yml` | `.env.production` | `scripts/deploy_production.sh` |
| staging | `docker-compose.staging.yml` | `.env.staging` | `scripts/deploy_staging.sh` |

---

## 0. 前提条件

- [ ] `20_staging_release_checklist.md` の全項目が完了している
- [ ] `14_test_strategy.md` に沿ったテストが実施され、staging で一定期間安定稼働している
- [ ] ロールバック手順（`15_rollback_procedures.md`）をリリース担当者が確認済み
- [ ] 関係者（PO / インフラ担当）にリリース日時を共有済み

---

## 1. 事前準備（法人・クラウド・ドメイン）

### 法人設立（将来対応 — 現在の実運用はブロックしない）
- [ ] 法人登記完了（BVI / シンガポール / 国内法人 選択済み）— **将来対応**
- [ ] 法人口座開設（Bybit / OKX 法人アカウント紐付け）— **将来対応**
- [ ] AML/KYC 書類提出・承認済み — **将来対応**

### 秘密鍵管理（現状: .env.production + chmod 600 で代替運用中）
- [x] `.env.production` のパーミッションが `chmod 600`（root 専用）✅
- [ ] AWS KMS / HashiCorp Vault 移行 — **将来対応**（スケール拡大時）
- [ ] AWS Secrets Manager への秘密鍵登録 — **将来対応**

### ドメイン・DNS
- [x] 本番サブドメイン設定済み ✅
  - API: `api.ultra-auto-trade.com`
  - Frontend: `app.ultra-auto-trade.com`
- [x] Cloudflare DNS レコード設定済み（CNAME → Named Tunnel）✅
- [x] SSL 証明書が有効（Cloudflare 自動発行）✅

---

## 2. インフラ（Docker / Tunnel / SSL）

### docker-compose.production.yml
- [x] `docker-compose.production.yml` が本番設定で作成済み（`restart: always`, Loki logging）✅
- [ ] イメージタグが `latest` ではなく SHA256 ダイジェスト or 固定バージョンタグ
- [x] PostgreSQL データボリュームが名前付きボリュームで永続化されている ✅
- [ ] バックエンドコンテナのメモリ上限が設定されている（例: `memory: 2g`）

### Cloudflare Tunnel（Named Tunnel）
- [x] Named Tunnel 移行済み（`api.ultra-auto-trade.com` / `app.ultra-auto-trade.com`）✅
  - Quick Tunnel は廃止済み（`trycloudflare.com` は使用しない）
- [x] Cloudflare ダッシュボードで Ingress ルール設定済み ✅
- [x] `network_mode: host` で localhost アクセス確認済み ✅
- [x] Tunnel 経由で `https://api.ultra-auto-trade.com/health` → 200 確認済み ✅
- [x] API ドキュメント（/docs）は `APP_ENV=production` で無効化済み ✅

### ネットワーク
- [x] バックエンドポート (8000) は `127.0.0.1:8000` バインド（外部公開しない）✅
- [x] フロントエンドポート (3000) は `127.0.0.1:3000` バインド ✅
- [x] Cloudflare Tunnel のみが外部アクセス経路 ✅
- [x] UFW で不要なポートを閉鎖済み（22/SSH のみ公開）✅

---

## 3. セキュリティ（ABSOLUTE Rules 準拠）

### 秘密鍵管理（現状: chmod 600 運用）
- [x] `.env.production` を `chmod 600` + root 専用で保護済み ✅
- [x] `.env.staging` と `.env.production` で **物理的に異なる** ウォレットアドレスを使用 ✅
- [x] 本番ウォレット秘密鍵を staging 環境のログ・モニタリングに露出していないことを確認 ✅
- [ ] AWS KMS / HashiCorp Vault 移行 — **将来対応**（スケール拡大時）

### Gnosis Safe（マルチシグ）— 将来対応
- [ ] 本番ウォレットに Gnosis Safe マルチシグを設定（2-of-3 以上推奨）— **将来対応**
- [ ] 初期資金は Gnosis Safe → hot wallet に最小限のみ移動するフローを確立 — **将来対応**

### Security Rules 再確認（全完了 — P0孤立コード0件確認済み 2026-04-06）
- [x] HF < 1.6 → HARD_STOP（`slippage_guard.py` + `rebalance_service.py`）✅
- [x] Max single trade: 総資産の10%（`exchange/service.py`）✅
- [x] Max daily trades: 総資産の30%（`exchange/service.py` commit `df5f41a`）✅
- [x] Cooldown: Aave 操作間10分（`aave/state_manager.py`）✅
- [x] Emergency stop フラグ: OR ロジック（手動停止は上書き不可）✅
- [x] LLM 出力は JSON Schema バリデーション必須（parse failure → HOLD）✅
- [x] 金額計算: Decimal 型のみ（float 禁止）✅
- [x] oracle_checker / reserve_monitor / stress_controller — workflow.py に配線確認済み ✅

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

### マイグレーション（手動方式）
- [x] alembic は未インストール。手動 `ALTER TABLE` 方式で運用 ✅
- [ ] 新カラム追加が必要な場合はバックアップ取得後に手動実行:
  ```bash
  docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
    "ALTER TABLE <table> ADD COLUMN IF NOT EXISTS <column> <type>;"
  ```

### ヘルスチェック
- [ ] `GET /health` が 200 を返すことを確認
- [ ] `GET /exchange/status` が接続中 (`connected: true`) を返すことを確認
- [ ] `GET /aave/status` が HF > 1.6 を返すことを確認

---

## 5. フロントエンド（Hetzner Docker内でビルド・配信）

> **注意:** フロントエンドは Cloudflare Pages ではなく Hetzner 上の Docker コンテナで稼働中。
> `docker-compose.production.yml` の `build.args` に NEXT_PUBLIC_* 変数を設定してビルドする。

### 環境変数（docker-compose.production.yml build.args）
- [x] `NEXT_PUBLIC_BACKEND_BASE_URL` = `https://api.ultra-auto-trade.com` ✅
- [x] `NEXT_PUBLIC_API_BASE_URL` = `https://api.ultra-auto-trade.com` ✅
- [x] `NEXT_PUBLIC_API_URL` = `https://api.ultra-auto-trade.com` ✅
- [x] `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID` 設定済み ✅
- [ ] `NEXT_PUBLIC_DEFAULT_CHAIN_ID` = 本番チェーン ID（8453 or 42161）
- [ ] RPC URL 群（`NEXT_PUBLIC_*_RPC`）設定済み

### ビルド確認
- [x] `npm run build` がエラーなく完了する ✅（verify.sh で確認済み）
- [x] `npx tsc --noEmit` が型エラー 0 ✅（verify.sh で確認済み）
- [ ] 本番ビルド後: `docker exec <frontend> grep -r "http://77" /app/.next/static/chunks/ | wc -l` → 0件確認

### アクセス確認
- [x] `https://app.ultra-auto-trade.com/login` → 200 ✅
- [x] `https://app.ultra-auto-trade.com/user/dashboard` → 200 ✅
- [ ] 管理者画面でCSPエラーが出ないことをブラウザ DevTools で確認
- [ ] モバイル（iPhone）での Mixed Content エラーがないことを確認

---

## 6. AI / 自動化

### スケジューラー
- [x] AIスケジューラーが 4時間間隔で正常稼働中 ✅
  - `scheduler_healthy: true` / `warnings: []` 確認済み（2026-04-06）
  - `last_judgment: 2026-04-05T23:41:32 UTC`
- [x] `DISABLE_AI_JUDGMENT_SCHEDULER` 未設定（デフォルト有効）✅

### LLM API
- [x] Claude Sonnet 4.6 API キーが本番用 ✅
- [x] GPT-4o API キーが本番用（Phase B クロス判定用）✅
- [ ] Perplexity API（使用する場合）の課金プラン確認済み

### GDELT / ニュース取得
- [x] GDELT ニュースソースへのアクセスが本番環境から可能 ✅（空レスポンス時の graceful handling 実装済み）
- [x] Knowledge Hub（PostgreSQL + pgvector）の本番 DB 初期化済み ✅

---

## 7. Aave（本番チェーン移行）

### コントラクト確認
- [x] 本番チェーンの Aave V3 Pool アドレスが `backend/app/aave/chains.py` に設定済み ✅
  - Base: `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`
  - Arbitrum: `0x794a61358D6845594F94dc1DB02A252b5b4814aD`
- [ ] USDC / USDT などのトークンアドレスが本番チェーン用に設定済み（`.env.production` で確認）

### HF 監視
- [ ] HF 監視が本番チェーンを対象としている（`AAVE_NETWORK` 設定確認）
- [ ] HF < 1.6 アラートが Slack 本番チャネルに飛ぶことを確認

### 安全機能（実装・配線確認済み 2026-04-06）
- [x] ガス代動的見積もり: `aave/gas_estimator.py` ✅
- [x] RPCフェイルオーバー: `aave/rpc_provider.py` ✅
- [x] スリッページ保護: `aave/slippage_guard.py` ✅
- [x] 日次取引上限30%: `exchange/service.py` ✅
- [x] oracle_checker: `workflow.py` から `is_oracle_fresh()` 経由で呼び出し済み ✅
- [x] reserve_monitor: `workflow.py` から `is_reserve_healthy()` 経由で呼び出し済み ✅
- [x] stress_controller: `workflow.py:425` から呼び出し済み ✅

### Aave 本番運用開始前テスト
- [ ] パートナーが **少額（$100 USDC）** でデポジット → ウィズドロー 1サイクルを `/user/approve` 画面から実施
- [ ] トランザクションハッシュと HF の変化を記録
- [ ] 緊急停止ボタン → resume フローをパートナーが確認

---

## 8. デプロイ手順

> ⚠️ **重要:** Hetzner上での直接的な `git merge` / `git commit` / ファイル編集は禁止。
> 正規フロー: ローカルMac → `git push origin main` → Hetzner `git pull origin main`。
> Hetznerには GitHub push 手段（SSH key / PAT）が設定されていないため、
> Hetzner上でコミットすると同期不能になる。

```bash
# 1. ローカルMacで main ブランチを最新に同期
git checkout main && git pull origin main
git push origin main  # GitHub に push

# 2. Hetzner でコードを pull（Hetzner は pull only — 直接コミット禁止）
ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14
cd /opt/ultra-autotrade
git pull origin main  # ← pull のみ。git commit / merge / nano 編集は禁止

# 3. バックエンドのみ再起動（コード変更の場合）
docker compose -f docker-compose.production.yml up -d --no-deps --build backend

# 4. フロントエンドを再ビルド（NEXT_PUBLIC_* 変数変更時のみ）
docker compose -f docker-compose.production.yml build --no-cache frontend
docker compose -f docker-compose.production.yml up -d --no-deps frontend

# 5. DB マイグレーション（手動方式）
# ⚠️ alembic は使用しない（未インストール、exit code 127 の原因）
# 新しいカラムが必要な場合は手動で ALTER TABLE を実行:
# docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
#   "ALTER TABLE <table> ADD COLUMN IF NOT EXISTS <column> <type>;"

# 6. ヘルスチェック
curl https://api.ultra-auto-trade.com/health
# 期待値: {"status": "ok", "scheduler_healthy": true, "warnings": []}
```

### ALLOW_TESTNET bypass（partner 先行検証フェーズ専用）

`scripts/deploy_production.sh` の Guard 1 は `.env.production` で `AAVE_NETWORK=*sepolia*` を検出すると abort する（mainnet 強制）。
partner 先行検証フェーズ等で意図的に testnet 運用する場合のみ、`ALLOW_TESTNET=1` を環境変数で指定して bypass 可能：
```bash
ALLOW_TESTNET=1 bash scripts/deploy_production.sh
```
mainnet 移行後は `ALLOW_TESTNET` 環境変数を外して通常運用に戻すこと。Guard 2-4（環境分離・compose 確認・健全性検証）は変更されない。

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

## 11. 状態サマリー（2026-04-06 現在）

### 完了済み（実運用中）
| 項目 | 状態 | 備考 |
|------|------|------|
| Cloudflare Named Tunnel | ✅ 完了 | api/app.ultra-auto-trade.com 稼働中 |
| docker-compose.production.yml | ✅ 完了 | 全コンテナ稼働中（healthy）|
| 127.0.0.1バインド + Tunnel経由のみ公開 | ✅ 完了 | 直IP接続拒否確認済み |
| AIスケジューラー | ✅ 稼働中 | 4時間間隔、scheduler_healthy: true |
| Security Rules（安全装置配線） | ✅ 完了 | P0孤立コード0件確認済み |
| PostgreSQL + pgvector | ✅ 稼働中 | healthy |
| .env.production chmod 600 | ✅ 完了 | 秘密鍵保護済み |
| フロントエンドビルド（Mixed Content解消） | ✅ 完了 | NEXT_PUBLIC_* 14変数全設定済み |

### 将来対応（現在の実運用をブロックしない）
| 項目 | 優先度 | 担当 |
|------|--------|------|
| AWS KMS / HashiCorp Vault 移行 | 低（スケール拡大時）| インフラ担当 |
| 法人設立・AML/KYC | 低（資金規模拡大時）| PO |
| Gnosis Safe マルチシグ | 低（資金規模拡大時）| PO |
| 有料 RPC プラン契約 | 中（Aave 実運用本格化時）| インフラ担当（`docs/30_rpc_plan_requirements.md`）|
| UtilizationMonitor 配線（P1孤立）| 中（今週中）| エンジニア |

---

## 12. パートナー実運用開始手順

パートナーが実資金で運用を開始する際の手順:

1. **パートナー用アカウント作成**（admin or editor ロール）
   - 管理者が `/admin/settings/users` からアカウントを作成
2. **パートナーにログイン情報を共有**（Slack DM）
3. **パートナーがMetaMaskウォレット接続**（`/user/connect`）
   - Arbitrum One または Base ネットワークを選択
4. **パートナーがウォレットにUSDC + ガス代ETH入金**
5. **環境変数の確認・変更（バックエンドのみ）**
   ```bash
   # Hetzner上で .env.production を確認
   grep -E "EXCHANGE_CLIENT_TYPE|AI_SHADOW_MODE|REBALANCE_SHADOW_MODE" /opt/ultra-autotrade/.env.production
   # → AI_SHADOW_MODE=false, REBALANCE_SHADOW_MODE=false であること
   ```
6. **バックエンド再起動**（環境変数変更時のみ）
   ```bash
   docker compose -f docker-compose.production.yml up -d --no-deps backend
   ```
   > フロントエンド再ビルド不要（バックエンド環境変数のみの変更）
7. **少額E2Eテスト**: パートナーが `$100 USDC` deposit → withdraw を `/user/approve` 画面から実施
   - トランザクションハッシュと HF の変化を記録
8. **緊急停止テスト**: パートナーが緊急停止ボタン → resume を確認
9. **2時間監視**: `/health` の `scheduler_healthy` + Slack `#ultra-auto-project` アラートを確認
   ```bash
   curl https://api.ultra-auto-trade.com/health | python3 -m json.tool
   # 期待値: {"status": "ok", "scheduler_healthy": true, "warnings": []}
   ```
10. **Aave HF 確認**: `GET /aave/status` で HF > 1.6 を確認
11. **運用開始**: Slack に運用開始通知を送信
