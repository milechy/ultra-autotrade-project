## プロパティ一覧
- URL（text or URL）
- Summary（text）
- Sentiment（select）
- Action（select: BUY/SELL/HOLD）
- Confidence（number）
- Status（select: 未処理 / 処理済）
- Timestamp（date）

## 内部モデル（NotionNewsItem）との対応

Phase1 では、Notion API から取得したレコードを  
`backend/app/notion/schemas.py` の `NotionNewsItem` として扱う。

| Notionプロパティ | 型             | Notionの例                                     | 内部フィールド            | 備考 |
| ---------------- | -------------- | ---------------------------------------------- | ------------------------- | ---- |
| URL              | URL / text     | `https://example.com/news`                     | `url: str`                | 空の場合はレコードをスキップ（必須扱い） |
| Summary          | text           | 「○○企業が△△を発表…」                        | `summary: str \| None`    | rich_text / title から plain_text を抽出 |
| Sentiment        | select         | `Positive`, `Negative`, `Neutral`              | `sentiment: str \| None`  | select.name を使用 |
| Action           | select         | `BUY`, `SELL`, `HOLD`                          | `action: str \| None`     | AI解析後に設定予定 |
| Confidence       | number         | `78`                                           | `confidence: float \| None` | 0〜100を想定 |
| Status           | select         | `未処理`, `処理済`                             | `status: str \| None`     | Phase1では「未処理」のみ取得対象 |
| Timestamp        | date           | `2025-01-01T12:34:56+00:00`                    | `timestamp: datetime \| None` | date.start を ISO8601 として扱う |

### Notion APIレスポンスとのマッピング仕様

- URL / Summary は、Notion の `url` / `rich_text` / `title` からプレーンテキストを抽出する。
- select 型は、`{ "select": { "name": "..." } }` の `name` をそのまま使用する。
- number 型は `number` の値を `float` に変換して使用する。
- date 型は `date.start` を ISO8601 文字列として受け取り、内部では `datetime` に変換する。

## 処理フロー

1. ユーザーが Notion にニュースURLを貼り付ける  
   - URL プロパティに値を設定  
   - Status を「未処理」にする
2. /notion/ingest  
   - Status が「未処理」のレコードのみを Notion API から取得  
   - 上記のマッピング仕様に従って `NotionNewsItem` に変換  
   - AI解析フェーズ（/ai/analyze）へ渡すデータとする
3. AI解析 → Action / Confidence / Summary / Sentiment を更新（Phase2以降）
4. OctoBotへ送信
5. 完了 → Status を「処理済」に更新（Phase2以降）
