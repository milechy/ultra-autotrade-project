# staging ビルド高速化設計書

> 作成: 2026-05-20 (night-mode タスク #6 / GID: 1214961931282135)
> 対象: staging-new stack (`docker-compose.staging.yml`)
> 注意: docker-compose.staging.yml は Tier S ファイル。実装変更は別タスク・1日1PR。

---

## 現状分析

### ボトルネック推定

deploy_production.sh の出力 (2026-05-20 本番デプロイ) から backend build 時間を観測:

```
[+] Building 65.7s (22/22) FINISHED
  builder 3/7: apt-get install gcc libpq-dev        7.3s
  builder 5/7: pip wheel (requirements.txt)         13.3s
  runtime 3/9: apt-get upgrade + libpq5 curl        4.8s
  runtime 5/9: pip install from wheels              15.3s
  exporting layers                                  20.9s
  unpacking image                                    3.6s
```

**合計: ~65秒 (backend)。frontend は別途 (Next.js build で 3-5分推定)**

### 最大ボトルネック

| # | ステージ | 時間 | 原因 |
|---|---|---|---|
| 1 | `exporting layers` | 20.9s | 変更のないレイヤーも全再エクスポート |
| 2 | `pip install from wheels` | 15.3s | wheel キャッシュなし (--no-cache-dir) |
| 3 | `pip wheel requirements.txt` | 13.3s | requirements.txt 変更なしでも毎回実行 |

### 現状の build 実行コマンド

```bash
# deploy_production.sh 内
docker compose --env-file .env.production -f docker-compose.production.yml \
  build --no-cache backend-green
```

**`--no-cache` が全レイヤーキャッシュを無効化している** が根本原因。

---

## 改善案

### 案 A (推奨): `--no-cache` をやめて BuildKit + inline cache を使う

**効果:** requirements.txt が変わっていなければ pip wheel ステップがキャッシュヒット → **40秒短縮 (65s → ~25s)**

```dockerfile
# Dockerfile (現状のまま変更不要)
# ── Stage 1: Builder ──
FROM python:3.11-slim AS builder
WORKDIR /build
COPY backend/requirements.txt .
RUN pip wheel ...   # ← requirements.txt が変わらなければキャッシュヒット
```

```bash
# deploy_production.sh の変更点:
# 変更前:
docker compose build --no-cache backend-green

# 変更後:
DOCKER_BUILDKIT=1 docker compose build \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  backend-green
```

**リスク:** イメージに古いコードが残る可能性 → `COPY backend/ backend/` はアプリコードをコピーするレイヤーなので、コード変更時は必ずキャッシュがミスする。requirements.txt が変わらない限り pip wheel のみキャッシュ流用される。安全。

**注意:** セキュリティパッチ (`apt-get upgrade`) はキャッシュされる可能性あり → 週次で `--no-cache` を入れる cron を別途設ける。

---

### 案 B: registry cache (BuildKit `--cache-from/--cache-to`)

**効果:** CI や別ホストでのビルドでもキャッシュ共有 → **20-50秒短縮**

```bash
DOCKER_BUILDKIT=1 docker buildx build \
  --cache-from type=registry,ref=ghcr.io/milechy/ultra-autotrade-backend:cache \
  --cache-to type=registry,ref=ghcr.io/milechy/ultra-autotrade-backend:cache,mode=max \
  -t ultra-autotrade-project-backend-green:latest \
  -f Dockerfile .
```

**前提条件:** GHCR または Docker Hub への push 権限、GitHub Actions との連携。
**実装コスト:** 高 (compose.yml + CI 両方の変更が必要)

---

### 案 C: frontend Next.js build の最適化

**現状推定:** `npm ci` + `next build` で 3-5分。

```dockerfile
# frontend/Dockerfile の改善点
# 変更前:
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps   # package.json が変わらなければキャッシュヒット

# → COPY src/ の前に npm ci を置くと、src 変更時は npm ci キャッシュが流用される
# (現状 Dockerfile が既にこの順序であれば効果なし)
```

---

## 推奨実装計画

### Phase 1 (Tier A / 30分): `--no-cache` 削除 + BuildKit 有効化

対象ファイル:
- `scripts/deploy_production.sh` (Tier S — 1日1PR)
- `scripts/deploy_staging.sh` (Tier S)

変更内容:
```bash
# deploy_*.sh の build コマンドを変更
- docker compose build --no-cache backend-green
+ DOCKER_BUILDKIT=1 docker compose build backend-green
```

週次セキュリティビルド (cron 日曜):
```bash
# scripts/weekly_nocache_build.sh (新規, Tier B)
DOCKER_BUILDKIT=1 docker compose build --no-cache backend-blue backend-green
```

### Phase 2 (Tier B / 60分): frontend COPY 順序の最適化 (要確認)

```bash
# frontend/Dockerfile の現状を確認してから判断
grep -n "COPY\|RUN npm" frontend/Dockerfile
```

---

## 期待値

| 項目 | 現状 | 改善後 |
|---|---|---|
| backend build (requirements 未変更) | 65s | **~25s** (△40s) |
| backend build (requirements 変更時) | 65s | 65s (変化なし) |
| frontend build (src のみ変更) | ~180s | ~120s (△60s、案C適用時) |
| 週次フル再ビルド | なし | 日曜 03:00 に --no-cache で自動実行 |

---

## 実装時の注意

- `docker-compose.staging.yml` は Tier S: 1日1PR 制約あり
- `deploy_production.sh` も Tier S: CLAUDE.md 分割 PR と同日に出さない
- Phase 1 実装 PR は `fix(deploy): BuildKit 有効化 + weekly nocache build 追加` として起票
- Gate 1-3 (verify.sh) + 本番 VPS で staging を試験ビルドして時間計測してから merge

---

*実装は別タスク化 (本設計書は設計のみ)*
