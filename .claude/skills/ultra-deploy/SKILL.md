---
name: ultra-deploy
description: Deploy Ultra AutoTrade to production or staging. MUST use ./scripts/deploy_production.sh (production) or ./scripts/deploy_staging.sh (staging). Manual `docker compose build frontend` is FORBIDDEN per CLAUDE.md §Lesson Learned 2026-05-03.
---

# Ultra AutoTrade Deploy Skill

## ABSOLUTE Rules

CLAUDE.md `## デプロイ時の教訓` 配下の `#### Lesson Learned: 2026-05-03 手打ちdeploy違反インシデント` に準拠:

1. **本番 frontend 再ビルドは `./scripts/deploy_production.sh --frontend-only` のみ**
2. **手打ち `docker compose build` を含むコマンドの生成・実行は禁止** — claude.ai が生成した場合も拒否し、deploy script への置き換えを要求
3. **`.env.staging` は使用禁止** (旧)、正規は `.env.staging-new` (guard-env-files.sh R1 で物理ブロック)
4. **SSH alias 経由 (`ssh hetzner ...`) で手打ち実行しない** — Hetzner 上で deploy script を直接実行

## Production Deploy

- Compose: `docker-compose.production.yml`
- Env: `.env.production`
- Container: `*-production` suffix (CLAUDE.md `## 環境定義（2026-04-17 B案リネーム後）` 参照)
- Blue/Green: backend-blue host port 8010, backend-green 8011, nginx 8080

```bash
# Hetzner 上で実行
cd /opt/ultra-autotrade
git pull origin main

./scripts/deploy_production.sh                  # フルデプロイ
./scripts/deploy_production.sh --frontend-only  # フロントエンドのみ
./scripts/deploy_production.sh --backend-only   # Blue/Green ゼロダウンタイム
./scripts/deploy_production.sh --no-build       # ビルドなし up -d のみ
```

## Staging Deploy

- Compose: `docker-compose.staging.yml`
- Env: `.env.staging-new` (NOT `.env.staging`)
- COMPOSE_PROJECT_NAME: `ultra-autotrade-staging`
- Port: frontend 127.0.0.1:3001 / backend 127.0.0.1:8020-8021 / nginx 127.0.0.1:8082 / postgres 127.0.0.1:5433

```bash
cd /opt/ultra-autotrade
git pull origin dev
./scripts/deploy_staging.sh
```

## Post-Deploy Verification (Gate 8 必須)

外形 `/health` 5 回連続 200 を必須確認 (内部 127.0.0.1 ループバック確認は不十分):

```bash
# Production
for i in 1 2 3 4 5; do
  curl -sf -o /dev/null -w "[%{http_code}] " https://api.ultra-auto-trade.com/health
  sleep 2
done; echo

# Staging (CF Access Service Token 必須)
curl -sf -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
       -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
       https://api-staging.ultra-auto-trade.com/health
```

確認項目:
- HTTP 200 が 5 回連続
- JSON レスポンスで `scheduler_healthy: true`
- 失敗時は即 Slack `#ultra-auto-project` 通知

## Pre-Deploy Checklist

CLAUDE.md `## Definition of Done (DoD)` を必ず全通過:

- [ ] `./scripts/verify.sh` 全 PASS (ruff / mypy / pytest 80%+)
- [ ] `git push origin <branch>` 完了 (Hetzner は pull only)
- [ ] DB カラム追加がある場合: Hetzner で先に `ALTER TABLE` 実行
- [ ] `NEXT_PUBLIC_*` 変更時はフロントエンド再ビルド必須

## Known Pitfalls

1. **手打ち `docker compose build` 禁止** — 2026-05-03 Privy 焼き込み欠落で本番ウォレット死亡、復旧 4-5h。CLAUDE.md `## デプロイ時の教訓` 配下の `#### Lesson Learned: 2026-05-03 手打ちdeploy違反インシデント` 参照。

2. **`.env.staging` 直接アクセスは guard-env-files.sh でブロック** — `ls .env.staging*` や `cat .env.staging` も R1 でブロックされる。正規は `.env.staging-new`。

3. **nginx 502 → 応急処置の判断は人間に委ねる** — `--frontend-only` 直後の 502 は nginx upstream IP 固着の既知バグ。応急処置 (例: nginx 再起動) は `docs/ops/03_deploy_procedures.md` および CLAUDE.md `### 2026-05-12追加（nginx upstream IP 固着 → frontend-only deploy 直後 502）` を参照し、**人間が判断する**。スキルが復旧コマンドを自動提案・実行することは禁止。

4. **`--frontend-only` はバックエンドAPI変更なしの場合のみ** — 新APIエンドポイント追加時はフルデプロイ必須。判定: `git diff main --name-only | grep "^backend/"` で何か出たらフルデプロイ。

5. **deploy_production.sh の「✅ OK」出力を信用しない** — 内部 healthcheck は 127.0.0.1 ループバック経由。外形 Cloudflare 経由 5 回連続 200 を必ず確認。

6. **`docker rmi -f` まで自動化済み** — deploy_production.sh はビルド前に古いイメージを完全削除する。手動で `docker system prune` 不要。

## References

- CLAUDE.md `## 環境定義（2026-04-17 B案リネーム後）`
- CLAUDE.md `## デプロイ時の教訓` 配下の `#### Lesson Learned: 2026-05-03 手打ちdeploy違反インシデント`
- CLAUDE.md `### 2026-05-12追加（nginx upstream IP 固着 → frontend-only deploy 直後 502）`
- CLAUDE.md `## Definition of Done (DoD)`
- `docs/ops/03_deploy_procedures.md` — コンテナ名・ボリューム・障害対応の正本
- `docs/22_production_release_checklist.md` — リリース手順
- `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` — RCA
