---
name: human-review-gate
description: Determine whether an autonomous development change requires human approval before proceeding. MUST use BEFORE committing or applying any change during autonomous/pipeline work. Stops on Tier S files, Aave/Health-Factor/Decimal logic, production DB write/deploy, secret-key access, and dependency additions. Tier-B new-file-only changes proceed automatically.
---

# Human Review Gate Skill

自走開発パイプライン（Planner→Generator→Evaluator→Tester / `docs/ops/agent_pipeline_v1.md`）が
**人間承認を挟まずに進んでよい変更か** を判定する。DannyMac180/skills の codex-dynamic-workflows の
承認ゲートパターンを、Ultra AutoTrade の Tier 分類・Security Rules に接続したもの。

> このスキルは**開発時の変更**に対するゲート。アプリ実行時の取引承認（`proposals` / `emergency_stop`）
> とは別レイヤー。混同しないこと。

## When to Use (Automatic Triggers)

以下の操作の **直前** に発火する想定:

1. `git commit` / ファイルの Write・Edit を適用する前（自走モード時）
2. Generator がプランに着手する前（Planner が立てたゲートの確認）
3. PR を作成する前
4. デプロイ・本番 DB 操作・スケジューラ配線変更の前

## 判定ロジック（このフローで分類する）

```
変更対象ファイル / 操作を列挙
        │
        ▼
 ┌─────────────────────────────────────────────┐
 │ STOP 条件のいずれかに該当するか？             │
 └─────────────────────────────────────────────┘
   │ YES → 🛑 HUMAN-REVIEW-REQUIRED（停止して人間承認を待つ）
   │ NO  → ✅ 自動進行可（Tier B 新規ファイルのみ）
```

### 🛑 STOP（人間承認必須）

| カテゴリ | 該当 | 根拠 |
|---|---|---|
| **Tier S ファイル** | `backend/app/main.py` / `requirements.txt` / `pyproject.toml` / `frontend/package.json` / `package-lock.json` / `.github/workflows/ci.yml` / `docker-compose.*.yml` / `nginx/upstream.*.conf` / `migrations/versions/*.py`（新規） / `database.py` / `automation/{scheduled_tasks,monitoring_service,workflow}.py` / `CLAUDE.md` / `CLAUDE.lessons.md` / `.claude/agents/*.md`（既存本体の上書き） | CLAUDE.md「Tier 分類」: 同時編集禁止・1日1PR |
| **DeFi 安全装置** | Aave トランザクション経路 / Health Factor ロジック / Decimal 計算 / `aave/` 配下の挙動変更 | Security Rules: HF<1.6→HARD_STOP / Decimal型のみ |
| **本番操作** | 本番 DB write / `deploy_production.sh` / `deploy_staging.sh` / 本番 VPS での git 操作 / 秘密鍵に触れる処理 | CLAUDE.md「本番デプロイフロー」 |
| **依存追加** | `requirements.txt` / `pyproject.toml` / `package.json` への新規依存 | Tier S + 並列開発でのlock同期事故 |
| **ロールバック不能** | migration 適用 / 不可逆な本番 SQL / volume 削除 | docs/15_rollback_procedures.md |

### ✅ 自動進行（承認不要 / Tier B 新規ファイルのみ）

| 該当 | 条件 |
|---|---|
| `docs/*.md`（新規） | 別ファイル |
| `scripts/*.sh`（新規） | 既存スクリプトを書き換えない |
| `.claude/skills/**`（新規） / `.claude/agents/*.md`（**新規追加のみ**、既存上書きは STOP） | 別ファイル |
| `backend/tests/*.py`（新規） | 別ファイル・既存テストを壊さない |
| `frontend/components/*.tsx`（新規） | 別ファイル |
| `.github/workflows/*.yml`（**新規・ci.yml 以外**） | ci.yml 本体への統合は STOP |
| `backend/app/protocols/*/*.py` | Phase 2 PoC は分離 |

## 停止時の出力フォーマット

```
🛑 HUMAN-REVIEW-REQUIRED

対象: <ファイル / 操作>
カテゴリ: <Tier S | DeFi安全装置 | 本番操作 | 依存追加 | ロールバック不能>
理由: <1行>
提示する3案（phase2-implementer 準拠）:
  - 最小案: ...
  - 標準案: ...
  - 根本案: ...
人間の承認を待機。承認なしに次フェーズへ進まない。
```

## 自動進行時の出力

```
✅ 自動進行可（Tier B / 新規ファイルのみ）
対象: <ファイル一覧>
→ Generator 着手 / commit を継続
```

## 差し戻しループの上限

同一タスクで Generator↔Evaluator の差し戻しが **3 往復** を超えたら、Tier に関わらず
🛑 HUMAN-REVIEW-REQUIRED に切り替える（`.claude/rules/night-mode-ci-autofix.md` の 3 往復制限）。

## 参照

- `docs/ops/agent_pipeline_v1.md`（パイプライン全体 / §6 人間承認ゲート）
- `.claude/agents/Planner.md`（Step 4 高リスク検出）
- `.claude/rules/night-mode-ci-autofix.md`（自動解消対象 / 除外 / 3往復制限）
- `.claude/agents/phase2-implementer.md`（3案提示パターン）
- CLAUDE.md「Tier 分類」「Security Rules (ABSOLUTE)」
