# mindfold-ai/Trellis 試験導入評価

> 2026-06-11 作成。Asana GID 1215615230413674。
> AIコーディングエージェント間でプロジェクト仕様・タスク・メモリを永続共有する
> Trellis フレームワークを UATa に導入すべきか評価する。

## 結論（先に）

**不採用（現時点）。** ただし設計思想の一部（scoped spec / workflow gate）は既存構造に取り込む価値あり。

| 判断軸 | 評価 |
|---|---|
| ライセンス | 🔴 **AGPL-3.0**（商用金融プロダクトでは法務レビュー必須・copyleft 伝播リスク） |
| 既存構造との重複 | 🔴 高い（CLAUDE.md + CLAUDE.lessons.md + `.claude/agents/` で同等機能を既に保持） |
| 付加価値 | 🟡 限定的（scoped spec / task PRD / workflow gate の概念は有用だが自前実装済みに近い） |
| 移行コスト | 🟡 中（既存 hook / Lane プロンプト / SessionStart 自動 Read との統合が必要） |

## 1. Trellis とは（実地確認 2026-06-11）

- **目的**: AIコーディングエージェントがセッション間でプロジェクト知識を失う問題を解決
- **ライセンス**: **AGPL-3.0**（※先行調査の「MIT 推定」は誤り。GitHub で実確認）
- **要件**: Node.js ≥18 / Python ≥3.9
- **セットアップ**:
  ```bash
  npm install -g @mindfoldhq/trellis@latest
  trellis init --claude-code -u <name>   # Claude Code 対応
  ```
- **生成構造**:
  - `.trellis/spec/` — プロジェクト仕様・コーディング規約
  - `.trellis/tasks/` — タスク・PRD・実装コンテキスト
  - `.trellis/workspace/` — 個人別ジャーナル・作業メモリ
- **対応**: Cursor / OpenCode / Codex / Claude Code 等「14プラットフォーム」
- **自動更新**: 完了時 `trellis-update-spec` で学習を spec に昇格

## 2. UATa の既存メモリ/仕様体系との対応

| Trellis 概念 | UATa の既存対応物 | 重複度 |
|---|---|---|
| `.trellis/spec/`（仕様・規約） | `CLAUDE.md` + `docs/ops/*.md` + `docs/14_test_strategy.md` | 高 |
| `.trellis/tasks/`（タスク・PRD） | Asana（GID 1213916581114014）+ `docs/launch/` | 高 |
| `.trellis/workspace/`（ジャーナル） | `CLAUDE.lessons.md`（時系列教訓）+ `memory/`（自動メモリ） | 高 |
| workflow gate | 7段階 DoD ゲート + `.claude/skills/human-review-gate` + `.claude/rules/night-mode-ci-autofix.md` | 中 |
| platform-aware 生成 | `.claude/agents/*.md` + `.claude/skills/**` | 中 |
| 完了→spec 昇格 | Phase 終了処理（CLAUDE.md「Phase 終了処理」§教訓集約） | 中 |

UATa は既に「仕様（CLAUDE.md）/ 教訓（lessons）/ タスク（Asana）/ ゲート（DoD）/ エージェント定義」を
独自に運用しており、Trellis の主要機能はほぼ自前で充足している。

## 3. 採用の障壁

1. **AGPL-3.0**（最重要）: 商用の金融サービスである UATa が AGPL ツールの生成物・改変物を
   どう扱うかは法務判断が必要。CLI を dev ツールとして使うだけなら影響は限定的だが、
   生成された `.trellis/` をリポジトリに commit して配布物に含める場合は伝播リスクの検討が必要。
2. **二重管理**: `.trellis/spec/` と `CLAUDE.md` の両方を保守すると、CLAUDE.md 分割 refactor
   （2026-05-21 core/lessons/ops 分離）で避けたかった「正本の二重化」が再発する。
3. **SessionStart Hook との競合**: UATa は `load-claude-lessons.sh` で lessons を auto-Read する
   仕組みを持つ。Trellis の workspace ジャーナルと役割が重なる。

## 4. 取り込む価値のある設計思想（Trellis を入れずに流用）

Trellis 本体は入れないが、以下の概念は既存構造の改善に使える:

- **scoped spec**: CLAUDE.md がモノリシック化する問題は、UATa も 2026-05-21 に core/lessons/ops 分割で
  対処済み。さらに module 単位の小 spec（例: `docs/ops/05_backend_modules_map.md`）を増やす方向は妥当。
- **task PRD**: Asana タスク notes に「触るファイル / DoD / 実装ステップ」を構造化する運用は
  既に `.claude/agents/Planner.md` の出力フォーマットで標準化済み。
- **workflow gate**: 本評価と同時に追加した `.claude/skills/human-review-gate` が同等の役割を果たす。

## 5. 再評価の条件

以下が変われば再評価する:
- Trellis がライセンスを許容的なもの（MIT/Apache）に変更した場合
- UATa が Cursor / OpenCode など複数の AI コーディングツールを横断運用する必要が出た場合
  （現状は Claude Code CLI 単独運用のため、マルチプラットフォーム共有の価値が低い）

## 6. 参照

- https://github.com/mindfold-ai/Trellis（AGPL-3.0）
- `docs/ops/agent_pipeline_v1.md`（UATa 自走パイプライン）
- `.claude/skills/human-review-gate/SKILL.md`
- CLAUDE.md「## 朝プロトコル §9」「Phase 終了処理」
