# Restore Runbook (本番 / staging DB 災害復旧手順)

**作成日**: 2026-05-27
**対象**: Asana 本番運用「MVP-P0-1 Backup 復元検証 (prod DB / .env / wallet 鍵)」
**前提**: launch gate L0 / L1 / L2 が PASS する状態の復元
**実行責任**: 人間 (この runbook は読みながら手で実行する想定)
**Lane / Claude の責任範囲**: scripts/restore_test.sh (dry-run) と本 runbook の整備まで。
  実機の本番 backup を使った復元実行は **Lane / Claude は実施しない**
  (memory: `no-prod-vps-commands-from-dev`)

---

## 0. 前提

本 runbook は以下の状況を想定する:

- 本番 / staging の DB データが破損した (例: 誤 DELETE、storage 障害、disk corruption、
  誤 ALTER TABLE による不可逆な変更、誤 DROP TABLE 等)
- 復元元: `scripts/backup_db.sh` で生成された `.sql.gz` (gzip-compressed pg_dump plain SQL)
- 復元先: 既存 DB を上書きするのではなく、**まず一時 DB に復元 → 検証 → 既存と差し替え** の手順を取る

### backup file 形式 (前提知識)

| 項目 | 値 |
|------|-----|
| 生成元 | `scripts/backup_db.sh` (production / staging-new 両対応) |
| ファイル名 | `${ENVIRONMENT}_ultra_autotrade_${TIMESTAMP}.sql.gz` |
| 形式 | `pg_dump -U ultra <db>` の標準出力を gzip 圧縮 (plain SQL 形式) |
| 保管場所 | `/opt/ultra-autotrade/db_backups/` (本番 VPS) |
| 月次アーカイブ | `/opt/ultra-autotrade/db_backups/monthly/${ENV}_monthly_${YYYYMM}.sql.gz` |
| 保持期間 | 直近 28 日 + 月次 6 ヶ月 |
| 自己検証 | backup 時点で gzip integrity + 最低サイズ (10 KB) を確認済み |

### 関連 doc

- `scripts/backup_db.sh` — 日次 backup スクリプト (cron 03:00 JST)
- `scripts/restore_test.sh` — 本 runbook の §2 で使う dry-run 検証スクリプト
- `docs/internal/2026-05-26_alembic_stamp_production_sync_runbook.md` — alembic head が
  本番と乖離した場合の stamp 手順 (本 runbook §3.4 から参照)
- `docs/ops/disable_release_runbook.md` — `DISABLE_AI_JUDGMENT_SCHEDULER` 周りの kill switch 操作
- `docs/ops/02_db_tables.md` — 復元後に存在することを確認すべきテーブル一覧
- `scripts/launch_gate/L0_schema.sh` / `L1_env.sh` / `L2_smoke.sh` — 復元後 PASS させる gate

---

## 1. Backup file の準備

### 1.1 担当者

- **本番 VPS への SSH 担当**: 小林さん (Lane / Claude は SSH しない)
- 復元の意思決定: 小林さん + claude.ai 朝プロトコル

### 1.2 backup 取得元

```bash
# 本番 VPS 上で実行 (人間担当)
ssh prod-vps
ls -lh /opt/ultra-autotrade/db_backups/ | tail -10
ls -lh /opt/ultra-autotrade/db_backups/monthly/ | tail -10
```

### 1.3 取得する世代の判断基準

| 状況 | 取得する世代 |
|------|--------------|
| 直前 24h 以内のデータ破損 | 前日 03:00 JST の日次 backup |
| 数日前からの破損 | 破損より前の最新日次 backup |
| 月単位の破損 | 月次アーカイブ `monthly/` から該当月のもの |

### 1.4 gzip integrity 再確認

復元前に必ず実行 (backup_db.sh の self-check と二重で):

```bash
gzip -t /opt/ultra-autotrade/db_backups/production_ultra_autotrade_YYYYMMDD_HHMMSS.sql.gz
echo "gzip exit=$?"   # 0 が期待値
```

---

## 2. Pre-flight: restore 動作確認 (`scripts/restore_test.sh`)

**本番に流す前に必ず一時 DB で動作確認する。** これが MVP-P0-1 の本質。

### 2.1 dev VPS / 検証用 VPS 上で実行する場合

dev VPS には本番 backup ファイルは存在しないので、復元検証は **本番 VPS 上の隔離した postgres
インスタンス**、または **小林さんがローカル/別 VPS にコピーした backup** で行う。

```bash
# host モード (postgres が localhost で listen している場合)
RESTORE_TEST_PG_HOST=localhost \
RESTORE_TEST_PG_PORT=5432 \
RESTORE_TEST_PG_USER=postgres \
  ./scripts/restore_test.sh \
    --backup-file=/path/to/production_ultra_autotrade_YYYYMMDD_HHMMSS.sql.gz \
    --env=production
```

### 2.2 本番 VPS 上の docker postgres を借りる場合

**注意**: ここで使う postgres コンテナは「**本番 DB と同じインスタンス**」になる。
スクリプト側の安全装置 (`restore_test_` プレフィックス強制) により本番 DB (`ultra_autotrade` /
`ultra_autotrade_staging`) を上書きすることはないが、念のため staging-new コンテナを使うのが推奨。

```bash
# 推奨: staging-new コンテナを使う (本番コンテナと隔離)
RESTORE_TEST_PG_CONTAINER=ultra-autotrade-postgres-staging-new \
RESTORE_TEST_PG_USER=ultra \
  ./scripts/restore_test.sh \
    --backup-file=/opt/ultra-autotrade/db_backups/production_ultra_autotrade_YYYYMMDD_HHMMSS.sql.gz \
    --env=production
```

### 2.3 期待出力

```
[restore-test] Restore: OK
[restore-test] ...
[restore-test]   restore         : OK
[restore-test]   tables          : <N>           # 02_db_tables.md と概ね一致
[restore-test]   expected tables : 8 / 8
[restore-test]   alembic head    : <head id>     # 本番 alembic head と一致するか確認
[restore-test]   total rows      : <M>           # > 0
[restore-test]   FK count        : <K>           # > 0、invalid: 0
[restore-test]   integrity       : OK
[restore-test] Final: OK
```

終了コード:
- `0`: OK → §3 に進んでよい
- `1`: restore 失敗 or 整合性 NG → **§3 に進まない**。別世代の backup を試す or 小林さんに報告
- `2`: 設定エラー (引数不正 / backup file 不存在 / 一時 DB 作成失敗) → 引数や接続情報を見直す

### 2.4 NG 時の判定

| 症状 | 対処 |
|------|------|
| `gzip integrity check failed` | backup file が破損。別世代を使う |
| `Restore FAILED` (psql エラー) | tail されたエラーを読む。pg version 不整合の場合は同じ pg major version の postgres で再試行 |
| `alembic_version head not found` | backup が alembic 管理外の古い世代。stamp 手順 (§3.4) と併用が必要 |
| `Missing expected tables` (users, alembic_version 以外) | backup の取得タイミングによっては新規追加テーブルが無い場合あり。02_db_tables.md と照合し、テーブルが「無くて当然」なら継続可 |
| `Unvalidated FK constraints exist` | restore は通ったが FK が壊れている。**§3 に進まない**。別世代を使う |

### 2.5 詳細調査が必要な場合

`--keep-temp-db` を付けると検証用 DB が残るので、手動で `psql` 接続して調査できる:

```bash
./scripts/restore_test.sh \
  --backup-file=... --env=production --keep-temp-db

# 残った DB を見る
psql -U postgres -d restore_test_YYYYMMDD_HHMMSS_<pid>
\dt
SELECT * FROM alembic_version;
SELECT count(*) FROM proposals;
...

# 終わったら DROP
psql -U postgres -d postgres -c 'DROP DATABASE "restore_test_...";'
```

---

## 3. 本番 DB 復元手順 (人間担当)

> **Lane / Claude はここを実行しない。** 小林さんが本 runbook を読みながら手で実行する。

### 3.1 影響範囲告知 + 緊急停止

```bash
# 1. Slack #ultra-auto-project に告知
#    "本番 DB 復元のため X 分間サービスを停止します"

# 2. AI scheduler を停止 (kill switch)
#    詳細: docs/ops/disable_release_runbook.md
ssh prod-vps
docker exec ultra-autotrade-backend-blue-production \
  /bin/sh -c 'kill -SIGTERM $(pgrep -f "python -m app")' \
  || true
# または .env.production の DISABLE_AI_JUDGMENT_SCHEDULER=1 で再起動
```

> memory `disable-scheduler-flag-inverted`: production では DISABLE_SCHEDULER=ON で停止。
> staging とフラグの意味が逆なので取り違えないこと。

### 3.2 既存 DB のスナップショット (念のため)

復元前に必ず取得 (復元に失敗したときに戻すため):

```bash
# 本番 VPS 上 (小林さん担当)
docker exec ultra-autotrade-postgres-production \
  pg_dump -U ultra ultra_autotrade \
  | gzip > /opt/ultra-autotrade/db_backups/pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz

# gzip 検証
gzip -t /opt/ultra-autotrade/db_backups/pre_restore_*.sql.gz
```

### 3.3 復元

#### 方針 A: 既存 DB を rename + 復元 DB を本番名に rename (推奨、ダウンタイム最小)

```bash
# 1. backend を停止 (postgres は残す)
docker compose -f docker-compose.production.yml stop backend-blue backend-green

# 2. 復元用 DB を作成
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d postgres -c 'CREATE DATABASE ultra_autotrade_restored;'

# 3. backup を流し込む
gunzip -c /opt/ultra-autotrade/db_backups/production_ultra_autotrade_YYYYMMDD_HHMMSS.sql.gz \
  | docker exec -i ultra-autotrade-postgres-production \
      psql -U ultra -d ultra_autotrade_restored -v ON_ERROR_STOP=1

# 4. 既存 DB を退避名にリネーム
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d postgres -c \
  'ALTER DATABASE ultra_autotrade RENAME TO ultra_autotrade_broken_YYYYMMDD;'

# 5. 復元 DB を本番名にリネーム
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d postgres -c \
  'ALTER DATABASE ultra_autotrade_restored RENAME TO ultra_autotrade;'

# 6. backend を再開
docker compose -f docker-compose.production.yml start backend-blue backend-green
```

#### 方針 B: 既存 DB を DROP + CREATE で復元 (ダウンタイム長め、シンプル)

> 既存 DB が完全に破損していて rename しても価値が無い場合のみ採用。

```bash
docker compose -f docker-compose.production.yml stop backend-blue backend-green

docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d postgres -c \
  'DROP DATABASE ultra_autotrade; CREATE DATABASE ultra_autotrade;'

gunzip -c /opt/ultra-autotrade/db_backups/production_ultra_autotrade_YYYYMMDD_HHMMSS.sql.gz \
  | docker exec -i ultra-autotrade-postgres-production \
      psql -U ultra -d ultra_autotrade -v ON_ERROR_STOP=1

docker compose -f docker-compose.production.yml start backend-blue backend-green
```

### 3.4 alembic upgrade head

復元した backup の alembic head が、現在の repo の `alembic heads` と一致しない場合は
stamp / upgrade を行う:

```bash
# 復元 DB の現在 head 確認
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "SELECT version_num FROM alembic_version;"

# repo 側の head 確認
docker exec ultra-autotrade-backend-blue-production \
  alembic heads

# 差分がある場合の対処:
# - backup が古く、repo が進んでいる → alembic upgrade head
# - backup と repo の head が乖離している → stamp が必要
#   → 詳細手順: docs/internal/2026-05-26_alembic_stamp_production_sync_runbook.md
```

> ※ memory `custom-limiter-expired-env-cleanup-pending`:
> `CUSTOM_LIMITER_EXPIRES_ON=2026-05-15` 期限切れにより、コード側は自動 strict revert 動作中。
> 復元後の .env 削除は人間担当 (dev からは env 触らない)。

### 3.5 動作確認 (launch_gate L0 / L1 / L2)

```bash
# L0: schema sync (model vs DB schema gap)
./scripts/launch_gate/L0_schema.sh

# L1: env (本番 env が想定通り)
./scripts/launch_gate/L1_env.sh

# L2: smoke (基本的な read API が応答する)
./scripts/launch_gate/L2_smoke.sh
```

3 つすべて PASS で復元完了。

### 3.6 解放 (緊急停止解除)

```bash
# AI scheduler 復帰
# .env.production: DISABLE_AI_JUDGMENT_SCHEDULER を 0 or unset に
# (production では DISABLE=OFF が稼働状態。memory: disable-scheduler-flag-inverted)

docker compose -f docker-compose.production.yml restart backend-blue backend-green

# Slack #ultra-auto-project に復旧告知
```

---

## 4. .env / wallet 鍵の復元 (該当する場合)

DB だけでなく .env / wallet 鍵も損失した場合の手順 (Lane / Claude は触らない領域)。

### 4.1 .env の復元

- `.env.production` / `.env.staging-new` は **secrets manager / 別保管** からのみ復元する。
  Lane / Claude は本番 env に触らない (memory: `no-prod-vps-commands-from-dev`)。
- secrets の保管場所 + decryption key の所在は別途 1Password / Vault / 紙保管を参照。
- 復元後は `./scripts/launch_gate/L1_env.sh` で必須 env が揃っていることを確認。

### 4.2 wallet 鍵の復元

- ホットウォレット private key は **DB / repo 内に保存しない** ことが原則。
- 復元元: cold backup (paper / HSM / encrypted USB) のみ。
- 復元後は少額 send をテストしてから本番取引に使うこと。

---

## 5. 復元 OK の判定基準 (チェックリスト)

すべてチェックが入って初めて「復元完了」と宣言できる。

- [ ] `scripts/restore_test.sh` が exit 0 (Pre-flight 検証 PASS)
- [ ] `pre_restore_*.sql.gz` (退避 backup) が取得済み
- [ ] `alembic_version` の head id が repo の `alembic heads` と一致
- [ ] `02_db_tables.md` で list されているテーブルがすべて存在
- [ ] 主要テーブル (users / proposals / ai_decisions / transactions /
      fund_allocations / fee_transactions / portfolio_snapshots) の row count が 0 以上、
      かつ復元前と概ね一致 (大幅減なら別世代を疑う)
- [ ] `launch_gate/L0_schema.sh` PASS
- [ ] `launch_gate/L1_env.sh` PASS
- [ ] `launch_gate/L2_smoke.sh` PASS
- [ ] Slack #ultra-auto-project に復旧告知済み
- [ ] `DISABLE_AI_JUDGMENT_SCHEDULER` を稼働モード (production=OFF) に戻し、AI judgment が
      流れている (ai_decisions テーブルに新規 row が積まれる) のを 5 分以内に確認

---

## 6. NG 時の rollback

復元後に launch_gate L0-L2 のいずれかが NG だった、もしくは AI judgment が回らない
等の不具合が発生したら即時 rollback:

### 方針 A (rename 方式) からの rollback

```bash
docker compose -f docker-compose.production.yml stop backend-blue backend-green

docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d postgres -c \
  'ALTER DATABASE ultra_autotrade RENAME TO ultra_autotrade_restored_failed;'

docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d postgres -c \
  'ALTER DATABASE ultra_autotrade_broken_YYYYMMDD RENAME TO ultra_autotrade;'

docker compose -f docker-compose.production.yml start backend-blue backend-green
```

### 方針 B (DROP/CREATE 方式) からの rollback

```bash
docker compose -f docker-compose.production.yml stop backend-blue backend-green

docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d postgres -c 'DROP DATABASE ultra_autotrade; CREATE DATABASE ultra_autotrade;'

gunzip -c /opt/ultra-autotrade/db_backups/pre_restore_YYYYMMDD_HHMMSS.sql.gz \
  | docker exec -i ultra-autotrade-postgres-production \
      psql -U ultra -d ultra_autotrade -v ON_ERROR_STOP=1

docker compose -f docker-compose.production.yml start backend-blue backend-green
```

### 後始末

- 復元失敗した DB (`ultra_autotrade_restored_failed` 等) は **1 週間は残す** (調査用)
- Slack #ultra-auto-project に rollback 結果を告知
- 失敗原因を `docs/internal/` に YYYY-MM-DD_restore_failure_postmortem.md として記録

---

## 付録 A. dev VPS / Lane / Claude の制約

本 runbook の実行範囲のうち、Lane / Claude (dev VPS) は以下のみ実施できる:

| 項目 | Lane / Claude | 人間 (小林さん) |
|------|---------------|----------------|
| `scripts/restore_test.sh` の dry-run (一時 DB) | ○ (dev local postgres があれば) | ○ |
| 本番 VPS への SSH | × | ○ |
| 本番 backup ファイルの取得 / 閲覧 | × | ○ |
| 本番 DB への接続 (read-only でも) | × | ○ |
| `.env.production` の read / write | × | ○ |
| wallet 鍵への access | × | ○ |
| 本 runbook §3 / §6 の実行 | × | ○ |

memory 参照:
- `no-prod-vps-commands-from-dev` — dev からは本番 VPS 向けコマンドを提案しない
- `staging-lives-on-prod-vps` — staging も本番 Hetzner VPS (77.42.46.155) 上に同居
- `prod-steps-not-done-until-verified` — 実機出力で裏取りするまで「完了」と書かない

---

## 付録 B. 定期訓練 (推奨)

MVP-P0-1 完了後、四半期ごとに以下を実施する:

1. 本番 backup の最新世代を取得
2. `scripts/restore_test.sh` を **本番に触らない隔離環境** (dev 専用 postgres)
   で実行し、exit 0 を確認
3. 結果を Asana タスク「Backup 復元検証 (Q<N>)」に記録

これにより、実際の災害発生前に backup が復元可能であることを継続的に保証する。
