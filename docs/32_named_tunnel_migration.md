# Cloudflare Named Tunnel 移行計画

## 現状（Quick Tunnel）

- `cloudflared tunnel --url http://localhost:8000` でランダムURL発行
- Hetzner再起動でURL変更 → CORS / CSP / `NEXT_PUBLIC_BACKEND_BASE_URL` 全更新 + フロントエンドリビルドが毎回必要
- テスター稼働中はプロセス再起動不可

## 目標（Named Tunnel）

- 固定URL（例: `api.ultra-autotrade.com`, `app.ultra-autotrade.com`）
- Hetzner再起動でもURL不変
- CORS / CSP 設定が安定し、以後の環境変数更新・リビルドが不要

---

## 前提条件

- カスタムドメイン取得（`ultra-autotrade.com` または類似）
- Cloudflare アカウント（Free Plan で利用可能）
- `cloudflared` のインストール（Hetzner VPS に既存）
- Cloudflare DNS にドメインを委任済み

---

## 移行手順

### Step 1: ドメイン取得 + Cloudflare DNS 委任

1. ドメインレジストラ（Namecheap / Google Domains 等）でドメインを取得
2. Cloudflare ダッシュボード → 「サイトを追加」
3. レジストラのネームサーバーを Cloudflare が指定する NS に変更
4. DNS プロパゲーション完了を確認（通常数分〜数時間、最大48時間）

### Step 2: Named Tunnel 作成（Hetzner VPS 上で実行）

```bash
# Cloudflare にログイン（ブラウザが開く）
cloudflared login

# Tunnel 作成
cloudflared tunnel create ultra-autotrade

# DNS レコード登録（CNAME で tunnel に向ける）
cloudflared tunnel route dns ultra-autotrade api.ultra-autotrade.com
cloudflared tunnel route dns ultra-autotrade app.ultra-autotrade.com
```

実行後、`~/.cloudflared/<TUNNEL_ID>.json` に認証情報が生成される。

### Step 3: config.yml 作成

```bash
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: api.ultra-autotrade.com
    service: http://localhost:8000
  - hostname: app.ultra-autotrade.com
    service: http://localhost:3000
  - service: http_status:404
EOF
```

`<TUNNEL_ID>` は `cloudflared tunnel create` の出力から取得。

### Step 4: systemd サービス化

```bash
# cloudflared をシステムサービスとして登録
cloudflared service install

# 自動起動 + 即時起動
systemctl enable cloudflared
systemctl start cloudflared

# 状態確認
systemctl status cloudflared
```

### Step 5: 環境変数更新（1回のみ）

Hetzner VPS 上の `.env.production` を更新:

```bash
# .env.production
CORS_ORIGINS=https://app.ultra-autotrade.com
NEXT_PUBLIC_BACKEND_BASE_URL=https://api.ultra-autotrade.com
```

CSP (`backend/app/core/security.py` または nginx 設定) も合わせて更新:

```
connect-src 'self' https://api.ultra-autotrade.com;
```

### Step 6: フロントエンドリビルド（1回のみ）

```bash
cd frontend
npm run build
# または Cloudflare Pages の場合は自動デプロイ
```

> 以後、Hetzner 再起動でもURLは不変のためリビルド不要。

---

## 工数見積もり

| 作業 | 工数 |
|---|---|
| ドメイン取得 + Cloudflare 設定 | 30分 |
| Named Tunnel 作成 + DNS 登録 | 30分 |
| config.yml + systemd 設定 | 30分 |
| 環境変数更新 + リビルド | 30分 |
| テスター確認 | 30分 |
| **合計** | **約2.5時間** |

---

## リスク・注意事項

| リスク | 対応 |
|---|---|
| DNS プロパゲーション遅延（最大48時間） | テスター稼働中を避けて実施 |
| テスターのブックマーク・MetaMask 設定変更が必要 | 事前に周知・マニュアル更新 |
| Quick Tunnel → Named Tunnel 切り替え時の一時的な接続断 | メンテナンス時間帯（深夜）に実施 |
| `cloudflared` の証明書ファイルのバックアップ | `~/.cloudflared/<TUNNEL_ID>.json` を `docs/backups/env/` に保管 |

---

## ロールバック手順

Named Tunnel 設定に問題が発生した場合:

```bash
# systemd サービスを停止
systemctl stop cloudflared

# Quick Tunnel に戻す（旧 URL を再発行）
cloudflared tunnel --url http://localhost:8000

# .env.production を旧 URL に戻して backend 再起動
docker compose -f /opt/ultra-autotrade/docker-compose.production.yml restart backend
```

---

## 関連ドキュメント

- `docs/16_infra_deployment_guide.md` — Hetzner VPS 構成
- `docs/19_operations_runbook.md` — 運用手順全般
- `docs/21_production_environment_config.md` — 環境変数一覧
- `docs/13_security_design.md` — CSP / CORS セキュリティ要件
