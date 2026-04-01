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
- `backend/tests/test_notifications_service.py`  
  - `LoggingNotificationSender` が severity に応じて適切なログレベルを使うこと。  
  - `CompositeNotificationService` が複数 Sender へファンアウトすること。
- `backend/tests/test_automation_reporting_notifications.py`  
  - `ReportingService.build_notification_message` が  
    サマリ内容に応じて NotificationSeverity / タイトル / 本文を正しく構築すること。

- `backend/tests/test_automation_backup_service.py`  
  - `BackupService` が複数のバックアップハンドラを順に実行し、  
    成功件数の集約と `SUCCESS / PARTIAL / FAILURE` 判定を正しく行うこと。  
  - 1つのハンドラが例外を投げても、他のハンドラの実行が継続されること。

- `backend/tests/test_automation_emergency_report_service.py`  
  - `EmergencyReportService.build_emergency_report` が  
    `AutomationReportSummary` と `MonitoringEvent[]` から人間向けレポートを生成できること。  
  - EMERGENCY あり / イベントゼロ / notes ありなどのパターンで、  
    レポート本文に必要な情報（期間・イベント数・重要イベント・ノート）が含まれていること。

- `backend/tests/test_automation_jobs.py`  
  - `run_daily_jobs` / `run_weekly_jobs` が  
    `ReportingService.generate_summary_report` → `build_notification_message` → `NotificationService.send`  
    の流れを1回ずつ実行すること。  
  - `run_backup_only` が渡された `BackupService` の `run_backup()` を1回実行すること。  
  - `run_backup=True` オプション時に、日次/週次ジョブからバックアップが起動されること。

- `backend/tests/test_automation_monitoring.py`
  - しきい値判定に加え、`MonitoringEvent` にメトリクス情報が正しく含まれることを確認する：
    - `metric_id`（例：`backend_http_latency_p95_ms`, `aave_health_factor_current` など）
    - `metric_value`（数値）
    - `metric_unit`（`ms` / `percent` / `ratio` など）
    - 対象コンポーネントやタグ（例：`component=backend`, `component=aave`）
  - `docs/08_automation_rules.md` の「6. 監視メトリクス一覧」で定義された主要メトリクスについて、
    閾値境界前後のケース（正常 / WARNING / ALERT / EMERGENCY）をユニットテストでカバーする。

- `backend/tests/test_automation_reporting.py`
  - 日次 / 週次サマリーレポートに、メトリクスサマリ（例：平均ヘルスファクター、期間内のエラー件数など）が
    含まれることを確認する。
  - EMERGENCY に至った場合は、どのメトリクスが閾値を超えたかがレポート本文に反映されることを確認する。

- `backend/tests/test_automation_reporting.py`
  - 日次 / 週次サマリーレポートに、メトリクスサマリ（例：平均ヘルスファクター、期間内のエラー件数など）が
    含まれることを確認する。
  - EMERGENCY に至った場合は、どのメトリクスが閾値を超えたかがレポート本文に反映されることを確認する。

- `backend/tests/test_automation_reporting.py`
  - 日次 / 週次サマリーレポートに、メトリクスサマリ（例：平均ヘルスファクター、期間内のエラー件数など）が
    含まれることを確認する。
  - EMERGENCY に至った場合は、どのメトリクスが閾値を超えたかがレポート本文に反映されることを確認する。
  - Phase10 では、`AutomationReportSummary.metric_aggregates` に対して、
    `latency_*` や `portfolio_value_change_1d_pct`、`aave_health_factor_current` などの代表的メトリクスが
    正しく集計されていることを確認するテストを追加する。

- `backend/tests/test_automation_dashboard_view.py`
  - `MonitoringService.build_dashboard_snapshot` により、ダッシュボード向けスナップショット
    （`DashboardSnapshot`）が期待どおりに構成されることを確認する：
    - `generated_at` / `period_start` / `period_end` が、テストで固定した現在時刻と `lookback` に整合している。
    - 対象期間内の `MonitoringEvent.metric` から、`metric_aggregates` に `count` / `min` / `max` / `avg` / `last` が
      正しく集計されている（範囲外のイベントは含まれない）。
    - `AutomationStatus` の情報（`is_trading_paused` / `last_health_factor` /
      `last_price_change_24h` / `last_event_level` / `emergency_reason` など）が、
      `DashboardSnapshot.status` にそのまま反映されている。
  - ダッシュボード UI 自体はツール依存であるため、本プロジェクトでは
    「バックエンドが提供するスナップショット構造」が契約となる。
    ツール変更時も、このテスト群が通っている限り、ダッシュボードに必要な情報は提供されているとみなす。

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

# 7. Browser UI Test（Claude in Chrome）

UIアップデート時に `claude --chrome` を使い、実際のブラウザ上でUI/UXを検証する。
実行タイミング: UIアップデート時のみ。バックエンドのみの変更時は不要。
注意: 複数プロジェクトで同時に `/chrome` を使うとバッティングする → 1プロジェクトずつ実行。

---

# 8. Codex Review（PR前コードレビュー）

## 概要
OpenAI Codex Plugin for Claude Code (`codex-plugin-cc`) を使い、PR作成前にコードレビューを実行。

## Review Gate: 常時OFF
使用量を大量消費するため常時OFF: `/codex:setup --disable-review-gate`

## コスト最適化運用ルール
| シナリオ | コマンド | 頻度 |
|---------|---------|------|
| PR作成前の標準レビュー | `/codex:review --base main --background` | 1日1-2回 |
| Aave/セキュリティ変更時 | `/codex:adversarial-review --base main --background` | 対象変更時のみ |
| バグ調査委任 | `/codex:rescue investigate <問題>` | 必要時のみ |
| 進捗確認 | `/codex:status` → `/codex:result` | レビュー実行後 |

## Playwright / Claude in Chrome / Codex Review の使い分け
| 観点 | Playwright | Claude in Chrome | Codex Review |
|------|-----------|-----------------|--------------|
| 目的 | 機能の回帰テスト | UI/UXユーザビリティ検証 | コード品質・セキュリティ |
| 実行タイミング | CI/CD（毎PR） | UI変更時のみ | PR作成前（1日1-2回） |
| 自動化 | 完全自動 | 半自動 | 手動トリガー |
| コスト | CI実行時間のみ | Claude Code使用量 | Codex/OpenAI使用量 |

---

# 9. Regression Test

GitHub PR 時に自動実行する想定：

- AI 判定の一括テスト（ニュース 50件程度）
- 全フローの統合テスト（モック OctoBot / モック Aave を利用）

PR マージ前に、既存機能が壊れていないことを担保する。

---

# 10. テスト実行順序（全体フロー）

1. pytest（自動） — Unit + Integration + Scenario。CI/CDで毎PR実行。カバレッジ80%+必須
2. Playwright E2E（自動） — smoke test。CI/CDで毎PR実行
3. 孤立コード検出（PR前） — 新モジュール追加時・DeFi安全系変更時は必須
4. Codex Review（手動トリガー） — PR作成前に `/codex:review --base main --background`
5. Claude in Chrome（半自動） — UIアップデート時のみ
6. 手動UIテスト（最後） — iPhone MetaMask / PCブラウザでの実機確認

---

# 11. 孤立コード検出（Dead Code / Disconnected Safety Scan）

## 概要

爆速開発では「実装したが配線を繋ぎ忘れた」安全装置が発生しやすい。pytest/Playwright/Chromeは**動いているコードのバグ**を検出するが、**呼ばれていないコードの孤立**は検出できない。本スキャンはその隙間を埋める。

## 検出対象

| カテゴリ | 代表ファイル | チェック観点 |
|---|---|---|
| 安全装置 | `automation/stress_controller.py` | SAFE_MODE/HARD_STOP がworkflowから呼ばれているか |
| ストレス制御 | `automation/monitoring_service.py` | `record_price_change_24h` が実際に呼ばれているか |
| リスクエンジン | `protocols/risk/` | RiskEngine/Scorerがoptimizer等から参照されているか |
| 退避ロジック | `protocols/risk/auto_evacuate.py` | `execute_evacuation` がworkflowから呼ばれているか |
| AI/Optimizer | `ai/optimizer/` | アロケーターが実際の判定フローに接続されているか |
| 監視・通知 | `automation/monitoring_service.py` | アラートメソッドが定期ジョブから呼ばれているか |

## 実行タイミング

- **PR作成前**（Codex Review前に実行）— 新モジュール追加時は必須
- **大量タスク一括完了後** — 爆速開発後は特にリスクが高い
- **DeFi安全系の変更時** — `aave/`, `automation/`, `protocols/` の変更時

## 実行方法（Claude Codeプロンプト）

```
プロジェクト全体で「実装されているが呼ばれていない」孤立コードを検出して。
重点チェック対象: backend/app/aave/, automation/, protocols/, ai/
方法: 各モジュールのpublicクラス/関数をリストアップ → grep -r でアプリコード内（tests/除外）の参照確認 → 参照0件=孤立
出力: | ファイル | クラス/関数 | アプリコードからの参照 | 状態(孤立/接続済み) |
```

## 検出後の対応優先度

| 優先度 | カテゴリ | 対応 | 期限 |
|---|---|---|---|
| **P0** | 安全装置系（emergency, stress, circuit_breaker） | 即修正（workflow.py/scheduled_tasks.pyに配線） | 当日 |
| **P1** | リスク管理系（risk, health_factor, limit, cooldown） | 1-2日以内に修正 | 翌営業日 |
| **P2** | ユーティリティ系（helper, util） | 将来使用予定なら許容、不要なら削除 | 次スプリント |

## 実際の検出事例（2026-04-01）

| 孤立コード | ファイル | 修正内容 | 優先度 |
|---|---|---|---|
| `StressController.evaluate()` | `automation/stress_controller.py` | `workflow.py` の `process_pending_knowledge()` 冒頭に接続 | P0 |
| `record_price_change_24h()` | `automation/monitoring_service.py` | `scheduled_tasks.py` の定期ジョブから呼び出し | P0 |
| PENDLE_YT 配分キャップ | `ai/optimizer/` | constraints に永続化するよう修正 | P1 |
| `execute_evacuation()` | `protocols/risk/auto_evacuate.py` | リスクエンジン連携として接続 | P0 |

## pytest/Playwright/Chrome/Codex/孤立検出の使い分け

| ツール | 検出できるもの | 検出できないもの |
|---|---|---|
| pytest | 実装バグ、ロジック誤り、型エラー | 呼ばれていないコード |
| Playwright E2E | UIフロー破綻、API疎通 | バックエンドの未接続ロジック |
| Claude in Chrome | 表示崩れ、UX問題 | コードレベルの孤立 |
| Codex Review | コード品質、セキュリティ | 動的な呼び出しパス |
| **孤立コード検出** | **未配線の安全装置・監視ロジック** | **実行時バグ** |

---

# 12. 最低合格ライン（MVP）

- エラー率：5% 以下  
- フロー成功率：95% 以上  
- AI 判定精度：80% 以上  

上記基準を満たした状態を **MVP の最低ライン** とし、  
以降は本番運用やフィードバックを通じて閾値を引き上げていく。

---

## フロントエンド（運用ダッシュボード）

本フェーズでは、フロントエンドは **読み取り専用** のため、テストは最小構成とする。

### 目的

- 既存 API 契約（`AutomationStatus` / `DashboardSnapshot` / `AutomationReportSummary`）と整合すること
- API 失敗時に運用者が原因追跡できるエラー表示になっていること

### 推奨テスト

- スモーク（手動/自動どちらでも可）
  - `/dashboard/automation` が 3 API を呼び出し、表示できる
  - `/dashboard/reports` が最新レポートを表示できる
- CI での最低限（将来タスク）
  - Playwright 等でページロードと主要DOMの存在を確認（契約変更なし前提）

## Automation APIs – 初期状態テスト

- データが0件でも 500 を返さないこと
- dashboard / reports は「空構造」を返す
- latest report は DAILY を既定 period とする
