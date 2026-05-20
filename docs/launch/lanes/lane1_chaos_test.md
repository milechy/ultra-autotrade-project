# Lane 1: chaos test script (staging で 3 日連続実行)

## メタ情報

| 項目 | 値 |
|---|---|
| Lane | 1 / Phase「ローンチ前 chaos 検証」 |
| Tier | **B** (`scripts/` 新規ファイル + `docs/launch/` 配下 + `backend/tests/chaos/` 新規) |
| auto-merge | **OK** (DoD 全通過時) |
| night-mode 投入 | **22:00 以降 〜 翌 04:00** (想定所要 4-6 h) |
| 並列 Lane 構成 | Lane 1-4 同時起動 (本指示書は Lane 1) |
| owner | Claude Code CLI bg lane (sonnet 4.6 で十分、Aave 触らないので opus 不要) |
| 関連 PR (要確認) | **#253** (chaos test の既存実装、本 Lane 着手前に状態確認必須) |
| 関連 roadmap | `docs/launch/roadmap_to_launch.md` §1 (条件群) + §3 (Lane 1) |

## /goal

**staging 環境で 3 日連続の chaos test を実行し、Aave / Lido / Pendle / 外部 API の障害シナリオで Ultra AutoTrade が safe-degrade することを実証する。** 結果は `docs/launch/chaos_test_results/YYYY-MM-DD_run_N.md` に記録し、roadmap §4 (実機データ再計算) の条件「chaos test 3 日連続 PASS」を満たす。

## 触るファイル (Tier 抵触チェック)

| ファイル | 種別 | Tier 判定 | 抵触可能性 | 備考 |
|---|---|---|---|---|
| `scripts/chaos_test_aave_outage.sh` | 新規 | B | なし | Aave RPC を mock URL に切替 → safe-degrade 確認 |
| `scripts/chaos_test_lido_outage.sh` | 新規 | B | なし | Lido API mock 化 |
| `scripts/chaos_test_pendle_outage.sh` | 新規 | B | なし | Pendle API mock 化 |
| `scripts/chaos_test_run_all.sh` | 新規 | B | なし | 上記 3 本を順次 / 並列実行する orchestrator |
| `backend/tests/chaos/test_*.py` | 新規 | B | なし | chaos シナリオの pytest version (CI 統合用) |
| `docs/launch/chaos_test_results/` | 新規 | B | なし | 3 日分の実行ログ格納 |
| `backend/app/automation/scheduled_tasks.py` | **既存 read only** | S | **触ったらアウト** | scheduler の挙動を chaos test 中に観測するだけ |
| `backend/app/main.py` | **既存 read only** | S | **触ったらアウト** | feature flag 等の追加禁止 |
| `docker-compose.staging.yml` | **既存 read only** | S | **触ったらアウト** | mock 注入は `.env.staging` 経由のみ |

**Tier S 抵触なし** を Lane 完了時に必ず再確認 (`git diff --name-only main..HEAD | grep -E "main\.py|scheduled_tasks|docker-compose|requirements"` で 0 件)。

## 前提確認 (Lane 開始直後、5 分以内)

```bash
cd /opt/ultra-autotrade/main

# 1. 既存 PR #253 の状態
gh pr view 253 --json state,title,headRefName,files,statusCheckRollup 2>&1 | head -60

# 2. 既存 chaos test ファイルの有無
find . -name "*chaos*" -not -path "*/node_modules/*" -not -path "*/.git/*"

# 3. staging 接続性 (CF Access Service Token 必須)
curl -fsS -o /dev/null -w "[%{http_code}]\n" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  https://api-staging.ultra-auto-trade.com/health

# 4. healthcheck baseline (chaos 前の正常値取得)
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
  "cd /opt/ultra-autotrade && cat /tmp/healthcheck_l1_l6.log 2>/dev/null | tail -50"
```

**判断**: PR #253 が
- **MERGED** → 既存 chaos test を staging で 3 日実行するだけ。本 Lane は「実行記録の取得 + DoD 完了」に scope 縮小
- **OPEN / DRAFT** → 本 Lane で **rebase + 補強実装** が必要
- **CLOSED (未 merge)** → 本 Lane で **新規実装** (本指示書本体の手順)
- **存在しない** → 同上、新規実装

## 実装手順

### Step 1: chaos シナリオ設計 (30 min)

3 シナリオを `docs/launch/chaos_test_design.md` に書き出してから実装に入る:

| シナリオ | 障害注入対象 | 期待 safe-degrade 挙動 |
|---|---|---|
| Aave RPC 死亡 | `AAVE_RPC_URL` を blackhole 化 | HF 取得失敗 → `HOLD` + Slack 警告 + scheduler 継続 |
| Lido API 死亡 | `LIDO_API_URL` を blackhole | Lido APY 取得失敗 → Pendle/Aave のみで Optimizer 判定継続 |
| Pendle API 死亡 | `PENDLE_API_URL` を blackhole | Pendle YT 評価 skip → 他 protocol で判定継続 |

各シナリオに「**期待しない挙動**」も明示 (例: HARD_STOP 誤発火、proposals テーブル汚染、DB connection leak)。

### Step 2: chaos_test_<service>_outage.sh 実装 (60 min × 3 = 3 h)

各スクリプトの構造:

```bash
#!/bin/bash
# scripts/chaos_test_aave_outage.sh
# Aave RPC 死亡シナリオ。staging のみ。production への適用禁止。

set -euo pipefail

# Guard: production への接続を物理ブロック
if [[ "${TARGET_ENV:-}" == "production" ]]; then
  echo "ERROR: chaos test は production 禁止"
  exit 1
fi

# Step 1: baseline snapshot (chaos 注入前)
# Step 2: AAVE_RPC_URL を blackhole に書き換え (.env.staging.chaos)
# Step 3: backend 再起動 (--no-deps --force-recreate backend-blue)
# Step 4: 60 min 観測 (scheduler 5 回判定 / Slack 通知件数 / DB 整合性)
# Step 5: 復旧 (元の AAVE_RPC_URL に戻す)
# Step 6: post-snapshot 取得 → diff レポート
```

**重要**:
- `.env.staging` 直接編集は禁止 (CLAUDE.md §環境ファイル更新ルール)。`.env.staging.chaos` を一時的に生成して `--env-file` で上書き
- restart は `up -d --force-recreate --no-deps` (CLAUDE.md 2026-05-17 教訓: `restart ≠ recreate`)
- production への接続は環境変数 / URL の prefix チェックで物理ブロック

### Step 3: orchestrator + 3 日実行 (30 min 実装 + 3 日待機)

```bash
# scripts/chaos_test_run_all.sh
# 3 シナリオを順次実行。1 シナリオ = 60 分観測。
# 3 シナリオ × 1 日 = 1 set。3 日連続 = 3 set。
# Day 1: 21:00 起動 → 24:00 完了
# Day 2: 同上
# Day 3: 同上
# 結果を docs/launch/chaos_test_results/2026-MM-DD_run_N.md に記録
```

**3 日連続実行は cron 化せず、各日 22:00 に手動で Agent View (`claude agents` 起動 → 該当 Lane 行を選択 → `/bg` で背景投入) で kick**。理由: chaos test の最中に他 Lane が staging を触ると干渉する。

### Step 4: pytest chaos suite (60 min)

CI 統合のため `backend/tests/chaos/test_*.py` を実装。VCR replay で外部 API mock 化、scheduler を test 内で 1 サイクル走らせて safe-degrade を verify。

### Step 5: 結果レポート (各日 30 min)

`docs/launch/chaos_test_results/2026-MM-DD_run_N.md` テンプレ:

```markdown
# Chaos Test Run #N (2026-MM-DD)

## Summary
- 開始: HH:MM JST
- 終了: HH:MM JST
- シナリオ: aave / lido / pendle
- 結果: PASS / PARTIAL_PASS / FAIL

## Per-scenario

### Aave RPC outage
- 期待挙動: HOLD + Slack 警告
- 実観測: TBD
- safe-degrade: PASS / FAIL
- 異常 (あれば): TBD

(同 Lido / Pendle)

## 検出された不具合
| Severity | 内容 | Asana 起票 |
|---|---|---|

## Run #N+1 への引継ぎ
```

## DoD

### A. 機能完了
- [ ] PR #253 状態判定済 (`gh pr view 253`)
- [ ] 3 chaos scripts (`aave_outage` / `lido_outage` / `pendle_outage`) staging で動作確認
- [ ] orchestrator `chaos_test_run_all.sh` 動作確認
- [ ] pytest chaos suite (`backend/tests/chaos/test_*.py`) CI で全 PASS
- [ ] **3 日連続実行ログ** が `docs/launch/chaos_test_results/` 配下に 3 件

### B. Gate 全通過 (CLAUDE.md §5)
- [ ] Gate 1-3: `./scripts/verify.sh` 全 pass
- [ ] Gate 4: Playwright E2E — **N/A** (chaos test は UI なし、pytest chaos suite で代替)
- [ ] Gate 5: 孤立コード検出 — **必須** (新規 scripts/scaffold の配線確認)
- [ ] Gate 6: Codex Review (`/codex:review --base main --background`) — **必須**
- [ ] Gate 7: Claude in Chrome — **N/A**
- [ ] Gate 8: deploy 後外形 `/health` — **N/A** (本 Lane は deploy しない)

### C. 教訓記録 (CLAUDE.md §0)
- [ ] chaos test 実装中の詰まり / 推測失敗 / 環境分離違反 を CLAUDE.md 「教訓-2026-05-2X」セクションに追記 (該当なしなら「特記なし」と明示)
- [ ] §13 環境分離違反は太字で記録

### D. Asana 連携
- [ ] PR description に該当 Asana GID + Closes 記述
- [ ] Lane 完了時 notes に PR link + Gate 結果 + 教訓サマリ
- [ ] PR main マージ後 close

### E. Slack JSON 通知 (`.claude/hooks/send-lane-completion.sh`)
```json
{
  "lane": "1",
  "phase": "ローンチ前 chaos 検証",
  "status": "completed | partial_complete | blocked | failed",
  "tier": "B",
  "lessons_learned_count": N,
  "gate_results": {
    "1-3_verify": "pass | fail",
    "4_e2e": "n/a — pytest chaos suite で代替",
    "5_dead_code": "pass | n/a",
    "6_codex": "approved | minor | major",
    "7_chrome": "n/a",
    "8_health": "n/a"
  },
  "chaos_runs": 3,
  "safe_degrade_results": ["aave: PASS", "lido: PASS", "pendle: PASS"],
  "pr_url": "...",
  "next_action": "roadmap §4 条件「chaos 3 日連続 PASS」マーク"
}
```

### F. claude.ai 引継ぎ
- [ ] PR URL / Gate 1-8 個別判定 / 教訓記録 CLAUDE.md 追記行
- [ ] staging 実機検証実値 (3 日 × 3 シナリオ = 9 件の safe-degrade 結果)
- [ ] roadmap_to_launch.md §4 「chaos test 3 日連続 PASS」マーク更新依頼

## 制約 (絶対遵守)

1. **production への chaos 注入禁止** (TARGET_ENV=production を物理ブロック / Aave Mainnet RPC URL の prefix チェック)
2. **staging DB への INSERT 限定** (CLAUDE.md §テストデータ投入制限、`ultra-autotrade-postgres-staging` コンテナ限定)
3. **production deploy 系コマンド禁止** (`deploy_production.sh` を含まない、`docker-compose.production.yml` を触らない)
4. **Tier S ファイル touch 禁止** (上記表参照、特に `main.py` / `scheduled_tasks.py` / `docker-compose.*` / `requirements.txt`)
5. **環境ファイル変更は `awk + tmpfile + mv`** (sed -i 禁止、CLAUDE.md §環境ファイル更新ルール)
6. **山本さんが UAT 中なら chaos test を一時停止** (Slack #ultra-auto-project で 22:00 段階の UAT 進行状況を確認、衝突回避)

## night-mode CI auto-fix

本 Lane の PR は night-mode で ruff format / I001 等の軽微 fix が走る可能性あり (`.claude/rules/night-mode-ci-autofix.md`)。3 往復制限超過時は HUMAN-REVIEW-REQUIRED で停止。

## References

- `CLAUDE.md` §並列開発フロー v4 (Tier 分類 / Lane プロンプト DoD 強化版)
- `CLAUDE.md` §2026-05-17 教訓 (docker compose restart ≠ recreate)
- `CLAUDE.md` §環境ファイル更新ルール (sed -i 禁止)
- `docs/launch/roadmap_to_launch.md` §3 Lane 1
- `docs/14_test_strategy.md` (chaos test の位置づけ)
- `docs/ops/03_deploy_procedures.md` (staging コンテナ操作)
- `scripts/healthcheck_l1_l6.sh` (chaos 中の継続監視に使用)
- handoff: https://mooores.slack.com/archives/C0ACS09FMGC/p1779245661503999

## 推定所要時間内訳

| 工程 | 想定 |
|---|---|
| 前提確認 + PR #253 状態判定 | 15 min |
| Step 1 設計 | 30 min |
| Step 2 scripts × 3 | 3 h |
| Step 3 orchestrator | 30 min |
| Step 4 pytest chaos suite | 60 min |
| Step 5 Run #1 実行 (Day 1, 22:00) | 90 min (実行 60 + レポート 30) |
| **Run #2 / #3** | **翌日以降、本 Lane 範囲外** |
| **night-mode 初回 (22:00-04:00) 想定** | **5-6 h で Step 1-4 + Run #1 完了** |
