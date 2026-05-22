# frontend build の Cloudflare Pages 切り出し — 移行設計書

> **ステータス**: 設計のみ。実装・設定ファイル変更・本番カットオーバーは別判断。
> **作成日**: 2026-05-22
> **Asana**: 1215028729815897
> **担当**: Lane (Claude Code)

---

## 1. 背景・目的

### 直近インシデント

2026-05-22、staging deploy 中に frontend の Docker build (`NODE_OPTIONS=--max-old-space-size=4096`) が
`docker buildx` と同時並走したことで **OOM が発生し staging stack が消滅**した。
同様のリスクは production にも常在する。

### 根本構造問題

| 問題 | 詳細 |
|---|---|
| VPS スペック | Hetzner 7.6GB RAM / swap なし / production + staging 同居 |
| frontend build ピーク | Next.js build は `--max-old-space-size=4096` でも 4GB+ に達する可能性あり |
| backend build との競合 | `docker buildx` と frontend build の同時起動でピーク重複 → OOM |
| 構造的除去の必要性 | `mem_limit` 調整・build 分離等の対症療法ではリスクが残る |

### 目的

**frontend build を VPS から Cloudflare Pages (CF Pages) へ切り出すことで、VPS の
build 起因 OOM リスクを構造的に除去する。**

副次効果として、CDN エッジ配信による応答速度向上も期待できる。

---

## 2. 現状 build / 配信経路

### 2.1 アーキテクチャ図（現状）

```
[開発者 push to main]
        │
        ▼
  [VPS: docker compose build frontend]
  ・context: ./frontend
  ・Dockerfile: Stage1(deps) → Stage2(builder) → Stage3(runner)
  ・NODE_OPTIONS=--max-old-space-size=4096   ← OOM 起因
  ・output: standalone (.next/standalone/)
        │
        ▼
  [Docker コンテナ: ultra-autotrade-frontend-*]
  ・staging:    127.0.0.1:3001 → container:3000
  ・production: 0.0.0.0:3000   → container:3000
  ・runtime: node server.js (Next.js standalone サーバー)
  ・SSR/CSR 両対応
        │
        ▼
  [cloudflared (network_mode: host)]
  ・Named Tunnel token 方式
  ・ingress: app.ultra-auto-trade.com → localhost:3000
  ・ingress: api.ultra-auto-trade.com → localhost:8080 (nginx → backend blue/green)
        │
        ▼
  Cloudflare Edge → ユーザーブラウザ
```

### 2.2 現状 build の詳細

| 項目 | 値 |
|---|---|
| ベースイメージ | `node:20-alpine` |
| build コマンド | `npm run build` |
| Next.js output | `standalone` (`.next/standalone/` + `.next/static/`) |
| メモリ上限設定 | `NODE_BUILD_MAX_OLD_SPACE_SIZE=4096` (ARG / ENV) |
| staging ポート | `127.0.0.1:3001:3000` |
| production ポート | `3000:3000` (外部公開) |
| SSR backend 接続 | `BACKEND_BASE_URL=http://nginx:8080` (Docker 内部 DNS) |
| PWA | `next-pwa@5.6.0` / `sw.js`, `workbox-*.js` を `public/` に生成 |
| i18n | `next-intl@3.26.5` |
| LIFF | `@line/liff@2.28.0` (LINE ミニアプリ) |
| Wallet | `@privy-io/react-auth@3.21.0`, WalletConnect |

### 2.3 現状の環境変数 (build-time, NEXT_PUBLIC_*)

以下はすべて **Dockerfile ARG → ENV → JS バンドルに焼き込まれる** build-time 変数:

| 変数名 | staging デフォルト | production デフォルト |
|---|---|---|
| `NEXT_PUBLIC_BACKEND_BASE_URL` | `https://api-staging.ultra-auto-trade.com` | `https://api.ultra-auto-trade.com` |
| `NEXT_PUBLIC_API_BASE_URL` | 同上 | 同上 |
| `NEXT_PUBLIC_API_URL` | 同上 | 同上 |
| `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID` | (空) | (空) |
| `NEXT_PUBLIC_DEFAULT_CHAIN` | (空) | `base` |
| `NEXT_PUBLIC_DEFAULT_CHAIN_ID` | `84532` (Base Sepolia) | `8453` (Base Mainnet) |
| `NEXT_PUBLIC_MAINNET_RPC` | (空) | (空) |
| `NEXT_PUBLIC_ARBITRUM_ONE_RPC` | (空) | (空) |
| `NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC` | (空) | (空) |
| `NEXT_PUBLIC_BASE_RPC` | (空) | (空) |
| `NEXT_PUBLIC_BASE_SEPOLIA_RPC` | (空) | (空) |
| `NEXT_PUBLIC_OPTIMISM_RPC` | (空) | (空) |
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | (空) | (空) |
| `NEXT_PUBLIC_LIFF_ID` | (空) | (空) |
| `NEXT_PUBLIC_PRIVY_APP_ID` | (空) | (空) |

runtime-only (SSR サーバー側のみ、バンドル非埋込):

| 変数名 | 用途 |
|---|---|
| `BACKEND_BASE_URL` | SSR → nginx (Docker 内部) 経由で backend API 到達 |

---

## 3. CF Pages 構成案

### 3.1 `output` モード選択：static export か Next on Pages か

**現在の `next.config.js` はすでに `output: 'export'` を設定済み**（`standalone` は
Dockerfile 内の fallback で強制されていたが、`next.config.js` 本体は static export）。
`public/_headers` も CF Pages 互換形式で整備済み。この点から **static export (output: 'export')** が
現実的な第一候補となる。

| 方式 | 概要 | 現状との整合 | 主なリスク |
|---|---|---|---|
| **(A) static export** | `next build` → `out/` に HTML/CSS/JS 静的書き出し | `next.config.js` が既に `output: 'export'` / `images.unoptimized: true` | SSR 不可、API routes 不可、動的レンダリング不可 |
| **(B) Next on Pages** | CF Workers + @cloudflare/next-on-pages でエッジ SSR | SSR/API routes を維持できる | `output: 'standalone'` ベースとの構成差異、Workers 制限、要検証 |

> **推奨案 (要確認)**: 方式 A (static export) を staging で先行検証。
> API 呼び出しはすべて CSR (client-side fetch) で処理し、SSR を廃止する方向が最小変更。
> ただし現状が SSR を利用しているか否かを `app/` 配下のコードで確認することを推奨。
> SSR 依存箇所が多い場合は方式 B も検討。

### 3.2 CF Pages プロジェクト設定案

```
# CF Pages Dashboard 設定（案）
Repository:       github.com/<org>/ultra-autotrade (main branch)
Build command:    cd frontend && npm install --legacy-peer-deps && npm run build
Build output dir: frontend/out
Root directory:   /   (monorepo のため、サブディレクトリ指定)
Node.js version:  20
```

> **要確認**: CF Pages の monorepo ビルドでは `Build command` にディレクトリ移動を
> 含める必要がある。`package.json` のスクリプト側で対応する方法もある。

### 3.3 staging / production ブランチ戦略案

| CF Pages 環境 | Git ブランチ | ドメイン案 |
|---|---|---|
| production | `main` | `app.ultra-auto-trade.com` (カスタムドメイン) |
| staging / preview | `staging` ブランチ (要作成) or PR Preview | `staging.ultra-auto-trade.com` |

> **要確認**: CF Pages の「プレビューデプロイ」機能を staging として活用するか、
> 専用 `staging` ブランチを作るかはチームの運用方針次第。

### 3.4 Functions (Workers) 要否

- static export (方式 A) では CF Pages Functions は不要。
- 方式 B (Next on Pages) の場合は Functions が必須。
- いずれの場合も、API は引き続き VPS backend が担当するため、Functions で API proxy する必要はない。

---

## 4. env / secret 移送

### 4.1 移送が必要な変数一覧

| 変数名 | 分類 | CF Pages 設定要否 | 機密性 |
|---|---|---|---|
| `NEXT_PUBLIC_BACKEND_BASE_URL` | build-time | 必要 (staging/production 別) | 低 |
| `NEXT_PUBLIC_API_BASE_URL` | build-time | 必要 | 低 |
| `NEXT_PUBLIC_API_URL` | build-time | 必要 | 低 |
| `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID` | build-time | 必要 | 中 (public key) |
| `NEXT_PUBLIC_DEFAULT_CHAIN` | build-time | 必要 | 低 |
| `NEXT_PUBLIC_DEFAULT_CHAIN_ID` | build-time | 必要 | 低 |
| `NEXT_PUBLIC_MAINNET_RPC` | build-time | 必要 | 中 (API key 含む可能性) |
| `NEXT_PUBLIC_ARBITRUM_ONE_RPC` | build-time | 必要 | 中 |
| `NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC` | build-time | 必要 | 中 |
| `NEXT_PUBLIC_BASE_RPC` | build-time | 必要 | 中 |
| `NEXT_PUBLIC_BASE_SEPOLIA_RPC` | build-time | 必要 | 中 |
| `NEXT_PUBLIC_OPTIMISM_RPC` | build-time | 必要 | 中 |
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | build-time | 必要 | 低 (public key) |
| `NEXT_PUBLIC_LIFF_ID` | build-time | 必要 | 低 |
| `NEXT_PUBLIC_PRIVY_APP_ID` | build-time | 必要 | 低 (public ID) |
| `BACKEND_BASE_URL` | runtime (SSR のみ) | **方式 A では不要** (SSR 廃止) / 方式 B では必要 | 低 |
| `NODE_BUILD_MAX_OLD_SPACE_SIZE` | build-time | **不要** (CF Pages は専用 build 環境) | — |

### 4.2 CF Pages での環境変数管理

- CF Pages Dashboard → Settings → Environment Variables で staging/production を別設定。
- `NEXT_PUBLIC_*` は build-time 変数として登録（CF Pages の build コマンド実行時に展開される）。
- RPC URL など API key を含む可能性のある変数は `Encrypted` 設定を推奨。

### 4.3 VPS 側で不要になる変数 (staging 完了後)

- `docker-compose.staging.yml` / `docker-compose.production.yml` の `frontend.build.args` 全体
- `frontend.environment` の `NEXT_PUBLIC_*` / `BACKEND_BASE_URL`
- `.env.staging-new` / `.env.production` の frontend 関連キー

> **注意**: VPS の `frontend` サービス自体を削除するまでは変数を残す必要がある。
> 段階移行中は両方に同じ値を維持すること。

---

## 5. DNS・ルーティング

### 5.1 現状のドメイン配置

| ドメイン | 用途 | 現状の向き先 |
|---|---|---|
| `app.ultra-auto-trade.com` | frontend (production) | cloudflared Named Tunnel → VPS:3000 |
| `api.ultra-auto-trade.com` | backend API (production) | cloudflared Named Tunnel → VPS:8080 (nginx) |
| `staging.ultra-auto-trade.com` | frontend (staging) | 未設定 (Phase 4 予定、docs/17 参照) |
| `api-staging.ultra-auto-trade.com` | backend API (staging) | 未設定 (Phase 4 予定) |

### 5.2 CF Pages 移行後の DNS 構成案

```
[ユーザーブラウザ]
        │
        ├── app.ultra-auto-trade.com → CF Pages (カスタムドメイン)
        │       静的アセット / PWA / CSR
        │
        └── api.ultra-auto-trade.com → cloudflared Named Tunnel → VPS nginx:8080
                backend API (FastAPI) ← 現状維持
```

- `app.ultra-auto-trade.com` の DNS を CF Pages カスタムドメインに向ける。
  - CF Pages カスタムドメイン設定により、CNAME `<project>.pages.dev` への委任が行われる。
  - Cloudflare ゾーン内のドメインであれば CF Pages の Cloudflare-managed TLS が自動適用。
- `api.ultra-auto-trade.com` は **現状維持**（cloudflared tunnel で VPS backend に到達）。
- `staging.ultra-auto-trade.com` は CF Pages プレビュー環境または staging ブランチデプロイに紐付け。

> **要確認**: `app.ultra-auto-trade.com` は現在 cloudflared tunnel の ingress に登録されている。
> CF Pages カスタムドメイン設定時に DNS CNAME を書き換えると tunnel 経由の frontend が即時切断される。
> カットオーバー時は tunnel ingress からの frontend エントリ削除と DNS 切替を同時に行うこと。
> staging で手順を先行検証することを強く推奨。

### 5.3 cloudflared tunnel との分担（移行後）

移行完了後、`config/cloudflared/config.yml` の ingress から `app.ultra-auto-trade.com` エントリを
削除し、API のみを tunnel 経由とする（案）:

```yaml
# 移行後の ingress イメージ（実装は別タスク）
ingress:
  - hostname: api.ultra-auto-trade.com
    service: http://localhost:8080
  - hostname: api-staging.ultra-auto-trade.com
    service: http://localhost:8082
  - service: http_status:404
```

---

## 6. backend API 接続

### 6.1 static export (方式 A) の場合

- **SSR 廃止**: `output: 'export'` ではサーバーサイドレンダリングが行われないため、
  `BACKEND_BASE_URL` (Docker 内部 URL `http://nginx:8080`) は不要になる。
- **全リクエストが CSR**: ブラウザから直接 `https://api.ultra-auto-trade.com` へ fetch する。
- `NEXT_PUBLIC_BACKEND_BASE_URL` = `https://api.ultra-auto-trade.com` を CF Pages build-time 変数として設定。

> **要確認**: 現在の `app/` 配下に `getServerSideProps` / RSC server component / API routes
> (`app/api/`) が存在するか確認が必要。存在する場合は方式 A への移行に追加対応が必要。

### 6.2 Next on Pages (方式 B) の場合

- **エッジ SSR**: CF Workers 上で SSR が実行される。
- Workers からは `https://api.ultra-auto-trade.com` を経由して backend API に到達する
  (Workers は Docker 内部ネットワークにアクセスできないため、公開 URL 経由が必須)。
- `BACKEND_BASE_URL` の値を `https://api.ultra-auto-trade.com` に変更する必要がある。

### 6.3 CORS

- 現在の CORS 設定 (`CORS_ORIGINS`) は `https://app.ultra-auto-trade.com` を含んでいると想定。
- CF Pages からのリクエストも同じドメインを使用するため、CORS 変更は不要と考えられる。
- ただし CF Pages プレビューデプロイ (`*.pages.dev`) からの開発アクセスが必要な場合は
  `CORS_ORIGINS` に `*.pages.dev` の追加を要検討。

---

## 7. ロールバック手順

CF Pages デプロイが失敗・問題発生した場合に VPS frontend に戻す手順（案）:

### 7.1 即時ロールバック（DNS 切戻し）

1. Cloudflare Dashboard → DNS → `app.ultra-auto-trade.com` のレコードを
   CF Pages カスタムドメイン設定から cloudflared tunnel 向けに戻す。
2. `config/cloudflared/config.yml` に `app.ultra-auto-trade.com → localhost:3000` の
   ingress エントリを復元。
3. cloudflared コンテナを再起動:
   ```bash
   docker compose -f docker-compose.production.yml restart cloudflared
   ```
4. VPS の `frontend` コンテナが稼働中であることを確認:
   ```bash
   docker compose -f docker-compose.production.yml ps frontend
   ```
   停止していれば `docker compose -f docker-compose.production.yml up -d frontend` で起動。

### 7.2 ロールバック前提条件

- VPS 側の `frontend` コンテナと `docker-compose.*.yml` の frontend サービス定義を
  **段階移行期間中は削除しない**こと。
- `.env.production` / `.env.staging-new` の frontend 関連変数を
  **段階移行期間中は削除しない**こと。

---

## 8. 段階移行手順

### フェーズ 1: staging 先行検証

1. CF Pages プロジェクト作成 (staging ブランチ or プレビュー環境)
2. `staging.ultra-auto-trade.com` の DNS を CF Pages preview URL に向ける (未設定のため新規設定)
3. `NEXT_PUBLIC_BACKEND_BASE_URL=https://api-staging.ultra-auto-trade.com` を CF Pages staging 環境変数に設定
4. `frontend/next.config.js` の `output: 'export'` 動作を確認 (現在すでに設定済み)
5. CF Pages build が成功することを確認 (`npm run build` → `out/` 生成)
6. staging URL で動作確認:
   - ページ表示
   - API 疎通 (CSR fetch)
   - PWA / Service Worker 登録
   - LIFF / Privy Wallet 動作 (要確認)
7. 問題なければフェーズ 2 へ

### フェーズ 2: production カットオーバー

1. `app.ultra-auto-trade.com` の CF Pages カスタムドメイン設定
2. DNS 切替（cloudflared tunnel ingress から CF Pages への移行）
3. production 動作確認
4. VPS の frontend コンテナは一定期間（1週間程度）停止せずに保持 → ロールバック用
5. 問題なければ VPS の `frontend` サービス定義・コンテナを削除 (別 PR・別タスク)

### フェーズ 3: VPS cleanup (別タスク)

- `docker-compose.staging.yml` / `docker-compose.production.yml` から `frontend` サービスを削除
- `frontend/Dockerfile` を CF Pages 専用に簡略化（または削除）
- VPS deploy スクリプトから frontend build 関連コマンドを削除

---

## 9. リスク・未決事項

### 9.1 Next.js 機能の CF 互換性

| 機能 | 現状 | CF Pages 静的 export での挙動 | 対応案 |
|---|---|---|---|
| SSR (`getServerSideProps` / RSC) | 使用有無: **要確認** | **不可** (output: 'export') | 廃止 or 方式 B へ変更 |
| API Routes (`app/api/`) | 使用有無: **要確認** | **不可** (output: 'export') | backend に移管 or CF Functions |
| `next/image` 最適化 | `unoptimized: true` 設定済み | 問題なし | — |
| ISR / Dynamic routes | 使用有無: **要確認** | 制限あり | `generateStaticParams` で対応可能か確認 |

### 9.2 PWA / Service Worker

- `next-pwa@5.6.0` は build 時に `public/sw.js` / `workbox-*.js` を生成。
  static export でも動作するが、cf pages の `_headers` 設定と整合が必要。
- `public/_headers` は CF Pages 互換形式でほぼ設定済みだが、CSP の `connect-src` に
  production / staging の backend URL が正しく含まれているか要確認。

### 9.3 LIFF (LINE ミニアプリ)

- `@line/liff@2.28.0` を使用。LIFF は特定のドメイン URL を LINE Developers Console に
  登録する必要がある。
- CF Pages に切り替える場合、LIFF Channel 設定の「エンドポイント URL」を
  `app.ultra-auto-trade.com` (変わらないなら問題なし) または新ドメインに更新が必要か
  **要確認**。

### 9.4 ビルド差異・monorepo 構成

- CF Pages の build コマンドはリポジトリルートから実行される。
  `frontend/` サブディレクトリへの `cd` が必要。
- `npm install --legacy-peer-deps` を build コマンドに含める必要がある（現 Dockerfile 踏襲）。
- `next.config.js` が `output: 'export'` / `images.unoptimized: true` になっていることを
  CF Pages build で使用するブランチ・コミット時点で確認。

### 9.5 コスト

- CF Pages Free Plan: ビルド 500回/月、帯域無制限。
- 月 500回 build を超える場合 (CI/CD の頻度次第) は Pro Plan ($25/月) が必要。
- **要確認**: 現在の deploy 頻度と CF Pages build 回数の見積もり。

### 9.6 `standalone` → `output: 'export'` の移行影響

- `frontend/Dockerfile` の Stage3 (runner: `node server.js`) は static export 後は不要になる。
  CF Pages は `out/` ディレクトリを直接配信するため、Node.js サーバーは起動しない。
- 現在 Dockerfile 内の `Ensure standalone output is enabled` シェルスクリプト
  (L61-66) は `output: 'export'` 環境では誤動作する可能性があるが、CF Pages では
  Dockerfile を使用しないため影響なし。

### 9.7 未決事項まとめ

| # | 未決事項 | 確認方法 |
|---|---|---|
| 1 | `app/` 配下に SSR (server component / `getServerSideProps` / API routes) があるか | `grep -r "getServerSideProps\|use server" frontend/app/` |
| 2 | LIFF Channel のエンドポイント URL 変更要否 | LINE Developers Console で確認 |
| 3 | CF Pages staging は専用ブランチ or プレビューデプロイか | チーム運用方針 |
| 4 | CF Pages build 回数が月 500回を超えるか | deploy 頻度の実績から試算 |
| 5 | `NEXT_PUBLIC_LIFF_ID`, `NEXT_PUBLIC_PRIVY_APP_ID` 等の実値 | `.env.production` / `.env.staging-new` で確認 (Git 管理外) |
| 6 | staging の tunnel ingress (`staging.ultra-auto-trade.com`) の設定状況 | cloudflared / CF Dashboard で確認 |

---

## 参照ドキュメント

- `docs/29_tunnel_ops_guide.md` — cloudflared Named Tunnel 運用
- `docs/32_named_tunnel_migration.md` — Named Tunnel 移行計画
- `docs/17_staging_environment_config.md` — staging 環境設定
- `docs/21_production_environment_config.md` — production 環境変数一覧
- `docs/16_infra_deployment_guide.md` — Hetzner VPS 構成
- `docs/postmortems/2026-05-19_production_stack_container_loss.md` — OOM 関連インシデント
- `docs/internal/staging_build_speedup_design.md` — staging build 高速化設計（対症療法的アプローチ）
- `config/cloudflared/config.yml` — 現在の tunnel ingress 設定
- `frontend/Dockerfile` — 現在の build 構成
- `frontend/next.config.js` — Next.js 設定 (output: 'export' 確認済み)
- `frontend/public/_headers` — CF Pages 互換ヘッダー設定 (CSP/XFO/XCTO)
