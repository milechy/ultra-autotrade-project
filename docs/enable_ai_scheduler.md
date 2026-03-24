# AI判定スケジューラー有効化手順

## 概要

AI判定スケジューラー（T-16）を Hetzner staging 環境で有効化し、テスターがログイン時に
`ai_decisions` と `proposals`（承認待ち）を確認できる状態にする手順。

## 環境変数（.env.staging 追加済み）

```
ENABLE_AI_JUDGMENT_SCHEDULER=1   # スケジューラー有効化フラグ
AI_JUDGMENT_INTERVAL_HOURS=4      # 実行間隔（デフォルト: 4時間）
```

## Staging 反映手順（人間が実行）

### 1. .env.staging を Hetzner にコピー

```bash
scp .env.staging hetzner:/opt/ultra-autotrade/.env.staging
```

### 2. Docker Compose 再起動

```bash
ssh hetzner "cd /opt/ultra-autotrade && docker compose -f docker-compose.staging.yml down && docker compose -f docker-compose.staging.yml up -d"
```

### 3. スケジューラー起動ログ確認

```bash
ssh hetzner "docker compose -f docker-compose.staging.yml logs backend | grep -i scheduler | tail -20"
```

期待されるログ出力:
```
INFO  AI judgment scheduler started (interval=4h)
```

## 初回AI判定の手動実行（テスト用）

スケジューラーは4時間ごとに自動実行されるが、手動でも即時実行できる。

### 管理者トークン取得

```bash
TOKEN=$(curl -s -X POST http://77.42.46.155:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ultra-auto-trade.com","password":"YOUR_PASSWORD"}' \
  | jq -r '.access_token')
```

### 手動トリガー実行

```bash
curl -s -X POST http://77.42.46.155:8000/api/ai/trigger \
  -H "Authorization: Bearer $TOKEN" \
  | jq .
```

期待レスポンス例:
```json
{
  "action": "HOLD",
  "confidence": 72,
  "proposals_created": 0,
  "decision_id": 1
}
```

BUY または SELL の場合:
```json
{
  "action": "BUY",
  "confidence": 85,
  "proposals_created": 3,
  "decision_id": 2
}
```

### AI判定履歴確認

```bash
curl -s http://77.42.46.155:8000/api/ai/decisions/latest \
  -H "Authorization: Bearer $TOKEN" | jq .

curl -s "http://77.42.46.155:8000/api/ai/decisions?limit=20" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### 承認待ちProposal確認

```bash
curl -s http://77.42.46.155:8000/api/proposals/pending \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## テスターへの案内

1. フロントエンドにログインすると `GET /api/ai/decisions/latest` が呼ばれ最新判定が表示される
2. BUY/SELL判定の場合、`GET /api/proposals/pending` で承認待ち提案が表示される
3. 提案を承認 (`POST /api/proposals/{id}/approve`) するとAave操作が実行される
4. 提案を拒否 (`POST /api/proposals/{id}/reject`) する場合は拒否のみ記録される

## トラブルシューティング

### スケジューラーが起動しない

```bash
ssh hetzner "docker compose -f docker-compose.staging.yml logs backend | grep -i 'judgment\|scheduler\|error' | tail -30"
```

`ENABLE_AI_JUDGMENT_SCHEDULER` が `1` になっているか確認:
```bash
ssh hetzner "docker compose -f docker-compose.staging.yml exec backend env | grep AI_JUDGMENT"
```

### AI判定が HOLD ばかりになる

- ANTHROPIC_API_KEY が正しく設定されているか確認
- `AI_CLAUDE_MODEL=claude-sonnet-4-20250514` が設定されているか確認
- ログで `API key not configured` エラーがないか確認

### proposals が作成されない

- BUY/SELL 判定時のみ proposals が作成される（HOLD では作成されない）
- アクティブユーザーが存在するか確認: `SELECT count(*) FROM users WHERE is_active=true;`
