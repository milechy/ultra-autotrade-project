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
- **テストデータ投入**: INSERT/UPDATE/DELETE は staging-new コンテナ + `ultra_autotrade_staging` DB に限定。production DB へのテストデータ投入は禁止（本番DB cleanup インシデント GID 1214121103957100）

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

### 並列開発フロー v4 (2026-05-15 確立 / v3 全面置換)

#### v4 改訂の経緯

v3 (2026-05-01 確立) で 3-5 Lane 並列が「Tier B + worktree + tmux + Agent Teams」で運用可能になった。
しかし 5/15 の Phase A 起動で以下の系統的問題が露呈:

1. **claude.ai プロジェクトファイルを正本扱いした推測連鎖** (古いdocs を実体と誤認 → Lane プロンプト全部やり直し)
2. **CLI レポートの「保守的判定」を文脈確認せず鵜呑み** (Lane A-3 中断レポート過剰反応で 4 Lane 全停止指示)
3. **Phase 計画立案時の現環境制約軸の事前列挙不足** (production 凍結期限 / 山本さん UAT 状況 / Opus 障害可能性 等)
4. **Lane プロンプト発行前の「実 endpoint パス CLI 確認」抜け** (推測パスで Lane プロンプト発行)
5. **Opus 障害時の Sonnet 退避ルートが言語化されていなかった** (Opus 4.6/4.7 elevated error rate で 3 Lane 停止)

v4 はこれらの根本対策を CLAUDE.md §0 / §6 / §14 と接続して制度化する。

---

#### v4 コア原則 (v3 の鉄則 7 つに 3 つ追加 + 強化)

##### v3 から継承する鉄則 7 つ (変更なし)

1. **Hetzner pull only / ローカル merge only** (CLAUDE.md ABSOLUTE)
2. **Tier S ファイルは 1 日 1 PR まで**
3. **PR 起票前に必ず `git fetch origin && git rebase origin/main`** (古い base の指数的乖離防止)
4. **並列レーンは Tier B のみで構成**
5. **Phase A (Tier B 並列) → main マージ → Phase B (Tier S シリアル)** の段階実行
6. **stash / 未コミット変更を残さない** (delete vs modify 衝突防止)
7. **package.json / requirements.txt は誰も触らない週**を作る

##### v4 で追加する鉄則 8-10

**8. 正本確認は CLI 経由 cat 必須 (claude.ai プロジェクトファイル古い前提)**

朝プロトコルで「正本確認」を行う際、claude.ai プロジェクトファイルは memory 同等扱い (古い可能性あり)。
必ず CLI で以下を流して結果を貼り戻してから Phase 計画立案を開始する:

```bash
# 朝プロトコル正本確認テンプレート (read-only / 15分)
cd ~/projects/ultra-autotrade

# 直近 docs 変更コミット (claude.ai プロジェクトファイル sync 後の変更可視化)
git log --since="2026-04-15" --oneline -- docs/ | head -30

# 主要 docs の最終更新コミット
for f in docs/14_test_strategy.md docs/22_production_release_checklist.md \
         docs/42_production_e2e_runbook.md docs/13_security_design.md \
         docs/15_rollback_procedures.md CLAUDE.md; do
  echo "=== $f ==="
  git log -1 --format="%h %ci %s" -- "$f"
done

# 直近 postmortem の有無
ls docs/postmortems/ 2>/dev/null | tail -10

# CLAUDE.md 教訓セクション最新分
grep -nE "^### 教訓|^#### Lesson Learned|^## 20[0-9]{2}-[0-9]{2}-[0-9]{2}" CLAUDE.md | tail -20
```

CLI 結果を claude.ai に貼り戻してから Phase 計画開始。**プロジェクトファイル内検索だけで Phase 計画を立てることを禁止**。

**9. Lane プロンプト発行前に「実 endpoint」「実 import path」CLI 確認必須**

Lane プロンプトに endpoint パス / import path / クラス名を書く前に、必ず CLI で実コード grep:

```bash
# Lane プロンプト発行前テンプレート (該当 module ごと)
grep -rn "@router\." backend/app/<対象module>/  # 実 endpoint
grep -rn "class <ClassName>" backend/app/       # 実 import path
grep -rn "<module>.*include_router\|<module_router>" backend/app/main.py  # main登録
git log -1 --format="%h %ci %s" -- backend/app/<対象module>/  # 最終更新時期
```

claude.ai プロジェクトファイルの記述から推測で書かない。

**10. Opus 障害時の Sonnet 退避ルート確立**

Opus 4.6/4.7 elevated error rate / outage 時に **Phase 全停止しない**。
以下を Sonnet 4.6 で進める:

| 作業カテゴリ | Sonnet 採用可否 |
|---|---|
| read-only 調査 (真因確定 / 影響範囲評価) | ✅ |
| .claude/agents/ + .claude/skills/ 作成 | ✅ |
| docs / Asana 整理 / postmortem 起草 | ✅ |
| pytest / E2E 追加のみの PR | ✅ |
| 既存実装の Lane プロンプト Phase 1-2 (コード把握 + test 設計) | ✅ |
| Lane プロンプト Phase 5 PR 作成 (Gate 4 一部保留可) | ✅ |
| Tier S 直列 / 大規模リファクタ / セキュリティ系本体修正 | ❌ Opus 復旧待ち |
| 安全装置系の配線変更 (workflow.py / scheduled_tasks.py) | ❌ Opus 復旧待ち |
| 本体修正の最終実装 | ❌ Opus 復旧待ち |

Sonnet で Phase 1-2 + テスト書き起こし + PR (Gate 4 保留版) まで進めれば、Opus 復旧後 15-30 分で完走できる状態を作れる。

---

#### Tier 分類 (v3 から変更なし)

**Tier S: 同時編集禁止 (1日1PR)**
- backend/app/main.py
- backend/requirements.txt / pyproject.toml
- frontend/package.json / frontend/package-lock.json
- .github/workflows/ci.yml
- docker-compose.production.yml / docker-compose.staging.yml
- nginx/upstream.{production,staging}.conf
- backend/migrations/versions/*.py (新規追加)
- backend/app/database.py
- backend/app/automation/scheduled_tasks.py / monitoring_service.py / workflow.py
- CLAUDE.md

**Tier A: 同セクション編集のみ衝突**
- backend/app/schemas/*.py (別ファイルなら並列OK)
- backend/app/api/routes/*.py (別ファイルなら並列OK)
- frontend/lib/api/*.ts (関数追加場所により衝突)
- .env.production / .env.staging-new (同 KEY 編集で衝突)

**Tier B: 並列OK**
- docs/*.md (別ファイル)
- backend/tests/*.py (別ファイル)
- frontend/components/*.tsx (別ファイル)
- backend/app/protocols/*/*.py (Phase 2 PoC は完全分離)
- scripts/*.sh (新規ファイル)
- .claude/agents/*.md / .claude/skills/*.md / .claude/hooks/*.sh (新規ファイル)

---

#### Phase 計画立案 必須セクション (v4 新設)

新 Phase 計画立案時、claude.ai は以下 5 軸を CLI で事前確認 + Phase 計画書に明記:

| 制約軸 | 確認内容 | 確認ソース CLI |
|---|---|---|
| 凍結期限 | 当日 production 反映可否 | `cat docs/15_rollback_procedures.md \| grep -iE "凍結\|期限\|RAS"` |
| 山本さん状況 | production UAT 進行段階 (wallet/SUPPLY/proposals) | `docker exec postgres psql -c "SELECT ... FROM users WHERE id=11"` |
| API 障害 | Opus / Sonnet 可用性 | status.claude.com スクショ + 状態判定 |
| 期限タスク | docs/45-48 Fee 移行 / F-シリーズ / その他 due 近接 | Asana search_tasks_preview で due 7日以内 |
| 残務 | 過去 postmortem の P1 未済 | `ls docs/postmortems/ && grep -l "P1" docs/postmortems/*.md` |

5 軸すべて確認後に Phase 計画を Asana ハブとして起票。
**5 軸抜けで Phase 計画を立てた場合、その Phase は推測ベースとして扱い、起動前に再立案する**。

---

#### Lane プロンプト DoD 強化版 (v4 必須テンプレ)

各 Lane プロンプトの DoD は以下 6 セクション必須:

**A. 機能完了 (Lane 個別)**
- Lane 元 DoD 項目

**B. Gate 全通過 (CLAUDE.md §5 + §test_strategy 準拠)**
- Gate 1-3: verify.sh 全 pass
- Gate 4: Playwright E2E 新規 spec staging baseURL 全 pass
- Gate 5: 孤立コード検出 (大きなリファクタ + DeFi 安全系変更時必須)
- Gate 6: Codex Review (Aave/セキュリティ変更時は adversarial review 追加)
- Gate 7: Claude in Chrome (UI 変更 Lane / staging で CF Access ブロック時は Playwright mobile 代替明記)

**C. 教訓記録 (CLAUDE.md §0「新規教訓・ルールは正本に追記」遵守)**
- 詰まった箇所 / 推測失敗 / 環境分離違反 / memory 仮定起因失敗 を CLAUDE.md「教訓-YYYY-MM-DD」セクションに追記
- 該当なしの場合も「特記なし」と明示 (silent skip 禁止)
- §6 / §12 / §13 / §14 違反は太字で記録

**D. Asana 連携**
- PR description に該当 Asana GID + Closes 記述
- Lane 完了時 notes に PR link + Gate 結果 + 教訓サマリ
- PR main マージ後 close

**E. Slack JSON 通知 (.claude/hooks/send-lane-completion.sh / lane-json.md スキーマ)**
```json
{
  "lane": "X-N",
  "phase": "Phase X",
  "status": "completed | partial_complete | blocked | failed",
  "tier": "S | B",
  "root_cause": "(blocked/failed 時のみ)",
  "lessons_learned_count": N,
  "gate_results": {
    "1-3_verify": "pass | fail",
    "4_e2e": "X/Y pass | deferred_to_<reason>",
    "5_dead_code": "pass | n/a",
    "6_codex": "approved | minor | major",
    "7_chrome": "pass | n/a | skipped_<reason>"
  },
  "pr_url": "...",
  "next_action": "..."
}
```

**F. claude.ai 引継ぎ**
- PR URL / Gate 1-7 個別判定 / 教訓記録 CLAUDE.md 追記行 / staging 実機検証実値 / 次 Lane への blocker

---

#### CLI レポート受領時の判断プロトコル (v4 新設)

CLI から以下のような保守的判定 / 制約レポートが来た場合、claude.ai は**鵜呑みにせず文脈確認**してから採用判断:

- 「中止推奨」「全停止」「制約あり」「Lane 不可能」等の保守的判定
- 「Tier 超過」「設計欠陥」「事前計画乖離」等の構造判定

必須確認 4 軸:

| 確認軸 | 質問 |
|---|---|
| 観測軸 | 制約は curl 側か frontend 側か agent 側か backend 側か |
| 環境軸 | production / staging-new / staging旧 のどれの話か |
| 時間軸 | 今日発生 / 既解消 / 未解消 / 過去のもの |
| 影響軸 | 当該 Lane だけ / Phase 全体 / プロジェクト全体 |

4 軸確認後に判断:
- 全 Lane 影響かつ未解消 → 全停止指示
- 当該 Lane のみ → 当該 Lane 修正 + 他 Lane 継続
- 環境違いの話 → 当該 Lane 注意点として記録のみで継続
- 既解消の話 → 継続

**4 軸確認なしの「全停止」「全撤回」指示を出してはならない**。

---

#### Phase 終了処理 (v4 新設 / 各 Phase 末尾必須)

Phase 全 Lane 完了後、claude.ai セッションで以下を 1-2 時間で実行:

1. **教訓集約**: 各 Lane が CLAUDE.md「教訓-YYYY-MM-DD」に追記したものを横断レビュー → Phase 全体レベルの教訓抽出 → 「教訓-YYYY-MM-DD Phase X 総括」セクション新設
2. **Postmortem (重大インシデント時)**: docs/postmortems/YYYY-MM-DD_*.md 作成
3. **ルール改訂判断**: Phase 教訓から新規 hook / agent / skill / ルール追加が必要か判断 → 必要なら CLAUDE.md 該当セクション更新 + claude.ai プロジェクト指示文改訂起案
4. **次 Phase 起動ハブ Asana 起票**: 5 軸事前確認 + Lane 構成 + DoD 強化版 全包含
5. **山本さん共有 (必要時)**: §10 文面禁止 / 小林さん本人で送信

---

#### Agent Teams + Worktree モード (推奨、コンフリクト物理回避)

3+ ファイル並列編集時は Agent Teams worktree モードを使用:
```
Create a team with worktree isolation for these tasks:

Teammate 1: feature/branch-a で <タスクA>
Teammate 2: feature/branch-b で <タスクB>
Teammate 3: feature/branch-c で <タスクC>
Each teammate gets its own git worktree.
```

各 Teammate が独立した worktree で作業 → main マージ時のみコンフリクト可能性。

落とし穴 (2026-02 以降の実運用知見):
- **Agent Teams は file conflict detection なし** — 他 Teammate の変更を**警告なしで上書き**することがある。File ownership を初期プロンプトで**明示**必須。
- **3-5 Teammate がスイートスポット** — 6+ は coordination overhead 過多。
- **Tokens 約 7 倍** (plan mode、複数 Teammate) — Sonnet/Haiku を実装係に割り当て、Lead のみ Opus。
- **session resumption 不安定** — 中断したらタスクリスト (~/.claude/tasks/<team-name>/) を確認して手動再開。
- **Teammate が message 受け取らないことがある** — tmux 検出失敗等が原因、`tmux ls` で確認。

#### `/batch` コマンド (シンプル並列、coordination 不要時)

Teammate 間のコミュニケーション不要、独立タスクのみなら `/batch` が最適 (worktree 分離自動):
```
/batch <タスク1> | <タスク2> | <タスク3>
```

Agent Teams は teammate が share/challenge する必要があるときに使用。

---

#### tmux 5 ペイン起動コマンド (v4 標準化)

```bash
cd ~/projects/ultra-autotrade
tmux new-session -d -s phase-<X>
tmux split-window -h -t phase-<X>
tmux split-window -v -t phase-<X>:0.0
tmux split-window -v -t phase-<X>:0.1
tmux split-window -h -t phase-<X>:0.3
tmux attach -t phase-<X>

# 各ペインで claude-uata (UATa の sic.nozawa@gmail.com 切替 alias)
# Lane X-1 (Tier S) → 左上 / Opus 4.7
# Lane X-2 (Tier B) → 左中 / Opus 4.7 or Sonnet 4.6
# Lane X-3 (Tier B) → 左下 / Opus 4.7 or Sonnet 4.6
# Lane X-4 (Tier B) → 右上 / Sonnet 4.6
# Lane X-5 (Tier B) → 右下 / Sonnet 4.6

# 復帰
tmux attach -t phase-<X>
# Ctrl+b → d でデタッチ
```

---

#### claude.ai 側の責務 (PM/アーキテクト / v4 強化版)

並列開発計画時、claude.ai は質問なしで以下を実行:

1. **5 軸事前確認** (Phase 計画立案前 / CLI 経由必須)
2. **各タスクの Tier 判定** (notes の「触るファイル」から自動)
3. **並列レーン化** (3-5 本のスイートスポット / Opus と Sonnet 配分判断)
4. **CLI 用包括プロンプト 5 本一括生成** (細切れ確認禁止)
5. **Asana タスク notes に並列レーン情報追記**
6. **CLI レポート受領時の 4 軸確認** (鵜呑み禁止)
7. **Phase 終了処理 (教訓集約 + postmortem + 次 Phase ハブ起票)**

ユーザーは tmux で 5 ペイン起動するだけ。
「やっていいですか?」の細切れ確認は禁止 (5/15 で実証された浪費パターン)。
設計判断と 4 軸確認のみ claude.ai に残す。

---

## Claude Code Agent View 運用 (2026-05-12 追加)

### 概要
Claude Code の並列セッションを 1 画面で管理する CLI ダッシュボード (Research Preview)。
tmux / 複数ターミナルタブ運用を置換する。
- 公式: https://claude.com/blog/agent-view-in-claude-code
- 要件: claude-code >= v2.1.139
- 対応プラン: Pro / Max / Team / Enterprise / Claude API

### UATa での運用ルール

1. **起動方法**
   - 既存セッション内: `←` (左矢印) で Agent View に切替
   - 新規起動: ターミナルで `claude agents`
   - 背景投入: 既存セッションを `/bg` で背景化、または `claude --bg "<prompt>"` で新規背景起動
   - フル復帰: 行を選択して `Enter` または `→`、概要のみ確認は `Space` で peek

2. **Tier B 並列 (3-5 レーン) は Agent View に統一**
   - claude.ai 側で生成した複数 CLI プロンプトを `claude --bg "<prompt>"` で順次背景起動
   - 状態把握 (working / waiting / completed / failed / idle / stopped) は Agent View 一覧で確認
   - tmux / 別タブ運用は段階的に廃止

3. **Lane T (終業時 Gate 4 回収) の標準フロー**
   - Agent View で全レーンの状態を一覧
   - waiting / failed のレーンを優先処理
   - 全レーン Playwright E2E (Gate 4) 結果取得後にマージ・Asana close 判定
   - verify.sh 単独通過での close 禁止は不変 (docs/14_test_strategy.md)

4. **Tier S 直列制約は不変**
   - main.py / CLAUDE.md / docker-compose / migrations / scheduled_tasks / monitoring_service / package.json / requirements.txt / nginx upstream は Agent View でも並列化しない
   - これらは前面セッションで 1 本ずつ実行

5. **アカウント切替の前提**
   - UATa 配下では sic.nozawa@gmail.com (Max) で起動 (§15 / direnv 自動切替)
   - Agent View 起動前に `echo "${CLAUDE_CODE_OAUTH_TOKEN:0:13}"` で `sk-ant-oat01-` を確認

6. **無効化 / 制約事項**
   - Org admin は `disableAgentView` managed setting で無効化可能
   - Research Preview 期間中はキーバインドが変更される可能性あり (公式 docs を都度参照)
   - 通常の rate limit が適用される (背景レーン乱立に注意)

7. **PR babysitter / 長時間ループジョブ**
   - スケジュール系プロンプトは Agent View に next run time が表示される
   - 終業時に Lane T で一括確認

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

### スキル（`.claude/skills/<name>/SKILL.md` 形式のみ。旧 `*.md` 直置きは 2026-05-14 廃止）

| スキル名 | 自動発火条件 | 手動呼び出し | 役割 |
|---|---|---|---|
| `defi-aave-review` | `backend/app/aave/` 変更時、HF / Decimal / approve+supply / rebalance 変更時 | `/defi-aave-review` | Aave V3 コードレビュー |
| `defi-security-audit` | Aikido / Snyk 結果評価、外部監査準備、脆弱性対応、依存更新時 | `/defi-security-audit` | セキュリティ監査チェックリスト |
| `defi-transparency-report` | パートナー向けバージョン更新報告、コスト試算、機能説明資料作成時 | `/defi-transparency-report` | パートナー向け報告書生成 |
| `health` | Claude が誤動作 / ルール無視 / hooks・MCP の監査が必要なとき | `/health` | Claude Code 設定健全性監査（6層フレームワーク） |
| `ultra-deploy` | `deploy_production.sh` / `deploy_staging.sh` 呼出時、デプロイ計画時 | `/ultra-deploy` | 本番 / staging デプロイ（手打ち build 禁止徹底） |
| `ops-doc-loader` | curl / ALTER TABLE / INSERT・UPDATE・DELETE SQL / deploy script 呼出直前 | `/ops-doc-loader` | `docs/ops/01-03` 強制先読み（2026-04-24 推測インシデント対策） |

**ルール:**
- 旧 `.claude/skills/*.md` 直置き形式は廃止。新規スキルは必ず `.claude/skills/<name>/SKILL.md` ディレクトリ形式で作成
- frontmatter には必ず `name` と `description` を含める
- `description` は自動発火させたい trigger 条件を具体的に書く（例: "MUST use X. Y is FORBIDDEN."）
- CLAUDE.md 内の参照は見出し名形式で書き、行番号は使わない（CLAUDE.md 編集による参照腐敗を防ぐ）

### フック（`.claude/hooks/`）
- `pre-large-edit.sh` (PreToolUse) — 50 行超の変更を警告
- `post-commit-diff.sh` (PostToolUse) — コミット時に diff 表示
- `pre-tool-guard.sh` (PreToolUse) — Lane 越境 + `.env.production` 並列書込の物理ブロック
- `guard-env-files.sh` (PreToolUse) — 旧 env ファイル / production_operation_checklist.md の物理ブロック（R1 / R2 / R3）
- `slack_notify.py` (Notification / Stop) — Slack 完了通知
- `slack_permission.py` (PreToolUse) — Slack パーミッションリクエスト
- `post-lane-notify.sh` / `send-lane-completion.sh` — Agent Teams Lane 完了通知

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

#### Lesson Learned: 2026-05-03 手打ちdeploy違反インシデント（claude.ai生成プロンプト起因）

**事象**: PR #191 デプロイで `docker compose -p ultra-autotrade-project -f docker-compose.production.yml build --no-cache frontend` を**手打ち実行**し、`--env-file .env.production` が抜けて `NEXT_PUBLIC_PRIVY_APP_ID` が空展開でビルドされた。本番ウォレット接続ボタンが完全死亡し、本番テスター（山本さん）が詰まり、復旧に追加 4-5 時間を要した。

**真因**: claude.ai が生成したデプロイプロンプトに `docker compose ... build` 直接コマンドが含まれていた。CLAUDE.md に「`deploy_production.sh` 必須」と上記で明記されていたが、claude.ai 側でルール参照漏れ。`compose config` で確認すると `--env-file` なしでは `${NEXT_PUBLIC_PRIVY_APP_ID:-}` が空展開、ありでは正しい値が解決される、と機械的に再現できた。

**再発防止（絶対遵守）**:
1. **本番 frontend 再ビルドは `./scripts/deploy_production.sh --frontend-only` のみ。** 手打ち `docker compose ... build` を含むプロンプトを生成・実行しない／受け取った場合は拒否して `deploy_production.sh` への置き換えを要求
2. デプロイ後は必ず焼き込み確認（値が JS バンドルに入っているか grep で検証）:
   ```bash
   PRIVY_VAL=$(grep '^NEXT_PUBLIC_PRIVY_APP_ID=' /opt/ultra-autotrade/.env.production | cut -d= -f2-)
   docker exec ultra-autotrade-frontend-production sh -c \
     "grep -lE '$PRIVY_VAL' /app/.next/static/chunks/*.js | wc -l"
   # 0件なら焼き込み失敗 → 即ロールバック
   ```
3. 焼き込み確認パス後も Gate 4 実機検証（Claude in Chrome / Playwright で Privy モーダル発火確認）必須
4. `--env-file` を付け忘れる手打ちが疑われる場合は `docker compose -p ultra-autotrade-project --env-file .env.production -f docker-compose.production.yml config` で `${NEXT_PUBLIC_*}` の解決値を事前確認できる

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

### 2026-05-02追加（テストデータ投入制限 — 本番DB cleanup インシデント GID 1214121103957100 再発防止）

**テストデータの INSERT / UPDATE / DELETE は staging のみ。production DB への投入は禁止。**

#### 対象コンテナ・DB
- **許可**: `ultra-autotrade-postgres-staging` コンテナ + DB `ultra_autotrade_staging`
- **禁止**: `ultra-autotrade-postgres-production` コンテナ + DB `ultra_autotrade`（本番）

#### scripts/seed_test_data.sh 等の既存スクリプトルール
スクリプト先頭で必ず staging コンテナ名チェックを実施すること:

```bash
# スクリプト先頭に必ず追加
CONTAINER="${POSTGRES_CONTAINER:-ultra-autotrade-postgres-staging}"
if [[ "$CONTAINER" != *"staging"* ]]; then
  echo "ERROR: テストデータ投入は staging コンテナのみ許可。production への投入は禁止。"
  exit 1
fi
```

#### production への INSERT / UPDATE / DELETE 適用: 3段プロンプト必須
production DB に対してデータ変更 SQL（INSERT / UPDATE / DELETE）を実行する場合、以下の3段確認を必ず経ること:

1. **プロンプト 1**: 「これは production DB への操作である」を明示して確認を取る
2. **プロンプト 2**: 「バックアップ取得済み」を確認（`pg_dump` 実行 + 出力確認）
3. **プロンプト 3**: 「実行してよいか」最終確認（明示的な YES 入力のみ続行）

自動スクリプト（Agent Teams / CI）から production DB へのデータ変更操作は **禁止**。手動確認のみ許可。

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

### 2026-05-09追加（Cloudflare Tunnel ingress 追従漏れによる staging 502 — RCA: docs/postmortems/2026-05-09_staging_api_502.md）

**症状:** Blue/Green nginx 化（df0faf6, 2026-04-27）で staging backend を 8001 直接 bind から `nginx:127.0.0.1:8082` 経由に変更したが、Cloudflare Tunnel ingress（`api-staging.ultra-auto-trade.com`）が dashboard 上で `localhost:8001` のまま残り、約 12 日間 502 が放置された。production 側は 5/01 (a7008f5/PR #163) で同型バグが発覚済みだったが、staging への水平展開が漏れていた。検出は 5/9 09:42 JST、UAT pre-check 実行を試みた瞬間 (Cloudflare Ray ID `9f8caa253993e360`)。production 影響なし。

**鉄則 (絶対):**

1. **Cloudflare Dashboard 等 dashboard 系設定の変更は必ず「インフラ変更チェックリスト」を経由する。**
   `docs/16_infra_deployment_guide.md` (or 新規 `docs/<番号>_infra_change_checklist.md`) に定義する「インフラ変更チェックリスト」を経由しないかぎり Dashboard 直接変更は禁止。Dashboard 直接変更を恒常運用しない (Phase 3b PR-A で token → config.yml 移行と合わせて完了)。`docker-compose.production.yml` / `docker-compose.staging.yml` の `ports:` 行や nginx port を変更する PR は、PR description のテストプランに「インフラ変更チェックリスト実行済」を明記する。

2. **cloudflared は token 方式 (dashboard 管理) を避け、`config.yml` 方式に移行する。**
   `--token` 方式では ingress がリポジトリ外で管理されるため、git diff / コードレビューで port mismatch を検知できない (CLAUDE.md L546 既知制約の延長)。Phase 3b PR-A で production / staging を独立 cloudflared + 独立 `config.yml` に分離する。

3. **deploy 後の外形 healthcheck を必須化する (Gate 8)。**
   `staging-deploy.yml` / `deploy_production.sh` 両方に `curl -fsS https://api{,-staging}.ultra-auto-trade.com/health` を deploy 直後に実行し、失敗したら Slack #ultra-auto-project に通知 + 自動ロールバック判断。内部 `127.0.0.1:8082/health` の確認だけでは「外形経路（cloudflared → nginx → backend）」は検証できない。

4. **production と同型のインフラインシデントが起きたら、PR description に「staging への水平展開状況」を必須記述する。** PR #163 (a7008f5) では production だけ後方互換 binding で塞いだが staging は塞がず放置 → 同じバグを 1 週間後に踏み直した。同型バグの再発防止には「他の環境にも同型リスクがないか」を PR テストプランに明示するルールが必要。

5. **インフラ変更前チェックリスト (`docs/16` 拡張 or 新規 docs) の必須項目:**
   - [ ] backend / frontend / nginx / cloudflared / postgres の port が変わるか
   - [ ] その port を参照する箇所 (cloudflared ingress, NEXT_PUBLIC_*, healthcheck script, docs, CLAUDE.md) が全て同期されているか
   - [ ] production / staging の両方で確認したか
   - [ ] 外形 `/health` が production と staging で 200 を返すか
   - [ ] Cloudflare Dashboard 設定変更が必要な場合、PR description に明記したか

6. **CF Access で保護した API サブドメインへのクロスオリジン fetch は必ず `credentials: 'include'` が必要。**
   CF Access はブラウザセッションで `CF_Authorization` Cookie を使う。SPA (staging.ultra-auto-trade.com)
   から CF Access 保護下の API (api-staging.ultra-auto-trade.com) に cross-origin fetch する場合、
   `credentials: 'include'` がないと Cookie が送信されず毎回 302 ループになる (2026-05-09 UAT pre-check で発覚)。

   **設計ルール:**
   - CF Access Application に API サブドメインを追加する場合、対応する SPA の fetch オプションも同時に変更する (PR に両方含める)
   - `frontend/lib/api/*.ts` の全 fetch 呼び出しには原則 `credentials: 'include'` を設定する
   - CF Access Service Token (`CF-Access-Client-Id` / `CF-Access-Client-Secret` ヘッダー) は CI/curl 向け。ブラウザ SPA では Cookie + `credentials: 'include'` が正しいアプローチ
   - staging で SPA + API を同一 CF Access Application に含める場合は、Cookie のクロスドメイン送信をブラウザで事前確認してから UAT に進む
   - 参照: `docs/postmortems/2026-05-09_staging_api_502.md` §CF Access SPA cross-origin Cookie 問題

**Dashboard 管理設定の事故パターン (3 回目):**

| 日付 | 事象 | 共通点 |
|---|---|---|
| 2026-04-02 | cloudflared token 方式移行時に ingress が Cloudflare Dashboard 管理に切替 | Dashboard 設定とコードが非連動 |
| 2026-04-03 | NEXT_PUBLIC_BACKEND_BASE_URL 古い trycloudflare URL 残存 → Mixed Content | URL 設定がコードと乖離 |
| 2026-05-01 | production cloudflared が `localhost:8000` のまま Blue/Green 切替 → 502 (PR #163) | nginx port 変更 vs Dashboard ingress 非連動 |
| 2026-05-09 | staging cloudflared が `localhost:8001` のまま Blue/Green 切替 → 502 (本件、12 日遅延) | 同上、PR #163 教訓の水平展開漏れ |

**確認コマンド (デプロイ直後):**

```bash
# production
curl -fsS -o /dev/null -w "%{http_code}\n" https://api.ultra-auto-trade.com/health

# staging (CF Access Service Token 必須)
curl -fsS -o /dev/null -w "%{http_code}\n" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  https://api-staging.ultra-auto-trade.com/health
```

200 以外なら即 Slack 通知 + Phase 1 (read-only) で原因切り分け。

**Gate 8 (新規) を本 CLAUDE.md `## Testing` セクションのテスト順序に追加**:
> テスト順序: pytest(自動) → tsc --noEmit(自動) → npm run build(自動) → Playwright E2E(自動) → 孤立コード検出(PR前) → Codex Review(PR前) → Claude in Chrome(UI変更時のみ) → **post-deploy-healthcheck (deploy後 自動) ★ Gate 8**

### 2026-05-12追加（nginx upstream IP 固着 → frontend-only deploy 直後 502）

**症状:** 12:00 production で `./scripts/deploy_production.sh --frontend-only` 実行直後から、
Cloudflare 経由 `https://api.ultra-auto-trade.com/health` = 502。backend container 自体は健全
(`localhost:8010` 直撃 = 200)。15:23 `docker restart ultra-autotrade-nginx-production` で復旧
(3 時間 23 分継続)。同日 15:25 staging-new でも同型 502 を発見し、nginx error.log で
**古い IP (172.19.0.6) への "Host is unreachable" 生証拠**を取得 (backend 実 IP は 172.19.0.5)。

**真因:** `docker/nginx/nginx.conf` に **`resolver` ディレクティブ未設定**で、
upstream を `server backend-blue:8000` の hostname 直書きにしていた。nginx は起動時に
Docker embedded DNS (127.0.0.11) で 1 回だけ解決し、ワーカーメモリに永続キャッシュする。
backend container が recreate されて新 IP を取得すると、nginx は古い IP に proxy_pass し続け、
`docker restart nginx` 以外復旧手段なし。

**トリガー:** `deploy_production.sh --frontend-only` 経路 (L367-384) が
`--no-deps --force-recreate` フラグなしで `docker compose up -d frontend` を実行。
compose の依存再評価で backend が recreate された (CLAUDE.md「本番フロントエンド操作ルール」
L1009 違反)。

**鉄則 (絶対):**

1. **nginx の upstream に hostname を直書きする場合は必ず `resolver` を併設する。**
   `docker/nginx/nginx.conf` で `resolver 127.0.0.11 valid=5s ipv6=off;` を宣言し、
   `proxy_pass http://$backend;` の変数経由で動的解決させる。`upstream` block + hostname
   直書きは hostname を起動時 1 回しか解決しないため**禁止**。
   現行構成: `upstream.{production,staging}.conf` は `set $backend backend-blue:8000;`
   の単一行で、`nginx.conf` の `location /` で include される。

2. **`deploy_{production,staging}.sh --frontend-only` 経路は `--no-deps --force-recreate` 必須。**
   `docker compose up -d frontend` 単独実行は禁止。本ルール違反が今回のトリガーになった。

3. **post-deploy で外形 `/health` を必ず確認する (Gate 8 拡張)。**
   `--frontend-only` の場合でも、production は `https://api.ultra-auto-trade.com/health`
   (staging は `http://127.0.0.1:8082/health`) を 5 回連続 200 で確認し、失敗時は
   `nginx -s reload` を自動実行 + Slack 通知 (`#ultra-auto-project`)。
   `deploy_{production,staging}.sh` に組み込み済 (本セクションと対の修正)。

4. **nginx コンテナのログは Loki に取り込む** (要追加実装、別 Asana タスク)。
   現在 promtail は `/var/log/*log` のみ scrape し、nginx コンテナ内 `/dev/stderr` を
   docker logs 経由でしか保持していないため、`docker restart nginx` で過去ログが完全消失する。
   今回の本番側 RCA で error.log を取得できなかった構造的弱点。

**Dashboard 管理設定の事故パターン (4 回目、L588 表に追加):**

| 日付 | 事象 | 共通点 |
|---|---|---|
| 2026-05-12 | nginx upstream IP 固着で frontend-only deploy 直後 502 | resolver 未設定 + `--no-deps` 不在の二重バグ |

**確認コマンド (deploy 直後・nginx 関連変更時):**

```bash
# nginx の resolver 設定確認 (1 以上必須)
docker exec ultra-autotrade-nginx-production nginx -T 2>&1 | grep -c "^[[:space:]]*resolver"
# upstream.conf が変数形式になっているか
docker exec ultra-autotrade-nginx-production cat /etc/nginx/conf.d/upstream.conf
# → "set $backend backend-blue:8000;" (新形式) or "server backend-blue:8000 ...;" (旧形式、要修正)
# 外形 /health 5 回連続
for i in 1 2 3 4 5; do
  curl -sf -o /dev/null -w "[%{http_code}] " https://api.ultra-auto-trade.com/health
  sleep 2
done; echo
```

5 回全て 200 でなければ即 Slack 通知 + Phase 1 (read-only) で原因切り分け。

**参照:** `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md`

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
| docs/postmortems/2026-05-09_staging_api_502.md | staging cloudflared ingress port mismatch 12日遅延検出 RCA | port変更PR・cloudflared変更時 |
| docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md | nginx upstream IP 固着 (resolver 未設定 + `--no-deps` 不在) RCA | nginx config・deploy script変更時 |

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

## Fee Model v10 (F-1〜F-16 進行中、2026-04-25〜)

詳細は `docs/45_fee_model_v10_migration_plan.md` 参照。F-2/F-3 で確定したルール:

### Tier (投資ティア、F-2)
- 内部値: `LOWER` / `MIDDLE` / `UPPER` (v10 三層、JPY 境界 100 万 / 1000 万)
- v9 互換値 `GENERAL` は deprecated として残置 (F-13 で削除)
- 日本語ラベル辞書: `app.auth.models.TIER_JP_LABELS`
- 判定関数: `app.users.tier_service.determine_tier_jpy(deposit_jpy)`
- 既存 6 ユーザーの再判定 SQL: `docs/46_users_tier_migration_plan.md` (F-16 で実行)

### RiskMode (リスクモード、F-3)
- 内部値: `conservative` / `balanced` / `aggressive` (v9 から **完全維持、リネーム禁止**)
  - Aave MDD / Optimizer Allocator / Aave Risk Profile が文字列リテラル直参照
- 表示: `app.auth.models.RISK_MODE_JP_LABELS` (ローリスク / ミドルリスク / ハイリスク) で日本語化
- Phase 1 制限: `PHASE_1_ALLOWED_RISK_MODES = {CONSERVATIVE}`、API 層 (`PUT /auth/risk-mode`) で 403
- API レスポンス: UserResponse に `risk_mode_label` (computed_field) 追加、フロントは英語値→日本語化辞書を持たない
- 関連 endpoint: `GET /auth/risk-modes` (新規、全モード一覧 + Phase + 許可状態)
- NULL 4 ユーザーの 'conservative' 物理 UPDATE: `docs/47_users_risk_mode_migration_plan.md` (F-16 で実行)

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

---

## 2026-05-13追加（5/12 終日 UAT ブロッカー 教訓 20 策 — RCA: docs/postmortems/2026-05-12_uat_blocker_full_day_failure.md）

### セクション 1: 朝プロトコル拡張 (策 1-2)

**策 1: production 業務動作サニティチェック（朝プロトコル冒頭に必須）**

`scheduler_healthy: true` の確認だけでは AI 判定が業務として動いているかを確認できない。
毎朝以下 SQL を実行して業務 KPI を確認すること:

```sql
-- AI 判定 24h 件数
SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';
-- 提案 24h 件数
SELECT COUNT(*), MAX(created_at) FROM proposals WHERE created_at > NOW() - INTERVAL '24 hours';
-- バックエンドエラー件数 (docker logs で確認)
-- docker logs --tail=200 ultra-autotrade-backend-production 2>&1 | grep -c "ERROR"
-- knowledge_sources スキーマ確認
SELECT COUNT(*) FROM knowledge_sources WHERE status = 'pending';
```

**策 2: Gate 8 標準 SQL — 業務動作 KPI を朝プロトコルに組み込む**

`/health` の `scheduler_healthy: true` + 上記 SQL 確認を合わせて「業務動作 Gate 8」とする。
Gate 8 が通らない場合は当日の AI 判定結果は信頼できないと判断し、原因調査を優先する。

### セクション 2: 判定癖修正 (策 3-5)

**策 3: エラー判定 3 軸ルール（即「既知/先送り」禁止）**

エラーを「既知」「先送り」と判断するには以下 3 軸を全て確認すること:
1. **影響範囲**: 山本さんの操作フローに影響が出ているか
2. **発生頻度**: 過去 24h で何件発生しているか (ゼロなら既知判断を慎重に)
3. **修正コスト**: 30 分以内に対応できるか

1 軸でも確認できていない状態で「既知/先送り」と判断することを禁止する。

**策 4: `scheduler_healthy=true` の意味の明文化**

`/health` レスポンスの `scheduler_healthy: true` は「スケジューラープロセスが生存している」
ことのみを示す。以下は**保証しない**:
- AI 判定が実際に実行されて BUY/SELL 提案が生成されていること
- 通知関数が呼ばれていること
- 業務ループが正常に完了していること

業務動作の確認には策 1 の SQL を使う。

**策 5: 影響度低判定チェックリスト（4 項目全 YES のみ「影響度低」と判定可）**

以下 4 項目が全て YES の場合のみ「影響度低」と判断可:
- [ ] 山本さんの操作フローに直接関係しないか
- [ ] 本番 API が正常に 200 を返しているか
- [ ] 24h エラーログが増加していないか
- [ ] 業務 KPI (提案/判定件数) が前日比で大きく下がっていないか

1 項目でも NO なら「影響度高」として即対応する。

### セクション 3: コマンド精度 (策 6-7)

**策 6: curl HTTP method を必ず明示する**

`curl -sI URL` は HEAD リクエストを送る。POST エンドポイントに `-sI` を使うと 405 が返り、
「エンドポイントが壊れている」と誤認する。

```bash
# 誤: HEAD リクエストになる → POST エンドポイントで 405
curl -sI https://api.ultra-auto-trade.com/health

# 正: GET で確認
curl -sf https://api.ultra-auto-trade.com/health
# 正: POST で確認
curl -sf -X POST -H 'Content-Type: application/json' \
  -d '{"key":"value"}' https://api.ultra-auto-trade.com/endpoint
```

**策 7: SSH heredoc 内の SQL に INTERVAL を使う場合は heredoc 必須**

```bash
# 誤: single quote 内で $() が展開されず意図しない SQL になる
ssh ultra@77.42.46.155 'psql -U ultra -d ultra_autotrade -c "SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '"'"'24 hours'"'"'"'

# 正: heredoc で SQL を渡す
ssh ultra@77.42.46.155 <<'ENDSSH'
psql -U ultra -d ultra_autotrade -c "SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours'"
ENDSSH
```

### セクション 4: テーブル・コード調査精度 (策 8-11)

**策 8: DB テーブル名から機能を推測しない**

- `ai_feedbacks` テーブル ≠ AI 判定本体（フィードバック履歴）
- `ai_decisions` テーブル = AI 判定実体（BUY/SELL/HOLD 決定）
- `proposals` テーブル = 承認待ち提案（ai_decisions の後段）

テーブル名だけで機能を推測せず、`docs/ops/02_db_tables.md` でスキーマを確認する。

**策 9: テストユーザー dry run 前に credentials アクセス事前 hash 確認**

テストユーザーでのログイン操作前に、対象ユーザーの password hash が DB に存在することを確認する:

```sql
SELECT id, email, hashed_password IS NOT NULL AS has_pwd, role
FROM users WHERE email = 'test@example.com';
```

hash が NULL のままテストするとログインが永遠に失敗し、「バグ」と誤認する。

**策 10: 朝起動時に ops_01/05 正本を通読**

毎朝作業開始前に以下を通読する:
- `docs/ops/01_api_endpoints.md` — 最新エンドポイント一覧
- `docs/ops/05_monitoring_runbook.md` (または最新 ops ドキュメント) — 監視・アラート手順

curl を書く前・ALTER TABLE を書く前に、まず ops ドキュメントを確認する習慣を徹底する。

**策 11: CLI 委譲ルール拡張（コード調査・grep も Claude Code に委譲）**

claude.ai セッションでコード調査・grep・ファイル探索が必要な場合、claude.ai が直接推測せず
Claude Code CLI に委譲する。claude.ai の「推測」が実装と乖離してインシデントを招く主要因。

委譲すべき操作:
- `grep -r "function_name" backend/` — 関数の参照箇所
- `cat backend/app/XXX/service.py` — 実装の確認
- `git log --oneline` — 最近の変更履歴

### セクション 5: production deploy + nginx (策 12-14)

**策 12: deploy 後は Cloudflare 経由 /health を Gate 5 として必須確認**

`deploy_production.sh` の内部 `127.0.0.1:8010/health` 確認だけでは不十分。
必ず Cloudflare 経由の外形 URL で確認する:

```bash
# 5 回連続 200 を確認 (Gate 8 外形確認)
for i in 1 2 3 4 5; do
  curl -sf -o /dev/null -w "[%{http_code}] " https://api.ultra-auto-trade.com/health
  sleep 2
done; echo
```

5 回全て 200 でなければ即 Slack 通知 + nginx reload を試みる。

**策 13: deploy script の「OK」出力を信用しない**

`deploy_production.sh` が「✅ deploy 完了」を出力しても、内部の healthcheck が
`127.0.0.1` ループバック経由のため、Cloudflare → nginx → backend の外形経路は
検証していない。策 12 の外形 curl を必ず追加実行する。

**策 14: nginx 502 が出たら frontend-only deploy とペアで疑う**

nginx 502 発生時の最初の確認:
1. 直近に `--frontend-only` deploy を実施したか
2. `docker ps` で backend container の `CREATED` 時刻が変わっているか (recreate の証拠)
3. `docker exec nginx nginx -T 2>&1 | grep resolver` で resolver 設定を確認

resolver 未設定かつ backend recreate 後なら、`docker restart nginx` で即時復旧できる。
恒久対策は `resolver 127.0.0.11 valid=5s;` 設定 + `proxy_pass http://$backend;` 変数化。

### セクション 6: 表示データ実体確認 (策 15-17)

**策 15: dummy/seed データの識別方法**

本番データとダミーデータを区別する 3 指標:
1. **時刻分散性**: 全レコードが同日同時刻 → seed データの可能性が高い
2. **ユーザー差異性**: 全レコードが同一ユーザー → seed データの可能性が高い
3. **24h 生成有無**: `WHERE created_at > NOW() - INTERVAL '24 hours'` で 0 件 → AI が動いていないか seed のみ

**策 16: production 表示データの実体は SQL で確認**

フロントエンドの表示値を見て「データが入っている」と判断しない。
フロントエンドはキャッシュや seed データを表示することがある。
必ず production DB に直接 SQL で確認する:

```bash
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c \
  "SELECT COUNT(*), MAX(created_at) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';"
```

**策 17: 孤立コード再発防止 — CI 週次 detect_orphan_functions.sh**

孤立コードは「大きなリファクタ時」だけでなく並列開発後も発生する。
以下を実施する:
- 毎週月曜の CI で `scripts/detect_orphan_functions.sh`（または同等の grep スクリプト）を自動実行
- `backend/app/notifications/service.py` の全 public 関数を特に重点チェック
- 孤立が検出された場合は P1 として当日中に配線修正または削除

### セクション 7: PR と実機の乖離 (策 18-20)

**策 18: wallet flow / 認証 flow / DB 書き込み伴う action は viem 実署名 E2E 必須**

component 単独 commit + route-mock テストでは「実際に signature が生成され、backend に
送られ、DB に書き込まれる」フローを検証できない。

以下のフローは必ず viem 実署名 E2E テストを追加すること:
- `POST /auth/wallet/link` — nonce 取得 → viem signMessage → POST の 3 ステップ
- `POST /auth/login` — email/password → JWT 取得 → ダッシュボードへのリダイレクト
- `POST /aave/rebalance` — health factor 確認 → deposit/withdraw

**策 19: Codex APPROVED + Playwright pass でも実機 (実ブラウザ) 確認は必須**

Playwright の動作環境 (ヘッドレス Chrome、拡張なし、自動 Content-Type 付与) と
実ユーザーの動作環境 (拡張入り Chrome、手動操作、browser の fetch 挙動) は異なる。

特に以下は実機確認を必須とする:
- `fetch()` の `Content-Type` / `body` が正しく設定されているか
- wallet 拡張 (MetaMask 等) の popup が正しく発火するか
- CF Access の Cookie が正しく送られているか (`credentials: 'include'` の有無)

**策 20: frontend container restart は image rebuild ではない**

```bash
# 誤: イメージが古いまま旧コードが起動する
docker compose up -d --force-recreate frontend

# 正: 必ず build してから recreate する
docker compose -f docker-compose.production.yml --env-file .env.production \
  build --no-cache frontend

# ビルド完了の確認: image hash が変化したか確認
docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep frontend

# その後 recreate
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate frontend
```

`--force-recreate` はコンテナの再生成のみ。イメージの再ビルドは `build --no-cache` が必要。
image hash が変化していなければ rebuild されていないため、旧コードが動き続ける。

**参照**: `docs/postmortems/2026-05-12_uat_blocker_full_day_failure.md`

---

## 2026-05-15追加（Phase A PoC staging endpoint 未実装パターン教訓）

### 教訓-2026-05-15: PoC 段階の schemas-only 定義と staging 実機検証の関係

**事象**: Lane A-4 (AI Optimizer staging E2E) で、`OptimizerRequest` / `OptimizerResponse` が
`app/ai/optimizer/schemas.py` に定義されているにも関わらず、対応する router が存在せず
`/api/optimizer/recommend` エンドポイントが staging に存在しない状態でタスクが完了指定されそうになった。
また `app/protocols/risk/router.py` の `/api/protocols/health` は main.py に登録済みだが、
`DummyClient` を使用しているため staging で `500: DummyClient cannot be used in staging environment` が返る。

**真因**: Phase 2 PoC では「schemas 先行定義 → router は実装フェーズで追加」という開発順序を取る。
CLAUDE.md の「Phase 4: staging 実機検証」フローに「PoC 段階でエンドポイントが未実装の場合の代替」が明記されていなかった。

**再発防止ルール**:

1. **staging 実機検証の前にエンドポイント存在確認を必須化**
   ```bash
   # curl の前に必ずエンドポイント存在を確認
   ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
     "curl -sf http://localhost:8082/openapi.json | python3 -c \"import sys,json; paths=json.load(sys.stdin)['paths']; print('\\n'.join(paths.keys()))\"" \
     | grep -E "optimizer|recommend"
   # 0件なら → PoC仕様 → pytest E2E で代替、その旨を DoD に明記
   ```

2. **PoC 段階の schemas-only 定義は「孤立コード検出」対象**
   router が存在しない `OptimizerRequest` / `OptimizerResponse` は P1 孤立として記録する。
   Lane 完了時の孤立コード検出でこれらを捕捉し、`[P1: router 実装待ち]` とラベリングして別タスク化する。

3. **DummyClient を使うプロトコルの staging 実機検証は skip 明示**
   `DummyClient` / `DummyLidoClient` / `DummyPendleClient` を使用するエンドポイントは
   staging で必ず 500 になる。pytest mock E2E で代替し、
   DoD に `Gate 4: staging スキップ (DummyClient - PoC仕様)` と明記すること。

4. **孤立クラスの P0/P1 分類基準**
   | 分類 | 対象 | 対応期限 |
   |---|---|---|
   | P0 | 安全装置・緊急停止・避難系 (AutoEvacuator, CompoundRiskAssessor 等) | 当日中 |
   | P1 | API スキーマ・router 待ち定義 (OptimizerRequest 等) | 次スプリント |
   | P2 | ユーティリティ・将来機能 | バックログ |
