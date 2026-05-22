# Staging / Prod Build 隔離 Runbook

| 項目 | 値 |
| --- | --- |
| 作成日 | 2026-05-23 |
| オーナー | infra / SRE ロール |
| 関連 Asana | 1215028729779736 (OOM postmortem) |
| 関連 PR | #382 (backend codeploy runbook) |
| ステータス | Draft (P0-2) |

---

## 1. 目的

本 runbook は **staging と prod の build を物理的・運用的に隔離する** ためのルールを定義する。

### 1.1 背景

2026-05 に staging ホストで以下の事象が発生した(Asana 1215028729779736)。

- staging ホスト上で `next build` (frontend production build) を実行
- 同ホストに backend / postgres / redis コンテナが同居
- build プロセスが Node の heap で 1.2GB 以上を要求
- swap 未設定だったため Linux OOM killer が postgres を kill
- staging が 12 分間停止、ai_decisions ストリームが欠落

この事象は本質的に「ホスト容量計画の不在」ではなく **「prod-grade build を staging ホストで行うべきではない」** という運用原則の欠如から発生した。本 runbook はそれを明文化する。

### 1.2 スコープ

- frontend (Next.js / Vite) の production build
- backend のコンテナビルド (docker buildx)
- staging ホスト上で許容される build の種類
- swap / メモリ監視ポリシー

スコープ外:

- prod の build ポリシー(prod は CI のみで build、ホスト上 build は禁止 — 別 runbook)
- CI/CD パイプラインの詳細(別 runbook 予定)

---

## 2. ルール

### 2.1 staging ホスト build 禁止原則

**staging ホスト上で frontend production build を実行してはならない。**

例外:

- pre-built artifact (CI で build 済の `out/` または `.next/standalone`) を `scp` / `rsync` で配置するのは可
- backend の `docker compose build` は許容するが、staging に backend の build job を割り当てるのは非推奨(CI で image を build して `ghcr.io` に push する方を優先)

### 2.2 swap 維持

staging ホストには **必ず swap を 2GB 以上** 確保する。

- 経緯: 2026-05 セッションで swap (2GB, `/swapfile`, swappiness=10) を投入
- 確認コマンド: `swapon --show`
- `/etc/fstab` に `/swapfile none swap sw 0 0` 行が存在することを確認

swap はあくまでセーフティネットであり、定常的に使われる前提では設計しない。

### 2.3 同居ホスト負荷監視

staging は backend / postgres / redis / frontend (serve) が同居する。常時以下の閾値を維持:

| メトリクス | 閾値 | 取得 |
| --- | --- | --- |
| MemAvailable | >= 1.5 GB | `free -h` |
| swap 使用 | < 256 MB 定常 | `free -h` |
| load average (1m) | < CPU 数 x 1.5 | `uptime` |
| postgres RSS | < 512 MB | `docker stats --no-stream` |

これらを下回るときは新規 build / deploy を着手しない。

---

## 3. Deploy 前チェックリスト

deploy / build 着手前に以下を順に確認する。チェックを 1 つでも満たさない場合は着手不可。

### 3.1 ホスト健全性

- [ ] `docker compose ps` で他コンテナが全て `Up (healthy)` または `Up`
- [ ] `docker stats --no-stream` で各コンテナの MEM USAGE を記録
- [ ] `free -h` で `MemAvailable >= 1.5GB`
- [ ] `swapon --show` で `/swapfile` が enable 状態かつ Used が 256MB 未満
- [ ] `uptime` で load average (1m) が CPU 数 x 1.5 未満

```bash
# まとめて確認するワンライナー
echo "=== docker ===" && docker compose ps && \
echo "=== mem ===" && free -h && \
echo "=== swap ===" && swapon --show && \
echo "=== load ===" && uptime && \
echo "=== stats ===" && docker stats --no-stream
```

### 3.2 artifact 健全性

- [ ] frontend artifact が CI で pre-built されている (GHA `build-frontend` workflow の最新 run が green)
- [ ] artifact の SHA が deploy 対象 commit と一致
- [ ] backend image tag が `ghcr.io/uata/backend:<sha>` で pull 可能

```bash
# artifact SHA 突き合わせ
gh run list --workflow=build-frontend --limit 1
git rev-parse HEAD
```

### 3.3 ロールバック準備

- [ ] 直前の docker tag (`backend:previous`) が手元に控えてある
- [ ] postgres の論理 backup (`pg_dump`) が 24h 以内にある
- [ ] rollback コマンドを 1 行で実行できる状態(history に残す or pin する)

---

## 4. 緊急時挙動

### 4.1 OOM kill 発生時

事象: `dmesg | grep -i 'killed process'` で OOM killer のログが出る、または `docker compose ps` で特定コンテナが `Exited (137)`。

#### Step 1: 影響範囲の確定

```bash
# OOM killer が誰を殺したか
sudo dmesg -T | grep -i 'killed process' | tail -20

# コンテナの最終 exit code
docker compose ps -a

# postgres が殺された場合、WAL の整合性を最初に確認
docker compose exec postgres pg_controldata /var/lib/postgresql/data | head -20
```

#### Step 2: 復旧

```bash
# 1. 殺された service を識別
KILLED=postgres   # 例

# 2. 単体起動して log を見る
docker compose up -d ${KILLED}
docker compose logs --tail=200 ${KILLED}

# 3. healthy 化を待つ
until docker compose ps ${KILLED} | grep -q healthy; do sleep 5; done

# 4. 依存 service を順に起動
docker compose up -d backend
docker compose up -d frontend
```

#### Step 3: postmortem 起票

- Asana に postmortem task を作成 (template: P1)
- 5 whys を 3 営業日以内に埋める
- 本 runbook と Asana 1215028729779736 を参照に追加

### 4.2 swap が unmount された場合

事象: `free -h` で Swap 行が `0B`, または `swapon --show` が空。

```bash
# 1. swapfile の存在確認
ls -lh /swapfile

# 2. 存在するなら enable
sudo swapon /swapfile

# 3. 存在しなければ作成
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 4. fstab に永続化(既存行がなければ)
grep -q '/swapfile' /etc/fstab || \
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 5. swappiness 再設定
sudo sysctl vm.swappiness=10
grep -q '^vm.swappiness' /etc/sysctl.conf || \
  echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
```

### 4.3 staging を一時的に縮退する手順

メモリ逼迫時に staging を最小構成へ落とす。コンテナ停止順は **frontend → ai_judgment_scheduler → backend → redis → postgres** を守る(scheduler は backend に依存、backend は redis/postgres に依存)。

```bash
# 1. frontend を停止(ユーザー影響あり、最初に告知)
docker compose stop frontend

# 2. scheduler を停止(ai_decisions の書き込み停止)
docker compose stop ai_judgment_scheduler

# 3. backend を停止
docker compose stop backend

# 4. redis を停止(キャッシュのみ)
docker compose stop redis

# 5. postgres は最後まで残す(データ整合性のため必ず graceful stop)
docker compose stop -t 30 postgres
```

復帰時は逆順:

```bash
docker compose up -d postgres
until docker compose ps postgres | grep -q healthy; do sleep 5; done
docker compose up -d redis
docker compose up -d backend
until docker compose ps backend | grep -q healthy; do sleep 5; done
docker compose up -d ai_judgment_scheduler
docker compose up -d frontend
```

**注意**: `ai_judgment_scheduler` の DISABLE フラグは反転している (staging=ON+shadow / production=OFF)。停止/復帰時に挙動が変わるので soak 検証中は scheduler を最後に上げ、`ai_decisions` 件数を必ず monitor する。

---

## 5. 参照

### 5.1 Asana

- **1215028729779736** — OOM postmortem (2026-05). 本 runbook の起源。

### 5.2 PR

- **#382** — backend codeploy runbook(隣接領域、deploy 手順の本体)。
- 本 PR (P0-2) — staging/prod build 隔離 runbook。

### 5.3 ホスト設定の経緯

- 2026-05: swap (2GB) 投入。swappiness=10 で設定。
- 2026-05: frontend production build を staging ホストで行わない方針を確立(本 runbook で明文化)。

### 5.4 関連用語

- **Tier-S ファイル**: `backend/app/main.py`, `backend/app/automation/ai_judgment_scheduler.py`, `backend/app/aave/client.py`, 既存 alembic 過去 revision。これらは本 runbook の対象外(コード変更なし)。
- **shadow mode**: ai_judgment_scheduler が判定するが取引を行わないモード。staging で常用。
- **soak**: 一定時間連続稼働させて健全性を確認する検証フェーズ。

---

## 6. 改訂履歴

| 日付 | 内容 | 起票 |
| --- | --- | --- |
| 2026-05-23 | 初版 (P0-2, OOM postmortem follow-up) | infra |
