# Docker コマンドチートシート (Ultra AutoTrade)

> 作成: 2026-05-20 / 更新: 2026-05-21
> 参照: CLAUDE.md「docker 操作前 (落とし穴 7 項目)」テーブル、`docs/35_docker_maintenance_runbook.md`
> 対象: dev VPS (`95.216.167.198`、2026-07-02時点未構築) / staging VPS (`188.34.167.142`) / production VPS (`5.223.88.14`) の全 docker 操作

---

## 落とし穴 7 項目 (docker 操作前に必ず確認)

### 落とし穴 1: `docker compose restart` ≠ recreate (env 変数再読込されない)

```bash
# ❌ 禁止: restart は既存コンテナを stop/start するだけ。HostConfig (env/ports/logging) は再読込されない
docker restart ultra-autotrade-backend-production
docker compose restart backend

# ✅ 正しい: env 変数・compose.yml 変更を確実に反映させる
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --force-recreate --no-deps backend-blue backend-green

# ✅ 適用確認 (コンテナ作成日時が compose 変更後か確認)
docker inspect ultra-autotrade-backend-blue-production --format '{{.Created}}'
```

**教訓 (2026-05-20):** `.env.production` に `AI_PROMPT_VERSION=v4` を追記後に `docker restart` したが未反映。v1 のまま稼働継続。

---

### 落とし穴 2: `restart` は旧イメージのまま再起動 (新ビルド後は stop→rm→up)

```bash
# ❌ 禁止: ビルド後に restart してもコンテナは新イメージを使わない
docker compose build backend
docker compose restart backend   # 旧イメージのまま!

# ✅ 正しい: 新ビルド後は必ずコンテナを作り直す
docker compose -f docker-compose.production.yml --env-file .env.production build --no-cache backend
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --force-recreate --no-deps backend-blue backend-green

# ✅ または deploy_production.sh を使う (フルデプロイ推奨)
./scripts/deploy_production.sh
```

**教訓 (2026-04-02):** 正しいデプロイ手順は `docker rm -f <container> && docker compose up -d --no-deps <service>`。空白時間を最小化するため stop→rm→up を連続実行。

---

### 落とし穴 3: `docker system prune -af` 禁止 (使用中イメージ削除リスク)

```bash
# ❌ 禁止: 使用中でない全イメージを削除 → deploy 直後に実行すると次回 up -d が起動不能になる
docker system prune -af

# ✅ 安全なクリーンアップ (build cache のみ)
docker builder prune -f              # build cache 削除 (named image は残る)
docker image prune -f               # dangling image (タグなし) のみ削除

# ✅ 週次推奨スクリプト
./scripts/docker_cleanup.sh              # dangling のみ (通常週次)
./scripts/periodic_docker_cleanup.sh     # ALL builder cache (cron: 毎日曜 03:00 JST)
```

**背景 (2026-04-19):** disk 79% (57G/75G) 逼迫 → `docker builder prune -f` で 27GB 解放。`docker system prune -af` では稼働イメージが消えるため禁止。

---

### 落とし穴 4: `--remove-orphans` は別スタックを道連れ削除する

```bash
# ❌ 禁止: production の down が同一 COMPOSE_PROJECT_NAME の staging-new コンテナを巻き込む
docker compose -f docker-compose.production.yml down --remove-orphans

# ✅ 正しい: --remove-orphans なしで down
docker compose -f docker-compose.production.yml down

# ✅ 孤立コンテナを個別に消したい場合は明示的に rm
docker rm -f ultra-autotrade-some-orphan-container
```

**教訓 (2026-05-20):** production deploy 時に `down --remove-orphans` が staging-new コンテナを 2 回道連れ削除。PR #332 で `deploy_production.sh` から除去済み。

---

### 落とし穴 5: container_name 衝突 (production は `-production` suffix 必須)

```bash
# container_name の命名規則 (2026-04-24 衝突修正後)
# production: ultra-autotrade-*-production
# staging:    ultra-autotrade-*-staging-new

# ✅ 現在の正しいコンテナ名一覧
# backend:    ultra-autotrade-backend-production / ultra-autotrade-backend-staging-new
# frontend:   ultra-autotrade-frontend-production / ultra-autotrade-frontend-staging-new
# postgres:   ultra-autotrade-postgres-production / ultra-autotrade-postgres-staging-new
# cloudflared: ultra-autotrade-cloudflared-production (staging なし)

# ✅ 稼働確認
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep ultra-autotrade
```

**教訓 (2026-04-24):** compose の `${POSTGRES_PASSWORD}` が手動 `up` 時に空文字化 → DB 接続失敗 → コンテナ終了 (container_name 衝突と重複インシデント)。現在は `.env.production` に `DATABASE_URL` を直接定義し解消済み。

---

### 落とし穴 6: 502 防止デプロイ手順 (rm -f → up -d --no-deps)

```bash
# ✅ 502 を最小化する 1 サービス入れ替え手順
docker rm -f ultra-autotrade-frontend-production
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps frontend

# ✅ nginx 経由の疎通確認
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
curl -sf https://app.ultra-auto-trade.com | head -3

# ✅ active slot 確認 (Blue/Green)
docker exec ultra-autotrade-nginx-production \
  cat /etc/nginx/conf.d/upstream.production.conf
# → "set $backend backend-blue:8000;" または "set $backend backend-green:8001;"
```

**502 デバッグ手順:**
1. `docker ps -a` でコンテナが存在・起動しているか確認
2. `docker logs --tail=50 ultra-autotrade-frontend-production` で Next.js Ready ログ確認
3. `curl http://127.0.0.1:3000` でホスト→フロントエンドの疎通確認
4. `docker logs ultra-autotrade-cloudflared-production --tail=50` で `connection refused` 確認
5. 502 の多くはデプロイ中の一時的状態 (30 秒待機で自然解消)

---

### 落とし穴 7: dev VPS と本番 VPS のパス構造差 (`/main/` の有無)

```bash
# ❌ production/staging VPS で dev VPS のパスを使うと "No such file or directory"
cd /opt/ultra-autotrade/main/         # dev VPS: ✅（構築後） / production・staging VPS: ❌

# ✅ production VPS の正しいパス
cd /opt/ultra-autotrade/              # production VPS (5.223.88.14) の repo root

# ✅ SSH 後は必ず pwd && ls で確認してから操作
# production は alias無し・3段階プロトコル経由のみ
ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14
pwd && ls
# → /opt/ultra-autotrade  (main/ サブディレクトリはない)
```

| VPS | git repo root | backend/ の絶対パス |
|---|---|---|
| **dev VPS** (`95.216.167.198`、2026-07-02時点未構築) | `/opt/ultra-autotrade/main/`（構築後） | `/opt/ultra-autotrade/main/backend/` |
| **staging VPS** (`188.34.167.142`) | `/opt/ultra-autotrade/` | `/opt/ultra-autotrade/backend/` |
| **production VPS** (`5.223.88.14`) | `/opt/ultra-autotrade/` | `/opt/ultra-autotrade/backend/` |

**背景:** dev VPS は git worktree 構造で `main/` サブディレクトリが存在する（構築後）。staging/production VPS には `main/` サブディレクトリは**存在しない**。

---

## 追加の落とし穴

### 落とし穴 A: `--env-file` を省略すると NEXT_PUBLIC_* が空展開される

```bash
# ❌ 禁止: --env-file 省略で NEXT_PUBLIC_PRIVY_APP_ID 等が空文字でビルドされる
docker compose -f docker-compose.production.yml build --no-cache frontend

# ✅ 正しい (または deploy_production.sh を使う)
docker compose -f docker-compose.production.yml --env-file .env.production build --no-cache frontend

# ✅ 焼き込み確認 (0件なら空展開ビルド失敗)
PRIVY_VAL=$(grep '^NEXT_PUBLIC_PRIVY_APP_ID=' .env.production | cut -d= -f2-)
docker exec ultra-autotrade-frontend-production sh -c \
  "grep -lE '$PRIVY_VAL' /app/.next/static/chunks/*.js | wc -l"
```

**教訓 (2026-05-03):** PR #191 デプロイで手打ち `docker compose build` に `--env-file` が抜け、本番ウォレット接続ボタンが完全死亡。復旧に 4-5 時間。**本番 frontend 再ビルドは `./scripts/deploy_production.sh --frontend-only` のみ使うこと。**

---

### 落とし穴 B: `docker ps --filter name=` は OR 動作 (複数 filter は AND でない)

```bash
# ❌ 誤解: 2 つの --filter name= は AND ではなく OR
docker ps --filter name=postgres --filter name=staging
# → "postgres" OR "staging" を含む全コンテナが返る (frontend 等も混入)

# ✅ 正しい: コンテナ名を完全一致で絞る
docker ps --filter name=ultra-autotrade-postgres-staging-new
```

**教訓 (2026-05-20):** staging 調査で誤 filter を使い、frontend コンテナが postgres と混在して返ってきた。

---

### 落とし穴 C: `docker compose down -v` は DB ボリューム全削除 (絶対禁止)

```bash
# ❌ 絶対禁止: DBボリュームが削除されテスターデータが全滅する
docker compose down -v
docker compose down --volumes

# ✅ 正しい: ボリューム削除なしの down
docker compose -f docker-compose.production.yml down
```

`deploy_production.sh` は `-v` / `--volumes` フラグを検出して即座に `exit 1` する。

---

### 落とし穴 D: COMPOSE_PROJECT_NAME 不一致 → DB 名前解決失敗

```bash
# compose は必ず同一プロジェクト名で実行すること
# プロジェクト名が異なると postgres ホスト名が解決できず 500 エラーになる

# ✅ 確認
docker inspect ultra-autotrade-backend-production \
  --format '{{index .Config.Labels "com.docker.compose.project"}}'
# → ultra-autotrade-project (全コンテナで一致すること)

# ❌ -p フラグで別名を指定しない
docker compose -p my-project -f docker-compose.production.yml up -d   # 禁止
```

---

## クイックリファレンス

| やりたいこと | 正しいコマンド |
|---|---|
| env 変数変更を反映して再起動 | `docker compose up -d --force-recreate --no-deps <svc>` |
| compose.yml 変更を反映 | `docker compose up -d --force-recreate --no-deps <svc>` |
| コードのみ変更 (HostConfig 変更なし) | `docker compose restart <svc>` 可 |
| 本番フルデプロイ | `./scripts/deploy_production.sh` |
| フロントのみ再ビルド | `./scripts/deploy_production.sh --frontend-only` |
| staging デプロイ | `./scripts/deploy_staging.sh` |
| active slot 確認 | `docker exec nginx cat /etc/nginx/conf.d/upstream.production.conf` |
| コンテナ作成日時確認 | `docker inspect <c> --format '{{.Created}}'` |
| logging driver 確認 | `docker inspect <c> --format '{{.HostConfig.LogConfig.Type}}'` |
| env 変数確認 | `docker inspect <c> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep <KEY>` |
| ビルドキャッシュ削除 (安全) | `docker builder prune -f && docker image prune -f` |
| disk 使用量確認 | `docker system df` |
| 孤立コンテナ強制削除 | `docker rm -f <container-name>` |
| 外形 health 確認 | `curl -sf https://api.ultra-auto-trade.com/health` |
| staging health 確認 | `curl http://localhost:8001/health` (本番 VPS 上) |

---

## 参照ドキュメント

| ドキュメント | 内容 |
|---|---|
| `docs/35_docker_maintenance_runbook.md` | ディスク管理 / cron / PostgreSQL バックアップ詳細 |
| `docs/ops/03_deploy_procedures.md` | デプロイ手順 / コンテナ名一覧 / ロールバック手順 |
| `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` | nginx upstream 問題 RCA |
| `scripts/docker_cleanup.sh` | 週次クリーンアップ (dangling のみ) |
| `scripts/periodic_docker_cleanup.sh` | 積極週次クリーンアップ (ALL builder cache) |
| `scripts/deploy_production.sh` | 本番フルデプロイスクリプト (手打ち禁止) |
