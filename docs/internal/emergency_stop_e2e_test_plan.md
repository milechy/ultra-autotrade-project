# 緊急停止 E2E テスト計画 (P0-4)

**バージョン:** 0.1 (Draft)
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
- staging を想定した curl / psql / docker コマンド
- scheduler フラグ逆転 (memory: `disable-scheduler-flag-inverted`) への注意喚起
- prod は dev から SSH 不可 (memory: `prod-steps-not-done-until-verified`) のため手動実行が必要な旨

本 doc に含まれないもの:
- 実 endpoint の最終 URL (TODO で記載)
- 実機 (staging/prod) 実行ログ
- merge 可否判断 (claude.ai + 小林さんの最終承認に従う)

---

## 1. 共通前提

### 1-1. 環境

| 項目 | staging | production |
|------|---------|-----------|
| backend URL | `https://staging.api.ultra-autotrade.example.com` (TODO 確定) | `https://api.ultra-autotrade.example.com` (TODO 確定) |
| DB | staging Postgres | production Postgres |
| scheduler フラグ | **ENABLED + shadow mode** | **DISABLED** |
| 実行可否 | 本 doc 手順で実行可 | dev から SSH 不可・**手動実行必須** |

### 1-2. ⚠️ scheduler フラグ逆転に関する注意

memory `disable-scheduler-flag-inverted` 参照。

- staging: `DISABLE_SCHEDULER=false` (ON) + `AI_JUDGMENT_SHADOW_MODE=true` で常時動作
- production: `DISABLE_SCHEDULER=true` (OFF) で停止
- soak テスト中にこのフラグを取り違えると `ai_decisions` 0 件で評価不成立になる
- 本 E2E でも staging で scheduler が動いている前提で手順を組む

### 1-3. ⚠️ production 実行の制約

memory `prod-steps-not-done-until-verified` 参照。

- dev 環境から prod へ SSH は不可
- prod でのテストは運用担当が手動で実行する
- 本 doc は staging のみ自動化対象。prod での実機出力で裏取りが取れるまで「完了」と書かない

### 1-4. 必要権限・トークン

- ADMIN ロールの API トークン (発動・解除両方)
- PARTNER ロールの API トークン (発動のみ・解除不可の検証用)
- staging Postgres への直接アクセス (psql)
- staging backend container への docker exec / docker logs 権限

### 1-5. 前提コード参照 (本 PR では変更しない)

- `backend/app/automation/automation_router.py` — `POST /automation/emergency-stop`
- `backend/app/automation/monitoring_service.py` — `activate_emergency_stop()` / `record_health_factor()`
- `backend/state.json` — 永続化先 (デプロイ環境ごとに path 異なる)

---

## 2. シナリオA: 手動発動

### 2-1. 概要

operator が API (将来的には UI) から emergency_stop を ON にする。

### 2-2. 前提条件

- staging backend が正常稼働
- `is_trading_paused=false` (停止していない状態から開始)
- 進行中の tx がなければベスト (あっても完走するはず)
- ADMIN トークンを取得済み

### 2-3. 手順

```bash
# Step 1: 事前状態確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/automation/status
# 期待: is_trading_paused=false

# Step 2: 緊急停止発動
curl -X POST \
  -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"e2e scenario A manual"}' \
  https://staging.api.ultra-autotrade.example.com/automation/emergency-stop

# Step 3: 発動後の状態確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/automation/status

# Step 4: state.json 確認
docker exec <staging-backend-container> cat /app/backend/state.json

# Step 5: 新規 proposal を投げて 503 を確認
curl -X POST \
  -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"test news"}' \
  https://staging.api.ultra-autotrade.example.com/automation/process-news

# Step 6: ai_decisions テーブルで reject が記録されているか確認
psql $STAGING_DB_URL -c \
  "SELECT id, decision, created_at FROM ai_decisions ORDER BY created_at DESC LIMIT 5;"
```

### 2-4. 期待結果

| ステップ | 期待 |
|---------|------|
| Step 2 | HTTP 200, `{"status":"stopped",...}` |
| Step 3 | `is_trading_paused=true`, `mode=HARD_STOP` |
| Step 4 | `emergency_stop=true`, `reason` に "Manual emergency stop by user" |
| Step 5 | HTTP 503 |
| Step 6 | 該当 proposal が `decision=reject` または同等で記録 |

### 2-5. 失敗時の調査ポイント

- HTTP 200 が返らない → トークン権限、CSRF、router 登録 (`automation_router.py`)
- state.json が更新されない → `MonitoringService.activate_emergency_stop()` のログ
- 503 が返らない → `is_trading_allowed()` の呼び出し点 (`backend/app/automation/router.py` 周辺)
- ai_decisions に何も記録されない → scheduler フラグ逆転を疑う (memory 参照)

### 2-6. 後始末

シナリオ C を続けて実行するか、ADMIN 経由で resume を呼ぶこと。

---

## 3. シナリオB: HF < 1.6 で自動発動

### 3-1. 概要

HealthFactor 監視が 1.6 を切ったタイミングで emergency_stop が自動 ON になる。

### 3-2. 前提条件

- staging backend が正常稼働
- emergency_stop は OFF からスタート
- HF を意図的に下げる手段がある (テスト用 mock endpoint or staging Aave fork)
- `MonitoringService.record_health_factor()` が呼ばれる経路が活きている

### 3-3. 手順

```bash
# Step 1: 事前 HF と emergency_stop 状態の確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/aave/status
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/automation/status

# Step 2: HF を 1.6 未満に下げる
# TODO: staging で HF を下げる手段を確定する
#   案 A: Aave testnet で borrow を増やす
#   案 B: mock endpoint で `record_health_factor(1.45)` を直接呼ぶ
#   案 C: staging 専用の admin endpoint (要追加実装)

# Step 3: 発動を待つ (監視周期 = 5〜30 秒想定、TODO で確定)
sleep 30

# Step 4: state.json と Slack 通知確認
docker exec <staging-backend-container> cat /app/backend/state.json
# staging Slack #alerts-staging チャンネルを目視確認

# Step 5: ログ確認
docker logs <staging-backend-container> 2>&1 | grep -i "emergency" | tail -20
```

### 3-4. 期待結果

| ステップ | 期待 |
|---------|------|
| Step 4 | `emergency_stop=true`, `health_factor` が 1.6 未満の値, `reason` に "health factor X.XX below emergency threshold 1.6" |
| Step 4 | Slack に `🚨 緊急停止が発動されました` が投稿 (severity=EMERGENCY) |
| Step 5 | ログに `EMERGENCY: Emergency stop activated: health factor ...` |

### 3-5. 失敗時の調査ポイント

- HF を下げてもフラグが立たない → 監視周期、`record_health_factor()` 呼び出しタイミング
- 立つが Slack が来ない → `CompositeNotificationService` の設定、Slack token
- ログに何も出ない → ログレベル、stdout buffering

### 3-6. 後始末

シナリオ C で解除する。

---

## 4. シナリオC: 解除フロー (cooldown 含む)

### 4-1. 概要

operator が解除 → HF 回復確認 → ENABLE 経路で復旧。cooldown 期間中の再発動防止を含む。

### 4-2. 前提条件

- emergency_stop が ON の状態 (シナリオ A or B の後)
- ADMIN トークン (PARTNER では解除不可)
- HF が 1.8 以上に回復済み

### 4-3. 手順

```bash
# Step 1: HF 回復確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/aave/status
# 期待: health_factor >= 1.8

# Step 2: PARTNER で解除を試みる (失敗確認)
curl -X POST \
  -H "Authorization: Bearer $STAGING_PARTNER_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/automation/emergency-stop/resume
# 期待: HTTP 403

# Step 3: ADMIN で解除
curl -X POST \
  -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/automation/emergency-stop/resume

# Step 4: 状態確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/automation/status

# Step 5: state.json 確認
docker exec <staging-backend-container> cat /app/backend/state.json

# Step 6: cooldown 期間中の挙動確認 (実装ある場合)
# TODO: cooldown 仕様の確定後に手順詳細化
# 期待: 解除直後でも自動取引は ENABLE するが、N 分間は再発動閾値が緩い

# Step 7: 自動取引の再開確認
curl -X POST \
  -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"test news after resume"}' \
  https://staging.api.ultra-autotrade.example.com/automation/process-news
# 期待: HTTP 200, 503 ではない
```

### 4-4. 期待結果

| ステップ | 期待 |
|---------|------|
| Step 2 | HTTP 403 (PARTNER は解除不可) |
| Step 3 | HTTP 200 |
| Step 4 | `is_trading_paused=false` |
| Step 5 | `emergency_stop=false`, `mode!=HARD_STOP` |
| Step 7 | HTTP 200 で proposal 受理 |

### 4-5. 失敗時の調査ポイント

- PARTNER が解除できてしまう → ロール制御 (`require_admin`)
- ADMIN でも 403 → トークン有効期限、ロール割当
- 解除後も 503 → `clear_emergency_stop()` の OR 条件、別フラグが残っている
- cooldown が効いていない → 仕様未実装の可能性

### 4-6. 後始末

state.json と Slack 通知 (`✅ 緊急停止が解除されました`) を確認。

---

## 5. シナリオD: state.json 永続 (再起動時)

### 5-1. 概要

emergency_stop=true の状態で backend container を再起動しても状態が維持される。

### 5-2. 前提条件

- emergency_stop が ON の状態 (シナリオ A or B の後)
- staging backend container の再起動権限
- state.json が永続 volume にマウントされていることを確認済み

### 5-3. 手順

```bash
# Step 1: 事前確認
docker exec <staging-backend-container> cat /app/backend/state.json
# 期待: emergency_stop=true

# Step 2: container 再起動
docker restart <staging-backend-container>

# Step 3: 起動完了を待つ
sleep 20
until curl -sf https://staging.api.ultra-autotrade.example.com/health > /dev/null; do
  sleep 2
done

# Step 4: 再起動後の state.json 確認
docker exec <staging-backend-container> cat /app/backend/state.json
# 期待: emergency_stop=true が維持されている

# Step 5: API 経由で状態確認
curl -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  https://staging.api.ultra-autotrade.example.com/automation/status
# 期待: is_trading_paused=true

# Step 6: 新規 proposal が 503 になることを確認
curl -X POST \
  -H "Authorization: Bearer $STAGING_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"test news after restart"}' \
  https://staging.api.ultra-autotrade.example.com/automation/process-news
# 期待: HTTP 503

# Step 7: ログで復元メッセージを確認
docker logs <staging-backend-container> 2>&1 | grep -i "state.json\|emergency_stop" | head -20
```

### 5-4. 期待結果

| ステップ | 期待 |
|---------|------|
| Step 4 | state.json が再起動前と同じ内容 |
| Step 5 | `is_trading_paused=true` |
| Step 6 | HTTP 503 |
| Step 7 | 起動時に state.json から復元したログが出力 |

### 5-5. 失敗時の調査ポイント

- state.json が空になる → volume マウント、permission
- 内容は残るが flag が効かない → 起動時 load ロジック
- ログに復元メッセージが出ない → ログレベル

### 5-6. 後始末

シナリオ C で解除する。

---

## 6. 実行順序の推奨

```
[A 手動発動] → [C 解除] → 状態リセット
[B HF 自動] → [D 再起動] → [C 解除] → 状態リセット
```

A と B は独立。C は A/B の後始末を兼ねる。D は B の後に流すと自然。

---

## 7. production での扱い

- dev 環境から prod へ SSH 不可 (memory: `prod-steps-not-done-until-verified`)
- prod での全シナリオ実行は **運用担当による手動実行** が必須
- 本 doc の手順を運用担当に共有し、実機出力で裏取りを取るまで「完了」と書かない
- prod では特に **シナリオ A の手動発動だけドリル** を四半期に 1 回行うことを推奨 (案・別チケット)

---

## 8. TODO (本 PR 後)

- [ ] staging backend URL の確定
- [ ] HF を staging で意図的に下げる手段の確定 (案 A/B/C のいずれか)
- [ ] cooldown 仕様の確定と手順反映
- [ ] `scripts/test_emergency_stop_e2e.sh` の実 endpoint 埋め
- [ ] CI への組込検討 (nightly staging E2E)
- [ ] prod 用 runbook 化 (運用担当へ引き渡し)

---

## 9. 参考

- [`docs/33_emergency_stop_governance.md`](../33_emergency_stop_governance.md)
- `backend/app/automation/automation_router.py`
- `backend/app/automation/monitoring_service.py`
- memory: `disable-scheduler-flag-inverted`
- memory: `prod-steps-not-done-until-verified`
