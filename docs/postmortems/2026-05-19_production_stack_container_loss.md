# Postmortem: 2026-05-19 Production Stack Container Loss (8→1コンテナ)

**発生日時**: 2026-05-19 11:30〜15:06 JST  
**検出日時**: 2026-05-19 15:06 JST (deploy時に発覚)  
**影響範囲**: Production stack 全体 (8コンテナ→1コンテナ)  
**重大度**: P0 (本番機能喪失の可能性)  
**ステータス**: 調査中 (SSH制約により真因未確定)

---

## 事象概要

2026-05-19 11:30頃、production stack は正常に8コンテナ全Up状態だった。
15:06のdeploy作業時点でコンテナ数が1コンテナのみになっていることが確認された。
約3.5時間の間に7コンテナが消失した。

### タイムライン (既知)

| 時刻 | 事象 | 確認者 |
|------|------|--------|
| 11:30 JST | production 8コンテナ全Up確認 | Claude Code セッション |
| ~11:30-15:06 | 不明 (調査コマンド参照) | — |
| 15:06 JST | deploy時に1コンテナのみ確認 | ユーザー |

---

## 調査状況

**制約**: dev VPS (77.42.79.75) から production VPS (77.42.46.155) へのSSH鍵が存在しないため、
Claude Code CLIからの直接調査不可。以下はMacターミナルから実行要。

---

## Phase 1: 現状確認 (Macから実行)

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
echo "=== 現在のコンテナ状態 ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.CreatedAt}}" | grep ultra-autotrade

echo ""
echo "=== 停止中・終了コンテナ (直近7日) ==="
docker ps -a --filter "name=ultra-autotrade" --format "table {{.Names}}\t{{.Status}}\t{{.FinishedAt}}"

echo ""
echo "=== compose stack 確認 ==="
docker compose -f /opt/ultra-autotrade/docker-compose.production.yml \
  --env-file /opt/ultra-autotrade/.env.production ps 2>/dev/null || \
  cd /opt/ultra-autotrade && docker compose -f docker-compose.production.yml --env-file .env.production ps
ENDSSH
```

---

## Phase 2: 真因調査 (Macから実行)

### A. docker events ログ解析

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
echo "=== docker events 11:00-15:30 JST ==="
docker events \
  --since "2026-05-19T02:00:00Z" \
  --until "2026-05-19T06:30:00Z" \
  --filter "type=container" \
  --filter "name=ultra-autotrade" \
  --format "{{.Time}} {{.Actor.Attributes.name}} {{.Action}}" 2>/dev/null | head -100
ENDSSH
```

### B. deploy スクリプト実行履歴

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
echo "=== bash_history (ultra ユーザー) ==="
grep -n "deploy\|docker compose\|docker rm\|docker stop" ~/.bash_history | tail -30

echo ""
echo "=== /opt/ultra-autotrade git log (15:06前後) ==="
cd /opt/ultra-autotrade
git log --oneline --since="2026-05-19 00:00" --format="%h %ai %s"

echo ""
echo "=== deploy_production.sh 最終実行時刻 ==="
ls -la /opt/ultra-autotrade/scripts/deploy_production.sh
ENDSSH
```

### C. systemd / journalctl / OOM

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
echo "=== systemd journalctl (11:00-15:30 JST / docker) ==="
journalctl --since="2026-05-19 02:00:00" --until="2026-05-19 06:30:00" \
  -u docker --no-pager | tail -50

echo ""
echo "=== OOM Killer ログ ==="
journalctl --since="2026-05-19 02:00:00" --until="2026-05-19 06:30:00" \
  -k --no-pager | grep -i "oom\|killed\|out of memory" | head -20

echo ""
echo "=== crontab (ultra ユーザー) ==="
crontab -l 2>/dev/null

echo ""
echo "=== crontab (root) ==="
sudo crontab -l 2>/dev/null || echo "(sudo権限なし)"
ENDSSH
```

### D. nginx / Loki コンテナ状態

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
echo "=== nginx upstream.production.conf (現在) ==="
cat /opt/ultra-autotrade/docker/nginx/upstream.production.conf 2>/dev/null || \
  cat /opt/ultra-autotrade/docker/nginx/upstream.production.conf.bak 2>/dev/null || \
  docker exec ultra-autotrade-nginx-production cat /etc/nginx/conf.d/upstream.conf 2>/dev/null

echo ""
echo "=== backend-blue / backend-green 状態 ==="
docker inspect ultra-autotrade-backend-blue-production 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin)[0]; s=d['State']; print('blue:', s['Status'], 'ExitCode:', s['ExitCode'], 'FinishedAt:', s['FinishedAt'])" || \
  echo "backend-blue-production: not found"
docker inspect ultra-autotrade-backend-green-production 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin)[0]; s=d['State']; print('green:', s['Status'], 'ExitCode:', s['ExitCode'], 'FinishedAt:', s['FinishedAt'])" || \
  echo "backend-green-production: not found"

echo ""
echo "=== backend-production (非blue/green) 状態 ==="
docker inspect ultra-autotrade-backend-production 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin)[0]; s=d['State']; print('backend:', s['Status'], 'ExitCode:', s['ExitCode'], 'FinishedAt:', s['FinishedAt'])" || \
  echo "backend-production: not found"
ENDSSH
```

---

## 仮説 (確度順)

### 仮説1: deploy_production.sh が `docker compose down --remove-orphans` を実行 (確度: 高)

`deploy_production.sh` のフルデプロイは `docker compose down --remove-orphans` を実行する。
11:30〜15:06の間に意図的または誤って `deploy_production.sh` が実行された場合、
compose down でコンテナが一括停止→1コンテナのみが起動した状態で止まった可能性がある。

**確認**: Phase 2-B の bash_history と docker events で deploy コマンドの実行を確認。

### 仮説2: deploy_production.sh の途中失敗 (確度: 中)

フルデプロイが途中で失敗し、compose down 後の compose up が完了しなかった場合。
healthcheck 失敗や DB 接続エラーで早期終了するとコンテナ数が1のみになりうる。

**確認**: Phase 2-B の bash_history + deploy スクリプトのログ出力 (`/tmp/deploy_*.log`等)。

### 仮説3: OOM Killer による連鎖的コンテナ停止 (確度: 中)

2026-05-17 と同型。Loki logging driver が半死状態になりpostgresがSIGKILLされ、
postgres依存コンテナが連鎖停止した場合。

**確認**: Phase 2-C の OOM Killer ログ。

### 仮説4: cron による docker cleanup または down (確度: 低)

`scripts/docker_cleanup.sh` は毎週日曜 03:00 JST。2026-05-19は火曜なのでcronは非対象。
しかし別のcron jobが存在する可能性は排除できない。

**確認**: Phase 2-C の crontab。

### 仮説5: 手動操作ミス (確度: 不明)

ユーザーまたは別セッションが手動でコンテナを停止した可能性。
**確認**: Phase 2-B の bash_history で `docker stop` / `docker rm` の有無。

---

## 既知の影響

- production stack が1コンテナのみの状態でサービス提供能力が大幅低下
- AI判定スケジューラ、Aave rebalance、frontend等が停止していた可能性
- 自動バックアップ (backup_db.sh) が走っていなかった可能性

---

## 再発防止策 (仮)

真因確定後に以下から適用策を選定する:

| 策 | 対象仮説 | 実装難易度 |
|---|---|---|
| deploy_production.sh 実行前の確認プロンプト追加 | 仮説1,2 | 低 |
| Loki logging driver を json-file に変更 (2026-05-17再発防止) | 仮説3 | 中 |
| cron jobの棚卸しと無害化 | 仮説4 | 低 |
| docker events をLoki/ファイルに永続化 | 全般 | 中 |
| コンテナ数監視アラート (8→N コンテナ減少でSlack通知) | 全般 | 中 |

---

## 調査後の追記欄

> 上記Phase 1-2をMacから実行後、結果をここに貼り付けて真因を確定する。

```
# 調査結果:
# 真因:
# 復旧方法:
# 恒久対策:
```

---

## 参照

- [2026-05-17 loki/postgres cascade postmortem](./2026-05-17_loki_postgres_cascade.md)
- [CLAUDE.md §本番デプロイフロー](../../CLAUDE.md)
- [docs/ops/03_deploy_procedures.md](../ops/03_deploy_procedures.md)
