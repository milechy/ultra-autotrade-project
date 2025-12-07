# 14_test_strategy.md  
Ultra AutoTrade – テスト戦略

---

# 1. テストの目的
Notion → AI → OctoBot → Aave のフローが  
「誤作動しない」「損失を生まない」「再現性がある」ことを保証する。

---

# 2. テスト構成

- Unit Test（モジュール単体）
- Integration Test（2つ以上の連携）
- Scenario Test（連続動作）
- E2E Test（テストネットでの本番模倣）
- Regression Test（変更の影響がないか）

---

# 3. Unit Test

## 対象
- AI判定処理（文章→BUY/SELL/HOLD）
- Aave SDK 操作（deposit, withdraw）
- Notion APIパーサー
- OctoBotシグナル送信モジュール

## Mock方針
- 外部APIはすべて Mock
- 時系列処理は固定日時を使用

---

# 4. Integration Test

## 対象シナリオ
- Notion → AI  
- AI → OctoBot  
- OctoBot → Aave  

## 成功基準
- 各ステップの遅延 10秒以内
- 95%以上の成功率

---

# 5. Scenario Test
ニュース10件を順に処理し：

- BUY → Aave deposit  
- SELL → Aave withdraw  
- HOLD → 何もしない  

各ニュースの結果が期待通りであること。

---

# 6. E2E Test（テストネット）

テストネット（Goerli / Sepolia）で以下を確認：

- deposit
- borrow
- repay
- withdraw

本番同様のスマートコントラクト動作、gas 計算まで含めて確認。

---

# 7. Regression Test

GitHub PR 時に自動実行：

- AI判定の一括テスト（ニュース50件）
- 全フローの統合テスト

---

# 8. 最低合格ライン（MVP）

- エラー率：5% 以下  
- フロー成功率：95% 以上  
- 判定精度：80% 以上  