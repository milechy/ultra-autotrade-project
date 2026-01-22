# 18_scheduler_and_cron.md
Ultra AutoTrade – スケジューラ & cron 設定ガイド

本ドキュメントは、Ultra AutoTrade の各種自動ジョブを  
Linux サーバの cron で実行するための設定例をまとめたものです。

- 対象：
  - `scripts/backup.sh`
  - `scripts/monitor.sh`
  - シンプルな HTTP ヘルスチェック（`/health`）
- 想定環境：
  - Linux（Debian / Ubuntu）
  - デプロイユーザ例：`ultra`
  - タイムゾーン：可能であればサーバ自体を `Asia/Tokyo` に設定

---

## 1. ジョブ一覧と目的

### 1.1 バックアップジョブ（backup_daily）

- スクリプト：`scripts/backup.sh`
- 目的：
  - Notion / AI 判定結果 / 取引履歴など、重要データの定期バックアップ
- 実行タイミング（推奨）：
  - 毎日 00:00（Asia/Tokyo 基準）
- 備考：
  - 失敗時はログを確認し、必要に応じて手動再実行する

### 1.2 日次監視・レポートジョブ（monitor_daily）

- スクリプト：`scripts/monitor.sh daily`
- 目的：
  - 過去 1 日分の監視イベントを集計し、日次レポート・通知を生成する
- 実行タイミング（推奨）：
  - 毎日 00:30（バックアップ完了後）
- 備考：
  - 期間の切り方は `ReportingService` / `ReportPeriod.DAILY` に従う

### 1.3 週次監視・レポートジョブ（monitor_weekly）

- スクリプト：`scripts/monitor.sh weekly`
- 目的：
  - 過去 1 週間分の状態を集計し、長期の傾向を把握する
- 実行タイミング（推奨）：
  - 毎週 月曜日 01:00
- 備考：
  - 前週（月〜日）のデータを対象とする想定

### 1.4 ヘルスチェックジョブ（health_check）

- コマンド例：`curl http://localhost:8000/health`
- 目的：
  - FastAPI バックエンドのヘルスチェック（HTTP レベル）を 1 分間隔で監視
- 実行タイミング（推奨）：
  - 毎分 1 回
- 備考：
  - 簡易的な監視として、外部サービス（UptimeRobot 等）と併用してもよい

---

## 2. 推奨スケジュール（一覧）

| ジョブ名           | 種別          | スクリプト / コマンド                        | 推奨タイミング（Asia/Tokyo） | 備考                            |
|--------------------|---------------|-----------------------------------------------|------------------------------|---------------------------------|
| `backup_daily`     | バックアップ  | `scripts/backup.sh`                           | 毎日 00:00                    | データ保全                      |
| `monitor_daily`    | 日次レポート  | `scripts/monitor.sh daily`                    | 毎日 00:30                    | 前日分の集計                    |
| `monitor_weekly`   | 週次レポート  | `scripts/monitor.sh weekly`                   | 毎週 月曜 01:00               | 前週分の集計                    |
| `health_check`     | 死活監視      | `curl http://localhost:8000/health` など      | 毎分                          | HTTP レベルの生存確認           |

サーバのタイムゾーンが UTC の場合は、上記時刻から 9 時間引いた時間を cron に設定する。

---

## 3. staging 環境向け crontab 設定例

以下は、staging サーバ上で `ultra` ユーザの crontab に設定する例である。

### 3.1 前提

- プロジェクトルート：`/opt/ultra-autotrade`
- ログディレクトリ：`/var/log/ultra`（存在しなければ事前に作成）
  ```bash
  sudo mkdir -p /var/log/ultra
  sudo chown ultra:ultra /var/log/ultra

### 3.2 crontab 設定例（crontab -e）

# Ultra AutoTrade (staging) cron jobs
# タイムゾーン: サーバローカル（可能なら Asia/Tokyo）

# 1) HTTP ヘルスチェック（毎分）
* * * * * cd /opt/ultra-autotrade && curl -fsS http://localhost:8000/health \
  >> /var/log/ultra/healthcheck.log 2>&1

# 2) 毎日 00:00 にバックアップ実行
0 0 * * * cd /opt/ultra-autotrade && ./scripts/backup.sh \
  >> /var/log/ultra/backup_daily.log 2>&1

# 3) 毎日 00:30 に日次監視・レポート実行
30 0 * * * cd /opt/ultra-autotrade && ./scripts/monitor.sh daily \
  >> /var/log/ultra/monitor_daily.log 2>&1

# 4) 毎週 月曜 01:00 に週次監視・レポート実行
0 1 * * 1 cd /opt/ultra-autotrade && ./scripts/monitor.sh weekly \
  >> /var/log/ultra/monitor_weekly.log 2>&1

注意:
cd /opt/ultra-autotrade によってプロジェクトルートへ移動してからスクリプトを実行している。
スクリプトには実行権限（chmod +x scripts/*.sh）を付けておくこと。

### 4. エラー時の扱いと再実行
4.1 スクリプト側の挙動
- scripts/backup.sh / scripts/monitor.sh は set -euo pipefail により、
途中でエラーが発生した場合は 即座に異常終了 し、終了ステータスは非ゼロとなる。
- cron から見ると「ジョブ失敗」として扱われる。

## 4.2 再実行戦略
- Phase7 時点では、専用のリトライスクリプトは用意しない。
- 再実行は以下のいずれかで行う：
 - 次のスケジュール時刻に、cron が自動で再実行する
 - オペレータがサーバにログインして手動実行する
  - 例：cd /opt/ultra-autotrade && ./scripts/backup.sh

連続して失敗している場合は、ログを確認し、
必要に応じて緊急停止フラグやロールバック手順（15_rollback_procedures.md）を検討する。

## 4.5 緊急停止フラグと自動ジョブの関係

Ultra AutoTrade では、致命的な異常や想定外の挙動が検知された場合、  
「緊急停止フラグ（emergency stop）」を ON にすることで **自動トレードを停止** できる。

### 4.5.1 緊急停止フラグ ON 時に止まるもの / 止まらないもの

- **停止するもの（またはブロックされるもの）**
  - 新規のトレード実行（Aave でのポジション変更）
  - OctoBot シグナルに応じた自動ポジション調整
  - AI 判定結果に基づくリスクの高い自動アクション

- **停止しないもの（継続するもの）**
  - 監視ジョブ（`scripts/monitor.sh`）
    - 異常状態の観測・記録・通知
  - バックアップジョブ（`scripts/backup.sh`）
    - 状態のスナップショット取得
  - ログ出力
    - 障害原因を特定するための情報蓄積

> 方針：  
> 「危険なアクション（トレード）」は即停止するが、  
> 「観測・記録・バックアップ」は止めないことで、  
> 後から原因を追える状態を維持する。

### 4.5.2 緊急停止フラグが ON になるトリガ例

緊急停止フラグは、以下のような条件で ON になることを想定する。

- Aave の Health Factor が閾値を大きく割り込んだ場合
- 短時間に異常な数のトレード要求が発生した場合
- 外部サービス（OctoBot / RPC など）が長時間ダウンしている場合
- 開発者・運用者が手動で「危険」と判断した場合

具体的な判定ロジック・閾値は、`MonitoringService` / `EmergencyReportService` の実装・  
および `05_ai_judgement_rules.md` などのルール定義に従う。

### 4.5.3 緊急停止フラグ ON 時の運用フロー（高レベル）

1. **通知を受け取る**
   - 緊急停止フラグが ON になった時点で、通知チャネル（LINE / Slack など）にアラートが送信される。

2. **状態を確認する**
   - `/health` エンドポイント、監視レポート、ログを確認し、  
     どのコンポーネントで問題が起きているかを把握する。

3. **必要に応じてロールバック / デプロイ停止を行う**
   - コードの変更が原因と疑われる場合は、`15_rollback_procedures.md` に従いロールバックを検討する。

4. **原因が解消されたことを確認する**
   - 再度ヘルスチェック、テストトレード、OctoBot との連携確認などを行う。

5. **緊急停止フラグを OFF にする**
   - 問題が解消されたと判断したら、緊急停止フラグを OFF にして自動トレードを再開する。
   - 誰が OFF にしてよいか（権限）は、`19_operations_runbook.md` で運用ルールとして定義する。

緊急停止フラグの実際の保持場所（例：Notion プロパティ、設定テーブルなど）は、  
アプリケーション実装および `09_notion_schema.md` の定義に従う。

### 5. ログ出力とローテーション

## 5.1 ログファイルの場所
本ドキュメントでは、以下のログファイルを想定している：
- /var/log/ultra/healthcheck.log
- /var/log/ultra/backup_daily.log
- /var/log/ultra/monitor_daily.log
- /var/log/ultra/monitor_weekly.log
これらはすべて ultra ユーザが書き込み可能である必要がある。

## 5.2 ログローテーション（方針）
- 長期間ログを残し続けるとディスクを圧迫するため、
OS 標準の logrotate などを利用してローテーションすることを推奨する。

- 例：
 - 日次でローテーション
 - 7〜30 世代分を保持
 - gzip 圧縮を有効化

ログローテーションの詳細な設定は、インフラ側の標準運用に合わせて決定する。

### 6. 実運用への展開
- staging 環境
 - 本ドキュメントの設定例をベースに、実際のサーバで cron を設定する。
 - 初期運用期間中は、ログ内容と通知内容を重点的に確認する。
- production 環境
 - staging で問題ないことを確認してから、
実行タイミング / ログパス / 通知チャンネルを本番用に変更して適用する。
 - 特に、バックアップの保存先や通知のエスカレーションルールは
本番用のセキュリティ・運用ポリシーに合わせて調整する。

以上により、scripts/backup.sh / scripts/monitor.sh を中心とした
自動実行ジョブを、インフラ側で一貫して管理できる。