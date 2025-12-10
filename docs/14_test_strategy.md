# 14_test_strategy.md  
Ultra AutoTrade – テスト戦略

---

# 1. テストの目的

Notion → AI → OctoBot → Aave のフローが  

- 誤作動しない  
- 不要な損失を生まない  
- 同じ入力に対して同じ結果が再現できる  

ことを保証する。

---

# 2. テスト構成（レベル）

- Unit Test（モジュール単体）
  - 例: AI 判定ロジック, Notion クライアント, OctoBot クライアント, Aave 操作ユーティリティ 等
- Integration Test（2つ以上の連携）
  - 例: Notion → AI, AI → OctoBot, OctoBot → Aave
- Scenario Test（連続動作）
  - ニュース複数件を時間順に処理するシナリオテスト
- E2E Test（テストネット）
  - 実際のテストネット上で Aave スマートコントラクトを叩く検証
- Regression Test（回帰テスト）
  - PR 時に自動実行する一括テスト（AI判定・統合フロー）

---

## 2.1 Unit Test 詳細（AI 周り）

- 対象ファイル
  - `backend/tests/test_ai_service.py`  
  - `backend/tests/test_ai_router.py`

  - `backend/tests/test_octobot_client.py`
  - OctoBotClient の初期化、例外クラス（OctoBotHTTPError が OctoBotClientError を継承していること）を確認。
- `backend/tests/test_octobot_service.py`
  - 信頼度しきい値に基づく SKIPPED 判定。
  - 1時間以内の同一アクション回数がしきい値を超えた場合にレート制限で SKIPPED になること。
- `backend/tests/test_octobot_router.py`
  - `/octobot/signal` の 400（count 不整合）を確認。
  - 正常リクエストで 400 以外（200 or 500）が返ることを確認（OctoBot 側はモック/no-op）。

- `test_ai_service.py`  
  - 入力ニュース文（ポジティブ / ネガティブ / 中立）に対して、  
    `TradeAction` が BUY / SELL / HOLD の期待値どおりになるかを確認。  
  - 信頼度スコアが 0〜100 の範囲に収まることを確認。  
  - `docs/05_ai_judgement_rules.md` の条件に沿った境界値テスト（しきい値ギリギリ前後）。

- `test_ai_router.py`  
  - `/ai/analyze` エンドポイントの正常系（200）レスポンスを確認。  
    - モックした `AIService.analyze_items` が返す `AIAnalysisResult` がそのままレスポンスに反映されること。  
  - `AIService.analyze_items` が予期しない例外を投げた場合、  
    ステータスコードが 500 系になることを確認。  
  - バリデーションエラー時に 422 Unprocessable Entity になること。

---

## 2.2 Unit Test 詳細（OctoBot 連携周り）

### 2.2.1 bots.client（OctoBot 外部シグナルAPIクライアント）

- 対象ファイル
  - `backend/tests/test_octobot_client.py`

- 目的  
  OctoBot 外部シグナルAPIへの HTTP 通信が、正常系・異常系ともに想定どおり振る舞うことを保証する。

- 主な観点  
  - 正常系: 2xx レスポンスを受け取った場合、成功として結果が返却されること。  
  - 4xx / 5xx レスポンス: 適切な例外クラスに変換され、上位層（service）でハンドリング可能になっていること。  
  - タイムアウト・接続エラー: 所定の回数リトライした上で、最終的に例外を返すこと。  
  - ログ出力: APIキーなどの機密情報がログに出力されないこと（メッセージをモック／スパイで検証）。

### 2.2.2 bots.service（シグナル生成・送信ロジック）

- 対象ファイル
  - `backend/tests/test_octobot_service.py`

- 目的  
  `AIAnalysisResult` を入力として、過剰取引制限・信頼度しきい値に基づいた  
  「送信 / スキップ / 失敗」の判定が正しく行われることを保証する。

- 主な観点  
  - 信頼度がしきい値以上のシグナルのみ、OctoBot 外部API送信対象となること。  
  - `docs/08_automation_rules.md` で定義された連続トレード制限ルールに抵触するシグナルは「skipped」として扱われること。  
  - client からエラーが返却された場合、「failed」として集計され、詳細メッセージがレスポンスに含まれること。  
  - すべてのシグナルがスキップまたは失敗になる場合でも、サービス層が異常終了せず、集計結果を返すこと。

### 2.2.3 bots.router（/octobot/signal エンドポイント）

- 対象ファイル
  - `backend/tests/test_octobot_router.py`

- 目的  
  `/octobot/signal` エンドポイントの外部仕様（Request/Response・ステータスコード）が  
  `docs/04_api_design.md` の定義と一致していることを保証する。

- 主な観点  
  - 正常なリクエスト → 200 OK とともに、`success_count / skipped_count / failed_count` が整合していること。  
  - bots.service がシグナル送信失敗を返した場合、設計された HTTP ステータス（例: 502）とエラーボディになること。  
  - リクエストボディの形式が明らかに不正（`count` と配列長の不一致など）の場合 → 400 Bad Request。  
  - 必須フィールド欠如や型不一致 → 422 Unprocessable Entity（FastAPI デフォルト）。

---

## 2.3 Unit Test 詳細（Notion / Aave / その他）

- Notion クライアント / ルータ
  - `backend/tests/test_notion_client.py`  
    - Notion API レスポンスのパース・エラーハンドリング。  
  - `backend/tests/test_notion_router.py`  
    - `/notion/ingest` の正常系・エラー系動作。

- Aave 関連（別フェーズで詳細実装）
  - Aave SDK ラッパの deposit / withdraw / borrow / repay の単体テスト。  
  - ガス計算・リトライロジック等。

---

# 3. Unit Test（サマリ）

## 3.1 対象

- AI 判定処理（文章 → BUY/SELL/HOLD）
- Notion API パーサ／クライアント
- OctoBot シグナル送信モジュール（client / service / router）
- Aave SDK 操作（deposit, withdraw, borrow, repay）※実装フェーズに応じて追加

## 3.2 Mock 方針

- 外部 API（Notion / OctoBot / Aave / 価格フィードなど）は **すべて Mock**。  
- 時系列処理は固定日時を使用し、同じテストが何度実行されても同じ結果になるようにする。

## 3.4 Aave 運用ロジックのテスト

### ユニットテスト（`test_aave_service.py`）

- FakeAaveClient を用意し、Aave 実ネットワークには一切アクセスしない
- 検証項目：
  - BUY かつ条件安全 → `DEPOSIT` が 1 回実行される
  - SELL → `WITHDRAW` が 1 回実行される
  - HOLD → クライアント呼び出し無し（NOOP）
  - ヘルスファクター < 閾値 → BUY は NOOP
  - クールダウン時間内の連続トレード → 2 回目以降は NOOP
  - 負の金額 → ValueError を投げる

### API テスト（`test_aave_router.py`）

- FastAPI の `TestClient` を使い `/aave/rebalance` を直接叩く
- AaveService は dependency override でダミー実装に差し替え
- 検証項目：
  - 正常系：200 + `operation=DEPOSIT` など
  - amount が負数 → 422（Pydantic バリデーション）
  - サービス層が ValueError → 400
  - 予期しない例外 → 500

### 統合テストの雛形（`test_flow_with_aave_stub.py`）

- 現時点では `pytest.mark.skip` としてプレースホルダのみ実装
- 将来的に Notion → AI → OctoBot → Aave のフローをすべてモックで接続し、
  「1件のニュースから Aave まで到達する」シナリオを増やす予定

### 監視・自動化まわりのテスト（Phase5）

- `backend/tests/test_automation_monitoring.py`  
  - `MonitoringService` 単体のしきい値判定（応答時間 / ヘルスファクター / 価格変動）。
- `backend/tests/test_automation_emergency_integration.py`  
  - 緊急停止フラグが立っている状態で、`AaveService.execute_rebalance` が  
    ポジションを増やさない（NOOP になる）ことを確認。
- `backend/tests/test_automation_reporting.py`  
  - 直近のイベント／ヘルスファクター履歴から、  
    `AutomationReportSummary` が日次 / 週次で正しく集計されることを確認。
- `backend/tests/test_notifications_service.py`  
  - `LoggingNotificationSender` が severity に応じて適切なログレベルを使うこと。  
  - `CompositeNotificationService` が複数 Sender へファンアウトすること。
- `backend/tests/test_automation_reporting_notifications.py`  
  - `ReportingService.build_notification_message` が  
    サマリ内容に応じて NotificationSeverity / タイトル / 本文を正しく構築すること。

---

# 4. Integration Test

## 4.1 対象シナリオ

- Notion → AI  
  - `/notion/ingest` → `/ai/analyze`
- AI → OctoBot  
  - `/ai/analyze` で生成された `AIAnalysisResult[]` を `/octobot/signal` に渡した際、
    安全弁の適用とシグナル送信の集計（success/skipped/failed）が期待どおりになること。
- OctoBot → Aave  
  - OctoBot シグナル → Aave 操作ユーティリティ（将来フェーズ）

## 4.2 成功基準

- 各ステップの遅延: 10秒以内（開発環境の目安）。
- 95%以上の成功率（ネットワーク障害など一時的要因は別途考慮）。

---

# 5. Scenario Test

ニュース 10件程度を時系列で処理するシナリオテスト：

- BUY → Aave deposit  
- SELL → Aave withdraw  
- HOLD → 何もしない  

を想定シナリオとして、各ニュースの結果が期待どおりであることを確認する。

- 確認観点
  - 過剰取引ルール（短時間に同一アクション連発しない）が守られている。  
  - 緊急停止条件に抵触した場合、システムが適切に処理を止める（`docs/08_automation_rules.md`, `docs/15_rollback_procedures.md` 参照）。

---

# 6. E2E Test（テストネット）

テストネット（Goerli / Sepolia など）で以下を確認：

- deposit
- borrow
- repay
- withdraw

本番同様のスマートコントラクト動作、gas 計算まで含めて確認する。  
E2E テストは頻度を絞り（例: デイリー、リリース前）、コストと安全性のバランスを取る。

---

# 7. Regression Test

GitHub PR 時に自動実行する想定：

- AI 判定の一括テスト（ニュース 50件程度）
- 全フローの統合テスト（モック OctoBot / モック Aave を利用）

PR マージ前に、既存機能が壊れていないことを担保する。

---

# 8. 最低合格ライン（MVP）

- エラー率：5% 以下  
- フロー成功率：95% 以上  
- AI 判定精度：80% 以上  

上記基準を満たした状態を **MVP の最低ライン** とし、  
以降は本番運用やフィードバックを通じて閾値を引き上げていく。