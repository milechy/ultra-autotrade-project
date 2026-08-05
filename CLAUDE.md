# Claude Code 開発ガイド

## プロジェクト: Ultra AutoTrade

Based on:
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)

> **2026-05-21 refactor (本 file の構成)**: `CLAUDE.md` は core のみを保持し、教訓は `CLAUDE.lessons.md`、ops 詳細は `docs/ops/` 配下に分離されている。
> SessionStart Hook (`.claude/hooks/load-claude-lessons.sh`) が `CLAUDE.lessons.md` を auto-Read する。
> 経緯: `docs/internal/claude_md_split_proposal.md` v2、TODO 1-10 の決定事項は本 PR description 参照。
>
> **「v4 指示文」と「CLAUDE.md」の関係**: 本 repo は 2 文書体制で運用。
> - **CLAUDE.md** (本ファイル) — Claude Code CLI / dev VPS 向けの正本。リポジトリに commit。
> - **v4 指示文** (claude.ai プロジェクト指示文、`/mnt/project/` 配下、browser 側) — claude.ai (PM/アーキテクト) 向けの正本。
> 文中の `§9 朝プロトコル` のように prefix 無しの §-number は **本 CLAUDE.md 内**を指す。
> `v4 指示文 §0 / §3 / §5 / §6 / §10 / §12 / §13 / §14` のように prefix 付きは **claude.ai 側指示文**を指す。
> 両者は意図的に分離 (二重管理回避) し、相互参照のみ行う。

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

### プロジェクト設定
**ファイル:** `.claude/settings.json` (リポジトリ committed)
- `hooks.SessionStart` — `CLAUDE.lessons.md` auto-Read (`.claude/hooks/load-claude-lessons.sh`)
- `hooks.PreToolUse` / `PostToolUse` / `Stop` — Lane / heartbeat / Slack 通知系

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

### 一括検証（コミット前に必ず実行）
```bash
./scripts/verify.sh
```

## Core Principles
1. **Simplicity First** — 最小限の変更で目的を達成。過剰な抽象化不要
2. **No Laziness** — テスト・lint・フォーマットを省略しない
3. **Minimal Impact** — 既存コードへの影響を最小化

## Frontend ルール
- package.json変更時は `npm install --legacy-peer-deps` → package-lock.json も一緒にコミット
- rechartsは必ず `dynamic(() => import('./XxxRecharts'), { ssr: false })` で読み込む（SSRクラッシュ防止）
- `grep -E "ignoreBuildErrors|ignoreDuringBuilds" frontend/next.config.js` でOOMワークアラウンド確認
- Playwright E2E: デフォルトは本番URL直打ち。ローカルテスト時は `STAGING_URL=http://localhost:3000` + `npm run dev` 必須。production VPS(5.223.88.14)直IPは127.0.0.1バインドにより接続拒否される（正常）

### Next.js App Router route group と URL の対応 (E2E spec 必須確認)

**route group `(xxx)` はディレクトリ名が URL に含まれない。** E2E で `page.goto()` する URL は
実ファイルパスではなくブラウザからアクセスできる URL に合わせること。

| ファイルパス | URL | よくある誤り |
|---|---|---|
| `app/(admin)/protocols/page.tsx` | `/protocols` | ❌ `/admin/protocols` |
| `app/(user)/strategies/page.tsx` | `/strategies` | ❌ `/user/strategies` |
| `app/(partner)/partner/dashboard/page.tsx` | `/partner/dashboard` | ✅ (subfolder `partner/` が入る) |
| `app/user/approve/page.tsx` (通常フォルダ) | `/user/approve` | ✅ (route group でない) |

**確認方法:** E2E spec に URL を書く前に、必ず `AppShell.tsx` / `BottomNav.tsx` 等のナビリンクで
使われている `href` 値を grep して確認すること:

```bash
grep -r "href=" frontend/src/components/ | grep -E "protocols|strategies" | head -10
```

**背景:** 2026-05-19 PR #307 で `pendle-staging-poc.spec.ts` / `phase2-admin-protocols.spec.ts` /
`phase2-iphone-mobile.spec.ts` の 3 ファイルに `/admin/protocols` / `/user/strategies` という
誤 URL が混入。`< 500` チェックのため 404 でもテストが通過し、長期間気づかれなかった。

---

## ops 詳細リファレンス (docs/ 配下に分離)

> 2026-05-21 refactor で `CLAUDE.md` から分離。詳細は各ファイル参照。

| トピック | 参照先 | いつ読むか |
|---|---|---|
| API エンドポイント一覧 | `docs/ops/01_api_endpoints.md` | curl を書く前 / エンドポイント追加時 |
| DB テーブル定義 | `docs/ops/02_db_tables.md` | ALTER TABLE を書く前 / スキーマ確認 |
| デプロイ手順 | `docs/ops/03_deploy_procedures.md` | デプロイ前 / コンテナ操作前 |
| バックエンドモジュールマップ (旧 Directory Structure) | `docs/ops/05_backend_modules_map.md` | router 追加 / main.py 編集前 |
| マルチLLM 開発ワークフロー | `docs/ops/multillm_workflow.md` | Opus/Sonnet/Haiku ロール選択時 |
| Testing 戦略 | `docs/14_test_strategy.md` | テスト設計時 / Gate 1-8 参照時 |
| Codex Plugin 運用 | `docs/ops/codex_plugin.md` | `/codex:review` 実行時 |
| 孤立コード検出 | `docs/ops/orphan_detection.md` | PR 作成前 (新モジュール時必須) |
| Claude Code Agent View 運用 | `docs/ops/agent_view.md` | 並列レーン起動時 |
| Claude Code 最新機能活用ガイド | `docs/ops/claude_code_features.md` | サブエージェント / Hook / MCP 設定時 |
| オンコールポリシー | `docs/ops/oncall_policy.md` | アラート受信時 / 当番判断 |
| Fee Model v10 (F-1〜F-16) | `docs/ops/fee_model_v10.md` | Tier / RiskMode 関連実装時 |
| docker コマンドチートシート | `docs/ops/docker_command_cheatsheet.md` | docker 操作前 (落とし穴 7 項目) |
| 本番運用 checklist | `docs/ops/production_operation_checklist.md` | 本番 SQL / deploy 直前 |
| staging 復旧 v4 prompt | `docs/ops/staging_recovery_v4_prompt.md` | staging-new 消滅時 |
| Web Push 本番有効化 | `docs/ops/web_push_production_activation_runbook.md` | VAPID 鍵設定 / 実機到達確認 (B-1/B-7) 実施時 |
| 24h 自走起動 checklist | `docs/ops/uata_24h_autonomous_startup_checklist.md` | 夜間自走前 |

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

v4 はこれらの根本対策を **v4 指示文 §0 / §6 / §14** (claude.ai プロジェクト指示文、`/mnt/project/` 配下) と接続して制度化する。

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

> **鉄則8 チェック項目に追加 (2026-05-20)**:  
> 本番 VPS 向け手順書・Lane プロンプトを書く前に **VPS パス構造を確認する**。  
> dev VPS は `/opt/ultra-autotrade/main/` が repo root。本番 VPS は `/opt/ultra-autotrade/` が repo root（`main/` サブディレクトリなし）。  
> SSH ログイン後に `pwd && ls` を実行してから手順を進める。推測で `/main/` を含む絶対パスを書かない。

```bash
# 朝プロトコル正本確認テンプレート (read-only / 15分)
cd ~/projects/ultra-autotrade

# 直近 docs 変更コミット (claude.ai プロジェクトファイル sync 後の変更可視化)
git log --since="2026-04-15" --oneline -- docs/ | head -30

# 主要 docs の最終更新コミット
for f in docs/14_test_strategy.md docs/22_production_release_checklist.md \
         docs/42_production_e2e_runbook.md docs/13_security_design.md \
         docs/15_rollback_procedures.md CLAUDE.md CLAUDE.lessons.md; do
  echo "=== $f ==="
  git log -1 --format="%h %ci %s" -- "$f"
done

# 直近 postmortem の有無
ls docs/postmortems/ 2>/dev/null | tail -10

# CLAUDE.md / CLAUDE.lessons.md 教訓セクション最新分
grep -nE "^## 20[0-9]{2}-[0-9]{2}-[0-9]{2}" CLAUDE.lessons.md | tail -20
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
- CLAUDE.md / CLAUDE.lessons.md

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

**B. Gate 全通過 (v4 指示文 §5 + `docs/14_test_strategy.md` 準拠)**
- Gate 1-3: verify.sh 全 pass
- Gate 4: Playwright E2E 新規 spec staging baseURL 全 pass
- Gate 5: 孤立コード検出 (大きなリファクタ + DeFi 安全系変更時必須)
- Gate 6: Codex Review (Aave/セキュリティ変更時は adversarial review 追加)
- Gate 7: Claude in Chrome (UI 変更 Lane / staging で CF Access ブロック時は Playwright mobile 代替明記)

**C. 教訓記録 (v4 指示文 §0「新規教訓・ルールは正本に追記」遵守)**
- 詰まった箇所 / 推測失敗 / 環境分離違反 / memory 仮定起因失敗 を `CLAUDE.lessons.md`「YYYY-MM-DD」セクションに追記
- 該当なしの場合も「特記なし」と明示 (silent skip 禁止)
- v4 指示文 §6 / §12 / §13 / §14 違反は太字で記録

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
- PR URL / Gate 1-7 個別判定 / 教訓記録 `CLAUDE.lessons.md` 追記行 / staging 実機検証実値 / 次 Lane への blocker

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

1. **教訓集約**: 各 Lane が `CLAUDE.lessons.md`「YYYY-MM-DD」に追記したものを横断レビュー → Phase 全体レベルの教訓抽出 → 「YYYY-MM-DD Phase X 総括」セクション新設
2. **Postmortem (重大インシデント時)**: docs/postmortems/YYYY-MM-DD_*.md 作成
3. **ルール改訂判断**: Phase 教訓から新規 hook / agent / skill / ルール追加が必要か判断 → 必要なら `CLAUDE.md` 該当セクション更新 + claude.ai プロジェクト指示文改訂起案
4. **次 Phase 起動ハブ Asana 起票**: 5 軸事前確認 + Lane 構成 + DoD 強化版 全包含
5. **山本さん共有 (必要時)**: v4 指示文 §10 文面禁止 / 小林さん本人で送信

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

## 環境定義（2026-04-17 B案リネーム後）

| 環境 | URL | compose | env | deploy script |
|------|-----|---------|-----|---------------|
| **production** | app/api.ultra-auto-trade.com | `docker-compose.production.yml` | `.env.production` | `scripts/deploy_production.sh` |
| **staging** | staging/api-staging.ultra-auto-trade.com（Phase 4設定予定）| `docker-compose.staging.yml` | `.env.staging` | `scripts/deploy_staging.sh` |
| **staging-v4** | https://staging-v4.ultra-auto-trade.com | `docker-compose.staging-v4.yml` | `.env.staging-v4` | — |

- **コンテナ名**: production は `*-production` suffix（2026-04-24 container_name 衝突インシデント後にリネーム済み）
- **staging**: Shadow Mode専用（`AI_SHADOW_MODE=true` / `REBALANCE_SHADOW_MODE=true`）、Base Sepolia、port 3001/8082(nginx経由)/5433（注: 旧8001は廃止。`curl http://127.0.0.1:8082/health` で確認）。`docker-compose.staging.yml` は `profiles:` 指定なし = `up -d` 既定で **7 サービス**（postgres / backend-blue / backend-green / nginx / frontend / loki / promtail）が全起動。nginx upstream は `docker/nginx/upstream.staging.conf` で `backend-blue:8000` に固定。旧記述「5コンテナ / green のみ」は B案リネーム期の名残であり現 compose と矛盾（2026-05-22 訂正）。
- **staging-v4** (2026-06-17 新設): v4 開発用 staging、v3 staging-new とは独立。frontend=3002 / backend=8030 / nginx=8083 / postgres=5434 (DB=ultra_autotrade_staging_v4) / `COMPOSE_PROJECT_NAME=ultra-autotrade-staging-v4`
- **production**: 実資金・実トレード、Base Mainnet、port 3000/8000(nginx host port)/8080(nginx container)/5432（8010=backend-blue直ポート、8011=backend-green直ポート、nginx経由=8000→8080→active backend）

---

## 開発環境 v4 (2026-07-02〜、ASSIST ONE 3VPS分離)

> 2026-07-02 に本番 Hetzner アカウントを別アカウント(ASSIST ONE)へ移行し、
> production / staging(+staging-v4) / dev を**3台の物理的に別VPS**に完全分離。
> 旧構成(開発環境v3、2026-05-18〜)は staging が production と同居していたが、
> 移行後は同居していない。旧VPS(77.42.46.155)は保険期間(3〜7日)保持後に解約予定。
> 詳細手順は `docs/ops/host_migration_runbook.md` を参照。

### 3 層運用 — ホスト / 作業ディレクトリ

| 層 | ホスト | IP | OS user | 作業ディレクトリ | 用途 |
|----|--------|----|---------|------------------|------|
| **dev** | ASSIST ONE dev VPS（Helsinki） | `95.216.167.198` | `root` | `/opt/ultra-autotrade/main`（main worktree）+ `/opt/ultra-autotrade-worktrees/<branch>` | Claude Code CLI による実装・並列レーン開発。実資金・実トレードなし。**2026-07-03構築完了**（repo clone / backend venv / frontend node_modules / Docker+Compose / Claude Code CLI 導入済み。HEAD は origin/main 追従） |
| **staging** | ASSIST ONE staging VPS（Falkenstein） | `188.34.167.142` | `root` | `/opt/ultra-autotrade`（staging compose stack） | Shadow Mode 専用（Base Sepolia）、port 3001/8082(nginx)/5433（旧8001廃止） |
| **staging-v4** | ASSIST ONE staging VPS（Falkenstein、staging と同居） | `188.34.167.142` | `root` | `/opt/ultra-autotrade`（staging-v4 compose stack） | v4 開発用 staging（Base Sepolia）、port 3002/8083(nginx)/8030(backend)/5434。v3 staging-new と独立 |
| **production** | ASSIST ONE production VPS（Singapore、専用 Hetzner Project で分離） | `5.223.88.14` | `root` | `/opt/ultra-autotrade`（production compose stack） | 実資金・実トレード（Base Mainnet）、port 3000/8000/5432 |

> **[CRITICAL] パス構造差 — 推測禁止**
>
> | VPS | git repo root | `backend/` の絶対パス |
> |---|---|---|
> | **dev VPS** (`95.216.167.198`) | `/opt/ultra-autotrade/main/` | `/opt/ultra-autotrade/main/backend/` |
> | **staging VPS** (`188.34.167.142`) | `/opt/ultra-autotrade/` | `/opt/ultra-autotrade/backend/` |
> | **production VPS** (`5.223.88.14`) | `/opt/ultra-autotrade/` | `/opt/ultra-autotrade/backend/` |
>
> dev VPS の `/main/` サブディレクトリは git worktree 構造に由来する（2026-07-03 構築済み）。staging/production 両VPSには `main/` サブディレクトリは**存在しない**。
> 手順書・Lane プロンプト・curl パスに `/opt/ultra-autotrade/main/` を書いた場合、staging/production VPS で `No such file or directory` になる。
> SSH ログイン直後に必ず `pwd && ls` で確認してから操作を開始すること。

- dev VPS への接続: ローカル Mac から `ssh uata-assistone-dev`（Mac `~/.ssh/config` に alias 定義済 →
  `root@95.216.167.198` / 鍵 `~/.ssh/hetzner_assistone_stagingdev`）。
- staging VPS への接続: ローカル Mac から `ssh uata-assistone-staging`（→ `root@188.34.167.142` / 鍵 `~/.ssh/hetzner_assistone_stagingdev`、dev と鍵共用）。
- **production VPS への接続: 意図的に `~/.ssh/config` に alias を作らない**。3段階プロトコル
  （phase1-investigator / phase2-implementer / phase3-deployer）経由のみで操作すること（CLAUDE.md ABSOLUTE）。
  やむを得ず直接 ssh する場合も `root@5.223.88.14` / 鍵 `~/.ssh/hetzner_assistone_production`。

### 役割分担（開発体制 v2 を 3 層に展開）

| 主体 | 稼働場所 | 責務 |
|------|----------|------|
| **claude.ai** | ブラウザ | PM / アーキテクト / Asana 管理 / Phase 計画 / 4 軸確認（コード実装はしない） |
| **Claude Code CLI** | dev VPS (`root@95.216.167.198`) | 実装・テスト・並列レーン（worktree 分離）・PR 作成 |
| **Mac（ローカル）** | 開発者端末 | GitHub への push 起点 / ローカル merge / レビュー。production VPS は **pull only**（CLAUDE.md ABSOLUTE） |

- 正規フロー: dev VPS で実装 → PR → ローカル Mac で merge → GitHub push → production VPS で `git pull origin main` → `deploy_production.sh`
- production VPS 上で直接 `git merge` / `git commit` / エディタ編集をしない（「本番デプロイフロー」セクション準拠）

### dev VPS 構築状況（2026-07-03時点）

> **構築完了。** ASSIST ONE dev VPS（95.216.167.198）で以下を実施・確認済み（read-only 実機確認 + セットアップ実行）:
> - repo clone（`/opt/ultra-autotrade/main/`、worktree構造）、`git pull origin main` で HEAD = origin/main 最新
> - backend `.venv` 依存インストール済み（`pip install -r requirements.txt` 差分なし）
> - frontend `node_modules` インストール済み（`npm install --legacy-peer-deps` up to date）
> - Docker / Docker Compose 新規インストール（`docker.io` 29.1.3 + `docker-compose-v2` 2.40.3、Ubuntu 26.04 標準リポジトリ。`hello-world` 疎通確認済み）
> - Claude Code CLI 導入済み（v2.1.197）
> - `/opt/ultra-autotrade-worktrees/` 新規作成（並列レーン用）
>
> 旧 `uata-dev-01`（77.42.79.75）は廃止対象のまま。手順は `docs/ops/host_migration_runbook.md`「Dev VPS 構築」セクション参照。
> 未実施: `.env.*` 実ファイルの配置（`.example` のみ）、VSCode Remote SSH 接続確認（小林さん側手動確認項目）。

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
- `load-claude-lessons.sh` (SessionStart) — `CLAUDE.lessons.md` を additionalContext として auto-Read (2026-05-21 分割と同時に追加)
- `pre-large-edit.sh` (PreToolUse) — 50 行超の変更を警告
- `post-commit-diff.sh` (PostToolUse) — コミット時に diff 表示
- `pre-tool-guard.sh` (PreToolUse) — Lane 越境 + `.env.production` 並列書込の物理ブロック
- `guard-env-files.sh` (PreToolUse) — 旧 env ファイル / production_operation_checklist.md の物理ブロック（R1 / R2 / R3）
- `slack_notify.py` (Notification / Stop) — Slack 完了通知
- `slack_permission.py` (PreToolUse) — Slack パーミッションリクエスト
- `post-lane-notify.sh` / `send-lane-completion.sh` — Agent Teams Lane 完了通知
- `update-heartbeat.sh` (PostToolUse) — `/tmp/uata-heartbeat` を更新 (stuck-detector 監視用)

### 並列 tool call は最大 2 本まで（24h 自走 / Agent Teams 必須ルール）

**背景:** Claude Code GitHub issues #43866, #44068, #39830, #46767 で報告されている
`[Tool result missing due to internal error]` バグは、**3本以上の並列 tool call** で
発生頻度が高い。24h 自走中に stuck すると人間が「続けて」と指示するまで停止する。

**ルール:**
- 並列 tool call は **最大 2 本**まで。3 本以上は順次実行 or 2 本ずつのバッチに分ける
- 独立性が高い調査でも 2 本 → 結果確認 → 2 本の順で実行
- `uata-stuck-detector.sh` が `/tmp/uata-heartbeat` の更新を 5 分間隔で監視し、
  30 分間更新なし → Slack `#ultra-auto-project` に `STUCK-DETECTED` 通知

**24h 自走起動手順:**
```bash
# stuck detector を起動してから claude を起動する
cd /opt/ultra-autotrade/main
./scripts/uata-stuck-detector.sh start
# → "stuck-detector 起動 (PID=XXXX, log=/tmp/uata-stuck-detector.log)"
claude --resume   # または新規セッション起動
```

---

## 朝プロトコル §9

### Step 0 (絶対実行 = 完了していなければ §9 進行禁止) — 2026-05-17 追加 / 2026-05-21 SessionStart Hook 統合

**CLI 側 (Claude Code)**: SessionStart Hook (`.claude/hooks/load-claude-lessons.sh`) が `claude` 起動時に
`CLAUDE.lessons.md` 全文を additionalContext として **自動 Read** する。手動 cat は不要。
Hook が動作していることの確認方法: セッション冒頭で「2026-05-19 AI v4 prompt KeyError」セクションが
context に含まれているか claude に問えば応答可能なはず (未登録なら「lessons.md が見えない」と返る)。

**claude.ai 側 (ブラウザ)**: 自動 Read 機構が無いため従来通り CLI cat 結果の貼付が必須。
claude.ai は §9 開始前に以下が claude.ai セッション内に貼り付けられていることを確認する。
貼り付けられていない場合は「朝プロトコル進行不可、Step 0 を実行してください」と返し、
他の作業を一切受け付けない。

CLI で実行 (所要 1分):

```bash
cd ~/projects/ultra-autotrade

echo "=== /mnt/project/CLAUDE.md head 80 (本指示文との整合確認用) ==="
head -80 /mnt/project/CLAUDE.md

echo ""
echo "=== /mnt/project/production_operation_checklist.md 全文 ==="
cat /mnt/project/production_operation_checklist.md

echo ""
echo "=== /mnt/project/CLAUDE.lessons.md 直近 5 セクション (新しい順) ==="
grep -nE "^## 20[0-9]{2}-" /mnt/project/CLAUDE.lessons.md | tail -5

echo ""
echo "=== 直近 postmortem (5件) ==="
ls -lt docs/postmortems/ 2>/dev/null | head -6

echo ""
echo "=== CLAUDE.md v4.1 反映確認 ==="
grep -n "並列開発フロー v4" CLAUDE.md
wc -l CLAUDE.md CLAUDE.lessons.md

echo ""
echo "=== 既install plugin 状態 ==="
claude plugin list 2>&1 | head -10
```

**claude.ai 側の責務**:
- 上記が貼り付けられていない時点で「§9 進行不可」を返す
- 貼り付け確認後、Step 1-5 (R2C ソート等) に進む
- §9 開始宣言に **「Step 0 確認済 (cat 結果セッション内に貼付 + CLI 側 SessionStart Hook 起動済)」を必ず含める**

### Step 0 違反の扱い

claude.ai が Step 0 をスキップして §9 を実行した場合、それは **鉄則8違反**。
- 1回目: 本人 (claude.ai) が指摘を受けて Step 0 やり直し
- 2回目以降: hkobayashi から claude.ai への信頼コスト発生、claude.ai は設計判断資格を失う
- v4 指示文 §3 「メモリルール3件以上参照 / 適用判定」と並んで運用される
- Step 0 未完のまま §9 を進めた事実は、§9 進行禁止ルールへの直接違反として記録される

### 経緯

2026-05-17 セッションで claude.ai が CLAUDE.md / production_operation_checklist.md /
31_backup_restore_procedures.md を view せず、本指示文 v4 のみで作業判断を進めた結果、
3回連続で鉄則8違反 (CLI 側 STOP 判断で救済)。同セッション中の P0 (postgres 2,448回クラッシュ
+ backup 全滅) 対応時にも /mnt/project/31_backup_restore_procedures.md を見ずに復旧手順を
推測しており、hkobayashi 直接指摘で発覚。

これを「気をつける」では防げないため、Step 0 強制化で **claude.ai が物理的に view せざるを得ない**
状態を作る。鉄則8違反の再発は本セクションの「Step 0 違反の扱い」に従って処理する。

2026-05-21 refactor で `CLAUDE.md` を分割 (core / lessons / ops) し、SessionStart Hook 経由で
`CLAUDE.lessons.md` を CLI 側で auto-Read するよう変更。claude.ai 側は引き続き手動 cat 必須。

---

## Lane 依頼標準テンプレート (1ブロック包括依頼) — 2026-05-20 v2 提案書 §A より統合

> 2026-05-20 night-mode で claude.ai が docker コマンドを 25 往復中継した違反 6 回の根本対策。
> Lane に「1ブロック依頼」すれば 1 往復で済む。

```
【Lane 依頼標準テンプレ】
環境: staging-new / production (どちらか明示)
現象: (1行で)
依頼: 以下を1ブロックで返す
  1. 実機 dump (docker ps / logs / DB query 等)
  2. 真因 (推測ではなく実データから)
  3. 修正案 (最小/標準/根本 の3択)
制約: 本番 DB write / deploy は HUMAN-REVIEW-REQUIRED で停止
```

違反パターン (P1-P5) と正しい行動は `CLAUDE.lessons.md` 2026-05-20 セクション参照。

---

## 参照ファイル

| ファイル | 内容 | いつ読むか |
|---------|------|----------|
| `CLAUDE.lessons.md` | **本指示文の教訓アーカイブ (時系列)** | 朝プロトコル §9 Step 0 で SessionStart Hook 経由 auto-Read。手動 review は postmortem 参照時 |
| docs/ops/01_api_endpoints.md | 全APIエンドポイント一覧（パス・認証・curl例） | curl を書く前・エンドポイントを推測しそうなとき |
| docs/ops/02_db_tables.md | 全DBテーブル定義（カラム・型・NULL可否） | ALTER TABLE を書く前・DBスキーマを推測しそうなとき |
| docs/ops/03_deploy_procedures.md | デプロイ手順・コンテナ名・ボリューム・障害対応 | デプロイ前・Docker環境を推測しそうなとき |
| docs/ops/05_backend_modules_map.md | backend モジュール一覧 (旧 Directory Structure) | router 追加 / main.py 編集前 |
| docs/ops/multillm_workflow.md | LLM ロール割り当て / デバッグ昇格ルール | Opus / Sonnet / Haiku 選択時 |
| docs/ops/codex_plugin.md | Codex Plugin 運用ルール | `/codex:review` 実行前 |
| docs/ops/orphan_detection.md | 孤立コード検出 (Dead Code / Disconnected Safety Scan) | PR 作成前 (新モジュール時必須) |
| docs/ops/agent_view.md | Claude Code Agent View 運用 | 並列レーン起動時 |
| docs/ops/claude_code_features.md | Claude Code 最新機能活用ガイド | サブエージェント / Hook / MCP 設定時 |
| docs/ops/oncall_policy.md | オンコールポリシー (1人プロジェクト) | アラート受信時 / 当番判断 |
| docs/ops/fee_model_v10.md | Fee Model v10 (Tier / RiskMode) | F-シリーズ実装時 |
| docs/13_security_design.md | セキュリティ設計詳細 | Aave/認証関連の実装時 |
| docs/14_test_strategy.md | テスト戦略詳細 | テスト設計時 |
| docs/28_staging_cors_csp_postmortem.md | CORS/CSPインシデント対策 | CORS/CSP問題発生時 |
| docs/29_tunnel_ops_guide.md | Cloudflare Tunnel運用手順 | Tunnel再起動時 |
| docs/34_phase2_protocols_guide.md | Phase 2 マルチプロトコル技術ガイド | Lido/Pendle/Optimizer/Risk Engine実装時 |
| docs/35_docker_maintenance_runbook.md | Docker 週次クリーンアップ手順 | disk 逼迫時・cron 設定変更時 |
| docs/postmortems/2026-05-09_staging_api_502.md | staging cloudflared ingress port mismatch 12日遅延検出 RCA | port変更PR・cloudflared変更時 |
| docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md | nginx upstream IP 固着 (resolver 未設定 + `--no-deps` 不在) RCA | nginx config・deploy script変更時 |

---

## Docker クリーンアップ運用

- **通常週次**: `scripts/docker_cleanup.sh`（dangling のみ / `builder prune -f` + `image prune -f`）
- **積極週次**: `scripts/periodic_docker_cleanup.sh`（ALL builder cache / `-a` フラグ + journal vacuum 1G）
  - cron 登録例: `0 3 * * 0 /opt/ultra-autotrade/scripts/periodic_docker_cleanup.sh`
- **禁止**: `docker system prune -af`（使用中イメージ削除リスク、CLAUDE.md 明記）
- 閾値: periodic スクリプト WARN=80% / CRITICAL=90%（Slack `#ultra-auto-project` 通知）
- **L7 ディスクチェック**: `healthcheck_l1_l6.sh` に組み込み済み（WARN=80%, CRITICAL=90% → overall FAIL）
- **月次ディスク監査** (小林さん専権、毎月手動):
  ```bash
  # 本番 VPS で実行
  df -h /
  du -sh /var/lib/docker/
  du -sh /var/log/journal/ 2>/dev/null
  docker system df
  ```
  80% 超 → `periodic_docker_cleanup.sh` 手動実行。90% 超 → 即時手動対応必須。
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

## 標準チェックリスト（全実装で必ず確認）

すべてのコード変更（機能追加・バグ修正・リファクタ問わず）で、実装完了前に以下を確認すること。

### UI / フロントエンド
- [ ] 全テキストが日本語（英語ハードコード禁止。ja.jsonにキーがあればそちらを使用）
- [ ] admin / partner / viewer(tester) の権限分離（role === "admin" で操作系の表示/非表示）
- [ ] 認証状態で表示が変わる要素（ログアウト/削除/設定等の操作系）は未ログイン時に必ずガード（`{(authenticated || token) && …}`）。新コンポーネントは既存コンポーネントの認証ガードをポートする（例: UserHeader 5c42868 の logout gate を AccountPanel に踏襲。ポート漏れ＝未ログインで「ログアウト」表示の再発要因）
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

## Launch Progress (2026-05-20〜)

正規ロードマップ: `docs/launch/roadmap_to_launch.md` (v1.0-skeleton)。5条件・6/3 シナリオ・実機データ再計算は本ロードマップで管理。CLAUDE.md §17 (5条件条文化) は本ロードマップ本文確定後に別 PR で追記する。

**現状 (2026-05-20)**:
- 想定ローンチ日 (claude.ai 提案 v1): 2026-06-03 (最早シナリオ、Tier B 4本並列構成)
- 並列レーン: chaos test script / approval_rate 計測 / 営業チーム運用 docs / 森先生 DM 草案 (詳細指示書は本日 16:00 までに別途起票)
- 起算ブロッカー: P0-X2 山本さん UAT INSERT が 4日 overdue (条件4 UAT 14日観測の起点遅延)
- HOLD bias v4: 2026-05-19 PR #302 merge 済 (memory 「staging 反映待ち」は陳腐化、要更新)

---

## ✅ 完了宣言の必須テンプレ

タスクや PR で「完了」「OK」「動きました」と書く時は、以下を貼る。
**1つでも欠けたら完了と書くことを禁ずる**。実機実行できない環境(prod / staging)
の場合は、人間に貼ってもらうコマンドを明示し、貼付け前に「完了」と書かない
(memory: prod-steps-not-done-until-verified)。

### Backend / API 系
- [ ] `git rev-parse HEAD`(対象 commit)
- [ ] `alembic current`(staging / production 両方)
- [ ] 該当 endpoint の curl 出力: HTTP code + body 1行
- [ ] 該当 DB 行の SELECT 結果(1〜5行)
- [ ] `scripts/launch_gate.sh --env=staging --only=Lx` 該当 L の PASS 出力

### Frontend 系
- [ ] git rev-parse HEAD
- [ ] Network tab で 200 を返した URL + payload(スクリーンショット or curl 同等)
- [ ] DOM に期待要素が表示された証跡(セレクタ + テキスト)
- [ ] Playwright e2e の該当テスト PASS 出力

### Config / Env / Migration 系
- [ ] `git diff` の影響範囲
- [ ] `bash scripts/check_env_separation.sh` PASS
- [ ] `bash scripts/check_db_migration_gap.sh --env <target>` PASS
- [ ] 配線確認: `grep -nE '<symbol>' backend/app/main.py`

### Blockchain 系
- [ ] tx hash + receipt の status=1
- [ ] event log の確認(emit された event 名)
- [ ] chain ID / RPC URL が想定通り

### 禁止事項
- 型チェック / lint / unit test pass「だけ」を根拠に完了と書かない
- "実装完了しました、テストしてください" は完了ではない
- 自分が書いた unit test のみで検証完了としない

---

## ✅ Codex Review セルフチェック(完了宣言前)

過去 PR #154/#155/#157/#162 で Codex Review が Claude の「完了」を救出した実例から抽出。
完了と書く前に Claude 自身がこのリストを通すこと。

### 実行ロジック
- [ ] dry_run=false が明示か(PR #157 例: process_news_loop で漏れていた)
- [ ] 非 2xx は failure 扱いか(PR #157 例)
- [ ] try/except で例外を握りつぶしていないか(silent failure)
- [ ] 後方互換モードで 503 リグレッションが出ないか(PR #155)
- [ ] ロールバック不能ステップが含まれていないか(PR #154)

### 環境分離
- [ ] staging-production クロスコンタミがないか(PR #154 / #155)
- [ ] DATABASE_URL / AAVE_NETWORK / *_API_KEY / container_name / volume が分離されているか
- [ ] APP_ENV が正しい値か(staging で APP_ENV=staging, prod で APP_ENV=production)
- [ ] AAVE_NETWORK が staging=base_sepolia / production=base か

### Migration / Schema
- [ ] models 変更で alembic migration が生成されているか(PR #155 privy_did)
- [ ] migration が staging / production に適用済みか
- [ ] schema 削除/型変更が含まれる場合の sanitize step があるか(PR #162)
- [ ] **CHECK 制約の enum 値が models.py と一致しているか** (models.py が唯一の真実源。migration 内で独自定義しない → 下記「CHECK制約ルール」参照)

### 配線
- [ ] 新規 class / router / scheduler / startup hook / endpoint が register / startup / crontab に登録済みか
- [ ] AutoEvacuator / CompoundRiskAssessor のような安全装置の孤立コードがないか
- [ ] PR #142 のような V2→V3 API 移行が他箇所にも反映されているか

### Auth / RBAC
- [ ] viewer に書き込み UI を露出していないか(PR #417 教訓)
- [ ] auth ガードを意図せず外していないか(401 リグレッション)

### 自己実行手順
完了宣言前に Claude が口頭で:
"Codex セルフチェック: <番号>. <項目> → PASS/該当なし" を全項目通す。
1つでも該当 → 修正してから再チェック。

---

## 📐 Pendle / AI Optimizer 開発ルール (EPIC-3/4, 2026-06-11)

### Pendle RouterV4 (hosted SDK)
- calldata は Pendle hosted SDK (`/sdk/api/v1`) が生成。web3.py での abi encode 不要、SDK レスポンスの calldata をそのまま tx に載せる。
- Pendle は2系統 API: `/core/v1`(PendleWebClient=market情報) と `/sdk/api/v1`(RouterV4=calldata)。混同禁止。
- Router 正式アドレス `0x888888888889758F76e7103c6CbF23ABbF58F946` はクラス定数で保持（env 上書きに依存しない）。slippage デフォルト `Decimal("0.005")`。

### Pendle market dynamic lookup + cache
- `/markets` から解決、TTL 300秒キャッシュ（`time.monotonic()` ベース＝金融計算でないので float 許容）。
- cache miss / API 失敗時は None 返却（fail-open）。キャッシュキーは大文字小文字不問。
- cache は `PendleRouterV4Client.__init__` 注入方式（既存シグネチャを変えない）。

### AI Optimizer シグナル統合 (weight 調整)
- optimizer は `backend/app/ai/optimizer/`（`protocols/optimizer/` ではない）。
- 実データ取得は Adapter 注入方式（`PendleSignalAdapter` / `LidoSignalAdapter`）。SignalAggregator は作らない。
- adapter は client=None/例外時にダミー定数へ fail-open フォールバック（optimizer 全体を落とさない）。
- adapter が呼ぶ client メソッドは read-only な APY/価格取得のみ（秘密鍵を要するメソッドは呼ばない）。メソッド名は実在を必ず grep 確認（鉄則9）。
- risk_mode weight: conservative ×1.5 / balanced ×1.0 / aggressive ×0.7 を全プロトコルの risk_penalty に一貫適用。未知 risk_mode は balanced 相当。

> 詳細技術ガイド: `docs/34_phase2_protocols_guide.md`

---

## 🗂 ドリフト再発カタログ(着手前に grep)

3ヶ月の Asana 履歴で形を変えて再発しているドリフト/配線漏れの典型箇所。
新規実装・変更前に以下に該当しないか確認すること。memory: project-recurring-drift-patterns

### 環境 / Infra
- DATABASE_URL の staging↔production 分離(2重定義 / 共有 / image 焼き込み)
- container_name 衝突(production.yml vs staging.yml)
- ultra-log-staging volume を production が使用
- AAVE_NETWORK が base_sepolia のまま production 稼働
- AAVE_RPC_URL_BASE_SEPOLIA が Ethereum Sepolia URL になっていた
- OPENAI_API_KEY staging・production 共有
- DISABLE スケジューラ flag の staging↔production 反転

### Migration / Schema
- production DB 未適用 alembic migration の手動適用漏れ
- proposals.execution_attempts のような新規列が片方の env にしかない
- models 変更時 alembic 必須化 CI が無いと検出されない
- **CHECK 制約 enum 値を migration 内で独自定義した結果 models.py と乖離 → IntegrityError** (例: d4 migration が `'LOW','MIDDLE','HIGH'` を定義、models.py は `'conservative','balanced','aggressive'` → 本番 INSERT 即死。Asana 1215272519685583)

### 配線 / 孤立コード
- AutoEvacuator + CompoundRiskAssessor 安全装置が register されず
- DummyClient staging guard 構造バグで write 経路全交換不能
- process_news_loop で dry_run=false 明示漏れ
- logging handler 欠落で app.* INFO ログ全 drop
- GPT-4o secondary_confidence=0 全件
- cognitive_state injection 漏れ
- _validate_model_config() startup hook 配線漏れ
- aave_data_fetcher.py V2→V3 API 移行漏れ
- factory が constructor 引数を供給せず属性未配線（make_aave_client が Web3AaveClient に token_addresses を渡さず build-tx が "Unknown asset"。複数生成経路で必須属性の供給有無を突き合わせる。#500）
- Asana タスク notes の「触るファイル」パスが実態と乖離（optimizer は `protocols/optimizer/` でなく `ai/optimizer/`、`signal_aggregator.py` は不在で実際は StrategyScorer）。実装着手前に必ず実パスを grep 確認（鉄則9）。2026-06-11 EPIC-4

### 依存 / ライブラリバージョン
- web3.py メジャー更新時の API drift（v6→v7 で `Contract.encodeABI()`→`encode_abi()`、`fn_name=`→位置引数。旧 API は `# type: ignore[attr-defined]` で mypy 検出を抑止していたため build-tx が runtime 500 になるまで気づかなかった）。依存更新 PR では camelCase web3 API（encodeABI/buildTransaction/rawTransaction 等）の残存を grep し、`# type: ignore[attr-defined]` を安易に付けない

該当しそうなものがあれば、修正してから完了宣言する。同種が出たら個別修正でなく
`scripts/launch_gate.sh` / CI gate に追加して再発防止する。

---

## 📐 CHECK制約と migration の二重管理ルール (Asana 1215272519685583)

### ルール: models.py が唯一の真実源

```
backend/app/<module>/models.py  ←  CHECK 制約 enum の正とする
        ↓ 従う
alembic/versions/*.py           ←  models.py の enum を読んで CHECK を書く
```

**やってはいけない:**
```python
# migration 内で独自 enum を定義 → models.py と乖離しやすい
sa.CheckConstraint("tier IN ('LOW','MIDDLE','HIGH')", name="ck_tier")
```

**やるべきこと:**
```python
# migration は models.py の enum 値リストを文字通り使う
# または CheckConstraint を設けず application-layer で制御する
# (値変更時は migration + models.py を同時に更新する)
```

### 背景
fee_transactions の d4 migration が `'LOW','MIDDLE','HIGH'` を CHECK 制約に定義、
一方 `models.py` は `'conservative','balanced','aggressive'` を使用していた。
production 適用後の INSERT が IntegrityError になり、production fee schema が壊れた。

### 確認コマンド
```bash
# CHECK 制約 enum と models.py の enum が一致するか grep で突き合わせ
grep -rn "CheckConstraint\|IN (" alembic/versions/ | grep -v "^Binary"
grep -rn "class.*Enum\|values\s*=\s*\[" backend/app/*/models.py
```
