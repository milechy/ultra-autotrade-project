# CLAUDE Lessons Learned

> 本番インシデント・教訓の時系列アーカイブ (2026-05-21 refactor で `CLAUDE.md` から分離)。
> 古い順 → 新しい順で並べる。参照元: `CLAUDE.md §参照ファイル`。
> 朝プロトコル §9 Step 0 で SessionStart Hook 経由で auto-Read される。

---

## 2026-04-01 デプロイ時の教訓

**環境変数:**
- `echo 'KEY=VALUE' >> .env.staging` は前行に改行がないと連結される（例: `OCTOBOT_API_KEY=dummyNEXT_PUBLIC_BACKEND_BASE_URL=...`）。必ず `printf '\nKEY=VALUE\n' >> file` を使う
- `docker compose restart` は環境変数を再読み込みしない場合がある。確実に反映するには `docker compose up -d --no-deps --build <service>`

**DB マイグレーション:**
- 新しいSQLAlchemyカラム追加後のデプロイでは、必ずモデル定義とDBカラムを比較して `ALTER TABLE ADD COLUMN IF NOT EXISTS` を実行。確認コマンド:
  `docker exec <postgres-container> psql -U ultra -d ultra_autotrade -c "SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position;"`

**CORS と 500エラーの混同:**
- FastAPIは500エラー時にCORSヘッダーを付けない。ブラウザではCORSエラーに見えるが、実態はバックエンドの500（DB不足カラム等）。CORS問題に見えたらまずバックエンドログを確認:
  `docker logs <backend-container> 2>&1 | grep -i 'error\|undefined.*column\|does not exist'`

**Mixed Content:**
- httpsトンネル経由のフロントエンドから httpバックエンドへのリクエストはブラウザにブロックされる（Mixed Content）。トンネル使用時はフロントエンド・バックエンド両方をトンネル経由にするか、IP直接アクセス（PCのみ）を使う

**孤立Dockerコンテナ:**
- `docker compose down --remove-orphans` で消えない場合は `docker rm -f <container-name>` で強制削除してから `up -d`

---

## 2026-04-02 cloudflared + network_mode:host

**cloudflared token方式の Ingress Rules:**
- `--token` 方式では ingress ルールは Cloudflare ダッシュボードで管理される（config.yml は無視される）
- ダッシュボードの ingress に `http://localhost:3000` / `http://localhost:8000` が設定されている場合、`network_mode: "host"` が必須

**network_mode: host 使用時の注意:**
- cloudflared コンテナが `localhost` に届くには `network_mode: "host"` が必要
- frontend/backend は `ports: "3000:3000"` / `"8000:8000"` でホストに公開されている必要がある
- `[::1]:3000`（IPv6）と `127.0.0.1:3000`（IPv4）両方で到達可能であること確認済み

**デプロイ手順（502防止）:**
- 正しい手順: `docker rm -f <container> && docker compose up -d --no-deps <service>`
- 空白時間を最小化するため stop → rm → up を連続実行する
- `restart` コマンドは旧イメージのまま再起動するため、新ビルド後には使わない
- cloudflared は `--no-deps` で単独起動（postgres 競合を避ける）

**502デバッグ手順:**
1. `docker ps -a` でコンテナが存在・起動しているか確認
2. `docker logs <frontend>` で Next.js の Ready ログを確認
3. `curl http://127.0.0.1:3000` でホスト → frontend の疎通確認
4. `docker logs <cloudflared>` で `connection refused` が出ていないか確認
5. 502 の多くはデプロイ中の空白期間が原因（数秒で自然解消）

---

## 2026-04-02 AIスケジューラー デフォルト有効化

**スケジューラーはデフォルト有効（DISABLE_ で明示的に停止する方式）:**
- 旧方式: `ENABLE_AI_JUDGMENT_SCHEDULER=1`（デフォルト無効） → 設定漏れで無音停止していた
- 新方式: `DISABLE_AI_JUDGMENT_SCHEDULER=1`（デフォルト有効） → 設定しなければ動く
- 同様に `DISABLE_BACKGROUND_MONITORING=1`（デフォルト有効）
- 旧 `ENABLE_=1` 変数は後方互換として引き続き機能する

**スケジューラーが無効で起動した場合:**
- ERROR ログ + Slack `#ultra-auto-project` に `⚠️ AIスケジューラーが無効状態で起動しました` 通知
- `/health` が `"status": "degraded"` を返す

**デプロイ後の確認手順:**
```bash
curl https://api.ultra-auto-trade.com/health
# → {"status": "ok", "scheduler": true, "last_judgment": "...", "next_judgment": "..."}
```

**`.env.staging.example` との差分確認（デプロイ前必須）:**
```bash
# 2026-04-17以降: productionデプロイ前は .env.production との差分を確認
diff <(grep -v '^#' backend/.env.staging.example | grep '=' | cut -d= -f1 | sort) \
     <(grep -v '^#' /opt/ultra-autotrade/.env.production | grep '=' | cut -d= -f1 | sort)
```

---

## 2026-04-02 Docker Composeプロジェクト名統一

**docker compose は必ず同一プロジェクト名で実行すること:**
- プロジェクト名が異なると各コンテナが別ネットワークに配置され、`postgres` ホスト名が解決できず DB 接続が 500 エラーになる
- 原因: `docker compose up` 実行時のカレントディレクトリや `-p` フラグによりプロジェクト名が変わることがある
- 対策: `.env.staging` に `COMPOSE_PROJECT_NAME=ultra-autotrade-project` を設定済み（この値が自動適用される）
- 確認: `docker inspect <container> --format "{{index .Config.Labels \"com.docker.compose.project\"}}"` で全コンテナのプロジェクト名が同一か確認
- 緊急修正: プロジェクト名が異なる場合は `docker network connect <正しいnetwork> <コンテナ名>` で即座に接続可能

**DB接続500エラーのデバッグ手順:**
1. `docker logs <backend> 2>&1 | grep "could not translate host name"` — postgres名前解決失敗なら本問題
2. `docker inspect <backend> --format "{{json .NetworkSettings.Networks}}"` でネットワーク確認
3. `docker inspect <postgres> --format "{{json .NetworkSettings.Networks}}"` と比較
4. ネットワーク名が異なれば `docker network connect <postgres側network> <backend>` → `docker restart <backend>`

---

## 2026-04-02 Named Tunnel移行時の環境変数

**NEXT_PUBLIC_BACKEND_BASE_URL の更新忘れ:**
- Named Tunnel（trycloudflare → api.ultra-auto-trade.com）移行時、`.env.staging` の `NEXT_PUBLIC_BACKEND_BASE_URL` が古い trycloudflare URL のままになっていた
- Next.js の `NEXT_PUBLIC_` 変数はビルド時に JS に埋め込まれるため、`.env` を変更しただけではダメで **フロントエンドの再ビルドが必須**

**3点セット（必ず同時に実施）:**
1. `NEXT_PUBLIC_BACKEND_BASE_URL=https://api.ultra-auto-trade.com` に更新
2. `CORS_ORIGINS` に `https://app.ultra-auto-trade.com` を追加
3. `docker compose build --no-cache frontend` でフロントエンド再ビルド → コンテナ入れ替え

**確認コマンド:**
```bash
# CORS ヘッダーが新ドメインを返しているか
curl -s -I -H 'Origin: https://app.ultra-auto-trade.com' https://api.ultra-auto-trade.com/health | grep access-control-allow-origin
# 新 URL がビルドに埋め込まれているか
docker exec <frontend> grep -rl 'api.ultra-auto-trade.com' /app/.next/static/chunks/ | wc -l
```

---

## 2026-04-03 フロントエンドAPI系環境変数 → Mixed Content

**フロントエンドのAPI系環境変数は3つある:**
- `NEXT_PUBLIC_BACKEND_BASE_URL` — Knowledge Hub / AI 等バックエンド全般
- `NEXT_PUBLIC_API_BASE_URL` — 認証・汎用 API（`/api/` プレフィックス）
- `NEXT_PUBLIC_API_URL` — 一部コンポーネントが直接参照する API URL

**すべて `frontend/Dockerfile` の `ARG`/`ENV` と `docker-compose.production.yml` の `build.args` に定義が必要。**（2026-04-17以降: 旧 `docker-compose.staging.yml`）
1つでも欠けると Dockerfile ビルド時にフォールバック値（`http://77.42.46.155:8000` 等）がJSバンドルに埋め込まれ、
HTTPS（Named Tunnel）経由のモバイルアクセスで Mixed Content エラーになる（2026-04-03 iPhoneインシデント）。

**PCで顕在化しにくい理由:** ブラウザキャッシュ・Service Worker キャッシュが旧ビルドを返し続けるため、
モバイルや初回アクセスでのみ症状が出ることがある。

**確認・修正手順:**
```bash
# 1. Dockerfile に ARG/ENV が揃っているか確認
grep -E "NEXT_PUBLIC_API" frontend/Dockerfile

# 2. docker-compose.production.yml の build.args に揃っているか確認
grep -A 20 "build:" docker-compose.production.yml | grep "NEXT_PUBLIC_API"

# 3. 不足があれば .env.production に追加し、フロントエンド再ビルド
docker compose -f docker-compose.production.yml build --no-cache frontend
docker compose -f docker-compose.production.yml up -d --no-deps frontend

# 4. 埋め込み URL を確認（http:// が残っていないか）
docker exec <frontend> grep -r "http://77" /app/.next/static/chunks/ | wc -l
```

---

## 2026-04-03 デプロイ・運用 (deploy_production.sh 必須)

- **`scripts/deploy_production.sh` を必ず使う。**（2026-04-17 B案リネーム: 旧 `deploy_staging.sh`）手打ちデプロイは孤立コンテナ（Conflict）、`--env-file` 忘れ（`NEXT_PUBLIC_*` 未焼き込み）、ビルドスキップ（古いイメージ起動）の3問題を毎回引き起こす。`deploy_production.sh` は `down --remove-orphans` → `docker rm -f` → `build --no-cache` → `up -d` → ヘルスチェック → Slack通知まで全自動。`--frontend-only` / `--backend-only` / `--no-build` オプションあり

### Lesson Learned: 2026-05-03 手打ちdeploy違反インシデント（claude.ai生成プロンプト起因）

**事象**: PR #191 デプロイで `docker compose -p ultra-autotrade-project -f docker-compose.production.yml build --no-cache frontend` を**手打ち実行**し、`--env-file .env.production` が抜けて `NEXT_PUBLIC_PRIVY_APP_ID` が空展開でビルドされた。本番ウォレット接続ボタンが完全死亡し、本番テスター（山本さん）が詰まり、復旧に追加 4-5 時間を要した。

**真因**: claude.ai が生成したデプロイプロンプトに `docker compose ... build` 直接コマンドが含まれていた。CLAUDE.md に「`deploy_production.sh` 必須」と上記で明記されていたが、claude.ai 側でルール参照漏れ。`compose config` で確認すると `--env-file` なしでは `${NEXT_PUBLIC_PRIVY_APP_ID:-}` が空展開、ありでは正しい値が解決される、と機械的に再現できた。

**再発防止（絶対遵守）**:
1. **本番 frontend 再ビルドは `./scripts/deploy_production.sh --frontend-only` のみ。** 手打ち `docker compose ... build` を含むプロンプトを生成・実行しない／受け取った場合は拒否して `deploy_production.sh` への置き換えを要求
2. デプロイ後は必ず焼き込み確認（値が JS バンドルに入っているか grep で検証）:
   ```bash
   PRIVY_VAL=$(grep '^NEXT_PUBLIC_PRIVY_APP_ID=' /opt/ultra-autotrade/.env.production | cut -d= -f2-)
   docker exec ultra-autotrade-frontend-production sh -c \
     "grep -lE '$PRIVY_VAL' /app/.next/static/chunks/*.js | wc -l"
   # 0件なら焼き込み失敗 → 即ロールバック
   ```
3. 焼き込み確認パス後も Gate 4 実機検証（Claude in Chrome / Playwright で Privy モーダル発火確認）必須
4. `--env-file` を付け忘れる手打ちが疑われる場合は `docker compose -p ultra-autotrade-project --env-file .env.production -f docker-compose.production.yml config` で `${NEXT_PUBLIC_*}` の解決値を事前確認できる

- **`docker compose build --no-cache` だけでは不十分な場合がある。** `--no-cache` はレイヤーキャッシュをスキップするが、**古いイメージ自体は残る**。COMPOSE_PROJECT_NAMEや--env-fileが不一致だと別名のイメージが使われ続ける。`deploy_production.sh` ではビルド前に `docker rmi -f` でイメージを完全削除してから再ビルドするため、この問題は自動的に回避される。手動で修正する場合は: `docker images | grep frontend | awk '{print $3}' | xargs -r docker rmi -f && docker compose build --no-cache frontend`
- **`docker system prune -af` の後は全コンテナリビルドが必須。** イメージが削除されるため `up -d` しても起動しない。prune後は必ず `deploy_production.sh`（フルビルド）を実行
- **テストアカウント（@ultra-autotrade.com系）は DB ボリューム再作成で消える可能性がある。** 消えた場合は `bcrypt` でハッシュ生成 → `INSERT INTO users` で再作成。Registration API が無効化されている場合がある（`INITIAL_ADMIN_EMAIL` 未設定）

---

## 2026-04-03 スケジューラー・監視

- **`/health` が 200 でもスケジューラーが死んでることがある。** `/health` はアプリ起動の確認であって、バックグラウンドジョブの健全性は保証しない。`scheduler_healthy` フィールドと `warnings` 配列で確認すること
- **`INTERNAL_API_TOKEN` が `.env.production` に未設定だとスケジューラー内部 API 呼び出しが 401 で失敗する。** AI 判定が実質走らず、テスターは「承認待ちの提案はありません」を見続ける。デプロイ後に `docker logs | grep 401` で確認
- **フロントエンドが最後の判定結果を表示し続けるため「AI が動いてる」と誤認しやすい。** HOLD (45%) が表示されていても、それが何時間も前の結果なら実際にはスケジューラーが停止している可能性がある
- **Watchdog（`scheduler_watchdog.py`）が 30 分ごとに監視。** `interval_hours * 2` を超えて未実行なら Slack 通知。`deploy_production.sh` もデプロイ後に `scheduler_healthy` を確認する

---

## 2026-04-03 Codex Review P1 安全装置バグ（修正済み）

- **`MonitoringService` は必ずシングルトン（`get_monitoring_service()`）を使う。** 新規インスタンス化するとHF低下を検知しても緊急停止フラグが global state に伝わらない。`scheduled_tasks.py` の3ループ（`health_check_loop` / `latency_monitor_loop` / `price_change_monitor_loop`）で修正済み
- **`exchange/service.py` の `get_price_change_24h()` は `fetch_ticker().percentage` をそのまま返す（`/100` しない）。** `percentage` はすでにパーセント単位（`-15.0` = -15%）。`/100` すると変動率が 100 分の 1 に縮小され、`SAFE_MODE`（-10%）や `HARD_STOP`（-20%）が発動しなくなる。`workflow.py` 側が `/100` して `StressController` の小数形式に変換する責務を持つ

---

## 2026-04-05 本番デプロイフロー (Hetzner pull only)

- **Hetznerは pull only。直接 git merge / git commit / nano 編集をしない。**
  正規デプロイフロー: ローカルMac → GitHub push → Hetzner `git pull origin main`。
  `22_production_release_checklist.md` 参照。Hetzner上で直接マージすると、
  Hetzner / ローカルMac / GitHub のブランチが不整合になり、復旧に時間がかかる。

- **docker-compose.production.yml の command に alembic を入れない。**
  alembicは requirements.txt に含まれておらず、実行すると exit code 127 でバックエンドが起動しない。
  DB マイグレーションは手動 `ALTER TABLE` 方式（auto-migration なし）。

- **docker-compose.production.yml を手動編集した場合:**
  1. ローカルMacで同じ変更を行う
  2. `git commit` → `git push origin main`
  3. Hetznerで `git pull origin main`
  絶対にHetzner上でコミットしない（push手段がないため行き止まりになる）。

- **NEXT_PUBLIC_* 変数は docker-compose.production.yml の build.args にも必要:**
  `.env.production` に書くだけでは不十分。`build.args` に以下の5つが必要:
  - `NEXT_PUBLIC_BACKEND_BASE_URL`
  - `NEXT_PUBLIC_API_BASE_URL`
  - `NEXT_PUBLIC_API_URL`
  - `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID`
  - `NEXT_PUBLIC_DEFAULT_CHAIN_ID`

---

## 2026-04-08 フロントエンド/バックエンド分離デプロイの罠

**`--frontend-only` デプロイは「バックエンドに新しいAPIがない」ことを意味する:**
- フロントエンドが新しいAPIエンドポイントを呼ぶコードを含む場合、`--frontend-only` でデプロイするとフロントは動くがAPI呼び出しが全て404になる
- 事例: `/admin/proposals` ページが `/api/proposals/admin/all` と `/api/proposals/admin/stats` を呼ぶが、バックエンドが古いまま → KPIカードが「Not Found」エラー
- **ルール: フロントエンドが新しいAPIエンドポイントを参照する変更では、必ずフルデプロイ（`deploy_staging.sh` 引数なし）を使う**
- `--frontend-only` は「CSSやテキスト修正など、APIに変更がない場合」のみ使用

**判断基準（デプロイ前に必ず確認）:**
```bash
git diff main --name-only | grep "^backend/"          # バックエンド変更あり → フルデプロイ
git diff main --name-only | grep "^frontend/lib/api/" # 新しいfetch関数 → フルデプロイ（対応APIが必要）
# 上記に何も出なければ --frontend-only OK
```

---

## 2026-04-15 本番DB操作ルール

**本番DBに対するALTER TABLE / UPDATE / DELETE等の操作手順書を生成する際、コンテナ名・DBユーザー・テーブル名を絶対に推測しない。**
手順書の冒頭に必ず「事前確認ステップ」を入れること:

```bash
# Step 1: コンテナ名を取得
docker ps | grep postgres

# Step 2: DBユーザー名・DB名を取得
docker exec <container> env | grep POSTGRES

# Step 3: テーブル一覧を取得
docker exec <container> psql -U <user> -d <db> -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
```

この3ステップの結果を確認してから、本番SQL手順を生成する。**推測で本番SQLを書くことは禁止。**

---

## 2026-04-17 本番フロントエンド操作ルール

**フロントエンドコンテナ操作は compose ファイルと env-file を必ず明示する。**

```bash
# 本番（必須）
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate frontend

# Staging（必須）
docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d --no-deps --force-recreate frontend
```

**ルール:**
- `docker-compose.production.yml + .env.production` ← 本番専用。他の compose/env の組み合わせ禁止
- `docker-compose.staging.yml + .env.staging-new` ← Staging専用
- Rolling restart は `--no-deps --force-recreate frontend`（他サービス影響なし、前回実績7秒）
- `NEXT_PUBLIC_*` 変数変更時は `build --no-cache frontend` → `up -d --no-deps` の2ステップ必須（env_file だけでは JS バンドルに焼き込まれない）
- デプロイ後は `for i in {1..30}; do curl -s -o /dev/null -w "%{http_code}\n" URL; sleep 1; done` で復旧確認

**過去インシデント（2026-04-17 Phase C）:** `docker-compose.staging.yml` を本番コンテナに誤適用 → 本番502（5分）。正しい compose ファイル指定で12秒で復旧。

---

## 2026-04-19 環境ファイル更新ルール (根本解決原則)

### 禁止事項
- sed -i 等で `.env.staging` と `.env.production` を同時更新することは禁止
  - 理由: 2026-04-18インシデントで両ファイルが完全一致状態に陥り、環境分離の意味を失った
- `.env.production` に以下の値を設定することは禁止:
  - `APP_ENV=staging`
  - `BYBIT_SANDBOX=true`
  - `AAVE_NETWORK=*sepolia*` (Phase 2メインネット移行後)

### 正しい更新手順
1. `.env.staging` を先に編集
2. 内容を確認
3. `.env.production` を別コマンドで編集 (値が本番固有なら差別化)
4. `bash scripts/check_env_separation.sh` で検証
5. コミット

### CIガード
PR作成時に `.github/workflows/env-separation-check.yml` が自動実行される。
失敗したPRはmergeできない。

---

## 2026-04-21 教訓: ドキュメント更新でも E2E 先行と3層確認を徹底

### 何が起きたか

`tester_onboarding_guide.md` v2 と関連 docs 4 ファイルを「Privy でログイン」前提でリライトし、
PR #111/#112 で main 反映。しかし実装の実態は:

- **フロント**: Privy SDK 実装済み（見た目のログイン UI は Privy）
- **バックエンド**: email/password (bcrypt) のみ。`/auth/privy-login` エンドポイント不在
- **DB**: `users` テーブルに `privy_did` カラムなし

結果: 公式ドキュメントが「Privy でログイン」と案内しているが、実際にはバックエンド JWT が
取れずダッシュボードに到達できない状態が本番に出た。Word 版配布用ドキュメントも誤情報で生成済み。

対応: Asana #1214148335864583 でバックエンド Privy 対応タスク化。
マニュアル修正版 (v3) は実装完了後に作成。

### 再発防止ルール

1. **E2E で通してからマニュアルを書く** (`docs/14_test_strategy.md` §10 に連動)
   ユーザー向け手順書 (tester_onboarding_guide / partner_tester_distribution 等) を書く・更新する場合:
   - その手順を Playwright E2E で先に実装して通す
   - E2E で「ユーザーが書かれた通りに操作して目的に到達できる」ことを確認
   - 確認できた手順のみドキュメントに反映し、確認できていない手順は main 禁止

2. **認証・権限系は3層確認** (Pre-check 原則の強化版)
   認証・権限・ログイン・ウォレット接続・ロール分岐の記述を書く前に以下を必ず CLI で全確認:
   - フロント UI 実装 (`components/` / `hooks/`)
   - バックエンドエンドポイント (`routers/` / `services/`)
   - DB スキーマ (`users` / auth 関連カラム)
   1 つでも欠けていれば「**その機能は使えない**」と判断する。

3. **ドキュメント更新にも同じ Pre-check を適用** (カテゴリ判断禁止)
   「ドキュメント更新だから安全」という判断で Pre-check を省略しない。
   ユーザーに影響が出る変更は、コード変更と同じレベルの事前確認を適用。

4. **memory からの推論拡大禁止**
   memory「Privy App ID を全環境に設定」→「Privy 認証が動いている」という拡大解釈が事故の原因。
   memory は事実記録。実装状態は都度 CLI で確認する。

---

## 2026-04-24 開発フェーズ別チェックポイント

> 2026-04-24 インシデント対策: curl推測・Docker実態未確認・DBスキーマ差分見落とし・E2E未検証でのドキュメント公開の4パターンを防ぐ。

### Phase 1: 調査（コードを書く前に必ず実施）
- [ ] `docs/ops/01_api_endpoints.md` でエンドポイントパスを確認 — curl を推測で書かない
- [ ] `docs/ops/02_db_tables.md` でDBカラムを確認 — ALTER TABLE を推測で書かない
- [ ] Docker 環境確認: `docker ps | grep ultra-autotrade` でコンテナ名を実際に取得（`docs/ops/03_deploy_procedures.md` 参照）
- [ ] 認証・権限系は3層確認（フロント UI / バックエンドエンドポイント / DB カラム）→ 「2026-04-21 教訓」§再発防止ルール 2 参照

### Phase 2: 実装
- [ ] `./scripts/verify.sh` 全パス（ruff / mypy / pytest 80%+）→ 「Testing」セクション参照
- [ ] DBカラム追加時: モデルファイル冒頭に ALTER TABLE コメント記載（Alembic 未使用）
- [ ] 新規エンドポイント追加時: `docs/ops/01_api_endpoints.md` を更新

### Phase 3: デプロイ
- [ ] `docs/ops/03_deploy_procedures.md` の手順に従う（Hetzner で `deploy_production.sh`）
- [ ] DBカラム追加がある場合: Hetzner で先に ALTER TABLE を実行してからデプロイ
- [ ] `docs/22_production_release_checklist.md` §8（デプロイ手順）を確認

### Phase 4: 検証（デプロイ後）
- [ ] `curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool` で `scheduler_healthy: true` 確認
- [ ] `docker logs --tail=100 ultra-autotrade-backend-production 2>&1 | grep "401\|ERROR"` で 401 確認
- [ ] `docs/22_production_release_checklist.md` §9（ポストデプロイ確認）を参照

### Phase 5: ユーザー向けドキュメント・連絡
- [ ] 手順書を書く前に Playwright E2E で動作確認 → `docs/14_test_strategy.md` §10.X 参照
- [ ] E2E で通過した手順のみドキュメントに記載（未確認の手順は記載禁止）
- [ ] partner ロール画面の記述: フロント UI / バックエンドエンドポイント / DB カラムの3層確認 → 「2026-04-21 教訓」§再発防止ルール 1・2 参照

---

## 2026-05-02 テストデータ投入制限 — 本番DB cleanup インシデント GID 1214121103957100 再発防止

**テストデータの INSERT / UPDATE / DELETE は staging のみ。production DB への投入は禁止。**

### 対象コンテナ・DB
- **許可**: `ultra-autotrade-postgres-staging` コンテナ + DB `ultra_autotrade_staging`
- **禁止**: `ultra-autotrade-postgres-production` コンテナ + DB `ultra_autotrade`（本番）

### scripts/seed_test_data.sh 等の既存スクリプトルール
スクリプト先頭で必ず staging コンテナ名チェックを実施すること:

```bash
# スクリプト先頭に必ず追加
CONTAINER="${POSTGRES_CONTAINER:-ultra-autotrade-postgres-staging}"
if [[ "$CONTAINER" != *"staging"* ]]; then
  echo "ERROR: テストデータ投入は staging コンテナのみ許可。production への投入は禁止。"
  exit 1
fi
```

### production への INSERT / UPDATE / DELETE 適用: 3段プロンプト必須
production DB に対してデータ変更 SQL（INSERT / UPDATE / DELETE）を実行する場合、以下の3段確認を必ず経ること:

1. **プロンプト 1**: 「これは production DB への操作である」を明示して確認を取る
2. **プロンプト 2**: 「バックアップ取得済み」を確認（`pg_dump` 実行 + 出力確認）
3. **プロンプト 3**: 「実行してよいか」最終確認（明示的な YES 入力のみ続行）

自動スクリプト（Agent Teams / CI）から production DB へのデータ変更操作は **禁止**。手動確認のみ許可。

---

## 2026-05-09 Cloudflare Tunnel ingress 追従漏れ (staging 502) — RCA: docs/postmortems/2026-05-09_staging_api_502.md

**症状:** Blue/Green nginx 化（df0faf6, 2026-04-27）で staging backend を 8001 直接 bind から `nginx:127.0.0.1:8082` 経由に変更したが、Cloudflare Tunnel ingress（`api-staging.ultra-auto-trade.com`）が dashboard 上で `localhost:8001` のまま残り、約 12 日間 502 が放置された。production 側は 5/01 (a7008f5/PR #163) で同型バグが発覚済みだったが、staging への水平展開が漏れていた。検出は 5/9 09:42 JST、UAT pre-check 実行を試みた瞬間 (Cloudflare Ray ID `9f8caa253993e360`)。production 影響なし。

**鉄則 (絶対):**

1. **Cloudflare Dashboard 等 dashboard 系設定の変更は必ず「インフラ変更チェックリスト」を経由する。**
   `docs/16_infra_deployment_guide.md` (or 新規 `docs/<番号>_infra_change_checklist.md`) に定義する「インフラ変更チェックリスト」を経由しないかぎり Dashboard 直接変更は禁止。Dashboard 直接変更を恒常運用しない (Phase 3b PR-A で token → config.yml 移行と合わせて完了)。`docker-compose.production.yml` / `docker-compose.staging.yml` の `ports:` 行や nginx port を変更する PR は、PR description のテストプランに「インフラ変更チェックリスト実行済」を明記する。

2. **cloudflared は token 方式 (dashboard 管理) を避け、`config.yml` 方式に移行する。**
   `--token` 方式では ingress がリポジトリ外で管理されるため、git diff / コードレビューで port mismatch を検知できない (CLAUDE.md「cloudflared token 方式の既知制約」の延長)。Phase 3b PR-A で production / staging を独立 cloudflared + 独立 `config.yml` に分離する。

3. **deploy 後の外形 healthcheck を必須化する (Gate 8)。**
   `staging-deploy.yml` / `deploy_production.sh` 両方に `curl -fsS https://api{,-staging}.ultra-auto-trade.com/health` を deploy 直後に実行し、失敗したら Slack #ultra-auto-project に通知 + 自動ロールバック判断。内部 `127.0.0.1:8082/health` の確認だけでは「外形経路（cloudflared → nginx → backend）」は検証できない。

4. **production と同型のインフラインシデントが起きたら、PR description に「staging への水平展開状況」を必須記述する。** PR #163 (a7008f5) では production だけ後方互換 binding で塞いだが staging は塞がず放置 → 同じバグを 1 週間後に踏み直した。同型バグの再発防止には「他の環境にも同型リスクがないか」を PR テストプランに明示するルールが必要。

5. **インフラ変更前チェックリスト (`docs/16` 拡張 or 新規 docs) の必須項目:**
   - [ ] backend / frontend / nginx / cloudflared / postgres の port が変わるか
   - [ ] その port を参照する箇所 (cloudflared ingress, NEXT_PUBLIC_*, healthcheck script, docs, CLAUDE.md) が全て同期されているか
   - [ ] production / staging の両方で確認したか
   - [ ] 外形 `/health` が production と staging で 200 を返すか
   - [ ] Cloudflare Dashboard 設定変更が必要な場合、PR description に明記したか

6. **CF Access で保護した API サブドメインへのクロスオリジン fetch は必ず `credentials: 'include'` が必要。**
   CF Access はブラウザセッションで `CF_Authorization` Cookie を使う。SPA (staging.ultra-auto-trade.com)
   から CF Access 保護下の API (api-staging.ultra-auto-trade.com) に cross-origin fetch する場合、
   `credentials: 'include'` がないと Cookie が送信されず毎回 302 ループになる (2026-05-09 UAT pre-check で発覚)。

   **設計ルール:**
   - CF Access Application に API サブドメインを追加する場合、対応する SPA の fetch オプションも同時に変更する (PR に両方含める)
   - `frontend/lib/api/*.ts` の全 fetch 呼び出しには原則 `credentials: 'include'` を設定する
   - CF Access Service Token (`CF-Access-Client-Id` / `CF-Access-Client-Secret` ヘッダー) は CI/curl 向け。ブラウザ SPA では Cookie + `credentials: 'include'` が正しいアプローチ
   - staging で SPA + API を同一 CF Access Application に含める場合は、Cookie のクロスドメイン送信をブラウザで事前確認してから UAT に進む
   - 参照: `docs/postmortems/2026-05-09_staging_api_502.md` §CF Access SPA cross-origin Cookie 問題

**Dashboard 管理設定の事故パターン (3 回目):**

| 日付 | 事象 | 共通点 |
|---|---|---|
| 2026-04-02 | cloudflared token 方式移行時に ingress が Cloudflare Dashboard 管理に切替 | Dashboard 設定とコードが非連動 |
| 2026-04-03 | NEXT_PUBLIC_BACKEND_BASE_URL 古い trycloudflare URL 残存 → Mixed Content | URL 設定がコードと乖離 |
| 2026-05-01 | production cloudflared が `localhost:8000` のまま Blue/Green 切替 → 502 (PR #163) | nginx port 変更 vs Dashboard ingress 非連動 |
| 2026-05-09 | staging cloudflared が `localhost:8001` のまま Blue/Green 切替 → 502 (本件、12 日遅延) | 同上、PR #163 教訓の水平展開漏れ |

**確認コマンド (デプロイ直後):**

```bash
# production
curl -fsS -o /dev/null -w "%{http_code}\n" https://api.ultra-auto-trade.com/health

# staging (CF Access Service Token 必須)
curl -fsS -o /dev/null -w "%{http_code}\n" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  https://api-staging.ultra-auto-trade.com/health
```

200 以外なら即 Slack 通知 + Phase 1 (read-only) で原因切り分け。

**Gate 8 (新規) を本 CLAUDE.md `## Testing` セクションのテスト順序に追加**:
> テスト順序: pytest(自動) → tsc --noEmit(自動) → npm run build(自動) → Playwright E2E(自動) → 孤立コード検出(PR前) → Codex Review(PR前) → Claude in Chrome(UI変更時のみ) → **post-deploy-healthcheck (deploy後 自動) ★ Gate 8**

---

## 2026-05-12 nginx upstream IP 固着 → frontend-only deploy 直後 502

**症状:** 12:00 production で `./scripts/deploy_production.sh --frontend-only` 実行直後から、
Cloudflare 経由 `https://api.ultra-auto-trade.com/health` = 502。backend container 自体は健全
(`localhost:8010` 直撃 = 200)。15:23 `docker restart ultra-autotrade-nginx-production` で復旧
(3 時間 23 分継続)。同日 15:25 staging-new でも同型 502 を発見し、nginx error.log で
**古い IP (172.19.0.6) への "Host is unreachable" 生証拠**を取得 (backend 実 IP は 172.19.0.5)。

**真因:** `docker/nginx/nginx.conf` に **`resolver` ディレクティブ未設定**で、
upstream を `server backend-blue:8000` の hostname 直書きにしていた。nginx は起動時に
Docker embedded DNS (127.0.0.11) で 1 回だけ解決し、ワーカーメモリに永続キャッシュする。
backend container が recreate されて新 IP を取得すると、nginx は古い IP に proxy_pass し続け、
`docker restart nginx` 以外復旧手段なし。

**トリガー:** `deploy_production.sh --frontend-only` 経路が
`--no-deps --force-recreate` フラグなしで `docker compose up -d frontend` を実行。
compose の依存再評価で backend が recreate された (CLAUDE.md「本番フロントエンド操作ルール」違反)。

**鉄則 (絶対):**

1. **nginx の upstream に hostname を直書きする場合は必ず `resolver` を併設する。**
   `docker/nginx/nginx.conf` で `resolver 127.0.0.11 valid=5s ipv6=off;` を宣言し、
   `proxy_pass http://$backend;` の変数経由で動的解決させる。`upstream` block + hostname
   直書きは hostname を起動時 1 回しか解決しないため**禁止**。
   現行構成: `upstream.{production,staging}.conf` は `set $backend backend-blue:8000;`
   の単一行で、`nginx.conf` の `location /` で include される。

2. **`deploy_{production,staging}.sh --frontend-only` 経路は `--no-deps --force-recreate` 必須。**
   `docker compose up -d frontend` 単独実行は禁止。本ルール違反が今回のトリガーになった。

3. **post-deploy で外形 `/health` を必ず確認する (Gate 8 拡張)。**
   `--frontend-only` の場合でも、production は `https://api.ultra-auto-trade.com/health`
   (staging は `http://127.0.0.1:8082/health`) を 5 回連続 200 で確認し、失敗時は
   `nginx -s reload` を自動実行 + Slack 通知 (`#ultra-auto-project`)。
   `deploy_{production,staging}.sh` に組み込み済 (本セクションと対の修正)。

4. **nginx コンテナのログは Loki に取り込む** (要追加実装、別 Asana タスク)。
   現在 promtail は `/var/log/*log` のみ scrape し、nginx コンテナ内 `/dev/stderr` を
   docker logs 経由でしか保持していないため、`docker restart nginx` で過去ログが完全消失する。
   今回の本番側 RCA で error.log を取得できなかった構造的弱点。

**Dashboard 管理設定の事故パターン (4 回目、旧 CLAUDE.md 「Dashboard 管理設定の事故パターン」表に追加):**

| 日付 | 事象 | 共通点 |
|---|---|---|
| 2026-05-12 | nginx upstream IP 固着で frontend-only deploy 直後 502 | resolver 未設定 + `--no-deps` 不在の二重バグ |

**確認コマンド (deploy 直後・nginx 関連変更時):**

```bash
# nginx の resolver 設定確認 (1 以上必須)
docker exec ultra-autotrade-nginx-production nginx -T 2>&1 | grep -c "^[[:space:]]*resolver"
# upstream.conf が変数形式になっているか
docker exec ultra-autotrade-nginx-production cat /etc/nginx/conf.d/upstream.conf
# → "set $backend backend-blue:8000;" (新形式) or "server backend-blue:8000 ...;" (旧形式、要修正)
# 外形 /health 5 回連続
for i in 1 2 3 4 5; do
  curl -sf -o /dev/null -w "[%{http_code}] " https://api.ultra-auto-trade.com/health
  sleep 2
done; echo
```

5 回全て 200 でなければ即 Slack 通知 + Phase 1 (read-only) で原因切り分け。

**参照:** `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md`

---

## 2026-05-13 5/12 終日 UAT ブロッカー 教訓 20 策 — RCA: docs/postmortems/2026-05-12_uat_blocker_full_day_failure.md

### セクション 1: 朝プロトコル拡張 (策 1-2)

**策 1: production 業務動作サニティチェック（朝プロトコル冒頭に必須）**

`scheduler_healthy: true` の確認だけでは AI 判定が業務として動いているかを確認できない。
毎朝以下 SQL を実行して業務 KPI を確認すること:

```sql
-- AI 判定 24h 件数
SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';
-- 提案 24h 件数
SELECT COUNT(*), MAX(created_at) FROM proposals WHERE created_at > NOW() - INTERVAL '24 hours';
-- バックエンドエラー件数 (docker logs で確認)
-- docker logs --tail=200 ultra-autotrade-backend-production 2>&1 | grep -c "ERROR"
-- knowledge_sources スキーマ確認
SELECT COUNT(*) FROM knowledge_sources WHERE status = 'pending';
```

**策 2: Gate 8 標準 SQL — 業務動作 KPI を朝プロトコルに組み込む**

`/health` の `scheduler_healthy: true` + 上記 SQL 確認を合わせて「業務動作 Gate 8」とする。
Gate 8 が通らない場合は当日の AI 判定結果は信頼できないと判断し、原因調査を優先する。

### セクション 2: 判定癖修正 (策 3-5)

**策 3: エラー判定 3 軸ルール（即「既知/先送り」禁止）**

エラーを「既知」「先送り」と判断するには以下 3 軸を全て確認すること:
1. **影響範囲**: 山本さんの操作フローに影響が出ているか
2. **発生頻度**: 過去 24h で何件発生しているか (ゼロなら既知判断を慎重に)
3. **修正コスト**: 30 分以内に対応できるか

1 軸でも確認できていない状態で「既知/先送り」と判断することを禁止する。

**策 4: `scheduler_healthy=true` の意味の明文化**

`/health` レスポンスの `scheduler_healthy: true` は「スケジューラープロセスが生存している」
ことのみを示す。以下は**保証しない**:
- AI 判定が実際に実行されて BUY/SELL 提案が生成されていること
- 通知関数が呼ばれていること
- 業務ループが正常に完了していること

業務動作の確認には策 1 の SQL を使う。

**策 5: 影響度低判定チェックリスト（4 項目全 YES のみ「影響度低」と判定可）**

以下 4 項目が全て YES の場合のみ「影響度低」と判断可:
- [ ] 山本さんの操作フローに直接関係しないか
- [ ] 本番 API が正常に 200 を返しているか
- [ ] 24h エラーログが増加していないか
- [ ] 業務 KPI (提案/判定件数) が前日比で大きく下がっていないか

1 項目でも NO なら「影響度高」として即対応する。

### セクション 3: コマンド精度 (策 6-7)

**策 6: curl HTTP method を必ず明示する**

`curl -sI URL` は HEAD リクエストを送る。POST エンドポイントに `-sI` を使うと 405 が返り、
「エンドポイントが壊れている」と誤認する。

```bash
# 誤: HEAD リクエストになる → POST エンドポイントで 405
curl -sI https://api.ultra-auto-trade.com/health

# 正: GET で確認
curl -sf https://api.ultra-auto-trade.com/health
# 正: POST で確認
curl -sf -X POST -H 'Content-Type: application/json' \
  -d '{"key":"value"}' https://api.ultra-auto-trade.com/endpoint
```

**策 7: SSH heredoc 内の SQL に INTERVAL を使う場合は heredoc 必須**

```bash
# 誤: single quote 内で $() が展開されず意図しない SQL になる
ssh ultra@77.42.46.155 'psql -U ultra -d ultra_autotrade -c "SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '"'"'24 hours'"'"'"'

# 正: heredoc で SQL を渡す
ssh ultra@77.42.46.155 <<'ENDSSH'
psql -U ultra -d ultra_autotrade -c "SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours'"
ENDSSH
```

### セクション 4: テーブル・コード調査精度 (策 8-11)

**策 8: DB テーブル名から機能を推測しない**

- `ai_feedbacks` テーブル ≠ AI 判定本体（フィードバック履歴）
- `ai_decisions` テーブル = AI 判定実体（BUY/SELL/HOLD 決定）
- `proposals` テーブル = 承認待ち提案（ai_decisions の後段）

テーブル名だけで機能を推測せず、`docs/ops/02_db_tables.md` でスキーマを確認する。

**策 9: テストユーザー dry run 前に credentials アクセス事前 hash 確認**

テストユーザーでのログイン操作前に、対象ユーザーの password hash が DB に存在することを確認する:

```sql
SELECT id, email, hashed_password IS NOT NULL AS has_pwd, role
FROM users WHERE email = 'test@example.com';
```

hash が NULL のままテストするとログインが永遠に失敗し、「バグ」と誤認する。

**策 10: 朝起動時に ops_01/05 正本を通読**

毎朝作業開始前に以下を通読する:
- `docs/ops/01_api_endpoints.md` — 最新エンドポイント一覧
- `docs/ops/05_monitoring_runbook.md` (または最新 ops ドキュメント) — 監視・アラート手順

curl を書く前・ALTER TABLE を書く前に、まず ops ドキュメントを確認する習慣を徹底する。

**策 11: CLI 委譲ルール拡張（コード調査・grep も Claude Code に委譲）**

claude.ai セッションでコード調査・grep・ファイル探索が必要な場合、claude.ai が直接推測せず
Claude Code CLI に委譲する。claude.ai の「推測」が実装と乖離してインシデントを招く主要因。

委譲すべき操作:
- `grep -r "function_name" backend/` — 関数の参照箇所
- `cat backend/app/XXX/service.py` — 実装の確認
- `git log --oneline` — 最近の変更履歴

### セクション 5: production deploy + nginx (策 12-14)

**策 12: deploy 後は Cloudflare 経由 /health を Gate 5 として必須確認**

`deploy_production.sh` の内部 `127.0.0.1:8010/health` 確認だけでは不十分。
必ず Cloudflare 経由の外形 URL で確認する:

```bash
# 5 回連続 200 を確認 (Gate 8 外形確認)
for i in 1 2 3 4 5; do
  curl -sf -o /dev/null -w "[%{http_code}] " https://api.ultra-auto-trade.com/health
  sleep 2
done; echo
```

5 回全て 200 でなければ即 Slack 通知 + nginx reload を試みる。

**策 13: deploy script の「OK」出力を信用しない**

`deploy_production.sh` が「✅ deploy 完了」を出力しても、内部の healthcheck が
`127.0.0.1` ループバック経由のため、Cloudflare → nginx → backend の外形経路は
検証していない。策 12 の外形 curl を必ず追加実行する。

**策 14: nginx 502 が出たら frontend-only deploy とペアで疑う**

nginx 502 発生時の最初の確認:
1. 直近に `--frontend-only` deploy を実施したか
2. `docker ps` で backend container の `CREATED` 時刻が変わっているか (recreate の証拠)
3. `docker exec nginx nginx -T 2>&1 | grep resolver` で resolver 設定を確認

resolver 未設定かつ backend recreate 後なら、`docker restart nginx` で即時復旧できる。
恒久対策は `resolver 127.0.0.11 valid=5s;` 設定 + `proxy_pass http://$backend;` 変数化。

### セクション 6: 表示データ実体確認 (策 15-17)

**策 15: dummy/seed データの識別方法**

本番データとダミーデータを区別する 3 指標:
1. **時刻分散性**: 全レコードが同日同時刻 → seed データの可能性が高い
2. **ユーザー差異性**: 全レコードが同一ユーザー → seed データの可能性が高い
3. **24h 生成有無**: `WHERE created_at > NOW() - INTERVAL '24 hours'` で 0 件 → AI が動いていないか seed のみ

**策 16: production 表示データの実体は SQL で確認**

フロントエンドの表示値を見て「データが入っている」と判断しない。
フロントエンドはキャッシュや seed データを表示することがある。
必ず production DB に直接 SQL で確認する:

```bash
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c \
  "SELECT COUNT(*), MAX(created_at) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';"
```

**策 17: 孤立コード再発防止 — CI 週次 detect_orphan_functions.sh**

孤立コードは「大きなリファクタ時」だけでなく並列開発後も発生する。
以下を実施する:
- 毎週月曜の CI で `scripts/detect_orphan_functions.sh`（または同等の grep スクリプト）を自動実行
- `backend/app/notifications/service.py` の全 public 関数を特に重点チェック
- 孤立が検出された場合は P1 として当日中に配線修正または削除

### セクション 7: PR と実機の乖離 (策 18-20)

**策 18: wallet flow / 認証 flow / DB 書き込み伴う action は viem 実署名 E2E 必須**

component 単独 commit + route-mock テストでは「実際に signature が生成され、backend に
送られ、DB に書き込まれる」フローを検証できない。

以下のフローは必ず viem 実署名 E2E テストを追加すること:
- `POST /auth/wallet/link` — nonce 取得 → viem signMessage → POST の 3 ステップ
- `POST /auth/login` — email/password → JWT 取得 → ダッシュボードへのリダイレクト
- `POST /aave/rebalance` — health factor 確認 → deposit/withdraw

**策 19: Codex APPROVED + Playwright pass でも実機 (実ブラウザ) 確認は必須**

Playwright の動作環境 (ヘッドレス Chrome、拡張なし、自動 Content-Type 付与) と
実ユーザーの動作環境 (拡張入り Chrome、手動操作、browser の fetch 挙動) は異なる。

特に以下は実機確認を必須とする:
- `fetch()` の `Content-Type` / `body` が正しく設定されているか
- wallet 拡張 (MetaMask 等) の popup が正しく発火するか
- CF Access の Cookie が正しく送られているか (`credentials: 'include'` の有無)

**策 20: frontend container restart は image rebuild ではない**

```bash
# 誤: イメージが古いまま旧コードが起動する
docker compose up -d --force-recreate frontend

# 正: 必ず build してから recreate する
docker compose -f docker-compose.production.yml --env-file .env.production \
  build --no-cache frontend

# ビルド完了の確認: image hash が変化したか確認
docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep frontend

# その後 recreate
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate frontend
```

`--force-recreate` はコンテナの再生成のみ。イメージの再ビルドは `build --no-cache` が必要。
image hash が変化していなければ rebuild されていないため、旧コードが動き続ける。

**参照**: `docs/postmortems/2026-05-12_uat_blocker_full_day_failure.md`

---

## 2026-05-15 Phase A PoC staging endpoint 未実装パターン教訓

### 教訓-2026-05-15: PoC 段階の schemas-only 定義と staging 実機検証の関係

**事象**: Lane A-4 (AI Optimizer staging E2E) で、`OptimizerRequest` / `OptimizerResponse` が
`app/ai/optimizer/schemas.py` に定義されているにも関わらず、対応する router が存在せず
`/api/optimizer/recommend` エンドポイントが staging に存在しない状態でタスクが完了指定されそうになった。
また `app/protocols/risk/router.py` の `/api/protocols/health` は main.py に登録済みだが、
`DummyClient` を使用しているため staging で `500: DummyClient cannot be used in staging environment` が返る。

**真因**: Phase 2 PoC では「schemas 先行定義 → router は実装フェーズで追加」という開発順序を取る。
CLAUDE.md の「Phase 4: staging 実機検証」フローに「PoC 段階でエンドポイントが未実装の場合の代替」が明記されていなかった。

**再発防止ルール**:

1. **staging 実機検証の前にエンドポイント存在確認を必須化**
   ```bash
   # curl の前に必ずエンドポイント存在を確認
   ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
     "curl -sf http://localhost:8082/openapi.json | python3 -c \"import sys,json; paths=json.load(sys.stdin)['paths']; print('\\n'.join(paths.keys()))\"" \
     | grep -E "optimizer|recommend"
   # 0件なら → PoC仕様 → pytest E2E で代替、その旨を DoD に明記
   ```

2. **PoC 段階の schemas-only 定義は「孤立コード検出」対象**
   router が存在しない `OptimizerRequest` / `OptimizerResponse` は P1 孤立として記録する。
   Lane 完了時の孤立コード検出でこれらを捕捉し、`[P1: router 実装待ち]` とラベリングして別タスク化する。

3. **DummyClient を使うプロトコルの staging 実機検証は skip 明示**
   `DummyClient` / `DummyLidoClient` / `DummyPendleClient` を使用するエンドポイントは
   staging で必ず 500 になる。pytest mock E2E で代替し、
   DoD に `Gate 4: staging スキップ (DummyClient - PoC仕様)` と明記すること。

4. **孤立クラスの P0/P1 分類基準**
   | 分類 | 対象 | 対応期限 |
   |---|---|---|
   | P0 | 安全装置・緊急停止・避難系 (AutoEvacuator, CompoundRiskAssessor 等) | 当日中 |
   | P1 | API スキーマ・router 待ち定義 (OptimizerRequest 等) | 次スプリント |
   | P2 | ユーティリティ・将来機能 | バックログ |

---

## 2026-05-17 P0: postgres 2,448回クラッシュ + バックアップ全滅 RCA

**事象概要:**
- 2026-05-15 08:18 〜 2026-05-17 11:55 (約2日間) postgres-production が SIGKILL (exit 137) で
  2,448回 restart loop。AI判定スケジューラが 5/16 08:25 以降 18.2h 停止
- 同期間に backup_db.sh が空 gzip (20バイト) を量産。5/14 18:00 以降の有効バックアップなし
- Slack Watchdog は 5/16 09:08 から 3分おきに警告を出し続けていたが、対応が打たれず
- 原因は Loki Docker logging driver の半死状態 (TCP受付するが処理しない)
- 全コンテナの logging.driver: loki が SPOF として機能した

**Logging driver は SPOF になりうる:**
- docker-compose で logging.driver を network 依存型 (loki/fluentd/syslog) に設定すると、
  ログ収集系の故障が全コンテナを巻き込む
- 本番DB等の stateful service は json-file driver を使い、
  ログ集約は pull 型 (promtail tail /var/lib/docker/containers/) で行う
- 教訓: 2026-05-15 08:18 Loki 半死 → postgres 2,448回 SIGKILL (10秒寿命) で 18.2h AI判定停止。
  Loki が応答しないが TCP は受け付ける半死状態が最悪

**HTTP 200 ≠ 健全:**
- /health 200 OK だが scheduler_healthy: false / scheduler_last_error あり / warnings あり の
  ケースを見落とした
- response body 全フィールド (scheduler_healthy, last_judgment, warnings, scheduler_last_error)
  を監視対象にする

**ログ件数 0 は致命的シグナル:**
- 2,448回 restart で1行もログが出ないのは normal ではない
- RestartCount > 10 + ログ件数 0 → 別系統 (容器外、systemd/dmesg/journalctl) で alert

**バックアップは「取れている」を証明する仕組み:**
- backup スクリプトの exit code だけでは不十分
- サイズチェック (>1KB) + 週次復元テスト + 失敗時 Slack 通知の三点セット
- backup_db.sh の動的コンテナ名解決 (ハードコード禁止)。例:
  `docker ps --filter "name=postgres-production" --filter "status=running" --format "{{.Names}}" | head -1`

**警告疲労 (Alert fatigue) は対応者不在と同じ:**
- 3分おきに警告が来ても誰も見ないなら、警告は単なるノイズ
- エスカレーション (5回連続で別チャネル / 10回連続で電話) 必須
- 1人プロジェクトは Twilio API 等で電話通知

**「動いていることになっている」を疑う:**
- Loki / backup / Watchdog / Slack / Docker healthcheck の5つが
  「動いている建前」で実際は機能していなかった
- 月1回 Chaos test (staging で Loki/postgres/backend を意図的に殺す)
- 「Status 200」「Up XX hours」は健全の証明ではない

**claude.ai は正本確認を忘れる前提で仕組み化:**
- 鉄則8 (CLI cat 必須) を明文化しても、急ぐ場面で必ず飛ばす
- 朝プロトコル §9 冒頭で /mnt/project/ docs を CLI cat して claude.ai セッションに
  貼り付けてから初めて作業開始 (貼られていない場合 §9 進行禁止)
- 2026-05-17 セッションで claude.ai が 3回連続で鉄則8違反、本指示文 v4 §9 に Step 0 強制化を追記

**復旧時の正本docsスキーマ実態 (推測禁止、CLI \\d で確定):**
- users: execution_policy (require_approval ではない), tier (tier_id ではない), wallet_address
- proposals: operation (action ではない), status, expires_at, error_message
- transactions: tx_hash, is_dry_run, status
- portfolio_snapshots: recorded_at (snapshot_at ではない), total_value_usd, health_factor
- ai_decisions: created_at, final_action, final_confidence

**Docker compose ps の空応答 ≠ サービス未定義:**
- `docker compose ps postgres` が空応答 → 「postgres compose 内未定義」と推測した claude.ai 違反
- 実際は project 名不一致または status=running なしのいずれか
- production_operation_checklist.md ゲート2 (`docker compose ls / docker ps / docker inspect`) を
  必ず先に流して、推測ではなく実態確認する

**Tier S 操作の sed -i 禁止 (compose YAML編集も含む):**
- 31_backup_restore_procedures.md L139-146 の awk + 一時ファイル + mv パターン厳守
- inode 保持 (bind-mount 対応) と memory 由来の運用ルール

**参考ドキュメント:**
- docs/postmortems/2026-05-17_loki_postgres_cascade.md (Lane B-4 で作成)
- docs/postmortems/2026-05-17_backup_silent_failure.md (Lane S-2 で作成)
- CLAUDE.md 並列開発フロー v4.1 鉄則8 (CLI cat 必須)
- 本指示文 v4 §9 朝プロトコル Step 0 強制化 (Lane B-6 で追記)

---

## 2026-05-17 docker compose restart ≠ recreate (Lane S-1 実機証明)

**docker compose restart ≠ recreate (2026-05-17 実機証明):**
- `docker compose restart <service>` は既存コンテナの停止+起動のみ。compose.yml の HostConfig（logging driver・network・port・env_file 等）変更は**適用されない**
- `docker compose up -d --force-recreate --no-deps <service>` を使うとコンテナが新規作成され HostConfig も付け替わる
- compose.yml 変更後は必ず `up -d --force-recreate --no-deps` を使う。`restart` だけで「適用したつもり」のミスは production_operation_checklist.md ゲート2 に明記済み
- 検証方法: `docker inspect <container> --format '{{.Created}}'` でコンテナ作成時刻を確認、compose.yml 変更時刻より新しいことを確認

**経緯**: Lane S-1 (2026-05-17) で logging driver を loki → json-file に変更した compose.yml を `docker compose restart` したところ、古い loki driver のままだった。`up -d --force-recreate --no-deps` で初めて適用された。関連 PR: #243 (Lane B-5 教訓-2026-05-17)

### docker compose 変更後 推奨コマンドテンプレ

| 変更内容 | 推奨コマンド | NG（compose変更が未適用になる）|
|---|---|---|
| logging driver 変更 | `docker compose up -d --force-recreate --no-deps <svc>` | `docker compose restart <svc>` |
| network 変更 | `docker compose up -d --force-recreate --no-deps <svc>` | `docker compose restart <svc>` |
| port 変更 | `docker compose up -d --force-recreate --no-deps <svc>` | `docker compose restart <svc>` |
| env_file 変更 | `docker compose up -d --force-recreate --no-deps <svc>` | `docker compose restart <svc>` |
| image 変更 | `docker compose pull <svc> && docker compose up -d --no-deps <svc>` | `docker compose restart <svc>` |
| コード変更のみ（HostConfig変更なし）| `docker compose restart <svc>` 可 | N/A |

```bash
# compose.yml 変更後の標準手順
docker compose up -d --force-recreate --no-deps <service>

# 適用確認: コンテナ作成時刻が compose.yml の変更時刻より新しいことを確認
docker inspect <container> --format '{{.Created}}'

# logging driver 適用確認
docker inspect <container> --format '{{.HostConfig.LogConfig.Type}}'
```

---

## 2026-05-19 24h 自走起動準備の教訓

> 24h 自走起動の準備フェーズで Bypass Permissions が不発し承認要求で実質停止、
> 設定修正のため session 再起動した経緯から確立。起動前チェックリストは
> `docs/ops/uata_24h_autonomous_startup_checklist.md`（8 項目）を参照。

### 1. Bypass Permissions の正しい有効化手順

- `.claude/settings.json` の **`permissions.defaultMode = "bypassPermissions"`** に
  ネストする。**root 直下に `defaultMode` を書いても効かない**。
- 公式 doc 推奨の確実な方法は CLI フラグ **`claude --dangerously-skip-permissions`**。
- `defaultMode` が settings.json から反映されない bug が GitHub issue
  **#29026 / #34923 / #12604** で継続報告中。settings.json 方式が不発のときは
  CLI フラグにフォールバックする。
- 公式 valid values: `default` / `acceptEdits` / `plan` / `dontAsk` / `bypassPermissions`。
- Bypass Permissions の警告画面で Yes は**新規セッション起動扱い**。進行中の
  session は `/resume` で復帰可能だが、**auto-memory に書かれていない進捗は失われる**。
  重要な setup 変更は session 起動前に完了させること。

### 2. dev VPS と Mac の secrets 分離原則

- Slack webhook / Pushover env / `scripts/uata-pushover-notify.sh` は
  **Mac 側のみに存在することが多い**。dev VPS で使うには以下 4 手順:
  1. `scp` で dev VPS の `~/.claude-uata/secrets/` 配下へ配置
  2. `chmod 600` で権限を絞る
  3. `~/.bashrc` に `source` 行を追加（起動時自動 load）
  4. 動作確認（`gh auth status` / webhook curl / `uata-pushover-notify.sh test`）
- **既存設定を前提にしない**。毎回 dev VPS 上で `grep` 確認してから使う。
- 標準配置: `~/.claude-uata/secrets/{github.env,slack.env,pushover.env}`（mode 600）。

### 3. 24h 自走起動前チェックリスト（8 項目 / 詳細は docs/ops）

1. Bypass Permissions が settings.json に正しくネスト or CLI フラグ起動
2. GitHub PAT（`github.env`, scope `repo`/`workflow`）が env load 済
3. Slack webhook（`slack.env`）配置・到達可能
4. Pushover（`pushover.env` + `uata-pushover-notify.sh`）配置・`test` 送信 OK
5. stuck-detector 起動済（`ps` で PID 確認 + `touch /tmp/uata-heartbeat` でリセット）
6. 正本確認（鉄則8）完了・結果をセッションに貼付
7. 安全境界をセッション冒頭に明示（本番 deploy 禁止 / HUMAN-REVIEW-REQUIRED 範囲 / 並列 2 本上限）
8. Phase 分解・DoD・auto-memory 逐次記録方針が確定

### 4. Claude Code session 再起動時のリスク

- Bypass Permissions 警告画面の Yes は**新規セッション起動扱い**になる。
- 進行中の session は `/resume` で復帰可能。ただし **auto-memory（MEMORY.md）に
  書かれていない進捗は失われる**。
- 重要な setup 変更（settings.json / secrets / hooks）は **session 起動前に
  完了**させ、起動後に再起動を要する変更を残さない。

---

## 2026-05-19 Next.js bundle 反映確認の盲点 — Asana GID 1214828247132605

**`static/chunks/` のみの grep では Next.js の SSR 出力を見逃す。**

2026-05-15 Pane 4 調査で発見:
- `grep -l 'LOWER' /app/.next/static/chunks/*.js` が 0 件 → 「frontend 未反映」と誤判定
- 実際は Next.js が SSR ページファイル (`/app/.next/server/`) にも出力していた

**正しい確認コマンド（`/app/.next/` 全体を再帰検索）**:
```bash
docker exec ultra-autotrade-frontend-production sh -c \
  "grep -rn '<検索文字列>' /app/.next/ 2>/dev/null | head -10"
```

**禁止**: `static/chunks/` のみ、`/app/.next/static/` のみの限定検索。
**理由**: この誤判定を信じていたら、山本さんへ「ダウンタイムアリ」の誤 DM を送り、F-16 を不要にフルビルドで実行していた。

---

## 2026-05-19 AI v4 prompt KeyError: 'agent_signals' — 本番 14 分停止 RCA

**service.py の `_build_prompt_content()` で v3 のみ `agent_signals` を渡す条件分岐が v4 を考慮していなかった。**

発生: 2026-05-19 16:28-16:42 JST に本番で `AI_PROMPT_VERSION=v4` を試用。
`_V4_USER_TEMPLATE` は `{agent_signals}` を含むが `else` ブランチ（v1/v2 向け）で処理されるため KeyError 発生。
14 分のスケジューラー停止 → v3 ロールバック。PR #302 で修正済み（`version in ("v3", "v4")`）。

**新しい prompt version を追加する際は `_build_prompt_content()` の条件分岐を必ず確認する。**
`{agent_signals}` を template に含む version は `if version in (...)` に必ず追加すること。

---

## 2026-05-20 朝プロトコル違反パターン (v2 提案書 §B より統合)

> 2026-05-20 night-mode で claude.ai が docker コマンドを 25 往復中継し、過去ルール違反を 6 回犯した経緯から確立。
> 詳細: `docs/internal/claude_md_split_proposal.md` v2 §B。

| # | 違反パターン | 正しい行動 |
|---|---|---|
| P1 | docker コマンドを 2 行以上中継する | 2 行目で停止 → Lane に 1 ブロック依頼 |
| P2 | コンテナ名を断定して SQL 発行 | `docker ps` で実名確認後に発行 |
| P3 | staging 消滅アラートで即復旧コマンドを出す | 先に Lane に診断依頼 |
| P4 | v4 / schema 変更後の SQL を docs 未確認で発行 | `docs/ops/02_db_tables.md` を先読み |
| P5 | `docker restart` で env 変更が反映されると思い込む | 「2026-05-17 docker compose restart ≠ recreate」を参照 |

**Lane 1 ブロック包括依頼テンプレ** は `CLAUDE.md` core §9 朝プロトコル直後に常駐化済。
本 P1-P5 違反パターンは「`CLAUDE.md` 朝プロトコル §9 Step 0 でこの lessons ファイル全体を SessionStart Hook 経由で auto-Read」される運用で防止する。

---

## 2026-05-26 staging soak 全 HOLD 三重故障 + 運用教訓

### 真因は「症状」の3層下にあった — 実機確認を最初に
staging soak 48h 全 HOLD の真因追跡で、仮説が3回更新された:
「AI の HOLD bias(confidence 閾値)」→「Guard 2 の AND-condition clamp」→「Aave feed 未設定」
→ 実真因「.env の Aave アドレスが Ethereum Sepolia 誤値 + RPC が死んだ Alchemy URL +
client.py の is_connected() false positive」の三重故障。
教訓: コードを読む前に、まず実機の .env / DB / ログを見る。dev VPS から本番 VPS の
staging が見えない時は、人間に SELECT を依頼してでも実データを先に取る。
推測の真因をコードで補強すると、もっともらしい誤答に到達する。

### .env は「未設定」と推測せず grep で実値を見る
「キーが未設定だから動かない」と推測したが、実際は誤値で既存だった
(AAVE_POOL_ADDRESS に Ethereum Sepolia 0x6Ae4... が入っていた)。
.env を扱う前に必ず grep -nE で実値・行番号を確認。awk 末尾追記の前に既存キー重複チェック必須。

### Web3.is_connected() は public RPC で信頼するな
web3.py の is_connected() は内部で web3_clientVersion を呼ぶ。Base 等の public RPC は
これに非対応で false を返すが、eth.block_number / eth.chain_id / eth_call は正常動作する。
RPC 疎通判定は is_connected() ではなく eth.chain_id か block_number で行う。

### 秘密鍵をターミナル出力・チャットに出さない
openssl rand の結果や .env の grep で秘密鍵が平文露出した。
鍵生成は openssl rand -hex 32 | pbcopy(画面に出さずクリップボードへ)。
.env の秘密値を確認する時は grep -c(件数)で済ませ、値を表示しない。
一度露出した鍵は testnet でも rotate する。

### Agent View はディレクトリ単位で別管理
/home/uata から claude agents を開くと空ビューが出て、別ディレクトリで起動した
agent を見失う。agent の確認は起動した worktree ディレクトリ(/opt/ultra-autotrade-worktrees/<branch>)
から claude agents すること。

### docker compose は staging で --env-file 必須
docker compose ps / build / up すべてで --env-file .env.staging-new を付ける。
省略すると COMPOSE_PROJECT_NAME が解決されず空応答 → 「コンテナ消失」と誤判定する。

### 自動 deploy と手動操作の衝突に注意
.deploy-staging.lock があったら rm する前に ps aux | grep deploy_staging で
生きているプロセスを確認。10:45 起動の自動 staging deploy(git reset --hard +
deploy_staging.sh)が稼働中だった。ps の ELAPSED は MM:SS 表記、誤読しない。

---

## 2026-05-31 custodial 実装が5ゲート全漏れ — テストが実装と同じ前提を持つと欠陥を追認する

**真因**: Aave 実行が最初から custodial 設計（サーバー共通鍵署名・サーバー wallet 資産・`onBehalfOf=サーバー`）。`client.py` 初出 commit `b1274b4`（5/27）時点で `AaveClient Protocol` が `deposit(asset, amount)` の 2 引数。`user.wallet_address` は監査ログのみで on-chain 未伝達。規約 ver03 / §17-5 / §20 の non-custodial と矛盾。`shadow=true` だったため実 tx が出ず顕在化せず、6/1 実 tx 解禁直前（5/31）にコード追跡で発覚。

**なぜ5ゲート全漏れか（全て「成功可否」は見たが「誰の資産が動いたか」を見ていない）**:
- **Gate A/B pytest**: `FakeAaveClient` も2引数で実装と同形。`supply` の `onBehalfOf` を assert せず回数だけ検証 → mock が欠陥を正常として追認
- **Gate C E2E**: `AaveService` を bypass しサーバー鍵で直接 `Web3AaveClient` を呼び完走 → 実コードパス未通過
- **Gate D/E dry run/UAT DoD**: basescan で `status=Success` のみ。`from` / `onBehalfOf` 未確認

**構造的教訓**:
- テストダブルが実装と同じ前提を持つと欠陥を検出でなく追認する。5/10 の `page.route` mock（mock pass → 実環境 fail）と同型の反復。
- money が動く操作は tx 成功でなく「誰の・どのアドレスの資産が・誰の署名で動いたか」を検証しなければ完走と呼べない。

**再発防止（§7 / §14 / checklist に反映）**:
1. §14 完走条件4: tx の `from=partner AND onBehalfOf=partner` を必須確認
2. §7 Gate1: Fake は `wallet_address` を記録・assert。`onBehalfOf` 引数を中身まで assert
3. §7 Gate4: `AaveService` を bypass しない。on-chain `from` / `onBehalfOf` を assert、mock 不可
4. 横断: money 操作は「誰の資産が・誰の署名で」を検証する原則を明文化

**対応**: Asana 1215263804492320（方式2 non-custodial 改修）で実装中。6/1 `shadow=false` 切替は本改修 + staging `from`/`onBehalfOf=partner` 実証まで凍結。

---

## 2026-06-04 V3一般公開日 — alembic stamp 早期発行・一括 merge・banner DevTools 省略の三教訓

### 本日の完了事項
- **本番 non-custodial 証跡 #1**: 山本さん supply tx `0x5dfd…928d`（Base Mainnet、USDC $10、DoD 1-4 PASS）。`from=partner wallet`・`onBehalfOf=partner wallet`・サーバー鍵非出現を on-chain で確認。
- **V3 一般公開**: LIFF degrade（#539）+ SessionExpiryBanner 根治（#542）。Safari プライベートでクリーン実証。main HEAD = `bf91204`、本日 merge = #530–#542。
- **本番状態**: active=blue、`alembic_version=s9t0u1v2w3x4`（stamp 適用済）。

### 教訓1: 一括「全 OPEN PR merge」は競合実装を流し込む

**何が起きたか**: 複数 PR を一括 merge した際、`app/legal`（孤立・0件）と `app/tos`（正本・配線済み）の二重定義が main 入りし、`tos_consents` が二重 CREATE になった。CI の Lint 失敗で Test job が skip → schema 衝突が merge ゲートを通過。

**再発防止**: PR は 1 本ずつ merge し、Lint PASS → Test PASS → merge の順を守る。required checks 化で物理的に強制（Asana 1215428893181908）。一括 merge は禁止。

### 教訓2: narrow evidence で alembic stamp head するな（§Alembic 教訓）

**何が起きたか**: `tos_consents` テーブルの存在だけを確認して `alembic_version` を `s9t0u1v2w3x4`（head）に stamp した。しかし `proposals.execution_route` / `ai_decision_outcomes.asset,protocol` の列は未適用のまま。stamp が「適用済み」の嘘を作り、deploy 毎に L0 で gap が露出（本日3回）。

**正しい手順**: stamp 前に「migration ファイルの全 DDL ↔ 実 DB のカラム/制約/インデックス」を列単位で完全突合。テーブル存在 ≠ migration 適用。`pg_constraint` / `pg_indexes` まで確認してから stamp。

**再発防止**: `deploy_production.sh` が `alembic upgrade head` を確実に実行するよう修正（Asana 1215423076968809・最優先）。stamp は実 schema = revision 定義の完全一致確認後のみ。

### 教訓3: UX 不具合はコードを読む前に DevTools/実データから

**何が起きたか**: SessionExpiryBanner 誤表示の修正を複数回外した（#541 で 3 箇所修正したが `lib/session/itp-guard.ts` の直接 `setItem` が残存）。コードを推測で読んで修正したため根本の write 経路を見落とした。

**正しい手順**: `localStorage.getItem('ultra_last_seen')` の実値・書き込みタイミングを DevTools で確認 → 書き込み経路を全列挙 → 条件ガードを入口に置く。#542 で「`!hasActiveToken()` → no-op」の不変条件強制で根治。

### 教訓4: 本番 deploy 後の確認は PWA SW キャッシュを避けた新規ブラウザで

**何が起きたか**: Chrome incognito で deploy 後も修正が反映されて見えなかった（PWA service worker が旧 JS を返していた）。Safari プライベートブラウズ（SW キャッシュなし）で即消滅を確認。

**再発防止**: deploy 後の動作確認は Safari プライベートまたは SW unregister 済みブラウザで実施。Chrome incognito は SW キャッシュを持つ場合がある。

---

## 2026-06-05 staging E2E 実機検証 — verify_browser_partner_approval の環境知見

### 教訓1: Alchemy RPC は staging コンテナ外 (VPS ホスト) から呼ぶ

**何が起きたか**: `verify_browser_partner_approval.py` を backend コンテナ内から実行しようとすると `ALCHEMY_RPC_URL_BASE_SEPOLIA` が 403 を返した (おそらく origin / IP 制限)。VPS ホスト上 (コンテナ外) からは通る。

**再発防止**: staging E2E スクリプトは backend コンテナ内ではなく VPS ホスト上の `backend/.venv/bin/python3` で実行する。代替 RPC `https://sepolia.base.org` でも代替可能。

### 教訓2: staging API_BASE はホストから 127.0.0.1:8082、コンテナ内からは nginx 内部 IP

**何が起きたか**: `API_BASE=http://127.0.0.1:8082` はコンテナ内では届かない。ホスト上からは nginx の外部ポート 8082 が正しい。コンテナ内から呼ぶ場合は `docker inspect` で nginx 内部 IP (例: 172.19.0.7:8080) を使う。

**再発防止**: E2E スクリプトの `API_BASE` は実行場所 (ホスト/コンテナ) に合わせる。VPS ホスト上実行が最もシンプル。

### 教訓3: staging の test wallet key は /tmp/ に生成され再起動・cleanup で消える

**何が起きたか**: 前回 E2E 実行時に `/tmp/.lifecycle_partner_key_*` が `trap cleanup EXIT` で削除され、users 25/26 の wallet_address に対応する秘密鍵が VPS 上から消滅した。新規 E2E 実行時に wallet_address を新規 test wallet に更新して対処。

**再発防止**: staging の test users (25/26 等) は wallet_address を「その都度新規 wallet に更新」する設計とする。永続的な key 保存が必要な場合は `/opt/ultra-autotrade/.test_keys/` 等に mode 600 で保管する。

### 教訓4: staging サーバー ETH は faucet 補充要 (0.001 ETH 台まで消耗)

**何が起きたか**: fund_partner_test_wallet.py (ETH_TO_SEND=0.02 ETH) を 2 回実行したことで AAVE_WALLET の Base Sepolia ETH が ~0.001 ETH まで減少した。

**再発防止**: E2E 実行前に `AAVE_WALLET_ADDRESS` の Base Sepolia ETH 残高を確認する。0.05 ETH 未満なら faucet (https://www.alchemy.com/faucets/base-sepolia) で補充。
