# 04_api_design.md
# API設計書

> **最終更新:** 2026-03-11 (Stream K)
> **対応バージョン:** Wave 0〜3 実装済みエンドポイントを反映

---

## 概要

本ドキュメントは Ultra AutoTrade バックエンド（FastAPI）の全 API エンドポイントを定義する。
スキーマの真実は `backend/app/*/schemas.py` にある。本書はそのドキュメント化版。

### ベース URL

| 環境 | URL |
|------|-----|
| ローカル開発 | `http://localhost:8000` |
| Staging | `http://188.34.167.142:8000` |
| 本番 | Cloudflare Tunnel 経由（別途設定） |

### 認証

全エンドポイントは Bearer トークン認証が必要（`Authorization: Bearer <token>`）。
ロール: `viewer`（読み取り）、`editor`（作成・更新）、`admin`（危険操作）

---

## 1. Knowledge Hub (`/knowledge/*`)

> **旧 `/notion/*` エンドポイントを完全置換。** Notion 依存を撤廃し PostgreSQL + pgvector による内部 Knowledge Hub に移行。

### 1.1 POST /knowledge/items — ナレッジアイテム登録

URL またはテキストを取り込み、チャンク分割・埋め込み生成を行い DB に保存する。

- **Method:** POST
- **Path:** `/knowledge/items`
- **Auth:** `editor` ロール必須
- **Status:** `201 Created`

#### リクエスト (`KnowledgeCreateRequest`)

```json
{
  "title": "BTC急騰ニュース（任意）",
  "item_type": "url",
  "source_url": "https://example.com/btc-news",
  "raw_text": null
}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `title` | string \| null | 任意 | アイテムのタイトル |
| `item_type` | `"url"` \| `"text"` | 必須 | 入力種別 |
| `source_url` | string \| null | `item_type=url` 時必須 | スクレイピング対象の URL |
| `raw_text` | string \| null | `item_type=text` 時必須 | 登録するテキスト |

#### レスポンス (`KnowledgeItem`)

```json
{
  "id": 1,
  "source_url": "https://example.com/btc-news",
  "title": "BTC急騰ニュース",
  "raw_text": null,
  "status": "pending",
  "chunk_count": 5,
  "item_type": "url",
  "quality_score": 87.5,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | int | DB 自動採番 ID |
| `status` | `pending` \| `analyzed` \| `skipped` \| `error` | 処理状態 |
| `chunk_count` | int | 生成されたチャンク数 |
| `quality_score` | float \| null | コンテンツ品質スコア（0〜100） |

#### エラー

| コード | 条件 |
|---|---|
| 422 | バリデーションエラー（item_type と source_url/raw_text の不整合など） |
| 500 | サーバ内部エラー |

---

### 1.2 GET /knowledge/items — アイテム一覧取得

- **Method:** GET
- **Path:** `/knowledge/items`
- **Auth:** `viewer` ロール必須
- **Query:** `status` (optional): `pending` / `analyzed` / `skipped` / `error`

#### レスポンス

`KnowledgeItem` の配列を返す。

```json
[
  {
    "id": 1,
    "status": "pending",
    "item_type": "url",
    ...
  }
]
```

---

### 1.3 POST /knowledge/search — ベクトル検索

pgvector コサイン類似度でナレッジを検索する（RAG 用）。

- **Method:** POST
- **Path:** `/knowledge/search`
- **Auth:** `viewer` ロール必須

#### リクエスト (`KnowledgeSearchRequest`)

```json
{
  "query": "BTC price trend bullish",
  "top_k": 5
}
```

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `query` | string | — | 検索クエリ文字列（1文字以上） |
| `top_k` | int | 5 | 返却する最大件数（1〜20） |

#### レスポンス (`KnowledgeSearchResponse`)

```json
{
  "results": [
    {
      "chunk_id": 12,
      "document_id": 1,
      "content": "BTC が 50,000 USD を突破...",
      "similarity": 0.923,
      "source_url": "https://example.com/btc-news",
      "title": "BTC急騰ニュース"
    }
  ],
  "count": 1,
  "query": "BTC price trend bullish"
}
```

---

### 1.4 PUT /knowledge/items/{item_id}/status — ステータス更新

- **Method:** PUT
- **Path:** `/knowledge/items/{item_id}/status`
- **Auth:** `editor` ロール必須

リクエストボディに `KnowledgeItemStatus` の値（`"pending"` / `"analyzed"` / `"skipped"` / `"error"`）を指定する。

---

## 2. AI 解析 (`/ai/*`)

### 2.1 POST /ai/analyze — Two-Phase AI 判定

ニュースを解析し BUY / SELL / HOLD を判定する。

**Two-Phase フロー:**
1. **Phase A（必須）:** Claude Opus 4.6 による一次判定
2. **Phase B（条件付き）:** BUY または SELL 判定、かつ `AI_CROSS_VALIDATION_ENABLED=true` の場合のみ GPT-4o による二次判定
3. **Shadow Mode:** `AI_SHADOW_MODE=true` の場合は判定結果をログに記録するだけで実取引は行わない

**ルールエンジン（LLM 呼び出し前に評価）:**
1. HF < 1.6 → HOLD（LLM 呼び出しなし）
2. クールダウン中 → HOLD
3. 日次上限（30%）到達 → HOLD

- **Method:** POST
- **Path:** `/ai/analyze`
- **Auth:** `editor` ロール必須

#### リクエスト (`AIAnalysisRequest`)

```json
{
  "items": [
    {
      "id": "item-001",
      "url": "https://example.com/news1",
      "summary": "The company reported record profit.",
      "sentiment": null,
      "action": null,
      "confidence": null,
      "status": "未処理",
      "timestamp": null
    }
  ]
}
```

#### レスポンス (`AIAnalysisResponse`)

```json
{
  "results": [
    {
      "id": "item-001",
      "url": "https://example.com/news1",
      "action": "BUY",
      "confidence": 80,
      "sentiment": "positive",
      "summary": "The company reported record profit.",
      "reason": "好材料多く、BUY判定。",
      "timestamp": "2026-01-01T08:00:00Z"
    }
  ],
  "count": 1
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `action` | `BUY` \| `SELL` \| `HOLD` | AI 最終判定 |
| `confidence` | int (0〜100) | 信頼度スコア。40未満は HOLD に倒す |
| `reason` | string \| null | 判定理由（日本語） |

#### Shadow Mode

`AI_SHADOW_MODE=true` 時は `/ai/analyze` は通常通りレスポンスを返すが、
後続の `/exchange/order` / `/aave/rebalance` は実行されない（`ShadowModeLog` に記録のみ）。

#### エラー

| コード | 条件 |
|---|---|
| 422 | リクエスト JSON スキーマ不整合 |
| 500 | LLM 呼び出し失敗など |

---

## 3. Exchange (`/exchange/*`)

Bybit（本番・Sandbox 切替可）または bitFlyer を抽象化した取引所 API。

**クライアント切替（`EXCHANGE_CLIENT_TYPE` 環境変数）:**
| 値 | クライアント | 用途 |
|---|---|---|
| `dummy` | DummyExchangeClient | テスト・開発用 |
| `bitflyer` | BitFlyerClient | bitFlyer（dry_run 強制） |
| `sandbox` / `bybit`（デフォルト） | BybitSandboxClient | Bybit Sandbox / 本番 |

`APP_ENV=prod` 時は Bybit が本番モード（`sandbox=False`）で動作する。

### 3.1 POST /exchange/order — 取引注文実行

- **Method:** POST
- **Path:** `/exchange/order`
- **Auth:** 認証あり

#### リクエスト (`OrderRequest`)

```json
{
  "action": "BUY",
  "symbol": "BTC/USDT",
  "amount_usd": "100.00",
  "reason": "AI判定 BUY: 信頼度80",
  "dry_run": false
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `action` | `BUY` \| `SELL` \| `HOLD` | AI 判定アクション |
| `symbol` | string \| null | 取引シンボル。未指定時は設定のデフォルト |
| `amount_usd` | Decimal (>0) | 注文金額（USD）|
| `reason` | string \| null | 注文根拠（ログ用） |
| `dry_run` | bool | true の場合は実注文なし |

#### レスポンス (`OrderResult`)

```json
{
  "order_id": "ORDER-12345",
  "status": "success",
  "side": "buy",
  "symbol": "BTC/USDT",
  "amount_usd": "100.00",
  "price": "45000.00",
  "message": null,
  "timestamp": "2026-01-01T08:00:00Z"
}
```

| `status` | 説明 |
|---|---|
| `success` | 注文成功 |
| `skipped` | HOLD またはルールチェック（日次上限・クールダウン・最大金額）に引っかかった |
| `failed` | 取引所エラー |

---

### 3.2 GET /exchange/status — 接続状態確認

- **Method:** GET
- **Path:** `/exchange/status`
- **Auth:** 認証あり

#### レスポンス (`ExchangeStatusResponse`)

```json
{
  "sandbox_mode": true,
  "connected": true,
  "balance_usdt": "1500.00",
  "daily_trades_used": 2,
  "daily_trade_limit": 5,
  "last_trade_at": "2026-01-01T07:30:00Z"
}
```

---

## 4. Aave (`/aave/*`)

### 4.1 POST /aave/rebalance — Aave ポジション調整

BUY/SELL/HOLD アクションを受け取り、Aave に対して deposit / withdraw / NOOP を実行する。

**安全ガード（優先順位順）:**
1. `emergency_stop=true` → NOOP（HARD_STOP）
2. HF < `AAVE_MIN_HEALTH_FACTOR`（デフォルト 1.6） → NOOP
3. クールダウン中（10分以内に操作済み）→ NOOP（BUY のみ）
4. `amount > AAVE_MAX_SINGLE_TRADE_USD` → `AAVE_MAX_SINGLE_TRADE_USD` にクリップ

**アクションマッピング:**
| AI アクション | Aave 操作 |
|---|---|
| `BUY` | `DEPOSIT`（安全ガードを満たした場合） |
| `SELL` | `WITHDRAW` |
| `HOLD` | `NOOP` |

**Flashbots 対応:**
`AAVE_FLASHBOTS_RPC_URL` を設定すると MEV 対策として Flashbots RPC 経由でトランザクションを送信する。
未設定の場合は通常の RPC を使用。

- **Method:** POST
- **Path:** `/aave/rebalance`
- **Auth:** `admin` ロール必須

#### リクエスト (`AaveRebalanceRequest`)

```json
{
  "action": "BUY",
  "amount": "10.00",
  "asset_symbol": "USDC",
  "dry_run": false
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `action` | `BUY` \| `SELL` \| `HOLD` | AI 判定アクション |
| `amount` | Decimal (>0) | 対象資産の金額（USD 相当）|
| `asset_symbol` | string \| null | トークンシンボル。未指定時は設定デフォルト（USDC） |
| `dry_run` | bool | true の場合は実トランザクション送信なし |

#### レスポンス (`AaveRebalanceResponse`)

```json
{
  "result": {
    "operation": "DEPOSIT",
    "status": "success",
    "asset_symbol": "USDC",
    "amount": "10.00",
    "tx_hash": "0xabc123...",
    "message": null,
    "before_health_factor": "2.10",
    "after_health_factor": "2.05"
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `operation` | `DEPOSIT` \| `WITHDRAW` \| `NOOP` | 実行された操作 |
| `status` | `success` \| `skipped` \| `error` | 結果ステータス |
| `tx_hash` | string \| null | トランザクションハッシュ。NOOP / dry_run 時は null |
| `before_health_factor` | Decimal \| null | 操作前 HF |
| `after_health_factor` | Decimal \| null | 操作後 HF |

#### エラー

| コード | 条件 |
|---|---|
| 400 | `amount <= 0` など入力異常 |
| 422 | Pydantic バリデーションエラー |
| 500 | サービス層の予期しない例外 |

---

## 5. OctoBot (`/octobot/signal`)

### 5.1 POST /octobot/signal — シグナル送信

AI 判定結果を OctoBot 外部シグナル API へ送信する。

- **Method:** POST
- **Path:** `/octobot/signal`

#### リクエスト

```json
{
  "signals": [
    {
      "id": "item-001",
      "url": "https://example.com/news1",
      "action": "BUY",
      "confidence": 85,
      "reason": "好材料多く BUY 判定",
      "timestamp": "2026-01-01T08:00:00Z"
    }
  ],
  "count": 1
}
```

`count` と `signals` の件数が不一致の場合は 400 Bad Request。

#### レスポンス

```json
{
  "success_count": 1,
  "skipped_count": 0,
  "failed_count": 0,
  "details": [
    {
      "id": "item-001",
      "status": "sent",
      "message": null
    }
  ]
}
```

---

## 6. Automation (`/api/automation/*`)

自動運用基盤のモニタリング API。

### 6.1 GET /api/automation/dashboard — ダッシュボードスナップショット

- **Query:** `lookback_hours` (int, 1〜24): 集計対象期間
- **Response:** `DashboardSnapshot`

### 6.2 GET /api/automation/status — 自動運用ステータス

緊急停止フラグ・HF・直近イベントなど。
- **Response:** `AutomationStatus`（`is_trading_paused` フィールド含む）

### 6.3 GET /api/automation/reports/latest — 最新レポート

直近のサマリレポートを返す。
- **Response:** `AutomationReportSummary`

> **注意:** これら 3 API のレスポンススキーマは backend 側定義を真実とする。
> フロントエンド / Grafana は未知フィールドを Raw JSON で吸収すること。

---

## 7. Auth (`/auth/*`)

| Method | Path | 説明 |
|---|---|---|
| POST | `/auth/login` | JWT トークン発行 |
| POST | `/auth/logout` | トークン無効化 |
| GET | `/auth/me` | 現在のユーザー情報取得 |

---

## 8. 廃止エンドポイント

以下のエンドポイントは **廃止済み**。移行先を参照すること。

| 廃止エンドポイント | 移行先 | 廃止バージョン |
|---|---|---|
| `POST /notion/ingest` | `POST /knowledge/items` | Wave 1 |
| `GET /notion/items` | `GET /knowledge/items` | Wave 1 |
| `POST /report/daily` | `GET /api/automation/reports/latest` | Wave 2 |

---

## 関連ドキュメント

- [05_ai_judgement_rules.md](./05_ai_judgement_rules.md) — AI 判定ルール詳細
- [07_aave_operation_logic.md](./07_aave_operation_logic.md) — Aave 運用ロジック
- [09_knowledge_hub_schema.md](./09_knowledge_hub_schema.md) — Knowledge Hub DB スキーマ
- [13_security_design.md](./13_security_design.md) — セキュリティ設計
- [14_test_strategy.md](./14_test_strategy.md) — テスト戦略
