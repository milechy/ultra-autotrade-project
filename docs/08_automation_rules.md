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

# 4. スケジューラ連携（cron 実行ルール）

本章では、これまでに定義した自動化ルールを、  
実際のサーバ上でどのようにスケジューラ（cron）に紐付けて実行するかを整理する。

- 実行主体：Linux サーバ上の cron（デプロイユーザ例：`ultra`）
- 実行対象：`scripts/backup.sh` / `scripts/monitor.sh`
- 詳細な crontab 設定例は `docs/18_scheduler_and_cron.md` を参照

## 4.1 ジョブとスクリプトの対応関係

自動化ルールと、実際に呼び出すスクリプトの対応は以下の通りとする。

1. **日次監視・レポート（daily）**
   - 目的：
     - 過去 1 日分の監視イベント / 取引履歴 / Aave 状態を集計し、
       `AutomationReportSummary` を生成・通知する。
   - 実行スクリプト：
     - `scripts/monitor.sh daily`
       - 内部で `python -m app.automation.jobs daily` を呼び出す。
   - 出力：
     - 通知（LINE / Slack など）
     - 日次サマリ（`ReportingService` ベース）

2. **週次監視・レポート（weekly）**
   - 目的：
     - 過去 1 週間分の状態を集計し、長期的な傾向や異常を確認する。
   - 実行スクリプト：
     - `scripts/monitor.sh weekly`
       - 内部で `python -m app.automation.jobs weekly` を呼び出す。
   - 出力：
     - 週次レポート（`ReportPeriod.WEEKLY` 相当）
     - 通知（必要に応じて）

3. **定期バックアップ（backup-only）**
   - 目的：
     - Notion / AI 判定結果 / 取引履歴などを安全なストレージにバックアップする。
   - 実行スクリプト：
     - `scripts/backup.sh`
       - 内部で `python -m app.automation.jobs backup-only` を呼び出す。
   - 出力：
     - バックアップファイル、あるいはバックアップ先ストレージへの書き込み

> 補足：  
> 「死活監視（1分ごと）」などの短周期ヘルスチェックは、  
> 外部監視サービス（例：Ping / Uptime 系）や、単純な `curl /health` ベースの cron ジョブで実装してよい。  
> その具体例は `18_scheduler_and_cron.md` で示す。

## 4.2 推奨スケジュール（論理レベル）

Ultra AutoTrade の論理的な日次 / 週次サイクルは、**Asia/Tokyo タイムゾーン** を基準とする。

- **日次監視・レポート**
  - 実行タイミング：毎日 00:30（前日分を集計）
  - 対象期間：前日 00:00:00〜23:59:59（UTC 換算は実装側が吸収）
- **週次監視・レポート**
  - 実行タイミング：毎週 月曜日 01:00
  - 対象期間：前週 月曜〜日曜の 7 日間
- **定期バックアップ**
  - 実行タイミング：毎日 00:00
  - 対象：直近状態のバックアップ

サーバ OS のタイムゾーンが UTC の場合、  
cron の時間指定は **UTC ベース** となるため、  
Asia/Tokyo と合わせる場合は +9 時間を考慮して設定すること。

## 4.3 環境ごとのジョブ有効化方針

- **ローカル開発環境**
  - 通常は cron による自動実行は行わず、必要に応じて手動実行のみとする。
  - 開発時に動作確認をしたい場合、直接 `scripts/backup.sh` / `scripts/monitor.sh` を叩く。

- **staging 環境**
  - Phase7 時点で、以下のジョブを有効化することを想定する：
    - 毎日 00:00: `scripts/backup.sh`
    - 毎日 00:30: `scripts/monitor.sh daily`
    - 毎週 月曜 01:00: `scripts/monitor.sh weekly`
  - 初期運用では、ログ監視・通知内容の確認を目的とし、閾値や頻度は保守的に設定する。

- **production 環境**
  - 本番フェーズで別途検討・有効化する。
  - 基本的なスケジュールは staging と同一だが、
    - 通知先
    - エラー時のエスカレーション
    などは本番用の運用ルールに従う。

## 4.4 失敗時の扱いとリトライ

- `scripts/backup.sh` / `scripts/monitor.sh` は `set -euo pipefail` により、
  途中でエラーが発生した場合は **非ゼロステータスで異常終了** する。
- cron 実行では、ジョブが失敗しても **次回スケジュールで自然に再試行される** ことを前提とする。
- 連続失敗や重大なエラーは、
  - ログ監視
  - `MonitoringService` / 通知サービス
  により検知し、人間オペレータが介入できるようにする。

cron の具体的な書式（`crontab -e` に書く 1 行ごとの設定例）は、  
`docs/18_scheduler_and_cron.md` に記載する。

---

# 5. 緊急時のAIレポート
- 異常検知時、AI/ルールベースロジックが状況説明レポートを生成  
- レポート内容：
  - 対象期間（daily / weekly）
  - イベント件数（info / warning / alert / critical / emergency）
  - ヘルスファクターの最小値・最大値・直近値
  - 直近の重要イベント（EMERGENCY / CRITICAL / ALERT 優先）
  - 補足ノート（人手 or AI からのコメント欄）

- 実装：
  - `backend/app/automation/emergency_report_service.py` の `EmergencyReportService` が、
    `AutomationReportSummary` と `MonitoringEvent[]` から `EmergencyReport`（title / body）を生成する。
  - 生成されたレポートは、通知（LINE / Slack）や Notion レポートページに再利用できるテキスト形式。
  - 現時点ではテンプレートベースの自然言語生成とし、将来的に LLM へ差し替え可能な構造とする。

> ※ Phase6 で `AutomationReportSummary` → 自然言語レポート生成ロジック (`EmergencyReportService`) まで実装済み。

# 6. 監視メトリクス一覧

本節では、Ultra AutoTrade で監視対象とするメトリクスを一覧化する。  
実際の集計・保存方法（Prometheus / ログ集計ツール / 独自 DB など）は実装に委ねるが、  
**「何をどの閾値で見るか」** は本ドキュメントを基準とする。

## 6.1 メトリクス一覧（論理定義）

| カテゴリ                   | メトリクスID                       | 説明                                                                 | 種別      | 正常レンジ / 目安                           | ALERT / EMERGENCY との関係                          |
|----------------------------|------------------------------------|----------------------------------------------------------------------|-----------|----------------------------------------------|-----------------------------------------------------|
| 死活・レイテンシ           | `backend_http_latency_p95_ms`      | `/health` など代表的な HTTP エンドポイントの p95 レイテンシ（ミリ秒） | gauge     | < 1,000ms                                   | > 10,000ms が一定時間継続で WARNING, > 30,000ms で ALERT（#1 死活監視と同じ） |
| 死活・エラー率             | `backend_http_error_rate_1m`       | HTTP リクエストの 1 分あたりエラー率（5xx / 全体）                  | gauge     | < 1%                                       | 連続 5 分間で > 5% なら ALERT                       |
| フロー成功率               | `news_pipeline_success_rate_1h`    | Notion → AI → OctoBot → Aave の 1 時間あたり成功率                   | gauge     | ≥ 95%                                      | < 90% が続く場合は ALERT                            |
| フロー異常件数             | `news_pipeline_error_count_1h`     | 上記フロー内でのエラー件数（例外・タイムアウトなど）                 | counter   | 0〜少数                                    | 急増（前時間比 X 倍）した場合に WARNING / ALERT     |
| 取引頻度（信号側）         | `signals_per_10min`                | OctoBot から受信したシグナル数（10分あたり）                         | counter   | 通常レンジは運用実績ベース                  | 異常に多い場合は「2. 過剰取引監視」のルールに基づき WARNING / ALERT |
| 取引頻度（実行側）         | `aave_executed_trades_1h`          | 実際に Aave で約定したトレード数（1時間あたり）                      | counter   | 通常レンジは運用実績ベース                  | 異常に多い場合は「2. 過剰取引監視」のクールダウン対象 |
| Aave リスク                | `aave_health_factor_min`           | 対象期間内の Aave Health Factor 最小値                              | gauge     | ≥ 1.8                                     | < 1.8 で WARNING, < 1.6 で EMERGENCY（#3 Aave運用監視と同じ） |
| Aave 現状リスク            | `aave_health_factor_current`       | 現在時点の Aave Health Factor                                       | gauge     | ≥ 1.8                                     | < 1.8 で WARNING, < 1.6 で EMERGENCY                |
| 資産変動                   | `portfolio_value_change_1d_pct`    | ポートフォリオの 1 日あたりの評価額変化率（%）                      | gauge     | ± 20% 以内                                 | 絶対値 > 20% で ALERT（#3 Aave運用監視のルールに対応） |
| 緊急停止フラグ             | `emergency_stop_flag`              | 自動トレード緊急停止フラグ（0: OFF, 1: ON）                          | gauge(0/1)| 0（OFF）が通常                             | 1（ON）の間は EMERGENCY 状態として扱う               |
| 緊急イベント件数           | `emergency_event_count_24h`        | 過去24時間の EMERGENCY レベル MonitoringEvent 件数                  | counter   | 0〜ごく少数                                | 急増した場合はインシデント扱い（Runbook 参照）      |
| バックアップ／ジョブ失敗数 | `automation_job_failure_count_24h` | `monitor_daily` / `monitor_weekly` / バックアップ等のジョブ失敗件数 | counter   | 0                                         | > 0 の場合は WARNING、継続する場合は ALERT          |

> ※ ここでの「通常レンジ」はあくまで目安であり、  
>  実際の値は運用実績を踏まえて調整する。  
>  ただし、閾値（ヘルスファクター 1.8 / 1.6 や 20%/日など）は、  
>  既存のルール（#1〜#3）と **矛盾させないこと**。

## 6.2 MonitoringEvent.level との対応

`MonitoringEvent.level`（info / warning / alert / critical / emergency）と  
メトリクスの関係性は、概ね次のように扱う。

| level       | 典型トリガ例                                      | 代表メトリクス例                         | Runbook 上の対応イメージ                      |
|-------------|---------------------------------------------------|------------------------------------------|-----------------------------------------------|
| info        | 正常系の完了通知、日次/週次レポート生成成功など   | `news_pipeline_success_rate_1h` など     | ログ・レポートとして記録。特に対応不要        |
| warning     | 閾値に近づいてきた状態                           | p95 レイテンシ上昇、軽微なエラー増加     | 運用担当が状況確認。原因調査のトリガ          |
| alert       | 閾値超過だが即時停止までは不要な状態             | `backend_http_latency_p95_ms` > 30s 等   | 優先度高めで調査。必要に応じて一時停止やリトライ |
| critical    | Aave リスク増大、連続エラー多発など、危険水準手前 | `aave_health_factor_min` が 1.6 付近など | 緊急停止フラグ ON を検討。即時エスカレーション |
| emergency   | 緊急停止フラグ ON、または明確な重大インシデント   | `emergency_stop_flag` = 1                | 自動トレード停止。Runbook の緊急対応フローに従う |

> 実装上は、メトリクスの値 → `MonitoringEvent.level` → 通知・レポート  
> の順で情報が伝播する想定とし、  
> 閾値ロジックは **本ドキュメントと Runbook の両方** に明示しておく。

## 6.3 ダッシュボード / レポートとの対応（Phase10）

本節で定義したメトリクスは、Phase10 で実装された  
`MonitoringService` / `ReportingService` / `DashboardSnapshot` により、次のように扱われる。

### 6.3.1 データの流れ（概念）

1. **MonitoringService**
   - 各種 `record_*` メソッドが、しきい値判定と同時に `MonitoringEvent` を発行する。
   - 関連するメトリクスは `MonitoringEvent.metric`（`MetricPoint`）として添付される。
     - 例：
       - レイテンシ: `metric_id=latency_{component}_s`（秒単位）
       - ヘルスファクター: `metric_id=aave_health_factor_current`
       - 資産変動率: `metric_id=portfolio_value_change_1d_pct`

2. **ReportingService**
   - 日次 / 週次の監視レポート生成時に、一定期間内の `MonitoringEvent.metric` を集計し、
     `AutomationReportSummary.metric_aggregates` にまとめる。
   - これにより、レポート本文では「どのメトリクスが閾値を超えたか」を説明しつつ、  
     サマリ部分では集計値（平均・最大など）を確認できる。

3. **DashboardSnapshot（MonitoringService.build_dashboard_snapshot）**
   - ダッシュボード向けには、直近 `lookback` 期間（例: 1 時間）に限定してメトリクスを集計し、
     `DashboardSnapshot.metric_aggregates` に格納する。
   - 各エントリは `MetricAggregate` として管理され、少なくとも次の情報を持つ：
     - `metric_id`
     - `unit`
     - `count`（期間内のサンプル数）
     - `min` / `max` / `avg` / `last`（いずれも `Decimal` または `None`）

### 6.3.2 メトリクス定義との関係

- 本ドキュメントの「6.1 メトリクス一覧（論理定義）」は、  
  **「運用者が見るべき論理メトリクス」** を定義している。
- `MetricPoint.metric_id` および `MetricAggregate.metric_id` は、  
  原則としてこの論理メトリクス ID と整合するように設計するが、
  必要に応じて次のようなパターンも許容する：
  - ダッシュボード上の論理メトリクスを、複数の raw メトリクス（例: `latency_system_s`）から算出する。
  - 実装上は秒単位 (`*_s`) を記録し、ダッシュボード側でミリ秒換算して表示する。

> 方針：  
> - 閾値判定・緊急停止は `MonitoringService` 側の実装（`record_health_factor` / `record_price_change_24h` など）を唯一の基準とする。  
> - ダッシュボードやレポートは、その結果を「可視化するだけ」であり、  
>   追加で独自の判定ロジックを持たないこと。

### 6.3.3 ダッシュボード構成時の注意

- ダッシュボードの各パネルは、可能な限り `metric_id` ベースで定義し、
  本節および「6.1 メトリクス一覧（論理定義）」に矛盾しないようにする。
- 代表的な対応イメージ：
  - Aave リスク系パネル
    - `DashboardSnapshot.metric_aggregates["aave_health_factor_current"]` の `last` / `min` を表示
  - 資産変動率パネル
    - `DashboardSnapshot.metric_aggregates["portfolio_value_change_1d_pct"]` の `last` を表示
  - レイテンシ系パネル
    - `latency_*` 系メトリクスの `avg` / `max` から、`backend_http_latency_p95_ms` 相当の指標を算出して表示

> 実際のダッシュボードツール（Grafana / CloudWatch 等）はプロジェクト外の前提とし、  
> ここでは **「どのメトリクスを、どのように見ればよいか」** のルールのみを定義する。