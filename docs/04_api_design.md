# 04_api_design.md
# API設計書

## API一覧

### 1. /notion/ingest
Notionから「未処理(Status: 未処理)」のニュースレコードを取得し、  
AI解析フェーズ（/ai/analyze）へ渡すためのデータ構造で返す。

- Method: POST
- Path: `/notion/ingest`
- 認証: （Phase1時点では未実装 / 今後追加予定）
- 用途: Notion → AI の入口となるAPI

### 2. /ai/analyze

ニュースを解析し、売買アクション（BUY / SELL / HOLD）と信頼度などを返す。

- Method: POST
- Path: `/ai/analyze`
- 認証: （Phase2時点では未実装 / 今後追加予定）
- 用途: Notion から取得したニュース（`NotionNewsItem`）を AI に渡し、売買判定を得るための API

#### リクエスト

- Content-Type: `application/json`
- Body スキーマ: `AIAnalysisRequest`

```json
{
  "items": [
    {
      "id": "page-1",
      "url": "https://example.com/news1",
      "summary": "The company reported record profit and strong growth.",
      "sentiment": null,
      "action": null,
      "confidence": null,
      "status": "未処理",
      "timestamp": null
    }
  ]
}

フィールド	型	説明
items	NotionNewsItem[]	解析対象ニュースの配列。/notion/ingest と同じ形式
NotionNewsItem の詳細な定義は docs/09_notion_schema.md を参照。
通常は /notion/ingest のレスポンスの items をそのまま渡す。
レスポンス（200 OK）
Body スキーマ: AIAnalysisResponse

{
  "results": [
    {
      "id": "page-1",
      "url": "https://example.com/news1",
      "action": "BUY",
      "confidence": 80,
      "sentiment": "positive",
      "summary": "The company reported record profit and strong growth.",
      "reason": "好材料が多く、市場にポジティブな影響が見込まれるため BUY 判定としました。",
      "timestamp": "2025-12-07T08:09:35.007682Z"
    }
  ],
  "count": 1
}

| フィールド   | 型                  | 説明                            |
| ------- | ------------------ | ----------------------------- |
| results | AIAnalysisResult[] | 各ニュースに対する AI 判定結果の配列          |
| count   | integer            | `results` の件数（`len(results)`） |

##### `AIAnalysisResult` スキーマ

| フィールド      | 型               | 説明                                                    |
| ---------- | --------------- | ----------------------------------------------------- |
| id         | string          | 入力 `NotionNewsItem.id` をそのまま引き継ぐ                      |
| url        | string          | 対象ニュースの URL                                           |
| action     | string          | `BUY` / `SELL` / `HOLD` のいずれか                         |
| confidence | integer         | 信頼度スコア（0〜100）。閾値は `docs/05_ai_judgement_rules.md` を参照 |
| sentiment  | string          | ニュース全体のセンチメント（例: `positive` / `negative` / `neutral`） |
| summary    | string          | ニュース内容の要約（入力 summary を補正またはそのまま利用）                    |
| reason     | string          | 当該アクションになった理由の短い説明（日本語）                               |
| timestamp  | string(ISO8601) | 判定実施時刻（UTC, 例: `2025-12-07T08:09:35.007682Z`）         |

#### エラーレスポンス（概要）

* 422 Unprocessable Entity

  * 条件: リクエスト JSON がスキーマと一致しない場合（必須項目の欠落、型不一致など）
  * 例: `items` が配列でない / `id` が string でない 等

* 500 Internal Server Error

  * 条件: AIService 内での予期しない例外（LLM 呼び出し失敗、想定外のエラーなど）
  * 備考: Phase2 実装では、内部例外は FastAPI の例外ハンドリングを通じて 500 として返却される。

````

---

## 2. `docs/03_directory_structure.md` 修正案

### 対象

- ファイル: `docs/03_directory_structure.md`
- セクション: `backend/app/` 配下のツリーのうち `ai/` 行

### 修正方針（概要）

- 実際に実装された `backend/app/ai/` 配下のファイル構成を明示。
- AI モジュールの責務が一目で分かるようにする。

### 具体的な修正文案

> 既存の `│ │ ├── ai/                     # AI解析ロジック（Phase2以降）` を、以下のブロックに置き換え

```markdown
project root/
├── backend/
│ ├── app/
│ │ ├── main.py                 # FastAPIエントリーポイント
│ │ ├── ai/                     # AI解析ロジック（Phase2）
│ │ │ ├── __init__.py           # AIモジュールパッケージマーカー
│ │ │ ├── schemas.py            # AIAnalysisRequest/Response, AIAnalysisResult, TradeAction 定義
│ │ │ ├── service.py            # LLM呼び出し＋ルールベース判定ロジック（BUY/SELL/HOLD 判定）
│ │ │ └── router.py             # /ai/analyze エンドポイント定義
│ │ ├── notion/                 # Notion連携モジュール（Phase1）
│ │ │ ├── __init__.py           # Notion連携パッケージマーカー
│ │ │ ├── config.py             # Notion API設定（環境変数読み取り）
│ │ │ ├── client.py             # Notion APIクライアント（HTTP通信）
│ │ │ ├── service.py            # Notionレコード取得・内部モデル変換サービス層
│ │ │ ├── schemas.py            # NotionNewsItem / NotionIngestResponse スキーマ
│ │ │ └── router.py             # /notion/ingest エンドポイント定義

### 3. /octobot/signal

AI が出した判定結果（AIAnalysisResult相当）をもとに、OctoBot 外部シグナルAPIへ送るための窓口。

- Method: `POST`
- Path: `/octobot/signal`

#### 3.1 Request

```json
{
  "signals": [
    {
      "id": "string",              // シグナルの一意なID（NotionレコードIDなど）
      "url": "string | null",      // ニュースURL（任意）
      "action": "BUY | SELL | HOLD",
      "confidence": 85,            // 0〜100
      "reason": "string",          // なぜそのアクションになったか
      "timestamp": "2025-01-01T00:00:00Z"
    }
  ],
  "count": 1                        // signals配列の件数（整合チェック用）
}
count と signals.length が一致しない場合、400 Bad Request。

3.2 Response

{
  "success_count": 1,              // OctoBotヘの送信成功件数
  "skipped_count": 0,              // 安全弁によりスキップされた件数
  "failed_count": 0,               // 送信エラー件数
  "details": [
    {
      "id": "string",
      "status": "sent | skipped | failed",
      "message": "string | null"   // エラー内容やスキップ理由
    }
  ]
}

- 200: リクエスト自体は正常に処理された（success/skipped/failed の内訳は details 参照）。
- 400: count と signals.length が不整合など、クライアント入力エラー。
- 500: サーバ内部エラー（OctoBot APIのエラーなど詳細はログで追跡）。

### 4. /aave/rebalance
BUY/SELL/HOLDに応じて資産操作。

### 5. /report/daily
日次レポート生成。

#### リクエスト

- Body: なし（Phase1時点ではリクエストボディ不要）
- Queryパラメータ: なし（将来、件数制限やページングを追加する余地あり）

#### レスポンス

- HTTP 200 OK

```json
{
  "items": [
    {
      "id": "ページID",
      "url": "https://example.com/news",
      "summary": "ニュースの要約テキスト",
      "sentiment": "Positive",
      "action": "BUY",
      "confidence": 78.0,
      "status": "未処理",
      "timestamp": "2025-01-01T12:34:56+00:00"
    }
  ],
  "count": 1
}

#### レスポンススキーマ

* `items`: NotionNewsItem の配列
* `count`: `items` の件数（int）

##### NotionNewsItem

| フィールド名     | 型           | 説明                                                    |
| ---------- | ----------- | ----------------------------------------------------- |
| id         | string      | NotionページID                                           |
| url        | string      | ニュースURL（必須／空の場合は内部的にスキップされる）                          |
| summary    | string|null | ニュース本文の要約（Notionの Summary プロパティ）                      |
| sentiment  | string|null | Sentiment select の name（例: Positive/Negative/Neutral） |
| action     | string|null | Action select の name（例: BUY/SELL/HOLD）                |
| confidence | number|null | 信頼度スコア（0〜100）                                         |
| status     | string|null | Status select の name（例: 未処理 / 処理済）                    |
| timestamp  | string|null | Timestamp date の start（ISO8601文字列）                    |

#### エラーレスポンス（概要）

* 502 Bad Gateway

  * 条件: Notion API 呼び出し失敗（ネットワークエラー / 4xx,5xx）
  * 例: Notion API キー不正、権限不足、タイムアウト など

* 500 Internal Server Error

  * 条件: 上記以外の予期しないエラー