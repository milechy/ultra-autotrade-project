# Ultra AutoTrade — 本番運用操作チェックリスト

> 最終更新: 2026-05-19
> 対象: production VPS (77.42.46.155) での運用操作全般
> 朝プロトコル §9 Step 0 で `cat /mnt/project/production_operation_checklist.md` として参照される正本

---

## ゲート 0: 環境混同防止 (必須・最初に確認)

- [ ] `hostname && pwd` で dev VPS (uata-dev-01 / 77.42.79.75) 上にいることを確認
- [ ] production VPS (77.42.46.155) 上で git commit / git merge / ファイル直接編集をしていないこと
- [ ] 対象コンテナ名: `docker ps | grep ultra-autotrade` で実際の名前を取得すること (推測禁止)
- [ ] .env ファイル編集: `sed -i` 禁止。`awk '{...}' file > /tmp/f && mv /tmp/f file` を使うこと
- [ ] production DB 変更 (INSERT/UPDATE/DELETE): 3段プロンプト確認必須 (CLAUDE.md §2026-05-02追加 参照)
- [ ] 本番 deploy: `./scripts/deploy_production.sh` のみ使用 (手打ち docker compose build 禁止)

---

## ゲート 1: Docker 環境確認

```bash
# Step 1: 起動中コンテナ一覧 (必ず実行してからコンテナ名を使う)
docker compose ls
docker ps | grep ultra-autotrade

# Step 2: compose project 名一致確認
docker inspect <container> --format "{{index .Config.Labels \"com.docker.compose.project\"}}"
# 全コンテナで同一 project 名であること

# Step 3: ネットワーク確認 (DB接続500エラー調査時)
docker inspect <backend-container> --format "{{json .NetworkSettings.Networks}}"
docker inspect <postgres-container> --format "{{json .NetworkSettings.Networks}}"
```

---

## ゲート 2: DB 接続・コンテナ名確認

```bash
# Step 1: コンテナ名を取得 (ハードコード禁止)
docker ps --filter "name=postgres-production" --filter "status=running" --format "{{.Names}}" | head -1

# Step 2: DBユーザー名・DB名を取得
docker exec <container> env | grep POSTGRES

# Step 3: テーブル一覧を取得
docker exec <container> psql -U <user> -d <db> -c \
  "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"
```

---

## ゲート 3: ヘルスチェック (内部 + 外形)

```bash
# 内部ヘルスチェック
curl -sf http://localhost:8010/health | python3 -m json.tool

# 外形ヘルスチェック (Cloudflare 経由 / Gate 8)
for i in 1 2 3 4 5; do
  curl -sf -o /dev/null -w "[%{http_code}] " https://api.ultra-auto-trade.com/health
  sleep 2
done; echo

# scheduler_healthy フィールド確認 (true 必須)
curl -sf https://api.ultra-auto-trade.com/health | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('scheduler_healthy:', d.get('scheduler_healthy')); print('warnings:', d.get('warnings','[]'))"
```

---

## ゲート 4: 業務動作 KPI 確認 (朝プロトコル必須)

```bash
# production VPS で実行
docker exec <postgres-production-container> psql -U ultra -d ultra_autotrade -c \
  "SELECT COUNT(*) AS decisions_24h FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';"

docker exec <postgres-production-container> psql -U ultra -d ultra_autotrade -c \
  "SELECT COUNT(*) AS proposals_24h, MAX(created_at) AS latest FROM proposals WHERE created_at > NOW() - INTERVAL '24 hours';"

# backend ERROR ログ件数
docker logs --tail=200 <backend-production-container> 2>&1 | grep -c "ERROR"
```

---

## ゲート 5: deploy 前チェック

```bash
# バックエンド変更有無 → フルデプロイか判断
git diff main --name-only | grep "^backend/"

# フロントエンドのみ変更の場合: --frontend-only 可
# バックエンド変更あり: フルデプロイ必須

# .env ファイル差分確認
diff <(grep -v '^#' backend/.env.staging.example | grep '=' | cut -d= -f1 | sort) \
     <(grep -v '^#' /opt/ultra-autotrade/.env.production | grep '=' | cut -d= -f1 | sort)
```

---

## ゲート 6: deploy 後確認

```bash
# NEXT_PUBLIC_PRIVY_APP_ID 焼き込み確認
PRIVY_VAL=$(grep '^NEXT_PUBLIC_PRIVY_APP_ID=' /opt/ultra-autotrade/.env.production | cut -d= -f2-)
docker exec <frontend-production-container> sh -c \
  "grep -lE '$PRIVY_VAL' /app/.next/static/chunks/*.js | wc -l"
# 0件なら焼き込み失敗 → 即ロールバック

# nginx resolver 設定確認 (1以上必須)
docker exec <nginx-production-container> nginx -T 2>&1 | grep -c "^[[:space:]]*resolver"

# upstream.conf が変数形式になっているか確認
docker exec <nginx-production-container> cat /etc/nginx/conf.d/upstream.conf
# → "set $backend backend-blue:8000;" が正しい形式
```

---

## ゲート 7: nginx 502 発生時のトリアージ

```bash
# Step 1: 直近 --frontend-only deploy 確認 → backend recreate の可能性
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.CreatedAt}}" | grep ultra-autotrade

# Step 2: nginx upstream IP 固着確認
docker exec <nginx-container> nginx -T 2>&1 | grep resolver
# resolver 未設定 + backend recreate → docker restart nginx で即時復旧

# Step 3: backend 直接疎通確認
curl -sf http://localhost:8010/health

# Step 4: cloudflared ログ確認
docker logs <cloudflared-container> 2>&1 | tail -20
```

---

## 緊急時参照

| 事象 | 対応 |
|------|------|
| postgres SIGKILL / exit 137 | `docs/postmortems/2026-05-17_loki_postgres_cascade.md` |
| バックアップ空ファイル | `docs/postmortems/2026-05-17_backup_silent_failure.md` |
| nginx 502 (upstream IP 固着) | `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` |
| staging cloudflared 502 | `docs/postmortems/2026-05-09_staging_api_502.md` |
| frontend build env 未焼き込み | CLAUDE.md §2026-05-03 Lesson Learned |
| DB 接続 500 エラー | CLAUDE.md §2026-04-02追加（Docker Compose プロジェクト名） |

---

*GID 1214888902535109 / 2026-05-19*
