# Cloudflare WAF 設定ガイド

## 概要

`scripts/cloudflare_waf_setup.sh` を使って Cloudflare WAF のルールを IaC (Infrastructure as Code) で管理する。

手動ダッシュボード操作を廃止し、Git 管理下のスクリプトで設定を再現可能にする。

---

## 前提条件

### 必要な Cloudflare API Token の権限

| 権限 | 必要な理由 |
|------|-----------|
| Zone > Firewall Services > Edit | Custom Rules の作成・更新 |
| Zone > Zone WAF > Edit | Managed Rulesets の有効化 |

### API Token の作成手順

1. [Cloudflare ダッシュボード](https://dash.cloudflare.com/) にログイン
2. 右上のアイコン → **My Profile** → **API Tokens**
3. **Create Token** → **Custom token**
4. Permissions に以下を追加:
   - `Zone > Firewall Services > Edit`
   - `Zone > Zone WAF > Edit`
5. Zone Resources: `Include > Specific zone > ultra-auto-trade.com`
6. **Create Token** → トークンを安全な場所に保存

### Zone ID の確認

1. Cloudflare ダッシュボード → `ultra-auto-trade.com` をクリック
2. 右サイドバー **API** セクション → **Zone ID** をコピー

---

## 使い方

### 1. dry-run（適用前の確認）

```bash
CF_API_TOKEN=your_token CF_ZONE_ID=your_zone_id \
  ./scripts/cloudflare_waf_setup.sh dry-run
```

API 呼び出しは行わず、適用予定のルール内容を表示する。

### 2. 現在のルール確認

```bash
CF_API_TOKEN=your_token CF_ZONE_ID=your_zone_id \
  ./scripts/cloudflare_waf_setup.sh status
```

### 3. ルールの適用

```bash
CF_API_TOKEN=your_token CF_ZONE_ID=your_zone_id \
  CF_ADMIN_IP=your_admin_ip \
  ./scripts/cloudflare_waf_setup.sh apply
```

> **注意:** `apply` は既存のルールを上書きする（PUT = 全置換）。
> 初回実行前に必ず `dry-run` で内容を確認すること。

---

## 適用されるルール一覧

### Custom WAF Rules (http_request_firewall_custom)

| 優先度 | ルール名 | アクション | 条件 |
|--------|---------|-----------|------|
| 1 | Block-Sensitive-Paths | block | `/docs`, `/openapi.json`, `/redoc` へのアクセス |
| 2 | Block-Bad-UA | block | sqlmap, nikto, dirbuster, nmap, masscan |
| 3 | Challenge-Non-JP-Auth | managed_challenge | `/auth` へのアクセスで country ≠ JP |
| 4 | Block-Admin-NonIP | block | `/admin` へのアクセスで IP ≠ CF_ADMIN_IP（設定時のみ） |

### Rate Limiting Rules (http_ratelimit)

| ルール名 | 制限 | ミティゲーション時間 | 対象 |
|---------|------|-------------------|------|
| Auth brute force | 5 req/60s | 600s | POST /auth/login |
| Register protection | 3 req/600s | 3600s | POST /auth/register |
| API general | 60 req/60s | 300s | /api/ 以下すべて |
| Aave rebalance | 2 req/600s | 1800s | POST /aave/rebalance |
| Emergency stop | 3 req/60s | 300s | POST /emergency-stop |

### Managed Rulesets (http_request_firewall_managed)

| ルールセット | 設定 |
|------------|------|
| Cloudflare Managed Ruleset | デフォルト設定 (block) |
| OWASP Core Ruleset | sensitivity: medium, action: block |

---

## バックエンド側の slowapi との関係

バックエンドにも slowapi による Rate Limiting が実装されている。
Cloudflare の Rate Limiting はその手前（CDN層）で動作するため、
悪意ある大量リクエストがバックエンドに到達する前にブロックされる。

```
Client → Cloudflare WAF (Rate Limit) → Cloudflare Tunnel → Backend (slowapi)
```

両方の設定値を一致させなくても良いが、Cloudflare 側を緩め、Backend 側を厳しくする運用を推奨。

---

## 誤検知への対応

### 特定ルールを一時無効化

```bash
# 現在のルール ID を確認
CF_API_TOKEN=xxx CF_ZONE_ID=yyy ./scripts/cloudflare_waf_setup.sh status

# ダッシュボードから一時無効化:
# Cloudflare → Security → WAF → Custom Rules → 該当ルールのトグルをオフ
```

### スクリプトからルールを除外して再適用

`scripts/cloudflare_waf_setup.sh` 内の該当ルールブロックをコメントアウトして再度 `apply` を実行する。

---

## 監視とアラート

適用後 2 週間は Cloudflare Analytics を確認する:

1. Cloudflare ダッシュボード → **Security** → **Overview**
2. ブロック数・チャレンジ数を確認
3. 正規ユーザーがブロックされていないか確認

---

## Managed Ruleset の固定 ID（参考）

| ルールセット | ID |
|------------|-----|
| Cloudflare Managed Ruleset | `efb7b8c949ac4650a09736fc376e9aee` |
| OWASP Core Ruleset | `4814384a9e5d4991b9815dcfc25d2f1f` |

これらは Cloudflare が提供するグローバル共通 ID であり変更されない。
参照: https://developers.cloudflare.com/waf/managed-rules/reference/cloudflare-managed-ruleset/
