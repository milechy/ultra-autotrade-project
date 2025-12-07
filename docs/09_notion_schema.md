# 09_notion_schema.md
# Notion DB構造

## プロパティ一覧
- URL（text）
- Summary（text）
- Sentiment（select）
- Action（select: BUY/SELL/HOLD）
- Confidence（number）
- Status（select: 未処理 / 処理済）
- Timestamp（date）

## 処理フロー
1. URL貼り付け → Status: 未処理
2. AI解析 → Action更新
3. OctoBotへ送信
4. 完了 → Status: 処理済