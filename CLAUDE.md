# Claude Code 開発ガイド
> 教訓・デプロイ知見・チェックリストは [`CLAUDE.lessons.md`](CLAUDE.lessons.md) に分割済み
> 読み込み: `cat CLAUDE.lessons.md`


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

