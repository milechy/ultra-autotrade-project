# Staging 復旧 + v4 プロンプト有効化 手順書

> 対象者: 小林さん（Mac から手動実施）  
> 目的: staging stack を v3 で復旧・28本 merge 検証 → v4 切替確認  
> 前提: PR #322 (v4 KeyError 完全修正) が main に merge 済みであること

---

## 概要（2フェーズ構成）

```
Step 1     : SSH
Step 2     : git pull origin main
Step 2.5   : staging stack 現状確認 → 必要なら full stack 起動
Step 3–5   : [Phase A] v3 で backend 起動・smoke 検証
Step 6     : [Phase B] v4 切替・4h 待機
```

Phase A で問題 → 該当 PR を main から revert → Step 3 からやり直し  
Phase B で問題 → env を v3 に戻して backend recreate（5分復旧）

---

## Step 1: Hetzner VPS に SSH

```bash
# Mac のターミナルから
ssh hetzner
# → VPS: 77.42.46.155
```

---

## Step 2: 最新コード取得 + 修正確認

> **パス注意**: 本番 VPS では `/opt/ultra-autotrade/` が git repo root（`main/` サブディレクトリなし）。
> dev VPS の `/opt/ultra-autotrade/main/` とは構造が異なる。

```bash
cd /opt/ultra-autotrade

# PR #322 が merge された main を取得
git pull origin main

# 確認: service.py が version in ("v3", "v4") になっていること
grep 'version in' backend/app/ai/service.py
# → if version in ("v3", "v4"):  が表示されれば OK
```

---

## Step 2.5: staging stack 現状確認

```bash
cd /opt/ultra-autotrade

# 起動中コンテナ一覧
docker compose -f docker-compose.staging.yml ps
```

### ケース A: backend のみ停止 (postgres / frontend は起動中)

```bash
# backend のみ再起動 → Step 3 へ進む
docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d --no-deps backend
```

### ケース B: 全コンテナ停止 / stack 未起動

```bash
# 全サービス起動 (full stack)
docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d

# 起動確認 (30秒待機)
sleep 30
docker compose -f docker-compose.staging.yml ps
```

### ケース C: 全コンテナ起動中 → 現状確認のみ

```bash
# health 確認して現バージョンをメモ
curl -sf http://localhost:8001/health | python3 -m json.tool | grep -E "status|scheduler|prompt"
docker exec ultra-autotrade-backend-staging-new env | grep AI_PROMPT_VERSION
```

---

## [Phase A] v3 で staging 起動・28本 merge 検証

### Step 3: staging env を v3 に設定

```bash
cd /opt/ultra-autotrade

# 現在値確認
grep 'AI_PROMPT_VERSION' .env.staging-new

# v3 に設定 (awk + tmpfile 方式)
awk '{gsub(/AI_PROMPT_VERSION=.*/, "AI_PROMPT_VERSION=v3"); print}' \
  .env.staging-new > /tmp/env_staging_tmp && mv /tmp/env_staging_tmp .env.staging-new

# もし AI_PROMPT_VERSION 行が存在しない場合のみ実行:
# printf '\nAI_PROMPT_VERSION=v3\n' >> .env.staging-new

# 確認
grep 'AI_PROMPT_VERSION' .env.staging-new
# → AI_PROMPT_VERSION=v3
```

### Step 4: backend 再ビルド & 起動

```bash
cd /opt/ultra-autotrade

docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  build --no-cache backend

docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d --no-deps backend
```

### Step 5: 起動確認

```bash
sleep 30

# health チェック
curl -sf http://localhost:8001/health | python3 -m json.tool
# 確認: "status": "ok" / "scheduler_healthy": true

# env 確認
docker exec ultra-autotrade-backend-staging-new env | grep AI_PROMPT_VERSION
# → AI_PROMPT_VERSION=v3

# エラーログ確認
docker logs --tail=50 ultra-autotrade-backend-staging-new 2>&1 | grep -i "ERROR\|CRITICAL"
```

### Step 5.5: smoke 検証（28本 merge の動作確認）

staging URL (`https://staging.ultra-auto-trade.com`) でブラウザから確認:

| 確認項目 | 期待動作 | 備考 |
|---|---|---|
| login (admin) | `/admin/dashboard` へ遷移 | JWT 取得 |
| login (partner) | `/partner/dashboard` へ遷移 | RAS Phase 1 |
| dashboard | AUM / PnL / HF 表示 | data 0 でも表示あれば OK |
| proposals (`/approve`) | 承認待ち一覧 or empty state | AIが v3 で動作中 |
| partner referral (`/partner/referral`) | 紹介コード表示 | PR #194/#201 |
| history (`/history`) | フィルターボタン表示 | PR #291 確認 |

**Phase A 合格条件**: 上記 6 画面がいずれも 500/404 エラーなく表示される

**Phase A で問題発生した場合**:
```bash
# 問題のある PR を特定 → main から revert
# git revert <commit-hash> → PR → merge → git pull → Step 4 からやり直し
```

---

## [Phase B] v4 切替テスト

> Phase A の smoke 確認完了後に実施

### Step 6: AI_PROMPT_VERSION を v4 に変更

```bash
cd /opt/ultra-autotrade

# v4 に変更
awk '{gsub(/AI_PROMPT_VERSION=.*/, "AI_PROMPT_VERSION=v4"); print}' \
  .env.staging-new > /tmp/env_staging_tmp && mv /tmp/env_staging_tmp .env.staging-new

# 確認
grep 'AI_PROMPT_VERSION' .env.staging-new
# → AI_PROMPT_VERSION=v4
```

### Step 7: backend のみ recreate（rebuild 不要 / env 変更のみ）

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d --no-deps --force-recreate backend

sleep 15

# env が正しく渡っているか確認
docker exec ultra-autotrade-backend-staging-new env | grep AI_PROMPT_VERSION
# → AI_PROMPT_VERSION=v4

# v4 がログで認識されているか確認
docker logs --tail=30 ultra-autotrade-backend-staging-new 2>&1 | grep -i "v4\|prompt_version\|ERROR"
```

### Step 8: 次の AI 判定（最大 4h 待機）で v4 確認

スケジューラーは 4h 間隔。次回判定後に確認:

```bash
docker exec -it ultra-autotrade-postgres-staging-new \
  psql -U ultra -d ultra_autotrade \
  -c "SELECT created_at, final_action, final_confidence, prompt_version \
      FROM ai_decisions ORDER BY created_at DESC LIMIT 5;"
```

**Phase B 合格条件**:
- `prompt_version = v4`
- `final_action` に BUY または SELL が含まれる（v3 では 99.2% HOLD）

**Phase B で問題発生した場合（5分復旧）**:
```bash
awk '{gsub(/AI_PROMPT_VERSION=.*/, "AI_PROMPT_VERSION=v3"); print}' \
  .env.staging-new > /tmp/env_staging_tmp && mv /tmp/env_staging_tmp .env.staging-new

docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d --no-deps --force-recreate backend

docker exec ultra-autotrade-backend-staging-new env | grep AI_PROMPT_VERSION
# → AI_PROMPT_VERSION=v3  (復旧完了)
```

---

## トラブルシューティング

### backend が起動しない

```bash
docker logs ultra-autotrade-backend-staging-new 2>&1 | tail -50
```

### smoke で 500 エラーが出る画面がある

```bash
# エラー詳細を確認
docker logs --tail=100 ultra-autotrade-backend-staging-new 2>&1 | grep "ERROR\|500"
# → 該当 PR の commit hash を特定 → git revert → Phase A やり直し
```

### postgres に接続できない

```bash
docker compose -f docker-compose.staging.yml ps postgres
# 停止していれば: docker compose -f docker-compose.staging.yml up -d postgres
# 30秒待機後に backend を再起動
```

---

## 本番への反映（Phase B 確認後 / 小林専権）

staging で `prompt_version = v4` + BUY/SELL 確認後:

```bash
cd /opt/ultra-autotrade

# 1. 本番 env に v4 を設定
awk '{gsub(/AI_PROMPT_VERSION=.*/, "AI_PROMPT_VERSION=v4"); print}' \
  .env.production > /tmp/env_prod_tmp && mv /tmp/env_prod_tmp .env.production

# 2. backend のみ recreate（rebuild 不要）
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate backend

# 3. ヘルスチェック
sleep 30
curl -sf http://localhost:8000/health | python3 -m json.tool
```

> **重要**: 本番 v4 切替は小林さん専権。staging での BUY/SELL 確認後に実施。

---

*更新: 2026-05-20 / 2フェーズ構成に改訂（Phase A: v3 smoke 検証 → Phase B: v4 切替）*  
*対象 PR: #322 (fix/ai-v4-agent-signals-template-keyerror)*
