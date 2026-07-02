# 24_partner_test_guide.md
# パートナー向けテストガイド

> **対象読者:** パートナー企業の開発者
> **最終更新:** 2026-03-11 (Stream K)
> **環境:** Staging（テストネット）。本番資金には一切アクセスしない。

---

## 1. 概要

Ultra AutoTrade は、ニュース情報を AI が解析し BUY/SELL/HOLD を判定、Bybit / bitFlyer への取引注文と Aave でのポジション管理を自動化するシステムです。

### パートナーが検証する範囲

| 対象 | 内容 |
|------|------|
| 運用ダッシュボード（読み取り専用）| 稼働状況・AI 判定履歴・直近レポートの確認 |
| AI シグナルフロー | `/api/ai/analyze` → `/api/octobot/signal` の動作確認 |
| Aave dry-run | `dry_run=true` での rebalance 動作確認 |
| 緊急停止ステータス確認 | `is_trading_paused` の確認 |

---

## 2. Staging 環境へのアクセス

| サービス | URL |
|----------|-----|
| フロントエンド | `https://app.ultra-auto-trade.com` |
| バックエンド API | `https://api.ultra-auto-trade.com` |
| API ドキュメント（Swagger UI） | 本番では無効化済み（APP_ENV=production） |

> **注意:** 188.34.167.142 への直接アクセスは127.0.0.1バインドにより接続拒否されます（正常動作）。
> 全てのアクセスはCloudflare Named Tunnel経由の上記URLを使用してください。

> **ログイン情報:** 別途 PM より共有します。

### Staging 環境の制約

- `AI_SHADOW_MODE=true` — AI 判定は記録されますが、**実際の取引は実行されません**
- `EXCHANGE_SANDBOX=true` — 取引所はサンドボックス環境
- `AAVE_CLIENT_TYPE=dummy` — Aave はダミークライアント（実チェーンには接続しない）
- dry_run 以外の Aave 操作は実行しないこと

---

## 3. 環境変数（.env）設定ガイド

パートナー環境でローカル動作確認を行う場合の `.env` 設定例。

```bash
# 必須
DATABASE_URL=postgresql://ultra:ultra@localhost:5432/ultra_autotrade
SECRET_KEY=<別途共有>
ANTHROPIC_API_KEY=<別途共有>

# 取引所（Staging では Sandbox / bitFlyer dry_run）
EXCHANGE_CLIENT_TYPE=bitflyer       # または "sandbox" / "dummy"
EXCHANGE_SANDBOX=true
BITFLYER_API_KEY=<別途共有>
BITFLYER_API_SECRET=<別途共有>

# AI（Staging では Shadow Mode 必須）
AI_SHADOW_MODE=true
AI_CROSS_VALIDATION_ENABLED=false   # staging ではコスト節約のため false
AI_CLAUDE_MODEL=claude-sonnet-4-20250514
AI_MIN_CONFIDENCE_THRESHOLD=40

# Knowledge Hub
KNOWLEDGE_EMBEDDING_MODEL=text-embedding-3-small
KNOWLEDGE_EMBEDDING_DIMENSIONS=1536

# Aave（Staging ではダミー）
AAVE_CLIENT_TYPE=dummy
AAVE_MIN_HEALTH_FACTOR=1.6
```

> **注意:** `.env` ファイルは絶対にコミットしないこと。本番と Staging で**必ず別々のキー**を使用すること（`docs/13_security_design.md` §7 参照）。

---

## 4. 開発ワークフロー

### ブランチ戦略

```
feature/<stream-id>-<description>   ← 各機能開発
       ↓ PR
dev                                  ← 統合・Staging デプロイ
       ↓ PR（Codex レビュー通過後）
main                                 ← 本番
```

- `main` への直接 push は禁止。PR + レビュー必須。
- 各 Stream は独立した feature ブランチで並行開発。
- Staging は `dev` ブランチを Hetzner VPS に手動デプロイ。

### ストリーム並行開発（Wave 体制）

各 Stream は機能単位で独立しており、同時並行で開発可能。

| Stream | 担当領域 |
|--------|---------|
| Stream A | Knowledge Hub（PostgreSQL + pgvector） |
| Stream B | Exchange（Bybit/bitFlyer ccxt 抽象化） |
| Stream C | AI 判定エンジン（Two-Phase + Shadow Mode） |
| Stream D | Aave 連携（web3.py + Flashbots） |
| Stream E | フロントエンド（Next.js + shadcn/ui） |
| Stream K | ドキュメント整備 |

---

## 5. テスト実行方法（DoD 準拠）

コード変更前後に以下を全て通過させること。

```bash
# 1. Lint（エラー 0 必須）
ruff check .

# 2. フォーマット（違反 0 必須）
ruff format --check .

# 3. 型チェック（エラー 0 必須）
mypy app/ --config-file ../pyproject.toml

# 4. テスト + カバレッジ（80%+ 必須）
pytest tests/ --cov=app --cov-fail-under=80 -q

# 5. セキュリティ確認（新規 critical なし）
ruff check . --select S
```

### 一括確認（`/verify` コマンド）

```bash
# Claude Code 内で
/verify
```

---

## 6. 検証シナリオ

### シナリオ A: ダッシュボード閲覧

1. `https://app.ultra-auto-trade.com/dashboard/automation` にアクセス
2. 稼働状況（`is_trading_paused`、最終取引時刻）を確認
3. `https://app.ultra-auto-trade.com/dashboard/reports` で最新レポートを確認

---

### シナリオ B: AI シグナルフロー確認

**Step 1: AI 判定**

```bash
curl -s -X POST https://api.ultra-auto-trade.com/ai/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [{
      "id": "test-001",
      "url": "https://example.com/btc-news",
      "summary": "Bitcoin breaks $100k amid institutional buying",
      "sentiment": null,
      "action": null,
      "confidence": null,
      "status": "未処理",
      "timestamp": null
    }]
  }' | python3 -m json.tool
```

期待レスポンス例:

```json
{
  "results": [{
    "id": "test-001",
    "action": "BUY",
    "confidence": 78,
    "reason": "機関投資家の買い材料あり"
  }],
  "count": 1
}
```

> **注意:** `AI_SHADOW_MODE=true` の Staging では実取引は行われません。

**Step 2: シグナル送信**

```bash
curl -s -X POST https://api.ultra-auto-trade.com/octobot/signal \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "signals": [{
      "id": "test-001",
      "url": "https://example.com/btc-news",
      "action": "BUY",
      "confidence": 78,
      "reason": "機関投資家の買い材料あり",
      "timestamp": "2026-01-01T08:00:00Z"
    }],
    "count": 1
  }' | python3 -m json.tool
```

---

### シナリオ C: Aave リバランス dry-run

```bash
# BUY (dry_run=true)
curl -s -X POST https://api.ultra-auto-trade.com/aave/rebalance \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"action": "BUY", "amount": "10.0", "asset_symbol": "USDC", "dry_run": true}' \
  | python3 -m json.tool

# SELL (dry_run=true)
curl -s -X POST https://api.ultra-auto-trade.com/aave/rebalance \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"action": "SELL", "amount": "10.0", "asset_symbol": "USDC", "dry_run": true}' \
  | python3 -m json.tool
```

期待レスポンス例（dry_run=true）:

```json
{
  "result": {
    "operation": "DEPOSIT",
    "status": "success",
    "asset_symbol": "USDC",
    "amount": "10.0",
    "tx_hash": null,
    "message": "dry_run: transaction not sent",
    "before_health_factor": "2.10",
    "after_health_factor": "2.10"
  }
}
```

---

### シナリオ D: 緊急停止状態の確認

```bash
curl -s https://api.ultra-auto-trade.com/api/automation/status \
  -H "Authorization: Bearer <token>" \
  | python3 -m json.tool
```

`is_trading_paused: true` の場合、全取引が停止中であることを確認。

---

## 7. デプロイ手順

Staging へのデプロイは `docs/deploy_staging.md` を参照。

主要ステップ概要:
1. `git pull origin dev` で最新を取得
2. `.env.staging` に Wave 1〜3 の新環境変数が含まれているか確認
3. `docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build`
4. ヘルスチェック: `GET /health` → 200

詳細手順: [deploy_staging.md](./deploy_staging.md)

---

## 8. Wave 0〜3 成果サマリー

| Wave | Stream | 主な成果 |
|------|--------|---------|
| Wave 0 | Core Setup | FastAPI + PostgreSQL + Docker Compose 基盤構築。認証（JWT）実装。 |
| Wave 1 | Stream A | Knowledge Hub（PostgreSQL + pgvector）実装。旧 Notion 依存を完全撤廃。POST/GET/search/status エンドポイント実装。 |
| Wave 2 | Stream B + C | Exchange 抽象化（Bybit Sandbox / bitFlyer 切替）実装。AI Two-Phase 判定（Claude + GPT-4o クロス検証）実装。Shadow Mode 追加。 |
| Wave 3 | Stream D + E | Aave web3.py 連携（Flashbots 対応）実装。セキュリティ強化（HF ガード、クールダウン、緊急停止）。Slack/LINE 通知実装。AI 判定精度テスト + 収益モデル（手数料計算）実装。 |

---

## 9. 制約と注意事項

- Staging 環境では `dry_run=false` の Aave 操作は実行しない
- 状態変更操作はダッシュボード経由のみ（直接トランザクション送信不可）
- API キーは別途 PM より共有。Slack や Git にコミットしないこと
- 本番資金には一切アクセスしない（Staging は全てテストネット）

---

## 10. 問題報告

バグや不整合を発見した場合:

1. **報告先:** プロジェクト Slack `#ultra-autotrade-bugs`
2. **再現手順フォーマット:**

```markdown
## 概要
<何が起きたか>

## 再現手順
1. ...
2. ...

## 期待動作
<こうなるはずだった>

## 実際の動作
<こうなった>

## 環境情報
- 日時（UTC）:
- エンドポイント:
- リクエスト本文:
- レスポンス本文:
- レスポンスコード:
```

---

## 関連ドキュメント

- [00_overview.md](./00_overview.md) — システム概要
- [04_api_design.md](./04_api_design.md) — API 設計書（全エンドポイント）
- [13_security_design.md](./13_security_design.md) — セキュリティ設計
- [14_test_strategy.md](./14_test_strategy.md) — テスト戦略
- [deploy_staging.md](./deploy_staging.md) — Staging デプロイ手順
- [19_operations_runbook.md](./19_operations_runbook.md) — 運用 Runbook（§2.5 ダッシュボード UI）
