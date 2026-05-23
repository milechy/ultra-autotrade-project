# Staging / Prod Build 隔離 Runbook

| 項目 | 値 |
| --- | --- |
| 作成日 | 2026-05-23 |
| オーナー | infra / SRE ロール |
| 関連 Asana | 1215028729779736 (OOM postmortem) |
| 関連 PR | #382 (backend codeploy runbook) / #383 (本 runbook, P0-2) |
| ステータス | Draft (P0-2 implementation) |

---

## 0. クロスリンク索引

| 種類 | 参照先 | 内容 |
| --- | --- | --- |
| Asana | 1215028729779736 | OOM postmortem (2026-05). 本 runbook の起源 |
| Asana | 1214828243363427 | Next.js build OOM の GID (frontend Dockerfile §2026-05-19) |
| Asana | 1214253004741363 | Blue/Green デプロイ導入 (2026-04-27) |
| PR | #382 | backend codeploy runbook (隣接領域、deploy 手順の本体) |
| PR | #383 | 本 runbook (staging/prod build 隔離) |
| Doc | `docs/internal/staging_build_speedup_design.md` | staging build 高速化設計 (並行整備) |
| Compose | `docker-compose.staging.yml` | staging サービス定義。container 名 / ポート / mem_limit を参照 |
| Compose | `docker-compose.production.yml` | prod サービス定義 (本 runbook では参考のみ、変更対象外) |
| Script | `scripts/deploy_staging.sh` | 現行 staging deploy (build → up -d)。本 runbook が記述するホスト build の主実行体 |
| Workflow | `.github/workflows/deploy-staging.yml` | main push → SSH で `deploy_staging.sh` を起動 |
| Workflow | `.github/workflows/ci.yml` | `npm run build` (lint/E2E 用)。**artifact は staging に渡されていない** (§5.4 参照) |
| Dockerfile | `frontend/Dockerfile` | `NODE_OPTIONS=--max-old-space-size=${NODE_BUILD_MAX_OLD_SPACE_SIZE}` (デフォルト 4096) |

---

## 1. 目的

本 runbook は **staging と prod の build を物理的・運用的に隔離する** ためのルールを定義する。

### 1.1 背景

2026-05 に staging ホストで以下の事象が発生した (Asana 1215028729779736)。

- staging ホスト (Hetzner / 7.6GB RAM / swap なし) で `docker compose build --no-cache frontend` を実行
- 同ホストに backend-blue / backend-green / postgres / nginx / loki / promtail / frontend (runtime) が同居
- Next.js build プロセスが `NODE_OPTIONS=--max-old-space-size=4096` で最大 4GB heap を要求
- swap 未設定だったため Linux OOM killer が postgres を kill
- staging が約 12 分間停止、ai_decisions ストリームが欠落

この事象は本質的に「ホスト容量計画の不在」ではなく **「prod-grade build を staging ホストで行うべきではない」** という運用原則の欠如から発生した。本 runbook はそれを明文化する。

### 1.2 スコープ

- frontend (Next.js standalone) の production build
- backend (uvicorn) のコンテナビルド (`docker compose build backend-blue|backend-green`)
- staging ホスト上で許容される build の種類
- swap / メモリ監視ポリシー
- OOM 検知と緊急時の縮退手順

スコープ外:

- prod の build ポリシー(prod は CI のみで build、ホスト上 build は禁止 — 別 runbook)
- CI/CD パイプラインの詳細設計(別 runbook 予定)
- Tier-S ファイル (`backend/app/main.py`, `backend/app/automation/ai_judgment_scheduler.py`, `backend/app/aave/client.py`, 過去 alembic) のコード変更

---

## 2. ルール

### 2.1 staging ホスト build 禁止原則

**staging ホスト上で frontend production build を `--no-cache` で実行してはならない (例外条件下のみ可)。**

現状 (2026-05) は `scripts/deploy_staging.sh` が `docker compose build --no-cache frontend` を実行しているため、暫定的に以下の条件を必須とする:

- 直前に §3 のチェックリストを **全項目満たした上で** 着手する
- build 中は別ターミナルで `docker stats --no-stream` を 60s 間隔で記録する
- build 完了後に必ず `docker builder prune --filter until=1h -f` を実行

恒久対策 (Phase 2, P1):

- CI で frontend を pre-build し、tar.gz artifact を `actions/upload-artifact` で保管
- staging deploy 時に GHA から SSH で artifact を `/opt/ultra-autotrade/frontend/.next/standalone` に展開
- staging 側は `docker compose up -d frontend` のみ実行 (build フェーズなし)
- §5.4 にフロー詳細

backend の `docker compose build backend-blue|backend-green` は許容するが、CI で image を build して `ghcr.io` へ push する方式に移行することが望ましい。

### 2.2 swap 維持

staging ホストには **必ず swap を 2GB 以上** 確保する。

- 経緯: 2026-05 セッションで swap (2GB, `/swapfile`, `swappiness=10`) を投入
- 現状値: swap 2.0GB、`vm.swappiness=10`
- 推奨値: swap 2.0GB 以上、`vm.swappiness=10` (build 時のみ一時的に最大 30 を許容)

確認コマンド:

```bash
# swap が有効か
swapon --show
# 期待値: NAME      TYPE  SIZE USED PRIO
#         /swapfile file   2G   0B  -2

# swappiness 現在値
sysctl vm.swappiness
# 期待値: vm.swappiness = 10

# fstab に永続化されているか
grep -E '^/swapfile' /etc/fstab
# 期待値: /swapfile none swap sw 0 0
```

swap はあくまでセーフティネットであり、定常的に使われる前提では設計しない (Used 列が定常 256MB 超なら容量計画見直し)。

### 2.3 同居ホスト負荷監視

staging は `ultra-autotrade-{loki,promtail,postgres,backend-blue,backend-green,nginx,frontend}-staging-new` (7 コンテナ) が同居する。常時以下の閾値を維持:

| メトリクス | warning | critical | 取得 |
| --- | --- | --- | --- |
| `MemAvailable` | < 1.5 GB | < 500 MB | `awk '/MemAvailable/ {print $2}' /proc/meminfo` |
| swap 使用 (定常) | > 256 MB | > 1 GB | `free -m \| awk '/Swap/ {print $3}'` |
| load average (1m) | > CPU数 × 1.5 | > CPU数 × 3 | `uptime` / `cat /proc/loadavg` |
| postgres RSS | > 400 MB | > 480 MB | `docker stats ultra-autotrade-postgres-staging-new --no-stream` |
| backend (active) RSS | > 600 MB | > 720 MB | `docker stats ultra-autotrade-backend-blue-staging-new --no-stream` |
| dmesg `oom-killer` | ≥ 1 回 / 24h | ≥ 1 回 / 1h | `dmesg --since '1 hour ago' \| grep -c oom_reaper` |

warning を下回るときは新規 build / deploy を **着手しない**。critical の場合は §4.3 縮退手順を検討。

メモリ予算 (compose の `mem_limit` 合計):

- loki 384m + promtail 128m + postgres 512m + backend-blue 768m + backend-green 768m + nginx 64m + frontend 512m = **3136m**
- これに対して staging-new は **7.6GB RAM**。残り 4.4GB がホスト OS + build バッファ
- Next build は host swap を併用して最大 4GB heap を確保 (frontend Dockerfile L58 `NODE_OPTIONS=--max-old-space-size=4096`)

---

## 3. Deploy 前チェックリスト

deploy / build 着手前に以下を順に確認する。チェックを 1 つでも満たさない場合は着手不可。

### 3.1 ホスト健全性

- [ ] `docker compose ps` で 7 コンテナが全て `Up (healthy)` または `Up`
- [ ] `docker stats --no-stream` で各コンテナの MEM USAGE を記録し §2.3 閾値内
- [ ] `free -h` で `MemAvailable >= 1.5GB`
- [ ] `swapon --show` で `/swapfile` が enable 状態かつ Used が 256MB 未満
- [ ] `uptime` で load average (1m) が CPU 数 × 1.5 未満
- [ ] `dmesg --since '24 hour ago' | grep -i 'killed process'` が空

```bash
# まとめて確認するワンライナー (staging)
cd /opt/ultra-autotrade && \
  echo "=== docker ===" && \
  docker compose -f docker-compose.staging.yml --env-file .env.staging-new ps && \
  echo "=== docker (json) ===" && \
  docker compose -f docker-compose.staging.yml --env-file .env.staging-new ps --format json | jq '.[] | {name: .Name, state: .State, status: .Status}' && \
  echo "=== mem ===" && free -h && \
  echo "=== meminfo ===" && grep -E 'MemAvailable|SwapTotal|SwapFree' /proc/meminfo && \
  echo "=== swap ===" && swapon --show && \
  echo "=== swappiness ===" && sysctl vm.swappiness && \
  echo "=== load ===" && uptime && \
  echo "=== oom (24h) ===" && (dmesg --since '24 hour ago' 2>/dev/null | grep -iE 'killed process|oom-kill|oom_reaper' || echo 'no OOM events') && \
  echo "=== stats ===" && docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}'
```

### 3.2 artifact 健全性

- [ ] CI lint / ci.yml の最新 run が green (`gh run list --workflow=ci.yml --branch=main --limit 1`)
- [ ] `git rev-parse HEAD` (host) と `gh run view <run-id> --json headSha` の SHA 一致
- [ ] backend `Dockerfile` / `frontend/Dockerfile` が変更されていれば mem_limit の妥当性を再評価

```bash
# CI run SHA 突合
gh run list --workflow=ci.yml --branch=main --limit 1 --json headSha,conclusion,createdAt
git rev-parse HEAD
```

### 3.3 ロールバック準備

- [ ] 直前のイメージ ID が控えてある (`docker images ultra-autotrade-staging-new-frontend --format '{{.ID}} {{.CreatedAt}}'`)
- [ ] postgres の論理 backup (`pg_dump`) が 24h 以内にある (`ls -lh /opt/ultra-autotrade/backups/postgres-staging-*.sql.gz | tail -3`)
- [ ] rollback コマンドを 1 行で実行できる状態 (history に残す or `~/rollback.sh` に pin)
- [ ] Blue/Green の inactive 側が直前バージョンで起動可能か確認 (`docker compose -f docker-compose.staging.yml ps backend-green` 等)

---

## 4. 緊急時挙動

### 4.1 OOM kill 発生時の検知と対応

事象: `dmesg | grep -i 'killed process'` で OOM killer のログが出る、または `docker compose ps` で特定コンテナが `Exited (137)`、または systemd-journald に `Out of memory: Killed process` が記録される。

#### Step 1: 影響範囲の確定

```bash
# 1) カーネル ringbuffer から OOM killer のログ抽出
sudo dmesg -T | grep -iE 'killed process|oom-kill|oom_reaper' | tail -20

# 2) journalctl 経由 (再起動を跨いだ場合はこちらが確実)
sudo journalctl -k --since '2 hour ago' | grep -iE 'killed process|oom-kill|memory cgroup out of memory'

# 3) どの cgroup (= どのコンテナ) で発生したか
sudo journalctl -k --since '2 hour ago' | grep -oE 'oom-kill:.*' | sort -u

# 4) コンテナの最終 exit code (137 = OOM, 143 = SIGTERM)
docker compose -f /opt/ultra-autotrade/docker-compose.staging.yml ps -a
docker compose -f /opt/ultra-autotrade/docker-compose.staging.yml ps --format json \
  | jq '.[] | select(.ExitCode != 0 and .ExitCode != null) | {name: .Name, exit: .ExitCode, status: .Status}'

# 5) postgres が殺された場合、WAL の整合性を最初に確認
docker compose -f /opt/ultra-autotrade/docker-compose.staging.yml exec postgres \
  pg_controldata /var/lib/postgresql/data | head -20
```

#### Step 2: 復旧

```bash
cd /opt/ultra-autotrade
COMPOSE="docker compose -f docker-compose.staging.yml --env-file .env.staging-new"

# 1) 殺された service を識別
KILLED=postgres   # 例: 上記 Step 1 の出力から決定

# 2) 単体起動して log を見る
${COMPOSE} up -d ${KILLED}
${COMPOSE} logs --tail=200 ${KILLED}

# 3) healthy 化を待つ (最大 5 分)
for i in $(seq 1 60); do
  if ${COMPOSE} ps ${KILLED} --format json | jq -e '.[].Health == "healthy"' > /dev/null 2>&1; then
    echo "${KILLED} healthy"; break
  fi
  sleep 5
done

# 4) 依存 service を順に起動 (staging は postgres → backend-{blue,green} → nginx → frontend → loki/promtail)
${COMPOSE} up -d backend-blue backend-green
${COMPOSE} up -d nginx
${COMPOSE} up -d frontend
${COMPOSE} up -d loki promtail

# 5) 復旧確認 (nginx 経由 /health が 5 連続 200)
for i in $(seq 1 10); do
  curl -sf -o /dev/null -w '%{http_code}\n' -m 5 http://127.0.0.1:8082/health
  sleep 2
done | sort | uniq -c

# 6) ai_decisions の書込再開を確認 (staging は shadow mode で記録継続が期待値)
docker compose -f docker-compose.staging.yml exec postgres \
  psql -U ultra -d ultra_autotrade_staging -c \
  "SELECT count(*), max(created_at) FROM ai_decisions WHERE created_at > now() - interval '30 minutes';"
```

#### Step 3: postmortem 起票

- Asana に postmortem task を作成 (template: P1, parent: 1215028729779736)
- 5 whys を 3 営業日以内に埋める
- 本 runbook と Asana 1215028729779736 を参照に追加
- §2.3 閾値違反だった場合は閾値の見直しを起票

### 4.2 swap が unmount された場合

事象: `free -h` で Swap 行が `0B`、または `swapon --show` が空。

```bash
# 1) swapfile の存在確認
ls -lh /swapfile

# 2) 存在するなら enable
sudo swapon /swapfile

# 3) 存在しなければ作成
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 4) fstab に永続化(既存行がなければ)
grep -q '/swapfile' /etc/fstab || \
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 5) swappiness 再設定
sudo sysctl vm.swappiness=10
grep -q '^vm.swappiness' /etc/sysctl.conf || \
  echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf

# 6) 確認
swapon --show && sysctl vm.swappiness
# 期待値: NAME=/swapfile SIZE=2G PRIO=-2 / vm.swappiness = 10
```

### 4.3 staging を一時的に縮退する手順

メモリ逼迫時 (`MemAvailable < 500MB` critical) に staging を最小構成へ落とす。コンテナ停止順は **frontend → backend-green (inactive) → backend-blue (active) → nginx → promtail → loki → postgres** を守る (上位ほど末端、下位ほど依存される側)。

postgres は最後まで残し、必ず graceful stop (-t 30) する。

```bash
cd /opt/ultra-autotrade
COMPOSE="docker compose -f docker-compose.staging.yml --env-file .env.staging-new"

# 1) frontend を停止 (ユーザー影響あり、最初に告知)
${COMPOSE} stop -t 10 frontend
# 実体: ultra-autotrade-frontend-staging-new

# 2) backend inactive (green) を停止 (まず予備系から)
${COMPOSE} stop -t 30 backend-green
# 実体: ultra-autotrade-backend-green-staging-new

# 3) backend active (blue) を停止
${COMPOSE} stop -t 30 backend-blue
# 実体: ultra-autotrade-backend-blue-staging-new
# 注意: scheduler は backend 内で動作。ここで ai_decisions の書込が停止する

# 4) nginx を停止 (もう upstream がいない)
${COMPOSE} stop -t 5 nginx

# 5) promtail → loki (ログパイプライン)
${COMPOSE} stop -t 5 promtail
${COMPOSE} stop -t 10 loki

# 6) postgres は最後まで残す。停止する場合は必ず graceful (-t 30)
${COMPOSE} stop -t 30 postgres
```

復帰時は逆順:

```bash
cd /opt/ultra-autotrade
COMPOSE="docker compose -f docker-compose.staging.yml --env-file .env.staging-new"

# 1) postgres → healthy 待ち
${COMPOSE} up -d postgres
for i in $(seq 1 60); do
  ${COMPOSE} ps postgres --format json | jq -e '.[].Health == "healthy"' > /dev/null 2>&1 && break
  sleep 5
done

# 2) loki → promtail
${COMPOSE} up -d loki
${COMPOSE} up -d promtail

# 3) backend (active 側を先に。ACTIVE_BACKEND_COLOR を .env.staging-new から確認)
ACTIVE=$(grep '^ACTIVE_BACKEND_COLOR=' .env.staging-new | cut -d= -f2)
INACTIVE=$([ "${ACTIVE}" = "blue" ] && echo "green" || echo "blue")
${COMPOSE} up -d backend-${ACTIVE}
for i in $(seq 1 60); do
  curl -sf -o /dev/null -w '%{http_code}' -m 5 \
    http://127.0.0.1:$([ "${ACTIVE}" = "blue" ] && echo 8020 || echo 8021)/health \
    | grep -q 200 && break
  sleep 5
done
${COMPOSE} up -d backend-${INACTIVE}

# 4) nginx
${COMPOSE} up -d nginx

# 5) frontend
${COMPOSE} up -d frontend

# 6) 復帰確認
curl -sf -m 5 http://127.0.0.1:8082/health
docker compose -f docker-compose.staging.yml exec postgres \
  psql -U ultra -d ultra_autotrade_staging -c \
  "SELECT count(*) AS recent_decisions FROM ai_decisions WHERE created_at > now() - interval '10 minutes';"
```

**注意**:

- `ai_judgment_scheduler` は **staging compose に独立サービスとしては存在せず**、backend (blue/green) 内のプロセスとして動作する。停止/復帰は backend と一体。
- DISABLE 系フラグは反転している (staging=ON+shadow / production=OFF)。`AI_SHADOW_MODE=true` / `REBALANCE_SHADOW_MODE=true` が docker-compose.staging.yml で hardcode されている。
- soak 検証中に scheduler を最後に上げ、`ai_decisions` 件数を必ず monitor する (上記 Step 6 で recent_decisions ≥ 1 を期待値とする。0 件なら scheduler 起動失敗の疑い)。

---

## 5. 参照

### 5.1 Asana

- **1215028729779736** — OOM postmortem (2026-05). 本 runbook の起源。
- **1214828243363427** — Next.js build OOM GID (frontend Dockerfile §2026-05-19)。`NODE_OPTIONS=--max-old-space-size=4096` の根拠。
- **1214253004741363** — Blue/Green デプロイ導入 (2026-04-27)。staging が 2 backend 化された経緯。

### 5.2 PR

- **#382** — backend codeploy runbook (隣接領域、deploy 手順の本体)。
- **#383** — 本 runbook (P0-2, staging/prod build 隔離)。

### 5.3 ホスト設定の経緯

- 2026-04-17: staging を `staging-new` に B 案リネーム。container_name に `-staging-new` suffix。
- 2026-04-24: container_name 衝突インシデント。prod 側を `-production` に統一。
- 2026-04-27: Blue/Green 導入 (Asana 1214253004741363)。backend が `backend-blue` / `backend-green` に分割。
- 2026-05-19: Next build OOM 対策 (Asana 1214828243363427)。`NODE_BUILD_MAX_OLD_SPACE_SIZE` を build arg 化。
- 2026-05-21: loki cascade fix (P0-2)。json-file logging に統一、promtail 経由収集。
- 2026-05-22: 各コンテナに `mem_limit` を設定 (postgres 512m / backend 768m / frontend 512m / loki 384m / promtail 128m / nginx 64m)。
- 2026-05 中旬: swap 2GB 投入、swappiness=10。
- 2026-05: frontend production build を staging ホストで `--no-cache` 実行する運用を本 runbook で明文化(暫定継続、Phase 2 で CI artifact 受渡しに移行)。

### 5.4 CI → staging artifact 引き渡しフロー (現状と移行先)

**現状 (2026-05 時点)**:

```
GHA: deploy-staging.yml (main push)
  └─ appleboy/ssh-action → staging host
       └─ /opt/ultra-autotrade で git reset --hard origin/main
            └─ scripts/deploy_staging.sh
                 ├─ docker compose build --no-cache frontend  ← staging ホスト上で Next build (OOM 元凶)
                 ├─ docker compose build backend-blue backend-green
                 └─ docker compose up -d
```

- artifact の事前 build は無く、`.github/workflows/ci.yml` の `npm run build` は **E2E smoke のためだけ** に実行され staging には渡されない (`actions/upload-artifact` で `playwright-report` のみ保存)。
- `ghcr.io` への image push も未実装 (`grep -rn ghcr.io .github/workflows/` で 0 件)。

**移行先 (Phase 2, P1)**:

```
GHA: build-frontend.yml (新規, main push)
  └─ ubuntu-latest で npm ci && npm run build
       └─ tar czf frontend-${{ github.sha }}.tar.gz frontend/.next/standalone frontend/.next/static frontend/public
            └─ actions/upload-artifact (name: frontend-standalone-${{ github.sha }}, retention 14d)

GHA: deploy-staging.yml (改修, main push, needs: build-frontend)
  └─ actions/download-artifact → tar.gz を runner に取得
       └─ appleboy/scp-action で staging host の /opt/ultra-autotrade/artifacts/ に転送
            └─ appleboy/ssh-action → staging host
                 └─ scripts/deploy_staging.sh --no-build --artifact /opt/ultra-autotrade/artifacts/frontend-<sha>.tar.gz
                      ├─ tar xzf artifact → frontend/.next/standalone
                      └─ docker compose up -d frontend  (build フェーズなし)
```

- 効果: staging ホスト上での Node heap 4GB 確保が消える → postgres OOM の主因が除去される。
- 残課題: backend image も `ghcr.io/uata/backend:<sha>` に push して staging では pull のみにする (Phase 3)。
- 実装 PR は本 runbook merge 後に別 PR で起票。

### 5.5 関連用語

- **Tier-S ファイル**: `backend/app/main.py`, `backend/app/automation/ai_judgment_scheduler.py`, `backend/app/aave/client.py`, 既存 alembic 過去 revision。これらは本 runbook の対象外 (コード変更なし)。
- **shadow mode**: ai_judgment_scheduler が判定するが取引を行わないモード。staging で常用 (`AI_SHADOW_MODE=true`)。
- **soak**: 一定時間連続稼働させて健全性を確認する検証フェーズ。
- **active/inactive color**: Blue/Green で現在 nginx upstream に登録されている色が active。`ACTIVE_BACKEND_COLOR` 環境変数で参照可能。

---

## 6. 改訂履歴

| 日付 | 内容 | 起票 |
| --- | --- | --- |
| 2026-05-23 | 初版 (P0-2, OOM postmortem follow-up) | infra |
| 2026-05-23 | P0-2 実装拡張: 監視コマンド実例 / swap 監視 / アラート閾値数値化 / 縮退手順を実コンテナ名で記述 / CI artifact フロー追記 | infra |
