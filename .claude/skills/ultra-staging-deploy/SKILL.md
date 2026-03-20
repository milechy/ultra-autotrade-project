---
name: ultra-staging-deploy
description: Deploy Ultra AutoTrade to staging environment on Hetzner VPS. Use when deploying to staging, building Docker images, updating the staging server, or troubleshooting deployment issues.
---

# Staging Deploy Skill

## When to Use
- staging（Hetzner VPS）へのデプロイ
- Docker イメージのビルド
- staging 環境のトラブルシューティング
- デプロイ後の動作確認

## Pre-Deploy Checklist
- [ ] `ruff check .` — lint エラー 0
- [ ] `ruff format --check .` — フォーマット違反 0
- [ ] `pytest tests/ -q --tb=short` — 全テスト通過
- [ ] `git push origin dev` — リモートに最新コードがpush済み

## Deploy Command（必ずこの順序）
```bash
ssh hetzner << 'SSHEOF'
cd /opt/ultra-autotrade
git pull origin dev

# ⚠️ CRITICAL: --no-cache 必須
docker compose -f docker-compose.staging.yml --env-file .env.staging build --no-cache frontend backend
docker compose -f docker-compose.staging.yml --env-file .env.staging down
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d

sleep 30

curl -s http://localhost:8000/health
curl -s -o /dev/null -w "Frontend: %{http_code}\n" http://localhost:3000
SSHEOF
```

## Post-Deploy Verification
- [ ] `{"status":"ok","env":"staging"}` を確認
- [ ] Frontend HTTP 200 を確認
- [ ] `GET /api/transparency/safety-score` でスコア取得
- [ ] ユーザー3名確認（admin/editor/viewer）

## Known Pitfalls
1. **`--no-cache` 必須** — 古いイメージがキャッシュされると変更が反映されない
2. **SSH alias は `hetzner`** — `ssh ultra@$STAGING_HOST` ではなく `ssh hetzner` を使う
3. **docker compose down でDBデータは消えない** — named volume（postgres-data）。`down -v` のみ削除
4. **POSTGRES_PASSWORD** — `.env.staging` に設定が必要（空だと警告）
5. **ユーザーロール** — 再ビルド後もDBは維持されるが、初回は seed が必要
6. **`No services to build` 警告** — staging compose に `build:` セクションがない場合
