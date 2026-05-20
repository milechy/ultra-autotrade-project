# Docker コマンドチートシート (Ultra AutoTrade)

> 2026-05-20 作成。本日発生した5+インシデントの教訓を7項目で整理。
> 参照: CLAUDE.md「2026-05-17追加 docker compose restart ≠ recreate」

---

## 1. docker compose 系は必ず --env-file を明示

```bash
# ✅ 正しい
docker compose -f docker-compose.production.yml --env-file .env.production up -d
docker compose -f docker-compose.staging.yml --env-file .env.staging-new up -d

# ❌ 禁止: --env-file 省略で NEXT_PUBLIC_* が空展開される
docker compose up -d
docker compose -f docker-compose.production.yml up -d
```

**教訓発生:** 2026-05-03 PR #191 手打ちデプロイ。`NEXT_PUBLIC_PRIVY_APP_ID` が空展開でウォレット接続死亡 (4-5時間ロス)

---

## 2. docker restart ≠ recreate (env 変更は --force-recreate 必須)

```bash
# ✅ 正しい: HostConfig (env/network/ports/logging) 変更を反映させる
docker compose up -d --force-recreate --no-deps backend-blue backend-green

# ✅ recreate 後の適用確認
docker inspect ultra-autotrade-backend-blue-production --format '{{.Created}}'
# compose.yml 変更時刻より新しければ OK

# ❌ 禁止: restart は既存コンテナを停止/起動するだけ。HostConfig 再読込なし
docker restart ultra-autotrade-backend-blue-production
docker compose restart backend-blue
```

**教訓発生:** 2026-05-20 `AI_PROMPT_VERSION=v4` を .env.production に追記後 `docker restart` → 未反映で v1 のまま動作継続。

---

## 3. --remove-orphans は別 stack を道連れ削除するリスク

```bash
# ✅ 正しい: --remove-orphans なしで down
docker compose -f docker-compose.production.yml down

# ❌ 禁止: 同一 COMPOSE_PROJECT_NAME の staging-new コンテナが巻き込まれる
docker compose -f docker-compose.production.yml down --remove-orphans
```

**教訓発生:** 2026-05-20 production deploy 時に `down --remove-orphans` が staging-new コンテナを2回道連れ削除。
**根本修正:** PR #332 で `deploy_production.sh` から `--remove-orphans` を除去済み。

---

## 4. docker ps --filter name= は OR 動作

```bash
# ✅ 正しい: コンテナ名を完全一致で指定
docker ps --filter name=ultra-autotrade-postgres-staging-new

# ❌ 誤解: 2つの --filter name= は AND ではなく OR になる
docker ps --filter name=postgres --filter name=staging
# → "postgres" OR "staging" を含む全コンテナが返る (frontend 等も混入)
```

**教訓発生:** 2026-05-20 staging 調査で `--filter name=postgres --filter name=staging` を使ったら frontend コンテナが返ってきた。

---

## 5. backend 再起動 (env 変更適用の標準手順)

```bash
# ✅ 標準手順 (Blue/Green 両方再起動)
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --force-recreate --no-deps backend-blue backend-green

# ✅ 適用確認: logging driver
docker inspect ultra-autotrade-backend-blue-production \
  --format '{{.HostConfig.LogConfig.Type}}'
# → json-file (正しい) or loki (古い設定が残存)

# ✅ 適用確認: env 変数
docker inspect ultra-autotrade-backend-blue-production \
  --format '{{range .Config.Env}}{{println .}}{{end}}' | grep AI_PROMPT_VERSION
```

---

## 6. Blue/Green の active slot は動的に確認

```bash
# ✅ 現在の active を確認してから操作
docker exec ultra-autotrade-nginx-production \
  cat /etc/nginx/conf.d/upstream.production.conf
# → "set $backend backend-blue:8000;" または "set $backend backend-green:8001;"

# ✅ nginx 経由の疎通確認
curl -sf http://localhost:8080/health | python3 -m json.tool
```

---

## 7. builder prune は image を残す (system prune との違い)

```bash
# ✅ 安全なクリーンアップ (build cache のみ)
docker builder prune -f              # build cache 削除
docker image prune -f               # dangling image (タグなし) のみ削除

# ✅ 週次推奨
./scripts/docker_cleanup.sh         # dangling のみ
./scripts/periodic_docker_cleanup.sh  # ALL builder cache (cron 日曜 03:00)

# ❌ 禁止: 使用中 image まで削除してしまう
docker system prune -af
```

**注意:** `docker builder prune -f` は build cache のみ削除。既存の named image (ultra-autotrade-project-backend-*) は残る。
`docker system prune -af` は使用中でない全 image を削除するため、deploy 直後に実行すると次回 up -d が起動不能になる。

---

## クイックリファレンス

| やりたいこと | 正しいコマンド |
|---|---|
| env 変更を反映して再起動 | `docker compose up -d --force-recreate --no-deps <svc>` |
| compose.yml 変更を反映 | `docker compose up -d --force-recreate --no-deps <svc>` |
| コードのみ変更 (HostConfig 変更なし) | `docker compose restart <svc>` 可 |
| active slot 確認 | `docker exec nginx cat /etc/nginx/conf.d/upstream.production.conf` |
| コンテナ作成時刻確認 | `docker inspect <c> --format '{{.Created}}'` |
| logging driver 確認 | `docker inspect <c> --format '{{.HostConfig.LogConfig.Type}}'` |
| 外形 health 確認 | `curl -sf https://api.ultra-auto-trade.com/health` |
