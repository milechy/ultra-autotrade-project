# scripts/ パイプライン補助スクリプト集

Ultra AutoTrade 自走開発パイプライン（Planner → Generator → Evaluator → Tester）を
支える品質ゲート・自動隔離スクリプトのリファレンス。ここでは
`docs/ops/agent_pipeline_v1.md` で導入した 6 本のスクリプトを集約して説明する。

> このドキュメントは「使い方の正本」。各スクリプト冒頭のコメントと内容が食い違った場合は、
> 実コード（スクリプト本体）を真実源とすること。

---

## 一覧

| スクリプト | 用途 | 前提 | 種別 |
|---|---|---|---|
| `run_repomix.sh` | リポジトリを単一 XML にパック（Gate 5 孤立コード検出の前処理） | node / npx | bash |
| `run_skillspector.sh` | `.claude/agents` / `.claude/skills` を NVIDIA SkillSpector でセキュリティスキャン | uv / git / make /（任意 jq） | bash |
| `run_code_review.sh` | Alibaba Open Code Review で PR diff を Claude レビュー（Gate 6 補完） | node / npm / `ANTHROPIC_API_KEY` | bash |
| `run_skillopt.py` + `skillopt_config.json` | microsoft/SkillOpt でエージェント定義を最適化する**安全ハーネス** | python3 /（実最適化時）`ANTHROPIC_API_KEY` + skillopt | python + JSON |
| `auto_isolate.sh` | `agent_pipeline_v1.md` §5 の自動隔離（rebase 衝突・未コミット退避・隔離・リグレッション検査） | git | bash |

> 種別「bash」「python」は実行系の違い。CI / Gate へ組み込む際の前提コマンドが揃っているかを
> 必ず確認すること（前提コマンド未充足のスクリプトは silent に no-op しがち）。

---

## run_repomix.sh

### 目的
リポジトリ（既定は `backend/`）を 1 つの AI フレンドリーな XML ファイルにパックし、
**Gate 5（孤立コード検出 / `docs/ops/orphan_detection.md`）の前処理**として
「実装されているが呼ばれていない」コードを Claude に一括で渡せるようにする。
並列レーン起動時のコンテキスト準備にも使う。

### 使い方
```bash
./scripts/run_repomix.sh                  # backend/ をパック（既定）
./scripts/run_repomix.sh backend/app/aave # 特定サブツリーのみ
./scripts/run_repomix.sh .                # リポジトリ全体
```
内部では `npx -y repomix@latest --config repomix.config.json --include "<TARGET>/**"`
を実行する。repomix は npx 経由で取得するため事前 install 不要。

### 出力
- `repomix-output.xml`（リポジトリ root / `.gitignore` 済み = コミットされない）

### 環境変数
- なし（引数 `$1` で対象サブツリーを指定。既定 `backend`）

### exit code
| code | 意味 |
|---|---|
| 0 | パック成功（出力ファイル生成あり） |
| 1 | `repomix-output.xml` が生成されなかった（パック失敗） |

### 前提
- node / npx（dev VPS は node v22）
- 除外設定ファイル `repomix.config.json`（`.env*` / `*.key` / `*.pem` / `node_modules` /
  `__pycache__` / `migrations` 等を除外）

---

## run_skillspector.sh

### 目的
`.claude/agents/*.md` と `.claude/skills/**/`（ディレクトリ単位）を
**NVIDIA SkillSpector**（Apache-2.0）でセキュリティスキャンし、
プロンプトインジェクション・権限昇格・データ流出パターンを検出する。
外部スキルを導入する前の審査として、金融システムの安全性を強化する。

### 使い方
```bash
./scripts/run_skillspector.sh        # スキャンして結果表示（人間確認用）
./scripts/run_skillspector.sh --ci   # CI モード: HIGH/CRITICAL 検出で exit 1
```

### 環境変数（すべて任意）
| 変数 | 既定 | 意味 |
|---|---|---|
| `SKILLSPECTOR_DIR` | `/tmp/skillspector` | SkillSpector の clone 先 |
| `REPORT_DIR` | `/tmp/skillspector-reports` | JSON レポート出力先 |
| `FAIL_SEVERITIES` | `HIGH CRITICAL` | blocking 扱いにする severity（スペース区切り） |

### exit code
| code | 意味 |
|---|---|
| 0 | 通常モード、または `--ci` で blocking 検出なし |
| 1 | `--ci` モードで `FAIL_SEVERITIES` に該当する検出があった |

> **設計メモ**: SkillSpector の README は「脆弱性検出時の exit code」を明記していないため、
> 本スクリプトは scan の終了コードに依存せず（`|| true`）、JSON 出力を `jq` でパースして
> severity を判定する。`jq` 不在時は判定をスキップし「人間が JSON を確認すること」と表示する。

### 前提
- uv（無ければ `astral.sh` から自動 install を試みる）/ git / make
- 任意: `jq`（不在でも動くが severity 自動判定はされない）

---

## run_code_review.sh

### 目的
**Alibaba Open Code Review**（`ocr` / Apache-2.0）で PR の git diff を Claude にレビューさせ、
行レベルの指摘を生成する。手動 **Gate 6（`/codex:review`）を補完**する位置づけ。
変更に `backend/app/aave/` が含まれる場合は「セキュリティ重点レビュー対象」として警告を出す。

### 使い方
```bash
./scripts/run_code_review.sh                    # origin/main..HEAD をレビュー
BASE=origin/dev ./scripts/run_code_review.sh    # base を変更
OUTPUT=review.json ./scripts/run_code_review.sh # 出力先を指定
```

### 環境変数
| 変数 | 必須/任意 | 既定 | 意味 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **必須** | — | Claude API キー（内部で `OCR_LLM_TOKEN` にマップ） |
| `BASE` | 任意 | `origin/main` | diff の base ref |
| `HEAD_REF` | 任意 | `HEAD` | diff の head ref |
| `OUTPUT` | 任意 | `/tmp/ocr-review.json` | レビュー JSON の出力先 |
| `OCR_LLM_MODEL` | 任意 | `claude-sonnet-4-6` | レビューに使うモデル |
| `OCR_LLM_URL` | 任意 | `https://api.anthropic.com` | API エンドポイント |

### exit code
| code | 意味 |
|---|---|
| 0 | レビュー出力が生成された |
| 1 | レビュー出力が生成されなかった |
| 2 | `ANTHROPIC_API_KEY` が未設定（CI では Secrets から渡す） |

### 前提
- node / npm（`ocr` が無ければ `npm install -g @alibaba-group/open-code-review` を試みる）
- `ANTHROPIC_API_KEY`（CI では GitHub Secrets 経由）
- 任意: `jq`（あれば指摘件数の目安を表示）

---

## run_skillopt.py + skillopt_config.json

### 目的
**microsoft/SkillOpt**（MIT）でエージェント定義（`.claude/agents/*.md`）を、モデルウェイトを
変更せずテキスト空間で最適化するための**安全ハーネス**。本スクリプトの核心は最適化そのものでは
なく、**原本を絶対に壊さない安全機構**にある。

> ⚠ **安全機構 4 点（必読）**
> 1. 原本 `.claude/agents/*.md` を**絶対に上書きしない**（Tier S 相当として扱う）
> 2. 最適化結果は `*.optimized.md` にのみ書き出す（例: `Planner.md` → `Planner.optimized.md`）
> 3. 原本との **unified diff** を生成し、人間が確認できる形にする
> 4. 原本への**反映は人間承認後に手動**で行う（このスクリプトは反映しない＝**HUMAN-REVIEW-REQUIRED**）

### 使い方
```bash
python scripts/run_skillopt.py --dry-run  # 設定検証 + 計画表示のみ（API 不要）
python scripts/run_skillopt.py            # 最適化を実行し *.optimized.md を生成
python scripts/run_skillopt.py --diff     # 既存の *.optimized.md と原本の diff を表示
```

### 設定ファイル `skillopt_config.json`
| キー | 値 |
|---|---|
| `backend` | `claude` |
| `model` | `claude-sonnet-4-6` |
| `output_suffix` | `.optimized.md`（原本を上書きしない担保） |
| `targets` | `Planner.md` / `Generator.md` / `Evaluator.md` / `Tester.md` の 4 エージェント |
| `safety.never_overwrite_originals` | `true`（false だと検証で問題扱い） |
| `safety.require_human_approval_before_apply` | `true` |

> **注記（未整備）**: `skillopt_config.json` の各 target が参照する `validation_tasks`
> （`scripts/skillopt_validation/planner_tasks.jsonl` 等）の置き場 `scripts/skillopt_validation/`
> は**現時点で未整備（今後整備予定）**。実最適化の held-out validation を回すには、このディレクトリと
> タスク定義 `*.jsonl` を別途作成する必要がある。本 README はこのパスを「実在する」とは断定しない。

### 環境変数
| 変数 | 必須/任意 | 意味 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 実最適化時のみ**必須** | Claude backend 用（`--dry-run` / `--diff` では不要） |
| `SKILLOPT_EXTRA_ARGS` | 任意 | SkillOpt 本体の未確定引数を外から注入（CLI 仕様は `docs/guideline.html` 参照） |

### exit code
| code | 意味 |
|---|---|
| 0 | `--dry-run` / `--diff` 正常終了、または実最適化で全対象成功 |
| 1 | 設定/対象ファイルの検証で問題あり（例: 原本保護無効・対象不在）。または実最適化で一部失敗 |
| 2 | 実最適化時に `ANTHROPIC_API_KEY` が未設定 |

> **重要**: exit code に関わらず、実最適化を行った場合は必ず
> `🛑 HUMAN-REVIEW-REQUIRED: 原本への反映は手動` のメッセージが出力される。
> exit 0（全成功）でも「原本へ反映済み」を意味しない — 反映は人間が `--diff` で差分確認後に
> 手動で原本を置き換える。**自走パイプラインがこのスクリプトの結果を自動コミットしてはならない。**

### 前提
- python3
- 実最適化時: `ANTHROPIC_API_KEY` + `skillopt`（`pip install skillopt`）
- `--dry-run` / `--diff` は API キー不要（設定検証と差分表示のみ）

---

## auto_isolate.sh

### 目的
`docs/ops/agent_pipeline_v1.md` §5 の**自動隔離**を実装する。失敗（rebase 衝突・リグレッション・
未コミット変更）を main / 作業ブランチに持ち込まず、隔離ブランチ（`quarantine/*`）に閉じ込め、
解決不能なものだけ人間にエスカレーションする。CLAUDE.md 並列開発フロー鉄則 3（rebase origin/main）/
鉄則 6（stash・未コミット変更を残さない）に対応。

### 使い方（サブコマンド）
```bash
./scripts/auto_isolate.sh rebase                  # origin/main に rebase。衝突→自動 abort + 隔離ブランチ作成
./scripts/auto_isolate.sh stash-guard             # 未コミット変更を stash に退避（delete vs modify 衝突防止）
./scripts/auto_isolate.sh quarantine <reason>     # 現在の変更を隔離ブランチに退避
./scripts/auto_isolate.sh check-regression <cmd>  # <cmd>（テスト）を実行。落ちたら隔離ブランチ作成
```

### 各サブコマンドの挙動
- **rebase** — `git fetch origin` → `git rebase origin/main`。成功で exit 0。衝突を検出したら
  `git rebase --abort` して元ブランチを rebase 前に戻し（main 汚染なし）、現状を
  `quarantine/rebase-conflict-<branch>-<timestamp>` ブランチに保全して exit 1。
- **stash-guard** — 未コミット変更があれば `git stash push -u` で退避（exit 0）。クリーンなら何もせず exit 0。
- **quarantine** — 現在の変更を `quarantine/<reason>-<timestamp>` ブランチに退避し、元ブランチを
  クリーンにする。常に HUMAN-REVIEW-REQUIRED として exit 1。
- **check-regression** — 渡したテストコマンドを実行。pass なら exit 0。fail なら
  `quarantine/regression-<branch>-<timestamp>` ブランチを作成し exit 1（原因切り分けを人間に促す）。

### 環境変数
- なし（引数のみ）

### exit code
| code | 意味 |
|---|---|
| 0 | 自動解決（rebase 成功 / クリーン / テスト pass） |
| 1 | 人間エスカレーション必要（衝突・隔離・リグレッション → `quarantine/*` ブランチに保全済み） |
| 2 | 引数エラー（不明なサブコマンド / 必須引数欠落 / `cd` 失敗） |

### 前提
- git（worktree / ブランチ内で実行すること。`set -uo pipefail` で `-e` は付けず、失敗を捕捉して判断する設計）

---

## 関連ドキュメント

- **`docs/ops/agent_pipeline_v1.md`** — 自走パイプライン（Planner → Generator → Evaluator → Tester）と
  §5 自動隔離の設計正本。`auto_isolate.sh` の根拠。
- **`docs/ops/orphan_detection.md`** — Gate 5 孤立コード検出（Dead Code / Disconnected Safety Scan）の
  検出プロンプト。`run_repomix.sh` の出力をここに渡す。
- **`CLAUDE.md`「Definition of Done (DoD)」/「標準チェックリスト（7 段階ゲート）」** — Gate 1-7 の正本。
  `run_code_review.sh` は Gate 6 を、`run_skillspector.sh` はエージェント定義の安全審査を補完する。
