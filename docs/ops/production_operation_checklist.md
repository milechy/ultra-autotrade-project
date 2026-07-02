# Ultra AutoTrade — 本番運用操作チェックリスト

> 最終更新: 2026-06-05
> 対象: production VPS (5.223.88.14) での運用操作全般
> 朝プロトコル §9 Step 0 で `cat /mnt/project/production_operation_checklist.md` として参照される正本

---

## ゲート 0: 環境混同防止 (必須・最初に確認)

- [ ] `hostname && pwd` で dev VPS (95.216.167.198、2026-07-02時点で未構築のため実際には production/staging VPS 上で直接この確認を行う) 上にいることを確認
- [ ] production VPS (5.223.88.14) 上で git commit / git merge / ファイル直接編集をしていないこと
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

## ゲート 8: ディスク使用率確認

```bash
# 本番 VPS で実行
df -h /
# → 80% 超: scripts/periodic_docker_cleanup.sh を実行
# → 90% 超: 即時手動対応 (healthcheck L7 が CRITICAL → Slack アラート発報)

# Docker 内訳確認
docker system df

# journal 使用量確認
du -sh /var/log/journal/ 2>/dev/null

# 積極クリーンアップ実行 (80% 超時)
/opt/ultra-autotrade/scripts/periodic_docker_cleanup.sh
# → docker builder prune -a -f + docker image prune -f + journalctl --vacuum-size=1G + Slack 通知
```

**月次監査チェックリスト** (毎月 1 回 / 小林さん専権):
- [ ] `df -h /` で使用率確認 (80% 超なら即 periodic_docker_cleanup.sh 実行)
- [ ] `docker system df` で builder cache / image 内訳確認
- [ ] `du -sh /var/log/journal/` で journal 使用量確認
- [ ] `scripts/periodic_docker_cleanup.sh` を手動実行 (月次定期実施)
- [ ] crontab -l で `periodic_docker_cleanup.sh` が登録されているか確認

---

## ゲート 9: PR merge 前チェック (大型 PR)

以下のいずれかに該当する PR は **CI all green 必須**。red のまま merge 禁止。

**大型 PR 判定条件 (ⓐⓑⓒ いずれか 1 つ該当で大型)**

| 条件 | 内容 | 例 |
|------|------|----|
| ⓐ 大 diff | 100行超 diff OR Tier S ファイル変更 | main.py / docker-compose / migrations / models / package.json / requirements.txt |
| ⓑ 多ディレクトリ | 3 ディレクトリ以上にまたがる変更 | backend/ + frontend/ + docs/ |
| ⓒ 古い PR | 起票から 7日超の PR | |

**merge 必須条件**

```
✅ CI 必須 pass: ruff lint/format, mypy, pytest (coverage 80%+), tsc --noEmit, npm run build
✅ CI 必須 pass: E2E Smoke Tests — merge gate (feat/gate1-e2e-staging PR #550 以降)
   ⚠️  失敗時: まず「Staging healthcheck (前段)」ステップを確認すること
              前段 healthcheck が失敗 → staging down が原因 (コードバグではない)
              前段 healthcheck が成功 → smoke test 自体の失敗 → コード修正必須
❌ 禁止: その他の CI red 状態での merge
```

**CI merge gate の正本: `ci.yml` の `Lint (ruff + mypy)` ジョブ**

> `pr-lint-report.yml` (`Ruff + Mypy + Pytest → PR Comment` ジョブ) は **参考表示専用**。
> このジョブを merge gate の根拠にしてはならない。
>
> 理由: `pr-lint-report.yml` の各ステップは `cmd 2>&1 | tee out; echo "exit_code=$?"` 形式で
> パイプ末尾 `tee` の exit code (常に 0) を記録するため、前段コマンド (ruff / mypy / pytest)
> が失敗しても「成功」として記録してしまう構造バグが存在した (2026-05-29 PR #469 で修正済)。
> このバグが存在した期間、PR Lint Report が緑でも実際には違反がある状態が継続した。
>
> **正しい確認方法**: PR の `CI` ワークフロー内の `Lint (ruff + mypy)` ジョブが ✅ であること。
> `PR Lint Report` の ✅ だけを見て merge してはならない。

**違反事例**

- **(2026-05-21)** #347 (F-13 InvestmentTier 削除, 3ディレクトリ跨ぎ) が red CI のまま merge → 残骸 PR が 2件発生 (#351 ruff fix / #355 pytest fix)、main 赤化で当日の他 PR merge ゲートをブロック
- **(2026-05-29)** `pr-lint-report.yml` の tee/pipefail バグで PR Lint Report が常に緑を返す「嘘の緑」が発生。ruff format 違反を含む複数 PR (#458〜#468) が main に merge され、`Lint (ruff + mypy)` ジョブが #458 以降ずっと赤になった。PR #469 で3ファイル整形 + pipefail バグ修正により解消。#347 (2026-05-21) と同種のパターン。

---

## 緊急時参照

| 事象 | 対応 |
|------|------|
| ディスク 90% 超 (L7 CRITICAL) | `scripts/periodic_docker_cleanup.sh` 手動実行 |
| postgres SIGKILL / exit 137 | `docs/postmortems/2026-05-17_loki_postgres_cascade.md` |
| バックアップ空ファイル | `docs/postmortems/2026-05-17_backup_silent_failure.md` |
| nginx 502 (upstream IP 固着) | `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` |
| staging cloudflared 502 | `docs/postmortems/2026-05-09_staging_api_502.md` |
| frontend build env 未焼き込み | CLAUDE.md §2026-05-03 Lesson Learned |
| DB 接続 500 エラー | CLAUDE.md §2026-04-02追加（Docker Compose プロジェクト名） |

---

*GID 1214888902535109 / 2026-05-20*
