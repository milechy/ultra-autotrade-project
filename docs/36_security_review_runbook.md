# セキュリティレビュー Runbook (週次)

> 最終更新: 2026-04-25
> 実施者: 小林 (lead)、必要に応じて山本さん共有
> 頻度: 週次（毎週月曜 10:00 JST 推奨）
> 関連: docs/35_docker_maintenance_runbook.md, docs/22_production_release_checklist.md

---

## 0. 目的

main ブランチで放置されがちなセキュリティ警告を早期に検知・対応する。

**背景インシデント (2026-04-10 〜 2026-04-20):**
Trivy コンテナスキャンの CRITICAL 脆弱性が 10 日間 fail 放置された。
原因は「required status checks」未設定により CI 失敗がマージをブロックしなかったこと。
本 runbook は再発防止のための週次チェック手順を定める。

**3 層対策 (2026-04-25 実装済み):**
| 層 | 内容 | 自動化 |
|---|---|---|
| 層 1 | GitHub branch protection required status checks (4 件) + enforce_admins | 常時 |
| 層 2 | main ブランチ CI 失敗を毎朝 09:00 JST に Slack 通知 | launchd 自動 |
| 層 3 | 本 runbook (週次手動レビュー) | 手動 |

---

## 1. 週次チェックリスト

### 1.1 Trivy 脆弱性 (GitHub Code Scanning Alerts)

```bash
# CRITICAL/HIGH の未クローズ alert 一覧
gh api repos/milechy/ultra-autotrade-project/code-scanning/alerts?state=open \
  --jq '.[] | select(.rule.severity == "critical" or .rule.severity == "high") |
    {id: .number, severity: .rule.severity, rule: .rule.id, file: .most_recent_instance.location.path}'
```

- [ ] CRITICAL/HIGH の新規発生を確認
- [ ] 各 alert について: 対応 / リスク受容 / Mute の判断
  - **対応**: Asana タスク起票 → 1 週間以内に fix PR
  - **リスク受容**: `.trivyignore` に追記 + コメントで理由明記
  - **Mute**: GitHub UI でアラートをクローズ + コメント記載
- [ ] 判断した内容を Asana タスクとして起票（Asana GID: 1213741124336104）

### 1.2 main ブランチ CI ヘルス

```bash
# 直近 50 件の main CI 結果サマリー
gh run list --branch main --limit 50 --json conclusion,name,createdAt \
  --jq 'group_by(.conclusion) | .[] |
    {conclusion: .[0].conclusion, count: length}'

# 失敗一覧
gh run list --branch main --limit 50 --json conclusion,name,htmlUrl,headSha \
  --jq '.[] | select(.conclusion == "failure") |
    "❌ \(.name) (\(.headSha[0:7])) \(.htmlUrl)"'
```

- [ ] 直近 50 件の success 率を確認
- [ ] 95% 未満なら原因調査タスク起票 (Asana)
- [ ] 72h 以上継続している失敗があれば即時対応

### 1.3 Dependabot alerts

```bash
gh api repos/milechy/ultra-autotrade-project/dependabot/alerts?state=open \
  --jq '.[] | select(.security_advisory.severity == "critical" or
                     .security_advisory.severity == "high") |
    {id: .number, severity: .security_advisory.severity,
     pkg: .dependency.package.name, cve: .security_advisory.cve_id}'
```

- [ ] CRITICAL/HIGH を確認
- [ ] **ルール: CRITICAL は 3 日以内、HIGH は 7 日以内に対応**
- [ ] `npm audit fix` または `pip install --upgrade <pkg>` で対応後、PR 作成

### 1.4 GitHub Secret Scanning

- [ ] GitHub リポジトリ → Security → Secret scanning タブを確認
- [ ] 検出されていれば **即時ローテーション** + インシデント起票

```bash
# CLI でも確認可能
gh api repos/milechy/ultra-autotrade-project/secret-scanning/alerts?state=open \
  --jq '.[] | {id: .number, secret_type: .secret_type, state: .state}' 2>/dev/null || \
  echo "(secret scanning API requires special permissions — check GitHub UI)"
```

### 1.5 Branch protection 設定確認

```bash
gh api repos/milechy/ultra-autotrade-project/branches/main/protection \
  --jq '{
    enforce_admins: .enforce_admins.enabled,
    required_status_checks: .required_status_checks.contexts,
    required_approving_reviews: .required_pull_request_reviews.required_approving_review_count
  }'
```

期待値:
```json
{
  "enforce_admins": true,
  "required_status_checks": [
    "Lint (ruff + mypy)",
    "Test (pytest + coverage)",
    "Security Check",
    "Trivy Container & Filesystem Scan"
  ],
  "required_approving_reviews": 1
}
```

- [ ] `enforce_admins: true` 維持確認
- [ ] required_status_checks に 4 件以上あること
- [ ] 上記から変更されていれば即時修正

---

## 2. 月次チェック（週次に追加）

月初めの週次実施時に以下も確認する:

- [ ] `.env.production` の md5sum を記録（前月比較 — ドリフト検出）
  ```bash
  # Hetzner 上で実行
  md5sum /opt/ultra-autotrade/.env.production
  ```
- [ ] Hetzner OS update 状況
  ```bash
  # Hetzner 上で実行
  apt list --upgradable 2>/dev/null | grep -c "upgradable" && echo "packages to update"
  ```
- [ ] Cloudflare Tunnel ログ異常検出
  ```bash
  docker logs ultra-autotrade-cloudflared-production --since 720h 2>&1 | grep -c "error\|fail"
  ```
- [ ] Aave V4 移行進捗確認（2026-Q3 target）
- [ ] RPC レート制限使用率確認（Alchemy ダッシュボード: 月間 CU 使用率）

---

## 3. インシデント発生時のエスカレーション

| 種別 | 対応期限 | アクション |
|---|---|---|
| CRITICAL Trivy alert | 24h 以内 | `.trivyignore` で受容 or fix PR + Asana 起票 |
| HIGH Trivy alert | 7 日以内 | fix PR + Asana 起票 |
| main CI 72h 以上 fail 継続 | 即時 | Slack `#ultra-auto-project` 報告 + 原因調査 |
| Secret scanning 検出 | 即時 | 鍵ローテーション + `git filter-repo` + Asana 起票 |
| 本番デプロイ後の異常 | 即時 | `docs/15_rollback_procedures.md` に従う |

---

## 4. 関連ツール・ファイル

| ツール / ファイル | 用途 |
|---|---|
| `gh` CLI | GitHub 操作全般 |
| `~/ft-automation/scripts/main_ci_health_check.sh` | 層 2 自動通知スクリプト |
| `~/ft-automation/launchd/com.kobayashi.uat-main-ci-monitor.plist` | launchd 登録ファイル |
| `docs/35_docker_maintenance_runbook.md` | Docker 周りの月次保守 |
| `docs/22_production_release_checklist.md` | デプロイ前後の全体チェック |
| `docs/13_security_design.md` | セキュリティ設計詳細 |
| `.trivyignore` | 受容済み CVE の管理 |
| Asana プロジェクト `1213741124336104` | タスク管理 |

---

## 5. launchd 監視設定の管理

層 2 の自動通知が停止した場合の確認手順:

```bash
# launchd 登録状態確認
launchctl list | grep uat-main-ci-monitor

# ログ確認
tail -30 ~/ft-automation/logs/main_ci_monitor.log
cat ~/ft-automation/logs/main_ci_monitor.err

# 再登録
launchctl unload ~/Library/LaunchAgents/com.kobayashi.uat-main-ci-monitor.plist
cp ~/ft-automation/launchd/com.kobayashi.uat-main-ci-monitor.plist \
   ~/Library/LaunchAgents/com.kobayashi.uat-main-ci-monitor.plist
launchctl load ~/Library/LaunchAgents/com.kobayashi.uat-main-ci-monitor.plist

# 即時テスト実行
launchctl start com.kobayashi.uat-main-ci-monitor
```

Webhook URL が変わった場合:
```bash
# ~/ft-automation/.env.ultra を更新
# SLACK_WEBHOOK_URL_ULTRA=https://hooks.slack.com/services/...
nano ~/ft-automation/.env.ultra
```

---

## 6. 完了条件

本 runbook を 4 週連続で実施し、false alarm 率 < 20% であれば運用安定とみなす。
**2026-05-25** にレビューして本 runbook の運用継続 / 見直しを判断する。
