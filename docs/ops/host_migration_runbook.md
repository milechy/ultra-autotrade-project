# 本番 Hetzner → 別アカウント Hetzner (ASSIST ONE) 移行ランブック

> 作成: 2026-06-30 / 改訂: 2026-07-02（3VPS・2プロジェクト構成へ変更）/ 実行予定: 2026-07-02以降
> 対象: 旧VPS(77.42.46.155、production+staging+staging-v4 の3スタック同居)を、別アカウント(ASSIST ONE)の **3台の新VPS** へ分離移行する。
> 方式: **VPSスナップショットは使わない**（別アカウントには直接コピー不可）。docker-compose 建て直し + DB dump/restore + 秘密ファイル安全コピー。

---

## 0. アーキテクチャ変更点（2026-07-02改訂）

**旧計画**（2026-06-30版）: 新VPS 1台に production+staging+staging-v4 の3スタックを同居させる（旧VPSと同じ構成）。

**新計画**（本改訂）: **本番を物理的に分離**する3VPS構成に変更。

| VPS | 用途 | Hetzner Cloud Project | Remote SSH |
|---|---|---|---|
| **production** | productionスタックのみ | `production`（専用APIトークン・専用ファイアウォール） | ❌ 直接ssh禁止。3段階プロトコル(phase1-investigator/phase2-implementer/phase3-deployer)経由のみ |
| **staging** | staging + staging-v4 の2スタック | `staging-dev`（staging/devで共用トークン） | ✅ VSCode Remote SSH可（実資金なし） |
| **dev** | Claude Code CLI開発・worktree並列レーン | `staging-dev` | ✅ VSCode Remote SSH可 |

理由: 実資金(Base Mainnet)を扱うproductionをVPSレベル・Hetzner Projectレベル（＝APIトークンのスコープ）の両方で隔離する。staging/devは実資金がないため同一プロジェクトで運用コストを抑える。

**バックアップ方針（新規）**:
- production: Hetzner Cloud **Backups**アドオン（VPS丸ごと自動スナップショット）＋ 既存 `backup_db.sh` cron（pg_dump）＋ **Hetzner Storage Box** へのオフホスト複製（3-2-1原則）
- staging/staging-v4: `backup_db.sh` cronのみ
- dev: バックアップ不要（コードはgit、DBは使い捨て）

**dev VPSは既存 `uata-dev-01`(77.42.79.75) を廃止し、ASSIST ONE上に新規構築**する（旧アカウントとの分散管理をやめて一元化）。

---

## 0-1. 重要原則（飛ばすと事故る、旧版から継続）

1. **automation を確実に止めてから移す。** 旧・新で AI判定スケジューラが同時稼働すると実トレード二重執行。実資金（Base Mainnet）なので最優先（§Phase 1）。
2. **バックアップは「復元できること」を移行前に検証。** 過去にバックアップ全滅事故あり。dump しただけで安心しない（§Phase 2）。
3. **DNS / ドメインは触らない。** Cloudflare Tunnel は token モード = ingress は旧CFアカウントのゾーンに CNAME。origin IP 非依存なので、**cloudflared を新ホストへ引っ越すだけ。A レコード変更不要**（§Phase 7）。
4. **秘密鍵を含む .env は暗号化して運ぶ。コミット厳禁・perms 600・staging/prod の鍵分離維持。**
5. **新ホスト上で git commit / merge しない**（pull only ルール継続。dev VPSは開発用途のため例外＝commit/push可、ただしmain直pushは禁止で従来通りPR経由）。
6. **トレード停止中＝ダウンタイム許容**なので、無理に zero-downtime にせず「止める→移す→起こす→切替」の単純安全手順で行く。
7. **production VPSへは直接ssh/VSCode Remote SSHで接続しない。** 3段階プロトコル(phase1-investigator/phase2-implementer/phase3-deployer)経由のみ。

### 想定パラメータ（実行前に埋める）

- 旧VPS: `ultra@77.42.46.155`（hostname=ultraautotrade, repo root=`/opt/ultra-autotrade/`）
- 新VPS production: `root@5.223.88.14`（hostname=uata-production、Hetzner Project: `production`、Singapore、鍵=`~/.ssh/hetzner_assistone_production`、SSH aliasは意図的に作らない）
- 新VPS staging: `root@188.34.167.142`（hostname=uata-staging、Hetzner Project: `staging-dev`、Falkenstein、鍵=`~/.ssh/hetzner_assistone_stagingdev`、alias=`uata-assistone-staging`）
- 新VPS dev: `root@95.216.167.198`（hostname=uata-dev、Hetzner Project: `staging-dev`、Helsinki、鍵=`~/.ssh/hetzner_assistone_stagingdev`、alias=`uata-assistone-dev`）
- 新VPS repo root（全台共通）: `/opt/ultra-autotrade/`（dev VPSのみ worktree構造で `/opt/ultra-autotrade/main/` — 開発環境v3の既存パターンを踏襲）
- Hetzner Storage Box: `u625607.your-storagebox.de` / user `u625607`（Falkenstein、SSH Support + External Reachability有効、鍵=`hetzner_assistone_production`）

### 新VPS プロビジョニング指定（確定 2026-07-02）

> 旧VPS実測: 4 vCPU / RAM 7.6GB(swap 970MB常用=逼迫) / disk 75GB中42GB(うち33GBはbuild cache+旧image=ゴミ)。実データは2GB未満。
> 3台に分離するため、各VPSは単一〜2スタック分の負荷で足りる（旧24GB/8vCPU一括案より縮小）。

| VPS | RAM | vCPU | SSD | swap | 追加 |
|---|---|---|---|---|---|
| **production** | 16GB | 4 | 80GB | 4GB | Hetzner Cloud Backups アドオン ON |
| **staging** | 16GB | 4 | 80GB | 4GB | — |
| **dev** | 8-16GB | 4 | 60GB | 任意 | — |

OS: Ubuntu 22.04 / 24.04 LTS想定 → **実際は3台ともUbuntu 26.04 LTSで作成された**（2026-07-02実機確認）。Docker CE公式aptリポジトリが26.04のコードネームに未対応の可能性があるため、Phase 4でのDocker導入時に `lsb_release -cs` の値がDocker公式repoにあるか確認し、無ければ24.04(noble)のコードネームで代替設定するフォールバックを用意すること。また3台ともswap 0Bだったため、Phase 4でswap設定を明示的に追加する（productionのみ想定していたswap 4GBを全台に適用）。

---

## 前日準備（無停止でできる）

- [ ] Hetzner Cloud Project `production` 作成、専用APIトークン発行
- [ ] Hetzner Cloud Project `staging-dev` 作成、専用APIトークン発行
- [ ] production VPS 起動（上記スペック、Backupsアドオン ON）
- [ ] staging VPS 起動（上記スペック）
- [ ] dev VPS 起動（上記スペック）
- [ ] Hetzner Storage Box 作成（小容量プランで可）
- [ ] 3VPS + Storage Box に公開鍵登録・SSH疎通確認（`ssh ____@新IP 'hostname && nproc && free -h && df -h /'`）
- [ ] 3VPS に Docker + docker compose + git インストール
- [ ] **秘密の棚卸し**（follow-up の起点）: 旧VPSの `.env.production` に生鍵があることを確認（`AAVE_WALLET_PRIVATE_KEY` / `OPERATOR_FEE_WALLET_KEY` / `JWT_SECRET_KEY` / `INTERNAL_API_TOKEN` / `CLOUDFLARE_TUNNEL_TOKEN`）。移行後に 1Password化 / 生鍵排除（§follow-up）
- [ ] バックアップ復元検証を**前日に1回リハーサル**（§Phase 2 を旧VPS内の一時DBで試す）
- [ ] `~/.ssh/config` に staging/dev のalias追加（production は直接ssh用aliasを作らない）
- [ ] **旧VPSのhost常駐cloudflaredがsystemd管理か確認**（`systemctl status cloudflared` / `systemctl is-enabled cloudflared`）。§Phase 7-Aの停止コマンドを確定させる（2026-07-02実機調査で発見: docker外にroot権限で常駐する経路が別途ある）
- [ ] Cloudflare Zero Trustダッシュボード（Networks→Tunnels）で既存トンネル(`e558c833-...`)のPublic Hostname一覧を確認し、staging-v4向けの新規Tunnel作成・Public Hostname設定を準備（§Phase 7-B）

---

## Phase 1: automation 停止（旧VPS / 二重執行防止）★最優先

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155
cd /opt/ultra-autotrade && pwd && ls   # repo root 確認（main/ は無い）

# 1-1. emergency_stop ON（実トレード系を即停止・監視/backupは継続）
docker exec ultra-autotrade-backend-blue-production python -c "
import json
p='/var/run/ultra/state.json'
s=json.load(open(p))
s['emergency_stop']=True
json.dump(s,open(p,'w'))
print('emergency_stop set:', s.get('emergency_stop'))
"

# 1-2. スケジューラ + 監視ループを env で停止
printf '\nDISABLE_AI_JUDGMENT_SCHEDULER=1\nDISABLE_BACKGROUND_MONITORING=1\n' >> /opt/ultra-autotrade/.env.production
chmod 600 /opt/ultra-autotrade/.env.production

# 1-3. backend 再起動で反映（--backend-only で active slot のみ）
./scripts/deploy_production.sh --backend-only

# 1-4. 停止確認: ログに scheduler が起動していないこと
docker logs ultra-autotrade-backend-blue-production 2>&1 | grep -iE "AI judgment scheduler|background monitoring" | tail -5
```

- [ ] emergency_stop=true 確認
- [ ] スケジューラ起動ログが出ていないこと確認
- [ ] staging / staging-v4 の backend も同様に停止（実資金は無いが整合のため）

> 補足: 既に DISABLE_* が効くので、新ホストでも検証完了まで `DISABLE_AI_JUDGMENT_SCHEDULER=1` のまま起動し、§Phase 9 で外す。

---

## Phase 2: バックアップ取得 + 復元検証（最重要）

```bash
# 2-1. 3環境すべて DB バックアップ
ENVIRONMENT=production   /opt/ultra-autotrade/scripts/backup_db.sh
ENVIRONMENT=staging-new  /opt/ultra-autotrade/scripts/backup_db.sh
# staging-v4 は backup_db.sh 非対応（production/staging-newのみ実装）→ 下記の手動 pg_dump のみ使用

# 手動 pg_dump（3 DB 個別・確実）
for pair in \
  "ultra-autotrade-postgres-production:ultra_autotrade:prod" \
  "ultra-autotrade-postgres-staging-new:ultra_autotrade_staging:stg" \
  "ultra-autotrade-postgres-staging-v4:ultra_autotrade_staging_v4:stgv4"; do
  c="${pair%%:*}"; rest="${pair#*:}"; db="${rest%%:*}"; tag="${rest##*:}"
  docker exec "$c" pg_dump -U ultra -d "$db" | gzip > /opt/ultra-autotrade/db_backups/migrate_${tag}_$(date +%Y%m%d_%H%M%S).sql.gz
done
ls -lh /opt/ultra-autotrade/db_backups/migrate_*.sql.gz

# 2-2. ★復元検証（本番DBには触らず一時DBへ復元して件数照合）
docker exec ultra-autotrade-postgres-production psql -U ultra -d postgres -c "CREATE DATABASE restore_test;"
gunzip -c /opt/ultra-autotrade/db_backups/migrate_prod_*.sql.gz | docker exec -i ultra-autotrade-postgres-production psql -U ultra -d restore_test
# 主要テーブルの件数が本番と一致するか
for t in users proposals ai_decisions fund_allocations; do
  echo "== $t =="
  docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade   -tAc "SELECT count(*) FROM $t;"
  docker exec ultra-autotrade-postgres-production psql -U ultra -d restore_test       -tAc "SELECT count(*) FROM $t;"
done
docker exec ultra-autotrade-postgres-production psql -U ultra -d postgres -c "DROP DATABASE restore_test;"

# 2-3. Storage Box へオフホスト複製（3-2-1原則。以後は移行と無関係に日次cronで継続 → §Phase 9）
tar czf - /opt/ultra-autotrade/db_backups/migrate_*.sql.gz | \
  ssh -p 23 u625607@u625607.your-storagebox.de "cat > migrate_backups_$(date +%Y%m%d).tar.gz"
```

- [ ] 3つの dump がサイズ>0・gzip 整合OK
- [ ] **復元検証で主要テーブル件数が本番と一致**（ここが通らなければ移行中止）
- [ ] dump を新VPSへ送る前に Storage Box にも1部退避（保険）

---

## Phase 3: 秘密・非gitファイルの安全コピー

> 平文 .env と Tunnel credentials を運ぶ。**Hetzner Storage Box を中継**に使う（Mac中継より本体運用に近い形で恒久化できる）。可能なら age/gpg で暗号化して転送。
> **転送先はスタックに応じて production VPS / staging VPS に振り分ける**（旧版は1台宛だったが今回は2台宛）。

```bash
# 3-1. 旧VPS → 暗号化 → Storage Box 経由 or 直接 scp（鍵が通れば）
# production 向け（production VPSのみに配置）:
#   .env.production ← 秘密鍵含む・perms 600
#   docker/nginx/upstream.production.conf ← active color 確認
#   db_backups/migrate_prod_*.sql.gz
#   backups/（state.json 等のうち production 分）
# staging 向け（staging VPSのみに配置）:
#   .env.staging-new / .env.staging-v4
#   docker/nginx/upstream.staging*.conf
#   db_backups/migrate_stg_*.sql.gz / migrate_stgv4_*.sql.gz

# 例（暗号化中継、production分）:
ssh ultra@77.42.46.155 "cd /opt/ultra-autotrade && tar czf - .env.production backups db_backups/migrate_prod_*.sql.gz docker/nginx/upstream.production.conf" \
  | age -p > ~/uata-migrate-prod-secrets.tar.gz.age
scp ~/uata-migrate-prod-secrets.tar.gz.age ____@新IP-production:/tmp/
ssh ____@新IP-production "age -d /tmp/uata-migrate-prod-secrets.tar.gz.age | tar xzf - -C /opt/ultra-autotrade/ && chmod 600 /opt/ultra-autotrade/.env.production"
rm ~/uata-migrate-prod-secrets.tar.gz.age
ssh ____@新IP-production "rm /tmp/uata-migrate-prod-secrets.tar.gz.age"

# 例（暗号化中継、staging分）:
ssh ultra@77.42.46.155 "cd /opt/ultra-autotrade && tar czf - .env.staging-new .env.staging-v4 backups db_backups/migrate_stg*_*.sql.gz docker/nginx/upstream.staging*.conf" \
  | age -p > ~/uata-migrate-staging-secrets.tar.gz.age
scp ~/uata-migrate-staging-secrets.tar.gz.age ____@新IP-staging:/tmp/
ssh ____@新IP-staging "age -d /tmp/uata-migrate-staging-secrets.tar.gz.age | tar xzf - -C /opt/ultra-autotrade/ && chmod 600 /opt/ultra-autotrade/.env.*"
rm ~/uata-migrate-staging-secrets.tar.gz.age
ssh ____@新IP-staging "rm /tmp/uata-migrate-staging-secrets.tar.gz.age"
```

- [ ] production VPS に `.env.production` のみ perms 600 で配置（staging系は置かない＝隔離維持）
- [ ] staging VPS に `.env.staging-new` / `.env.staging-v4` perms 600 で配置
- [ ] **DATABASE_URL がフルURL直書き**であること確認（`grep '^DATABASE_URL=' .env.production' に `@postgres:5432` が含まれる）。空展開依存は事故の元
- [ ] CLOUDFLARE_TUNNEL_TOKEN が各 .env に存在
- [ ] 中継した平文/暗号化ファイルを削除（Mac・旧VPS・新VPS /tmp すべて）

---

## Phase 4: 新ホスト構築

### 4-A. production VPS

```bash
ssh ____@新IP-production
sudo mkdir -p /opt/ultra-autotrade && sudo chown $USER /opt/ultra-autotrade
cd /opt/ultra-autotrade
git clone <repo-url> .          # main を clone（commit はしない）
git checkout main && git pull origin main
# Phase 3 で .env.production と backups/ は配置済み
grep 'set $backend' docker/nginx/upstream.production.conf   # active color を旧VPSの現値に合わせる
```

### 4-B. staging VPS

```bash
ssh ____@新IP-staging
sudo mkdir -p /opt/ultra-autotrade && sudo chown $USER /opt/ultra-autotrade
cd /opt/ultra-autotrade
git clone <repo-url> .
git checkout main && git pull origin main
# Phase 3 で .env.staging-new / .env.staging-v4 と backups/ は配置済み
```

- [ ] production/staging 両VPSで repo clone・main 最新
- [ ] `.env.*` と nginx upstream の active color が旧VPSと一致
- [ ] swap（RAM<8GB なら）有効化 ※本構成は16GBのため基本不要

---

## Phase 5: DB 移行（dump → restore）

### 5-A. production VPS

```bash
cd /opt/ultra-autotrade
docker compose --env-file .env.production -f docker-compose.production.yml up -d postgres
gunzip -c db_backups/migrate_prod_*.sql.gz | docker exec -i ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade
for t in users proposals ai_decisions fund_allocations; do
  docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -tAc "SELECT '$t', count(*) FROM $t;"
done
```

### 5-B. staging VPS（staging + staging-v4 の2DB）

```bash
cd /opt/ultra-autotrade
docker compose --env-file .env.staging-new -f docker-compose.staging.yml up -d postgres
docker compose --env-file .env.staging-v4 -f docker-compose.staging-v4.yml up -d postgres
gunzip -c db_backups/migrate_stg_*.sql.gz   | docker exec -i ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade_staging
gunzip -c db_backups/migrate_stgv4_*.sql.gz | docker exec -i ultra-autotrade-postgres-staging-v4  psql -U ultra -d ultra_autotrade_staging_v4
```

- [ ] production: 1 DB 復元完了・件数が旧VPSと一致
- [ ] staging: 2 DB 復元完了・件数が旧VPSと一致
- [ ] `alembic_version` が旧VPSと同一（各DBで `SELECT version_num FROM alembic_version;`）

---

## Phase 6: 全サービス起動 + color 整合

### 6-A. production VPS

```bash
cd /opt/ultra-autotrade
./scripts/deploy_production.sh        # build → up → ヘルスチェック（blue 初期化、DISABLE_*はまだ有効のまま）
docker exec ultra-autotrade-backend-blue-production printenv | grep -E "BACKEND_COLOR|ACTIVE_BACKEND_COLOR"
grep 'set $backend' docker/nginx/upstream.production.conf

# ★★重要（2026-07-02実機で発覚・約1時間のスプリットブレイン発生・解消済み）:
# docker-compose.production.yml には cloudflared サービスが同梱されており、上記 deploy_production.sh 実行で
# 自動的に起動し、.env.production の CLOUDFLARE_TUNNEL_TOKEN（旧VPSと同じ既存トンネル e558c833 のトークン）で
# 旧トンネルへアウトバウンド接続してしまう。Phase 7-A（意図的な切替）より前にこの接続が生きていると、
# 旧VPS(2経路)+新VPS(1経路)の3経路が同一トンネルに同時接続し、Cloudflareがリクエストを新旧へランダム振り分け
# → 新旧で別々のDBに書き込まれデータ不整合の恐れ。デプロイ直後、必ず以下で止めること:
docker stop ultra-autotrade-cloudflared-production
docker ps -a | grep cloudflared   # Exited になっていることを確認
```

- [ ] backend(127.0.0.1:8010) / frontend(3000) / nginx(8000) ローカル health 200
- [ ] ACTIVE_BACKEND_COLOR と nginx upstream が一致（blue/blue）
- [ ] **`ultra-autotrade-cloudflared-production` を明示的に stop したことを確認**（デプロイ直後は自動起動している）
- [ ] **この時点ではまだ Tunnel 旧ホスト → トラフィックは旧へ。新ホストはローカル検証のみ**
- [ ] **Phase 7-A実施まで、新VPSで `deploy_production.sh` の再実行や `docker compose ... up -d` を絶対に行わない**（cloudflaredが再起動し同じスプリットブレインが再発する）
- [ ] **[要follow-up、Tier S変更なので今回の移行では強制しない]** cloudflaredコンテナに `.env.production` 全体が env_file 経由で注入される構成になっていないか確認（旧VPSで同構成を確認済み・秘密鍵含む全変数がトンネルトークンだけで足りるコンテナに渡っている）。新VPSでも同じ compose 定義を使う限り同じ状態を引き継ぐ。安全化(tunnel tokenのみ渡す構成への変更)は移行と切り離した別PRで対応する（詳細は §follow-up）

### 6-B. staging VPS

```bash
cd /opt/ultra-autotrade
./scripts/deploy_staging.sh            # staging用デプロイスクリプト（存在確認の上で実行）
docker compose --env-file .env.staging-v4 -f docker-compose.staging-v4.yml up -d
```

- [ ] staging(3001/8082) / staging-v4(3002/8083) ともにローカル health 200

---

## Phase 7: Tunnel 引っ越し

> **2026-07-02 実機調査 + CFダッシュボード確認で判明した重要事実（旧版の前提を修正）**:
> 1. 旧VPSでは単一の Cloudflare Tunnel（名前`ultra-autotrade-staging`、tunnel id `e558c833-014f-40a0-ad84-4562cf01af20`）が **host常駐バイナリ**（docker外、root権限、`/usr/bin/cloudflared --no-autoupdate tunnel run --token ...`）と **dockerコンテナ**（`ultra-autotrade-cloudflared-production`）の**2経路（レプリカ2、両方とも77.42.46.155由来）で二重稼働**している。docker composeスタックだけを移すと host側が取り残される。
> 2. staging-new / staging-v4 には独立した cloudflared は存在しない。**全6ホスト名がこの単一トンネルを経由**し、CFダッシュボードのPublic Hostname設定で各ホスト名をVPS内の各localhostポートへ振り分けている。確認済みマッピング（2026-07-02実機確認）:
>
>    | ホスト名 | Service | 移行先 |
>    |---|---|---|
>    | `api.ultra-auto-trade.com` | `http://localhost:8000` | production VPS（既存トンネルのまま） |
>    | `app.ultra-auto-trade.com` | `http://localhost:3000` | production VPS（既存トンネルのまま） |
>    | `staging.ultra-auto-trade.com` | `http://localhost:3001` | staging VPS（新規トンネル） |
>    | `api-staging.ultra-auto-trade.com` | `http://localhost:8082` | staging VPS（新規トンネル） |
>    | `staging-v4.ultra-auto-trade.com` | `http://localhost:3002` | staging VPS（新規トンネル） |
>    | `api-staging-v4.ultra-auto-trade.com` | `http://localhost:8030` | staging VPS（新規トンネル、nginxではなくbackend直ポートなので注意） |
>
>    **旧版の「staging は外部公開なし」という理解は誤り**（docker-compose.staging.ymlのコメントは「独立cloudflaredコンテナが無い」という意味であり、実際は単一トンネル経由で`staging.ultra-auto-trade.com`として公開されていた）。
> 3. この方式は「同一ホスト内の複数ポート」を前提にしているため、production/stagingを別VPSに分けると、staging系4ホスト名のingressルールが新production VPS側のトンネルからは届かなくなる。よって **staging VPS 側には新規に別の Cloudflare Tunnel を作成し、上記4ホスト名をそちらへ移す**（§7-B）。production hostname(app./api.)は既存トンネル`e558c833`をそのまま新production VPSへ引っ越すだけで良く、DNS変更は不要。**staging系4ホスト名だけはCNAME/ingress変更が必要**（原則3「DNS/ドメインは触らない」の唯一の例外、影響範囲はstaging関連サブドメインのみ）。

### 7-A. production（既存トンネル e558c833 の引っ越し・DNS変更なし）

```bash
# 新production VPSでdocker cloudflaredが接続できていることを確認
docker logs ultra-autotrade-cloudflared-production 2>&1 | tail -20   # "Registered tunnel connection" を確認

# ★切替の瞬間: 旧VPSの両経路（host binary(systemd) + docker）を停止
# host側（2026-07-02実機確認済み: /etc/systemd/system/cloudflared.service、enabled/active、2026-05-21から稼働。
#          自動更新タイマー cloudflared-update.timer も別途動いているため合わせて停止）
ssh ultra@77.42.46.155 "sudo systemctl stop cloudflared && sudo systemctl disable cloudflared"
ssh ultra@77.42.46.155 "sudo systemctl stop cloudflared-update.timer && sudo systemctl disable cloudflared-update.timer"
# docker側
ssh ultra@77.42.46.155 "docker stop ultra-autotrade-cloudflared-production"

# 旧VPSでcloudflared関連プロセスが完全停止したことを確認
ssh ultra@77.42.46.155 "systemctl is-active cloudflared; docker ps -a | grep -i cloudflared; ps aux | grep -i cloudflare[d]"

curl -s -o /dev/null -w "%{http_code}\n" https://api.ultra-auto-trade.com/health
curl -s -o /dev/null -w "%{http_code}\n" https://app.ultra-auto-trade.com
```

- [ ] **§前日準備で「host cloudflaredがsystemd管理か」を事前確認済み**（未確認のままkillで代用しない。誤ると再起動されて二重稼働に戻る）
- [ ] 旧VPSでdocker+host両方のcloudflaredが停止したことを確認（`docker ps -a` と `ps aux` 両方）
- [ ] 新production VPSはdockerコンテナのみで運用し、host常駐バイナリは作らない（二重稼働の再発防止）

### 7-B. staging（2026-07-02実施済み・完了）

> **実施済み記録**: production cutover前に、staging側は独立して先行実施した（productionと違いDBが別・実資金なしのため、productionの安定確認を待つ必要はないと判断）。
>
> 1. `dash.cloudflare.com` の **旧アカウント側**（`Hkobayashi@mooores.com`、`ultra-auto-trade.com`ゾーンを持つ方。ASSIST One新規アカウントには当該ゾーンへのアクセス権が無く新規トンネル作成不可と判明）で新規Tunnel `ultra-autotrade-staging-v2`（tunnel id `f3523ef4-dbff-49f8-a747-5564de918678`）を作成
> 2. staging VPS上で `docker run -d --restart unless-stopped --name ultra-autotrade-cloudflared-staging cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <新トークン>` で起動（docker-compose外の単独コンテナ。docker-compose.staging.yml/staging-v4.ymlはTier Sのため今回編集せず、旧VPSのhost binary方式と同様の独立起動パターンを採用）
> 3. CFダッシュボードでPublic Hostname 4件を追加:
>
> | ホスト名 | Service |
> |---|---|
> | `staging.ultra-auto-trade.com` | `http://localhost:3001` |
> | `api-staging.ultra-auto-trade.com` | `http://localhost:8082` |
> | `staging-v4.ultra-auto-trade.com` | `http://localhost:3002` |
> | `api-staging-v4.ultra-auto-trade.com` | `http://localhost:8030` |
>
> **★重要な発見**: Public Hostnameを新Tunnelに追加すると、**CNAMEは即座に自動的に新Tunnelへ切り替わる**（「旧トンネルのルート削除を待ってから」ではなく、追加した瞬間に旧→新へ即時カットオーバーされる）。事前に「productionの安定確認をしてから」といった余裕を持たせる設計は通用しない。ルート追加＝即カットオーバーと心得ること。
> 4. `/health`で実際に新staging VPSのbackendが応答することを確認（`{"status":"degraded","env":"staging","scheduler":false,...}` — scheduler:falseはPhase1停止状態と一致）
> 5. 旧トンネル(e558c833)側に残る同名4ルートは実質無効化されているが、混乱防止のため後日削除する（クリーンアップのみ、緊急性なし）

- [x] staging系4ホスト名、新Tunnel経由で疎通確認済み（2026-07-02）
- [ ] 旧トンネル(e558c833)側の同名4ルートをクリーンアップ（任意タイミング）

---

## Phase 8: 移行後検証（automation 再開の前）

```bash
# production
docker exec ultra-autotrade-backend-blue-production python -c "from alembic.config import main; main(argv=['current'])"
curl -s https://api.ultra-auto-trade.com/health
docker exec ultra-autotrade-backend-blue-production printenv | grep -E "AAVE_NETWORK|CHAIN_ID|APP_ENV|BYBIT_SANDBOX"
```

- [ ] APP_ENV=production / AAVE_NETWORK=base / CHAIN_ID=8453 / BYBIT_SANDBOX=false
- [ ] alembic current が head と一致（production・staging・staging-v4 いずれも）
- [ ] 外形 health 200 / ログイン可 / 既存ユーザーのデータ（提案・残高）が見える
- [ ] Slack healthcheck 通知が新ホストから飛ぶ（cron 登録後）

---

## Phase 9: cron 登録 + automation 再開 + オフホストバックアップ恒久化

### production VPS

```bash
crontab -e
# 0 3 * * *  ENVIRONMENT=production /opt/ultra-autotrade/scripts/backup_db.sh >> /opt/ultra-autotrade/logs/backup.log 2>&1
# */5 * * * * /opt/ultra-autotrade/scripts/healthcheck_l1_l6.sh >> /opt/ultra-autotrade/logs/healthcheck.log 2>&1
# 0 3 * * 0  /opt/ultra-autotrade/scripts/docker_cleanup.sh >> /opt/ultra-autotrade/logs/docker_cleanup.log 2>&1
# 30 3 * * * tar czf - /opt/ultra-autotrade/db_backups/*.sql.gz | ssh -p 23 u625607@u625607.your-storagebox.de "cat > backup_$(date +\%Y\%m\%d).tar.gz"
mkdir -p /opt/ultra-autotrade/logs

cd /opt/ultra-autotrade
awk '!/^DISABLE_AI_JUDGMENT_SCHEDULER=/ && !/^DISABLE_BACKGROUND_MONITORING=/' .env.production > /tmp/envp && mv /tmp/envp .env.production
chmod 600 .env.production
docker exec ultra-autotrade-backend-blue-production python -c "
import json; p='/var/run/ultra/state.json'; s=json.load(open(p)); s['emergency_stop']=False; json.dump(s,open(p,'w')); print('emergency_stop:', s['emergency_stop'])
"
./scripts/deploy_production.sh --backend-only
docker logs ultra-autotrade-backend-blue-production 2>&1 | grep -iE "AI judgment scheduler started" | tail -3
```

### staging VPS

```bash
crontab -e
# 0 3 * * *  ENVIRONMENT=staging-new /opt/ultra-autotrade/scripts/backup_db.sh >> /opt/ultra-autotrade/logs/backup.log 2>&1
# staging-v4 は backup_db.sh 非対応（production/staging-newのみ実装）。手動pg_dumpをcron化する:
# 0 4 * * *  docker exec ultra-autotrade-postgres-staging-v4 pg_dump -U ultra -d ultra_autotrade_staging_v4 | gzip > /opt/ultra-autotrade/db_backups/stagingv4_$(date +\%Y\%m\%d).sql.gz
# */5 * * * * /opt/ultra-autotrade/scripts/healthcheck_l1_l6.sh >> /opt/ultra-autotrade/logs/healthcheck.log 2>&1
mkdir -p /opt/ultra-autotrade/logs
# staging系は emergency_stop / DISABLE_* を外す必要があれば同様に実施（実資金なしのため必須ではない）
```

- [ ] production: cron 4本登録（backup / healthcheck / docker_cleanup / storage-box複製）
- [ ] staging: cron 2-3本登録
- [ ] production: DISABLE_* 削除・emergency_stop=false・スケジューラ起動ログ確認
- [ ] **automation 再開は新ホストのみ**（旧ホストは止まったまま）

---

## Phase 10: 旧ホスト保険 → 破棄

- [ ] 旧VPS は **数日（推奨3〜7日）止めたまま保持**（ロールバック保険）。automation は旧で再開しないこと
- [ ] 新ホスト（production/staging）で ai_decisions 新規書込・トレード提案・残高・Slack 通知が正常を数日観測
- [ ] 問題なければ旧VPS 解約。解約前に `.env.*` と最終 dump を Storage Box へ暗号化退避

---

## Dev VPS 構築（データ移行フェーズとは独立、並行して実施可）

> 既存 `uata-dev-01`(77.42.79.75) を廃止し、ASSIST ONE `staging-dev` プロジェクト上に新規構築する。
> production/staging のデータ移行フェーズとは独立して並行作業できる（本番影響なし）。

```bash
ssh ____@新IP-dev
sudo mkdir -p /opt/ultra-autotrade && sudo chown $USER /opt/ultra-autotrade
cd /opt/ultra-autotrade
git clone <repo-url> main       # dev VPSは worktree構造（既存 開発環境v3 パターン踏襲）
cd main
git checkout main && git pull origin main

# Python venv
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Frontend
cd ../frontend && npm install --legacy-peer-deps

# swap（RAM<8GBの場合のみ、本構成は8-16GBのため状況次第）
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```

- [ ] repo clone（worktree構造 `/opt/ultra-autotrade/main/`）
- [ ] backend venv 構築・依存インストール
- [ ] frontend node_modules 構築
- [ ] VSCode Remote SSH で接続確認（`~/.ssh/config` の dev alias 経由）
- [ ] CLAUDE.md / .claude/CLAUDE.md のホスト判定表を新IPに合わせて更新（別PR）

---

## ロールバック手順（新ホストで重大問題が出たら）

```bash
# production をロールバックする場合
ssh ____@新IP-production "docker stop ultra-autotrade-cloudflared-production"
ssh ultra@77.42.46.155 "docker start ultra-autotrade-cloudflared-production"
#    ※ 新ホストで DB 書込が進んでいた場合、旧へ戻すとその間の差分は失われる。
#       自動売買は止めていたので実トレード差分は無いはずだが、提案/ユーザー操作差分に注意。
curl -s https://api.ultra-auto-trade.com/health

# staging をロールバックする場合（production とは独立に判断可）
ssh ____@新IP-staging "docker stop ultra-autotrade-cloudflared-staging ultra-autotrade-cloudflared-staging-v4"
ssh ultra@77.42.46.155 "docker start ultra-autotrade-cloudflared-staging ultra-autotrade-cloudflared-staging-v4"
```

- ロールバックの前提: 移行中は automation 停止＝実トレード差分ゼロ。戻しても資金状態は一致する設計。
- production と staging は Phase 7 で個別に cutover しているため、**片方だけロールバックすることも可能**（旧版は1台一括だったため不可だった）。

---

## follow-up（移行と同時にやらない・落ち着いてから）

> 「移行」と「秘密管理の刷新」を同時に変えない（切り分け不能になる）。下記は移行後の別タスク。

1. **config secrets の 1Password 化**: `.env` の非鍵系（PERPLEXITY/OPENAI/PRIVY/SLACK/DBパス等）を 1Password へ。deploy 時に `op inject -i .env.*.tpl -o .env.*` で実体化。平文を運ばない。staging/prod は別 vault。
2. **生鍵の排除（最重要）**: `AAVE_WALLET_PRIVATE_KEY` / `OPERATOR_FEE_WALLET_KEY` をホストの .env から消す方向。Privy サーバ委譲署名 / SCW（既存の進行方向）か KMS/HSM で「サーバが生鍵を持たない」状態へ。**1Password/MCP には入れない**（agent から到達させない）。
3. **アカウント権限の整理**: 本改訂で production / staging-dev の Hetzner Project・APIトークンは分離済み。残りは Cloudflare アカウント・GitHub の権限整理。
4. **2FA**: GitHub / Hetzner（新旧・両プロジェクト）/ Cloudflare すべて有効化。
5. **v4 PWA版スタックの追加**: 移行・安定確認の後に、staging VPS 上で4スタック目（staging-v4-pwa）を追加検討。詳細は従来案（別サブドメイン・独立backend/DB/frontend/nginx）を踏襲。

---

## 見落としやすい注意点（移行前に再読）

1. **DATABASE_URL はフルURL直書き必須**（`@postgres:5432` 含む）。compose の `${POSTGRES_PASSWORD}` 空展開で DB 接続不能 → 全API 500（/health は通るので気づきにくい）。
2. **.env.* は perms 600**。deploy_production.sh が前提チェックで弾く。
3. **ACTIVE_BACKEND_COLOR と nginx upstream のドリフト**＝AI判定スケジューラが静かに死ぬ（22日停止事故）。Phase 6 で必ず一致確認。
4. **cloudflared を新旧同時稼働させない**（HTTPスプリットブレイン）。Phase 7 のクリーン切替を厳守。production/staging は個別に切替可能だが、それぞれの中では同時稼働厳禁。
5. **frontend ビルド OOM**: 本構成は16GB確保済みのため基本発生しないはずだが、発生時は `NODE_BUILD_MAX_OLD_SPACE_SIZE=4096` を .env に明示。
6. **3VPS構成 = production/staging/dev の3台、DB は production 1個 + staging 2個（staging/staging-v4）**。旧版の「1台に3スタック」ではない点に注意。
7. **production VPS への直接ssh/VSCode Remote SSHは禁止**。3段階プロトコル経由のみ（本改訂の最重要変更点）。
