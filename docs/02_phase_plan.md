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

---

# Phase 2：マルチプロトコル連携（feature/phase2-protocols）

### 実装タスク完了状況

| タスク | 内容 | ステータス |
|---|---|---|
| C-1 | BaseProtocolClient インターフェース（OCP準拠） | ✅ 完了 |
| C-2 | Lido PoC / Pendle PoC 実装 | ✅ 完了 |
| U-09 | AI Optimizer（Expected Net Benefit）実装 | ✅ 完了 |
| A-10 | Risk Engine（ProtocolMonitor / PegMonitor / MaturityManager / CompoundRiskAssessor）実装 | ✅ 完了 |

### ✔ 完了条件（Definition of Done）
- BaseProtocolClient の7抽象メソッドを全プロトコルが実装済み
- Lido / Pendle の MockClient でテスト通過
- AI Optimizer（ENB計算・配分決定）が Risk Engine と統合済み
- 全テスト 1754 passed（feature/phase2-protocols ブランチ）
- フロントエンド: 戦略選択画面（/user/strategies）+ プロトコルヘルスモニター（/admin/protocols）実装済み

### 次のステップ
1. テスター運用完了確認
2. feature/phase2-protocols → dev マージ
3. staging デプロイ
4. E2E テスト（Playwright）実施