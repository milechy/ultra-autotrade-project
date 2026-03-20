# Staging 手動デプロイ手順書

対象: VPS operator による Hetzner VPS への手動デプロイ
ブランチ: `dev`
Compose ファイル: `docker-compose.staging.yml`

---

## 0. 前提確認

```bash
# ローカルで確認
git log origin/dev -3 --oneline   # デプロイしたいコミットを確認
```

---

## 1. SSH 接続

```bash
ssh root@77.42.46.155
# または ~/.ssh/config にエイリアスを設定している場合
ssh hetzner-staging
```

接続後、作業ディレクトリへ移動:

```bash
cd /opt/ultra-autotrade
```

---

## 2. .env.staging の更新確認

デプロイ前に環境変数ファイルを確認・更新する。

```bash
nano /opt/ultra-autotrade/.env.staging
# または
vi /opt/ultra-autotrade/.env.staging
```

### 2-1. 要設定（空欄のもの）

以下は現在 `.env.staging` で未設定。用途に応じて値を入れること。

| 変数名 | 要設定理由 |
|--------|-----------|
| `SLACK_WEBHOOK_URL` | Slack 通知を使う場合。不要なら空欄のままで可 |
| `BITFLYER_API_KEY` | `EXCHANGE_CLIENT_TYPE=bitflyer` 使用時。現状 `pending` |
| `BITFLYER_API_SECRET` | 同上。現状 `pending` |

### 2-2. Wave 1-3 で追加された新環境変数

以下が `.env.staging` に**含まれているか**を確認する。なければ追記すること。

```bash
# ---- AI / Shadow Mode（Wave 3: stream-e）----
AI_SHADOW_MODE=true                   # true=判定記録のみ・実際のトレード実行しない
AI_PROMPT_VERSION=v1                  # AIプロンプトテンプレートバージョン
AI_CLAUDE_MODEL=claude-sonnet-4-20250514
AI_OPENAI_MODEL=gpt-4o
AI_MIN_CONFIDENCE_THRESHOLD=40        # 信頼度閾値。40未満はHOLDに倒す
AI_CROSS_VALIDATION_ENABLED=false     # staging ではコスト節約のため false 推奨

# ---- Exchange（Wave 3: 段階的資金投入）----
EXCHANGE_PHASE=1                      # 1=マイクロテスト($50), 2=小規模($100), 3=本格($1000)
EXCHANGE_MAX_ORDER_USD=50             # Phase 1 に対応した上限
EXCHANGE_DAILY_TRADE_LIMIT=5
EXCHANGE_COOLDOWN_SECONDS=300
EXCHANGE_TIMEOUT_SECONDS=30

# ---- Aave（Wave 3: Flashbots 対応）----
AAVE_FLASHBOTS_RPC_URL=               # 空欄で可（Flashbots不使用時はダミークライアントがスキップ）
AAVE_WARN_HEALTH_FACTOR=1.8           # SAFE_MODE 遷移閾値（AAVE_MIN_HEALTH_FACTOR と区別）
AAVE_OPERATION_MODE=NORMAL            # NORMAL / SAFE_MODE / HARD_STOP
AAVE_STATE_STALE_THRESHOLD_SECONDS=300

# ---- Knowledge Hub（Wave 1）----
KNOWLEDGE_EMBEDDING_MODEL=text-embedding-3-small
KNOWLEDGE_EMBEDDING_DIMENSIONS=1536
KNOWLEDGE_CHUNK_SIZE_TOKENS=500
KNOWLEDGE_CHUNK_OVERLAP_TOKENS=50
KNOWLEDGE_SEARCH_TOP_K=5
```

### 2-3. 変更不要の設定（確認のみ）

```bash
EXCHANGE_CLIENT_TYPE=bitflyer   # このまま
AAVE_CLIENT_TYPE=dummy          # このまま（testnet ダミー）
AI_SHADOW_MODE=true             # staging では true 必須
EXCHANGE_SANDBOX=true           # staging では true 必須
```

---

## 3. デプロイ手順

### 3-1. dev ブランチの最新を取得

```bash
cd /opt/ultra-autotrade
git fetch origin
git checkout dev
git pull origin dev

# 現在のコミットを確認
git log -3 --oneline
```

> **注意:** `deploy.sh` は `origin/main` を pull するため、dev ブランチデプロイ時は使用しないこと。

### 3-2. Docker イメージのビルド

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging build --no-cache
```

ビルド時間の目安: 3〜5 分

### 3-3. 旧コンテナ停止

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging down
```

### 3-4. 新コンテナ起動

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

### 3-5. コンテナ起動確認

```bash
docker compose -f docker-compose.staging.yml ps
```

期待される出力（全サービスが `running` または `healthy`）:

```
NAME                                  STATUS
ultra-autotrade-postgres-staging      running (healthy)
ultra-autotrade-backend-staging       running
ultra-autotrade-frontend-staging      running
```

ログ確認:

```bash
docker compose -f docker-compose.staging.yml logs backend --tail 50 -f
```

---

## 4. ヘルスチェック

### 4-1. バックエンド起動待ち

```bash
for i in $(seq 1 30); do
  curl -sf http://localhost:8000/health && echo "OK" && break
  echo "Waiting... ($i/30)"
  sleep 2
done
```

### 4-2. Swagger UI

```bash
curl -sf http://localhost:8000/docs -o /dev/null -w "%{http_code}\n"
# 期待値: 200
```

### 4-3. Exchange ステータス確認

```bash
curl -s http://localhost:8000/exchange/status | python3 -m json.tool
```

期待レスポンス例:

```json
{
  "status": "ok",
  "exchange": "bitflyer",
  "sandbox": true,
  "phase": 1
}
```

### 4-4. Knowledge Search 動作確認

```bash
curl -s -X POST http://localhost:8000/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "BTC price trend", "top_k": 3}' \
  | python3 -m json.tool
```

期待レスポンス例:

```json
{
  "results": [],
  "query": "BTC price trend",
  "total": 0
}
```

（Knowledge Hub にデータがない場合は `results: []` で正常）

### 4-5. Shadow Mode 動作確認（Wave 3）

```bash
curl -s http://localhost:8000/ai/shadow-mode/status | python3 -m json.tool
```

期待レスポンス:

```json
{
  "shadow_mode": true,
  "message": "Shadow mode is active. Trades will not be executed."
}
```

---

## 5. 問題が発生した場合

### ログ確認

```bash
# バックエンドのエラーログ
docker compose -f docker-compose.staging.yml logs backend --tail 100

# PostgreSQL のログ
docker compose -f docker-compose.staging.yml logs postgres --tail 50
```

### DB 接続確認

```bash
docker exec -it ultra-autotrade-postgres-staging \
  psql -U ultra -d ultra_autotrade -c "\dt"
```

### コンテナへの直接アクセス

```bash
docker exec -it ultra-autotrade-backend-staging bash
```

---

## 6. ロールバック手順

### 6-1. 1つ前のコミットに戻す

```bash
cd /opt/ultra-autotrade

# 戻したいコミットのハッシュを確認
git log -5 --oneline

# 指定コミットに切り替え
git checkout <commit-hash>

# 再ビルド・再起動
docker compose -f docker-compose.staging.yml --env-file .env.staging down
docker compose -f docker-compose.staging.yml --env-file .env.staging build --no-cache
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

### 6-2. 緊急停止のみ（コンテナ停止）

```bash
docker compose -f docker-compose.staging.yml down
```

### 6-3. main ブランチに戻す

```bash
git checkout main
git pull origin main
docker compose -f docker-compose.staging.yml --env-file .env.staging build --no-cache
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
```

---

## 7. デプロイ完了チェックリスト

```
[ ] git pull origin dev で最新コミットが反映されている
[ ] .env.staging に Wave 1-3 の新環境変数が追記されている
[ ] docker compose ps で全コンテナが running
[ ] GET /health → 200
[ ] GET /docs → 200
[ ] GET /exchange/status → JSON レスポンスあり
[ ] POST /knowledge/search → JSON レスポンスあり
[ ] AI_SHADOW_MODE=true を確認（staging では実トレード禁止）
[ ] EXCHANGE_SANDBOX=true を確認
```
