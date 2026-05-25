# 18_scheduler_and_cron.md
Ultra AutoTrade – スケジューラ & cron 設定ガイド

> **改訂 2026-05-25 (Asana 1215028941466139):** in-repo source-of-truth はまだ存在せず、本ドキュメントを正本扱いする。
> 旧記述 (backup.sh + monitor.sh のみ) は実態と乖離していたため、production / staging 両方の現状を反映。

本ドキュメントは Ultra AutoTrade の自動ジョブを Linux サーバ (Hetzner VPS) で実行するための構成と cron 例をまとめる。

ジョブは大きく **2 系統**:
1. **外部 cron** (`crontab -e` 経由) — バックアップ、HF 監視、Asana / DB 監査、スキーマ差分など
2. **内部 scheduler** (Python AsyncIO `backend/app/automation/scheduled_tasks.py` 経由) — daily/weekly/monthly レポート、月次手数料バッチ、AI judgment loop など

両者は独立。**cron の役割は「アプリ外部からトリガすべきもの」** に限定し、**アプリ内部 loop は Python scheduler が持つ**。

---

## 1. ジョブ一覧と目的

### 1.1 PostgreSQL バックアップ (env-aware) — `backup_db.sh`

- 実体スクリプト: `scripts/backup_db.sh`
- 対象: production / staging-new (ENV で切替)
- 自己検証: ファイルサイズ ≥ 10KB + gzip 整合性 + Slack 成否通知
- 月次アーカイブ: 月の最初の backup を `db_backups/monthly/` にコピー、6 ヶ月保持
- 推奨タイミング: **毎日 03:00 JST** (UAT 動線がない時間帯)
- ログ: `/var/log/ultra-autotrade/backup.log`

```cron
0 3 * * * ENVIRONMENT=production /opt/ultra-autotrade/scripts/backup_db.sh \
  >> /var/log/ultra-autotrade/backup.log 2>&1
```

> 詳細: `docs/31_backup_restore_procedures.md` / `docs/ops/backup_restore_runbook.md` (W0-1)

### 1.2 旧 `backup.sh` (Notion 撤去前のラッパー、現在は SubProcess)

- `scripts/backup.sh` は `backend/app/automation/jobs.py backup-only` を呼ぶ薄ラッパー
- **新規 production cron からは利用しない**。後方互換のため残存。新規導入は §1.1 を使用。

### 1.3 監視 / レポート (`monitor.sh daily / weekly`)

- `scripts/monitor.sh daily` — `/health` 死活 + レイテンシ計測。`/var/log/ultra/monitor_daily.log`
- `scripts/monitor.sh weekly` — 週次集計
- 推奨タイミング: 毎日 00:30 / 毎週月曜 01:00 (JST)
- **注**: 重要レポート (月次手数料 / 取引集計) は内部 scheduler (§1.7) が担当。`monitor.sh` は HTTP 死活の補助に位置付け。

### 1.4 HTTP ヘルスチェック (1 分間隔)

- 実装: `scripts/healthcheck_l1_l6.sh` (L1〜L6 段階チェック) もしくは単純 `curl /health`
- 簡易: 1 分間隔の `curl` を cron で。重い L1-L6 は §1.6 で別系統。

```cron
* * * * * cd /opt/ultra-autotrade && curl -fsS http://localhost:8000/health \
  >> /var/log/ultra/healthcheck.log 2>&1
```

### 1.5 Cloud-routine cron (本番運用の主要 cron) — `scripts/cloud-routine/`

`scripts/cloud-routine/` 配下のスクリプトは Hetzner VPS の crontab で実運用される。詳細は `scripts/cloud-routine/README.md` 参照。

| ジョブ | スクリプト | 頻度 | 目的 |
|---|---|---|---|
| Aave HF monitor | `hf_monitor.sh` | 15 分 | Health Factor 監視 + 閾値割れで Slack alert |
| Asana 期限超過 | `expired_tasks_monitor.sh` | 毎朝 8:00 JST | 期限切れタスクを Slack 通知 |
| DB スキーマ差分 | `db_schema_diff.sh` | 毎日 9:00 JST | prod DB と repo migration の差分検知 |

```cron
# Aave Health Factor 監視 (15 分間隔)
*/15 * * * * cd /opt/ultra-autotrade && \
  INTERNAL_API_TOKEN=$(grep INTERNAL_API_TOKEN .env.production | cut -d= -f2-) \
  SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
  bash scripts/cloud-routine/hf_monitor.sh >> /var/log/ultra/hf_monitor.log 2>&1

# Asana 期限超過 (毎朝 8:00 JST = 23:00 UTC)
0 23 * * * cd /opt/ultra-autotrade && \
  ASANA_PAT=$(grep ASANA_PAT .env.production | cut -d= -f2-) \
  SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
  bash scripts/cloud-routine/expired_tasks_monitor.sh \
    >> /var/log/ultra/expired_tasks_monitor.log 2>&1

# DB スキーマ差分 (毎日 9:00 JST = 00:00 UTC)
0 0 * * * cd /opt/ultra-autotrade && \
  PROD_DB_CONTAINER=$(docker ps --format '{{.Names}}' | grep postgres | grep production) \
  PROD_DB_USER=ultra PROD_DB_NAME=ultra_autotrade \
  SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
  bash scripts/cloud-routine/db_schema_diff.sh >> /var/log/ultra/db_schema_diff.log 2>&1
```

### 1.6 staging 復旧 watchdog — `staging-watchdog.sh`

- 実体: `scripts/staging-watchdog.sh`
- 役割: staging stack の落ちたコンテナを **既存 image で** 再起動 (build はしない、`--no-build` 強制)
- 多重起動防止: `flock`
- Image 欠落時: build を誘発せず Slack alert で人手介入待ち (PR #376 設計)
- 推奨タイミング: 5 分間隔
- **OOM 螺旋対策後、cron 再有効化は人手判断**。`docs/postmortems/2026-05-22_staging_stack_oom.md` §7 AI #2 参照。

```cron
# (一時無効化中) staging watchdog
# */5 * * * * /opt/ultra-autotrade/scripts/staging-watchdog.sh >> /var/log/ultra/watchdog.log 2>&1
```

### 1.7 内部 scheduler (Python AsyncIO) — `backend/app/automation/scheduled_tasks.py`

cron では起動しない。**FastAPI 起動時に `ScheduledTaskManager` が同時に起動**し、以下を内部 loop で回す:

| Loop | 周期 | 役割 |
|---|---|---|
| AI judgment | 設定 (`AI_JUDGMENT_INTERVAL_SECONDS`) | Aave + Bybit 取得 → LLM 判定 → proposals 起票 |
| Daily report | 毎日 (`DAILY_REPORT_TIME` JST) | 日次レポート Slack 通知 |
| Weekly report | 毎週 月曜 (`WEEKLY_REPORT_TIME` JST) | 週次サマリ |
| Monthly fee batch | 毎月 1 日 (`MONTHLY_FEE_BATCH_TIME` JST) | 月次手数料計算 (F-7) |
| Rebalance | 設定 | Aave rebalance 判定 (`rebalance_job.py`) |
| Scheduler watchdog | 設定 | Blue/Green color 判定で二重起動防止 (PR #373) |

> Python loop の中断 (FastAPI 落ち) を検知するのは §1.4 / §1.5 / §1.6 の **外部** cron 群の責務。

---

## 2. 推奨スケジュール (一覧 / production 実態)

| ジョブ名 | 系統 | スクリプト | タイミング (JST) | ログ |
|---|---|---|---|---|
| `backup_db_production` | 外部 cron | `scripts/backup_db.sh` (ENV=production) | 毎日 03:00 | `/var/log/ultra-autotrade/backup.log` |
| `hf_monitor` | 外部 cron | `scripts/cloud-routine/hf_monitor.sh` | 15 分間隔 | `/var/log/ultra/hf_monitor.log` |
| `expired_tasks_monitor` | 外部 cron | `scripts/cloud-routine/expired_tasks_monitor.sh` | 毎朝 08:00 | `/var/log/ultra/expired_tasks_monitor.log` |
| `db_schema_diff` | 外部 cron | `scripts/cloud-routine/db_schema_diff.sh` | 毎日 09:00 | `/var/log/ultra/db_schema_diff.log` |
| `healthcheck` (簡易) | 外部 cron | `curl /health` | 毎分 | `/var/log/ultra/healthcheck.log` |
| `monitor_daily` | 外部 cron (staging テンプレ) | `scripts/monitor.sh daily` | 毎日 00:30 | `/var/log/ultra/monitor_daily.log` |
| `monitor_weekly` | 外部 cron (staging テンプレ) | `scripts/monitor.sh weekly` | 毎週月曜 01:00 | `/var/log/ultra/monitor_weekly.log` |
| `staging-watchdog` | 外部 cron (一時無効) | `scripts/staging-watchdog.sh` | 5 分 (停止中) | `/var/log/ultra/watchdog.log` |
| `ai_judgment_loop` | **内部 (Python)** | `scheduled_tasks.py` | 連続 | アプリログ |
| `daily_report` / `weekly_report` / `monthly_fee_batch` | **内部 (Python)** | `scheduled_tasks.py` | JST 設定値 | アプリログ |

> サーバ TZ が UTC の場合は JST から -9h オフセット。

---

## 3. staging 環境向け crontab 設定例 (テンプレ)

> **production 用は §1.5 (cloud-routine) と §1.1 (backup_db)、staging は本節**。両者を混同しない。

### 3.1 前提

- プロジェクトルート: `/opt/ultra-autotrade`
- ログディレクトリ: `/var/log/ultra` (`mkdir -p && chown ultra:ultra`)

### 3.2 crontab 設定例 (`crontab -e`)

```cron
# Ultra AutoTrade (staging) cron jobs
# TZ: Asia/Tokyo (サーバ設定推奨)

# 1) HTTP ヘルスチェック (毎分)
* * * * * cd /opt/ultra-autotrade && curl -fsS http://localhost:8000/health \
  >> /var/log/ultra/healthcheck.log 2>&1

# 2) 毎日 03:00 にバックアップ (staging-new DB)
0 3 * * * ENVIRONMENT=staging-new /opt/ultra-autotrade/scripts/backup_db.sh \
  >> /var/log/ultra-autotrade/backup.log 2>&1

# 3) 毎日 00:30 に日次監視
30 0 * * * cd /opt/ultra-autotrade && ./scripts/monitor.sh daily \
  >> /var/log/ultra/monitor_daily.log 2>&1

# 4) 毎週 月曜 01:00 に週次監視
0 1 * * 1 cd /opt/ultra-autotrade && ./scripts/monitor.sh weekly \
  >> /var/log/ultra/monitor_weekly.log 2>&1
```

> スクリプトには `chmod +x scripts/*.sh` を付ける。`set -euo pipefail` で異常時即終了 → cron は「失敗」扱い。

---

## 4. エラー時の扱いと再実行

### 4.1 スクリプト挙動
- `set -euo pipefail` で異常即終了、終了ステータス非ゼロ
- `backup_db.sh` のみ **ERR trap で Slack 失敗通知**を送る (§1.1)

### 4.2 再実行戦略
- 専用リトライスクリプトは持たない
- 自動: 次のスケジュール時刻で cron が自動再実行
- 手動: オペレータが該当ジョブを単発実行 (`cd /opt/ultra-autotrade && ENVIRONMENT=production scripts/backup_db.sh`)
- 連続失敗時: `docs/15_rollback_procedures.md` / `docs/ops/backup_restore_runbook.md` / §4.5 緊急停止フローを検討

### 4.5 緊急停止フラグと自動ジョブの関係

緊急停止フラグ (`state.json` の `emergency_stop`) が ON のとき:

- **停止するもの**: 新規トレード執行、Aave ポジション変更、AI 判定に基づく自動 action
- **継続するもの**: 監視 (`monitor.sh` / `hf_monitor.sh`)、バックアップ (`backup_db.sh`)、ログ出力

> 観測・記録は止めず、危険アクションのみ即停止。後追い RCA を可能にする方針。

OR-logic のため、コードや scheduler が自動で OFF にすることはない。手動 OFF のみ (`docs/19_operations_runbook.md`)。

---

## 5. ログ出力とローテーション

### 5.1 ログファイル
- `/var/log/ultra-autotrade/backup.log` (backup_db.sh)
- `/var/log/ultra/hf_monitor.log` / `expired_tasks_monitor.log` / `db_schema_diff.log` (cloud-routine)
- `/var/log/ultra/healthcheck.log` / `monitor_daily.log` / `monitor_weekly.log` / `watchdog.log`

すべて `ultra` ユーザが書き込み可能であること。

### 5.2 ログローテーション
- OS 標準 `logrotate` を利用
- 推奨: 日次ローテーション、7-30 世代保持、gzip 圧縮

---

## 6. 実運用への展開

- **staging**: 本ドキュメント §3 を baseline。初期は通知内容を重点確認。
- **production**: §1.1 (`backup_db.sh`) と §1.5 (cloud-routine) を必須。タイミング・通知 channel は本番ポリシーに合わせる。

### 6.1 IN-REPO source-of-truth crontab (NEW · TODO)

実 crontab を repo に取り込む計画 (`infra/cron/production.crontab` 等):

- 利点: 本ドキュメントとの drift を git diff で検知できる
- 課題: secret 直書き禁止 (現状 cron 例は `.env.production` から `grep` で抽出する形式)
- 進め方: 別 PR で `infra/cron/production.crontab.template` を導入 → 本ドキュメントを「実体への参照」に縮小

> 上記の実現までは、本ドキュメントが **正本**。production / staging で crontab を変えるときは必ず本ドキュメントを先に更新する。

---

## 関連

- `scripts/backup_db.sh` (env-aware backup)
- `scripts/cloud-routine/README.md` (本番運用 cron 群)
- `scripts/monitor.sh` / `scripts/healthcheck_l1_l6.sh`
- `backend/app/automation/scheduled_tasks.py` (内部 scheduler)
- `docs/ops/backup_restore_runbook.md` (W0-1)
- `docs/postmortems/2026-05-22_staging_stack_oom.md` (watchdog 螺旋事案)
- `docs/19_operations_runbook.md` (オンコール / 緊急停止フロー)
