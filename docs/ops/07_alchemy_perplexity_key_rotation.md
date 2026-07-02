# Alchemy / Perplexity API キー rotation 影響範囲 & 確認手順

> **このドキュメントの位置付け**
> - 対象: staging (`docker-compose.staging.yml`, `.env.staging`)
> - 目的: 鍵 rotation / revoke 前後に「どこが壊れる可能性があるか」「何を確認すれば復旧確認できるか」を網羅
> - 実際の revoke 操作はオペレーター手動 (Alchemy ダッシュボード / Perplexity ダッシュボード)。本書はあくまで影響範囲一覧 + 確認手順
> - production 反映時は本書を雛形にしつつ、別 PR で同等の手順を起こすこと (Base Mainnet RPC を扱うため別レビュー必須)

最終更新: 2026-05-26

---

## 1. 環境変数マップ

### 1.1 Alchemy (RPC エンドポイントの API key 部分)

| env var | 用途 | ロード経路 | コンシューマ |
|---|---|---|---|
| `ALCHEMY_RPC_URL_BASE_SEPOLIA` | Base Sepolia RPC (staging primary) | `.env.staging` → backend container | `backend/app/aave/chains.py:121` (CHAIN_REGISTRY) |
| `ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA` | Arbitrum Sepolia RPC (staging 副) | `.env.staging` → backend container | `backend/app/aave/chains.py:105` (CHAIN_REGISTRY) |
| `AAVE_RPC_URL` | Aave 単一チェーン RPC (Web3AaveClient 必須) | `.env.staging` → backend | `backend/app/aave/client.py:392/403/988`, `monitor.py:80/133`, `config.py:123` |
| `AAVE_RPC_URL_BASE_SEPOLIA` | Base Sepolia RPC (テストスクリプト向け) | `.env.staging` → backend | `backend/app/aave/chains.py::get_rpc_url_for_chain`, `scripts/aave_*.py` 多数 |
| `AAVE_RPC_URL_SECONDARY` | フェイルオーバー副 RPC | `.env.staging` → backend | `backend/app/aave/config.py:124` |
| `WEB3_RPC_URL` | Oracle / Reserve checker fallback | `.env.staging` → backend | `backend/app/aave/reserve_monitor.py:177`, `oracle_checker.py:208` |
| `AAVE_FLASHBOTS_RPC_URL` | Ethereum Flashbots RPC (本番のみ用途) | `.env.staging` には通常未設定 | `backend/app/aave/client.py:445`, `config.py:146` |
| `NEXT_PUBLIC_BASE_SEPOLIA_RPC` | Frontend wallet 接続 (Base Sepolia) | **build-time** embed (`docker-compose.staging.yml:268`) | `frontend/lib/web3/config.ts:78` |
| `NEXT_PUBLIC_BASE_RPC` | Frontend wallet 接続 (Base Mainnet) | **build-time** embed (`docker-compose.staging.yml:267`) | `frontend/lib/web3/config.ts:83` |
| `NEXT_PUBLIC_ARBITRUM_ONE_RPC` | Frontend wallet 接続 (Arbitrum) | **build-time** embed | `frontend/lib/web3/config.ts:73` |
| `NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC` | Frontend wallet 接続 (Arbitrum Sepolia) | **build-time** embed | `frontend/lib/web3/config.ts` |
| `NEXT_PUBLIC_OPTIMISM_RPC` | Frontend wallet 接続 (Optimism) | **build-time** embed | `frontend/lib/web3/config.ts` |
| `NEXT_PUBLIC_MAINNET_RPC` | Frontend wallet 接続 (Ethereum) | **build-time** embed | `frontend/lib/web3/config.ts` |

> **[CRITICAL] frontend の NEXT_PUBLIC_* は build-time 埋め込み**。
> `.env.staging` を書き換えただけでは反映されず、必ず `docker compose build frontend` で再ビルドが必要。
> backend は `env_file: .env.staging` 経由 runtime 参照のため `up -d --force-recreate` で再読込される。

### 1.2 Perplexity

| env var | 用途 | コンシューマ |
|---|---|---|
| `PERPLEXITY_API_KEY` | Sonar / Sonar Pro 呼出 (全箇所共通) | `backend/app/data_feeds/finance_feed.py:81`, `backend/app/data_feeds/news_feed.py:69`, `backend/app/health/probes.py:109` |

---

## 2. 影響範囲 — Alchemy

### 2.1 Backend (runtime)
- **Aave Web3 client**: `backend/app/aave/client.py`
  - `AAVE_RPC_URL` が無効化されると `Web3AaveClient` 初期化で `AaveClientError` または `ValueError`。supply / withdraw / borrow / repay / HF 取得すべて停止。
- **HF monitor**: `backend/app/aave/monitor.py`
  - `AAVE_RPC_URL` 未設定 → warning ログのみ、HF 取得スキップ (fail-safe)。
- **Oracle / Reserve checker**: `backend/app/aave/oracle_checker.py`, `reserve_monitor.py`
  - `WEB3_RPC_URL` (fallback: `POLYGON_RPC_URL`) 失敗時、`is_oracle_fresh`/`is_reserve_healthy` が例外で fail-closed → `_oracle_fresh=False`/`_reserve_healthy=False` → `/health/detail` に反映 + 取引一時停止判断材料。
- **Chain registry**: `backend/app/aave/chains.py`
  - testnet 2 系 (base_sepolia / arbitrum_sepolia) が Alchemy key 必須。`AAVE_ACTIVE_CHAINS` に testnet が含まれる場合のみ起動時に必要。

### 2.2 Frontend (build-time)
- `frontend/lib/web3/config.ts:73-83` — `process.env.NEXT_PUBLIC_*_RPC` を読み、フォールバックとして public RPC (`https://sepolia.base.org` 等) を使用。
  - **古いキー bundle がブラウザに残る**: revoke 後、ユーザーが古い CDN cache を引いている間は 401 が出る可能性。Cloudflare Pages 経由なら cache purge 推奨。
  - フォールバック public RPC は rate-limit が厳しいため、UAT 中の操作が著しく遅くなる可能性あり。

### 2.3 Scripts (オンデマンド)
- `scripts/aave_faucet_base.py`, `aave_borrow_test.py`, `aave_supply_test.py`, `aave_e2e_base.py`, `bridge_eth_to_base.py`, `e2e_aave_sepolia.py`, `check_deposit_dryrun.py`, `aave_hf_monitor_test.py`, `aave_withdraw_test.py`, `mint_test_usdc.py`, `batch_send_test_usdc.py`, `test_aave_arbitrum_sepolia.py`, `check_sepolia.py`
- 全て手動実行 (cron / scheduler では未起動)。revoke 直後の起動で失敗するのは想定内。

---

## 3. 影響範囲 — Perplexity

### 3.1 Background loops (backend 起動時に常駐)
| ループ | 周期 | 失敗時挙動 |
|---|---|---|
| `health.probes.perplexity_probe_loop` | 15分 | `_perplexity_status.reachable=False, last_error="auth_failed"` を `/health/detail` で表示 |
| `data_feeds.finance_feed.start_finance_background_task` | 60分 (env: `FINANCE_FEED_INTERVAL_MINUTES`) | warning ログ、`_finance_cache` 更新せず |
| `data_feeds.news_feed.start_news_background_task` | 15分 (env: `NEWS_FEED_INTERVAL_MINUTES`) | warning ログ、`_news_cache` 更新せず |

### 3.2 API endpoints (revoke 後に状態確認に使う)
- `GET  /api/data-feeds/finance` — 最後の cache 返却 (revoke 後はキャッシュ TTL 後に default response)
- `POST /api/data-feeds/finance/refresh` — 即時 fetch (401/403 を直接観測可能)
- `GET  /api/data-feeds/news` — 同上
- `POST /api/data-feeds/news/refresh` — 即時 fetch
- `GET  /health/detail` — `components.perplexity.reachable` で probe 状態を返す

### 3.3 AI 判定への波及
- 経路: `data_feeds/context.py::build_market_context` → `MarketContext` → 以下が消費:
  - `backend/app/automation/workflow.py:35`
  - `backend/app/automation/ai_judgment_scheduler.py:30`
  - `backend/app/ai/agents.py:28`
  - `backend/app/ai/service.py:21`
  - `backend/app/data_feeds/router.py:13`
- **fail-open 設計**: key 不在時は default response (`macro_summary="API key not configured."` 等) を返し、AI prompt 組み立てを継続。ただし AI 判定の品質低下 (macro context 欠落) は監視必要。
- staging は `AI_SHADOW_MODE=true` のため、Shadow 判定で `summary="No news data available yet."` 系のログが急増したら revoke の兆候。

---

## 4. Revoke 前チェック (read-only / 約 3 分)

```bash
# 1. 現在のキー一覧 (.env.staging 側) — マスク後 echo
ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142
cd /opt/ultra-autotrade
grep -E "^(PERPLEXITY_API_KEY|ALCHEMY_RPC_URL_|AAVE_RPC_URL|NEXT_PUBLIC_.*_RPC|WEB3_RPC_URL)" .env.staging \
  | sed -E 's/(=.{6}).*$/\1********/'   # 最初の6文字 + マスク

# 2. backend container が読んでいる env を確認
docker exec ultra-autotrade-backend-blue-staging-new \
  env | grep -E "PERPLEXITY|ALCHEMY|AAVE_RPC|WEB3_RPC" \
  | sed -E 's/(=.{6}).*$/\1********/'

# 3. probe の最新状態 (キー失効していないかベースライン取得)
curl -s http://127.0.0.1:8082/health/detail \
  | jq '.components | {openai, perplexity, oracle_fresh, reserve_healthy}'

# 4. data_feeds の最終更新時刻
curl -s http://127.0.0.1:8082/api/data-feeds/finance | jq '.updated_at'
curl -s http://127.0.0.1:8082/api/data-feeds/news    | jq '.updated_at'
```

---

## 5. Revoke 後 動作確認手順

### Step 1 — 新キーを `.env.staging` に投入 (sed -i 禁止)

```bash
# ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142 で staging 用 VPS へ
cd /opt/ultra-autotrade

# バックアップ
cp .env.staging .env.staging.bak.$(date +%Y%m%d_%H%M%S)

# 書換は awk + tmpfile + mv (CLAUDE.md ファイル編集ルール準拠)
awk -v new="PERPLEXITY_API_KEY=pplx-NEW" \
  'BEGIN{FS=OFS="="} /^PERPLEXITY_API_KEY=/{print new; next} {print}' \
  .env.staging > /tmp/env.new && mv /tmp/env.new .env.staging

# Alchemy 系も同様に書き換え (ALCHEMY_RPC_URL_BASE_SEPOLIA / AAVE_RPC_URL / 各 NEXT_PUBLIC_*_RPC)
```

### Step 2 — backend 再起動 (env_file 再読込)

```bash
docker compose -f docker-compose.staging.yml up -d --no-deps --force-recreate backend-blue
# 起動完了待ち (15-30秒)
docker logs --tail 50 -f ultra-autotrade-backend-blue-staging-new
# Ctrl+C で抜ける
```

### Step 3 — frontend 再ビルド (NEXT_PUBLIC_* は build-time)

```bash
# build args として .env.staging から拾うので --no-cache 推奨
docker compose -f docker-compose.staging.yml build --no-cache frontend
docker compose -f docker-compose.staging.yml up -d --no-deps frontend
```

### Step 4 — Perplexity probe 確認 (5 分以内に reachable=true 化)

```bash
# 5 分待つ (probe 1サイクル) → 再確認
sleep 60
curl -s http://127.0.0.1:8082/health/detail | jq '.components.perplexity'
# expect: {"reachable": true, "last_check": "...", "last_error": null}

# 即時確認したい場合は refresh endpoint
curl -s -X POST http://127.0.0.1:8082/api/data-feeds/finance/refresh | jq '.updated_at, .macro_summary' | head
curl -s -X POST http://127.0.0.1:8082/api/data-feeds/news/refresh    | jq '.updated_at, .summary'      | head
```

### Step 5 — Alchemy RPC 接続確認 (chain_id / block_number で生存確認)

```bash
docker exec ultra-autotrade-backend-blue-staging-new python -c "
import os
from web3 import Web3
# staging は Base Sepolia
url = os.environ.get('ALCHEMY_RPC_URL_BASE_SEPOLIA') or os.environ.get('AAVE_RPC_URL_BASE_SEPOLIA') or os.environ.get('AAVE_RPC_URL')
assert url, 'no RPC URL env set'
w3 = Web3(Web3.HTTPProvider(url))
print('connected:', w3.is_connected())
print('chain_id :', w3.eth.chain_id)
print('block_num:', w3.eth.block_number)
"
# expect: connected=True, chain_id=84532 (Base Sepolia), block_num>0
```

### Step 6 — HF / Aave monitor が再開しているか

```bash
docker logs --since 5m ultra-autotrade-backend-blue-staging-new 2>&1 \
  | grep -iE "monitor|health.factor|AAVE_RPC|alchemy" \
  | grep -viE "skipping|not set"
# expect: HF 値が定期出力 / "skipping" が出ていない
```

### Step 7 — AI judgment loop が context を受け取っているか

```bash
docker logs --since 15m ultra-autotrade-backend-blue-staging-new 2>&1 \
  | grep -iE "finance_feed|news_feed|build_market_context|MarketContext"
# expect: cache 更新ログがある / "API key not configured" / "auth_failed" が出ていない
```

### Step 8 — Frontend wallet 接続確認 (ブラウザ手動)

1. staging URL (https://staging.ultra-auto-trade.com) を開く
2. ブラウザ devtools Network タブで `*.alchemy.com` への request を確認
3. wallet 接続 → Base Sepolia 切替 → block number 表示で生存確認
4. Cloudflare Pages cache を疑う場合は `?cb=$(date +%s)` で cache bust

### Step 9 — 旧キー無効化の最終確認

- Alchemy ダッシュボードで旧 key の status = `revoked`
- Perplexity ダッシュボードで旧 key の status = `disabled`
- 15 分待ち、`/health/detail.components.perplexity.last_error` が `null` のまま、かつ過去 1 時間で `auth_failed` ログが出ていないこと

```bash
docker logs --since 1h ultra-autotrade-backend-blue-staging-new 2>&1 \
  | grep -iE "auth_failed|401|403" | head -20
# expect: 出力 0 行 (revoke 直前直後の数件は許容)
```

---

## 6. ロールバック手順 (新キーで 401/403 発生時)

```bash
# 1. .env.staging を直前バックアップから復元
cd /opt/ultra-autotrade
LATEST_BAK=$(ls -t .env.staging.bak.* | head -1)
cp "$LATEST_BAK" .env.staging

# 2. backend 即時再起動
docker compose -f docker-compose.staging.yml up -d --no-deps --force-recreate backend-blue

# 3. frontend は build-time のため、旧 image に rollback
# 直前イメージ tag を確認
docker images | grep frontend-staging-new | head -5
# 旧 tag に手動で書き戻す or `docker compose -f docker-compose.staging.yml up -d --no-deps frontend` で
# キャッシュ層の旧 build を再採用 (build はしない)
```

> ロールバックする場合、Alchemy / Perplexity 側でも旧キーの revoke を一時取り消す必要あり。
> Perplexity は revoke = 即時無効化のため復活不可 → 別の新キー発行で再投入。

---

## 7. 既知の落とし穴 (CLAUDE.lessons.md 由来)

- **`sed -i` で `.env.staging` を編集すると前行連結バグ** (2026-04-01 教訓)。awk + tmpfile + mv または printf を使う。
- **`docker compose restart` だけでは env が反映されない**ことがある (2026-04-01 教訓)。`up -d --no-deps --force-recreate <service>` を使う。
- **frontend NEXT_PUBLIC_* は build-time 埋め込み** → restart だけでは反映されない。必ず `build --no-cache frontend` 経由。
- **`AAVE_RPC_URL` と `ALCHEMY_RPC_URL_BASE_SEPOLIA` の二重定義**: chain registry は後者を見るが、`Web3AaveClient` は前者を必須とする (`client.py:392/403/988`)。staging では両方 `.env.staging` に投入が必要。
- **fail-open / cache フォールバック**: data_feeds は key 失効後しばらく古いキャッシュで動作するため「壊れた」と気付きにくい。必ず Step 4-7 を実行して active 確認すること。
- **古い frontend bundle のブラウザキャッシュ**: revoke から数時間は古いキーが含まれた JS が配信される可能性。Cloudflare cache purge + ハードリロード周知が必要。
- **`AAVE_RPC_URL_SECONDARY` が同じプロバイダ**: primary と secondary が同じ Alchemy アカウントなら、両方 revoke 対象。別プロバイダで二重化されているか確認。

---

## 8. Production への展開 (参考、本書では対象外)

production 側の env var は以下に対応 (Base Mainnet):

| staging env var | production env var |
|---|---|
| `ALCHEMY_RPC_URL_BASE_SEPOLIA` | `AAVE_RPC_URL_BASE` |
| `AAVE_RPC_URL` (Base Sepolia 指す) | `AAVE_RPC_URL` (Base Mainnet 指す) |
| `NEXT_PUBLIC_BASE_SEPOLIA_RPC` | `NEXT_PUBLIC_BASE_RPC` |

production 反映は別 PR で:
- `docker-compose.production.yml` + `.env.production`
- container 名: `*-production` suffix (`ultra-autotrade-backend-blue-production` 等)
- 実資金トレード稼働中のため、メンテナンスウィンドウ + Slack 周知必須
- 本ドキュメントの Step 1-9 を `production` 用に置換した上で別途レビュー (CLAUDE.md §[CRITICAL] Definition of Done 準拠)

---

## 参照

- `CLAUDE.md` (Security Rules / 環境定義)
- `CLAUDE.lessons.md` 2026-04-01 (env 改行 / restart vs up -d)
- `docs/ops/03_deploy_procedures.md`
- `docs/13_security_design.md`
- `backend/app/aave/chains.py` / `client.py` / `monitor.py`
- `backend/app/data_feeds/finance_feed.py` / `news_feed.py`
- `backend/app/health/probes.py`
- `frontend/lib/web3/config.ts`
