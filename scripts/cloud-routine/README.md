# scripts/cloud-routine — Cloud Routine スクリプト群

Ultra AutoTrade の定期自動実行スクリプト群。
Slack `#ultra-auto-project` への通知を標準インターフェースとして使用する。

---

## スクリプト一覧

| ファイル | 役割 | 推奨実行頻度 |
|---------|------|-------------|
| `expired_tasks_monitor.sh` | Asana 期限超過タスク検出 → Slack 通知 | 毎朝 8:00 JST |
| `hf_monitor.sh` | Aave V3 Health Factor 監視 → Slack 警告/アラート | 15 分間隔 |
| `db_schema_diff.sh` | models.py vs 実 DB カラム差分検出 → Slack 通知 | 毎日 9:00 JST |
| `yamamoto_24h_observer.sh` | テスター山本さん 24h 行動観察 (L6 担当) | 別スケジュール |

> `yamamoto_24h_observer.sh` は L6 レーンが管理。本ディレクトリで共存するが目的は異なる。

---

## 共通仕様

- **通知先**: Slack `#ultra-auto-project` (Webhook: `SLACK_WEBHOOK_URL`)
- **ログ**: 標準出力 + `>> /var/log/ultra/<script>.log` にリダイレクト推奨
- **DRY_RUN**: `DRY_RUN=true` を設定すると Slack 通知をスキップしてログのみ出力
- **終了コード**: 0 = 正常, 1 = エラー or アラート検出

---

## 各スクリプトの詳細

### expired_tasks_monitor.sh

Asana の複数プロジェクトから期限超過タスクを検出し、件数と上位 5 件を通知する。

**必須環境変数:**

| 変数 | 説明 |
|------|------|
| `ASANA_PAT` | Asana Personal Access Token |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |

**オプション環境変数:**

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `MAX_REPORT_TASKS` | 5 | 通知する上位タスク数 |
| `DRY_RUN` | false | true のとき Slack 通知をスキップ |

**監視プロジェクト GID 一覧:**
スクリプト内 `PROJECT_GIDS` 配列に定義済み (8 プロジェクト)。

---

### hf_monitor.sh

production backend API (`/api/aave/status`) 経由で Aave V3 Health Factor を取得し、
閾値を下回った場合に Slack 通知を送る。

**必須環境変数:**

| 変数 | 説明 |
|------|------|
| `INTERNAL_API_TOKEN` | backend 内部 API トークン |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |

**オプション環境変数:**

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `BACKEND_URL` | `https://api.ultra-auto-trade.com` | backend URL |
| `HF_WARN_THRESHOLD` | 1.8 | 警告閾値 |
| `HF_ALERT_THRESHOLD` | 1.6 | アラート閾値 |
| `DRY_RUN` | false | true のとき Slack 通知をスキップ |

**通知レベル:**

| 条件 | レベル | 内容 |
|------|--------|------|
| HF >= 1.8 | 正常 | 通知なし |
| 1.6 <= HF < 1.8 | ⚠️ 警告 | Slack に HF 低下を通知 |
| HF < 1.6 | 🚨 アラート | Slack に緊急通知 + 緊急停止フラグ確認を促す |

**緊急停止フラグ確認コマンド (アラート発生時):**
```bash
curl -sf https://api.ultra-auto-trade.com/health | jq '.emergency_stop'
```

---

### db_schema_diff.sh

`backend/app/*/models.py` で定義された `__tablename__` を元に、
production (および任意で staging) DB の実テーブル存在を確認し、
不在のテーブルを Slack に通知する。

**必須環境変数:**

| 変数 | 説明 |
|------|------|
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |
| `PROD_DB_CONTAINER` | production postgres コンテナ名 |
| `PROD_DB_USER` | postgres ユーザー名 |
| `PROD_DB_NAME` | postgres DB 名 |

**オプション環境変数:**

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `HETZNER_SSH_HOST` | (なし) | SSH 経由実行時のホスト |
| `HETZNER_SSH_USER` | root | SSH ユーザー名 |
| `HETZNER_SSH_KEY` | `~/.ssh/id_ed25519` | SSH 鍵パス |
| `REPO_PATH` | `/opt/ultra-autotrade` | Hetzner 上のリポジトリパス |
| `CHECK_STAGING` | false | true のとき staging も確認 |
| `STAGING_DB_CONTAINER` | (なし) | staging postgres コンテナ名 |
| `DRY_RUN` | false | true のとき Slack 通知をスキップ |

> **重要**: コンテナ名は `docker ps | grep postgres` で必ず実際の値を確認してから設定すること。
> 推測禁止 (`docs/ops/03_deploy_procedures.md` 参照)。

---

## cron 設定例

### Hetzner VPS (crontab)

```crontab
# Aave Health Factor 監視 (15 分間隔)
*/15 * * * * cd /opt/ultra-autotrade && \
  INTERNAL_API_TOKEN=$(grep INTERNAL_API_TOKEN .env.production | cut -d= -f2-) \
  SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
  bash scripts/cloud-routine/hf_monitor.sh >> /var/log/ultra/hf_monitor.log 2>&1

# 期限超過タスク監視 (毎朝 8:00 JST = 23:00 UTC)
0 23 * * * cd /opt/ultra-autotrade && \
  ASANA_PAT=$(grep ASANA_PAT .env.production | cut -d= -f2-) \
  SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
  bash scripts/cloud-routine/expired_tasks_monitor.sh >> /var/log/ultra/expired_tasks_monitor.log 2>&1

# DB スキーマ差分チェック (毎日 9:00 JST = 00:00 UTC)
0 0 * * * cd /opt/ultra-autotrade && \
  PROD_DB_CONTAINER=$(docker ps --format '{{.Names}}' | grep postgres | grep production) \
  PROD_DB_USER=ultra PROD_DB_NAME=ultra_autotrade \
  SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-) \
  bash scripts/cloud-routine/db_schema_diff.sh >> /var/log/ultra/db_schema_diff.log 2>&1
```

### Mac (launchd) — SSH 経由でリモート実行

```xml
<!-- ~/Library/LaunchAgents/com.ultra-autotrade.hf-monitor.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ultra-autotrade.hf-monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/hkobayashi/projects/ultra-autotrade/scripts/cloud-routine/hf_monitor.sh</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HETZNER_SSH_HOST</key>
        <string>77.42.46.155</string>
        <key>HETZNER_SSH_USER</key>
        <string>root</string>
        <key>BACKEND_URL</key>
        <string>https://api.ultra-auto-trade.com</string>
    </dict>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>StandardOutPath</key>
    <string>/var/log/ultra/hf_monitor.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/ultra/hf_monitor.err</string>
</dict>
</plist>
```

launchd 登録:
```bash
launchctl load ~/Library/LaunchAgents/com.ultra-autotrade.hf-monitor.plist
```

---

## 障害時のフォールバック手順

### hf_monitor.sh が接続エラーを返す場合

1. backend が起動しているか確認:
   ```bash
   ssh root@77.42.46.155 'docker ps | grep backend'
   ```
2. `/health` エンドポイントを直接確認:
   ```bash
   curl -sf https://api.ultra-auto-trade.com/health | jq .
   ```
3. Aave ポジションを直接確認:
   ```bash
   ssh root@77.42.46.155 'docker logs ultra-autotrade-backend-production 2>&1 | grep -i aave | tail -20'
   ```

### expired_tasks_monitor.sh が API エラーを返す場合

1. Asana PAT の有効期限を確認 (Asana 設定画面 → My Profile → Apps)
2. 手動確認:
   ```bash
   curl -H "Authorization: Bearer ${ASANA_PAT}" \
     "https://app.asana.com/api/1.0/users/me" | jq .
   ```

### db_schema_diff.sh でテーブル不在が検出された場合

1. `docs/ops/02_db_tables.md` で期待カラム定義を確認
2. 対象テーブルの ALTER TABLE を実行:
   ```bash
   # コンテナ名を実際に確認してから実行
   docker ps | grep postgres
   docker exec <container> psql -U ultra -d ultra_autotrade -c \
     "SELECT column_name FROM information_schema.columns WHERE table_name='<table>';"
   ```
3. `docs/ops/03_deploy_procedures.md` の DB 操作手順に従う

---

## ログファイル管理

```bash
# ログディレクトリ作成 (初回のみ)
mkdir -p /var/log/ultra

# ログローテーション (logrotate 設定例: /etc/logrotate.d/ultra-cloud-routine)
/var/log/ultra/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```
