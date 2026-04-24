# Claude Code 開発ガイド

## プロジェクト: Ultra AutoTrade

Based on:
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)

---

## Claude Code 設定

### グローバル設定
**ファイル:** `~/.claude/settings.json`
```json
{
  "cleanupPeriodDays": 99999
}
```
- **効果:** メモリ永続化（プロジェクトコンテキスト長期保持）
- **デフォルト:** 30日（短すぎる）

---

## 開発原則

### 1. Start Small, Iterate
- 大きな機能は小さく分割
- 例: Web3AaveClient
  1. まず `get_health_factor()` のみ
  2. 次に `deposit()` + テスト
  3. 最後に `withdraw()` + 統合テスト

### 2. Explicit is Better than Implicit
- 全ての動作を明示的に
- 暗黙の副作用を避ける
- ログには「何をしたか」「なぜしたか」を記録

### 3. Trust but Verify
- コード生成後は必ずテスト実行
- staging環境で動作確認
- ログとトランザクションを確認

### 4. Use Plan Mode for High-Risk Changes
- Aave / Automation / State 関連は必ず Plan モード
- 変更内容をレビューしてから実行

---

## Definition of Done (DoD)

コード変更をコミットする前に、以下をすべて通過させること:

1. `ruff check .` — lint エラー 0
2. `ruff format --check .` — フォーマット違反 0
3. `mypy app/ --config-file ../pyproject.toml` — 型エラー 0
4. `pytest tests/ --cov=app --cov-fail-under=80 -q` — 全テスト通過 + coverage 80%+
5. `ruff check . --select S` — セキュリティ警告の確認（新規の critical なし）

### 一括検証（コミット前に必ず実行）
```bash
./scripts/verify.sh
```

### Core Principles (3つのみ)

1. **Simplicity First** — 最小限の変更で目的を達成する。過剰な抽象化・将来対応は不要
2. **No Laziness** — テスト・lint・フォーマットを省略しない。verify コマンドで確認
3. **Minimal Impact** — 既存コードへの影響を最小化。変更はスコープ内に限定

---

## Architecture

- Backend: FastAPI (Python 3.11) — Hetzner VPS (Docker Compose)
- Frontend: Next.js App Router + shadcn/ui + TailwindCSS — Cloudflare Pages
- DB: PostgreSQL 16 + pgvector (HNSW index, NOT IVFFlat)
- Exchange: Bybit (primary, via ccxt) + OKX (backup)
- Aave: V3 on Polygon/Arbitrum (web3.py)
- AI: Claude Sonnet 4.6 (primary judge) + GPT-4o (cross-verify on BUY/SELL only)
- Proxy/DNS: Cloudflare Tunnel → Hetzner backend
- Notion: 完全撤去 → Knowledge Hub (PostgreSQL + pgvector)

---

## Frontend 開発ルール

### package.json に依存を追加した場合
`package.json` に依存を追加したら、必ず以下を実行して `package-lock.json` も一緒にコミットすること:

```bash
cd frontend
npm install --legacy-peer-deps
git add package.json package-lock.json
git commit -m "chore(frontend): ..."
```

**理由:** 並行開発で `package.json` が更新されると `package-lock.json` が同期されず、
Docker ビルド・CI が失敗する。`npm install` は `package.json` ベースで解決するため同期問題が起きない。
（`npm ci` は `package-lock.json` との完全一致を要求するため並行開発と相性が悪い）

---

## Security Rules (ABSOLUTE — docs/13_security_design.md)

## [CRITICAL] Security Rules
1. Private keys: environment variables ONLY. Never hardcode. Never log.
2. Health Factor < 1.6 → automatic HARD_STOP
3. Max single trade: 10% of total assets
4. Max daily trades: 30% of total assets
5. Cooldown: 10 minutes between Aave operations
6. Emergency stop flag: OR logic — manual stop can NEVER be overwritten
7. .env.staging and .env.production MUST use physically different keys
8. No tokens/keys in logs — mask to first 6 + last 4 chars
9. main branch: no direct push, PR + review required
10. LLM output MUST be JSON Schema validated — parse failure → HOLD
11. Financial calculations: Decimal type ONLY (never float)

## [CRITICAL] Definition of Done (DoD)
コミット前に以下を全通過:
1. `ruff check .` — lint エラー 0
2. `ruff format --check .` — フォーマット違反 0
3. `mypy app/ --config-file ../pyproject.toml` — 型エラー 0
4. `pytest tests/ --cov=app --cov-fail-under=80 -q` — 全通過 + coverage 80%+
5. `ruff check . --select S` — セキュリティ警告確認

## Core Principles
1. **Simplicity First** — 最小限の変更で目的を達成。過剰な抽象化不要
2. **No Laziness** — テスト・lint・フォーマットを省略しない
3. **Minimal Impact** — 既存コードへの影響を最小化

## Frontend ルール
- package.json変更時は `npm install --legacy-peer-deps` → package-lock.json も一緒にコミット
- rechartsは必ず `dynamic(() => import('./XxxRecharts'), { ssr: false })` で読み込む（SSRクラッシュ防止）
- `grep -E "ignoreBuildErrors|ignoreDuringBuilds" frontend/next.config.js` でOOMワークアラウンド確認
- Playwright E2E: デフォルトは本番URL直打ち。ローカルテスト時は `STAGING_URL=http://localhost:3000` + `npm run dev` 必須。77.42.46.155直IPは127.0.0.1バインドにより接続拒否される（正常）

---

## Key API Endpoints

- POST /knowledge/items — register knowledge (replaces /notion/ingest)
- GET  /knowledge/items?status=pending — fetch unprocessed items
- POST /knowledge/search — RAG vector search
- POST /ai/analyze — multi-LLM BUY/SELL/HOLD judgment
- POST /octobot/signal — OctoBot signals
- POST /aave/rebalance — Aave deposit/withdraw with safety
- POST /exchange/order — ccxt → Bybit order execution
- GET  /exchange/status — exchange connection & balance

---

## Directory Structure

```
backend/app/
├── knowledge/     # NEW: PostgreSQL + pgvector (replaces notion/)
│   ├── schemas.py, client.py, service.py, router.py
├── exchange/      # NEW: ccxt abstraction (Bybit/OKX)
│   ├── client.py, schemas.py, service.py, router.py
├── ai/            # ENHANCED: multi-LLM judge + JSON Schema
├── aave/          # UPGRADE: DummyClient → web3.py
├── bots/          # KEEP: OctoBot signals
├── automation/    # KEEP: monitoring, reporting, emergency stop
└── notifications/ # KEEP: Slack/LINE
```

---

## マルチLLM開発ワークフロー

### ロール割り当て
| LLM | ロール | 使うタイミング |
|-----|--------|---------------|
| **Claude Opus 4.6** | アーキテクト & インテグレーター | 新モジュール設計、Aave/セキュリティ、統合レビュー |
| **Claude Sonnet 4.5** | 高速実装 (デフォルト) | 実装80%、テスト、バグ修正、ドキュメント |
| **Claude Haiku 4.5** | インフラ & ユーティリティ | Docker、CI/CD、シェルスクリプト |
| **Codex 5.3** | 自動レビュアー | PR作成→GitHub Actions自動実行 |
| **GPT-4o** | クロス判定 (本番のみ) | BUY/SELL判定のPhase B、仕様書共同作成 |

### デバッグ昇格ルール
- フロントエンド / 一般バグ → Sonnet で開始
- 複雑 or 解決しない → Opus に昇格 (`claude --model opus`)
- Aave / セキュリティ → 最初から Opus
- CI / Docker → Haiku (`claude --model haiku`)

### ブランチ戦略
```
feature/* (各LLM担当) → dev (Opus統合) → staging (Codex最終レビュー) → main
```

---

## Testing (docs/14_test_strategy.md)

- Unit: pytest + mypy strict + ruff
- LLM: VCR replay (record once, replay in CI = zero API cost)
- E2E: Playwright (mobile viewport)
- Browser UI: Claude in Chrome (`claude --chrome`) — UIアップデート時のみ
- Codex Review: PR作成前に `/codex:review --base main --background`
- Dead Code Scan: PR作成前に孤立コード検出（新モジュール追加時・DeFi安全系変更時は必須）
- Aave: Sepolia testnet before mainnet
- Exchange: Bybit Sandbox API
- Coverage gate: 80%+ (pyproject.toml --cov-fail-under=80)
- CI: GitHub Actions (lint → test → security-check)
- テスト順序: pytest(自動) → tsc --noEmit(自動) → npm run build(自動) → Playwright E2E(自動) → 孤立コード検出(PR前) → Codex Review(PR前) → Claude in Chrome(UI変更時のみ)
- 一括検証: ./scripts/verify.sh（1-3を一括実行、コミット前に必須）
- PR/デプロイ前ゲート: 1-4 必須。5-7 は状況に応じて実施

---

## Codex Plugin 運用ルール (codex-plugin-cc)

### セットアップ済み
```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
```

### Review Gate: 常時OFF
Review gateは全コード変更で自動レビューが走り、使用量を大量消費する。常時OFFにする。
```
/codex:setup --disable-review-gate
```

### コスト最適化運用ルール
1. **普段の開発** → review gate OFF。Claude Code Agent Teamsで通常開発
2. **PR作成前のみ手動レビュー（1日1-2回）:**
   ```
   /codex:review --base main --background
   /codex:status
   /codex:result
   ```
3. **Aave/セキュリティ変更時のみ adversarial review:**
   ```
   /codex:adversarial-review --base main --background challenge the Aave safety logic and DeFi risk handling
   ```
4. **問題検出時** → Codexの指摘をClaude Codeに貼って修正させる
5. **バグ調査をCodexに委任:**
   ```
   /codex:rescue investigate why the tests started failing
   ```

### やらないこと
- review gate ON（使用量10-20倍になる）
- 小さな変更ごとのレビュー（PR前にまとめて1回）
- Codexだけに頼る（Claude Code + Codex の補完関係）

---

## 孤立コード検出（Dead Code / Disconnected Safety Scan）

### 背景
爆速開発で安全装置やリスク管理のコードを実装しても、配線（呼び出し元）が切れているケースが発生する。
UIテスト（/chrome）やpytestでは検出できない。2026-04-01に StressController、record_price_change_24h、PENDLE_YTキャップ、execute_evacuation の4件が孤立していた。

### 実行タイミング
- PR作成前（Codex Review前に実行）— 新モジュール追加時は必須
- 大量タスク一括完了後 — 爆速開発後は特にリスクが高い
- DeFi安全系の変更時 — aave/, automation/, protocols/ の変更時

### 実行方法（Claude Codeプロンプト）
プロジェクト全体で「実装されているが呼ばれていない」孤立コードを検出して。
重点チェック対象: backend/app/aave/, automation/, protocols/, ai/
方法: 各モジュールのpublicクラス/関数をリストアップ → grep -r でアプリコード内（tests/除外）の参照確認 → 参照0件=孤立
出力: | ファイル | クラス/関数 | アプリコードからの参照 | 状態(孤立/接続済み) |

### 検出後の対応
- P0: 安全装置系の孤立 → 即修正（workflow.pyやscheduled_tasks.pyに配線）
- P1: リスク管理系の孤立 → 1-2日以内に修正
- P2: ユーティリティ系の孤立 → 将来使用予定なら許容、不要なら削除

---

## Agent Teams 運用ルール

### Slack通知（必須）
タスクを1つ完了するたびに、以下のコマンドでSlack通知を送ること：
```bash
WEBHOOK=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-)  # 2026-04-17以降: .env.production
curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"text": "✅ [チームメイト名] 完了: [タスク名]\n結果: [1行サマリー]\nファイル: [変更したファイル一覧]"}'
```

エラー時:
```bash
curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"text": "❌ [チームメイト名] エラー: [タスク名]\n原因: [エラー内容]"}'
```

---

## 環境定義（2026-04-17 B案リネーム後）

| 環境 | URL | compose | env | deploy script |
|------|-----|---------|-----|---------------|
| **production** | app/api.ultra-auto-trade.com | `docker-compose.production.yml` | `.env.production` | `scripts/deploy_production.sh` |
| **staging** | staging/api-staging.ultra-auto-trade.com（Phase 4設定予定）| `docker-compose.staging.yml` | `.env.staging` | `scripts/deploy_staging.sh` |

- **コンテナ名**: production は `*-production` suffix（2026-04-24 container_name 衝突インシデント後にリネーム済み）
- **staging**: Shadow Mode専用（`AI_SHADOW_MODE=true` / `REBALANCE_SHADOW_MODE=true`）、Base Sepolia、port 3001/8001/5433
- **production**: 実資金・実トレード、Base Mainnet、port 3000/8000/5432

---

## Claude Code 最新機能活用ガイド（2026年4月 v2.1.89〜v2.1.92）

### 1. カスタムサブエージェント + @メンション呼び出し

`.claude/agents/` にMarkdownファイル（YAMLフロントマター付き）でサブエージェントを定義。
プロンプト内で `@agent-name` と入力するだけで呼び出し可能（v2.1.89〜のTypeahead対応）。
プロジェクトにコミットすればチーム共有される。

**Ultra AutoTrade 定義済みエージェント（`.claude/agents/`）:**

| ファイル | 役割 | 呼び出し例 |
|---------|------|-----------|
| `security-reviewer.md` | Aave/DeFiセキュリティレビュー | `@security-reviewer backend/app/aave/client.pyをレビューして` |
| `test-runner.md` | 7段階DoDゲート一括実行 | `@test-runner verify.shを実行して結果を報告して` |
| `i18n-checker.md` | 多言語対応チェック | `@i18n-checker frontend/の翻訳漏れをチェックして` |
| `deploy-checker.md` | デプロイ前チェックリスト実行 | `@deploy-checker stagingデプロイ前チェックを実行して` |

### 2. Named Subagents → Agent Teams 連携

`.claude/agents/` で定義したサブエージェントをAgent Teamsのチームメイトとしてそのまま利用可能。
```
spawn a teammate using the security-reviewer agent type to audit the aave module
```
- `tools` 制限とsystem promptは引き継がれる
- `skills` と `mcpServers` フロントマターはTeammate時には適用されない（通常セッション設定を使用）
- Agent Teams運用ルール（Slack通知等）は既存の「## Agent Teams 運用ルール」セクションに従うこと

### 3. PreToolUse Hooks の `defer` パーミッション（v2.1.89）

ヘッドレスセッション（`-p` モード）でツール呼び出しを一時停止し、後から `--resume` で再評価できる。

**Ultra活用:** FTパイプライン（`~/ft-automation/`）の `claude --print` 実行で、Aave関連ファイル変更等の重要操作のみ承認フローを挟む。

### 4. PermissionDenied フック（v2.1.89）

autoモードの分類器がツール実行を拒否した後に発火するフック。`{retry: true}` を返せば再試行。
Agent Teams自動実行時のフォールバック制御に有用。

### 5. MCP結果サイズ上限 500K文字（v2.1.91）

`_meta["anthropic/maxResultSizeChars"]` で50万文字まで拡大。
Asana MCP（プロジェクトGID: 1213741124336104 等）やSlack MCP（#ultra-auto-project: C0ACS09FMGC）から大量データ取得時に結果切れ問題を軽減。

### 6. `/cost` モデル別・キャッシュヒット内訳（v2.1.92）

Agent Teams使用時のモデル別トークン消費を可視化。Opus/Sonnet/Haiku のコスト配分を確認。
```
/cost
```

### 7. Write tool 差分計算 60%高速化（v2.1.92）

大きなファイル（タブや特殊文字含む）の書き込みが高速化。
workflow.py、scheduled_tasks.py 等の大ファイル編集で体感改善。

### 8. MCP_CONNECTION_NONBLOCKING=true（v2.1.89）

`-p` モードでMCP接続待ちをスキップ。MCPサーバー接続は5秒上限にバウンド。
**Ultra活用:** FTパイプラインの `claude --print --dangerously-skip-permissions` 実行の高速化。

### 9. --exclude-dynamic-system-prompt-sections（printモード）

ユーザー間でプロンプトキャッシュを共有しやすくする。FTパイプライン等のバッチ実行のコスト削減。
```bash
claude --print --exclude-dynamic-system-prompt-sections "タスク内容"
```

### 10. /powerup — インタラクティブ学習（v2.1.90）

Claude Codeの機能をアニメーションデモで学べるコマンド。新機能のキャッチアップに。
```
/powerup
```

### 11. CLAUDE_CODE_NO_FLICKER=1（v2.1.89）

alt-screen描画でフリッカーを抑制。長時間セッション・Agent Teams運用時（tmux + iTerm2）のターミナル表示安定化。

### 12. Monitor tool — バックグラウンドスクリプト監視（v2.1.91）

バックグラウンドで実行中のスクリプトからイベントをストリーム受信。
デプロイ中の `docker compose logs -f` やpytestの長時間実行をモニタリングしながら並行作業可能。

### 13. --resume セッション再開の改善（v2.1.92）

deferred tools、MCPサーバー（Asana/Slack）、カスタムエージェント使用時の `--resume` がプロンプトキャッシュミスを起こす問題が修正。長時間作業の中断・再開がスムーズに。

### 推奨 settings.json 追加設定

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    "CLAUDE_CODE_NO_FLICKER": "1",
    "MCP_CONNECTION_NONBLOCKING": "true"
  }
}
```

**注意:** 上記は `~/.claude/settings.json` またはプロジェクトの `.claude/settings.json` に追加。
既存の `cleanupPeriodDays: 99999` 設定と共存可能。

---

## 開発体制 v2（2026-03-20〜）

- **claude.ai**: PM/アーキテクト/Asana管理
- **Claude Code Agent Teams**: 並行開発の主力（tmux + iTerm2）
- **Cursor**: 廃止（Agent Teamsに統合）
- **Slack #ultra-auto-project**: 完了通知・CI・承認リクエスト
- **Asana**: タスク管理（プロジェクトGID: 1213741124336104）

## Skills & Hooks

### スキル（.claude/skills/）
- single-function-edit.md — 1回1関数ルール
- pre-commit-diff.md — コミット前diff確認

### フック
- pre-large-edit.sh (PreToolUse) — 50行超の変更を警告
- post-commit-diff.sh (PostToolUse) — コミット時にdiff表示

---

## デプロイ時の教訓

### 2026-04-01追加

**環境変数:**
- `echo 'KEY=VALUE' >> .env.staging` は前行に改行がないと連結される（例: `OCTOBOT_API_KEY=dummyNEXT_PUBLIC_BACKEND_BASE_URL=...`）。必ず `printf '\nKEY=VALUE\n' >> file` を使う
- `docker compose restart` は環境変数を再読み込みしない場合がある。確実に反映するには `docker compose up -d --no-deps --build <service>`

**DB マイグレーション:**
- 新しいSQLAlchemyカラム追加後のデプロイでは、必ずモデル定義とDBカラムを比較して `ALTER TABLE ADD COLUMN IF NOT EXISTS` を実行。確認コマンド:
  `docker exec <postgres-container> psql -U ultra -d ultra_autotrade -c "SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position;"`

**CORS と 500エラーの混同:**
- FastAPIは500エラー時にCORSヘッダーを付けない。ブラウザではCORSエラーに見えるが、実態はバックエンドの500（DB不足カラム等）。CORS問題に見えたらまずバックエンドログを確認:
  `docker logs <backend-container> 2>&1 | grep -i 'error\|undefined.*column\|does not exist'`

**Mixed Content:**
- httpsトンネル経由のフロントエンドから httpバックエンドへのリクエストはブラウザにブロックされる（Mixed Content）。トンネル使用時はフロントエンド・バックエンド両方をトンネル経由にするか、IP直接アクセス（PCのみ）を使う

**孤立Dockerコンテナ:**
- `docker compose down --remove-orphans` で消えない場合は `docker rm -f <container-name>` で強制削除してから `up -d`

### 2026-04-02追加（cloudflared + network_mode:host）

**cloudflared token方式の Ingress Rules:**
- `--token` 方式では ingress ルールは Cloudflare ダッシュボードで管理される（config.yml は無視される）
- ダッシュボードの ingress に `http://localhost:3000` / `http://localhost:8000` が設定されている場合、`network_mode: "host"` が必須

**network_mode: host 使用時の注意:**
- cloudflared コンテナが `localhost` に届くには `network_mode: "host"` が必要
- frontend/backend は `ports: "3000:3000"` / `"8000:8000"` でホストに公開されている必要がある
- `[::1]:3000`（IPv6）と `127.0.0.1:3000`（IPv4）両方で到達可能であること確認済み

**デプロイ手順（502防止）:**
- 正しい手順: `docker rm -f <container> && docker compose up -d --no-deps <service>`
- 空白時間を最小化するため stop → rm → up を連続実行する
- `restart` コマンドは旧イメージのまま再起動するため、新ビルド後には使わない
- cloudflared は `--no-deps` で単独起動（postgres 競合を避ける）

**502デバッグ手順:**
1. `docker ps -a` でコンテナが存在・起動しているか確認
2. `docker logs <frontend>` で Next.js の Ready ログを確認
3. `curl http://127.0.0.1:3000` でホスト → frontend の疎通確認
4. `docker logs <cloudflared>` で `connection refused` が出ていないか確認
5. 502 の多くはデプロイ中の空白期間が原因（数秒で自然解消）

### 2026-04-02追加（AIスケジューラー デフォルト有効化）

**スケジューラーはデフォルト有効（DISABLE_ で明示的に停止する方式）:**
- 旧方式: `ENABLE_AI_JUDGMENT_SCHEDULER=1`（デフォルト無効） → 設定漏れで無音停止していた
- 新方式: `DISABLE_AI_JUDGMENT_SCHEDULER=1`（デフォルト有効） → 設定しなければ動く
- 同様に `DISABLE_BACKGROUND_MONITORING=1`（デフォルト有効）
- 旧 `ENABLE_=1` 変数は後方互換として引き続き機能する

**スケジューラーが無効で起動した場合:**
- ERROR ログ + Slack `#ultra-auto-project` に `⚠️ AIスケジューラーが無効状態で起動しました` 通知
- `/health` が `"status": "degraded"` を返す

**デプロイ後の確認手順:**
```bash
curl https://api.ultra-auto-trade.com/health
# → {"status": "ok", "scheduler": true, "last_judgment": "...", "next_judgment": "..."}
```

**`.env.staging.example` との差分確認（デプロイ前必須）:**
```bash
# 2026-04-17以降: productionデプロイ前は .env.production との差分を確認
diff <(grep -v '^#' backend/.env.staging.example | grep '=' | cut -d= -f1 | sort) \
     <(grep -v '^#' /opt/ultra-autotrade/.env.production | grep '=' | cut -d= -f1 | sort)
```

### 2026-04-02追加（Docker Composeプロジェクト名の統一）

**docker compose は必ず同一プロジェクト名で実行すること:**
- プロジェクト名が異なると各コンテナが別ネットワークに配置され、`postgres` ホスト名が解決できず DB 接続が 500 エラーになる
- 原因: `docker compose up` 実行時のカレントディレクトリや `-p` フラグによりプロジェクト名が変わることがある
- 対策: `.env.staging` に `COMPOSE_PROJECT_NAME=ultra-autotrade-project` を設定済み（この値が自動適用される）
- 確認: `docker inspect <container> --format "{{index .Config.Labels \"com.docker.compose.project\"}}"` で全コンテナのプロジェクト名が同一か確認
- 緊急修正: プロジェクト名が異なる場合は `docker network connect <正しいnetwork> <コンテナ名>` で即座に接続可能

**DB接続500エラーのデバッグ手順:**
1. `docker logs <backend> 2>&1 | grep "could not translate host name"` — postgres名前解決失敗なら本問題
2. `docker inspect <backend> --format "{{json .NetworkSettings.Networks}}"` でネットワーク確認
3. `docker inspect <postgres> --format "{{json .NetworkSettings.Networks}}"` と比較
4. ネットワーク名が異なれば `docker network connect <postgres側network> <backend>` → `docker restart <backend>`

### 2026-04-02追加（Named Tunnel移行時の環境変数）

**NEXT_PUBLIC_BACKEND_BASE_URL の更新忘れ:**
- Named Tunnel（trycloudflare → api.ultra-auto-trade.com）移行時、`.env.staging` の `NEXT_PUBLIC_BACKEND_BASE_URL` が古い trycloudflare URL のままになっていた
- Next.js の `NEXT_PUBLIC_` 変数はビルド時に JS に埋め込まれるため、`.env` を変更しただけではダメで **フロントエンドの再ビルドが必須**

**3点セット（必ず同時に実施）:**
1. `NEXT_PUBLIC_BACKEND_BASE_URL=https://api.ultra-auto-trade.com` に更新
2. `CORS_ORIGINS` に `https://app.ultra-auto-trade.com` を追加
3. `docker compose build --no-cache frontend` でフロントエンド再ビルド → コンテナ入れ替え

**確認コマンド:**
```bash
# CORS ヘッダーが新ドメインを返しているか
curl -s -I -H 'Origin: https://app.ultra-auto-trade.com' https://api.ultra-auto-trade.com/health | grep access-control-allow-origin
# 新 URL がビルドに埋め込まれているか
docker exec <frontend> grep -rl 'api.ultra-auto-trade.com' /app/.next/static/chunks/ | wc -l
```

### 2026-04-03追加（フロントエンドAPI系環境変数 → Mixed Content）

**フロントエンドのAPI系環境変数は3つある:**
- `NEXT_PUBLIC_BACKEND_BASE_URL` — Knowledge Hub / AI 等バックエンド全般
- `NEXT_PUBLIC_API_BASE_URL` — 認証・汎用 API（`/api/` プレフィックス）
- `NEXT_PUBLIC_API_URL` — 一部コンポーネントが直接参照する API URL

**すべて `frontend/Dockerfile` の `ARG`/`ENV` と `docker-compose.production.yml` の `build.args` に定義が必要。**（2026-04-17以降: 旧 `docker-compose.staging.yml`）
1つでも欠けると Dockerfile ビルド時にフォールバック値（`http://77.42.46.155:8000` 等）がJSバンドルに埋め込まれ、
HTTPS（Named Tunnel）経由のモバイルアクセスで Mixed Content エラーになる（2026-04-03 iPhoneインシデント）。

**PCで顕在化しにくい理由:** ブラウザキャッシュ・Service Worker キャッシュが旧ビルドを返し続けるため、
モバイルや初回アクセスでのみ症状が出ることがある。

**確認・修正手順:**
```bash
# 1. Dockerfile に ARG/ENV が揃っているか確認
grep -E "NEXT_PUBLIC_API" frontend/Dockerfile

# 2. docker-compose.production.yml の build.args に揃っているか確認
grep -A 20 "build:" docker-compose.production.yml | grep "NEXT_PUBLIC_API"

# 3. 不足があれば .env.production に追加し、フロントエンド再ビルド
docker compose -f docker-compose.production.yml build --no-cache frontend
docker compose -f docker-compose.production.yml up -d --no-deps frontend

# 4. 埋め込み URL を確認（http:// が残っていないか）
docker exec <frontend> grep -r "http://77" /app/.next/static/chunks/ | wc -l
```

### 2026-04-03追加（デプロイ・運用）

- **`scripts/deploy_production.sh` を必ず使う。**（2026-04-17 B案リネーム: 旧 `deploy_staging.sh`）手打ちデプロイは孤立コンテナ（Conflict）、`--env-file` 忘れ（`NEXT_PUBLIC_*` 未焼き込み）、ビルドスキップ（古いイメージ起動）の3問題を毎回引き起こす。`deploy_production.sh` は `down --remove-orphans` → `docker rm -f` → `build --no-cache` → `up -d` → ヘルスチェック → Slack通知まで全自動。`--frontend-only` / `--backend-only` / `--no-build` オプションあり
- **`docker compose build --no-cache` だけでは不十分な場合がある。** `--no-cache` はレイヤーキャッシュをスキップするが、**古いイメージ自体は残る**。COMPOSE_PROJECT_NAMEや--env-fileが不一致だと別名のイメージが使われ続ける。`deploy_production.sh` ではビルド前に `docker rmi -f` でイメージを完全削除してから再ビルドするため、この問題は自動的に回避される。手動で修正する場合は: `docker images | grep frontend | awk '{print $3}' | xargs -r docker rmi -f && docker compose build --no-cache frontend`
- **`docker system prune -af` の後は全コンテナリビルドが必須。** イメージが削除されるため `up -d` しても起動しない。prune後は必ず `deploy_production.sh`（フルビルド）を実行
- **テストアカウント（@ultra-autotrade.com系）は DB ボリューム再作成で消える可能性がある。** 消えた場合は `bcrypt` でハッシュ生成 → `INSERT INTO users` で再作成。Registration API が無効化されている場合がある（`INITIAL_ADMIN_EMAIL` 未設定）

### 2026-04-03追加（スケジューラー・監視）

- **`/health` が 200 でもスケジューラーが死んでることがある。** `/health` はアプリ起動の確認であって、バックグラウンドジョブの健全性は保証しない。`scheduler_healthy` フィールドと `warnings` 配列で確認すること
- **`INTERNAL_API_TOKEN` が `.env.production` に未設定だとスケジューラー内部 API 呼び出しが 401 で失敗する。** AI 判定が実質走らず、テスターは「承認待ちの提案はありません」を見続ける。デプロイ後に `docker logs | grep 401` で確認
- **フロントエンドが最後の判定結果を表示し続けるため「AI が動いてる」と誤認しやすい。** HOLD (45%) が表示されていても、それが何時間も前の結果なら実際にはスケジューラーが停止している可能性がある
- **Watchdog（`scheduler_watchdog.py`）が 30 分ごとに監視。** `interval_hours * 2` を超えて未実行なら Slack 通知。`deploy_production.sh` もデプロイ後に `scheduler_healthy` を確認する

### 2026-04-03追加（Codex Review P1 安全装置バグ → 修正済み）

- **`MonitoringService` は必ずシングルトン（`get_monitoring_service()`）を使う。** 新規インスタンス化するとHF低下を検知しても緊急停止フラグが global state に伝わらない。`scheduled_tasks.py` の3ループ（`health_check_loop` / `latency_monitor_loop` / `price_change_monitor_loop`）で修正済み
- **`exchange/service.py` の `get_price_change_24h()` は `fetch_ticker().percentage` をそのまま返す（`/100` しない）。** `percentage` はすでにパーセント単位（`-15.0` = -15%）。`/100` すると変動率が 100 分の 1 に縮小され、`SAFE_MODE`（-10%）や `HARD_STOP`（-20%）が発動しなくなる。`workflow.py` 側が `/100` して `StressController` の小数形式に変換する責務を持つ

### 2026-04-08追加（フロントエンド/バックエンド分離デプロイの罠）

**`--frontend-only` デプロイは「バックエンドに新しいAPIがない」ことを意味する:**
- フロントエンドが新しいAPIエンドポイントを呼ぶコードを含む場合、`--frontend-only` でデプロイするとフロントは動くがAPI呼び出しが全て404になる
- 事例: `/admin/proposals` ページが `/api/proposals/admin/all` と `/api/proposals/admin/stats` を呼ぶが、バックエンドが古いまま → KPIカードが「Not Found」エラー
- **ルール: フロントエンドが新しいAPIエンドポイントを参照する変更では、必ずフルデプロイ（`deploy_staging.sh` 引数なし）を使う**
- `--frontend-only` は「CSSやテキスト修正など、APIに変更がない場合」のみ使用

**判断基準（デプロイ前に必ず確認）:**
```bash
git diff main --name-only | grep "^backend/"          # バックエンド変更あり → フルデプロイ
git diff main --name-only | grep "^frontend/lib/api/" # 新しいfetch関数 → フルデプロイ（対応APIが必要）
# 上記に何も出なければ --frontend-only OK
```

### 本番デプロイフロー（2026-04-05 インシデントから）

- **Hetznerは pull only。直接 git merge / git commit / nano 編集をしない。**
  正規デプロイフロー: ローカルMac → GitHub push → Hetzner `git pull origin main`。
  `22_production_release_checklist.md` 参照。Hetzner上で直接マージすると、
  Hetzner / ローカルMac / GitHub のブランチが不整合になり、復旧に時間がかかる。

- **docker-compose.production.yml の command に alembic を入れない。**
  alembicは requirements.txt に含まれておらず、実行すると exit code 127 でバックエンドが起動しない。
  DB マイグレーションは手動 `ALTER TABLE` 方式（auto-migration なし）。

- **docker-compose.production.yml を手動編集した場合:**
  1. ローカルMacで同じ変更を行う
  2. `git commit` → `git push origin main`
  3. Hetznerで `git pull origin main`
  絶対にHetzner上でコミットしない（push手段がないため行き止まりになる）。

- **NEXT_PUBLIC_* 変数は docker-compose.production.yml の build.args にも必要:**
  `.env.production` に書くだけでは不十分。`build.args` に以下の5つが必要:
  - `NEXT_PUBLIC_BACKEND_BASE_URL`
  - `NEXT_PUBLIC_API_BASE_URL`
  - `NEXT_PUBLIC_API_URL`
  - `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID`
  - `NEXT_PUBLIC_DEFAULT_CHAIN_ID`

## 2026-04-21 教訓: ドキュメント更新でも E2E 先行と3層確認を徹底

### 何が起きたか

`tester_onboarding_guide.md` v2 と関連 docs 4 ファイルを「Privy でログイン」前提でリライトし、
PR #111/#112 で main 反映。しかし実装の実態は:

- **フロント**: Privy SDK 実装済み（見た目のログイン UI は Privy）
- **バックエンド**: email/password (bcrypt) のみ。`/auth/privy-login` エンドポイント不在
- **DB**: `users` テーブルに `privy_did` カラムなし

結果: 公式ドキュメントが「Privy でログイン」と案内しているが、実際にはバックエンド JWT が
取れずダッシュボードに到達できない状態が本番に出た。Word 版配布用ドキュメントも誤情報で生成済み。

対応: Asana #1214148335864583 でバックエンド Privy 対応タスク化。
マニュアル修正版 (v3) は実装完了後に作成。

### 再発防止ルール

1. **E2E で通してからマニュアルを書く** (`docs/14_test_strategy.md` §10 に連動)
   ユーザー向け手順書 (tester_onboarding_guide / partner_tester_distribution 等) を書く・更新する場合:
   - その手順を Playwright E2E で先に実装して通す
   - E2E で「ユーザーが書かれた通りに操作して目的に到達できる」ことを確認
   - 確認できた手順のみドキュメントに反映し、確認できていない手順は main 禁止

2. **認証・権限系は3層確認** (Pre-check 原則の強化版)
   認証・権限・ログイン・ウォレット接続・ロール分岐の記述を書く前に以下を必ず CLI で全確認:
   - フロント UI 実装 (`components/` / `hooks/`)
   - バックエンドエンドポイント (`routers/` / `services/`)
   - DB スキーマ (`users` / auth 関連カラム)
   1 つでも欠けていれば「**その機能は使えない**」と判断する。

3. **ドキュメント更新にも同じ Pre-check を適用** (カテゴリ判断禁止)
   「ドキュメント更新だから安全」という判断で Pre-check を省略しない。
   ユーザーに影響が出る変更は、コード変更と同じレベルの事前確認を適用。

4. **memory からの推論拡大禁止**
   memory「Privy App ID を全環境に設定」→「Privy 認証が動いている」という拡大解釈が事故の原因。
   memory は事実記録。実装状態は都度 CLI で確認する。

---

## 環境ファイル更新ルール (2026-04-19 根本解決原則)

### 禁止事項
- sed -i 等で `.env.staging` と `.env.production` を同時更新することは禁止
  - 理由: 2026-04-18インシデントで両ファイルが完全一致状態に陥り、環境分離の意味を失った
- `.env.production` に以下の値を設定することは禁止:
  - `APP_ENV=staging`
  - `BYBIT_SANDBOX=true`
  - `AAVE_NETWORK=*sepolia*` (Phase 2メインネット移行後)

### 正しい更新手順
1. `.env.staging` を先に編集
2. 内容を確認
3. `.env.production` を別コマンドで編集 (値が本番固有なら差別化)
4. `bash scripts/check_env_separation.sh` で検証
5. コミット

### CIガード
PR作成時に `.github/workflows/env-separation-check.yml` が自動実行される。
失敗したPRはmergeできない。

### 2026-04-15追加（本番DB操作ルール）

**本番DBに対するALTER TABLE / UPDATE / DELETE等の操作手順書を生成する際、コンテナ名・DBユーザー・テーブル名を絶対に推測しない。**
手順書の冒頭に必ず「事前確認ステップ」を入れること:

```bash
# Step 1: コンテナ名を取得
docker ps | grep postgres

# Step 2: DBユーザー名・DB名を取得
docker exec <container> env | grep POSTGRES

# Step 3: テーブル一覧を取得
docker exec <container> psql -U <user> -d <db> -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
```

この3ステップの結果を確認してから、本番SQL手順を生成する。**推測で本番SQLを書くことは禁止。**

### 2026-04-17追加（本番フロントエンド操作ルール）

**フロントエンドコンテナ操作は compose ファイルと env-file を必ず明示する。**

```bash
# 本番（必須）
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate frontend

# Staging（必須）
docker compose -f docker-compose.staging.yml --env-file .env.staging-new \
  up -d --no-deps --force-recreate frontend
```

**ルール:**
- `docker-compose.production.yml + .env.production` ← 本番専用。他の compose/env の組み合わせ禁止
- `docker-compose.staging.yml + .env.staging-new` ← Staging専用
- Rolling restart は `--no-deps --force-recreate frontend`（他サービス影響なし、前回実績7秒）
- `NEXT_PUBLIC_*` 変数変更時は `build --no-cache frontend` → `up -d --no-deps` の2ステップ必須（env_file だけでは JS バンドルに焼き込まれない）
- デプロイ後は `for i in {1..30}; do curl -s -o /dev/null -w "%{http_code}\n" URL; sleep 1; done` で復旧確認

**過去インシデント（2026-04-17 Phase C）:** `docker-compose.staging.yml` を本番コンテナに誤適用 → 本番502（5分）。正しい compose ファイル指定で12秒で復旧。

---

## 参照ファイル

| ファイル | 内容 | いつ読むか |
|---------|------|----------|
| docs/13_security_design.md | セキュリティ設計詳細 | Aave/認証関連の実装時 |
| docs/14_test_strategy.md | テスト戦略詳細 | テスト設計時 |
| docs/28_staging_cors_csp_postmortem.md | CORS/CSPインシデント対策 | CORS/CSP問題発生時 |
| docs/29_tunnel_ops_guide.md | Cloudflare Tunnel運用手順 | Tunnel再起動時 |
| docs/34_phase2_protocols_guide.md | Phase 2 マルチプロトコル技術ガイド | Lido/Pendle/Optimizer/Risk Engine実装時 |
| docs/35_docker_maintenance_runbook.md | Docker 週次クリーンアップ手順 | disk 逼迫時・cron 設定変更時 |
| docs/ops/01_api_endpoints.md | 全APIエンドポイント一覧（パス・認証・curl例） | curl を書く前・エンドポイントを推測しそうなとき |
| docs/ops/02_db_tables.md | 全DBテーブル定義（カラム・型・NULL可否） | ALTER TABLE を書く前・DBスキーマを推測しそうなとき |
| docs/ops/03_deploy_procedures.md | デプロイ手順・コンテナ名・ボリューム・障害対応 | デプロイ前・Docker環境を推測しそうなとき |

---

## Docker クリーンアップ運用

- 週次自動実行: `scripts/docker_cleanup.sh`（毎週日曜 03:00 JST、Hetzner cron 登録）
- 使用コマンド: `docker builder prune -f` + `docker image prune -f`
- **禁止**: `docker system prune -af`（使用中イメージ削除リスク、CLAUDE.md 明記）
- 閾値: WARN 70% / CRITICAL 85%（Slack `#ultra-auto-project` 通知）
- 詳細: `docs/35_docker_maintenance_runbook.md`

---

## Current Phase: Phase 2 コア実装完了（dev マージ済み）

- Phase 2コア実装完了: Lido PoC / Pendle PoC / AI Optimizer（ENB）/ Risk Engine
- BaseProtocolClient インターフェース（OCP準拠）導入済み
- Optimizer ↔ Risk Engine 統合済み（動的リスクスコア取得）
- フロントエンド: 戦略選択画面（/user/strategies）+ プロトコルヘルスモニター（/admin/protocols）
- テスト: 1762 passed（dev ブランチ）
- 次: staging デプロイ → E2Eテスト → main マージ

---

## 開発フェーズ別チェックポイント（2026-04-24追加）

> 2026-04-24 インシデント対策: curl推測・Docker実態未確認・DBスキーマ差分見落とし・E2E未検証でのドキュメント公開の4パターンを防ぐ。

### Phase 1: 調査（コードを書く前に必ず実施）
- [ ] `docs/ops/01_api_endpoints.md` でエンドポイントパスを確認 — curl を推測で書かない
- [ ] `docs/ops/02_db_tables.md` でDBカラムを確認 — ALTER TABLE を推測で書かない
- [ ] Docker 環境確認: `docker ps | grep ultra-autotrade` でコンテナ名を実際に取得（`docs/ops/03_deploy_procedures.md` 参照）
- [ ] 認証・権限系は3層確認（フロント UI / バックエンドエンドポイント / DB カラム）→ 「2026-04-21 教訓」§再発防止ルール 2 参照

### Phase 2: 実装
- [ ] `./scripts/verify.sh` 全パス（ruff / mypy / pytest 80%+）→ 「Testing」セクション参照
- [ ] DBカラム追加時: モデルファイル冒頭に ALTER TABLE コメント記載（Alembic 未使用）
- [ ] 新規エンドポイント追加時: `docs/ops/01_api_endpoints.md` を更新

### Phase 3: デプロイ
- [ ] `docs/ops/03_deploy_procedures.md` の手順に従う（Hetzner で `deploy_production.sh`）
- [ ] DBカラム追加がある場合: Hetzner で先に ALTER TABLE を実行してからデプロイ
- [ ] `docs/22_production_release_checklist.md` §8（デプロイ手順）を確認

### Phase 4: 検証（デプロイ後）
- [ ] `curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool` で `scheduler_healthy: true` 確認
- [ ] `docker logs --tail=100 ultra-autotrade-backend-production 2>&1 | grep "401\|ERROR"` で 401 確認
- [ ] `docs/22_production_release_checklist.md` §9（ポストデプロイ確認）を参照

### Phase 5: ユーザー向けドキュメント・連絡
- [ ] 手順書を書く前に Playwright E2E で動作確認 → `docs/14_test_strategy.md` §10.X 参照
- [ ] E2E で通過した手順のみドキュメントに記載（未確認の手順は記載禁止）
- [ ] partner ロール画面の記述: フロント UI / バックエンドエンドポイント / DB カラムの3層確認 → 「2026-04-21 教訓」§再発防止ルール 1・2 参照

---

## 標準チェックリスト（全実装で必ず確認）

すべてのコード変更（機能追加・バグ修正・リファクタ問わず）で、実装完了前に以下を確認すること。

### UI / フロントエンド
- [ ] 全テキストが日本語（英語ハードコード禁止。ja.jsonにキーがあればそちらを使用）
- [ ] admin / partner / viewer(tester) の権限分離（role === "admin" で操作系の表示/非表示）
- [ ] ダミー/ハードコードデータがないこと（value={5.2} のような固定値禁止。データ未取得時は「データなし」表示）
- [ ] Decimal型（バックエンドからの文字列）→ Number() ラップしてから .toFixed() 等を呼ぶ
- [ ] recharts → 別ファイルに分離 + dynamic(() => import('./XxxRecharts'), { ssr: false })
- [ ] NEXT_PUBLIC_* 環境変数は build-time 埋め込み。変更時はフロントエンド再ビルド必須
- [ ] フッター/デバッグ情報に内部URL（api.ultra-auto-trade.com等）を露出しない

### バックエンド
- [ ] 新規テーブル → ALTER TABLE SQL をモデルファイル冒頭にコメントで記載（Alembic未使用）
- [ ] API レスポンスの Decimal 型は文字列で返却（JSON シリアライズ）
- [ ] 新規エンドポイント → RBAC（role チェック）を必ず実装
- [ ] fail-open 設計（外部サービス接続エラーでAPIが500にならない）

### テスト / 品質ゲート（7段階ゲート準拠）
- [ ] Gate 1-3: scripts/verify.sh 通過（pytest 80%+ / tsc --noEmit / npm run build）
- [ ] Gate 4: Playwright E2E（UI変更がある場合。baseURL=本番、ローカルはSTAGING_URL指定）
- [ ] Gate 5: 孤立コード検出（大きなリファクタ時）
- [ ] Gate 6: Codex Review（PR前に1回。/codex:review --base main --background）
- [ ] Gate 7: claude --chrome（UI変更時に手動実行。別ターミナルから起動。バックエンド配線の問題は検出できない点に注意）
- [ ] 新規機能 → pytest 新規テスト追加

### デプロイ
- [ ] dev ブランチに commit & push → PR作成 → main にマージ → Hetzner で **deploy_production.sh**
- [ ] deploy_production.sh は Hetzner 上で実行（ローカルMacではない）
- [ ] --frontend-only はバックエンドAPIに変更なしの場合のみ
- [ ] DB変更がある場合は Hetzner で事前に CREATE TABLE / ALTER TABLE 実行
