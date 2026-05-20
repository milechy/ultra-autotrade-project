# CLAUDE.md 分割提案 v2

**作成:** 2026-05-20 (night-mode 事前準備 / claude-code-cli)
**更新:** 2026-05-20 v2 (night-mode タスク #12 — 5/20 教訓 3点追加)
**レビュー予定:** 2026-05-21 06:30 JST (claude.ai)
**実行予定:** 2026-05-21 06:30 レビュー → 承認後 Tier S 枠で実行

---

## v2 追加内容 (2026-05-20 教訓から)

### A. Lane への 1ブロック包括依頼テンプレ (core.md に追加)

分割後 `CLAUDE.md` のどこに入れるか: **§9 朝プロトコルの直後** (Step 0 の延長として)

```
【Lane 依頼標準テンプレ】
環境: staging-new / production (どちらか明示)
現象: (1行で)
依頼: 以下を1ブロックで返す
  1. 実機 dump (docker ps / logs / DB query 等)
  2. 真因 (推測ではなく実データから)
  3. 修正案 (最小/標準/根本 の3択)
制約: 本番 DB write / deploy は HUMAN-REVIEW-REQUIRED で停止
```

**背景:** 2026-05-20 に claude.ai が docker コマンドを 25往復中継し、§25 違反を6回犯した。Lane に「1ブロック依頼」すれば 1往復で済む。

### B. 朝プロトコル違反パターン (lessons.md に追加 / 2026-05-20セクション)

分割後のどこに入れるか: `CLAUDE.lessons.md` の **2026-05-20 セクション**として追加。

| # | 違反パターン | 正しい行動 |
|---|---|---|
| P1 | docker コマンドを 2行以上中継する | 2行目で停止 → Lane に1ブロック依頼 |
| P2 | コンテナ名を断定して SQL 発行 | `docker ps` で実名確認後に発行 |
| P3 | staging 消滅アラートで即復旧コマンドを出す | 先に Lane に診断依頼 |
| P4 | v4/schema 変更後の SQL を docs 未確認で発行 | `docs/ops/02_db_tables.md` を先読み |
| P5 | `docker restart` で env 変更が反映されると思い込む | CLAUDE.md「docker restart ≠ recreate」を参照 |

### C. docker 罠 7項目リンク (ops.md に追加)

分割後のどこに入れるか: `CLAUDE.ops.md` または `docs/ops/docker_command_cheatsheet.md` への参照として追加。

> 詳細: `docs/ops/docker_command_cheatsheet.md` (2026-05-20 作成)

7項目の概要:
1. `--env-file` 必須
2. `restart ≠ recreate`
3. `--remove-orphans` 別 stack 巻き込みリスク
4. `--filter name=` は OR 動作
5. backend 再起動標準手順
6. Blue/Green active 動的確認
7. `builder prune` vs `system prune`

### D. 配置先まとめ (v2 決定事項)

| 追加コンテンツ | 配置先 |
|---|---|
| Lane 1ブロック依頼テンプレ | `CLAUDE.md` core — §9 朝プロトコル直後 |
| 朝プロ違反パターン 5件 | `CLAUDE.lessons.md` — 2026-05-20 セクション |
| docker 罠 7項目リンク | `CLAUDE.ops.md` — Docker 運用セクション |
| docker_command_cheatsheet.md | `docs/ops/` (新規 — 本 PR 外で作成済み) |

---

## 現状サマリー

| 項目 | 値 |
|---|---|
| 分割前サイズ | 122,369 bytes / 2,162 lines (PR #329 merge 前) |
| 現在のサイズ (PR #329 適用済) | **119,906 bytes / 2,103 lines** |
| 問題 | コンテキスト注入コストが高い / 教訓が毎月増える / 検索性が低い |
| 目標 | core を 40KB 以下に / 教訓は別ファイルに分離 |

---

## 現状セクション分析

### 凡例
- **鉄則系** → `CLAUDE.md` コアに残す (絶対ルール)
- **体制系** → `CLAUDE.md` コアに残す (環境・役割定義)
- **教訓系** → `CLAUDE.lessons.md` へ移動
- **ops 系** → `CLAUDE.ops.md` へ移動 (詳細運用手順)
- **重複** → 削除
- **朝プロ** → `CLAUDE.md` コアに残す

| L開始 | L終了 | 行数 | 文字数 | 分類 | セクション名 |
|---:|---:|---:|---:|---|---|
| 3 | 10 | 8 | 208 | core | プロジェクト: Ultra AutoTrade |
| 11 | 24 | 14 | 176 | core | Claude Code 設定 |
| 25 | 49 | 25 | 438 | core | 開発原則 |
| 50 | 72 | 23 | 577 | core | Definition of Done (DoD) ※[CRITICAL]と統合推奨 |
| 73 | 85 | 13 | 499 | core | Architecture |
| 86 | 103 | 18 | 449 | core | Frontend 開発ルール |
| 104 | 105 | 2 | 59 | core | Security Rules ABSOLUTE (header のみ) |
| 106 | 118 | 13 | 660 | core | [CRITICAL] Security Rules |
| 119 | 126 | 8 | 297 | core | [CRITICAL] Definition of Done (DoD) |
| 127 | 131 | 5 | 149 | core | Core Principles |
| 132 | 162 | 31 | 1,415 | core | Frontend ルール (E2E URL対応表含む) |
| 163 | 175 | 13 | 473 | ops | Key API Endpoints |
| 176 | 192 | 17 | 538 | ops | Directory Structure |
| 193 | 216 | 24 | 666 | ops | マルチLLM開発ワークフロー |
| 217 | 236 | 20 | 1,181 | ops | Testing (docs/14_test_strategy.md) |
| 237 | 275 | 39 | 881 | ops | Codex Plugin 運用ルール |
| 276 | 299 | 24 | 760 | ops | 孤立コード検出 |
| 300 | 627 | 328 | 10,087 | core | **Agent Teams 運用ルール** (v4鉄則10本+Tier分類+Lane DoD含む) |
| 628 | 674 | 47 | 1,634 | **DELETE** | **⚠️ Agent View 運用 (完全重複)** |
| 675 | 721 | 47 | 1,634 | ops | Agent View 運用 (重複解消後に残す方) |
| 722 | 734 | 13 | 754 | core | 環境定義 (B案リネーム後) |
| 735 | 792 | 58 | 2,968 | core | 開発環境 v3 (3層運用) |
| 793 | 896 | 104 | 2,972 | ops | Claude Code 最新機能活用ガイド |
| 897 | 904 | 8 | 245 | core | 開発体制 v2 |
| 905 | 956 | 52 | 2,496 | core | Skills & Hooks + 並列 tool call 最大2本 |
| 957 | 1,169 | 213 | 11,080 | **lessons** | **デプロイ時の教訓** (2026-04-01〜04-08) |
| 1,170 | 1,211 | 42 | 1,295 | **lessons** | **2026-04-21 教訓: E2E先行と3層確認** |
| 1,212 | 1,508 | 297 | 13,188 | **lessons** | **環境ファイル更新ルール + 各種2026-04〜05 教訓** |
| 1,509 | 1,572 | 64 | 1,689 | core | **朝プロトコル §9** |
| 1,573 | 1,590 | 18 | 1,061 | core | 参照ファイル |
| 1,591 | 1,611 | 21 | 793 | core | Docker クリーンアップ運用 |
| 1,612 | 1,660 | 49 | 1,612 | ops | オンコールポリシー |
| 1,661 | 1,671 | 11 | 342 | core | Current Phase |
| 1,672 | 1,693 | 22 | 1,024 | ops | Fee Model v10 |
| 1,694 | 1,725 | 32 | 1,442 | **lessons** | **開発フェーズ別チェックポイント** |
| 1,726 | 1,760 | 35 | 1,397 | core | 標準チェックリスト |
| 1,761 | 1,994 | 234 | 6,986 | **lessons** | **2026-05-13 UAT ブロッカー 教訓 20策** |
| 1,995 | 2,036 | 42 | 1,710 | **lessons** | **2026-05-15 PoC staging 未実装パターン** |
| 2,037 | 2,070 | 34 | 1,800 | **lessons** | **2026-05-17 docker compose restart ≠ recreate** |
| 2,071 | 2,121 | 51 | 2,057 | **lessons** | **2026-05-19 24h 自走起動準備** |
| 2,122 | 2,140 | 19 | 587 | **lessons** | **2026-05-19 Next.js bundle 盲点** |
| 2,141 | 2,150 | 10 | 534 | **lessons** | **2026-05-19 AI v4 KeyError RCA** |

---

## 分割提案 v0

### ファイル構成

```
CLAUDE.md            ← コア (鉄則 + 体制 + 朝プロ + チェックリスト)
CLAUDE.lessons.md    ← 教訓アーカイブ (時系列、月次追記)
CLAUDE.ops.md        ← 詳細運用ガイド (API一覧/Testing/LLM運用等)
```

> **注意:** `.claude/CLAUDE.md` (CLI auto-inject 用) は現状のまま維持。
> `CLAUDE.md` のみを分割対象とする。

---

### CLAUDE.md コア (目標 ~45KB bytes / ~1,000 lines)

残すセクション一覧 (順序はほぼ現状維持):

1. プロジェクト: Ultra AutoTrade
2. Claude Code 設定
3. 開発原則
4. Architecture
5. Frontend 開発ルール
6. `[CRITICAL] Security Rules` (rooted here)
7. `[CRITICAL] Definition of Done (DoD)` ← 旧 `Definition of Done (DoD)` と **統合**
8. Core Principles
9. Frontend ルール (E2E URL 対応表含む)
10. Agent Teams 運用ルール (v4 鉄則 10本 + Tier 分類 + Lane DoD) ← **最大セクション、構造維持**
11. 環境定義 + 開発環境 v3 (3層)
12. 開発体制 v2
13. Skills & Hooks + 並列 tool call 最大 2 本
14. **朝プロトコル §9** (Step 0 含む)
15. 参照ファイル (CLAUDE.lessons.md / CLAUDE.ops.md への参照を追加)
16. Docker クリーンアップ運用
17. Current Phase / Launch Progress
18. 標準チェックリスト

**推定: ~32,000 chars / ~50KB bytes**

---

### CLAUDE.lessons.md (目標 ~40-60KB bytes / ~1,000 lines)

移動するセクション (時系列順に並べ直し):

```markdown
# CLAUDE Lessons Learned

> 本番インシデント・教訓の時系列アーカイブ。
> 最新教訓を先頭に。参照元: CLAUDE.md §参照ファイル

## 2026-04-01 デプロイ時の教訓
## 2026-04-02 cloudflared + network_mode:host
## 2026-04-02 AIスケジューラー デフォルト有効化
## 2026-04-02 Docker Composeプロジェクト名統一
## 2026-04-02 Named Tunnel移行時の環境変数
## 2026-04-03 フロントエンドAPI系環境変数 → Mixed Content
## 2026-04-03 デプロイ・運用 (deploy_production.sh 必須)
## 2026-04-03 Lesson Learned: 手打ちdeploy違反インシデント
## 2026-04-03 スケジューラー・監視
## 2026-04-03 Codex Review P1 安全装置バグ
## 2026-04-05 本番デプロイフロー (Hetzner pull only)
## 2026-04-08 フロントエンド/バックエンド分離デプロイの罠
## 2026-04-15 本番DB操作ルール
## 2026-04-17 本番フロントエンド操作ルール
## 2026-04-19 環境ファイル更新ルール (根本解決原則)
## 2026-04-21 教訓: E2E先行と3層確認
## 2026-04-24 開発フェーズ別チェックポイント
## 2026-05-02 テストデータ投入制限
## 2026-05-09 Cloudflare Tunnel ingress 追従漏れ (staging 502)
## 2026-05-12 nginx upstream IP固着 → frontend-only deploy 502
## 2026-05-12 UAT ブロッカー 教訓 20策
## 2026-05-13 5/12終日 UAT ブロッカー 教訓 20策
## 2026-05-15 PoC staging endpoint 未実装パターン
## 2026-05-17 P0: postgres 2,448回クラッシュ + バックアップ全滅 RCA
## 2026-05-17 docker compose restart ≠ recreate
## 2026-05-18 オンコールポリシー
## 2026-05-19 24h 自走起動準備の教訓
## 2026-05-19 Next.js bundle 反映確認の盲点
## 2026-05-19 AI v4 prompt KeyError: 'agent_signals'
```

**推定: ~41,000 chars / ~60KB bytes**

---

### CLAUDE.ops.md (目標 ~10-15KB bytes / ~250 lines)

移動するセクション:

```markdown
# CLAUDE Ops Reference

> 詳細運用参照集。マルチLLM戦略 / API一覧 / Testing / オンコール / Fee Model 等

## Key API Endpoints
## Directory Structure
## マルチLLM開発ワークフロー (ロール / デバッグ昇格 / ブランチ戦略)
## Testing (docs/14_test_strategy.md)
## Codex Plugin 運用ルール
## 孤立コード検出
## Agent View 運用 (重複解消後 1コピー)
## Claude Code 最新機能活用ガイド
## オンコールポリシー
## Fee Model v10
```

**推定: ~12,000 chars / ~18KB bytes**

---

## 要修正・要検討事項

### ① 重複セクション (即削除対象)

| セクション | 重複箇所 | 処置 | 状態 |
|---|---|---|---|
| `## Claude Code Agent View 運用 (2026-05-12 追加)` | 旧 L628-674 と L675-721 で完全同一 | 旧 L628-674 を **削除** | **✅ 完了 (PR #329, 2026-05-20 merged)** |

### ② 統合推奨セクション

| 現状 | 問題 | 提案 |
|---|---|---|
| 旧 L50-72 `## Definition of Done (DoD)` と `## [CRITICAL] Definition of Done (DoD)` | ほぼ同内容で2箇所存在 | [CRITICAL] 版に統合し旧版削除 |

### ③ Agent Teams 運用ルール (10,087 chars) の扱い

この 1 セクションが core 全体の ~30% を占める。
中に含まれる要素と参照頻度:

| 含まれる要素 | 参照頻度 | 備考 |
|---|---|---|
| v4 鉄則 10本 | **毎 Lane 起動時** | Lane プロンプト作成前に必ず確認 |
| Tier 分類表 (S/A/B) | **毎 Lane 起動時** | どのファイルを触るか判断に必須 |
| Phase 計画必須 5軸 | **毎 Phase 立案時** | 省略すると v4 鉄則違反 |
| Lane DoD 6 セクション | **毎 Lane DoD 確認時** | Gate 1-7 の運用判断基準 |
| CLI レポート受領プロトコル | **毎 Lane 報告受信時** | 4 軸確認なし全停止禁止 |
| Phase 終了処理 | **各 Phase 末尾** | 教訓集約・次 Phase ハブ起票 |
| tmux 5ペイン起動コマンド | 並列起動時 (頻度中) | Agent View 移行後は参照頻度低下傾向 |

**コスト比較:**
- **毎回 Read**: Lane プロンプト発行のたびに `Read CLAUDE.md` → inject コスト 119KB 毎回
- **inject 済み (core 維持)**: 起動時 1 回 inject で Lane プロンプト発行中は参照無料

**提案 A (現状維持 = 推奨):** core に丸ごと残す。inject コスト効率が高く、参照漏れリスクがない。CLAUDE.lessons.md の分離だけで △40KB 削減になるため、10,087 chars の追加コストは許容範囲。
**提案 B (抽出):** 鉄則10本 + Tier分類表のみ core に残し、詳細 (tmux/Phase計画/Lane DoD) を `docs/ops/04_multiLLM_and_tooling.md` へ。Lane DoD 6セクションが ops に行くと、Lane 作成者が Read を忘れた場合に DoD 省略リスクが発生する。

→ **推奨: 提案 A (core 維持)**
- 根拠: v4 鉄則 10 本すべてが「毎 Lane プロンプト作成時」に参照される。inject 済みなら Read コスト不要。
- CLAUDE.lessons.md 分離で inject bytes が 119KB → **~55KB** (△54%) になるため、Agent Teams セクション維持でもコスト目標を達成できる。
- リスク: 提案 B を選ぶと Lane DoD 6セクションが ops.md に移動し、Lane 作成者が Read を忘れた場合に DoD 省略 (Gate 1-7 スキップ) リスクが発生する。安全装置として core 維持が優る。

---

## 実行手順 (5/21 06:00-09:00 Tier S 枠)

### Step 0: 準備 (10 min)

```bash
git checkout -b refactor/claude-md-split
```

### Step 1: 重複削除 (15 min)

L628-674 (`## Claude Code Agent View 運用` 1コピー目) を削除:

```bash
# 確認: L628-674 と L675-721 が同一内容か
diff <(sed -n '628,674p' CLAUDE.md) <(sed -n '675,721p' CLAUDE.md)
# diff が 0 件なら削除
```

### Step 2: DoD 統合 (15 min)

L50-72 を L119-126 の `[CRITICAL]` 版に統合。旧 L50-72 を削除し `[CRITICAL]` 版を前に移動。

### Step 3: CLAUDE.lessons.md 作成 (45 min)

以下のセクションを抽出して新規ファイルに:
- L957-1169 (デプロイ時の教訓)
- L1170-1211 (2026-04-21 教訓)
- L1212-1508 の「環境ファイル更新ルール + 各サブ教訓」
- L1694-1725 (開発フェーズ別チェックポイント)
- L1761-2150 (2026-05-13〜05-19 各教訓)

### Step 4: CLAUDE.ops.md 作成 (30 min)

以下を抽出:
- L163-175 (Key API Endpoints)
- L176-192 (Directory Structure)
- L193-216 (マルチLLM開発ワークフロー)
- L217-236 (Testing)
- L237-275 (Codex Plugin)
- L276-299 (孤立コード検出)
- L675-721 (Agent View, 重複解消後)
- L793-896 (Claude Code 最新機能)
- L1612-1660 (オンコールポリシー)
- L1672-1693 (Fee Model v10)

### Step 5: CLAUDE.md の参照ファイルセクション更新 (10 min)

```markdown
| CLAUDE.lessons.md | 教訓アーカイブ全文 | 事後レビュー時・postmortem 参照時 |
| CLAUDE.ops.md     | 詳細運用参照集   | API/LLM戦略/Testing 確認時 |
```

### Step 6: verify + PR (15 min)

```bash
# サイズ確認
wc -c CLAUDE.md CLAUDE.lessons.md CLAUDE.ops.md

# セクション存在確認 (CRITICAL / 朝プロトコル / Tier 分類 が core に残っているか)
grep -c "CRITICAL\|朝プロトコル\|Tier S\|Tier B" CLAUDE.md

# PR 作成
gh pr create --title "refactor(docs): CLAUDE.md 分割 (core/lessons/ops)" \
  --body "..."
```

---

## 期待値

| ファイル | 現在 | 分割後 |
|---|---|---|
| `CLAUDE.md` | 122 KB / 2,150 行 | **~55 KB / ~1,050 行** |
| `CLAUDE.lessons.md` | (新規) | ~60 KB / ~1,000 行 |
| `CLAUDE.ops.md` | (新規) | ~18 KB / ~280 行 |
| 合計 | 122 KB | ~133 KB (増加分は参照ファイルヘッダー分) |

**コンテキスト注入コスト削減:** `CLAUDE.md` のみを inject する現状と比較して、
inject bytes は 122KB → 55KB (△67KB, 約 55% 削減)。
教訓・ops は必要時のみ Read で参照する運用に移行。

---

## TODO (claude.ai レビュー時に決めること)

- [ ] Agent Teams v4 セクション: 提案 A (core 維持) / 提案 B (ops 分離) どちらか
- [ ] CLAUDE.ops.md を作るか、ops 系は既存 `docs/ops/` に統合するか
- [ ] オンコールポリシー (L1612-1660): ops.md vs lessons.md どちらか
- [ ] 開発フェーズ別チェックポイント (L1694-1725): lessons vs core どちらか
- [ ] PR 分割 (重複削除のみ先行 / 全部一発) どちらか

---

*作成: claude-code-cli / night-mode 事前準備 (2026-05-20)*
