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
- テスト順序: pytest(自動) → Playwright E2E(自動) → 孤立コード検出(PR前) → Codex Review(PR前) → Claude in Chrome(UI変更時) → 手動UIテスト(最後)

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
WEBHOOK=$(grep SLACK_WEBHOOK_URL .env.staging | cut -d= -f2-)
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

---

## 参照ファイル

| ファイル | 内容 | いつ読むか |
|---------|------|----------|
| docs/13_security_design.md | セキュリティ設計詳細 | Aave/認証関連の実装時 |
| docs/14_test_strategy.md | テスト戦略詳細 | テスト設計時 |
| docs/28_staging_cors_csp_postmortem.md | CORS/CSPインシデント対策 | CORS/CSP問題発生時 |
| docs/29_tunnel_ops_guide.md | Cloudflare Tunnel運用手順 | Tunnel再起動時 |
| docs/34_phase2_protocols_guide.md | Phase 2 マルチプロトコル技術ガイド | Lido/Pendle/Optimizer/Risk Engine実装時 |

---

## Current Phase: Phase 2 コア実装完了（dev マージ済み）

- Phase 2コア実装完了: Lido PoC / Pendle PoC / AI Optimizer（ENB）/ Risk Engine
- BaseProtocolClient インターフェース（OCP準拠）導入済み
- Optimizer ↔ Risk Engine 統合済み（動的リスクスコア取得）
- フロントエンド: 戦略選択画面（/user/strategies）+ プロトコルヘルスモニター（/admin/protocols）
- テスト: 1762 passed（dev ブランチ）
- 次: staging デプロイ → E2Eテスト → main マージ
