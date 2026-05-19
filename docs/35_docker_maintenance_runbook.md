# 35. Docker Maintenance Runbook

## 概要

Ultra AutoTrade の Hetzner VPS（77.42.46.155）で Docker イメージ・ビルドキャッシュの
蓄積によるディスク逼迫を防ぐための定期メンテナンス runbook。

## 背景

- 2026-04-19 に disk 79%（57G/75G）まで逼迫
- `docker builder prune -f` で 27GB 解放（79%→42%）
- builder cache は 1日 +1GB ペースで再蓄積 → 週次クリーンアップで対応
- `docker system prune -af` は使用中イメージを削除するリスクがあるため **禁止**（CLAUDE.md 明記）

## 運用ポリシー

| 項目 | 方針 |
|---|---|
| 実行スクリプト | `scripts/docker_cleanup.sh` |
| 実行コマンド | `docker builder prune -f` + `docker image prune -f` |
| **禁止コマンド** | **`docker system prune -af`**（使用中イメージ削除リスク） |
| 実行頻度 | 週次（毎週日曜 03:00 JST） |
| ログ | `/opt/ultra-autotrade/logs/docker_cleanup.log` |
| Slack 通知 | `#ultra-auto-project` （`SLACK_WEBHOOK_URL` via `.env.production`） |

## 閾値

| レベル | disk 使用率 | Slack 通知 |
|---|---|---|
| :white_check_mark: OK | < 70% | 実行結果のみ |
| :warning: WARN | 70–84% | 警告メッセージ |
| :rotating_light: CRITICAL | ≥ 85% | 緊急通知 |

閾値は環境変数でオーバーライド可能:

```bash
DOCKER_CLEANUP_WARN_THRESHOLD=60 /opt/ultra-autotrade/scripts/docker_cleanup.sh
```

## cron 登録手順（Hetzner ultra ユーザ）

> **注**: Hetzner サーバーは JST (Asia/Tokyo) 運用。cron 表記は JST で計算する（UTC ではない）。


1. Hetzner に SSH ログイン:
   ```bash
   ssh hetzner
   ```

2. crontab を編集:
   ```bash
   crontab -e
   ```

3. 以下の行を追加:
   ```
   # Docker cleanup - 毎週日曜 03:00 JST
   0 3 * * 0 /opt/ultra-autotrade/scripts/docker_cleanup.sh
   ```

4. 登録を確認:
   ```bash
   crontab -l | grep docker_cleanup
   ```
   既存の `backup_db.sh`（毎日 18:00 JST）と時刻が重複しないことを確認。

## 手動実行

```bash
# デフォルト設定で実行
/opt/ultra-autotrade/scripts/docker_cleanup.sh

# 閾値オーバーライド例
DOCKER_CLEANUP_WARN_THRESHOLD=60 /opt/ultra-autotrade/scripts/docker_cleanup.sh

# staging の .env を参照する場合
DOCKER_CLEANUP_ENV_FILE=/opt/ultra-autotrade/.env.staging-new \
  /opt/ultra-autotrade/scripts/docker_cleanup.sh

# ログ出力先を変える場合
DOCKER_CLEANUP_LOG=/tmp/docker_cleanup_test.log \
  /opt/ultra-autotrade/scripts/docker_cleanup.sh
```

## ログ確認

```bash
# 直近の実行結果（最終50行）
tail -50 /opt/ultra-autotrade/logs/docker_cleanup.log

# エラーのみ抽出
grep "ERROR" /opt/ultra-autotrade/logs/docker_cleanup.log | tail -20

# 実行日時一覧
grep "Docker cleanup started" /opt/ultra-autotrade/logs/docker_cleanup.log
```

## トラブルシューティング

### 想定ケース 1: disk 90% 到達（CRITICAL アラート後も高い）

1. 手動でスクリプト即時実行:
   ```bash
   /opt/ultra-autotrade/scripts/docker_cleanup.sh
   ```

2. それでも減らない場合、内訳を確認:
   ```bash
   docker system df
   docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | sort -k2 -h
   ```

3. 停止中コンテナが大量にある場合（個別に削除）:
   ```bash
   docker ps -a --filter "status=exited" --format "{{.Names}}"
   docker rm <container-name>
   ```

4. dangling volumes の確認と個別削除（稼働コンテナのボリュームは **削除禁止**）:
   ```bash
   docker volume ls -qf dangling=true
   # 安全確認後に個別削除
   docker volume rm <volume-name>
   ```

5. **絶対禁止**: `docker system prune -af` は実行しない（使用中イメージを削除する）

### 想定ケース 2: Slack 通知が来ない

1. SLACK_WEBHOOK_URL が `.env.production` に設定されているか確認:
   ```bash
   grep -c SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production
   ```
   （値は出力しない）

2. 手動で webhook をテスト:
   ```bash
   WEBHOOK=$(grep SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production | cut -d= -f2-)
   curl -s -X POST "$WEBHOOK" -H "Content-Type: application/json" \
     -d '{"text": "test from Hetzner"}' && echo " OK"
   ```

3. Slack 側でアプリの webhook が有効か確認（Slack ワークスペース管理者）

### 想定ケース 3: cron が実行されない

1. cron サービスの状態確認:
   ```bash
   systemctl status cron
   ```

2. crontab 登録の確認:
   ```bash
   crontab -l | grep docker_cleanup
   ```

3. cron ログでエラー確認:
   ```bash
   grep docker_cleanup /var/log/syslog | tail -20
   # または
   journalctl -u cron --since "7 days ago" | grep docker_cleanup
   ```

4. スクリプトの実行権限確認:
   ```bash
   ls -la /opt/ultra-autotrade/scripts/docker_cleanup.sh
   # -rwxr-xr-x になっていること
   ```

### 想定ケース 4: スクリプトが途中で失敗する

1. ログで ERROR 行を確認:
   ```bash
   grep ERROR /opt/ultra-autotrade/logs/docker_cleanup.log | tail -10
   ```

2. Docker デーモンが動いているか確認:
   ```bash
   docker info 2>&1 | head -5
   ```

3. ディスクが完全に埋まった場合は手動でスペースを確保してから再実行

---

## PostgreSQL 週次バックアップ

### 概要

| 項目 | 方針 |
|---|---|
| 実行スクリプト | `scripts/backup_db.sh` |
| 実行頻度 | 週次（毎週日曜 03:00 JST）|
| 保存先 | `/opt/ultra-autotrade/db_backups/` |
| 月次アーカイブ | `/opt/ultra-autotrade/db_backups/monthly/` |
| 保持期間（週次） | 直近 28 日（4 週分） |
| 保持期間（月次） | 6 ヶ月 |
| 検証 | ファイルサイズ 10KB 以上 + gzip 整合性チェック |
| Slack 通知 | 成功/失敗とも `#ultra-auto-project` |

### cron 登録手順（Hetzner ultra ユーザー / 初回のみ）

```bash
# Hetzner VPS にログイン (production VPS: ultra@77.42.46.155)
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155

# crontab 編集
crontab -e

# 以下の行を追加 (毎週日曜 03:00 JST)
0 3 * * 0 ENVIRONMENT=production /opt/ultra-autotrade/scripts/backup_db.sh >> /opt/ultra-autotrade/logs/backup_db.log 2>&1

# 確認
crontab -l | grep backup_db
```

### ログディレクトリ確認

```bash
# ログディレクトリが存在しない場合は作成
mkdir -p /opt/ultra-autotrade/logs

# バックアップ先ディレクトリ確認
ls -lh /opt/ultra-autotrade/db_backups/ 2>/dev/null || echo "ディレクトリなし (初回実行で自動作成)"
```

### 手動実行テスト

```bash
# production VPS で手動実行
ENVIRONMENT=production /opt/ultra-autotrade/scripts/backup_db.sh

# 成功確認
ls -lh /opt/ultra-autotrade/db_backups/production_*.sql.gz | tail -5
ls -lh /opt/ultra-autotrade/db_backups/monthly/ 2>/dev/null
```

### トラブルシューティング

#### バックアップが空 (20 bytes) の場合

2026-05-17 インシデント: backup_db.sh が空 gzip を量産 → ハードコードされたコンテナ名が実際と不一致だった。

現行スクリプトは動的コンテナ名解決のため再発しないが、確認手順:

```bash
# postgres コンテナが起動中か確認
docker ps --filter "name=postgres-production" --filter "status=running"

# バックアップファイルサイズ確認
stat -c%s /opt/ultra-autotrade/db_backups/production_*.sql.gz | sort -n | tail -5
# 10240 (10KB) 未満なら異常 → Slack 通知が届いているはず
```

#### 月次アーカイブが作成されない

月初（1日）以降の初回実行時に自動作成される。手動で作成する場合:

```bash
CURRENT_MONTH=$(date +%Y%m)
cp /opt/ultra-autotrade/db_backups/production_$(ls /opt/ultra-autotrade/db_backups/production_*.sql.gz | sort | tail -1 | xargs basename) \
   /opt/ultra-autotrade/db_backups/monthly/production_monthly_${CURRENT_MONTH}.sql.gz
```

---

## 関連ドキュメント

- `docs/19_operations_runbook.md` — 全体的な運用手順
- `docs/16_infra_deployment_guide.md` — インフラ・デプロイガイド
- `scripts/backup_db.sh` — 週次 DB バックアップ（4 週保持 + 月次 6 ヶ月アーカイブ）
- `scripts/deploy_production.sh` — `slack_notify()` の参照元実装
- `docs/postmortems/2026-05-17_backup_silent_failure.md` — バックアップ無音失敗 RCA
