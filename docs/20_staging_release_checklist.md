# 20_staging_release_checklist.md
Ultra AutoTrade – Staging リリース前チェックリスト

本ドキュメントは、Ultra AutoTrade の各フェーズで実装した機能を  
**staging 環境で実際に動かす前に確認すべき項目** を一覧化したものである。

このチェックリストを満たすことで、  
「staging での結合動作確認に進んでよい状態」を定義する。

---

## 1. インフラ準備チェック

- [ ] Staging 用サーバ（例：Hetzner Cloud）が用意されている
- [ ] OS のセキュリティアップデートが適用されている
- [ ] `git`, `docker`, `docker compose` など必要なツールがインストール済み
- [ ] プロジェクトリポジトリが `/opt/ultra-autotrade`（または同等のパス）に配置されている
- [ ] `Dockerfile` / `docker-compose.staging.yml` がサーバに反映されている
- [ ] `.env.staging` が作成されており、**Git に含まれていない**

参考：`16_infra_deployment_guide.md`, `13_security_design.md`, `17_staging_environment_config.md`

---

## 2. アプリケーション動作チェック

### 2.1 基本動作

- [ ] `docker compose -f docker-compose.staging.yml up -d` で backend コンテナが起動している
- [ ] `/health` に対して HTTP 200 が返る
  ```bash
  curl -fsS http://localhost:8000/health

- [ ] ログに致命的エラーが出ていない（起動直後のログを確認）

### 2.2 Notion 連携
- [ ] .env.staging の NOTION_API_KEY / NOTION_DATABASE_ID が staging 用 Notion DB を指している
- [ ] テスト用ニュースページを作成し、Notion → Backend への Ingest（/notion/ingest）が成功する
- [ ] 失敗時に適切なエラーメッセージがログに記録される

### 2.3 OctoBot（staging）連携
- [ ] .env.staging の OCTOBOT_API_BASE_URL / OCTOBOT_API_KEY が staging OctoBot を指している
- [ ] テスト用シグナル送信が成功し、OctoBot 側で受信が確認できる
- [ ] OctoBot 側がダウンしている場合、リトライ・エラーハンドリングが正常に動作する

### 2.4 Aave（テストネット）連携
- [ ] .env.staging の Aave 関連変数がテストネット設定になっている（AAVE_NETWORK=polygon-mumbai など）
- [ ] ウォレットはテスト用アドレスであり、本番資金が入っていない
- [ ] 少額のテスト取引が正常に実行できる（またはシュミレーションが成功する）
- [ ] Health Factor やリスク関連設定が保守的な値になっている

## 3. ジョブ・スケジューラチェック
### 3.1 手動実行
- [ ] ./scripts/backup.sh を手動実行し、バックアップ処理が成功する
- [ ] ./scripts/monitor.sh daily を手動実行し、日次レポートが生成・通知される
- [ ] ./scripts/monitor.sh weekly を手動実行し、週次レポートが生成・通知される
- [ ] いずれもエラー終了せず、ログに異常が残っていない

### 3.2 cron 設定
- [ ] crontab -l で、以下のジョブが設定されていることを確認
 - 毎日 00:00 バックアップ
 - 毎日 00:30 日次監視・レポート
 - 毎週 月曜 01:00 週次監視・レポート
 - 毎分ヘルスチェック（必要に応じて）
- [ ] /var/log/ultra/*.log が生成され、更新されていることを確認
- [ ] ログファイルのサイズが肥大化していない、または logrotate 設定が検討されている

## 3. ログ・監視設定チェック

- [ ] `docs/08_automation_rules.md` の「6. 監視メトリクス一覧」にある主要メトリクスが、
      少なくともログファイルまたは簡易ダッシュボード上で確認できる
- [ ] `scripts/monitor.sh daily` / `scripts/monitor.sh weekly` を手動実行し、
      `monitor_daily.log` / `monitor_weekly.log` に正常終了のログが出力されることを確認した
- [ ] 緊急停止フラグを一時的に ON/OFF した際、MonitoringEvent / ログに
      `emergency_stop_flag` の変化が記録されることを確認した（staging 資金で実施）


## 4. 運用フロー確認
- [ ] 19_operations_runbook.md に一度目を通し、
　日常運用フロー・異常時のフローが理解できている
- [ ] 緊急停止フラグの ON/OFF 方法を把握している
- [ ] 緊急停止フラグを ON にした場合、トレード系処理がブロックされることを確認済み
- [ ] 15_rollback_procedures.md に従い、staging での簡易ロールバック手順を一度試してみた
- [ ] ロールバック後もバックアップ・監視ジョブが正常に動作していることを確認

## 5. サインオフ
- チェック完了日：
- 確認者：
- 備考欄：
 - 例：一部項目についての補足、今後の改善点など