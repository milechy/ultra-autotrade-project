# deploy_production.sh ゼロダウンタイムデプロイ 設計検討

調査日: 2026-04-26  
Asana: 1214253004741363  
Due: 2026-04-28（設計検討のみ、実装は別タスク）  
担当: Claude Sonnet 4.6

---

## TL;DR

**推奨案: 案A（nginx リバースプロキシ + Blue/Green デプロイ）**

- 実装工数: 約 4〜5 時間
- ダウンタイム: 0 秒（nginx reload は Linux カーネル保証）
- Hetzner 追加リソース: ~10 MB RAM（nginx コンテナ）
- 前提変更: Cloudflare ダッシュボードの Tunnel Ingress を 1 回変更（localhost:8000 → localhost:8080）

案Bは案Aに近い本格度だがコンテナ数が増え複雑。案Cは最小変更で downtime を 5〜8 秒に短縮できるが「真のゼロダウンタイム」ではない。

---

## 1. 現状の deploy_production.sh 分析

### 1-1. バックエンドデプロイの流れ（--backend-only）

```bash
# scripts/deploy_production.sh L178-L191
docker compose stop backend                           # ← ここで :8000 が停止
docker compose build backend                          # ← ビルド（キャッシュ有効だが数秒）
docker compose up -d backend                          # ← 起動（uvicorn 初期化 ~3秒）
wait_healthy "http://localhost:8000/health" "backend" # ← 最大60秒待機
```

**ダウンタイム発生区間:** `stop` 完了〜`up -d` 後に `/health` が 200 を返すまで。  
実測値は約 8〜15 秒（uvicorn 起動 + DB 接続確立 + FastAPI startup events）。

### 1-2. フルデプロイの流れ

```bash
docker compose down --remove-orphans  # 全コンテナ停止（postgres も含む）
docker rmi -f <frontend-images>       # フロントイメージ完全削除
docker compose build --no-cache frontend  # Next.js ビルド（2〜4 分）
docker compose build backend
docker compose up -d
wait_healthy backend + frontend       # 合計最大 120 秒
```

**ダウンタイム:** `down` 完了〜全コンテナ healthy まで。フロント再ビルドを含めると 3〜5 分。

### 1-3. フロントエンドデプロイの流れ（--frontend-only）

```bash
docker compose stop frontend          # ← :3000 停止
docker rmi -f <frontend-images>       # イメージ削除
docker compose build --no-cache frontend  # 2〜4 分
docker compose up -d frontend
wait_healthy "http://localhost:3000"
```

**ダウンタイム:** Next.js ビルド全体（2〜4 分）。最も長い。

### 1-4. 現状のトラフィック経路

```
Internet
  └─ Cloudflare CDN (WAF/DDoS)
       └─ Named Tunnel（ダッシュボード管理の Ingress Rules）
            └─ cloudflared コンテナ (network_mode: host)
                 ├─ localhost:3000  → frontend コンテナ (:3000)
                 └─ localhost:8000  → backend コンテナ (:8000)
```

**制約:** cloudflared は Named Tunnel + dashboard 管理 Ingress のため、
upstream の切り替えにはダッシュボード操作またはリロードが必要。  
→ これが「ポート前段に何かを置く」必要性の根拠。

---

## 2. UATa 環境制約まとめ

| 制約 | 詳細 |
|------|------|
| ホスト | Hetzner VPS 単一ノード（1 台のみ） |
| オーケストレーション | Docker Compose v3.9（Swarm / k8s なし） |
| Tunnel | Cloudflare Named Tunnel（dashboard Ingress 管理） |
| Ports（本番） | 3000 (frontend) / 8000 (backend) / 5432 (postgres) |
| Ports（staging） | 3001 / 8001 / 5433（127.0.0.1 バインド分離） |
| VPS リソース | RAM は限定的（推定 4〜8 GB、postgres + backend + frontend + loki/promtail で使用中） |
| DB | PostgreSQL 16 + pgvector（volume 永続化） |
| デプロイ方式 | Hetzner 上で `deploy_production.sh` を手動実行 |
| cloudflared | `network_mode: "host"` で `localhost:PORT` に転送 |

**ゼロダウンタイムの本質的な課題:**  
2 コンテナが同一ポートにバインドできない。新旧コンテナを同時に動かしてトラフィックを切り替えるには、
前段に「切り替え役」が必要。

---

## 3. 手法比較

| 手法 | 実装複雑度 | 追加 RAM | ロールバック | 真のゼロ DT | UATa 適合 |
|------|-----------|----------|-------------|------------|----------|
| 案A: nginx + Blue/Green | ★★☆ 中 | ~10 MB | ◎ nginx reload | ✅ | ✅ |
| 案B: Traefik + Blue/Green | ★★★ 高 | ~30 MB | ◎ ラベル切替 | ✅ | △（複雑） |
| 案C: Build 先行 + Graceful stop | ★☆☆ 低 | 0 MB | △ 手動ロールバック | ❌（5〜8 秒 DT） | ✅（最小変更） |

---

## 4. 案A: nginx リバースプロキシ + Blue/Green デプロイ（推奨）

### 4-1. アーキテクチャ

```
cloudflared (host)
  ├─ localhost:8080 → nginx (:8080)
  │                     ├─ upstream backend-blue  (内部 :8010) [active or standby]
  │                     └─ upstream backend-green (内部 :8011) [standby or active]
  └─ localhost:3000 → frontend（変更なし）
```

- cloudflared Ingress 変更（初回 1 回のみ）: `localhost:8000 → localhost:8080`
- nginx が内部ポート（:8010/:8011）への転送を担う
- `nginx -s reload` でトラフィックを切り替える（reload は zero-downtime 保証）

### 4-2. docker-compose.production.yml 変更案

```yaml
services:
  nginx:
    image: nginx:1.27-alpine
    container_name: ultra-autotrade-nginx-production
    ports:
      - "8080:8080"  # cloudflared を localhost:8000 → localhost:8080 に変更（1回のみ）
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./docker/nginx/upstream.conf:/etc/nginx/conf.d/upstream.conf:rw
    restart: always
    networks:
      - production-net

  backend-blue:
    container_name: ultra-autotrade-backend-production-blue
    # ... (既存 backend と同じビルド設定)
    ports:
      - "127.0.0.1:8010:8000"  # ホスト :8010 → コンテナ内 :8000
    networks:
      - production-net

  backend-green:
    container_name: ultra-autotrade-backend-production-green
    # ... (同上)
    ports:
      - "127.0.0.1:8011:8000"  # ホスト :8011 → コンテナ内 :8000
    networks:
      - production-net
```

### 4-3. nginx 設定ファイル

`docker/nginx/nginx.conf`:
```nginx
events { worker_processes auto; }

http {
  upstream backend_active {
    include /etc/nginx/conf.d/upstream.conf;  # 動的切り替え対象
    keepalive 32;
  }

  server {
    listen 8080;
    location / {
      proxy_pass         http://backend_active;
      proxy_http_version 1.1;
      proxy_set_header   Connection "";
      proxy_read_timeout 90s;
      proxy_connect_timeout 5s;
    }
  }
}
```

`docker/nginx/upstream.conf`（初期値）:
```nginx
server 127.0.0.1:8010;  # blue がアクティブ
```

### 4-4. deploy_production.sh 追加ロジック（--backend-only モード）

```bash
deploy_backend_zero_downtime() {
  local active_port
  active_port=$(grep -oP '\d+' docker/nginx/upstream.conf | head -1)

  # 新旧スロットを決定
  if [ "${active_port}" = "8010" ]; then
    local new_slot="green"; local new_port=8011
    local old_slot="blue";  local old_port=8010
  else
    local new_slot="blue";  local new_port=8010
    local old_slot="green"; local old_port=8011
  fi

  log "Blue/Green: ${old_slot}(:${old_port}) → ${new_slot}(:${new_port})"

  # 1. 新コンテナをビルド（旧コンテナは動いたまま）
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build "backend-${new_slot}"

  # 2. 新コンテナを起動（新ポートで）
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --no-deps "backend-${new_slot}"

  # 3. 新コンテナのヘルスチェック（ポート直打ち）
  wait_healthy "http://127.0.0.1:${new_port}/health" "backend-${new_slot}"

  # 4. nginx upstream を切り替え（reload = zero-downtime）
  echo "server 127.0.0.1:${new_port};" > docker/nginx/upstream.conf
  docker exec ultra-autotrade-nginx-production nginx -s reload
  log "✅ nginx upstream → ${new_slot}(:${new_port}) に切り替え完了"

  # 5. 旧コンテナを graceful stop（既存接続が自然に閉じるのを待ってから停止）
  sleep 5
  ${DC} -f "${COMPOSE_FILE}" stop "backend-${old_slot}"
  log "✅ 旧コンテナ(${old_slot}) 停止完了"
}
```

### 4-5. Pros / Cons

**Pros:**
- nginx reload は Linux カーネル保証の zero-downtime（既存接続を処理しながら新コンフィグを適用）
- cloudflared への影響は Ingress ポート変更 1 回のみ（初回セットアップ後は不変）
- ロールバックが 1 コマンド: `upstream.conf` を戻して `nginx -s reload`
- nginx は軽量（~10 MB RAM）
- --backend-only のみ変更、フルデプロイ・フロントのみは現行フローを維持可能
- Blue/Green の同時稼働は「切り替え中の数十秒」のみ（RAM ダブル消費は一時的）

**Cons:**
- Cloudflare ダッシュボードで Tunnel Ingress を 1 回変更が必要（localhost:8000 → localhost:8080）
- docker-compose.production.yml に nginx + 2 サービス追加で yml が複雑化
- `upstream.conf` ファイルをコンテナにマウントするため、Hetzner VPS 上にディレクトリが必要
- フロントエンドの大幅なダウンタイム（ビルド 2〜4 分）は本案では解決しない（別途対応が必要）

### 4-6. 推定工数

| 作業 | 工数 |
|------|------|
| docker-compose.production.yml 変更（nginx + blue/green） | 1.0 h |
| nginx 設定ファイル作成（docker/nginx/） | 0.5 h |
| deploy_production.sh の `deploy_backend_zero_downtime()` 実装 | 1.5 h |
| Cloudflare ダッシュボード変更 + 疎通確認 | 0.5 h |
| ローカル + staging での統合テスト | 1.0 h |
| **合計** | **4.5 h** |

---

## 5. 案B: Traefik ラベルベースルーティング

### 5-1. アーキテクチャ

```
cloudflared → localhost:80 (Traefik) → backend (Docker ラベルで routing 制御)
```

Traefik の設定は Docker ラベルで完結するため、compose ファイル外に nginx 設定ファイルを別管理する必要がない。

### 5-2. docker-compose.production.yml 変更案

```yaml
services:
  traefik:
    image: traefik:v3.3
    container_name: ultra-autotrade-traefik-production
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
      - "--entrypoints.backend.address=:8080"
    ports:
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - production-net

  backend-blue:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.backend.entrypoints=backend"
      - "traefik.http.routers.backend.rule=PathPrefix(`/`)"
      - "traefik.http.services.backend.loadbalancer.server.port=8000"
      - "traefik.http.services.backend.loadbalancer.server.weight=100"  # active

  backend-green:
    labels:
      - "traefik.enable=true"
      - "traefik.http.services.backend-green.loadbalancer.server.port=8000"
      - "traefik.http.services.backend-green.loadbalancer.server.weight=0"  # standby
```

### 5-3. Blue/Green 切り替え

```bash
# Traefik はラベル変更を Docker API 経由で検知して自動的に routing を更新する
docker compose up -d backend-green  # 新コンテナ起動（weight=0 なのでトラフィックなし）
# health check 後、weight 逆転
docker container update --label-add traefik.http.services.backend-green.loadbalancer.server.weight=100 backend-green
docker container update --label-add traefik.http.services.backend.loadbalancer.server.weight=0 backend-blue
```

### 5-4. Pros / Cons

**Pros:**
- ラベルベースで設定ファイル管理不要
- Traefik の自動サービス検出（Docker socket 経由）
- Canary リリース（traffic splitting %）など将来拡張が容易
- ダッシュボード UI で routing 状態を可視化できる

**Cons:**
- 案Aより設定複雑度が高い（Traefik 概念の学習コスト）
- Docker socket を Traefik に渡す（セキュリティリスク: read-only マウント + 権限制限が必要）
- メモリ ~30 MB（nginx より重い）
- ラベル動的変更が Docker API 経由のため操作が煩雑
- Traefik v3.x の設定変更が頻繁で yml の陳腐化リスク

**推定工数:** 6〜8 時間（Traefik 習熟コストを含む）

---

## 6. 案C: Build 先行 + Graceful Stop（最小変更版）

### 6-1. アーキテクチャ

既存の docker-compose.production.yml、cloudflared の設定を一切変更しない。
`deploy_production.sh` の実行順序の改善のみで downtime を短縮する。

**考え方:** `docker compose build` は実行中のコンテナに影響しない。Build を先に終わらせ、stop → up の間隔を最小化する。

### 6-2. 改善版 --backend-only フロー

```bash
deploy_backend_minimal_dt() {
  # 1. 旧コンテナが動いている間にビルド（ダウンタイムが発生しない）
  log "Backend をビルド中（旧コンテナは稼働継続）..."
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build backend

  # 2. uvicorn が in-flight リクエストを処理できるよう SIGTERM を送って graceful stop
  #    (--time 30 = 30秒のドレイン猶予)
  log "Graceful stop (30秒ドレイン)..."
  docker stop --time 30 "${BACKEND_CONTAINER}" 2>/dev/null || true
  docker rm -f "${BACKEND_CONTAINER}" 2>/dev/null || true

  # 3. 新コンテナ起動（ビルド済みイメージを使うので起動が速い）
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --no-deps backend

  wait_healthy "http://localhost:8000/health" "backend"
}
```

### 6-3. ダウンタイム試算

| フェーズ | 所要時間 |
|---------|---------|
| Build（旧コンテナ稼働中） | 20〜60 秒（ダウンタイムではない） |
| docker stop（SIGTERM 送信〜プロセス終了） | 1〜3 秒（uvicorn graceful） |
| docker rm + up -d（コンテナ再生成） | 1 秒 |
| uvicorn 起動〜health check 200 | 3〜5 秒 |
| **実質ダウンタイム** | **約 5〜8 秒**（現状 10〜15 秒から約 40% 削減） |

### 6-4. Pros / Cons

**Pros:**
- deploy_production.sh のみの変更（docker-compose.yml, cloudflared 不変）
- リスクが低い（新しいコンポーネントなし）
- 実装工数 1〜2 時間
- ロールバックは git revert の 1 コマンド

**Cons:**
- 真のゼロダウンタイムではない（5〜8 秒の停止が残る）
- uvicorn の graceful shutdown は `--graceful-timeout` の設定に依存
  - 未設定の場合は 10 秒でタイムアウト、大量リクエスト中は接続が切れる可能性
- フロントエンドのビルド時間（2〜4 分）は解決しない

### 6-5. 推定工数

| 作業 | 工数 |
|------|------|
| deploy_production.sh の build 先行化 | 0.5 h |
| uvicorn コマンドへの `--graceful-timeout` 追加 | 0.5 h |
| テスト（ローカル + staging） | 0.5 h |
| **合計** | **1.5 h** |

---

## 7. フロントエンドのダウンタイム対策（3 案共通の補完策）

バックエンドのゼロダウンタイム化と独立して実施できる改善。

### 7-1. Next.js ビルドの事前実行

現状: フロントエンドデプロイ = stop → rm → build (2〜4 分) → up

改善: build を旧コンテナが動いている間に実施する。

```bash
deploy_frontend_prebuilt() {
  # 1. 旧コンテナが動いている間に --no-cache ビルド（2〜4 分のダウンタイムを排除）
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache frontend

  # 2. 短時間の stop → up（ビルド済みイメージ使用）
  ${DC} -f "${COMPOSE_FILE}" stop frontend
  docker rm -f "${FRONTEND_CONTAINER}" 2>/dev/null || true
  ${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --no-deps frontend
  wait_healthy "http://localhost:3000"
}
```

**効果:** フロントダウンタイムが 2〜4 分 → 5〜10 秒に短縮（ゼロにはならないが大幅改善）。

### 7-2. Cloudflare のエッジキャッシュ活用

Next.js の静的ページ（`/`, `/login` 等）は Cloudflare がエッジキャッシュするため、
フロントエンドが短時間停止しても多くのユーザーには影響が出ない。
動的 API call（/api/*）は backend のゼロダウンタイム化（案A）で対処。

---

## 8. 推奨案の選定

### 選定: 案A（nginx + Blue/Green）

#### 理由

1. **真のゼロダウンタイム** — `nginx -s reload` は POSIX 仕様で既存接続を引き継ぎ新コンフィグを適用。山本さんが AI 判定を確認しているタイミングでもリクエストが切れない。

2. **リソース影響が軽微** — nginx:alpine は 10〜15 MB RAM。Blue/Green の同時稼働は切り替え中の数十秒のみ。

3. **段階的実装が可能** — まずバックエンドの Blue/Green を実装し、フロントエンドは後回しにできる。

4. **ロールバックが確実** — `upstream.conf` を戻して `nginx -s reload` で即座に旧コンテナへ切り戻し可能。旧コンテナは停止後 5 分間生きているため実質的に確実。

5. **UATa 環境に適合** — cloudflared の Ingress ポート変更 1 回以外、既存インフラを変更しない。postgres, loki, promtail は影響ゼロ。

#### 実装優先順位

```
Phase 1 (1.5h): docker/nginx/ ディレクトリ作成 + nginx.conf + upstream.conf
Phase 2 (1.5h): docker-compose.production.yml に nginx + backend-blue + backend-green 追加
Phase 3 (1.0h): deploy_production.sh に deploy_backend_zero_downtime() 追加
Phase 4 (0.5h): Cloudflare ダッシュボード Ingress 変更 + staging で疎通確認
Phase 5 (1.0h): 本番適用 + ヘルスチェック確認
```

#### リスクと軽減策

| リスク | 軽減策 |
|--------|--------|
| nginx 起動失敗で全トラフィック遮断 | staging で先行テスト、cloudflared Ingress に旧ポート(:8000)フォールバック設定 |
| upstream.conf の競合（並行デプロイ） | `flock` でデプロイスクリプトの同時実行を排除 |
| Blue/Green コンテナの DB 接続数 2 倍 | 切り替え後 5 秒で旧コンテナを stop するため接続上限に影響なし |
| Cloudflare ダッシュボード変更ミス | staging で先行テスト（staging は :8001 直向きのため変更不要） |

---

## 9. 次タスク提案

### タスク A1（本案の実装 — P1）

**タイトル:** deploy_production.sh ゼロダウンタイム実装（nginx + Blue/Green）  
**Asana GID:** 新規作成推奨  
**工数見積:** 4.5 時間  
**依存:** 本ドキュメント（設計承認後）  
**実装順:**
1. `docker/nginx/` 設定ファイル作成
2. `docker-compose.production.yml` 変更（nginx + blue/green サービス）
3. `deploy_production.sh` に `deploy_backend_zero_downtime()` 追加
4. staging 確認 → 本番適用

### タスク A2（フロントエンドのビルド先行化 — P2）

**タイトル:** frontend deploy の Build-first 化（downtime 2〜4 分 → 10 秒）  
**工数見積:** 1.5 時間  
**依存:** 案Aと独立して実施可能

---

## 参照

- nginx upstream reload zero-downtime: https://nginx.org/en/docs/control.html
- Docker Compose Blue/Green pattern: https://docs.docker.com/compose/how-tos/
- cloudflared Named Tunnel ingress: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- uvicorn graceful shutdown: https://www.uvicorn.org/deployment/#running-with-gunicorn
- deploy_production.sh: `scripts/deploy_production.sh`
- docker-compose.production.yml: `docker-compose.production.yml`
- 過去インシデント（2026-04-02 cloudflared + network_mode:host）: `CLAUDE.md` §デプロイ時の教訓
