# Ultra AutoTrade — 未配線スクリプト運用ガイド

> 生成: 2026-07-07 / 対象タスク: Asana GID 1216317544884468 (Tier B)
> 目的: `scripts/` 配下に実装済みだが cron / CI / 既存 runbook のどこにも配線されておらず、
> 手動起動のみ（＝忘れられやすい）のスクリプト 10 本を棚卸しし、分類と推奨運用を記録する。
> ソース: 各スクリプト本体（header コメント・usage・cron 例）を実読して分類（推測なし）。

---

## スコープ外の宣言

**本ドキュメントは推奨設定の記録のみを目的とする。**
dev / staging / production VPS の実際の `crontab` への登録作業は本タスクのスコープ外であり、
別途 人間承認済みの実行タスクとして行うこと。以下に記載する `crontab -e` 追記例は
「レビュー・承認用の提案」であり、本タスクの一部としては一切実行していない。

---

## 1. 分類サマリ

| スクリプト | 分類 | 推奨頻度 |
|---|---|---|
| `loki_watchdog.sh` | 定期監視 | 3分毎 |
| `staging-watchdog.sh` | 定期監視 | 5分毎 |
| `check_main_ci_health.sh` | 定期監視（参考実装・要確認） | 1時間毎 |
| `staging_observation_monitor.sh` | 定期監視 | 4時間毎（+ UAT期間中は5分毎の警戒モード） |
| `healthcheck_external.sh` | 定期監視 | 10〜15分毎 |
| `cf_pages_check.sh` | 定期監視（deploy後 + 定期ドリフト検知） | 30分毎 |
| `verify_rebalance_shadow_source.sh` | 手動/オンデマンド | config変更時・deploy前後 |
| `measure_tier_s_approval_rate.sh` | 手動/オンデマンド | ローンチ判定レビュー時 |
| `compute_approval_rate.sh` | 手動/オンデマンド | 週次レポートが欲しい時（任意） |
| `analyze_hold_bias.sh` | 手動/オンデマンド | HOLD偏向調査時 |

> **注記**: `staging_observation_monitor.sh` は当初「手動系」と見込まれていたが、実読の結果
> スクリプト自身の header に cron 登録手順（4時間毎 + UAT期間中5分毎）が明記されており、
> 定期監視スクリプトとして分類し直した。

---

## 2. 定期監視スクリプト（periodic/monitoring）

### 2.1 `loki_watchdog.sh`

- **目的**: Loki 2.9.0 の ingester ring 未登録による半死状態（`/ready` 503）を検知し、
  `docker compose up -d --force-recreate --no-deps loki` で自動復旧する。
  （背景: `docs/postmortems/2026-05-17_loki_postgres_cascade.md`）
- **推奨頻度**: 3分毎（スクリプト自身の header コメントに記載の cron 例と同じ）
- **crontab 例**（本番 VPS / ultra ユーザー、登録は別タスク）:
  ```cron
  */3 * * * * /opt/ultra-autotrade/scripts/loki_watchdog.sh >> /opt/ultra-autotrade/logs/loki_watchdog.log 2>&1
  ```
- **安全装置**: `COOLDOWN_SEC`（既定 600秒）で recreate 連打を防止。検知/復旧の各段階で Slack 通知。

### 2.2 `staging-watchdog.sh`

- **目的**: staging-new スタック（postgres コンテナ死活を sentinel として使用）が停止している場合に
  `up -d` で自動復旧する defense-in-depth。真因（`deploy_production.sh` の
  `--remove-orphans` が staging を巻き込み削除していた件）は既に別途修正済みだが、本スクリプトは保険として残す。
- **推奨頻度**: 5分毎（スクリプト自身の header コメントに記載）
- **crontab 例**:
  ```cron
  */5 * * * * /opt/ultra-autotrade/scripts/staging-watchdog.sh >> /var/log/ultra-autotrade/staging-watchdog.log 2>&1
  ```
- **安全装置**: `flock` による多重実行防止（OOM螺旋対策）、`COOLDOWN_SEC`（既定 1800秒）で通知連発を抑制（復旧試行自体は毎回行う）。

### 2.3 `check_main_ci_health.sh`

- **目的**: main ブランチの直近 N 時間の CI 失敗を `gh api` で集計し Slack 通知する。
- **⚠ 重要な前提**: スクリプト header に「実運用は `~/ft-automation/scripts/main_ci_health_check.sh` +
  launchd で行う」と明記されており、**本リポジトリ版は参考実装（reference implementation）**という位置付け。
  本リポジトリの cron へ配線する前に、既存の launchd 版が現在も稼働中かを確認すること。
  稼働中であれば本スクリプトを VPS cron に追加するのは重複になるため非推奨。
  launchd 版が失われている／属人化している場合のみ、本スクリプトを VPS 側の正式な定期ジョブとして
  昇格させる判断を別途行う。
- **推奨頻度（配線する場合）**: 1時間毎
- **crontab 例（配線する場合）**:
  ```cron
  0 * * * * /opt/ultra-autotrade/scripts/check_main_ci_health.sh --hours 24 >> /opt/ultra-autotrade/logs/main_ci_health.log 2>&1
  ```
- **依存**: `gh` CLI（認証済み）、`jq`、`curl`

### 2.4 `staging_observation_monitor.sh`

- **目的**: Stream 8（#365 PR: SELL/BUY dual-agent AND条件）の効果観測 + 2026-05-21 P0
  （scheduler 暴走 / proposal spike）再発検知。staging `ai_decisions` を集計し Slack 通知。
  dev VPS では DB/health に接続できないため自動的に skip し `exit 0`（cron を壊さない設計）。
- **推奨頻度**: 通常運用は4時間毎。UAT期間中のみ5分毎の警戒モードを追加。
- **crontab 例**（スクリプト自身の header に記載の推奨設定をそのまま踏襲）:
  ```cron
  # 4時間ごと観測レポート
  0 */4 * * * /opt/ultra-autotrade/scripts/staging_observation_monitor.sh >> /opt/ultra-autotrade/logs/staging_obs_monitor.log 2>&1

  # UAT期間中のみ推奨: 5分ごとの spike/health 警戒モード
  */5 * * * * WINDOW="1 hour" /opt/ultra-autotrade/scripts/staging_observation_monitor.sh >> /opt/ultra-autotrade/logs/staging_obs_monitor.log 2>&1
  ```
- **前提**: `/opt/ultra-autotrade/logs` ディレクトリの事前作成が必要（cron 実行前）。

### 2.5 `healthcheck_external.sh`

- **目的**: Cloudflare → nginx → backend の外形経路を通しで確認する（`/health` を5回連続で叩き全て200かを見る）。
  Usage: `healthcheck_external.sh [production|staging]`。staging は CF Access token が必要なため
  現状は常に skip（`exit 0`）する実装になっている点に注意。
- **推奨頻度**: 10〜15分毎（production のみ意味を持つ）
- **crontab 例**:
  ```cron
  */15 * * * * /opt/ultra-autotrade/scripts/healthcheck_external.sh production >> /opt/ultra-autotrade/logs/healthcheck_external.log 2>&1
  ```
- **Exit code**: `0`=全部200 / `1`=失敗あり（監視ツール側でアラート条件として利用可能）。

### 2.6 `cf_pages_check.sh`

- **目的**: Cloudflare Pages 公開後の7項目チェック（TLS / WAF block / tunnel reachable /
  root 200 / security headers / HTTP→HTTPS redirect / cache-control）。Asana P0-5.1 由来。
- **運用方針**: 本来は CF Pages への deploy 直後に1回叩く「post-deploy verification」としての性格が強いが
  （deploy パイプラインへのフック方法は `docs/ops/03_deploy_procedures.md` 側の管轄・本書では扱わない）、
  設定ドリフト（WAF ルール変更・証明書更新漏れ等）を継続検知するための定期実行としても有用。
- **推奨頻度**: 30分毎（定期ドリフト検知用途）
- **crontab 例**:
  ```cron
  */30 * * * * /opt/ultra-autotrade/scripts/cf_pages_check.sh --host app.ultra-auto-trade.com --api-host api.ultra-auto-trade.com >> /opt/ultra-autotrade/logs/cf_pages_check.log 2>&1
  ```
- **Exit code**: `0`=全7項目PASS / `1`=1項目以上FAIL / `2`=引数エラー。

---

## 3. 手動/オンデマンドスクリプト（manual/on-demand）

### 3.1 `verify_rebalance_shadow_source.sh`

- **いつ実行するか**: `REBALANCE_SHADOW_MODE` 関連の compose / `.env` 変更を行った際
  （PR #457 `chore/rebalance-shadow-mode-env-ref-20260529` が起点）、または deploy 前後の設定確認時。
- **なぜ**: `REBALANCE_SHADOW_MODE` が compose の `environment:` に直書きされていないか
  （`.env.production` / `.env.staging-new` の単一ソースで管理されているか）を検証する回帰チェック。
  読み取り専用、DB/本番環境への書き込みなし。
- **実行例**: `./scripts/verify_rebalance_shadow_source.sh`（引数なし、exit 0=PASS / 1=FAIL）

### 3.2 `measure_tier_s_approval_rate.sh`

- **いつ実行するか**: ローンチ判定基準3「本番 Tier S 操作の人間承認率100%」（`docs/launch_decision_criteria_v2.md` §3）の
  レビュー時、または Tier S ファイル周りの運用逸脱（直push / --no-verify 実行等）を確認したい時。
- **なぜ**: (a) Tier S ファイルを触った merged PR の Approve率、(b) main への直push数、
  (c) `--no-verify` / `--dangerously-skip-permissions` 実行数、の3軸を計測し PASS/FAIL 判定する。
  read-only（GitHub read API + ローカル read のみ）。
- **実行例**:
  ```bash
  ./scripts/measure_tier_s_approval_rate.sh            # 直近14日
  ./scripts/measure_tier_s_approval_rate.sh --days 30 --slack
  ```

### 3.3 `compute_approval_rate.sh`

- **いつ実行するか**: proposals の承認率（v3/v4 プロンプト内訳含む）を確認したい任意のタイミング。
  現状 cron 化はされていないが、週次サマリとして Slack へ流したい場合は定期実行に昇格させる余地がある
  （その場合は本書 §2 相当の追記が別途必要）。
- **なぜ**: 本番 DB を read-only で集計し（`proposals` テーブルの approved/rejected/expired/pending件数）、
  承認率と v3/v4 内訳を Slack 通知する。
- **実行例**: `./scripts/compute_approval_rate.sh --days 7`（`--quiet` で Slack 通知なし・stdout のみ）

### 3.4 `analyze_hold_bias.sh`

- **いつ実行するか**: AI判定が HOLD に偏っている疑いがある時のアドホック調査
  （例: proposal 生成数が想定より少ない、BUY/SELL がほぼ出ていない、といった報告を受けた際）。
- **なぜ**: production DB に直接繋がず `/ai/decisions` API 経由で直近の BUY/SELL/HOLD 比率を集計する
  軽量な調査スクリプト。エンドポイント未実装環境では警告を出して終了する。
- **実行例**: `./scripts/analyze_hold_bias.sh --days 7 --api-url https://api.ultra-auto-trade.com`

---

## 4. 既存 cron ドキュメントとの重複チェック

- `docs/35_docker_maintenance_runbook.md`: `docker_cleanup.sh` の週次 cron（日曜03:00 JST）を管轄。
  本書で扱う10スクリプトとは対象が異なり重複なし。
- `docs/ops/vps_ops_runbook_2026_06.md`: `periodic_docker_cleanup.sh`（週次 Docker 積極cleanup）と
  `backup_db.sh`（週次 DB バックアップ）の VPS cron 登録手順を管轄。同様に対象重複なし。
- 上記2つの既存 runbook は「登録手順書（実際に crontab へ入れる前提の文書）」であるのに対し、
  本書 (`08_unwired_scripts_integration.md`) は現時点では「推奨設定の記録」に留まる点に注意
  （§ スコープ外の宣言を参照）。将来的に本書の内容を実際に VPS へ配線する際は、
  上記2ファイルと同じログディレクトリ作成手順・cron 衝突確認の作法を踏襲すること。

---

## 5. Next Step（本タスクの範囲外）

- [ ] dev / staging / production VPS への実際の `crontab -e` 登録（人間承認必須の別タスク）
- [ ] `check_main_ci_health.sh` について、既存 launchd 版（`~/ft-automation`）の稼働状況を確認し、
      本リポジトリ版を配線すべきか／不要かを判断
- [ ] `cf_pages_check.sh` の deploy パイプラインへのフック要否を `docs/ops/03_deploy_procedures.md`
      側で別途検討（本書では扱わない）
