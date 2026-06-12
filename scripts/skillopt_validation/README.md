# skillopt_validation — SkillOpt held-out validation タスク置き場

## 目的

このディレクトリは [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt)（MIT License）の
**held-out validation セット** を管理します。

`scripts/run_skillopt.py` が `scripts/skillopt_config.json` を読み込み、各エージェント定義
（`.claude/agents/*.md`）の最適化を試みる際、**スコア改善が検証セットで確認された場合のみ**
最適化版 (`*.optimized.md`) を採用します（スコア悪化 → 棄却）。

---

## `skillopt_config.json` との対応関係

| エージェント | config の `path` | config の `validation_tasks` |
|---|---|---|
| Planner | `.claude/agents/Planner.md` | `scripts/skillopt_validation/planner_tasks.jsonl` |
| Generator | `.claude/agents/Generator.md` | `scripts/skillopt_validation/generator_tasks.jsonl` |
| Evaluator | `.claude/agents/Evaluator.md` | `scripts/skillopt_validation/evaluator_tasks.jsonl` |
| Tester | `.claude/agents/Tester.md` | `scripts/skillopt_validation/tester_tasks.jsonl` |

---

## 公式確認済みスキーマ (2026-06-12)

> **[確認済み]** microsoft/SkillOpt の `skillopt/envs/_template/loader_template.py`（`_normalize_item()`）
> および `skillopt/envs/base.py` を確認した結果、以下のスキーマが公式推奨です。
>
> 出典:
> - https://github.com/microsoft/SkillOpt `skillopt/envs/_template/loader_template.py`
> - https://github.com/microsoft/SkillOpt `skillopt/envs/base.py`

各ファイルは **1 行 1 タスクの JSON Lines** 形式です。フィールド定義:

```json
{
  "id": "role-001",
  "question": "エージェントへの入力（タスク説明 / コンテキスト）",
  "ground_truth": "期待される出力・判断・振る舞いの記述",
  "task_type": "カテゴリ名（stratified sampling 用）",
  "scoring_hint": "スコアリング時に参照するヒント（何が正解か）[カスタムフィールド]"
}
```

### フィールド詳細

| フィールド | 必須 / 推奨 | 説明 |
|---|---|---|
| `id` | **必須** | SkillOpt 唯一の Hard requirement。`role-NNN` 形式（例: `planner-001`） |
| `question` | 推奨標準 | エージェントへの入力。旧フィールド名 `input` に相当 |
| `ground_truth` | 推奨標準 | 期待する出力・判断。旧フィールド名 `expected_behavior` に相当 |
| `task_type` | 推奨標準 | タスクカテゴリ。SkillOpt の stratified sampling に使用 |
| `scoring_hint` | カスタム | 本プロジェクト独自フィールド。SkillOpt 本体は参照しないが独自ハーネス（`run_skillopt.py`）が使用 |

> **注意:** SkillOpt 本体は `scripts/skillopt_validation/` 配下の jsonl を直接読まない。
> `skillopt_config.json` の `validation_tasks` フィールドは `run_skillopt.py` 独自ハーネスが
> 参照する。CLI への `--validation-data` 引数配線は現時点では行っていない。

---

## 各エージェントの validation で測るべきこと

### Planner（`planner_tasks.jsonl`）

- **Tier 判定の正確性**: Tier S / A / B の正しい分類ができるか
- **HUMAN-REVIEW-REQUIRED 検出**: 高リスク変更（Aave / 安全装置 / 本番 DB 操作）を見落とさないか
- **触るファイル列挙の網羅性**: grep なしで推測したファイルを挙げていないか（鉄則 9 遵守）
- **DoD の明確さ**: Generator が即着手できる粒度のプランを出力できるか

### Generator（`generator_tasks.jsonl`）

- **実装が DoD を通過するか**: verify.sh（ruff / mypy / pytest 80%+）が通る実装を出すか
- **Tier S ファイルへの無断編集がないか**: worktree 分離・ブランチ分離の遵守
- **HUMAN-REVIEW-REQUIRED ゲートの遵守**: 承認なしに着手しないか
- **Minimal Impact 原則**: 必要最小限の変更に留めているか（過剰な抽象化・リファクタをしないか）

### Evaluator（`evaluator_tasks.jsonl`）

- **セキュリティ違反の検出**: ハードコード秘密鍵 / float 金融計算 / RBAC 漏れを見逃さないか
- **環境分離ドリフトの検出**: staging ↔ production 設定混在を指摘できるか
- **approved / minor / major 判定の妥当性**: 重大問題を「minor」に過小評価しないか
- **配線漏れの検出**: 新規モジュールが main.py / 安全装置に未登録のケースを指摘できるか

### Tester（`tester_tasks.jsonl`）

- **Gate 1-3 の正確な実行**: verify.sh の各チェックを正しく解釈・実行できるか
- **E2E 証跡の品質**: pass/fail を証跡（curl 出力 / Playwright スクリーンショット）付きで報告できるか
- **差し戻し判断の適切さ**: テスト失敗時に適切に Generator へ差し戻せるか
- **完了宣言テンプレの遵守**: 必須フィールドが揃ってから「完了」と書くか

---

## ファイル追加・更新の方針

1. タスク数は **最低 5 件以上** を目標にする（2-3 件は最小 scaffold）
2. 実際の運用でバグ・見落とし・誤判定が発生したら、その事例を validation タスクに追加する
3. 正式 SkillOpt スキーマ確認後に全ファイルを一括フォーマット更新する

---

*2026-06-11 初版 scaffold / 2026-06-12 公式推奨スキーマへ移行（id 必須 / question / ground_truth / task_type 追加、Asana 1215615130885943）*
