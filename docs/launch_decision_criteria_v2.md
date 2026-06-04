# ローンチ判断条件 v2

> **目的**: §17 ローンチ判断条件 (UATa-claude-ai-instructions v5 §17) を測定可能な客観指標に落とし込む。  
> **参照**: `healthcheck_l1_l6.sh` (PR #247) / `docs/UATa-claude-ai-instructions-v5.md §17`  
> **作成**: 2026-05-18

---

## §17 原文 (2026-05-28 改訂版)

```
5/31 強行はしない。客観条件で判断:
- 両 partner (山本 user_id=11 + 橋口 user_id=18) 本運用 14日 (L1-L6 は監視継続だがローンチ判定軸として使わない)
- staging で chaos test 3日連続失敗ゼロ
- 本番 Tier S 操作の人間承認率 100% (auto-bypass ゼロ)
- 山本さん UAT 完走 (proposals 全件 EXECUTED 判定基準満たす)
- 森先生 法務確認 (BVI / non-custodial)
```

> **改訂経緯 (2026-05-28)**: 旧原文の条件 1「L1-L6 14日連続緑」は数学的に 6/1 不達確定だったため、両 partner 本運用 14日に置換。**6/1 (Day 1) 両 partner 本運用起算 → 6/14 達成 → 6/15 full launch**。L1-L6 評価は継続するが、ローンチ判定軸ではない(§1.5 で監視枠として保持)。条件 2-5 は変更なし。Asana 1215186751757662。旧原文は §9 変更履歴に保存。

---

## 1. ローンチ判定軸 — 両 partner (山本+橋口) 本運用 14日

> **2026-05-28 改訂**: 旧「L1-L6 14日連続緑」をローンチ判定軸から外し、両 partner (山本 user_id=11 + 橋口 user_id=18) **本運用 14日観測** を新判定軸とする。L1-L6 詳細評価は §1.5「L1-L6 監視 (判定軸外、参考指標)」に移植して継続。

### 1.1「両 partner 本運用 14日」の定義

| 用語 | 定義 |
|---|---|
| 本運用 (Day 1 起算) | 両 partner (山本 user_id=11, 橋口 user_id=18) が production 環境で実 launch (Shadow Mode 並走でなく実 launch)。6/1 (Day 1) 起算予定 |
| 「本運用 1日達成」 | その暦日 (JST 00:00-23:59) 内に両 partner それぞれ:<br/>① `ai_decisions` が生成されている (production AI 判定が稼働している)<br/>② proposals が active (ステータス変更フローを経て final 状態に到達 or 期限内継続) で「stale ≥ 24h」がゼロ<br/>③ `non_executed_active = 0` 又は当該 partner の `proposals.expires_at > NOW()` で進行中 |
| 「14日達成」 | 上記「本運用 1日達成」が両 partner で連続 14 日継続 (= 6/1 起算で 6/14 達成) |
| 既存 UAT 5条件 (条件 4) との関係 | 条件 4 は UAT 完走判定 (proposals 全件 EXECUTED)、本条件 1 は 14日継続観測。両者は別軸。条件 4 完走後に本条件 1 が起算可能になる構造ではなく、両者は並行観測 |

### 1.2 判定 SQL (両 partner 本運用 1日達成チェック)

```sql
-- 両 partner それぞれが当該 JST 暦日内に ai_decisions を生成し、stale proposals がゼロかを確認
WITH partners AS (
  SELECT id, name FROM users WHERE id IN (11, 18) AND role = 'partner' AND is_active = TRUE
),
target_day AS (
  -- ${TARGET_DATE} を引数で渡す。デフォルトは「昨日 JST」
  SELECT (CURRENT_DATE - INTERVAL '1 day' AT TIME ZONE 'Asia/Tokyo')::date AS d
),
daily_ai_decisions AS (
  SELECT p.id AS partner_id, COUNT(ad.id) AS ai_decision_count
  FROM partners p
  LEFT JOIN ai_decisions ad
    ON ad.user_id = p.id
   AND ad.created_at >= (SELECT d FROM target_day) AT TIME ZONE 'Asia/Tokyo'
   AND ad.created_at <  (SELECT d FROM target_day) AT TIME ZONE 'Asia/Tokyo' + INTERVAL '1 day'
  GROUP BY p.id
),
stale_proposals AS (
  SELECT p.id AS partner_id, COUNT(pr.id) AS stale_count
  FROM partners p
  LEFT JOIN proposals pr
    ON pr.user_id = p.id
   AND pr.status NOT IN ('executed','expired','rejected')
   AND pr.expires_at < NOW()
  GROUP BY p.id
)
SELECT
  p.name,
  COALESCE(d.ai_decision_count, 0) AS ai_decision_count,
  COALESCE(s.stale_count, 0) AS stale_proposals_count,
  CASE
    WHEN COALESCE(d.ai_decision_count, 0) >= 1
     AND COALESCE(s.stale_count, 0) = 0
    THEN '✅ 1日達成'
    ELSE '❌ 未達 (ai_decisions=' || COALESCE(d.ai_decision_count, 0)::text
         || ', stale=' || COALESCE(s.stale_count, 0)::text || ')'
  END AS daily_status
FROM partners p
LEFT JOIN daily_ai_decisions d ON d.partner_id = p.id
LEFT JOIN stale_proposals s ON s.partner_id = p.id
ORDER BY p.id;
```

両 partner で「✅ 1日達成」が出た日のみ「本運用 1日達成」をカウント。連続 14 日で 14 日達成。

### 1.3「両 partner 本運用 14日」カウント方法

- **起算条件**: 両 partner の wallet 登録完了 + production 反映 + 本 PR (§17 改訂) merge + scheduler flag conflict 解消 (Asana 1215153474346999) が全て満たされた翌 JST 暦日 0:00 から起算
- **streak リセット条件**:
  - いずれかの partner で当該日 `ai_decision_count = 0` (production AI 判定が走っていない)
  - いずれかの partner で当該日 `stale_proposals_count > 0` (stale ≥ 24h の proposals がある = 障害)
  - production 障害発生 (`docs/postmortems/*.md` 該当日付に追加されたら streak リセット候補)
- **集計タイミング**: 翌日 JST 00:30 (24 時間集計余裕後) に上記 SQL を batch 実行、結果を `launch_partner_uat_streak.log` (or 同等の summary) に追記

### 1.4 現在値 (2026-05-28 時点)

| 項目 | 現在値 | 判定 |
|---|---|---|
| 山本さん (id=11) wallet 登録 | `0x2064...cc66` 登録済 | ✅ |
| 橋口さん (id=18) wallet 登録 | 2026-06-01 までに登録予定 | ⏳ |
| scheduler flag conflict (Asana 1215153474346999) | production .env で ENABLE/DISABLE 両 set 競合中 | ❌ |
| 両 partner 本運用 14日 streak | 0/14 日 (起算前、6/1 予定) | ❌ |

> **6/1 launch 起算条件**: 上記 4 項目を全て解消 + 本 PR merge で 6/1 (Day 1) から streak カウント開始。

### 1.5 L1-L6 監視 (判定軸外、参考指標)

> **2026-05-28 改訂注記**: L1-L6 評価は **継続して監視**するが、ローンチ判定軸ではない(参考指標扱い)。Day 1 起算後の障害早期検出に使う。詳細仕様 (PASS/FAIL 判定式 / 14日連続緑カウント方法 / healthcheck_l1_l6.sh 整合版) は以下に保持。

#### 1.5.1「緑」の定義 (旧 §1.1)

| 用語 | 定義 |
|---|---|
| 1日の「緑」 | その日の `*/5` cron 実行 (~288 回) のうち、L1-L5 全 PASS が **95% 以上** |
| 「連続緑」 | 上記「緑」が途切れなく続く暦日数 |
| L6 WARN の扱い | L6 WARN は UAT 期間中「緑」判定に影響しない (FAIL でない限り許容) |
| 5% 失敗許容の根拠 | nginx restart 等の一時 502 を吸収する設計余裕。連続 15 回以上の FAIL は即 Slack 通知 |

#### 1.5.2 L1-L6 PASS/FAIL 判定式 (旧 §1.2、healthcheck_l1_l6.sh 整合版)

| チェック | PASS 条件 | FAIL 条件 | 備考 |
|---|---|---|---|
| **L1 インフラ** | コンテナ ≥7 Up AND 内部 `/health` 200 AND 外形 `/health` 200 | いずれか1つでも失敗 | 8コンテナ構成: blue/green/frontend/nginx/postgres/loki/promtail/cloudflared |
| **L2 スケジューラ** | `scheduler_healthy=true` AND `last_judgment_age_min ≤ 270` AND `warnings=[]` | いずれか1つでも違反 | ⚠️ 現行コードは `60min` 閾値 (id=29 で `270min` に修正予定) |
| **L3 AI 判定** | `ai_decisions` 24h 件数 ≥ 3 | 2件以下 | 4時間間隔 → 24h で 5-6件期待、最低 3件 |
| **L4 ユーザー反応** | `proposals` 0件 OR `expired_rate < 0.5` | `expired_rate ≥ 0.5` | UAT 中: proposals 0件 → PASS |
| **L5 実取引** | 実取引 0件 OR `fail_rate < 0.2` | 実取引ありかつ `fail_rate ≥ 0.2` | UAT 中: `is_dry_run=false` が 0件 → PASS |
| **L6 収益** | `zero_value_snapshots < 50%` | `≥ 50%` → WARN のみ | WARN は全体 PASS 判定に影響しない |

**全体判定ロジック** (`healthcheck_l1_l6.sh` L375-382 と整合):
```
overall = PASS  ← L1 PASS AND L2 PASS AND L3 PASS AND L4 PASS AND L5 PASS
L6 WARN は overall=PASS に影響しない
```

#### 1.5.3「14日連続緑」(参考、旧 §1.3) カウント方法

**DB 側 (L3-L5)**: 下記 §5 のダッシュボード SQL で集計

**ログ側 (L1-L2)**: `/opt/ultra-autotrade/logs/healthcheck_l1_l6.log` を集計

```bash
# 直近 14 日の L1/L2 日別 PASS率 (Hetzner で実行)
python3 -c "
import re, sys, datetime
from collections import defaultdict

today = datetime.date.today()
cutoff = today - datetime.timedelta(days=14)
day_pass = defaultdict(int)
day_total = defaultdict(int)

with open('/opt/ultra-autotrade/logs/healthcheck_l1_l6.log') as f:
    for line in f:
        m = re.search(r'(\d{4}-\d{2}-\d{2}).*結果: L1=(PASS|FAIL) L2=(PASS|FAIL)', line)
        if not m:
            continue
        day_str = m.group(1)
        day = datetime.date.fromisoformat(day_str)
        if day < cutoff:
            continue
        l1, l2 = m.group(2), m.group(3)
        day_total[day_str] += 1
        if l1 == 'PASS' and l2 == 'PASS':
            day_pass[day_str] += 1

print('day          | total | pass | rate | green')
for day_str in sorted(day_total.keys()):
    t = day_total[day_str]
    p = day_pass[day_str]
    rate = p/t if t else 0
    green = '✅' if rate >= 0.95 else '❌'
    print(f'{day_str} | {t:5} | {p:4} | {rate:.1%} | {green}')
"
```

#### 1.5.4 L1-L6 現在値 (旧 §1.4、2026-05-18 時点、参考)

| 項目 | 現在値 | 判定 |
|---|---|---|
| L1 | containers_running=8/7, internal=200, external=200 | ✅ PASS |
| L2 | scheduler_healthy=true, last_judgment_age_min≈219 (閾値 bug: 60min → 要 270min) | ❌ FAIL |
| L3 | ai_decisions_24h=14 | ✅ PASS |
| L4 | proposals_24h=0 | ✅ PASS |
| L5 | real_tx_24h=0 (UAT 中正常) | ✅ PASS |
| L6 | zero_value_pct=100.0% | ⚠️ WARN (UAT 常態) |
| **全体** | L2 FAIL (閾値 bug、id=29 修正後 PASS 予定) | ❌ FAIL |
| **連続緑日数** | 0日 | ❌ 0/14 |

> **注**: id=29 で L2 閾値を 270min に修正後、実質的に L2 PASS になる見込み。  
> 修正マージ翌日 0:00 JST から連続緑カウント開始。

---

## 2. chaos test 3日連続失敗ゼロ

### 2.1 定義

**chaos test シナリオ** (staging 環境で実施):

| テスト | 手順 | PASS 条件 |
|---|---|---|
| postgres kill | `docker kill ultra-autotrade-postgres-staging` | 5分以内に自動再起動 + `/health` 200 復帰 |
| backend kill | `docker kill ultra-autotrade-backend-*-staging` | 5分以内に自動再起動 + `/health` 200 復帰 |
| nginx kill | `docker kill ultra-autotrade-nginx-staging` | 5分以内に自動再起動 + nginx が upstream を再解決 |
| Loki kill | `docker kill ultra-autotrade-loki-staging` | 5分以内に自動再起動 + promtail 接続復旧 |

**3日連続失敗ゼロ**: 上記シナリオを 3日連続で実施し、全回 PASS。

### 2.2 PASS 判定基準

1. kill 後 5分以内にコンテナが自動再起動 (`docker ps` で `Up X seconds` 確認)
2. 再起動後 2分以内に `/health` が 200 を返す
3. Loki に対象コンテナの `Exited` + `Started` ログが記録されている (観測性の確認)
4. staging の `ai_decisions` が chaos test 前後で継続して生成されている

### 2.3 現在値 (2026-05-18 時点)

| 項目 | 現在値 |
|---|---|
| chaos test 実施日数 | **未実施** |
| 判定 | ❌ 未計測 (id=10: A-2「Chaos test 月次計画」タスク waiting) |

---

## 3. 本番 Tier S 操作の人間承認率 100%

### 3.1 Tier S ファイル一覧

CLAUDE.md「Tier S: 同時編集禁止」より:

```
backend/app/main.py
backend/requirements.txt / pyproject.toml
frontend/package.json / frontend/package-lock.json
.github/workflows/ci.yml
docker-compose.production.yml / docker-compose.staging.yml
nginx/upstream.{production,staging}.conf
backend/migrations/versions/*.py (新規追加)
backend/app/database.py
backend/app/automation/scheduled_tasks.py
backend/app/automation/monitoring_service.py
backend/app/automation/workflow.py
CLAUDE.md
```

### 3.2 PASS 定義

| 条件 | 測定方法 |
|---|---|
| Tier S ファイルを含む全 PR に GitHub PR Approve ≥ 1件 | `gh pr list --state merged` + Tier S ファイルフィルタ |
| main への直接 push ゼロ (force push 含む) | `git log --merges origin/main` — non-merge commit がないこと |
| `--no-verify` / `--dangerously-skip-permissions` の本番使用ゼロ | Claude session logs の確認 |
| Step 0 スキップ (朝プロトコル §9) ゼロ | 朝プロトコルログの Step 0 実行証跡 |

### 3.3 測定コマンド (GitHub PR Approve 確認)

```bash
# Tier S ファイルを含む merged PR に Approve があるか確認
# (ローカル Mac で実行、gh CLI 必要)

TIER_S_PATTERN='main\.py$|requirements\.txt|pyproject\.toml|package\.json|package-lock\.json|ci\.yml|docker-compose\.(production|staging)\.yml|upstream\.(production|staging)\.conf|database\.py|scheduled_tasks\.py|monitoring_service\.py|workflow\.py|CLAUDE\.md'

gh pr list --state merged --limit 50 --json number,title,reviews \
  --jq '.[] | {number, title, approved: ([.reviews[].state] | any(. == "APPROVED"))}' \
| python3 -c "
import sys, json

# NOTE: gh pr list は files を含まないため、別途 pr view で取得
print('PR# | approved | title')
for line in sys.stdin:
    pr = json.loads(line.strip())
    print(f\"#{pr['number']} | {'✅' if pr['approved'] else '❌'} | {pr['title'][:60]}\")
"

# Tier S ファイル変更 PR の特定は個別に確認:
# gh pr view <PR番号> --json files --jq '.files[].path' | grep -E '<TIER_S_PATTERN>'
```

### 3.4 Step 0 強制化との連携 (PR #246)

PR #246 (7cec8f1) で追加された CLAUDE.md §9 Step 0 強制化:
- `claude.ai` は朝プロトコル §9 開始前に CLI で `CLAUDE.md` + `production_operation_checklist.md` を cat することが必須
- Step 0 未完了時: `§9 進行不可` を返し、他の作業を受け付けない
- 連続違反: claude.ai の「設計判断資格を失う」制度的罰則

**Step 0 スキップ測定 (現在: 未実装)**:
```bash
# 将来実装: 朝プロトコルログに Step 0 実行証跡を記録
# /opt/ultra-autotrade/logs/morning_protocol.log で以下のパターンを確認:
grep "Step 0 確認済" /opt/ultra-autotrade/logs/morning_protocol.log | wc -l
# 0件 = Step 0 記録機能が未実装
```

### 3.5 現在値 (2026-05-18 時点)

| 項目 | 現在値 |
|---|---|
| 直近 Tier S PR の Approve 状況 | 未計測 (gh CLI で個別確認必要) |
| main への直接 push | 未確認 |
| `--no-verify` 本番使用 | 未確認 |
| Step 0 スキップ記録機能 | ❌ 未実装 (要別 Tier B タスク) |
| 判定 | ❌ 未計測 |

---

## 4. Partner UAT 完走

> 2026-05-28 改訂: 2 partner 体制（山本+橋口）対応。SQL を `user_id=11` ハードコードから `role='partner' AND is_active=TRUE` 一般化（Asana 1215185448109917）。
> 詳細閾値・partner 別内訳 SQL は `docs/uat_completion_criteria.md` 参照。

### 4.1 定義

「Partner UAT 完走」= 以下の**全条件**を満たす状態:

| 条件 | 測定方法 |
|---|---|
| UAT シナリオ全ステップ実行完了 | Asana id=16 (A-4) タスクで閾値詳細化中 |
| 全 partner (`role='partner' AND is_active=TRUE`) の active な未完了 proposals が 0 | `non_executed_active = 0` (下記 SQL) |
| partner 合算で proposals が実際に生成・承認フローを経ている | `total_proposals ≥ 5` かつ `executed ≥ 1` |
| 各 partner から小林さんへの明示的承認メッセージ受領 | DM 確認 (非自動化) |

> **注**: id=16 Lane で proposals 全件 EXECUTED の数値閾値を詳細化済 (`docs/uat_completion_criteria.md` PR #251 → Asana 1215185448109917 改訂)。本ドキュメントは枠組みのみ。

### 4.2 UAT 完走判定 SQL

```sql
-- Partner UAT 状態確認 (role='partner' AND is_active=TRUE で合算)
WITH partners AS (
  SELECT id FROM users WHERE role = 'partner' AND is_active = TRUE
)
SELECT
  (SELECT COUNT(*) FROM proposals p JOIN partners ON partners.id = p.user_id) AS total_proposals,
  (SELECT COUNT(*) FROM proposals p JOIN partners ON partners.id = p.user_id WHERE p.status = 'executed') AS executed,
  (SELECT COUNT(*) FROM proposals p JOIN partners ON partners.id = p.user_id WHERE p.status = 'expired')  AS expired,
  (SELECT COUNT(*) FROM proposals p JOIN partners ON partners.id = p.user_id WHERE p.status = 'rejected') AS rejected,
  (SELECT COUNT(*)
     FROM proposals p
     JOIN partners ON partners.id = p.user_id
    WHERE p.status NOT IN ('executed', 'expired', 'rejected')
      AND p.expires_at > NOW()) AS non_executed_active,
  -- UAT 完走候補判定: active な未完了 proposals が 0件かつ partner 合算 total >= 5
  CASE
    WHEN (SELECT COUNT(*) FROM proposals p JOIN partners ON partners.id = p.user_id) < 5
      THEN 'WAITING (proposals 生成待ち)'
    WHEN (SELECT COUNT(*) FROM proposals p JOIN partners ON partners.id = p.user_id
          WHERE p.status NOT IN ('executed','expired','rejected')
            AND p.expires_at > NOW()) = 0
      THEN 'CANDIDATE (最終承認 DM 待ち)'
    ELSE 'IN_PROGRESS'
  END AS uat_state;
```

partner 別内訳は `docs/uat_completion_criteria.md` § partner 別内訳 SQL を参照。

### 4.3 現在値 (2026-05-28 改訂時点)

| 項目 | 現在値 |
|---|---|
| UAT 進行段階 | 山本さん wallet `0x2064...cc66` 登録済、橋口さん 2026-06-01 までに wallet 登録予定。proposals 生成待ち |
| total_proposals (partner 合算) | 旧値（2026-05-18, 山本さん単独）2件 expired のみ。本 PR マージ後に partner 合算で再計測 |
| non_executed_active | 0件 (proposals 自体が未生成のため) |
| partner 承認 DM | 未受領 |
| 判定 | ❌ 未完走 (proposals 生成・承認フロー未到達) |

---

## 5. 森先生 法務確認

### 5.1 定義

| 確認対象 | 内容 |
|---|---|
| BVI 設立 | BVI 法人でのサービス運営の適法性 |
| non-custodial 構造 | ユーザー資産をカストディしない構造の法的扱い |
| 日本居住者向け配信 | 金融商品取引法 / 資金決済法との整合性 |

**判定条件**: 森先生から「問題なし」または「条件付き OK」の文書・メッセージ受領

### 5.2 現在値 (2026-05-18 時点)

| 項目 | 現在値 |
|---|---|
| 森先生への DM | 未送信 (Asana id=9: A-5「5/22 までに DM」) |
| 回答受領 | ❌ 未受領 |
| 判定 | ❌ 未確認 |

---

## 6. ローンチ判断ダッシュボード SQL

本番 postgres から 1 コマンドで DB 側全項目の状態を取得するクエリ。

**実行方法** (Hetzner SSH):

```bash
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -t -A \
  -f /opt/ultra-autotrade/scripts/launch_dashboard.sql
```

> `scripts/launch_dashboard.sql` として別ファイル化済み (以下と同内容)。

```sql
-- ============================================================
-- Ultra AutoTrade ローンチ判断ダッシュボード
-- 実行: docker exec <postgres> psql -U ultra -d ultra_autotrade -t -A -f scripts/launch_dashboard.sql
-- ============================================================

WITH
now_jst AS (
  SELECT NOW() AT TIME ZONE 'Asia/Tokyo' AS ts
),

-- L3: 直近 14日の ai_decisions 日別集計
l3_daily AS (
  SELECT
    DATE(created_at AT TIME ZONE 'Asia/Tokyo') AS day,
    COUNT(*) AS cnt
  FROM ai_decisions
  WHERE created_at > NOW() - INTERVAL '14 days'
  GROUP BY DATE(created_at AT TIME ZONE 'Asia/Tokyo')
),
l3_summary AS (
  SELECT
    COUNT(*) FILTER (WHERE cnt >= 3)  AS green_days,
    COUNT(*) FILTER (WHERE cnt < 3)   AS red_days,
    COALESCE(MIN(cnt), 0)             AS min_daily,
    COALESCE(MAX(cnt), 0)             AS max_daily,
    COALESCE(SUM(cnt), 0)             AS total_14d
  FROM l3_daily
),

-- L4: 直近 14日の proposals 日別集計
l4_daily AS (
  SELECT
    DATE(created_at AT TIME ZONE 'Asia/Tokyo') AS day,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE status = 'expired') AS expired_cnt,
    COALESCE(
      ROUND(COUNT(*) FILTER (WHERE status='expired')::numeric / NULLIF(COUNT(*),0) * 100, 1),
      0
    ) AS expired_pct
  FROM proposals
  WHERE created_at > NOW() - INTERVAL '14 days'
  GROUP BY DATE(created_at AT TIME ZONE 'Asia/Tokyo')
),
l4_summary AS (
  SELECT
    COUNT(*) FILTER (WHERE total = 0 OR expired_pct < 50) AS green_days,
    COUNT(*) FILTER (WHERE total > 0 AND expired_pct >= 50) AS red_days
  FROM l4_daily
),

-- L5: 直近 14日の transactions 日別集計
l5_daily AS (
  SELECT
    DATE(created_at AT TIME ZONE 'Asia/Tokyo') AS day,
    COUNT(*) FILTER (WHERE is_dry_run = false) AS real_cnt,
    COUNT(*) FILTER (WHERE tx_hash IS NULL AND is_dry_run = false) AS failed_cnt,
    COALESCE(
      ROUND(
        COUNT(*) FILTER (WHERE tx_hash IS NULL AND is_dry_run = false)::numeric
        / NULLIF(COUNT(*) FILTER (WHERE is_dry_run = false), 0) * 100,
      1), 0) AS fail_pct
  FROM transactions
  WHERE created_at > NOW() - INTERVAL '14 days'
  GROUP BY DATE(created_at AT TIME ZONE 'Asia/Tokyo')
),
l5_summary AS (
  SELECT
    COUNT(*) FILTER (WHERE real_cnt = 0 OR fail_pct < 20) AS green_days,
    COUNT(*) FILTER (WHERE real_cnt > 0 AND fail_pct >= 20) AS red_days
  FROM l5_daily
),

-- 直近 24h スナップショット
recent AS (
  SELECT
    (SELECT COUNT(*) FROM ai_decisions
     WHERE created_at > NOW() - INTERVAL '24 hours')                         AS ai_24h,
    (SELECT COUNT(*) FROM proposals
     WHERE created_at > NOW() - INTERVAL '24 hours')                         AS proposals_24h,
    (SELECT COUNT(*) FROM transactions
     WHERE is_dry_run = false AND created_at > NOW() - INTERVAL '24 hours')  AS real_tx_24h,
    (SELECT COALESCE(SUM(CASE WHEN total_value_usd = 0 THEN 1 ELSE 0 END), 0)
       * 100.0 / NULLIF(COUNT(*), 0)
     FROM portfolio_snapshots
     WHERE recorded_at > NOW() - INTERVAL '24 hours')                        AS l6_zero_pct
),

-- Partner UAT 状態 (2026-05-28: 2 partner 化 / role='partner' AND is_active=TRUE 一般化)
uat AS (
  SELECT
    COUNT(*)                                                                   AS total,
    COUNT(*) FILTER (WHERE p.status = 'executed')                              AS executed,
    COUNT(*) FILTER (WHERE p.status NOT IN ('executed','expired','rejected')
                     AND p.expires_at > NOW())                                 AS active_non_exec
  FROM proposals p
  JOIN users u ON u.id = p.user_id
  WHERE u.role = 'partner' AND u.is_active = TRUE
)

SELECT '============================================' AS metric, '' AS value
UNION ALL SELECT 'ローンチ判断ダッシュボード', (SELECT ts::text FROM now_jst)
UNION ALL SELECT '============================================', ''

UNION ALL SELECT '--- DB 側指標 (L3-L5 過去 14日) ---', ''

UNION ALL SELECT 'L3 (AI判定) 14日緑日数',
  (SELECT green_days || '/14 日 PASS (要: 14/14) | min=' || min_daily || ' max=' || max_daily FROM l3_summary)
UNION ALL SELECT 'L3 RED 日数',
  (SELECT red_days || '日 (ai_decisions < 3/day)' FROM l3_summary)

UNION ALL SELECT 'L4 (user反応) 14日緑日数',
  (SELECT green_days || '/14 日 PASS (要: 14/14)' FROM l4_summary)
UNION ALL SELECT 'L4 RED 日数',
  (SELECT red_days || '日 (expired_rate >= 50%)' FROM l4_summary)

UNION ALL SELECT 'L5 (実取引) 14日緑日数',
  (SELECT green_days || '/14 日 PASS (要: 14/14)' FROM l5_summary)
UNION ALL SELECT 'L5 RED 日数',
  (SELECT red_days || '日 (real tx fail_rate >= 20%)' FROM l5_summary)

UNION ALL SELECT '--- 直近 24h ---', ''
UNION ALL SELECT 'L3 ai_decisions_24h', (SELECT ai_24h::text || ' 件 (要: ≥3)' FROM recent)
UNION ALL SELECT 'L4 proposals_24h',    (SELECT proposals_24h::text || ' 件' FROM recent)
UNION ALL SELECT 'L5 real_tx_24h',      (SELECT real_tx_24h::text || ' 件 (0=UAT中正常)' FROM recent)
UNION ALL SELECT 'L6 zero_value_pct',   (SELECT ROUND(COALESCE(l6_zero_pct,0),1)::text || '% (100%=UAT常態)' FROM recent)

UNION ALL SELECT '--- 山本さん UAT ---', ''
UNION ALL SELECT 'total_proposals(id=11)',    (SELECT total::text FROM uat)
UNION ALL SELECT 'executed proposals(id=11)', (SELECT executed::text FROM uat)
UNION ALL SELECT 'active_non_exec(id=11)',    (SELECT active_non_exec::text || ' (0=CANDIDATE)' FROM uat)
UNION ALL SELECT 'UAT 状態',
  (SELECT CASE
    WHEN total < 5   THEN 'WAITING (proposals 生成待ち, 要: total≥5)'
    WHEN active_non_exec = 0 THEN 'CANDIDATE (最終承認 DM 待ち)'
    ELSE 'IN_PROGRESS (' || active_non_exec || ' 件 active)'
  END FROM uat)

UNION ALL SELECT '--- DB 外指標 (別途確認) ---', ''
UNION ALL SELECT 'L1/L2 14日緑', 'grep healthcheck_l1_l6.log で確認 (§1.3 参照)'
UNION ALL SELECT 'chaos test',   'id=10 タスク waiting'
UNION ALL SELECT 'Tier S Approve', 'gh pr list --state merged で確認 (§3.3 参照)'
UNION ALL SELECT '森先生法務',    'id=9 A-5: 5/22 DM 予定'
UNION ALL SELECT '============================================', ''
;
```

---

## 7. ローンチ判断サマリー (2026-05-18 時点)

| 条件 | 現在値 | 判定 | ブロッカー / 次アクション |
|---|---|---|---|
| 両 partner 本運用 14日 (2026-05-28 改訂 / 旧「L1-L6 14日連続緑」) | 0/14 日 (起算前) | ❌ 未達 | 6/1 (Day 1) 起算 → 6/14 達成 → 6/15 full launch。起算条件: 山本さん wallet 登録済、橋口さん wallet 6/1 までに登録 + scheduler flag conflict (Asana 1215153474346999) 解消 + 本 PR merge |
| chaos test 3日連続 | 未実施 | ❌ 未計測 | id=10 タスク起動 |
| Tier S 承認率 100% | 未計測 | ❌ 未計測 | gh CLI 計測 + Step 0 記録機能実装 |
| 山本さん UAT 完走 | 進行中 | ❌ 未完走 | proposals 生成フロー到達待ち |
| 森先生 法務確認 | 未送信 | ❌ 未確認 | 5/22 DM 送信 (id=9) |
| **総合** | **0/5 green** | ❌ **ローンチ不可** | L2 修正 → 14日緑積み上げ → 他項目並行 |

---

## 8. ローンチ判断フロー

> **2026-05-28 改訂注記**: 旧フロー (L2 閾値 270min 修正 → L1-L6 14日連続緑) は条件 1 改訂で **判定軸ではなく参考指標** に移行 (§1.5)。新フローでは「両 partner wallet 登録 + scheduler flag conflict 解消 + 本 PR merge → 6/1 (Day 1) 起算 → 6/14 達成」が条件 1 の流れ。下記フロー図は旧版のままだが、6/1 launch を狙う実機は §1.3 を正本とする(本フロー図は次版 v2.2 で書き換え予定)。

```
[現在 2026-05-18]
       │
       ▼
L2 閾値 270min 修正 (id=29, Tier B) ─────────────────────┐
       │                                                    │
       ▼                                                    ▼ 並行
L1-L6 14日連続緑 積み上げ開始 (5/18 L2 修正後から)    chaos test (id=10)
       │                                                    │
       │  ─── 並行 ───────────────────────────────────────┤
       │                                                    │
       │  山本さん UAT 完走 (proposals フロー稼働)          │
       │  森先生 法務 DM (id=9, 5/22 予定)                 │
       │  Tier S 承認率計測実装                             │
       │                                                    │
       ▼ (全5条件 GREEN)                                   ▼
ローンチ判断会議 (小林さん + 山本さん合意)
       │
       ▼
ローンチ日決定 → deploy_production.sh (実資金フル稼働)
```

---

## 9. 変更履歴

| 日付 | バージョン | 変更内容 |
|---|---|---|
| 2026-05-18 | v2.0 | 新規作成。§17 v5 原文を客観指標に落とし込み。healthcheck_l1_l6.sh (PR #247) と整合 |
| 2026-05-28 | v2.1 | **§17 条件 1 改訂**: 旧「L1-L6 14日連続緑」→ 新「両 partner (山本+橋口) 本運用 14日」(Asana 1215186751757662 / Lane H 案採用 / userMemories #8 訂正済)。L1-L6 評価詳細は §1.5 に移植し参考指標として保持。§7 サマリー / §8 フロー注記更新。**6/1 (Day 1) 両 partner 本運用 launch → 6/14 達成 → 6/15 full launch**。旧 §17 原文は下記アーカイブに保存。 |

### 9.1 旧 §17 原文アーカイブ (2026-05-18 〜 2026-05-28)

```
5/31 強行はしない。客観条件で判断:
- L1-L6 14日連続緑                                                ← 2026-05-28 改訂で削除、新条件 1 に置換
- staging で chaos test 3日連続失敗ゼロ
- 本番 Tier S 操作の人間承認率 100% (auto-bypass ゼロ)
- 山本さん UAT 完走 (proposals 全件 EXECUTED 判定基準満たす)
- 森先生 法務確認 (BVI / non-custodial)
```
