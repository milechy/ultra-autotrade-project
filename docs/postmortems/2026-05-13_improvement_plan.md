# 2026-05-13 Claude Code 運用改善計画

**作成**: 2026-05-13 ストリーム F  
**Asana GID**: 1214737294340621  
**対象ブランチ**: feat/5-13-F  
**ベース情報**: .claude/agents/ × 9 / .claude/skills/ × 4 / .claude/commands/ × 2 + bg-launch.log 実測値

---

## 概要

本稿は 2026-05-13 時点の Ultra AutoTrade Claude Code 運用インベントリ調査で判明した  
「未実装・要修正・要明記」の空白を優先度付けし、Phase 2/3/4 の改善体制をまとめたものである。  
調査ファイル `/tmp/uata_claude_code_inventory_20260513_0735.md` が参照不能だったため、  
bg-launch.log 実測値・CLAUDE.md 全文・.claude/ ディレクトリ直読みで代替情報を補完した。

---

## §D-1 空白 件 — 優先度付き一覧

> "6件" は未済項目のカウント。P0 env Hook は 済 扱い。

| # | 優先度 | 種別 | 名称 | 状態 | 担当フェーズ |
|---|--------|------|------|------|-------------|
| 1 | **P0** | docs 修正 | OAuth 記述 → Claude Max account ログインに修正 | 要修正 | Phase 2 (即時) |
| 2 | **P0** | hook | env guard hook (`guard-env-files.sh`) | **済** ✓ | 完了 |
| 3 | **P1** | agent | `parallel-lane-worker` agent 新規作成 | 未実装 | Phase 3 |
| 4 | **P1** | skill | `production-deploy` skill 新規作成 | 未実装 | Phase 3 |
| 5 | **P1** | skill | `prod-curl` skill 新規作成 | 未実装 | Phase 3 |
| 6 | **P1** | skill | `db-ops` skill 新規作成 | 未実装 | Phase 3 |
| 7 | **P2** | routine | `healthcheck` 定期ルーティン (cron/schedule) | 未実装 | Phase 4 |
| 8 | **P2** | loop | Lane T `/loop` 設定 | 未実装 | Phase 4 |

### P0-1: OAuth 記述修正 — 詳細

**現状の問題**:  
インベントリ §15 および関連ドキュメントで Claude Code の認証フローを「OAuth」として記述している箇所がある。  
実際は **Claude Max account（claude.ai サブスクリプション）によるログイン** であり、OAuth flow は存在しない。

**影響箇所**（要確認・修正）:
- インベントリ §15 (今後再作成時に修正)
- CLAUDE.md の Claude Code 設定セクション（現時点では OAuth 明示なし — 追記不要の可能性）
- docs/ 内で「OAuth」と記述している箇所: `docs/26_slack_automation_guide.md`（Slack App OAuth — これはアプリ側 OAuth であり Claude Code とは無関係。混同注意）

**修正アクション**:
1. 新規 CLAUDE.md セクション「## Claude Code 認証」を追加: 「Claude Code は claude.ai Claude Max アカウントでログイン。API Key 方式も可。OAuth flow は Claude Code 自体には存在しない」
2. インベントリ §15 再作成時は「OAuth」表記を削除し実態を記載

---

## Phase 2/3/4 体制プラン

### Phase 2（即時 — 本週中）

**目的**: P0 修正 + CLAUDE.md 整合性

| タスク | 担当 | ファイル | Tier |
|--------|------|----------|------|
| OAuth 記述を Claude Max account ログインに修正 | Sonnet (現在) | CLAUDE.md | S |
| CLAUDE.md L396 に agents / BG session 区別注記追加 | Sonnet (現在) | CLAUDE.md | S |
| CLAUDE.md 分割計画の実行（43.7k → 40k 未満）| Sonnet 単独 | CLAUDE.md + docs/ops/ | S |

> Tier S のため **1日1PR**。ストリーム F ブランチ (feat/5-13-F) に集約する。

### Phase 3（今週〜来週初め）

**目的**: P1 スキル・エージェント追加でオペレーション自動化カバレッジ拡大

| タスク | 担当 | ファイル | Tier |
|--------|------|----------|------|
| `parallel-lane-worker` agent 新規作成 | Sonnet | `.claude/agents/parallel-lane-worker.md` | B |
| `production-deploy` skill 新規作成 | Sonnet | `.claude/skills/production-deploy/SKILL.md` | B |
| `prod-curl` skill 新規作成 | Sonnet | `.claude/skills/prod-curl/SKILL.md` | B |
| `db-ops` skill 新規作成 | Sonnet | `.claude/skills/db-ops/SKILL.md` | B |

> Tier B のため並列レーン化可。Agent Teams + worktree モード推奨。

### Phase 4（来週以降）

**目的**: P2 自動化ルーティン稼働

| タスク | 担当 | ファイル | 備考 |
|--------|------|----------|------|
| `healthcheck` 定期ルーティン設定 | Haiku | `/schedule` コマンド or cron | 外形 `/health` 5分間隔 |
| Lane T `/loop` 設定 | Sonnet | `.claude/commands/` or セッション内 | Lane T 定義要確認 |

---

## 既存アセット流用方針

### 9 Agents（`.claude/agents/`）

| エージェント | 現用途 | Phase 3 流用先 |
|-------------|--------|---------------|
| `morning-protocol` | 朝の Asana 確認 | そのまま維持 |
| `team-coordinator` | Asana → Tier 判定 → レーン化 | **`parallel-lane-worker` の前段処理として流用**。GID 取得まで任せ、worktree 起動は新 agent が担当 |
| `phase1-investigator` | 本番 read-only 確認 | `prod-curl` skill の前段として呼び出し。READ-ONLY 制約はそのまま維持 |
| `phase2-implementer` | 本番変更計画 | `production-deploy` skill の設計段階で呼び出し |
| `phase3-deployer` | 本番変更実行 | `production-deploy` skill の実行段階で呼び出し。ただし `deploy_production.sh` 必須ルールを引き継ぐ |
| `deploy-checker` | デプロイ前チェックリスト | `production-deploy` skill 内部から自動呼び出し |
| `security-reviewer` | Aave/DeFi レビュー | `db-ops` skill の DDL 変更時にも呼び出し検討 |
| `test-runner` | 7段階 DoD ゲート | 新 skill にも `@test-runner` 呼び出しフックを組み込む |
| `i18n-checker` | 翻訳漏れチェック | 現状のまま。フロントエンド変更 PR に組み込み |

**設計方針**: 既存 9 agents は **スペシャリスト層**。新規 P1 skills/agents は既存エージェントを `@agent-name` で呼び出す **オーケストレーター層** として設計する。重複実装しない。

### 4 Skills（`.claude/skills/`）

| スキル | 現用途 | 拡張方針 |
|--------|--------|---------|
| `ultra-staging-deploy` | staging Hetzner デプロイ | **`production-deploy` skill のテンプレートとして流用**。staging 固有部分を置き換えるだけ |
| `defi-aave-review` | Aave コードレビュー | 新 `db-ops` skill で Aave 関連 DB 操作をレビューするときに呼び出し |
| `defi-security-audit` | セキュリティ監査 | `production-deploy` skill の gate として組み込み |
| `defi-transparency-report` | パートナー向けレポート生成 | 現状維持。他 skill との連携なし |

**設計方針**: `ultra-staging-deploy` の構造（when-to-use / 前提条件 / 実行手順 / DoD / ロールバック）を  
そのまま `production-deploy` と `prod-curl` と `db-ops` のテンプレートにする。コピー改変で作成。

### 2 Slash（`.claude/commands/`）

| コマンド | 現用途 | Phase 3/4 方針 |
|---------|--------|---------------|
| `/verify` | DoD 一括チェック (ruff/mypy/pytest) | **そのまま維持**。新規 skill 内からも `scripts/verify.sh` を呼び出す |
| `/plan-review` | Codex Gate レビュー | **そのまま維持**。P1 skill 作成前に `/plan-review` を実行するフローを CLAUDE.md に明記 |

---

## 追加必須対応事項

### (1) §15 OAuth 記述修正

上記 §D-1 #1 参照。要点:
- Claude Code 自体に OAuth は存在しない（Claude Max account login）
- アプリ内 OAuth（LINE, Slack）との混同を防ぐため、用語を分離して明記
- `docs/15_rollback_procedures.md` には OAuth 記述なし → 修正不要
- 新規 CLAUDE.md セクション「## Claude Code 認証」を追加する

### (2) CLAUDE.md 43.7k → 40k 未満への分割計画

**現状**: 43,738 chars / 1,123 lines

**削減対象セクション**（合計 ~21,180 chars）:

| セクション | 現 chars | アクション | 削減後 CLAUDE.md |
|-----------|---------|-----------|----------------|
| §23 デプロイ時の教訓 | 11,076 | `docs/ops/04_deploy_lessons.md` に移動。CLAUDE.md には「詳細は docs/ops/04_deploy_lessons.md 参照」の3行ポインタのみ残す | ~200 |
| §25 環境ファイル更新ルール | 10,104 | `docs/ops/05_env_update_rules.md` に移動。禁止事項3行 + ポインタのみ CLAUDE.md に残す | ~150 |

**削減効果試算**:
```
43,738 - (11,076 - 200) - (10,104 - 150) = 43,738 - 10,876 - 9,954 = 22,908 chars
```

→ 22,908 chars (49% 削減) で 40k 未満を達成。これで context 圧迫問題を解消。

**実行手順**:
1. `docs/ops/04_deploy_lessons.md` を新規作成 → §23 本文をそのまま移動
2. `docs/ops/05_env_update_rules.md` を新規作成 → §25 本文をそのまま移動  
3. CLAUDE.md §23 / §25 をポインタ行に置き換え
4. `docs/参照ファイル表` を更新
5. Tier S → feat/5-13-F ブランチに集約 → PR → main マージ

**実行スケジュール**: Phase 2（本週中）。PR は §D-1 #1 / (3) / (4) と同一 PR に束ねてよい。

### (3) CLAUDE.md L396 — `claude agents` と `.claude/agents/` の混同防止

**問題**: CLAUDE.md L397 の見出し `## Claude Code 最新機能活用ガイド` の §1 が  
「`.claude/agents/` にMarkdownファイルでサブエージェントを定義」と書いているが、  
**`claude agents` という CLI コマンドが「バックグラウンドセッション一覧」を返す**ことと  
混同しやすい。

**実測値**（`/tmp/uata-5-13-F-bg-launch.log`）:
```
backgrounded · b693c6c4
  claude agents             list sessions      ← BG セッション一覧
  claude attach b693c6c4    open in this terminal
  claude logs b693c6c4      show recent output
  claude stop b693c6c4      stop this session
```

**修正内容**: CLAUDE.md L405 の「**Ultra AutoTrade 定義済みエージェント（`.claude/agents/`）:**」の直前に以下の注記を追加:

```markdown
> **⚠️ 用語注意**: `claude agents` (CLI コマンド) はバックグラウンド BG セッション一覧を返す。
> `.claude/agents/` は**サブエージェント定義ファイル置き場**であり、実行中 BG セッション一覧ではない。
```

### (4) `claude --bg` 構文確定情報（Step 3-1 実測）

**確認方法**: `/tmp/uata-5-13-F-bg-launch.log` の実測出力から逆算

**確定した構文**:

```bash
# バックグラウンドセッション起動（ストリーム F の例）
claude --bg "タスク内容"
# または
claude -b "タスク内容"

# 起動後の出力:
# backgrounded · <session-id>  (例: b693c6c4)
#   claude agents             list sessions
#   claude attach <session-id>    open in this terminal
#   claude logs <session-id>      show recent output
#   claude stop <session-id>      stop this session
```

**セッション管理コマンド**:

```bash
claude agents                    # 全 BG セッション一覧
claude attach <session-id>       # ターミナルにアタッチ
claude logs <session-id>         # 出力ログ確認
claude stop <session-id>         # セッション停止
```

**CLAUDE.md への追加場所**: §22 `## Skills & Hooks` の直後、または新規 `## Claude Code BG Session 管理` セクションとして追加。

**活用場面**:
- 並列ストリーム起動: `for i in A B C D E F; do claude --bg "ストリーム $i: ..."; done`
- BG セッションのログ監視: `claude logs <id>` を別ターミナルで watch
- AG Teams との使い分け: チームメイト間通信不要・独立タスクは `claude --bg`、協調が必要なら Agent Teams

---

## 新規アセット仕様（Phase 3 実装時の設計指針）

### `parallel-lane-worker` agent

```yaml
---
name: parallel-lane-worker
description: >
  BG セッションを使ったレーン並列実行の実行係。
  team-coordinator が生成したレーン編成を受け取り、
  claude --bg で各レーンを起動し、claude agents で監視する。
tools:
  - Bash  # claude --bg / claude agents / claude logs / claude stop
  - Read
---
```

**処理フロー**:
1. `team-coordinator` の出力（レーン編成表 + 起動コマンド）を受け取る
2. 各レーンを `claude --bg "..."` で起動
3. `claude agents` で全セッションの状態を監視
4. 完了検知 → `claude logs <id>` で結果取得 → Slack 通知

### `production-deploy` skill

`ultra-staging-deploy/SKILL.md` をベースに以下を変更:
- `docker-compose.staging.yml` → `docker-compose.production.yml`
- `.env.staging` → `.env.production`
- `ultra-autotrade-*-staging` → `ultra-autotrade-*-production`
- **`deploy_production.sh` 必須ルール** (手打ち docker compose build 禁止) を先頭に追加
- Gate 8 (外形 /health 確認) を必須ステップに追加

### `prod-curl` skill

```
用途: 本番 API への read-only curl 操作（GET/HEAD のみ）
前提: phase1-investigator の制約をスキルとして自動化
主な操作:
  - curl -sf https://api.ultra-auto-trade.com/health
  - curl -sf https://api.ultra-auto-trade.com/exchange/status
  - curl -sf https://api.ultra-auto-trade.com/ai/status
出力: JSON を python3 -m json.tool で整形して表示
制約: POST/PUT/DELETE 禁止。CF Access Service Token は環境変数から取得
```

### `db-ops` skill

```
用途: staging DB への読み取り・テストデータ投入
制約:
  - production DB への INSERT/UPDATE/DELETE は絶対禁止
  - staging コンテナ名に "staging" が含まれることをスクリプト先頭でチェック
  - ALTER TABLE は staging のみ可（production は docs/ops/02_db_tables.md の手順に従う）
前提確認: phase1-investigator で先にコンテナ名・DB名を確認してから実行
```

---

## 実装スケジュール（フェーズ別）

```
Week 1 (2026-05-13〜05-16):
  Phase 2 (即時対応)
  ├── [本日] CLAUDE.md 修正 PR 作成 (L396 注記 + OAuth 修正 + --bg 構文追記)
  ├── [本日] CLAUDE.md 分割計画の実行 (43.7k → ~23k)
  └── [本日] feat/5-13-F → PR → main マージ

Week 2 (2026-05-19〜05-23):
  Phase 3 (P1 スキル・エージェント)
  ├── parallel-lane-worker agent 作成 (Tier B — 独立ブランチ)
  ├── production-deploy skill 作成 (ultra-staging-deploy をコピー改変)
  ├── prod-curl skill 作成
  └── db-ops skill 作成

Week 3 (2026-05-26〜):
  Phase 4 (P2 自動化)
  ├── healthcheck routine (/schedule で 5 分間隔外形確認)
  └── Lane T /loop 設定 (Lane T の定義確定後)
```

---

## 既知リスクと緩和策

| リスク | 影響 | 緩和策 |
|--------|------|--------|
| CLAUDE.md 分割で既存 grep/参照が切れる | 中 | docs/参照ファイル表を先に更新。`grep -r "デプロイ時の教訓"` → `grep "04_deploy_lessons"` に更新 |
| `claude agents` と `.claude/agents/` の混同が残る | 低 | Phase 2 で即時注記追加 |
| `parallel-lane-worker` が team-coordinator と機能重複 | 低 | team-coordinator は「計画」、parallel-lane-worker は「実行」と役割分離を仕様に明記 |
| BG セッション起動で `--bg` フラグが将来廃止・変更 | 低 | CLAUDE.md の構文情報は「実測値」と明記し、バージョン変更時に更新を促す |
| production-deploy skill が手打ち docker compose を呼ぶ可能性 | 高 | CLAUDE.md「deploy_production.sh 必須ルール」をスキル冒頭に警告ボックスで再掲 |

---

## Asana 更新内容

Asana GID 1214737294340621 に以下のコメントを追加予定:
- §D-1 優先度付きリスト確定
- Phase 2/3/4 実装スケジュール確定
- 既存 9 agent / 4 skill / 2 slash の流用方針確定

---

*第 1 稿: 2026-05-13 ストリーム F*  
*インベントリファイル未参照のため、bg-launch.log 実測値 + CLAUDE.md 直読みで補完*  
*インベントリファイル入手後に §D-1 件数・詳細を照合・更新すること*
