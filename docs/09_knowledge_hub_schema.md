# 09_knowledge_hub_schema.md
# Knowledge Hub スキーマ定義

> **旧 Notion スキーマから移行済み（2026-03）**
> Notion は完全撤去。入力・ストレージ・検索をすべて PostgreSQL + pgvector で完結する。

---

## アーキテクチャ概要

```
ユーザー入力（URL / テキスト）
        ↓  POST /knowledge/items
  KnowledgeSource（メタ情報）
        ↓  1:N
  KnowledgeDocument（生テキスト）
        ↓  1:N
  KnowledgeChunk（チャンク + pgvector embedding）
        ↓  コサイン類似度検索
  POST /knowledge/search → RAG コンテキスト → AI 判定
```

---

## テーブル定義

### 1. `knowledge_sources`

登録されたナレッジアイテムのメタ情報テーブル。

| カラム名       | 型                        | NULL許可 | デフォルト | 説明 |
| -------------- | ------------------------- | -------- | ---------- | ---- |
| `id`           | INTEGER (PK, autoincrement) | No     | —          | プライマリキー |
| `source_url`   | VARCHAR(2048)             | Yes      | NULL       | スクレイピング元 URL（item_type=url の場合） |
| `title`        | VARCHAR(500)              | Yes      | NULL       | アイテムのタイトル |
| `item_type`    | VARCHAR(20)               | No       | `"text"`   | 入力種別: `"url"` / `"text"` |
| `status`       | VARCHAR(20)               | No       | `"pending"` | 処理状態（後述） |
| `quality_score` | FLOAT                    | Yes      | NULL       | コンテンツ品質スコア（0〜100） |
| `created_at`   | TIMESTAMPTZ               | No       | now()      | 作成日時 |
| `updated_at`   | TIMESTAMPTZ               | No       | now()      | 更新日時（onupdate） |

**インデックス:** `status` にインデックスあり（pending フィルタの高速化）

#### status 値

| 値           | 説明 |
| ------------ | ---- |
| `pending`    | 登録済み・embedding 生成済み・AI 判定未実施 |
| `analyzed`   | AI 判定・取引処理完了 |
| `skipped`    | ルールエンジンにより取引スキップ / HOLD 判定 |
| `error`      | 処理中にエラー発生 |

---

### 2. `knowledge_documents`

ソースから取得した生テキスト本文テーブル。

| カラム名     | 型                        | NULL許可 | 説明 |
| ------------ | ------------------------- | -------- | ---- |
| `id`         | INTEGER (PK, autoincrement) | No     | プライマリキー |
| `source_id`  | INTEGER (FK → knowledge_sources.id) | No | 親ソース ID |
| `raw_text`   | TEXT                      | No       | 生テキスト全文 |
| `created_at` | TIMESTAMPTZ               | No       | 作成日時 |

---

### 3. `knowledge_chunks`

チャンク分割された断片と pgvector 埋め込みベクトルのテーブル。

| カラム名      | 型                          | NULL許可 | 説明 |
| ------------- | --------------------------- | -------- | ---- |
| `id`          | INTEGER (PK, autoincrement) | No       | プライマリキー |
| `document_id` | INTEGER (FK → knowledge_documents.id) | No | 親ドキュメント ID |
| `content`     | TEXT                        | No       | チャンクのテキスト内容 |
| `chunk_index` | INTEGER                     | No       | ドキュメント内でのチャンク順序（0始まり） |
| `token_count` | INTEGER                     | No       | チャンクのトークン数（tiktoken 計算） |
| `embedding`   | VECTOR(1536)                | Yes      | pgvector 埋め込みベクトル（OpenAI text-embedding-3-small） |
| `created_at`  | TIMESTAMPTZ                 | No       | 作成日時 |

**pgvector インデックス:** HNSW インデックス（NOT IVFFlat）でコサイン類似度検索

---

## Pydantic スキーマ（API）

### リクエスト: `KnowledgeCreateRequest`

```python
{
    "title": "任意のタイトル",          # Optional[str]
    "item_type": "url" | "text",        # 必須
    "source_url": "https://...",        # item_type=url の場合に必須
    "raw_text": "生テキスト..."         # item_type=text の場合に必須
}
```

### レスポンス: `KnowledgeItem`

```python
{
    "id": 1,
    "source_url": "https://...",
    "title": "タイトル",
    "raw_text": "生テキスト...",
    "status": "pending",
    "chunk_count": 5,
    "item_type": "url",
    "quality_score": 72.5,
    "created_at": "2026-03-10T00:00:00Z",
    "updated_at": "2026-03-10T00:00:00Z"
}
```

### 検索リクエスト: `KnowledgeSearchRequest`

```python
{
    "query": "BTC 価格上昇 Federal Reserve",  # 必須
    "top_k": 5                                  # 1〜20、デフォルト 5
}
```

### 検索レスポンス: `KnowledgeSearchResponse`

```python
{
    "results": [
        {
            "chunk_id": 10,
            "document_id": 3,
            "content": "チャンクテキスト...",
            "similarity": 0.89,
            "source_url": "https://...",
            "title": "タイトル"
        }
    ],
    "count": 1,
    "query": "BTC 価格上昇 Federal Reserve"
}
```

---

## API エンドポイント一覧

| メソッド | パス                              | 説明 |
| -------- | --------------------------------- | ---- |
| POST     | `/knowledge/items`                | アイテム登録（スクレイピング + embedding 生成） |
| GET      | `/knowledge/items?status=pending` | アイテム一覧取得（status フィルタ対応） |
| POST     | `/knowledge/search`               | ベクトル検索（RAG 用） |
| PUT      | `/knowledge/items/{id}/status`    | ステータス更新 |

**認証:** 登録・更新は `editor` ロール必須。参照は `viewer` ロール以上。

---

## テキスト処理仕様

### チャンク分割（tiktoken）

- チャンクサイズ: 設定値 `chunk_size_tokens`（デフォルト 512 tokens）
- オーバーラップ: 設定値 `chunk_overlap_tokens`（デフォルト 64 tokens）
- フォールバック: tiktoken 非対応環境では文字数ベース分割（1 token ≈ 4 chars）

### 埋め込みモデル

- モデル: `text-embedding-3-small`（OpenAI API）
- 次元数: 1536
- バッチ処理: 複数チャンクをまとめて API 呼び出し

### 品質スコア計算（0〜100）

| 項目                     | 満点 | 算出方法 |
| ------------------------ | ---- | -------- |
| テキスト長（log スケール） | 40 点 | log10(length) / log10(5000) × 40（5000文字で満点） |
| チャンク数               | 20 点 | chunk_count × 4（5チャンクで満点） |
| 数値密度                 | 15 点 | 数値マッチ数 × 1.5 |
| 文章数（20文字超）        | 15 点 | 文章数（上限15） |
| 語彙多様性               | 10 点 | ユニーク語 / 総語数 × 10 |

---

## Notion からの移行対応表

| 旧 Notion プロパティ | 旧 型 | 新 Knowledge Hub カラム | 新 型 |
| -------------------- | ------ | ----------------------- | ------ |
| URL                  | URL    | `source_url`            | VARCHAR(2048) |
| Summary              | text   | `raw_text`（documents） | TEXT |
| Sentiment            | select | AI 判定結果（ai モジュール管理） | — |
| Action               | select | AI 判定結果（BUY/SELL/HOLD） | — |
| Confidence           | number | AI 判定結果（confidence） | — |
| Status               | select | `status`                | VARCHAR(20) |
| Timestamp            | date   | `created_at`            | TIMESTAMPTZ |

> **Note:** Sentiment / Action / Confidence は Knowledge Hub ではなく AI 判定モジュール（`app/ai/`）で管理される。

---

## 関連ファイル

- `backend/app/knowledge/models.py` — SQLAlchemy ORM モデル
- `backend/app/knowledge/schemas.py` — Pydantic スキーマ
- `backend/app/knowledge/service.py` — ビジネスロジック（スクレイピング・チャンク・embedding）
- `backend/app/knowledge/router.py` — FastAPI エンドポイント
- `docs/25_workflow_knowledge_hub.md` — E2E ワークフロー詳細
