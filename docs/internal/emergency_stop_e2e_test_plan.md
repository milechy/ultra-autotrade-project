# 緊急停止 E2E テスト計画 (P0-4)

**バージョン:** 0.2 (実 endpoint 反映)
**起票日:** 2026-05-23
**担当:** Ultra AutoTrade 運用チーム / Claude Code
**関連 Asana:** P0-4 (緊急停止 E2E)
**関連 doc:** [`docs/33_emergency_stop_governance.md`](../33_emergency_stop_governance.md)

---

## 0. 本 doc の目的・スコープ

緊急停止 (emergency_stop) の挙動を E2E でテストする計画を 4 シナリオに分けて定義する。
本 PR では **実機実行は行わない**。staging での実行は別チケットで行う。

本 doc に含まれる:
- 4 シナリオの前提条件・手順・期待結果・失敗時調査ポイント
- 実 endpoint / state.json path / 期待 HTTP コードを反映
- staging を想定した curl / psql / docker compose コマンド
- scheduler フラグ逆転 (memory: `disable-scheduler-flag-inverted`) への注意喚起
- prod は dev から SSH 不可 (memory: `prod-steps-not-done-until-verified`) のため手動実行が必要な旨

本 doc に含まれないもの:
- 実機 (staging/prod) 実行ログ
- merge 可否判断 (claude.ai + 小林さんの最終承認に従う)

---

## 1. 共通前提

### 1-1. 環境

| 項目 | staging | production |
|------|---------|-----------|
| backend URL | `https://api-staging.ultra-auto-trade.com` | `https://api.ultra-auto-trade.com` (TODO 確定) |
| compose file | `docker-compose.staging.yml` | `docker-compose.production.yml` |
| backend container | `ultra-autotrade-backend-blue-staging-new` / `-green-` | `-prod-*` |
| postgres container | `ultra-autotrade-postgres-staging-new` (user: `ultra` / db: `ultra_autotrade_staging`) | prod compose 参照 |
| state.json path | `/var/run/ultra/state.json` (volume `ultra-state-staging-new`) | 同 path |
| scheduler フラグ | **ENABLED + shadow mode** | **DISABLED** |
| 実行可否 | 本 doc 手順で実行可 | dev から SSH 不可・**手動実行必須** |

### 1-2. 実 endpoint 一覧

| Method | Path | Auth | Source |
|--------|------|------|--------|
| POST | `/api/automation/emergency-stop` | Bearer, `require_partner` (Partner+) | `backend/app/api/automation_dashboard.py:168` |
| POST | `/api/automation/emergency-stop/resume` | Bearer, `require_admin` | `backend/app/api/automation_dashboard.py:187` |
| GET  | `/api/automation/status` | Bearer, `require_viewer` | `backend/app/api/automation_dashboard.py:83` |
| GET  | `/api/aave/status` | (router 参照) | `backend/app/aave/router.py` |
| POST | `/automation/emergency-stop` (legacy) | Bearer, `require_active_user`, no body | `backend/app/automation/automation_router.py:168` |
| POST | `/automation/process-news` | `X-Internal-Token` header | `backend/app/automation/automation_router.py:63` |

本テストでは **`/api/automation/*` (dashboard router) を主系** として使用する。
legacy の `/automation/emergency-stop` (require_active_user) は誰でも発動できてしまうため
シナリオ A の冗長確認には使わない。

### 1-3. ⚠️ scheduler フラグ逆転に関する注意

memory `disable-scheduler-flag-inverted` 参照。

- staging: `DISABLE_SCHEDULER=false` (ON) + `AI_JUDGMENT_SHADOW_MODE=true` で常時動作
- production: `DISABLE_SCHEDULER=true` (OFF) で停止
- soak テスト中にこのフラグを取り違えると `ai_decisions` 0 件で評価不成立になる
- 本 E2E でも staging で scheduler が動いている前提で手順を組む

### 1-4. ⚠️ production 実行の制約

memory `prod-steps-not-done-until-verified` 参照。

- dev 環境から prod へ SSH は不可
- prod でのテストは運用担当が手動で実行する
- 本 doc は staging のみ自動化対象。prod での実機出力で裏取りが取れるまで「完了」と書かない

### 1-5. 必要権限・トークン

- ADMIN ロールの Bearer API トークン (`STAGING_ADMIN_TOKEN`) — 発動・解除両方
- PARTNER ロールの Bearer API トークン (`STAGING_PARTNER_TOKEN`) — 解除不可の検証用
- `INTERNAL_API_TOKEN` 環境変数の値 (`STAGING_INTERNAL_TOKEN`) — `/automation/process-news` 用
- staging postgres への `docker compose exec` 権限
- staging backend container への `docker compose exec` / `docker compose logs` 権限

### 1-6. 前提コード参照 (本 PR では変更しない)

- `backend/app/api/automation_dashboard.py` — `/api/automation/emergency-stop[/resume]`
- `backend/app/automation/automation_router.py` — `/automation/emergency-stop`, `/automation/process-news`
- `backend/app/automation/monitoring_service.py` — `activate_emergency_stop()` / `clear_emergency_stop()` / `record_health_factor()` / `_restore_emergency_state()`
- `backend/app/automation/workflow.py:330` — `is_trading_allowed()` 否定で全件 HOLD する rule_engine_pre_check
- `backend/app/aave/state_manager.py` — state.json の atomic write / parse error 時 fail-closed
- `backend/app/aave/schemas.py:39` — `AaveSystemState` スキーマ

### 1-7. state.json 構造 (vault: AaveSystemState)

`backend/app/aave/schemas.py:39` より:

```json
{
  "emergency_stop": true,
  "mode": "hard_stop",
  "health_factor": "1.45",
  "last_update": "2026-05-23T12:34:56+00:00",
  "reason": "health factor 1.45 below emergency threshold 1.6",
  "circuit_closed": true,
  "stale_threshold_seconds": 300
}
```

- `mode` enum: `normal` / `safe_mode` / `hard_stop` (`AaveOperationMode`)
- `health_factor` は文字列 (Decimal serialized) — `null` の場合はポジションなし
- `circuit_closed`: `false` の場合は Circuit Breaker 開放で全停止
- atomic write は `state_manager.py:save_system_state` を経由 (NamedTemporaryFile + os.replace)

---

## 2. シナリオA: 手動発動

### 2-1. 概要

operator が API (将来的には UI) から emergency_stop を ON にする。
本テストでは PARTNER 権限以上で発動できる `/api/automation/emergency-stop` を使用。

### 2-2. 前提条件

- staging backend が正常稼働 (`/api/automation/status` が 200)
- `is_trading_paused=false` から開始
- 進行中の tx がなければベスト
- ADMIN Bearer トークンを取得済み

### 2-3. 手順 (script: `scenario_a`)

```bash
# Step 1: 事前状態確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/automation/status
# 期待: HTTP 200, .is_trading_paused == false

# Step 2: 緊急停止発動 (Partner+ 権限)
curl -X POST \
  -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"e2e scenario A manual"}' \
  https://api-staging.ultra-auto-trade.com/api/automation/emergency-stop
# 期待: HTTP 200, .status == "stopped"

# Step 3: 発動後の状態確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/automation/status
# 期待: .is_trading_paused == true

# Step 4: state.json 確認
docker compose -f docker-compose.staging.yml exec -T backend-blue \
  cat /var/run/ultra/state.json
# 期待: .emergency_stop == true, .mode == "hard_stop"

# Step 5: process-news で全件 HOLD を確認 (HTTP 200 だが skipped == fetched)
curl -X POST \
  -H "X-Internal-Token: $STAGING_INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  'https://api-staging.ultra-auto-trade.com/automation/process-news?dry_run=true'
# 期待: HTTP 200, .octobot_skipped_count == .fetched_count
# 注: 元の skeleton にあった「503」は workflow.py の実装と合わない (rule_engine_pre_check が HOLD する)。

# Step 6: ai_decisions の最近の記録を確認
docker compose -f docker-compose.staging.yml exec -T postgres \
  psql -U ultra -d ultra_autotrade_staging -c \
  "SELECT id, action, confidence, primary_provider, created_at FROM ai_decisions ORDER BY created_at DESC LIMIT 5;"
```

### 2-4. 期待結果

| ステップ | 期待 |
|---------|------|
| Step 2 | HTTP 200, `{"status":"stopped","message":...}` |
| Step 3 | `is_trading_paused=true` |
| Step 4 | `emergency_stop=true`, `mode=hard_stop`, `reason` に `Manual emergency stop ... (user_id=...)` |
| Step 5 | HTTP 200, `octobot_skipped_count == fetched_count` (`hold_count` で計上される) |
| Step 6 | rule_engine は LLM 呼出し前にブロックするため新規 ai_decisions は通常追加されない (既存件のみ) |

### 2-5. 失敗時の調査ポイント

- HTTP 200 が返らない → トークン権限 (`require_partner`), router 登録 (`backend/app/main.py:249`)
- state.json が更新されない → `MonitoringService.activate_emergency_stop()` の `_sync_state_file` ログ
- process-news が trade してしまう → `workflow.py:330 is_trading_allowed()`, `monitoring_service._trading_paused` の値
- ai_decisions に何も記録されない → 元々 pending が 0、または scheduler フラグ逆転 (memory 参照)

**ログ場所:**
- backend container stdout: `docker compose -f docker-compose.staging.yml logs backend-blue`
- 永続ログ volume: `ultra-log-staging-new` (`/var/log/ultra-autotrade`)
- Loki: promtail 経由で集約 (`docker-compose.staging.yml:53 loki`)

### 2-6. 後始末

シナリオ C を続けて実行するか、ADMIN 経由で resume を呼ぶこと。

---

## 3. シナリオB: HF < 1.6 で自動発動

### 3-1. 概要

HealthFactor 監視が 1.6 を切ったタイミングで emergency_stop が自動 ON になる。

実 Aave testnet の HF を意図的に下げるのは非現実的なので、**2 経路** を定義:

- **B-1 (実装済み)**: state.json を手動で `emergency_stop=true / health_factor=1.45` に書き換え、
  backend を restart して `_restore_emergency_state()` が拾うことを確認する。
  → これは「永続化と起動時復元の経路」をカバーし、シナリオ D と一部重複するが、
  HF<1.6 のシナリオを構造的に再現できる唯一の安全な手段。
- **B-2 (未実装・案)**: staging 専用の admin endpoint を追加し、
  `MonitoringService.record_health_factor(Decimal("1.45"))` を直接呼ぶ。
  これで監視ループ経由の自動発動を再現できる。
  → 本 PR では実装しない。実装する場合は `backend/app/api/automation_dashboard.py` に
  `@router.post("/_test/inject-hf")` を追加し、staging 環境変数で gating する。

### 3-2. 前提条件

- staging backend が稼働
- emergency_stop は OFF からスタート
- backend container を再起動できる権限

### 3-3. 手順 (script: `scenario_b`, B-1 経路)

```bash
# Step 1: 事前状態確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/aave/status
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/automation/status

# Step 2: state.json をバックアップして HF=1.45 に書き換え
docker compose -f docker-compose.staging.yml exec -T backend-blue \
  cat /var/run/ultra/state.json > /tmp/state.before.json

jq '.emergency_stop=true | .mode="hard_stop" | .health_factor="1.45"
    | .reason="e2e scenario B: HF 1.45 below emergency threshold 1.6 (synthetic)"
    | .last_update=(now | strftime("%Y-%m-%dT%H:%M:%SZ"))' \
    /tmp/state.before.json > /tmp/state.after.json

cat /tmp/state.after.json | docker compose -f docker-compose.staging.yml exec -T backend-blue \
  sh -c 'cat > /var/run/ultra/state.json.new && mv /var/run/ultra/state.json.new /var/run/ultra/state.json'

# Step 3: backend restart で _restore_emergency_state() を発火
docker compose -f docker-compose.staging.yml restart backend-blue

# Step 4: 起動完了を待つ
until curl -sf -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/automation/status > /dev/null; do sleep 2; done

# Step 5: state.json と is_trading_paused を確認
docker compose -f docker-compose.staging.yml exec -T backend-blue \
  cat /var/run/ultra/state.json

# Step 6: ログで復元メッセージを確認
docker compose -f docker-compose.staging.yml logs --tail=120 backend-blue 2>&1 \
  | grep -i "Restored emergency_stop"
```

### 3-4. 期待結果

| ステップ | 期待 |
|---------|------|
| Step 5 | state.json の `emergency_stop=true` / `mode=hard_stop` が維持、`/api/automation/status` で `is_trading_paused=true` |
| Step 6 | `Restored emergency_stop=True from state.json (reason=...)` のログが出力される (`monitoring_service.py:173`) |

### 3-5. 失敗時の調査ポイント

- restart 後 emergency_stop=false になる → `monitoring_service._restore_emergency_state()` の例外ログ (`Failed to restore emergency state from file`)
- state.json が読めない (parse error) → `state_manager.py:76` で fail-closed (`mode=HARD_STOP` の初期値で復帰)
- B-2 経路 (HF を直接記録) が必要な場合 → staging-only inject endpoint の追加を検討

**ログ場所:**
- 起動時の復元ログ: `docker compose logs backend-blue | grep "Restored emergency_stop"`
- state.json parse error: `state_manager.py:76` `"state.json parse error - fail-closed for safety"` で grep

### 3-6. 後始末

シナリオ C で解除する。

---

## 4. シナリオC: 解除フロー (PARTNER 不可・cooldown 含む)

### 4-1. 概要

operator が解除 → HF 回復確認 → ENABLE 経路で復旧。PARTNER は解除不可。

### 4-2. cooldown 仕様の現状

`git grep cooldown backend/app/automation/` を確認した結果、**emergency_stop 専用の cooldown は存在しない**。
関連は以下:

- `AAVE_TRADE_COOLDOWN_SECONDS` (`backend/app/aave/config.py:117`, default=600s) — Aave 操作間隔の throttle。emergency と直交。
- `REBALANCE_COOLDOWN_SECONDS` (`backend/app/aave/rebalance_config.py:154`) — rebalance 間隔。
- 監視ループ間隔: `DEFAULT_MONITORING_INTERVAL_SECONDS=60` (`backend/app/automation/background_tasks.py:27`) — HF を 60s 周期で再評価し、危険域なら再度 HARD_STOP になる。

本テストでは「resume 後 N 秒待って自動再トリガーが起きないこと」(= HF が健康な場合の挙動) を `COOLDOWN_SECONDS` env で待機して確認する (default 30s)。

### 4-3. 前提条件

- emergency_stop が ON の状態 (シナリオ A or B の後)
- ADMIN トークン (PARTNER では解除不可)
- HF が 1.8 以上に回復済み (B-1 経路では state.json を書き換えたままなので、resume 後に
  監視ループが実 HF=1.8+ を取得して上書きする)

### 4-4. 手順 (script: `scenario_c`)

```bash
# Step 1: HF 回復確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/aave/status

# Step 2: PARTNER で解除を試みる (失敗確認)
curl -X POST \
  -H "Authorization: Bearer $STAGING_PARTNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  https://api-staging.ultra-auto-trade.com/api/automation/emergency-stop/resume
# 期待: HTTP 403, "Admin access required"

# Step 3: ADMIN で解除
curl -X POST \
  -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  https://api-staging.ultra-auto-trade.com/api/automation/emergency-stop/resume
# 期待: HTTP 200, .status == "resumed"

# Step 4: 状態確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/automation/status
# 期待: .is_trading_paused == false

# Step 5: state.json 確認
docker compose -f docker-compose.staging.yml exec -T backend-blue \
  cat /var/run/ultra/state.json
# 期待: .emergency_stop == false

# Step 6: cooldown 期間中の挙動確認 (30s 待って二重トリガー無し)
sleep 30
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/automation/status
# 期待: .is_trading_paused == false (HF が健康なら再発動しない)

# Step 7: process-news が正常実行されることを確認
curl -X POST \
  -H "X-Internal-Token: $STAGING_INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  'https://api-staging.ultra-auto-trade.com/automation/process-news?dry_run=true'
# 期待: HTTP 200
```

### 4-5. 期待結果

| ステップ | 期待 |
|---------|------|
| Step 2 | HTTP 403 (PARTNER は `/emergency-stop/resume` 不可) |
| Step 3 | HTTP 200, `.status == "resumed"` |
| Step 4 | `is_trading_paused=false` |
| Step 5 | `emergency_stop=false`, `mode in {normal, safe_mode, hard_stop}` (HF 次第) |
| Step 6 | 30s 後も resumed のまま (HF が 1.6 以上) |
| Step 7 | HTTP 200 で proposal 受理 |

### 4-6. 失敗時の調査ポイント

- PARTNER が解除できてしまう → `automation_dashboard.py:190` が `require_admin` であることを再確認
- ADMIN でも 403 → トークン有効期限、ロール割当 (`auth.models.User.role`)
- 解除後も 503 / HOLD が続く → `clear_emergency_stop()` の OR 条件 (`monitoring_service.py:243` 既存 emergency_stop=True 維持の挙動)。HF が 1.6 未満なら HARD_STOP は維持される (emergency_stop は False)。
- cooldown が効いていない → emergency 専用 cooldown は無い。HF を再確認。

**ログ場所:**
- resume ログ: `docker compose logs backend-blue | grep "Cleared emergency stop"`
- HF 再評価: `grep "HF_BELOW_EMERGENCY\|record_health_factor"` for ongoing checks

### 4-7. 後始末

state.json と Slack 通知 (`✅ 緊急停止が解除されました`) を確認。

---

## 5. シナリオD: state.json 永続 (再起動時)

### 5-1. 概要

emergency_stop=true の状態で backend container を再起動しても状態が維持される。
`_restore_emergency_state()` (`monitoring_service.py:168`) の動作確認。

### 5-2. 前提条件

- emergency_stop を ON にしてから開始 (script では Step 0 で発動)
- staging backend container の `docker compose restart` 権限
- state.json が `ultra-state-staging-new` volume にマウントされていることを確認済み (`docker-compose.staging.yml:167`)

### 5-3. 手順 (script: `scenario_d`)

```bash
# Step 0: 緊急停止発動 (前提)
curl -X POST \
  -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"e2e scenario D precondition"}' \
  https://api-staging.ultra-auto-trade.com/api/automation/emergency-stop

# Step 1: 事前 state.json
docker compose -f docker-compose.staging.yml exec -T backend-blue \
  cat /var/run/ultra/state.json
# 期待: .emergency_stop == true

# Step 2: container 再起動
docker compose -f docker-compose.staging.yml restart backend-blue

# Step 3: 起動完了を待つ
until curl -sf -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/automation/status > /dev/null; do sleep 2; done

# Step 4: 再起動後の state.json
docker compose -f docker-compose.staging.yml exec -T backend-blue \
  cat /var/run/ultra/state.json
# 期待: .emergency_stop == true (維持)

# Step 5: API 経由で確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://api-staging.ultra-auto-trade.com/api/automation/status
# 期待: .is_trading_paused == true

# Step 6: process-news が引き続き全件 skipped
curl -X POST \
  -H "X-Internal-Token: $STAGING_INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  'https://api-staging.ultra-auto-trade.com/automation/process-news?dry_run=true'
# 期待: HTTP 200, octobot_skipped_count == fetched_count

# Step 7: 復元ログ確認
docker compose -f docker-compose.staging.yml logs --tail=120 backend-blue 2>&1 \
  | grep -i "Restored emergency_stop\|state.json"
```

### 5-4. 期待結果

| ステップ | 期待 |
|---------|------|
| Step 4 | state.json が再起動前と同じ内容 (`emergency_stop=true`) |
| Step 5 | `is_trading_paused=true` |
| Step 6 | HTTP 200, 全件 skipped |
| Step 7 | `Restored emergency_stop=True from state.json (reason=...)` のログ (`monitoring_service.py:173`) |

### 5-5. 失敗時の調査ポイント

- state.json が空になる → volume マウント (`ultra-state-staging-new` が backend-blue/green 両方に rw でマウントされているか)
- 内容は残るが flag が効かない → 起動時 `_restore_emergency_state` のログ。例外で fail-open になっていないか
- ログに復元メッセージが出ない → ログレベル、stdout buffering。`compose logs backend-blue` で全件取得して `Restored` で grep

**ログ場所:**
- 復元ログ: `docker compose logs backend-blue 2>&1 | grep -i "Restored emergency_stop"`
- volume 状態: `docker volume inspect ultra-state-staging-new`
- state.json 直接読取: `dc_exec_backend cat /var/run/ultra/state.json` (本スクリプトの `read_state_json` 関数)

### 5-6. 後始末

シナリオ C で解除する。

---

## 6. 実行順序の推奨

```
[A 手動発動] → [C 解除] → 状態リセット
[B HF 自動 (B-1 path)] → [D 再起動] → [C 解除] → 状態リセット
```

A と B は独立。C は A/B の後始末を兼ねる。D は B の後に流すと自然。

スクリプトの `all` モードはこの順序を踏襲する。

---

## 7. production での扱い

- dev 環境から prod へ SSH 不可 (memory: `prod-steps-not-done-until-verified`)
- prod での全シナリオ実行は **運用担当による手動実行** が必須
- 本 doc の手順を運用担当に共有し、実機出力で裏取りを取るまで「完了」と書かない
- prod では特に **シナリオ A の手動発動だけドリル** を四半期に 1 回行うことを推奨 (案・別チケット)

---

## 8. TODO (本 PR 後)

- [ ] B-2 経路 (`_test/inject-hf` admin endpoint) の追加検討 — staging 限定 gating 必須
- [ ] CI への組込検討 (nightly staging E2E、Slack 通知の自動判定)
- [ ] prod 用 runbook 化 (運用担当へ引き渡し)
- [ ] PARTNER ロールで `/api/automation/emergency-stop` (発動) は 200 が返る (Partner+) ことの positive 確認ケース追加
- [ ] Slack 通知の自動 assertion (現状はログ目視)

---

## 9. 参考

- [`docs/33_emergency_stop_governance.md`](../33_emergency_stop_governance.md)
- `backend/app/api/automation_dashboard.py` (主系 endpoint)
- `backend/app/automation/automation_router.py` (legacy / process-news)
- `backend/app/automation/monitoring_service.py`
- `backend/app/aave/state_manager.py` / `backend/app/aave/schemas.py:39`
- `docker-compose.staging.yml` (container 名 / volume / port)
- memory: `disable-scheduler-flag-inverted`
- memory: `prod-steps-not-done-until-verified`
