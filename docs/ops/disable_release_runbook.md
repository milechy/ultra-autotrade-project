# DISABLE_AI_JUDGMENT_SCHEDULER 解除 Runbook

**作成日**: 2026-05-21  
**対象 PR 群**: #365 (AI HOLD bias / BUY-SELL AND 条件), #367 (chain Base / AAVE_RPC_URL_BASE), #370 (startup delay 300s), Stream4 (blue-green color 判定)  
**実施予定**: 2026-05-23 朝 (staging 24h 観測完了後)  
**レビュー必須**: 小林さん + claude.ai 朝プロトコル Step 0 後に GO 判断

---

## A. 前提

本番 backend は `DISABLE_AI_JUDGMENT_SCHEDULER=1` で AI judgment scheduler が停止中。

- **停止理由**: 2026-05-21 P0 対応 — AI が 99.2% HOLD のまま BUY/SELL 指示を出せない状態  
- **暫定対応**: #365 (HOLD bias 修正: SELL/BUY の AND 閾値ロジック) を staging-new に deploy  
- **観測中**: staging で #365 の効果を 24h 観測（2026-05-21 夜 〜 2026-05-22 夜）  
- **本 runbook の目的**: 観測完了後の解除判断基準・手順・ロールバック方法を明文化する

### 関連 Asana タスク

| GID | タスク |
|-----|--------|
| `1214994592672308` | P0-2 DISABLE_AI_JUDGMENT_SCHEDULER 解除判断 |
| #365 PR | AI HOLD bias 修正 (BUY/SELL AND 条件 → 70% 閾値) |
| #367 PR | chain Base 設定 + AAVE_RPC_URL_BASE 本番設定 |
| #370 PR | scheduler startup delay 300s (fan-out 緩和) |

---

## B. staging 24h 観測結果 評価 SQL（確定版）

観測完了後、**本番 VPS で実行する前に** staging で以下 SQL を実行して結果を確認すること。

```bash
# staging ai_decisions の action 分布 (24h)
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade_staging -c \
  "SELECT action, prompt_version, count(*)
   FROM ai_decisions
   WHERE created_at > NOW() - INTERVAL '24 hours'
   GROUP BY action, prompt_version
   ORDER BY count DESC;"
```

### 補足確認 SQL

```bash
# BUY/SELL が出た場合、proposals にも fan-out されているか確認
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade_staging -c \
  "SELECT status, count(*)
   FROM proposals
   WHERE created_at > NOW() - INTERVAL '24 hours'
   GROUP BY status;"

# startup delay 効果: tick 間隔が 300s 後から開始されているか
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade_staging -c \
  "SELECT created_at, action
   FROM ai_decisions
   ORDER BY created_at ASC
   LIMIT 5;"
```

---

## C. 判定分岐

SQL 結果を確認し、以下の基準で判断する。

### C-1: 解除 GO (手順 D へ進む)

**条件**: BUY または SELL が **1 件以上** 存在する

- AND 条件 (70% 閾値) が正常動作している証拠
- fan-out / startup delay の動作も合わせて確認
- claude.ai + 小林さんが結果を確認してから GO 宣言

### C-2: 解除 HOLD (再調整 → 再観測)

**条件**: BUY = 0 件 かつ SELL = 0 件

AND 閾値が厳しすぎる可能性が高い。以下の対応を行う:

1. **閾値を調整**: `70%` → `65%` に緩和  
   - 変更対象ファイル: `backend/app/ai/prompts.py` の BUY/SELL 判定閾値  
   - 変更対象ファイル: `backend/app/ai/service.py` の AND 条件評価ロジック  
2. **PR を再起票**: 既存 #365 を更新 or 新規 `fix/hold-bias-threshold-65` ブランチで PR  
3. **staging 再 deploy**: 再調整後の コードを staging-new に deploy  
4. **再観測 24h**: 再観測完了後に本 runbook C-1 / C-2 を再適用  
5. **解除は再観測完了後**: 再観測前に本番解除しない

---

## D. 本番 DISABLE 解除手順

**前提チェックリスト (セクション F) を全て「done」にしてから開始すること。**

### D-1: DISABLE フラグ削除

本番 VPS で実行。`sed -i` は禁止（前行連結バグ）。

```bash
# 本番 VPS: /opt/ultra-autotrade/ が repo root (main/ サブディレクトリなし)
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155

# .env.production のバックアップ作成
cp /opt/ultra-autotrade/.env.production /opt/ultra-autotrade/.env.production.bak.$(date +%Y%m%d-%H%M%S)

# DISABLE_AI_JUDGMENT_SCHEDULER を 0 に変更 (awk + tmpfile + mv)
awk '{gsub(/DISABLE_AI_JUDGMENT_SCHEDULER=1/, "DISABLE_AI_JUDGMENT_SCHEDULER=0"); print}' \
  /opt/ultra-autotrade/.env.production > /tmp/env_production_new.txt \
  && mv /tmp/env_production_new.txt /opt/ultra-autotrade/.env.production

# 変更確認
grep DISABLE_AI_JUDGMENT_SCHEDULER /opt/ultra-autotrade/.env.production
# → DISABLE_AI_JUDGMENT_SCHEDULER=0 と表示されること
```

> **注意**: `DISABLE_AI_JUDGMENT_SCHEDULER` を完全削除でも `=0` 設定でも動作は同じ。  
> バックアップファイルが残っている場合、誤って古い設定を参照しないよう `.bak.*` ファイルは `/tmp/` に移動推奨。

### D-2: backend コンテナ再起動 (active color のみ)

Stream4 (blue-green deployment) の active color を確認してから、**active side のみ** recreate する。

```bash
# active color 確認 (Stream4 実装後)
# nginx upstream または healthcheck で現在 active な color を確認
grep -E "blue|green" /opt/ultra-autotrade/nginx/upstream.production.conf | head -5

# active color のみ再起動 (例: green が active の場合)
docker compose -f /opt/ultra-autotrade/docker-compose.production.yml \
  --env-file /opt/ultra-autotrade/.env.production \
  up -d --no-deps --force-recreate backend-green

# ※ Stream4 未適用時 (blue-green 未分離): backend-production を使用
# docker compose -f docker-compose.production.yml --env-file .env.production \
#   up -d --no-deps --force-recreate backend-production
```

### D-3: 起動確認

```bash
# ログ確認: "scheduler started" が出ること
docker logs ultra-autotrade-backend-green-production --since=2m --tail=50 2>&1 \
  | grep -E "scheduler|DISABLE|startup|delay"

# 期待するログ:
# INFO: scheduler started (interval=4h)
# INFO: startup delay 300s — waiting before first tick

# startup delay (#370) により第1 tick は約5分後
# 5分後に ai_decisions に新規レコードが INSERT されることを確認
```

### D-4: AAVE_RPC_URL_BASE 設定確認 (#367)

```bash
# AAVE_RPC_URL_BASE と AAVE_ACTIVE_CHAINS=base が設定済みであることを確認
grep -E "AAVE_RPC_URL_BASE|AAVE_ACTIVE_CHAINS" /opt/ultra-autotrade/.env.production
# → AAVE_RPC_URL_BASE=https://... (実 RPC URL)
# → AAVE_ACTIVE_CHAINS=base
```

### D-5: 第1 tick 後の監視 (5〜10 分後)

```bash
# ai_decisions に新規レコードが入ったか確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
  "SELECT id, action, prompt_version, created_at
   FROM ai_decisions
   ORDER BY created_at DESC
   LIMIT 5;"

# proposals fan-out 確認 (BUY/SELL が出た場合)
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
  "SELECT id, status, created_at
   FROM proposals
   ORDER BY created_at DESC
   LIMIT 5;"
```

---

## E. ロールバック（再 DISABLE）

### E-1: scheduler の即時停止

```bash
# 本番 VPS
# .bak ファイルがあれば確認
ls /opt/ultra-autotrade/.env.production.bak.*

# DISABLE を 1 に戻す (awk + tmpfile + mv)
awk '{gsub(/DISABLE_AI_JUDGMENT_SCHEDULER=0/, "DISABLE_AI_JUDGMENT_SCHEDULER=1"); print}' \
  /opt/ultra-autotrade/.env.production > /tmp/env_production_rollback.txt \
  && mv /tmp/env_production_rollback.txt /opt/ultra-autotrade/.env.production

# 確認
grep DISABLE_AI_JUDGMENT_SCHEDULER /opt/ultra-autotrade/.env.production
# → DISABLE_AI_JUDGMENT_SCHEDULER=1

# コンテナ再起動
docker compose -f /opt/ultra-autotrade/docker-compose.production.yml \
  --env-file /opt/ultra-autotrade/.env.production \
  up -d --no-deps --force-recreate backend-green
```

### E-2: proposal 異常時 (緊急 backend 停止)

proposal 連続異常 / 暴走が確認された場合:

```bash
# backend コンテナを停止 (P0 手順と同様)
docker compose -f /opt/ultra-autotrade/docker-compose.production.yml \
  stop backend-green

# 停止確認
docker ps | grep backend
```

> **判断基準**:  
> - proposals が 5 件/分 超で連続生成 → 異常 → 即時 stop  
> - BUY/SELL が出たが 1〜2 件/4h サイクル → 正常範囲

---

## F. 解除前提条件チェックリスト

**このチェックリストを全て「done」にするまで、手順 D を開始しない。**

| # | 確認項目 | 確認方法 | done? |
|---|----------|----------|-------|
| 1 | staging 24h 観測完了 (2026-05-22 夜以降) | 観測開始時刻 + 24h 経過確認 | [ ] |
| 2 | BUY または SELL >= 1 件を確認 | セクション B の SQL 実行結果 | [ ] |
| 3 | PR #367 (chain Base / AAVE_RPC_URL_BASE) が main に merge 済み | `git log origin/main --oneline | grep 367` | [ ] |
| 4 | AAVE_RPC_URL_BASE が .env.production に設定済み | `grep AAVE_RPC_URL_BASE .env.production` | [ ] |
| 5 | Stream4 blue-green color 判定 PR が main に merge 済み | `gh pr list --state merged | grep stream4` | [ ] |
| 6 | PR #370 (startup delay 300s) が main に merge 済み | `git log origin/main --oneline | grep 370` | [ ] |
| 7 | proposals テーブルの未完了 proposal (#1 等) が terminal 済み | `SELECT status, count(*) FROM proposals WHERE status NOT IN ('executed','rejected','expired')` | [ ] |
| 8 | 小林さんの GO 承認 | Slack #ultra-auto-project または直接確認 | [ ] |
| 9 | claude.ai の朝プロトコル Step 0 完了後に最終確認 | claude.ai セッションで Step 0 宣言あり | [ ] |

---

## G. 参照ドキュメント

| ドキュメント | 参照タイミング |
|---|---|
| `docs/ops/03_deploy_procedures.md` | Docker コンテナ操作前 |
| `docs/ops/02_db_tables.md` | SQL 実行前 (ai_decisions / proposals テーブル定義) |
| `docs/ops/production_operation_checklist.md` | 本番操作前の全般チェック |
| `docs/ops/staging_recovery_v4_prompt.md` | staging-new 消滅時の復旧 |
| `.claude/CLAUDE.md` | 本番 VPS での禁止操作確認 (sed -i 禁止等) |
| `CLAUDE.lessons.md` | 2026-05-21 P0 インシデント教訓 |

---

*runbook version: 1.0 / 作成: 2026-05-21 Stream5 Lane / Tier B (docs 新規)*
