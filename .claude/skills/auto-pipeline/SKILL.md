---
name: auto-pipeline
description: Use when running the autonomous Planner→Generator→Evaluator→Tester pipeline over a backlog of tasks, or when the user invokes /goal-style continuous development. Orchestrates subagents, enforces human-review-gate, auto-transitions between tasks.
---

# Auto-Pipeline スキル

## 1. 概要

このスキルは「メインセッションが司令塔として 4 つのサブエージェント（Planner / Generator /
Evaluator / Tester）を順に起動し、1 タスクを完遂してから次タスクへ自動遷移する」
**オーケストレーションループ**の手順書である。

全体設計の正本は `docs/ops/agent_pipeline_v1.md`。このスキルは同 doc を参照し、
メインセッションが実際にループを回すための**操作手順**をエンコードしたものである。

```
 Asana / backlog
       │
       ▼
 ┌───────────┐   plan    ┌────────────┐  diff   ┌─────────────┐ approved ┌──────────┐
 │  Planner  │ ────────▶ │ Generator  │ ──────▶ │  Evaluator  │ ───────▶ │  Tester  │
 │ (Opus/RO) │           │ (Sonnet)   │         │ (Opus/RO)   │          │ (Sonnet) │
 └───────────┘           └────────────┘         └─────────────┘          └──────────┘
       ▲                      ▲  │                     │ CHANGES                │ pass
       │                      │  └─────────────────────┘ REQUESTED              │
       │ 差し戻し（設計）      └──────────── 差し戻し（実装修正）◀──── FAIL ───┘
       │
   🛑 HUMAN-REVIEW-REQUIRED（高リスク時のみ人間承認まで停止）
```

---

## 2. 前提

### サブエージェントの登録タイミング

`.claude/agents/*.md` に新規作成したエージェント定義は、**セッション実行中には即座に
`subagent_type` として認識されない**（エージェントレジストリはセッション起動時にロード
される仕様）。詳細は `docs/ops/agent_pipeline_v1.md §3 モードA 注記` 参照。

対処方法:
- (a) `.claude/agents/*.md` 定義作成後にセッションを**再起動**（`/agents` で再読込）
- (b) 再起動前の暫定対応として、**メインセッションが各ロールの規律を自分で実演**する
  「代替モード」でパイプラインを回す（Planner 規律→Generator 規律→... の順に実演）

本パイプライン初回構築（2026-06-11）でも代替モードでの完走を確認済み。
正式起動は定義作成後のセッション再起動後が推奨。

### CLAUDE.md 前提ルール（遵守必須）

- **並列 tool call は最大 2 本まで**（`#並列 tool call は最大 2 本まで` ルール）
  → 1 タスク内のサブエージェント呼び出しは必ず直列
- **Tier S ファイルは 1 日 1 PR**（Tier 分類 / 並列開発フロー v4）
- **本番 VPS での直接実装禁止**（dev VPS worktree 内で作業）

---

## 3. 1 タスクのループ手順

以下の擬似コード / 箇条書きが 1 タスクの完走手順である。

```
[Step 1] backlog から次の pending タスクを取得
  → Asana MCP (`get_task` / `search_tasks`) または TaskList で取得
  → GID または説明テキストを Planner に渡す

[Step 2] Planner サブエージェント起動
  Agent(subagent_type="Planner", prompt="<タスク GID または説明>")
  → 出力: 構造化プラン（Tier 判定 / 触るファイル / 実装ステップ / DoD / 推奨ブランチ）

[Step 3] human-review-gate 判定
  プランを参照し:
    IF 🛑 HUMAN-REVIEW-REQUIRED: あり
      → パイプライン停止。人間に通知（Slack / 出力）して承認を待つ
      → 承認後に Step 4 から再開
    ELIF Tier B のみ（新規ファイル追加のみ）
      → ✅ 自動継続

[Step 4] Generator サブエージェント起動
  Agent(subagent_type="Generator", prompt="<Planner の構造化プラン全文>")
  → 実装・セルフ DoD（ruff/mypy/tsc）実行・コミット
  → 出力: 変更ファイル一覧・差分要点・セルフ DoD 結果

[Step 5] Evaluator サブエージェント起動
  Agent(subagent_type="Evaluator", prompt="<変更ブランチ・diff 情報>")
  → 出力: APPROVED / CHANGES_REQUESTED / BLOCKED

  IF CHANGES_REQUESTED:
    差し戻し回数 += 1
    IF 差し戻し回数 > 3:
      → 🛑 HUMAN-REVIEW-REQUIRED（3 往復超過）
    ELSE:
      → Step 4 に戻る（指摘内容を Generator に渡す）
  IF BLOCKED:
    → 🛑 HUMAN-REVIEW-REQUIRED（設計判断・安全装置）
  IF APPROVED:
    → Step 6 へ

[Step 6] Tester サブエージェント起動
  Agent(subagent_type="Tester", prompt="<APPROVED 済みブランチ・worktree パス>")
  → verify.sh（Gate 1-3）+ E2E（UI 変更時 Gate 4）+ 孤立コード検出（大リファクタ時 Gate 5）
  → 出力: PASS / FAIL

  IF FAIL:
    原因切り分け:
      新規変更起因 → Generator に差し戻し（Step 4 へ。差し戻し回数カウント継続）
      環境依存・設計問題 → 🛑 HUMAN-REVIEW-REQUIRED
    複数件 FAIL / coverage 80% 割れ → 🛑 HUMAN-REVIEW-REQUIRED
    Flaky 疑い → 1 回 re-run → それでも FAIL なら 🛑
  IF PASS:
    → Step 7 へ

[Step 7] タスク完了処理
  1. Slack 通知（CLAUDE.md「Agent Teams 運用ルール / Slack 通知」テンプレ使用）
  2. Asana タスクを完了マーク（MCP `update_task` または notes に完了記録）
  3. diff_count / 差し戻し回数 / Gate 結果を CLAUDE.lessons.md に記録（教訓があれば追記）
  4. backlog に次の pending タスクがあれば Step 1 へ自動遷移
  5. backlog が空なら停止（完了報告）
```

差し戻しカウントはタスクをまたがずにリセット（次タスクでは 0 から）。

---

## 4. 並列実行（worktree）

Tier B タスクが 2 本あり、**触るファイルが非衝突**である場合のみ並列実行を許可する。

### 並列の判断基準

| 条件 | 並列可否 |
|---|---|
| 両タスクとも Tier B（新規ファイル追加のみ） | ✅ 並列可 |
| 触るファイルに重複なし | ✅ 並列可 |
| どちらかが Tier S / Tier A（既存ファイル改変） | ❌ 直列 |
| 同ファイルに両タスクが触れる | ❌ 直列 |

### 並列起動手順（最大 2 タスク同時）

```bash
# 各タスクに独立 worktree を用意
git fetch origin
git worktree add /opt/ultra-autotrade-worktrees/ut-lane-1 -b feat/<branch-a> origin/main
git worktree add /opt/ultra-autotrade-worktrees/ut-lane-2 -b feat/<branch-b> origin/main
```

レーン編成は `team-coordinator` エージェントに委譲することを推奨:

```
Agent(subagent_type="team-coordinator",
      prompt="以下 2 タスクを worktree 隔離で並列実行するレーン構成を生成してください:
              タスクA: <概要> / 触るファイル: <files>
              タスクB: <概要> / 触るファイル: <files>")
```

コンフリクト発生時は `scripts/auto_isolate.sh` で隔離する
（`scripts/auto_isolate.sh` は実在確認済み / `docs/ops/agent_pipeline_v1.md §5`）。

> **注意**: Agent Teams は file conflict detection が無い（CLAUDE.md）。
> File ownership を Teammate 初期プロンプトで**明示**しないと他レーンを上書きする。

---

## 5. トークン最適化（重要）

メインセッション（Fable 5 / 設計監査ロール）のコンテキストを軽量に保つため、
以下のモデル配分を推奨する（`docs/ops/agent_pipeline_v1.md §1` 準拠）:

| ロール | 推奨モデル | 理由 |
|---|---|---|
| メインセッション（司令塔） | Fable 5（軽量維持） | ループ制御のみ。実作業は委譲 |
| Planner | Opus または Sonnet | 設計・Tier 判定・推測禁止の精度重視 |
| Generator | Sonnet | 実装コスト効率。lint/型ミスは Evaluator が検出 |
| Evaluator | Opus またはメインセッション | adversarial レビューは設計判断を含む |
| Tester | Sonnet | コマンド実行・結果貼り付け中心 |
| Explore / general-purpose | Sonnet / Haiku | 調査・検索の委譲先 |

メインセッションが直接 grep/Read で調査をしない。調査は Explore エージェントに委譲する。

Opus 障害時の退避ルート（CLAUDE.md「並列開発フロー v4 鉄則10」）:
- Planner → Sonnet で代替可
- Evaluator → Sonnet（ただし設計判断精度が落ちる点を記録）
- Tier S 変更・安全装置変更は Opus 復旧まで待機

---

## 6. 持続（Ralph-style / 24h 自走 / `/goal`）

- `/goal` の Stop hook が「全タスク完了 + DoD 全 pass」条件を満たすまで停止をブロック
- 1 タスク完了 → Step 1（backlog 取得）へ自動遷移。人間操作は不要
- 夜間 CI failure の自動解消は `.claude/rules/night-mode-ci-autofix.md` の対象・除外ルールに従う
- `scripts/uata-stuck-detector.sh` が heartbeat（`/tmp/uata-heartbeat`）を 5 分間隔で監視:
  30 分間更新なし → Slack `#ultra-auto-project` に `STUCK-DETECTED` 通知
- 各タスク完了時の Slack 通知テンプレ（CLAUDE.md「Agent Teams 運用ルール」）:

  ```bash
  WEBHOOK=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-)
  curl -s -X POST "$WEBHOOK" \
    -H "Content-Type: application/json" \
    -d '{"text": "✅ [auto-pipeline] 完了: [タスク名]\n結果: [1行サマリー]\nファイル: [変更ファイル一覧]"}'
  ```

24h 自走起動前に stuck-detector を起動してから claude を起動する:

```bash
cd /opt/ultra-autotrade/main
./scripts/uata-stuck-detector.sh start
claude --resume
```

---

## 7. 停止条件

パイプラインが停止（Slack 通知 + 待機状態へ移行）する条件:

| 条件 | 停止理由 |
|---|---|
| backlog が空 | 全タスク完了（正常終了） |
| 🛑 HUMAN-REVIEW-REQUIRED 発生 | Tier S / Aave / 本番操作 / 依存追加 / ロールバック不能 |
| Generator↔Evaluator 差し戻し 3 往復超過 | 設計的問題の可能性 → 人間判断 |
| Tester 複数件 FAIL / coverage 80% 割れ | リグレッション疑い → 人間調査 |
| Tester FAIL（flaky 以外）2 回連続 | 実装根本問題 → 人間判断 |
| `git rebase origin/main` コンフリクト解決不能 | ブランチ乖離 → 人間 merge |
| Evaluator BLOCKED 判定 | 設計判断・安全装置配線 → 人間判断 |

停止時の出力フォーマット（`human-review-gate` スキルの出力フォーマットに準拠）:

```
🛑 HUMAN-REVIEW-REQUIRED

対象: <タスク名 / ファイル / 操作>
カテゴリ: <停止理由の分類>
理由: <1行>
現状: <差し戻し回数 / FAIL 詳細 / Evaluator 判定など>
次アクション候補:
  - 最小案: ...
  - 標準案: ...
  - 根本案: ...
人間の承認を待機。承認なしに次フェーズへ進まない。
```

---

## 8. 関連

| 参照先 | 役割 |
|---|---|
| `docs/ops/agent_pipeline_v1.md` | パイプライン全体設計の正本（§1 全体像 / §2 ライフサイクル / §3 起動方法 / §5 隔離 / §6 人間ゲート / §7 24h 持続） |
| `.claude/agents/Planner.md` | Planner ロール規律・構造化プラン出力フォーマット |
| `.claude/agents/Generator.md` | Generator ロール規律・セルフ DoD 手順 |
| `.claude/agents/Evaluator.md` | Evaluator ロール規律・adversarial レビュー観点 |
| `.claude/agents/Tester.md` | Tester ロール規律・Gate 1-5 手順・報告フォーマット |
| `.claude/skills/human-review-gate/SKILL.md` | 停止判定ロジックの詳細（STOP 条件一覧 / 自動進行条件） |
| `scripts/auto_isolate.sh` | コンフリクト・バグ自動隔離スクリプト |
| `scripts/uata-stuck-detector.sh` | heartbeat 監視 / 30 分 stuck → Slack 通知 |
| `.claude/rules/night-mode-ci-autofix.md` | 夜間 CI failure の自動解消ルール / 3 往復制限 |
| CLAUDE.md「並列開発フロー v4」 | Tier 分類 / 鉄則 1-10 / Agent Teams 運用ルール |
| CLAUDE.md「✅ 完了宣言の必須テンプレ」 | タスク完了時の証跡フォーマット |
