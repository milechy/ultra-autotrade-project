# Roadmap to Launch (v1 — Skeleton)

> **ステータス**: SKELETON / DRAFT (2026-05-20 起票)
> **本文確定**: 未 — claude.ai が今朝 (2026-05-20) 出した「6/3 最早 / 4本並列」案の本文は本セッションに引き継がれず、Slack thread にも保存されていない。本ファイルは **構造 (TOC) と Tier B 4本並列レーンの確定情報のみ** を保持する placeholder。
> **本文埋め担当**: 小林さん (claude.ai 案の原文を本ファイルに貼付)
> **完了条件**: 全章の `[TBD: ...]` が消え、6/3 シナリオを実機データで再計算した数値表が埋まり、L1-L6 PASS 率 + approval_rate + UAT 14日観測の3軸が定量化されること

---

## 0. メタ情報

| 項目 | 値 |
|---|---|
| ローンチ目標日 (claude.ai 提案 v1) | **2026-06-03** (最早シナリオ) |
| 並列構成 | Tier B 4本並列 |
| handoff thread | https://mooores.slack.com/archives/C0ACS09FMGC/p1779245661503999 |
| Asana ハブ GID | [TBD: 小林さんが起票後追記] |
| 関連 Asana プロジェクト | 1213741124336104 (Phase 1-2 機能タスク), 1213916581114014 (本番運用・パートナー実運用) |
| 起票セッション | dev VPS `/opt/ultra-autotrade/main` (Claude Code CLI / Opus 4.7) |
| 前 session (handoff 元) | `/home/uata` — settings.json `defaultMode: dontAsk` + `additionalDirectories` が Mac パスのみで silent deny |

---

## 1. ローンチ判定 5条件

> **CLAUDE.md §17 として正式採用されることを想定。** 現在 CLAUDE.md には §17 が無いため、本ファイル確定後に CLAUDE.md へ条文化 (別 PR)。

### 条件 1: [TBD — 本文貼付]
- **指標**: TBD
- **閾値**: TBD
- **計測方法**: TBD
- **現状値 (2026-05-20)**: TBD
- **6/3 達成見込み**: TBD

### 条件 2: [TBD — 本文貼付]
- **指標**: TBD
- **閾値**: TBD
- **計測方法**: TBD
- **現状値 (2026-05-20)**: TBD
- **6/3 達成見込み**: TBD

### 条件 3: [TBD — 本文貼付]
- **指標**: TBD
- **閾値**: TBD
- **計測方法**: TBD
- **現状値 (2026-05-20)**: TBD
- **6/3 達成見込み**: TBD

### 条件 4: 山本さん UAT 14日観測完走 (handoff から確定)
- **指標**: UAT 期間中の本番 AI 判定が HOLD 一辺倒でないこと + 致命エラー 0 件
- **閾値**: 14日連続観測 / 観測期間中 BUY/SELL 提案が最低 1 件以上発火 / HF < 1.6 ハード停止が発火していないこと
- **計測方法**: production DB `ai_decisions` テーブルの 14日 SELECT + Slack #ultra-auto-project の異常通知 0 件
- **現状値 (2026-05-20)**: handoff 記載 — 起算点 (P0-X2 山本さん INSERT) が **4日 overdue**。本日 5/20 Pushover High で再依頼予定
- **6/3 達成見込み**: 起算点が 5/20 ならば 6/3 着地は 14日に **足りない** (5/20 → 6/3 = 14日だが、観測ウィンドウは inclusive で計算要)
- **依存タスク**: Asana P0-X2 山本さん INSERT 完了 (assignee=小林さん専権、4日 overdue)

### 条件 5: [TBD — 本文貼付]
- **指標**: TBD
- **閾値**: TBD
- **計測方法**: TBD
- **現状値 (2026-05-20)**: TBD
- **6/3 達成見込み**: TBD

---

## 2. 6/3 シナリオ採用根拠 (実機データ再計算)

> **TBD**: claude.ai の「6/3 最早 / 4本並列」案の元計算と、本日の実機データによる再計算結果。
> handoff 記載の「ユーザーが指摘してほしいと明示した点」7項目を本章に反映する必要がある:
>
> 1. 6/3-6/5 最早が本当に最早か実機ベースで再計算
> 2. 各条件の進捗が引継ぎパッケージの数字を鵜呑みにしただけ
> 3. 山本さん UAT 14日観察が 5/25 - 6/8 で完走できるか (現状 100% HOLD)
> 4. chaos test 3日連続が staging で実施可能か (PR #253 実機状態未確認)
> 5. 並列 4本構成の Tier S 禁止ファイル抵触リスク
> 6. 抜けているリスク (HUMAN-REVIEW 14本処理 / v4 反映後の観察期間 / 山本さん wallet 接続 / 営業チーム運用 docs / Phase 2 機能の Phase 1 ローンチ前必要性)
> 7. (handoff 内に明示なし)

### 2.1 起算点と着地点 (calendar 計算)

| 起算イベント | 起算日 (実機) | 必要日数 | 着地日 |
|---|---|---|---|
| 山本さん UAT 開始 (P0-X2 INSERT) | TBD (現状 4日 overdue → 5/20 中) | 14日 | TBD |
| chaos test 3日連続 | TBD | 3日 + 観測 1日 | TBD |
| HUMAN-REVIEW 14本処理完了 | TBD | TBD | TBD |
| v4 反映後の観察期間 | 2026-05-19 (PR #302 merge済) | TBD | TBD |
| L1-L6 14日 PASS 率 100% | TBD | 14日 | TBD |

### 2.2 critical path

[TBD — 上記計算から逆算した critical path 図]

### 2.3 6/3 vs 6/5 vs 6/8 比較表

[TBD — claude.ai 提案 v1 の 3 シナリオ比較。本セッションでは元データ無いため再構築不可]

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

CLAUDE.md §「Claude Code Agent View 運用」に従い、`claude --bg` で 4 Lane 起動。tmux 多分割は廃止済み。

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

[TBD — `healthcheck.log` 直近14日集計] (Lane 2 で取得予定)

### 4.4 production AI 判定 24h KPI (CLAUDE.md §2026-05-13 教訓 策1)

```sql
-- 本ロードマップの定量化に必須。Lane 2 (approval_rate) と同時取得
SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';
SELECT COUNT(*), MAX(created_at) FROM proposals WHERE created_at > NOW() - INTERVAL '24 hours';
SELECT final_action, COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY final_action;
```

実行結果: [TBD — 取得予定]

---

## 5. 既知ブロッカー (handoff から確定)

| ID | 内容 | 状態 | 影響 |
|---|---|---|---|
| P0-X2 | 山本さん INSERT が 4日 overdue | overdue | 条件4 (UAT 14日) の起算点遅延 — 6/3 シナリオが計算上後ろ倒し |
| P3 | (詳細未記載) | 7日以上 overdue | TBD |
| P2 | (詳細未記載) | 7日以上 overdue | TBD |
| P0-X1 | (詳細未記載) | 7日以上 overdue | TBD |

3件が 7日以上 overdue、全件 assignee=小林さん専権。

---

## 6. Phase X 起動条件

[TBD — 6/3 ローンチ後の Phase 2 (マルチプロトコル) 起動条件、Phase 3 (multi-tier capital) 起動条件等]

---

## 7. References

### docs (リポジトリ内)

| ファイル | 関連章 | 状態 |
|---|---|---|
| `CLAUDE.md` | 全章 (鉄則 7-10 / Tier 分類 / 教訓 2026-05-13 策1-20 等) | 正本 |
| `CLAUDE.md §17` (ローンチ 5条件) | §1 | **未作成** — 本ロードマップ確定後に別 PR で追記 |
| `docs/22_production_release_checklist.md` | §3 (Tier B 並列) | 既存 |
| `docs/14_test_strategy.md` | §4 (実機データ Gate 4 / Gate 8) | 既存 |
| `docs/postmortems/2026-05-17_loki_postgres_cascade.md` | §5 (既知ブロッカーの教訓) | 既存 |
| `docs/postmortems/2026-05-17_backup_silent_failure.md` | §5 | 既存 |
| `docs/launch/launch_decision_criteria_v2.md` | §1 (5条件の元案) | **リポジトリに未追加** |
| `docs/launch/l1_l6_evaluation_v1.md` | §4.3 (L1-L6 評価方法) | **リポジトリに未追加** |

### Slack

- handoff parent: `https://mooores.slack.com/archives/C0ACS09FMGC/p1779245661503999`
- #ultra-auto-project: `C0ACS09FMGC`

### Asana

- Phase 1-2 機能タスク: project `1213741124336104`
- 本番運用・パートナー実運用: project `1213916581114014`
- ローンチハブタスク: [TBD — 本 PR merge 後に起票]

---

## 改訂履歴

| 日付 | 版 | 変更 | 担当 |
|---|---|---|---|
| 2026-05-20 | v1.0-skeleton | 初版 (placeholder)。Tier B 4本並列構成のみ確定、本文 5条件・6/3 計算は TBD | Claude Code (dev VPS) |
| TBD | v1.0 | 本文埋め (claude.ai 案の原文反映) | 小林さん |
| TBD | v1.1 | 実機データ再計算結果反映 (Lane 2 完了後) | TBD |
