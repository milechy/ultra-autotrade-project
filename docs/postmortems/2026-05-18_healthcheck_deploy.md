# 2026-05-18 L1-L6 ヘルスチェック本番デプロイ記録

> 分類: デプロイ記録 (インシデントではなく正規デプロイ)
> 実施日: 2026-05-18
> 担当: Lane S-Hetzner-Deploy (Claude Sonnet 4.6)
> 関連 PR: #247 (scripts/healthcheck_l1_l6.sh 追加)
> DoD: §17 L1-L6 観測の正本稼働開始

---

## 1. 背景

RC-7「本番運用に必要な observability が『動いていることになっている』だけ」を解消するため、
5分間隔で L1-L6 を機械チェックする `scripts/healthcheck_l1_l6.sh` を実装・デプロイした。

---

## 2. デプロイ実施内容

### 2.1 スクリプト配置

| 項目 | 値 |
|---|---|
| スクリプトパス | `/opt/ultra-autotrade/scripts/healthcheck_l1_l6.sh` |
| パーミッション | `-rwxrwxr-x` (chmod +x 済) |
| オーナー | `ultra:ultra` |
| 配置確認時刻 | 2026-05-18 10:51 JST (既配置) |

### 2.2 cron 登録

```cron
*/5 * * * * /opt/ultra-autotrade/scripts/healthcheck_l1_l6.sh >> /opt/ultra-autotrade/logs/healthcheck_l1_l6.log 2>&1
```

`crontab -l` 確認: 登録済み (`ultra` ユーザー)

### 2.3 ログ出力先

`/opt/ultra-autotrade/logs/healthcheck_l1_l6.log` — 2026-05-18 11:05 JST 時点で 148KB (稼働確認済み)

---

## 3. 重要な事実: PR #247 merge 前から本番配置されていた

**事実**: `scripts/healthcheck_l1_l6.sh` は PR #247 が main にマージされる前から、
すでに Hetzner 本番 (`/opt/ultra-autotrade/scripts/`) に配置されており、
cron も登録済みだった。

**発覚経緯**:
- Lane S-Hetzner-Deploy の Phase 1 (read-only 調査) で SSH にて現状確認
- `/opt/ultra-autotrade/scripts/healthcheck_l1_l6.sh` が存在
- crontab に `*/5` エントリ確認済み
- ログファイル `/opt/ultra-autotrade/logs/healthcheck_l1_l6.log` に当日分 148KB のデータ

**推定原因**: Lane B-3 完了後、ユーザーまたは別プロセスが手動でスクリプトを Hetzner に転送・登録した。
PR #247 のマージ前デプロイは CLAUDE.md「Hetzner pull only / ローカル merge only」鉄則1 の運用外。

**対応**: 既存の配置・cron を尊重し、上書き・変更は行わなかった。
DoD 検証 (FAIL_SIMULATE_L1 / 通常実行 / ゲート確認) は既存配置で実施した。

---

## 4. DoD 検証結果

| DoD 項目 | 結果 | 証跡 |
|---|---|---|
| スクリプト配置 + chmod +x + ultra:ultra | ✅ | `ls -la /opt/.../healthcheck_l1_l6.sh → -rwxrwxr-x 1 ultra ultra` |
| cron `*/5` 登録 | ✅ | `crontab -l \| grep healthcheck_l1_l6` 1件ヒット |
| 手動実行 L1-L6 全項目結果出力 | ✅ | ログ末尾 JSON 確認 |
| FAIL_SIMULATE_L1=true → Slack FAIL 通知到達 | ✅ | 連続6回目 / `"details":"L1 FAIL simulated for testing"` |
| FAIL_SIMULATE 解除 → L1=PASS 確認 | ✅ | `結果: L1=PASS L2=FAIL L3=PASS L4=PASS L5=PASS L6=WARN` |
| Gate 1: docker ps 全コンテナ Up+healthy | ✅ | 8コンテナ全 Up (blue/green/frontend/nginx/postgres/loki/promtail/cloudflared) |
| Gate 2: /health scheduler_healthy=true | ✅ | `scheduler_healthy: True, status: ok` |
| Gate 3: DB アクセス (ai_decisions 24h) | ✅ | 14件 |
| Gate 4: Slack 通知到達 | ✅ | FAIL_SIMULATE テストで確認 |
| Gate 5: ログ末尾確認 | ✅ | `/opt/ultra-autotrade/logs/healthcheck_l1_l6.log` 末尾 JSON valid |

---

## 5. 既知の設計ギャップ (別 PR / 別タスクで解決)

### 5.1 L2 閾値ギャップ — 別 PR で解決

**症状**: L2 が常時 FAIL 状態で Slack に連続 FAIL 通知が届き続けている

**原因**:
- `healthcheck_l1_l6.sh` の L2 PASS 条件: `last_judgment_age_min < 60` (60分)
- AI 判定スケジューラーの実行間隔: 4時間 (240分)
- スケジューラー実行直後の約60分しか L2 PASS しない (残り3時間は FAIL)

**実測値** (2026-05-18 02:05 UTC): `last_judgment_age_min=207` (scheduler_healthy=true なのに FAIL)

**解決策** (別 PR):
```bash
# L2 閾値を 4.5時間 (270分) に変更
if [[ "${last_judgment_age_min}" -gt 270 && "${last_judgment_age_min}" != "-1" ]]; then
  status="FAIL"
fi
```

### 5.2 ログパス不整合 — morning-report との連携: 別 Tier B タスクで解決

| 種別 | パス |
|---|---|
| スクリプトコメントヘッダー記載 | `/var/log/ultra-autotrade/healthcheck.log` |
| cron 実際の出力先 | `/opt/ultra-autotrade/logs/healthcheck_l1_l6.log` |
| `/var/log/ultra-autotrade/` | 未作成 (DoD では作成対象だったが既存 cron を尊重して不要と判断) |

**影響**: `morning-report` や他スクリプトがコメント記載パスを参照した場合、ログ取得に失敗する

**解決策** (別 Tier B タスク):
- スクリプトコメントのパス記述を実際の cron パスに合わせて修正
- または cron を `/var/log/ultra-autotrade/healthcheck.log` に統一

---

## 6. L1-L6 現状スナップショット (2026-05-18 02:16 UTC)

```
L1 インフラ:    PASS — containers_running=8/7, internal=200, external=200
L2 スケジューラ: FAIL — scheduler_healthy=true, last_judgment_age_min=219 (§5.1 設計ギャップ)
L3 AI判定:     PASS — ai_decisions_24h=14
L4 ユーザー反応: PASS — proposals_24h=0, expired_rate=0.0
L5 実取引:     PASS — total_real_tx_24h=0, tx_failed_24h=0 (UAT中 0件正常)
L6 収益:      WARN — zero_value_pct=100.0 (UAT期間中常態化)
```

---

## 7. 次アクション

| 優先度 | タスク | 担当 |
|---|---|---|
| P1 | L2 閾値を 270分に修正 (別 PR) | Lane B / Sonnet |
| P2 | ログパス不整合解消 — コメント修正 (別 Tier B タスク) | Lane B |
| P3 | morning-report との L1-L6 ログ連携実装 | 別 Phase |
