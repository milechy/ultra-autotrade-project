# 自走開発パイプライン v1（Planner → Generator → Evaluator → Tester）

> 2026-06-11 作成。`/goal` による 24h+ 持続自走を、4 つの専門サブエージェント
> （`.claude/agents/{Planner,Generator,Evaluator,Tester}.md`）の協調で実現するための設計。
> CLAUDE.md「並列開発フロー v4」「Tier 分類」「Agent Teams 運用ルール」を前提とする。

---

## 1. 全体像

```
 Asana / backlog
       │
       ▼
 ┌───────────┐   plan    ┌────────────┐  diff   ┌─────────────┐ approved ┌──────────┐
 │  Planner  │ ────────▶ │ Generator  │ ──────▶ │  Evaluator  │ ───────▶ │  Tester  │
 │ (Opus/RO) │           │ (Sonnet)   │         │ (Opus/RO)   │          │ (Sonnet) │
 └───────────┘           └────────────┘         └─────────────┘          └──────────┘
       ▲                       ▲  │                     │  changes              │ pass
       │                       │  └─────────────────────┘  requested           │
       │ 差し戻し（設計）       └───────────── 差し戻し（実装修正）◀────── fail ──┘
       │
   🛑 HUMAN-REVIEW-REQUIRED（高リスクのみ人間に停止）
```

- **上流 Planner**（Opus / READ-ONLY）: タスク分解・Tier 判定・触るファイル特定・高リスク検出 → 構造化プラン
- **中流 Generator**（Sonnet）: プランに沿って実装・リファクタ。自分の worktree 内のみ編集
- **下流 Evaluator**（Opus / READ-ONLY）: セキュリティ・lint・RBAC・環境分離・孤立コードを adversarial レビュー
- **検証 Tester**（Sonnet）: verify.sh + 必要なら Playwright E2E を実機実行し pass/fail を証跡付き報告

各エージェントの責務・出力フォーマットは `.claude/agents/*.md` の system prompt に定義。

---

## 2. 1 タスクのライフサイクル

1. **Planner** がタスクを受け取り構造化プランを生成
   - `🛑 HUMAN-REVIEW-REQUIRED: あり`（Tier S / Aave / 本番）→ **ここで停止し人間承認を待つ**
   - Tier B のみ → 自動で次へ
2. **Generator** がプランに沿って実装 → セルフ DoD（ruff/mypy/tsc）→ コミット
3. **Evaluator** が `git diff origin/main...HEAD` をレビュー
   - `CHANGES_REQUESTED` → Generator に差し戻し（指摘添付）→ 2 に戻る
   - `BLOCKED` → 人間判断（設計・安全装置）
   - `APPROVED` → 次へ
4. **Tester** が verify.sh / E2E 実行
   - `FAIL` → 原因切り分け → Generator に差し戻し（実装起因時）→ 2 に戻る
   - `PASS` → タスク完了。PR 作成（ユーザー指示時）→ 次タスクへ自動遷移

差し戻しループは **最大 3 往復**（`.claude/rules/night-mode-ci-autofix.md` の 3 往復制限に準拠）。
3 往復を超えたら `🛑 HUMAN-REVIEW-REQUIRED` に切り替えて停止する。

---

## 3. 起動方法（2 モード）

### モード A: メインセッションが sub-agent を逐次起動（推奨 / 安定）

メインセッション（このセッション）が司令塔となり、Agent ツールで 1 タスクずつ 4 エージェントを
順に呼ぶ。CLAUDE.md「並列 tool call は最大 2 本まで」を遵守するため、**1 タスク内は直列**。

```
1. Agent(subagent_type=Planner,   prompt=<タスク>)        → プラン取得
2. （HUMAN-REVIEW-REQUIRED なら停止して報告）
3. Agent(subagent_type=Generator, prompt=<プラン>)        → 実装
4. Agent(subagent_type=Evaluator, prompt=<差分レビュー依頼>) → 判定
5. （CHANGES_REQUESTED なら 3 へ / 最大3往復）
6. Agent(subagent_type=Tester,    prompt=<検証依頼>)      → pass/fail
7. PASS → 次タスクへ
```

複数タスクの並列は「タスク間」で行う（Tier B 同士・触るファイル非衝突のもののみ）。
最大 2 タスクを同時に走らせ、各タスク内は直列。

### モード B: Agent Teams + worktree（3+ タスク並列 / コンフリクト物理回避）

Tier B タスクが 3 本以上あり、触るファイルが完全分離している場合のみ。
`team-coordinator` エージェントにレーン編成させてから:

```
Create a team with worktree isolation:
Teammate 1 (Generator): feat/<branch-a> で <タスクA>  — 触る: <files>
Teammate 2 (Generator): feat/<branch-b> で <タスクB>  — 触る: <files>
Teammate 3 (Evaluator): 各 PR をレビュー
Each teammate gets its own git worktree. File ownership は上記の通り。
```

> Agent Teams は file conflict detection が無い（CLAUDE.md）。File ownership を初期プロンプトで
> 明示必須。3-5 teammate がスイートスポット。6+ は coordination overhead 過多。

---

## 4. git worktree 並列戦略

- dev VPS は既に worktree 運用中（`/opt/ultra-autotrade/main/.claude/worktrees/agent-*`）
- 各並列タスクは `origin/main` から切った独立ブランチ + 独立 worktree で作業
  ```bash
  git fetch origin
  git worktree add ../ut-lane-<n> -b feat/<branch> origin/main
  ```
- 利点: 同一ファイルを別タスクが触っても物理的に別ディレクトリなので衝突しない
- main マージ時のみコンフリクト可能性 → 各レーンは着手時に `git rebase origin/main` 必須

---

## 5. コンフリクト / バグ自動隔離

| 事象 | 自動対応 | エスカレーション条件 |
|---|---|---|
| `git rebase origin/main` でコンフリクト | Generator が自ブランチ内で解決を試行 | 解決不能 → `rebase --abort` → 🛑 人間 |
| 実装中の既存テスト破壊（リグレッション） | 自変更起因なら修正。既存バグなら `git stash`→新ブランチに隔離 | 原因不明 → 🛑 人間 |
| Evaluator が CRITICAL 検出 | Generator へ差し戻し（最大3往復） | 3往復超 → 🛑 人間 |
| Tester FAIL（flaky 疑い） | 1回 re-run | 複数件 fail / coverage 割れ → 🛑 人間 |
| ロールバック不能ステップ（migration/本番SQL） | 実行せず Planner に差し戻し | 常に 🛑 人間 |

隔離の基本: **失敗を main に持ち込まない**。worktree / feature ブランチ内に閉じ込め、
解決不能なものだけ人間に上げる。

---

## 6. 人間承認ゲート（HUMAN-REVIEW-REQUIRED で停止する範囲）

自動進行 **しない**（必ず人間承認を挟む）:
- Tier S ファイル変更（main.py / ci.yml / migration / automation 安全装置 / database.py / CLAUDE.md / `.claude/agents/*.md` 本体上書き）
- Aave トランザクション / Health Factor / Decimal 計算ロジックの変更
- 本番 DB write / deploy / 秘密鍵に触れる操作
- `package.json` / `requirements.txt` / `pyproject.toml` への依存追加

自動進行 **する**（Tier B のみ・新規ファイル追加）:
- `docs/*.md`（新規）/ `scripts/*.sh`（新規）/ `.claude/skills/**`（新規）/
  `backend/tests/*.py`（新規）/ `.github/workflows/*.yml`（新規・ci.yml 以外）

---

## 7. 24h+ 持続（Ralph-style loop / `/goal`）

- `/goal` の Stop hook が「全タスク完了 + DoD 全 pass」条件を満たすまで停止をブロック
- 1 タスク完了 → TaskList で次の pending タスクを取得 → 自動遷移
- 夜間 CI failure は `.claude/rules/night-mode-ci-autofix.md` の自動解消ルールに従う
- `scripts/uata-stuck-detector.sh` が heartbeat を監視（30分更新なし → Slack 通知）
- 各タスク完了時に CLAUDE.md「Agent Teams 運用ルール / Slack 通知」に従い Slack 通知

---

## 8. 現在の backlog（Asana UAT / 2026-06-11 起票分）

| GID | タスク | Tier | 自動/承認 |
|---|---|---|---|
| 1215615066081277 | repomix を Gate 5 前処理に導入 | B | 自動可 |
| 1215615119980380 | human-review-gate skill 作成 | B | 自動可 |
| 1215615230413674 | Trellis 試験導入評価（docs） | B | 自動可 |
| 1215615119964753 | skillspector CI 組み込み（新規 workflow） | B | 自動可（ci.yml 本体統合は承認） |
| 1215615047475673 | open-code-review CI 統合（新規 workflow） | B | 自動可（ci.yml 本体統合は承認） |
| 1215615130885943 | SkillOpt で agents 定義最適化 | **S相当** | 🛑 承認（agents 本体上書き） |

推奨実行順: repomix → human-review-gate → Trellis → skillspector → open-code-review → （SkillOpt は承認後）
理由: 触るファイルが完全分離した Tier B から着手し、最後に承認が必要な SkillOpt を回す。

---

## 9. 参照

- `.claude/agents/Planner.md` / `Generator.md` / `Evaluator.md` / `Tester.md`
- `.claude/agents/team-coordinator.md`（レーン編成）
- `.claude/rules/night-mode-ci-autofix.md`（CI 自動解消・3往復制限）
- CLAUDE.md「並列開発フロー v4」「Tier 分類」「✅ 完了宣言の必須テンプレ」「🗂 ドリフト再発カタログ」
- `docs/ops/orphan_detection.md`（Gate 5）/ `docs/14_test_strategy.md`（Gate 1-8）
