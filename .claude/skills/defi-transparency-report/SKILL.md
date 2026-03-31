---
name: defi-transparency-report
description: Generate partner-facing update reports and communications for Ultra AutoTrade. Use when creating version update documents, partner progress reports, feature explanations, or cost estimation documents.
---

# Partner Report Generation Skill

## When to Use
- パートナーへのアップデート報告
- 新機能の説明資料
- コスト試算資料
- テスト結果の共有

## Target Audience
- 仮想通貨に詳しいがITリテラシーは低い
- 専門用語は避け、比喩を使う
- 表とビジュアルで伝える

## Writing Rules

1. **専門用語 → 平易な日本語**
   - Health Factor → 「安全度スコア」
   - Utilization Rate → 「借入率」
   - Rebalance → 「資産の調整」

2. **構成テンプレート**
   ```
   ## 今回のアップデート
   ## 安全性の状況
   ## 数字で見る進捗
   ## 次のステップ
   ```

3. **数字は具体的に**
   - 「テスト ○○件全通過」
   - 「コンソールエラー0件」
   - 「Safety Score: XX点（注意/良好/優秀）」

4. **絶対にやらないこと**
   - 利回りの保証・約束
   - 「AIがやるから安心」
   - 技術的な実装詳細の羅列

## Safety Score の説明方法
| スコア | ラベル | 色 | 説明 |
|--------|--------|-----|------|
| 80+ | 優秀 | 緑 | 安全に運用できる状態 |
| 60-79 | 注意 | 黄 | 監視が必要な状態 |
| 0-59 | 危険 | 赤 | 運用を停止すべき状態 |
