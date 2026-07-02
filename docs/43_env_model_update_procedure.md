# docs/43 — Hetzner 実 .env モデル名更新手順

## 対象

Anthropic Claude モデル名（`AI_CLAUDE_MODEL` / `AI_FALLBACK_MODEL`）を更新する際に
Hetzner VPS 上の実ファイルへ反映する手順。

`.env.production.example` / `.env.staging.example` をリポジトリで更新した後、
本手順に従って Hetzner 上の実ファイルに手動反映する。

---

## 前提

- Hetzner SSH: `ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142`
- 作業ディレクトリ: `/opt/ultra-autotrade`
- 許可モデルリスト: `backend/app/ai/config.py` の `VALID_CLAUDE_MODELS`
- CI スクリプト: `scripts/validate_anthropic_model.py` (root `.env.*.example` を検証)

## ⚠️ 禁止事項

- `sed -i` などで `.env.staging-new` と `.env.production` を同時一括置換しない
  （2026-04-18 インシデント: 両ファイルが完全一致し環境分離が崩壊）
- ファイルを nano 以外で直接編集する場合も必ず片方ずつ実施

---

## 手順

### STEP 0: 事前確認

```bash
# Hetzner SSH
ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142
cd /opt/ultra-autotrade

# 現在の稼働モデル確認（staging）
curl -s http://localhost:8001/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('claude_model'), d.get('claude_fallback_model'))"

# 現在の稼働モデル確認（production）
curl -s http://localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('claude_model'), d.get('claude_fallback_model'))"

# .env 内の現在値確認
grep "AI_CLAUDE_MODEL\|AI_FALLBACK_MODEL" .env.staging-new
grep "AI_CLAUDE_MODEL\|AI_FALLBACK_MODEL" .env.production
```

### STEP 1: バックアップ取得（必須）

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# staging バックアップ
cp .env.staging-new ".env.staging-new.bak.${TIMESTAMP}"
echo "Backup: .env.staging-new.bak.${TIMESTAMP}"

# production バックアップ
cp .env.production ".env.production.bak.${TIMESTAMP}"
echo "Backup: .env.production.bak.${TIMESTAMP}"
```

### STEP 2: Shadow Staging の更新（先行反映）

```bash
# nano で staging のみ編集（production は触らない）
nano .env.staging-new
```

変更箇所:
```
AI_CLAUDE_MODEL=claude-sonnet-4-6-20250929
AI_FALLBACK_MODEL=claude-haiku-4-5-20251001
```

```bash
# staging backend のみ再起動
docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d --no-deps --force-recreate backend

# 起動確認
sleep 10
curl -s http://localhost:8001/health | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('claude_model:', d.get('claude_model')); print('fallback:', d.get('claude_fallback_model')); print('scheduler_healthy:', d.get('scheduler_healthy'))"
```

### STEP 3: 30分観察

```bash
# scheduler_healthy と last_judgment を確認
watch -n 60 "curl -s http://localhost:8001/health | python3 -c \"import sys,json; d=json.load(sys.stdin); print('scheduler:', d.get('scheduler_healthy'), '| last:', d.get('last_judgment','none')[:19] if d.get('last_judgment') else 'none')\""
```

確認項目:
- `scheduler_healthy: true`
- `last_judgment` が現在時刻付近（過去30分以内）に更新されていること
- エラーログなし: `docker logs ultra-autotrade-project-backend-staging-1 2>&1 | grep -i error | tail -20`

### STEP 4: claude.ai に staging 観察結果を報告し GO 合図を受ける

```json
// 報告用: curl -s http://localhost:8001/health | jq '{claude_model, claude_fallback_model, scheduler_healthy, last_judgment}'
```

### STEP 5: Production の更新（GO 合図後）

```bash
# production のみ編集（staging は触らない）
nano .env.production
```

変更箇所:
```
AI_CLAUDE_MODEL=claude-sonnet-4-6-20250929
AI_FALLBACK_MODEL=claude-haiku-4-5-20251001
```

```bash
# production backend のみ再起動（フロント・DB に影響なし）
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate backend

# 起動確認
sleep 15
curl -s http://localhost:8000/health | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('claude_model:', d.get('claude_model')); print('fallback:', d.get('claude_fallback_model')); print('scheduler_healthy:', d.get('scheduler_healthy'))"

# Cloudflare Tunnel 経由でも確認
curl -s https://api.ultra-auto-trade.com/health | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('claude_model:', d.get('claude_model'))"
```

### STEP 6: 2時間監視

```bash
# エラー監視
docker logs -f ultra-autotrade-project-backend-1 2>&1 | grep -E "ERROR|DEPRECATED|ValueError"

# AI 判定成功確認（次回スケジュール実行後）
curl -s http://localhost:8000/health | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(json.dumps({'scheduler_healthy': d.get('scheduler_healthy'), 'last_judgment': d.get('last_judgment')}, indent=2))"
```

---

## ロールバック手順

```bash
TIMESTAMP=<バックアップ時刻>  # 例: 20260420_143000

# staging ロールバック
cp ".env.staging-new.bak.${TIMESTAMP}" .env.staging-new
docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d --no-deps --force-recreate backend

# production ロールバック（緊急時）
cp ".env.production.bak.${TIMESTAMP}" .env.production
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate backend
```

詳細: `docs/15_rollback_procedures.md` 参照

---

## 参照

- 許可モデルリスト: `backend/app/ai/config.py` → `VALID_CLAUDE_MODELS`
- CI 検証スクリプト: `scripts/validate_anthropic_model.py`
- 環境分離ガイド: `docs/42_environment_separation_design.md`
- 環境ファイル更新ルール: `CLAUDE.md` §「環境ファイル更新ルール」
