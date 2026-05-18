# L1-L6 評価指標 v1

**作成**: 2026-05-18  
**根拠**: docs/UATa-claude-ai-instructions-v5.md §17 / docs/24h-automation-runbook.md §完了条件  
**関連スクリプト**: `scripts/healthcheck_l1_l6.sh` (PR #247 / cron `*/5 * * * *`)  
**集計スクリプト**: `scripts/l1_l6_daily_summary.sh`

---

## 1. L1-L6 項目定義と重み

| 項目 | 名称 | 判定条件 | 重み | 備考 |
|---|---|---|---|---|
| **L1** | インフラ | コンテナ 7本以上 Up かつ 内部・外形 `/health` 200 | **critical** | FAIL → 全サービス停止 |
| **L2** | スケジューラ | `scheduler_healthy=true` かつ `last_judgment_age_min < 270` かつ `warnings_count=0` | **critical** | AI 判定の前提 |
| **L3** | AI 判定量 | `ai_decisions` 24h >= 3件 | normal | 業務稼働の最低ライン |
| **L4** | ユーザー反応 | `proposals` 24h の expired 率 < 50% | normal | ユーザーが承認できている指標 |
| **L5** | 実取引成功率 | is_dry_run=false の tx_hash=NULL 失敗率 < 20%。UAT 中 0件は PASS | **critical** | 実資金リスク |
| **L6** | 収益 | `portfolio_snapshots` 24h の zero_value 率 < 50% | warning-only | **UAT 期間中は WARN = PASS 扱い** |

### 重みの適用ルール

- **critical** 項目 (L1 / L2 / L5) のいずれかが FAIL → overall = FAIL
- **normal** 項目 (L3 / L4) が FAIL → overall = FAIL
- **warning-only** 項目 (L6) が WARN → overall = PASS (ログ・Slack には WARN と記録)
- L6 が FAIL (zero_value 率 >= 50%) → overall = FAIL

---

## 2. 「日次緑」の定義

> **1日 (JST 00:00-23:59) 中に実行される */5 cron の全 288 回のうち、**  
> **`overall_status == PASS` のラン数が 95% 以上 (= 失敗 14回/日 以内)**

### 計算式

```
daily_pass_count  = その日の overall=PASS のラン数
daily_total_count = その日の全ラン数 (最大 288)
daily_pass_rate   = daily_pass_count / daily_total_count

日次緑 = (daily_pass_rate >= 0.95) AND (daily_total_count >= 240)
```

> **最低 240 ラン** (1日の 83%+) が記録されていること。記録不足日はカウント対象外。

### 95% の根拠

- 5分ごとの単発エラー (cron 失敗 / 一時的コンテナ再起動) を許容
- 14 回 = 70分相当のダウンタイム許容
- これ以上の失敗は「本日の業務稼働が不十分」と判断

---

## 3. 「14日連続緑」の定義

> **直近 14 日間、毎日「日次緑」を満たしていること**

### カウント方式

```
streak = 0
for each day d in [today - 13, ..., today]:  # 14日分 (JST)
    if is_daily_green(d):
        streak += 1
    else:
        streak = 0  # リセット

14日連続緑達成 = (streak == 14)
```

### リセット条件

以下のいずれかが発生した日で streak がリセットされる:

| リセット条件 | 説明 |
|---|---|
| `daily_pass_rate < 0.95` | 1日で 15 回以上 FAIL (> 75分相当のダウン) |
| `daily_total_count < 240` | 記録が 240 ラン未満 (cron 停止・ログローテート等) |
| ログファイル不在 | `/opt/ultra-autotrade/logs/healthcheck_l1_l6.log` が当日分ゼロ |

### カウントダウン表示

```
14日連続緑まで: [streak日/14日] (残り [14 - streak] 日)
```

---

## 4. 集計 SQL

ログではなく PostgreSQL に記録する将来実装向け (現状は shell スクリプトで代替)。

```sql
-- 日次緑の集計 (将来 healthcheck_results テーブル実装後)
SELECT
  date_trunc('day', checked_at AT TIME ZONE 'Asia/Tokyo') AS day_jst,
  COUNT(*) AS total_runs,
  SUM(CASE WHEN overall_status = 'PASS' THEN 1 ELSE 0 END) AS pass_runs,
  ROUND(
    SUM(CASE WHEN overall_status = 'PASS' THEN 1 ELSE 0 END)::numeric
    / COUNT(*) * 100, 1
  ) AS pass_rate_pct,
  CASE
    WHEN COUNT(*) >= 240
     AND SUM(CASE WHEN overall_status = 'PASS' THEN 1 ELSE 0 END)::numeric / COUNT(*) >= 0.95
    THEN 'GREEN'
    ELSE 'NOT_GREEN'
  END AS daily_status
FROM healthcheck_results
WHERE checked_at >= NOW() - INTERVAL '14 days'
GROUP BY day_jst
ORDER BY day_jst DESC;
```

---

## 5. 現状スナップショット (2026-05-18 初日)

### 5.1 稼働開始

| 項目 | 値 |
|---|---|
| cron 稼働開始 | 2026-05-18 (PR #247 merge 前から本番配置済) |
| ログパス | `/opt/ultra-autotrade/logs/healthcheck_l1_l6.log` |
| ログサイズ | 148 KB (2026-05-18 11:05 JST 時点) |
| 観測ラン数 | 約 21 ラン (11:05 JST 時点 / 稼働 ~105分) |

### 5.2 実測値 (2026-05-18 02:16 UTC = 11:16 JST)

```
L1 インフラ:     PASS — containers=8/7, internal=200, external=200
L2 スケジューラ:  FAIL — scheduler_healthy=true, last_judgment_age_min=219
                  ※ 既知設計ギャップ (§5.3 参照)
L3 AI 判定:      PASS — ai_decisions_24h=14
L4 ユーザー反応:  PASS — proposals_24h=0, expired_rate=0.0
L5 実取引:       PASS — total_real_tx_24h=0 (UAT 中 0件正常)
L6 収益:         WARN — zero_value_pct=100.0 (UAT 期間中常態化)
→ overall:      FAIL (L2 起因)
```

### 5.3 L2 既知設計ギャップ (threshold 不整合)

| 項目 | 値 |
|---|---|
| L2 FAIL 条件 (`healthcheck_l1_l6.sh` v1) | `last_judgment_age_min >= 60` |
| AI スケジューラ実行間隔 | 240 分 (4h) |
| L2 PASS となる時間帯 | スケジューラ実行後の 60 分のみ |
| 理論的 L2 PASS 率 | 60 / 240 = **25%** |
| 影響 | 1日 288 ランのうち約 216 ランが L2 FAIL → 日次緑 達成不可 |

**対応** (別 PR):  
`last_judgment_age_min >= 270` に変更 (スケジューラ間隔 240 分 + バッファ 30 分)。  
この fix がデプロイされるまで、**14日連続緑のカウントは事実上開始しない**。

### 5.4 L6 WARN (UAT 期間中は許容)

`portfolio_snapshots` に実資産データが入っていない間、zero_value_pct=100% は想定内。  
メインネット資産が Aave V3 に供給され、スナップショットが取得され始めると自然解消。  
L6 WARN は overall PASS に影響しない (`§1` 記載通り)。

---

## 6. 14日連続緑 カウントダウン (2026-05-18 時点)

```
streak: 0 / 14 日  (残り 14 日)
状態  : COUNTING_BLOCKED — L2 設計ギャップ解消後に再開
```

### カウント再開条件

1. L2 threshold fix PR がデプロイされる (last_judgment_age_min >= 270 に変更)
2. その日から `is_daily_green(d) == true` が連続する

予想: L2 fix デプロイ翌日から streak 開始 → 14日後にローンチ条件達成

---

## 7. 集計スクリプト使用方法

```bash
# ログから日次サマリーを出力 (ローカル実行)
bash scripts/l1_l6_daily_summary.sh

# リモート (Hetzner) での実行
ssh ultra@77.42.46.155 \
  "bash /opt/ultra-autotrade/scripts/l1_l6_daily_summary.sh \
  --log /opt/ultra-autotrade/logs/healthcheck_l1_l6.log"

# 14日連続緑チェックのみ
bash scripts/l1_l6_daily_summary.sh --streak-only
```

出力例:

```
日付          総ラン  PASS  FAIL  PASS率   日次状態
2026-05-18    288    72    216   25.0%   NOT_GREEN (L2 gap)
...

連続緑 streak: 0 / 14
```

---

## 8. 改訂履歴

| バージョン | 日付 | 変更内容 |
|---|---|---|
| v1 | 2026-05-18 | 初版。cron 稼働開始日の実測値 + 設計ギャップ記録 |
