# 25_workflow_knowledge_hub.md
# E2E ワークフロー: Knowledge Hub → RAG → AI Judge → Exchange

> **旧フロー（Notion → /notion/ingest）から移行済み（2026-03）**
> Notion は完全撤去。Knowledge Hub（PostgreSQL + pgvector）が唯一の入力・検索ストアになった。

---

## 全体フロー

```
[ユーザー / 外部システム]
        ↓ POST /knowledge/items
[Knowledge Hub]
  1. テキスト取得（URL スクレイピング / 生テキスト）
  2. チャンク分割（tiktoken）
  3. embedding 生成（OpenAI text-embedding-3-small）
  4. PostgreSQL + pgvector に保存（status: pending）
        ↓
[Rule Engine — 前段ガード]
  5. Health Factor チェック（< 1.6 → HOLD）
  6. クールダウンチェック（10分以内 → HOLD）
  7. 日次上限チェック（30% 超 → HOLD）
        ↓ ガードを通過した場合のみ
[RAG — コンテキスト生成]
  8. POST /knowledge/search でベクトル検索
  9. top_k チャンクをプロンプトに結合
        ↓
[Phase A — AI Judge (Claude Opus 4.6)]
  10. POST /ai/analyze（Claude Opus 4.6）
  11. JSON Schema バリデーション
      → parse 失敗 → HOLD（安全側へ）
  12. action: BUY / SELL → Phase B へ
      action: HOLD → status=skipped で終了
        ↓ BUY / SELL のみ
[Phase B — クロス検証 (GPT-4o)]
  13. GPT-4o でクロス判定（本番環境のみ）
  14. 両 LLM の判断が不一致 → HOLD
        ↓ 合意した場合のみ
[Rule Engine — 後段ガード]
  15. 最大取引量チェック（総資産の 10% 以内）
  16. 緊急停止フラグチェック（OR ロジック、手動停止は上書き不可）
        ↓
[Exchange Execution]
  17. POST /exchange/order（ccxt → Bybit）
  18. status: analyzed に更新
        ↓
[Notification]
  19. Slack / LINE 通知
```

---

## ステップ詳細

### Step 1-4: Knowledge Hub への登録

**エンドポイント:** `POST /knowledge/items`

```json
// URL 種別
{
  "item_type": "url",
  "source_url": "https://example.com/news/article"
}

// テキスト種別
{
  "item_type": "text",
  "title": "市場分析レポート",
  "raw_text": "本日のBTC価格は..."
}
```

**内部処理:**
1. item_type=url → httpx でスクレイピング（`<article>` → `<main>` → `<body>` の優先順位）
2. tiktoken でチャンク分割（デフォルト 512 tokens、オーバーラップ 64 tokens）
3. OpenAI embeddings API でバッチ embedding 生成
4. `knowledge_sources` / `knowledge_documents` / `knowledge_chunks` に INSERT
5. `status = "pending"` で保存

---

### Step 5-7: Rule Engine（前段ガード）

LLM 呼び出し前にルールエンジンで判定。コスト節約と安全性確保が目的。

| ルール                      | 閾値             | 発動時の挙動 |
| --------------------------- | ---------------- | ------------ |
| Health Factor チェック      | HF < 1.6         | HOLD（即時）、LLM 呼び出しなし |
| クールダウンチェック        | Aave 操作後 10 分 | HOLD、待機 |
| 日次取引上限チェック        | 総資産の 30% 超  | HOLD、翌日まで停止 |

---

### Step 8-9: RAG コンテキスト生成

**エンドポイント:** `POST /knowledge/search`

```json
{
  "query": "BTC Federal Reserve 利上げ 価格影響",
  "top_k": 5
}
```

返却された `results[].content` を結合し、AI プロンプトの `context` フィールドに埋め込む。

---

### Step 10-12: Phase A — Claude Opus 4.6 判定

**エンドポイント:** `POST /ai/analyze`

**入力プロンプト構成:**
```
[system]: あなたは金融AI判定エージェントです。JSON のみで回答してください。
[user]:
  context: <RAG で取得したチャンク群>
  query: <ユーザーの分析依頼>
```

**期待する JSON 出力（JSON Schema バリデーション必須）:**
```json
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0〜1.0,
  "reason": "判定理由（200文字以内）",
  "sentiment": "positive" | "negative" | "neutral"
}
```

- **parse 失敗 → 強制 HOLD**（安全側に倒す）
- **HOLD → `status = "skipped"`** で処理終了

---

### Step 13-14: Phase B — GPT-4o クロス判定（本番のみ）

BUY / SELL 判定時のみ実行。staging 環境ではスキップ。

両 LLM が同じ action に合意した場合のみ次ステップへ進む。
不一致の場合は HOLD。

---

### Step 15-16: Rule Engine（後段ガード）

| ルール                      | 閾値             | 発動時の挙動 |
| --------------------------- | ---------------- | ------------ |
| 最大取引量チェック          | 総資産の 10% 以内 | 超過分をカット or HOLD |
| 緊急停止フラグチェック      | OR ロジック      | フラグが立っていたら無条件 HOLD（手動 STOP は上書き不可） |

---

### Step 17-18: Exchange 発注

**エンドポイント:** `POST /exchange/order`

```json
{
  "symbol": "BTC/USDT",
  "side": "buy",
  "amount": 0.01,
  "order_type": "market"
}
```

- プライマリ: Bybit（ccxt 経由）
- バックアップ: OKX（Bybit が利用不可の場合）
- 発注完了後: `status = "analyzed"` に更新

---

### Step 19: 通知

- **Slack:** 取引結果・エラーを #trading-alerts チャンネルへ
- **LINE:** 緊急停止・Health Factor 警告のみ

---

## Knowledge Hub ステータス遷移

```
[登録]
  → pending

[Rule Engine 前段ガード: HF/クールダウン/日次上限に引っかかった]
  → skipped

[Claude Opus: HOLD 判定 or JSON parse 失敗]
  → skipped

[GPT-4o: 不一致]
  → skipped

[処理中にエラー発生]
  → error

[発注完了]
  → analyzed
```

---

## 旧フロー（Notion）との対応表

| 旧フロー                     | 新フロー（Knowledge Hub） |
| ---------------------------- | ------------------------- |
| Notion にニュース URL を貼る | POST /knowledge/items     |
| GET /notion/ingest           | GET /knowledge/items?status=pending |
| NotionNewsItem スキーマ      | KnowledgeItem スキーマ    |
| Notion の Status 更新        | PUT /knowledge/items/{id}/status |
| Notion API                   | PostgreSQL + pgvector     |

---

## 関連ドキュメント

- `docs/09_knowledge_hub_schema.md` — Knowledge Hub スキーマ定義（テーブル・Pydantic・API）
- `docs/05_ai_judgement_rules.md` — AI 判定ルール詳細
- `docs/07_aave_operation_logic.md` — Health Factor / Aave 操作ロジック
- `docs/13_security_design.md` — セキュリティルール（緊急停止・HF 閾値等）
- `docs/04_api_design.md` — 全 API エンドポイント一覧
