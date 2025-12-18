# 02_phase_plan.md  
Ultra AutoTrade – フェーズ計画（DoD 追加版）

---

# Week1：Notion → AI → OctoBot → Aave（基本連携）

### ✔ 完了条件（Definition of Done）
- Notion APIで最低1件取得  
- AI APIレスポンス < 5秒  
- BUY/SELL/HOLD の基本判定成功  
- OctoBot へシグナル送信成功  
- Aaveテストネットで deposit/withdraw 成功  

---

# Week1.5：シミュレーション・バックテスト

### ✔ 完了条件
- 過去ニュース10件で精度80%以上  
- 誤判定の原因メモ  
- しきい値最適化の反映  

---

# Week2：自動化・安定化

### ✔ 完了条件
- 監視＆アラート動作確認  
- レポート自動生成成功  
- 全フロー成功率95%以上  

※ 実装マッピング（Phase5）  
- 監視＆アラート: `MonitoringService` + Aave/OctoBot 連携  
- レポート自動生成: `ReportingService` による日次/週次サマリー  
- 通知インターフェース: `notifications/*` で NotificationMessage / Sender 抽象化  
- 緊急停止時の安全動作: Aave 側での NOOP 保証（ヘルスファクター/緊急停止フラグ連携）