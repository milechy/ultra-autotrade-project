# Cloudflare Tunnel 運用ガイド

## 概要

Ultra AutoTrade の staging / production 環境では Cloudflare Named Tunnel を使用して
Hetzner VPS のバックエンド・フロントエンドを固定 URL で公開する。

Named Tunnel の移行計画・手順詳細は `docs/32_named_tunnel_migration.md` を参照。

---

## アーキテクチャ

```
インターネット
   │
Cloudflare Edge
   │ (Named Tunnel)
   ├── api.ultra-autotrade.com → backend:8000
   └── app.ultra-autotrade.com → frontend:3000
                                    │
                              Hetzner VPS
                         (Docker Compose)
```

---

## ファイル構成

| ファイル | 用途 |
|---|---|
| `config/cloudflared/config.yml` | Tunnel 設定テンプレート（`<TUNNEL_ID>` は実際の値に置換） |
| `docker-compose.staging.yml` | `cloudflared` サービス定義を含む |
| `/root/.cloudflared/<TUNNEL_ID>.json` | Tunnel 認証情報（Hetzner VPS 上、Git 管理外） |

---

## 初回セットアップ手順（Hetzner VPS 上で実行）

```bash
# 1. Cloudflare にログイン
cloudflared login

# 2. Named Tunnel 作成
cloudflared tunnel create ultra-autotrade
# → Tunnel ID が出力される（例: a1b2c3d4-...）

# 3. DNS ルーティング登録
cloudflared tunnel route dns ultra-autotrade api.ultra-autotrade.com
cloudflared tunnel route dns ultra-autotrade app.ultra-autotrade.com

# 4. config.yml の <TUNNEL_ID> を実際の値に置換
sed -i "s/<TUNNEL_ID>/a1b2c3d4-.../g" /opt/ultra-autotrade/config/cloudflared/config.yml

# 5. Docker Compose で起動
docker compose -f docker-compose.staging.yml up -d cloudflared
```

---

## 日常運用

### 状態確認

```bash
# コンテナログ確認
docker logs ultra-autotrade-cloudflared-staging

# 接続テスト
curl -s https://api.ultra-autotrade.com/health
```

### 再起動

```bash
docker compose -f docker-compose.staging.yml restart cloudflared
```

### Tunnel 一覧・状態確認

```bash
cloudflared tunnel list
cloudflared tunnel info ultra-autotrade
```

---

## ロールバック（Quick Tunnel に戻す）

```bash
# 1. cloudflared コンテナを停止
docker compose -f docker-compose.staging.yml stop cloudflared

# 2. Quick Tunnel を手動起動（一時的）
cloudflared tunnel --url http://localhost:8000 &

# 3. .env.staging の NEXT_PUBLIC_BACKEND_BASE_URL を新しいランダム URL に更新
# 4. backend を再起動
docker compose -f docker-compose.staging.yml restart backend
```

---

## インシデント履歴

| 日付 | 症状 | 原因 | 対応 | 再発防止 |
|---|---|---|---|---|
| 2026-04-01 | CORS→実は500（不足カラム）+ Mixed Content + .env改行欠落 | (1) terms_version等9カラムがDBに未追加→500→CORSヘッダーなし→CORSエラーに見えた (2) NEXT_PUBLIC_BACKEND_BASE_URL=http://でトンネルhttps経由アクセス→Mixed Content (3) echo追記で改行なし連結 | ALTER TABLE全カラム追加、IP直接アクセスに切り替え、printf使用 | — |

---

## トラブルシューティング

| 症状 | 原因 | 対応 |
|---|---|---|
| `tunnel: <TUNNEL_ID>` がそのまま残っている | config.yml の placeholder 未置換 | `sed -i "s/<TUNNEL_ID>/実際のID/g" config.yml` |
| `/root/.cloudflared` がマウントできない | 認証情報ファイル未生成 | `cloudflared tunnel create` を先に実行 |
| 502 Bad Gateway | backend が起動していない | `docker compose ps` で状態確認 |
| DNS エラー | DNS プロパゲーション未完了 | 最大48時間待機 |
| CORSエラーだがOPTIONSは正常 | バックエンドが500を返している（CORSヘッダーはエラー時に付かない） | `docker logs <backend> 2>&1 \| grep error` でDB不足カラム等を確認→修正 |
| httpsページからhttpバックエンドへのリクエストがブロック | Mixed Content（https→http） | IP直接アクセス（http同士）を使うか、バックエンドもトンネル経由にする |
| echo追記した環境変数が効かない | 前行の末尾に改行がなく連結された | `grep <KEY> .env.staging` で確認。`printf '\nKEY=VALUE\n' >> file` を使う |

---

## セキュリティ注意事項

- `/root/.cloudflared/<TUNNEL_ID>.json` は **Git 管理外**（`.gitignore` に記載済み）
- Tunnel 認証情報は `docs/backups/env/` に暗号化して保管すること
- Tunnel ID は公開しても安全だが、認証情報ファイルは絶対に公開しない

---

## 関連ドキュメント

- `docs/32_named_tunnel_migration.md` — 移行計画・詳細手順
- `docs/16_infra_deployment_guide.md` — Hetzner VPS 構成
- `docs/21_production_environment_config.md` — 環境変数一覧
- `docs/13_security_design.md` — CORS / CSP セキュリティ要件
