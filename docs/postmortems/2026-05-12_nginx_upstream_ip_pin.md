# Postmortem: nginx upstream IP 固着で frontend-only deploy 直後に本番 502

| 項目 | 値 |
|---|---|
| 発生日時 | 2026-05-12 12:00 JST (production) / 同 15:25 JST (staging-new 二次発見) |
| 検出 | 2026-05-12 12:00 (production) — `deploy_production.sh --frontend-only` 実行直後にユーザー操作が 502 |
| 復旧 | 2026-05-12 15:23 (production) — `docker restart ultra-autotrade-nginx-production` で復旧 (3 時間 23 分継続) |
| 影響範囲 | production の Cloudflare 経由 `https://api.ultra-auto-trade.com/*` 全リクエストが 502。frontend SSR ヘルスチェック / `localhost:8010` 直撃は 200 で正常。 |
| Severity | P0 (本番 API 全停止) |
| Owner | claude.ai (PM) + Claude Code (実装) |

## TL;DR

`docker/nginx/nginx.conf` の `upstream backend_active` ブロックで `server backend-blue:8000` (Docker hostname) を直書きしつつ `resolver` ディレクティブを宣言していなかったため、nginx は起動時に 1 回だけ Docker embedded DNS (`127.0.0.11`) で hostname を解決してワーカーメモリに**永続キャッシュ**していた。`scripts/deploy_production.sh --frontend-only` が `docker compose up -d frontend` を `--no-deps` フラグなしで実行したため compose が依存関係を再評価して backend を recreate、Docker bridge IP が変動 → nginx は古い IP に固着し続けて 502。`docker restart nginx` で再解決して復旧。

恒久対策として nginx に `resolver 127.0.0.11 valid=5s ipv6=off;` を追加し、`upstream` ブロックを撤去して `proxy_pass http://$backend;` の変数経由に変更。同時に `deploy_{production,staging}.sh --frontend-only` を `--no-deps --force-recreate` 必須化し、post-deploy で Cloudflare 経由 `/health` 5 回連続 200 を確認 + 失敗時 nginx 自動 reload を追加。

## タイムライン (JST)

| 時刻 | 事象 |
|---|---|
| 12:00 | production で `./scripts/deploy_production.sh --frontend-only` 実行 |
| 12:00:XX | frontend container 再生成。直後から Cloudflare 経由 `/api/*` が 502 |
| 12:00 – 15:23 | 山本さん (本番テスター) の操作が全て失敗。原因切り分けに 3h+ |
| 15:22 | `docker restart ultra-autotrade-nginx-production` 実行 |
| 15:22:42 (UTC 06:22:42) | nginx 起動完了、Docker DNS で backend-blue → 172.18.0.5 を再解決 |
| 15:23 | Cloudflare 経由 `/health` = 200 復旧確認 |
| 15:30 | claude.ai が RCA 調査を Claude Code (Opus 4.7) に依頼 |
| 15:32 | Phase 1 read-only 調査開始 (Hetzner ssh) |
| 15:45 | staging-new でも**同型 502 を抱えたまま放置されていた**ことを発見 (`/health` = 502) |
| 15:50 | staging-new の nginx error.log で**生証拠取得**: `upstream: "http://172.19.0.6:8000/health" connect() failed (113: Host is unreachable)` (backend 実 IP は 172.19.0.5) |
| 15:55 | staging-new で `docker restart nginx-staging-new` → 200 復旧 (本番と同じ復旧パターン) |
| 16:00 | RCA レポート確定。Option 1 (resolver + 変数 proxy_pass) + Option 2 (deploy script --no-deps + post-deploy reload) 採用 |
| 16:15 - 17:00 | 本 PR の実装・staging-new 検証・PR 作成 |

## 真因 (Root Cause)

### 一次原因
`docker/nginx/nginx.conf` に **`resolver` ディレクティブが未設定**。`upstream` ブロック内の `server backend-blue:8000` は nginx 起動時にのみ Docker embedded DNS で解決され、結果はワーカープロセスメモリに永続キャッシュされる (nginx OSS の標準動作)。

### 二次原因 (トリガー)
`scripts/deploy_production.sh` L367-384 の `--frontend-only` 経路が、CLAUDE.md L1009「本番フロントエンド操作ルール」(2026-04-17 追加) で**必須**と定められた `--no-deps --force-recreate` フラグを欠いた `docker compose up -d frontend` を実行していた。これにより compose が依存関係を再評価し、backend container を recreate (= Docker bridge IP 変動) するパスが開いていた。

### 三次原因 (RCA 困難化)
`promtail` の `scrape_configs` が `/var/log/*log` (ホスト) のみを対象としており、nginx コンテナ内の `/dev/stderr` (= docker logs) を Loki に取り込んでいなかった。nginx を `docker restart` した瞬間に過去ログが完全消失し、本番側で「どの IP に proxy_pass していたか」の証拠が消えた。

## 証拠

### staging-new で取得した決定的ログ (UTC 06:25-06:32)

```
upstream: "http://172.19.0.6:8000/health"   ← nginx がキャッシュした古い IP
connect() failed (113: Host is unreachable)
rt=3.0  urt=3.0  → 502
```

同時刻の現実:
```
backend-blue 実 IP           = 172.19.0.5
nginx 内 getent backend-blue = 172.19.0.5   ← Docker DNS は正解を返している
nginx upstream cache         = 172.19.0.6   ← 起動時 1 回解決した古い IP に固着
```

### 環境証拠 (pre-fix snapshot — 本 PR で全て修正済)

下表は本 PR (`fix/nginx-upstream-ip-pin-20260512`) **適用前**の状態を示す。
本 PR マージ後はいずれも fixed (詳細は「対策」セクション参照)。

| 項目 | pre-fix の値 | 説明 |
|---|---|---|
| nginx.conf `resolver` 出現回数 | 0 | 致命的 |
| upstream.production.conf | `server backend-blue:8000 max_fails=3 fail_timeout=10s;` | hostname 直書き、起動時 1 回解決 |
| deploy_production.sh L384 | `up -d frontend` (no flags) | CLAUDE.md L1009 違反 |
| promtail target | `/var/log/*log` のみ | nginx container log 取り込みなし (本 PR では未対応、別タスク) |

### Phase 1 復旧確認

| Step | 操作 | 外形 /health | nginx upstream cache |
|---|---|---|---|
| Before | 朝 deploy_staging の置き土産 | **502** | 172.19.0.6 (古い) |
| Restart | `docker restart nginx-staging-new` | **200** ✓ | 172.19.0.5 (再解決) |

## 対策 (本 PR で実装)

### Option 1: nginx 設定変更 (本質修正)

`docker/nginx/nginx.conf`:
```diff
 http {
+    resolver 127.0.0.11 valid=5s ipv6=off;
+    resolver_timeout 3s;
     ...
-    upstream backend_active {
-        include /etc/nginx/conf.d/upstream.conf;
-        keepalive 32;
-    }
     server {
         location / {
-            proxy_pass http://backend_active;
+            include /etc/nginx/conf.d/upstream.conf;
+            proxy_pass http://$backend;
         }
     }
 }
```

`docker/nginx/upstream.{production,staging}.conf`:
```diff
-server backend-blue:8000 max_fails=3 fail_timeout=10s;
+set $backend backend-blue:8000;
```

**効果**: backend container 再生成で IP が変動しても、nginx が TTL 5s で DNS を再解決するため**自動復旧**。`docker restart nginx` 手動対応が不要に。

**トレードオフ**:
- `upstream` block の `keepalive 32` プールは失われる (変数 proxy_pass と両立しない)。本サービスの QPS は低く、TCP セッション再確立コストは無視できる。
- `proxy_next_upstream` は維持しているが、**upstream group の peer failover ではなく同一 `$backend` に対する単純リトライ**として動作する点を運用上明示する必要がある (NGINX OSS の `upstream` block 撤去に伴う必然的挙動差)。Blue/Green 切替時の peer failover は `write_upstream_conf` + `nginx -s reload` で行う仕組みは従来どおり機能する。
- `max_fails` / `fail_timeout` は upstream block 専用のディレクティブのため変数 proxy_pass では無効化される。backend 単一インスタンス故障の検知は `proxy_next_upstream` の retry + Slack 通知 (post-deploy gate) でカバー。

### Option 2: deploy script の防御層

`scripts/deploy_{production,staging}.sh` `--frontend-only` 経路:
```diff
-${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d frontend
+${DC} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" \
+  up -d --no-deps --force-recreate frontend

 wait_healthy "http://localhost:3000" "frontend" || on_failure

+# post-deploy: Cloudflare 経由 (production) / nginx 経由 (staging) /health を 5 回試行
+# 失敗時は nginx -s reload で upstream を強制再解決
+# それでも 200 にならなければ on_failure
```

**効果**: Option 1 が機能しない/退行した場合の**保険**。`--frontend-only` deploy 直後の 502 を 15 秒以内に自動検出・自動復旧。

### Option 3: 採用見送り (アーキ変更)

nginx を撤去して cloudflared → backend 直接 ingress に変更する案は、Blue/Green の前提が崩れるため 5/31 ローンチに間に合わない。将来的なアーキ改善として保留。

## 検証方法 (DoD)

### staging-new での本番反映前検証
1. PR を staging-new に手動 deploy
2. `docker rm -f ultra-autotrade-backend-blue-staging-new && docker compose up -d --no-deps backend-blue` で backend recreate を誘発
3. 直後に外形 `/health` を 30 秒間 1 秒ごとに polling → **5 秒以内に再 200** であることを確認
4. nginx error.log の `upstream` が新 IP に切り替わっていることを確認

### Playwright E2E
`frontend/e2e/nginx-upstream-recovery.spec.ts` (新規、smoke test):
- 指定の `HEALTH_URL` (デフォルト production) を 5 回連続で叩いて全て 200 を要求する
- 1 回目のレスポンス body に `status` / `scheduler_healthy` フィールドが含まれることを確認 (nginx 固定レスポンスでなく backend FastAPI が実際に応答していることの担保)
- chaos test (backend recreate での自動復旧) は Playwright spec では実施せず、deploy_staging.sh 経由の手動 chaos 検証 (本 PR の DoD で staging-new で実施済) に委ねる。Playwright は CI で定期的に「経路が通っているか」を見張る smoke 役割

## 再発防止

CLAUDE.md 末尾に教訓セクション追記:

1. **nginx の upstream に hostname を直書きする場合は必ず `resolver` を併設する。**
2. **`deploy_{production,staging}.sh --frontend-only` 経路は `--no-deps --force-recreate` 必須。**
3. **post-deploy で外形 `/health` を必ず確認する (Gate 8 拡張)。**
4. **nginx コンテナのログは Loki に取り込む** (本 PR では未実装、別 Asana タスクで対応)。

### Dashboard 管理設定の事故パターン (4 回目)

| 日付 | 事象 | 共通点 |
|---|---|---|
| 2026-04-02 | cloudflared token 方式で ingress が Dashboard 管理化 | Dashboard 設定とコードが非連動 |
| 2026-05-01 | production cloudflared が `localhost:8000` のまま Blue/Green 切替 → 502 (PR #163) | nginx port 変更 vs Dashboard ingress 非連動 |
| 2026-05-09 | staging cloudflared が `localhost:8001` のまま → 502 (12 日遅延検出) | 同上、PR #163 教訓の水平展開漏れ |
| **2026-05-12** | **nginx upstream IP 固着で frontend-only deploy 直後 502** | **resolver 未設定 + `--no-deps` 不在の二重バグ** |

## 関連ファイル / リンク

- `docker/nginx/nginx.conf` (本 PR で変更)
- `docker/nginx/upstream.production.conf` / `upstream.staging.conf` (本 PR で変更)
- `scripts/deploy_production.sh` L367-396 (本 PR で変更)
- `scripts/deploy_staging.sh` L311-333 (本 PR で変更)
- `CLAUDE.md` L1009 「本番フロントエンド操作ルール」(2026-04-17 既存)
- `docs/postmortems/2026-05-09_staging_api_502.md` (前回の Cloudflare ingress + nginx port mismatch RCA)
- Asana タスク (要追加): "promtail に nginx コンテナログ scrape 設定追加"
- Slack `#ultra-auto-project`: 2026-05-12 12:00-15:23 の 502 アラート (もし残っていれば)
