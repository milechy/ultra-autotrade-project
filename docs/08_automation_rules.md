# 08_automation_rules.md  
Ultra AutoTrade – 自動化ルール（アラート閾値追加）

---

# 1. 死活監視（1分ごと）
```
応答時間 > 10秒 → 警告  
応答時間 > 30秒 → アラート  
```

---

# 2. 過剰取引監視

（既存のルールに加えて）

- Aave へのトレード間隔ルール：
  - 同一ウォレットからの `/aave/rebalance` 実行は **10分に1回まで**
  - 直近トレードから 10分未満のリクエストは
    - サービス層で `NOOP (status=skipped)` として処理
    - ログに「cooldown によりスキップ」と明示的に残す

これにより「AIが暴走して BUY を連打する」ケースでも、  
Aave 側のポジション増加ペースを機械的に抑制する。

---

# 3. Aave運用監視
```
ヘルスファクター < 1.8 → 警告  
ヘルスファクター < 1.6 → 緊急停止  
資産変動 > 20%/日 → アラート

# 3.1 緊急停止ルール

- ヘルスファクター < 1.8 → 警告  
- ヘルスファクター < 1.6 → 緊急停止  
- 資産変動 > 20%/日 → アラート  

※ Phase5 実装状況  
- `backend/app/automation/monitoring_service.py` の `MonitoringService` にて、  
  上記しきい値に基づく `MonitoringEvent` 発行と `is_trading_paused` 制御を実装済み。  
- `backend/app/aave/service.py` の `AaveService` が `MonitoringService` を参照し、  
  緊急停止中は BUY/DEPOSIT 系のトレードを NOOP として扱う。  
```

---

# 4. 自動バックアップ
- 毎日0時に Notion→AI→取引履歴をバックアップ  

---

# 5. 緊急時のAIレポート
- 異常検知時、AIが状況説明レポートを生成  

※ Phase5 時点  
- 緊急時のサマリーデータ（イベント分布・ヘルスファクターなど）は  
  `AutomationReportSummary`（`backend/app/automation/schemas.py`）として集計可能。  
- そこから自然言語レポートを生成する AI ロジックは **次フェーズ以降** の実装対象とする。
