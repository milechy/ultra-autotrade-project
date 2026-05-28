# Roadmap to Launch (v1 — Skeleton + §17 原文転記)

> **ステータス**: SKELETON / DRAFT (2026-05-20 起票、同日 §17 原文転記で §1 5条件本文確定)
> **本文確定**: 部分 — §1 5条件本文は `docs/launch_decision_criteria_v2.md` §17 原文 (L11-18) からの実コピー転記済み。§2 (6/3 シナリオ計算) / §4 / §6 は依然 TBD。
> **本文埋め担当**: 小林さん (claude.ai の 6/3 シナリオ計算原文を §2 に貼付)
> **完了条件**: §2 / §4 / §6 の TBD が消え、6/3 シナリオを実機データで再計算した数値表が埋まり、L1-L6 PASS 率 + approval_rate + UAT 14日観測の3軸が定量化されること

---

## 0. メタ情報

| 項目 | 値 |
|---|---|
| ローンチ目標日 (claude.ai 提案 v1) | **2026-06-03** (最早シナリオ) |
| 並列構成 | Tier B 4本並列 |
| handoff thread | https://mooores.slack.com/archives/C0ACS09FMGC/p1779245661503999 |
| **§17 原文格納先** | **`docs/launch_decision_criteria_v2.md` L11-18 (PR #254 merge 済、2026-05-18)** |
| **§17「14日連続緑」定義** | **`docs/l1_l6_evaluation_v1.md` §2-§3 (PR #252 merge 済、2026-05-18)** |
| **§17 原文の判断方針** | **「5/31 強行はしない。客観条件で判断」(`docs/launch_decision_criteria_v2.md` §17 原文より)** |
| Asana ハブ GID | [TBD: 小林さんが起票後追記] |
| 関連 Asana プロジェクト | 1213741124336104 (Phase 1-2 機能タスク), 1213916581114014 (本番運用・パートナー実運用) |
| 起票セッション | dev VPS `/opt/ultra-autotrade/main` (Claude Code CLI / Opus 4.7) |
| 前 session (handoff 元) | `/home/uata` — settings.json `defaultMode: dontAsk` + `additionalDirectories` が Mac パスのみで silent deny |

---

## 1. ローンチ判定 5条件

> **正本**: `docs/launch_decision_criteria_v2.md` (PR #254 merge 済 2026-05-18)。本章は同 docs §17 原文 (L11-18) の **実コピー転記** + 各条件の詳細仕様への link。**言い回し変更・要約・補足は禁止** (CLAUDE.md §2026-04-21 教訓 §再発防止ルール 4: memory からの推論拡大禁止)。

### §17 原文 (`docs/launch_decision_criteria_v2.md` L11-18 より実コピー)

```
5/31 強行はしない。客観条件で判断:
- L1-L6 14日連続緑
- staging で chaos test 3日連続失敗ゼロ
- 本番 Tier S 操作の人間承認率 100% (auto-bypass ゼロ)
- 山本さん UAT 完走 (proposals 全件 EXECUTED 判定基準満たす)
- 森先生 法務確認 (BVI / non-custodial)
```

---

### 条件 1: L1-L6 14日連続緑
- **詳細仕様**: `docs/launch_decision_criteria_v2.md` §1 (PASS/FAIL 判定式 + healthcheck_l1_l6.sh 整合版)
- **14日連続緑の定義**: `docs/l1_l6_evaluation_v1.md` §2-§3 (日次緑 = `pass_rate ≥ 0.95` かつ `daily_total ≥ 240`、14日連続 = streak == 14)
- **現状値 (2026-05-18 時点、`launch_decision_criteria_v2.md` §1.4 より)**: 0/14 日 (L2 閾値 bug、id=29 修正後カウント開始予定)
- **6/3 達成見込み**: L2 修正翌日 0:00 JST から 14日積み上げ。L2 修正日次第 (本ロードマップでは TBD、Lane 2 で実機集計)
- **依存タスク**: id=29 L2 閾値 270min 修正 (Tier B)

### 条件 2: staging で chaos test 3日連続失敗ゼロ
- **詳細仕様**: `docs/launch_decision_criteria_v2.md` §2 (postgres / backend / nginx / Loki kill シナリオ、5分以内自動再起動 + `/health` 200 復帰)
- **PASS 判定基準** (同 docs §2.2): kill 後 5分以内自動再起動 / 再起動後 2分以内 `/health` 200 / Loki に `Exited`+`Started` 記録 / chaos 前後で `ai_decisions` 継続生成
- **現状値 (2026-05-18 時点、同 docs §2.3)**: 未実施 (id=10 A-2 タスク waiting)
- **6/3 達成見込み**: Lane 1 (chaos test、`docs/launch/lanes/lane1_chaos_test.md`) で 3日連続実行
- **依存タスク**: Lane 1 起動 (5/20 16:00 以降)

### 条件 3: 本番 Tier S 操作の人間承認率 100% (auto-bypass ゼロ)
- **詳細仕様**: `docs/launch_decision_criteria_v2.md` §3 (Tier S ファイル一覧 + PR Approve + main 直 push ゼロ + `--no-verify` 本番使用ゼロ + Step 0 スキップゼロ)
- **Tier S ファイル一覧** (同 docs §3.1): `main.py` / `requirements.txt` / `pyproject.toml` / `package.json` / `package-lock.json` / `ci.yml` / `docker-compose.*` / `upstream.*.conf` / `database.py` / `scheduled_tasks.py` / `monitoring_service.py` / `workflow.py` / CLAUDE.md / `alembic/versions/*.py`
- **現状値 (2026-05-18 時点、同 docs §3.5)**: 未計測 (gh CLI 計測 + Step 0 記録機能未実装)
- **6/3 達成見込み**: 計測機能実装 (別 Tier B タスク) + 直近 PR の Approve 状況確認後に評価
- **依存タスク**: Step 0 記録機能実装 (要別タスク起票)

### 条件 4: Partner UAT 完走 (proposals 全件 EXECUTED 判定基準満たす)
- **詳細仕様**: `docs/launch_decision_criteria_v2.md` §4 (UAT 完走 SQL: `non_executed_active = 0` かつ `total_proposals ≥ 5` かつ `executed ≥ 1` + 各 partner から明示承認 DM)
- **判定 SQL** (同 docs §4.2): `proposals` JOIN `users` WHERE `role='partner' AND is_active=TRUE` の group by status + uat_state 判定 CASE 式（2026-05-28 改訂で 2 partner 化 / Asana 1215185448109917）
- **partner 別内訳 SQL**: `docs/uat_completion_criteria.md` § partner 別内訳 SQL（合算で達成しても 1 partner に集中していないか確認）
- **現状値 (2026-05-28 改訂時点)**: ❌ 未完走 (旧山本さん単独 total_proposals=2 expired のみ / 橋口さん proposals 未生成 / partner 合算 baseline は本改訂後再計測)
- **5/20 進捗**: P0-X2 fund_allocations $4,600 INSERT 完了 (Asana 1214825504961756 / id=6 / 2026-05-20 04:49:51 UTC) — UAT proposals 生成フローの起算点が立った
- **5/28 進捗**: 橋口さん (id=18, role=partner) を `users` テーブルに INSERT 済。山本さん wallet `0x2064...cc66` 登録済、橋口さん 2026-06-01 までに wallet 登録予定 — 2 partner 並走で UAT を回す体制が整った
- **6/3 達成見込み**: proposals 5 件以上生成 + 全件 EXECUTED/EXPIRED/REJECTED + 各 partner 承認 DM。proposals 生成速度に依存 (TBD)
- **依存タスク**: id=16 (A-4) UAT 完走閾値詳細化 / 橋口さん wallet 登録 (6/1 までに) → 2 partner 体制で proposals 生成

### 条件 5: 森先生 法務確認 (BVI / non-custodial)
- **詳細仕様**: `docs/launch_decision_criteria_v2.md` §5 (BVI 設立 / non-custodial 構造 / 日本居住者向け配信)
- **判定条件** (同 docs §5.1): 森先生から「問題なし」または「条件付き OK」の文書・メッセージ受領
- **現状値 (2026-05-18 時点、同 docs §5.2)**: ❌ 未確認 (id=9 A-5「5/22 までに DM」未送信)
- **6/3 達成見込み**: Lane 4 (森先生 DM、`docs/launch/lanes/lane4_mori_dm.md`) で 5/22 までに DM 草案 → 小林さん本人送信 → 回答受領
- **依存タスク**: Lane 4 起動 (本日 16:00 最優先)

---

## 2. 6/3 シナリオ採用根拠 (実機データ再計算)

> **TBD**: claude.ai の「6/3 最早 / 4本並列」案の元計算と、本日の実機データによる再計算結果。
> handoff 記載の「ユーザーが指摘してほしいと明示した点」7項目を本章に反映する必要がある:
>
> 1. 6/3-6/5 最早が本当に最早か実機ベースで再計算
> 2. 各条件の進捗が引継ぎパッケージの数字を鵜呑みにしただけ
> 3. Partner UAT 14日観察が 5/25 - 6/8 で完走できるか (現状 100% HOLD / 2026-05-28 から 2 partner 体制)
> 4. chaos test 3日連続が staging で実施可能か (PR #253 実機状態未確認)
> 5. 並列 4本構成の Tier S 禁止ファイル抵触リスク
> 6. 抜けているリスク (HUMAN-REVIEW 14本処理 / v4 反映後の観察期間 / 橋口さん wallet 接続 (6/1 までに登録予定 / 山本さんは 0x2064...cc66 登録済) / 営業チーム運用 docs / Phase 2 機能の Phase 1 ローンチ前必要性)
> 7. (handoff 内に明示なし)

### 2.1 起算点と着地点 (calendar 計算)

| 起算イベント | 起算日 (実機) | 必要日数 | 着地日 |
|---|---|---|---|
| Partner UAT 開始 (P0-X2 INSERT) | 2026-05-20 04:49:51 UTC (Asana 1214825504961756 / id=6 完了 / 2026-05-28 から 2 partner 体制: 山本=id 11 wallet 登録済、橋口=id 18 wallet 6/1 まで登録予定) | proposals 生成速度依存 (TBD) | TBD |
| chaos test 3日連続 | TBD (Lane 1 起動次第) | 3日 + 観測 1日 | TBD |
| HUMAN-REVIEW 14本処理完了 | TBD | TBD | TBD |
| v4 反映後の観察期間 | 2026-05-19 (PR #302 merge済) | TBD | TBD |
| L1-L6 14日 PASS 率 100% | L2 閾値 270min 修正 (id=29) 翌日 0:00 JST | 14日 | TBD |

### 2.2 critical path

[TBD — 上記計算から逆算した critical path 図]

### 2.3 6/3 vs 6/5 vs 6/8 比較表

[TBD — claude.ai 提案 v1 の 3 シナリオ比較。本セッションでは元データ無いため再構築不可]

### 2.4 launch_decision_criteria_v2.md §7 ローンチ判断サマリー (2026-05-18 時点、参考)

| 条件 | 現在値 | 判定 | ブロッカー / 次アクション (同 docs §7 より) |
|---|---|---|---|
| L1-L6 14日連続緑 | 0/14 日 | ❌ 未達 | L2 閾値 270min 修正 (id=29) → 修正後から連続緑カウント開始 |
| chaos test 3日連続 | 未実施 | ❌ 未計測 | id=10 タスク起動 |
| Tier S 承認率 100% | 未計測 | ❌ 未計測 | gh CLI 計測 + Step 0 記録機能実装 |
| Partner UAT 完走 (山本+橋口) | 進行中 | ❌ 未完走 | proposals 生成フロー到達待ち (5/20 INSERT 完了で起点進行 / 5/28 から 2 partner 体制) |
| 森先生 法務確認 | 未送信 | ❌ 未確認 | 5/22 DM 送信 (id=9 / Lane 4) |
| **総合** | **0/5 green** | ❌ **ローンチ不可** (2026-05-18 評価) | L2 修正 → 14日緑積み上げ → 他項目並行 |

> 本表は `docs/launch_decision_criteria_v2.md` §7 の 2026-05-18 時点スナップショット。本ロードマップ確定後は本表の更新タイミングを Lane 2 (approval_rate / KPI 集計) と合わせる。

---

## 3. Tier B 4本並列レーン構造 (本日 16:00 までに指示書作成)

> handoff から確定。各レーンの **詳細指示書** は別 docs / Asana タスク で起票する。本章は「並列構成として確定した」事実のみ記載。

| Lane | テーマ | 想定成果物 | Tier 判定 (CLAUDE.md §Tier 分類) | Tier S 抵触リスク |
|---|---|---|---|---|
| Lane 1 | chaos test script | `scripts/chaos_test_*.sh` 新規 + staging で 3日連続実行記録 | Tier B (scripts/ 新規ファイル) | なし |
| Lane 2 | approval_rate 計測 script | `scripts/measure_approval_rate.sh` + backend SQL query module | Tier B (scripts/ + 新規 SQL) / 既存テーブル read のみなら Tier B | `backend/app/main.py` 触らない限り B |
| Lane 3 | 営業チーム運用 docs | `docs/sales/` 配下に運用 SOP / 顧客対応フロー | Tier B (docs/ 新規) | なし |
| Lane 4 | 森先生 (法務) DM 草案 | `docs/legal/mori_dm_draft_*.md` 草案 | Tier B (docs/ 新規) | なし — **送信は claude.ai 文面禁止ルール (§10) に従い小林さん本人が送信** |

### 3.1 並列実行手段

CLAUDE.md §「Claude Code Agent View 運用」に従い、Agent View (`claude agents` → `/bg`) で 4 Lane 起動。tmux 多分割は廃止済み。

### 3.2 4本同時の Tier S 抵触チェック

並列 4 Lane が触る可能性のあるファイルを事前列挙し、Tier S (1日1PR) と衝突しないことを確認:

| Lane | 触る可能性のあるファイル | Tier 判定 | 同時編集衝突可能性 |
|---|---|---|---|
| 1 | `scripts/` 新規ファイルのみ | B | なし |
| 2 | `scripts/` 新規 + `backend/app/automation/*.py` (read のみ想定) | B | `scheduled_tasks.py` を write する場合のみ Tier S 抵触 |
| 3 | `docs/sales/` 新規ファイルのみ | B | なし |
| 4 | `docs/legal/` 新規ファイルのみ | B | なし |

**4本並列 = Tier S 抵触なし** を確認できれば本構成は CLAUDE.md §並列開発フロー v4 鉄則 4 (並列レーンは Tier B のみで構成) に準拠。

---

## 4. 実機データ再計算 (取得済みのみ記載)

> 2026-05-20 fetch 時点で確実な事実のみ。推測値は記載しない。

### 4.1 Asana 既知 6 GID 状態 (handoff 記載)

[TBD: 個別 GID と状態を貼付。handoff 内に「6 GID 状態」とあるが詳細未記載]

### 4.2 HOLD bias v4 完了状況

- GID 1214890565948368: **completed (2026-05-19, PR #302 merge済)**
- memory `phase1-progress-20260519` の「Pushover 通知済み → staging 反映待ち」記述は **陳腐化**

### 4.3 L1-L6 14日 PASS 率

- **評価方法は `docs/l1_l6_evaluation_v1.md` で定義済** (PR #252 merge 済 2026-05-18)
  - §1 項目定義 + 重み (L1/L2/L5=critical / L3/L4=normal / L6=warning-only)
  - §2 「日次緑」= 1日 (JST 00:00-23:59) の `*/5` cron 全 288 回のうち `overall=PASS` が 95% 以上 + 最低 240 ラン
  - §3 「14日連続緑」= 直近 14日連続で「日次緑」、`pass_rate < 0.95` or `daily_total < 240` or ログ不在で streak リセット
- **集計スクリプト**: `scripts/l1_l6_daily_summary.sh` (PR #252 同梱) + healthcheck log (`/opt/ultra-autotrade/logs/healthcheck_l1_l6.log`)
- **直近 14日集計実行**: Lane 2 で実施予定 (`docs/launch/lanes/lane2_approval_rate.md` Step 3)

### 4.4 production AI 判定 24h KPI (CLAUDE.md §2026-05-13 教訓 策1)

```sql
-- 本ロードマップの定量化に必須。Lane 2 (approval_rate) と同時取得
SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';
SELECT COUNT(*), MAX(created_at) FROM proposals WHERE created_at > NOW() - INTERVAL '24 hours';
SELECT final_action, COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY final_action;
```

実行結果: [TBD — 取得予定]

### 4.5 ローンチ判断ダッシュボード SQL (1 コマンド集計)

`docs/launch_decision_criteria_v2.md` §6 + `scripts/launch_dashboard.sql` (本番 postgres から 1 コマンドで DB 側全項目状態を取得):

```bash
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -t -A \
  -f /opt/ultra-autotrade/scripts/launch_dashboard.sql
```

集計対象: L3 (ai_decisions 14日)、L4 (proposals expired_rate)、L5 (transactions fail_rate)、直近 24h スナップショット、Partner UAT (`role='partner' AND is_active=TRUE` で合算: 山本 id=11 + 橋口 id=18) 状態。

---

## 5. 既知ブロッカー (handoff から確定)

| ID | 内容 | 状態 | 影響 |
|---|---|---|---|
| ~~P0-X2~~ | ~~山本さん INSERT が 4日 overdue~~ | **✅ closed (2026-05-20 04:49:51 UTC, Asana 1214825504961756 / id=6)** | 条件 4 (UAT proposals 全件 EXECUTED) の起算点が確定 |
| P3 | (詳細未記載) | 7日以上 overdue | TBD |
| P2 | (詳細未記載) | 7日以上 overdue | TBD |
| P0-X1 | (詳細未記載) | 7日以上 overdue | TBD |

3件が 7日以上 overdue、全件 assignee=小林さん専権 (P0-X2 close で残り 3 件)。

---

## 6. Phase X 起動条件

[TBD — 6/3 ローンチ後の Phase 2 (マルチプロトコル) 起動条件、Phase 3 (multi-tier capital) 起動条件等]

---

## 7. References

### docs (リポジトリ内)

| ファイル | 関連章 | 状態 |
|---|---|---|
| `CLAUDE.md` | 全章 (鉄則 7-10 / Tier 分類 / 教訓 2026-05-13 策1-20 等) | 正本 |
| `docs/launch_decision_criteria_v2.md` | §0 / §1 / §2.4 / §4.5 (§17 原文 + 全 5 条件の客観指標化 + ダッシュボード SQL) | **✅ PR #254 merge 済 (2026-05-18)** |
| `docs/l1_l6_evaluation_v1.md` | §0 / §1 条件 1 / §4.3 (L1-L6 評価方法 + 日次緑 / 14日連続緑の定義) | **✅ PR #252 merge 済 (2026-05-18)** |
| `scripts/healthcheck_l1_l6.sh` | §4.3 (cron `*/5 * * * *` で実行、L1-L6 PASS 判定) | 既存 (PR #247) |
| `scripts/l1_l6_daily_summary.sh` | §4.3 (日次集計スクリプト) | 既存 (PR #252) |
| `scripts/launch_dashboard.sql` | §4.5 (1 コマンドでローンチ判断ダッシュボード) | 既存 (PR #254) |
| `CLAUDE.md §17` (ローンチ 5条件) | §1 | **未作成** — 正本は `docs/launch_decision_criteria_v2.md`。CLAUDE.md への条文化は別 PR で検討 |
| `docs/22_production_release_checklist.md` | §3 (Tier B 並列) | 既存 |
| `docs/14_test_strategy.md` | §4 (実機データ Gate 4 / Gate 8) | 既存 |
| `docs/postmortems/2026-05-17_loki_postgres_cascade.md` | §5 (既知ブロッカーの教訓) | 既存 |
| `docs/postmortems/2026-05-17_backup_silent_failure.md` | §5 | 既存 |
| `docs/launch/lanes/lane1_chaos_test.md` | §1 条件 2 / §3 Lane 1 | 既存 (PR #325 merge 済 / PR #327 修正済) |
| `docs/launch/lanes/lane2_approval_rate.md` | §4.3 / §4.4 / §3 Lane 2 | 既存 (PR #325 merge 済) |
| `docs/launch/lanes/lane3_sales_ops.md` | §3 Lane 3 | 既存 (PR #325 merge 済) |
| `docs/launch/lanes/lane4_mori_dm.md` | §1 条件 5 / §3 Lane 4 | 既存 (PR #325 merge 済) |

### Slack

- handoff parent: `https://mooores.slack.com/archives/C0ACS09FMGC/p1779245661503999`
- #ultra-auto-project: `C0ACS09FMGC`

### Asana

- Phase 1-2 機能タスク: project `1213741124336104`
- 本番運用・パートナー実運用: project `1213916581114014`
- ローンチハブタスク: [TBD — 本 PR merge 後に起票]
- P0-X2 (closed): `1214825504961756` (2026-05-20 04:49:51 UTC)
- A-1 L1-L6 (closed): `1214888619973197` (2026-05-20、PR #252 / #254 完了で close)

---

## 改訂履歴

| 日付 | 版 | 変更 | 担当 |
|---|---|---|---|
| 2026-05-20 | v1.0-skeleton | 初版 (placeholder)。Tier B 4本並列構成のみ確定、本文 5条件・6/3 計算は TBD | Claude Code (dev VPS) |
| 2026-05-20 | v1.0-skeleton+criteria_link | §17 原文転記 (実コピー、`docs/launch_decision_criteria_v2.md` L11-18) + §References path 訂正 (`docs/launch/` 配下誤判定 → `docs/` 直下に修正) + §4.3 L1-L6 評価方法 link + §0 メタに criteria_v2 / l1_l6_v1 明記 + §2.1 起算点更新 (P0-X2 close) + §5 ブロッカー P0-X2 を closed 化 + §2.4 / §4.5 追加 (launch_decision_criteria_v2.md §7 / §6 への link) | Claude Code (dev VPS) |
| TBD | v1.0 | §2 / §4 / §6 の TBD 本文埋め (claude.ai 案の 6/3 計算原文反映) | 小林さん |
| TBD | v1.1 | 実機データ再計算結果反映 (Lane 2 完了後) | TBD |
