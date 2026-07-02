# VPS 運用セットアップ runbook（2026-06）

本番 VPS（Hetzner `5.223.88.14` / user `ultra`）で実施する運用ジョブ登録の手順書。
リポジトリ側のスクリプト・CI は実装済み。本書の作業は **VPS 実行（3段プロトコル）** が前提。

> **[CRITICAL] パス**: 本番 VPS の repo root は `/opt/ultra-autotrade/`（`main/` サブディレクトリなし）。
> SSH ログイン後に必ず `pwd && ls` で確認してから実行すること。
> 接続は3段プロトコル（@phase1-investigator → @phase2-implementer → @phase3-deployer）経由。

対象 Asana:
- 1214954820902281（ディスク監視 + Docker 自動 cleanup）
- 1214702770084840（DB 週次バックアップ自動化・5/2 以降停止の再開）
- 1214988731707550（journald 永続上限 SystemMaxUse=1G）
- 1214696986457078（.env 旧ファイル削除 ／ 検知 CI は実装済み）

---

## 0. 事前準備（ログ出力先）

cron が書き込むログディレクトリを作成しておく（未作成だと cron が無言で失敗する）。

```bash
sudo mkdir -p /var/log/ultra-autotrade
sudo chown ultra:ultra /var/log/ultra-autotrade
```

---

## 1. Docker 積極 cleanup（週次）

スクリプト: `scripts/periodic_docker_cleanup.sh`（builder cache 全削除 + dangling image +
journal vacuum 1G。WARN=80% / CRITICAL=90% で Slack 通知）。

`crontab -e`（user `ultra`）に追記:

```cron
# 毎週日曜 04:00 — Docker 積極 cleanup（ディスク逼迫対策）
0 4 * * 0 /opt/ultra-autotrade/scripts/periodic_docker_cleanup.sh >> /var/log/ultra-autotrade/periodic_cleanup.log 2>&1
```

検証:
```bash
crontab -l | grep periodic_docker_cleanup        # 登録確認
/opt/ultra-autotrade/scripts/periodic_docker_cleanup.sh   # 手動 1 回実行（ログ確認）
df -h / && docker system df                       # 効果確認
```

> 禁止: `docker system prune -af`（使用中 image 削除リスク・CLAUDE.md 明記）。本スクリプトは使わない。

---

## 2. PostgreSQL バックアップ（週次・5/2 以降停止の再開）

スクリプト: `scripts/backup_db.sh`（バックアップ後に gzip 整合性を自己検証、失敗時 Slack 通知 + exit 1）。

`crontab -e`（user `ultra`）に追記:

```cron
# 毎週日曜 02:00 — production DB バックアップ（cleanup と時間をずらす）
0 2 * * 0 ENVIRONMENT=production /opt/ultra-autotrade/scripts/backup_db.sh >> /var/log/ultra-autotrade/backup.log 2>&1
```

> 日次にする場合は `0 3 * * *`（スクリプト header の推奨値）。タスクは「週次」のため上記を既定とする。

検証:
```bash
crontab -l | grep backup_db                                   # 登録確認
ENVIRONMENT=production /opt/ultra-autotrade/scripts/backup_db.sh   # 手動 1 回実行
ls -lh <バックアップ出力先>                                    # ファイル生成 + サイズ確認
bash /opt/ultra-autotrade/scripts/restore_test.sh             # リストア検証（任意・推奨）
```

---

## 3. journald 永続上限（SystemMaxUse=1G）

systemd journal が無制限に肥大化してディスクを圧迫するのを防ぐ。root（sudo）作業。

```bash
# /etc/systemd/journald.conf を編集（sed -i は使わず確実に）
sudo cp /etc/systemd/journald.conf /etc/systemd/journald.conf.bak.$(date +%Y%m%d)
# [Journal] セクションの SystemMaxUse を 1G に設定（行が無ければ追記）
sudo sed -n 's/^#\?SystemMaxUse=.*/SystemMaxUse=1G/p' /etc/systemd/journald.conf  # まず現状確認
```

`SystemMaxUse=1G` を `[Journal]` セクションに設定（コメントアウト `#SystemMaxUse=` を有効化、
または無ければ追記）。エディタ作業のため手動編集が確実。設定後:

```bash
sudo systemctl restart systemd-journald
journalctl --disk-usage           # 反映確認（1.0G 以下に収束していく）
sudo journalctl --vacuum-size=1G  # 即時に 1G まで縮小（任意）
```

---

## 4. 旧 .env ファイルの物理削除（VPS / ローカル）

非推奨の旧 env ファイル（R1: 単独名 `.env.staging` 等）が VPS / ローカルに残っている場合に削除する。
正式名は `.env.staging-new`（v3 staging）/ `.env.staging-v4`（v4 staging）/ `.env.production`。

> **削除前に必ず中身を確認**し、正式ファイルが別に存在することを確かめてから消すこと。

```bash
cd /opt/ultra-autotrade
ls -la .env*                       # 現状の env ファイル一覧
# 例: 旧 .env.staging（単独名・R1 非推奨）が .env.staging-new と別に残っていれば削除
#     diff .env.staging .env.staging-new で差分確認 → 不要なら:
# rm .env.staging
```

> 自動削除はしない（誤削除防止）。差分確認のうえ手動で。CI 側は committed な実 env ファイルの
> 混入を `scripts/check_no_committed_env_files.sh`（env-separation-check）で検出する。

---

## 5. 完了確認チェックリスト

- [ ] `/var/log/ultra-autotrade/` 作成済み（chown ultra）
- [ ] `crontab -l` に `periodic_docker_cleanup`（日曜 04:00）登録
- [ ] `crontab -l` に `backup_db`（日曜 02:00 / ENVIRONMENT=production）登録
- [ ] 各スクリプトを手動 1 回実行してログ・出力を確認
- [ ] `journalctl --disk-usage` が 1G 近辺に収束
- [ ] 旧 `.env.staging`（単独名）が VPS に残っていれば差分確認のうえ削除
- [ ] CI: env-separation-check の "Check no real .env files committed" が green

---

*リポジトリ側（スクリプト + 検知 CI）は実装済み。本書は VPS 実行手順のみ。*
