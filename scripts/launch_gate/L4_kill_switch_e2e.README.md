# L4 Kill Switch e2e — 実行手順

> §17 Launch Gate L4 拡張版。6/1 partner 並走前のローンチ条件のうち独立して
> 今日確認できる「緊急停止 (kill switch) の 5 項目 e2e 実機検証」を行う。
> dev VPS では構造上実行不可。**iMac から本番 VPS に SSH 後、staging stack に対して実行する。**

---

## 検証項目 (5 項目)

| # | 項目 | 期待結果 |
|---|---|---|
| 1 | `POST /api/automation/emergency-stop` | HTTP 200 / `status=stopped` |
| 2 | 発動後、新規 AI 提案生成が止まる | `ai_decisions` delta=0 / manual trigger `proposals_created=0` |
| 3 | 発動後、workflow.run が skip | `/api/automation/workflow/run` で `emergency_stop` 系応答 |
| 4 | `POST /api/automation/emergency-stop/resume` | HTTP 200 / `status=resumed` + 再開後 AI 判定動く |
| 5 | 発動・解除ログが Slack #ultra-auto-project に出る | backend ログから activate / clear 通知の発火を検出 |

> Test 5 は backend ログから Slack post 試行を検出する仕組み。
> #ultra-auto-project チャネル側でも目視確認することを推奨。

---

## 前提

1. **実行先**: 本番 VPS (`77.42.46.155`) 上、staging stack に対して実行
2. **実行ユーザー**: `ultra@77.42.46.155` (SSH key: `~/.ssh/hetzner_direct`)
3. **必須コマンド**: `bash`, `curl`, `jq`, `docker`
4. **必須コンテナ稼働状態**:
   - `*postgres*staging*` (例: `ultra-autotrade-postgres-staging-new`)
   - `*nginx*staging*`
   - `*backend*staging*` (nginx upstream の active 側)
5. **staging admin user 存在**: `role=admin` の user。未投入なら先に
   `scripts/seed_staging_admin.sh` を実行。

---

## 実行手順 (iMac から)

### 1. credentials を export (1Password 等から)

```bash
# iMac で実行 (本番 VPS に送らず、SSH トンネル先で export)
export ADMIN_EMAIL='hkobayashi@mooores.com'
export ADMIN_PASSWORD='<staging admin password>'  # 1Password から取得
```

> ⚠️ `.bash_history` / `.zsh_history` に password を残さないこと。
> `export ADMIN_PASSWORD=$(security find-generic-password -s ultra-staging -w)` 等を推奨。

### 2. 本番 VPS に SSH (credentials を持ち込んで実行)

```bash
ssh -i ~/.ssh/hetzner_direct -o SendEnv=ADMIN_EMAIL,ADMIN_PASSWORD \
    ultra@77.42.46.155 \
    'cd /opt/ultra-autotrade && bash scripts/launch_gate/L4_kill_switch_e2e.sh'
```

または対話的に:

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155
# (本番 VPS 上で)
read -s -p "ADMIN_PASSWORD: " ADMIN_PASSWORD; echo
export ADMIN_EMAIL='hkobayashi@mooores.com'
export ADMIN_PASSWORD
cd /opt/ultra-autotrade
bash scripts/launch_gate/L4_kill_switch_e2e.sh
```

> ⚠️ `ssh ... -o SendEnv=...` を使う場合、`~/.ssh/config` または
> `/etc/ssh/sshd_config` の `AcceptEnv` が必要。届かない場合は対話実行に切替。

### 3. 期待出力

```
[INFO] POSTGRES_CONTAINER=ultra-autotrade-postgres-staging-new
[INFO] BACKEND_CONTAINER=ultra-autotrade-backend-blue-staging-new
[INFO] BASE_URL=http://127.0.0.1:8082
[INFO] /health env=staging 確認 OK
[INFO] admin JWT 取得 OK
... (各 Test の詳細)
=== L4 Kill Switch e2e Summary ===
  [PASS] 1. emergency-stop POST   HTTP 200 status=stopped
  [PASS] 2. ai_decisions blocked  delta_wait=0 trigger HTTP=200 action=HOLD proposals=0
  [PASS] 3. workflow.run skipped  HTTP=200 ... contains emergency_stop=true
  [PASS] 4. resume + AI restart   resume HTTP=200, trigger HTTP=200 decision_id=...
  [PASS] 5. Slack notify          activate=1 clear=1 slack-related=2 (backend log)
  ---------------------------
  PASS=5  FAIL=0  SKIP=0
  Launch Gate: PASSED
```

`FAIL` が 1 件以上出た場合、exit code は 1。
Asana 起票 → 6/1 までに修正タスク化する。

---

## オプション環境変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `STAGING_BASE_URL` | `http://127.0.0.1:8082` | staging nginx 内部 URL |
| `POSTGRES_CONTAINER` | 自動検出 (`*postgres*staging*`) | staging postgres コンテナ名 |
| `BACKEND_CONTAINER` | 自動検出 (nginx upstream active 側) | staging backend コンテナ名 |
| `DB_USER` | `ultra` | PostgreSQL ユーザー |
| `DB_NAME` | `ultra_autotrade_staging` | staging DB 名 |
| `AI_DELTA_WAIT_SEC` | `5` | ai_decisions delta 観測待ち秒数 |
| `LOG_TAIL_LINES` | `200` | Test 5 で確認する backend ログ行数 |

---

## 安全装置

- dev VPS (`hostname` が `uata-dev*` 等) では即 SKIP し本番 stack を一切叩かない
- 検出した postgres / backend コンテナ名に `staging` を含まない場合は abort
- DB 操作は `SELECT COUNT(*)` のみ。write は一切しない
- 発動した emergency_stop は script 末尾で必ず resume を再送
  (Test 4 が FAIL でも staging を停止状態で放置しない)
- emergency stop の `reason` に `L4-e2e-<timestamp>` を含める → ログ追跡可能

---

## 失敗時の手動復旧

万一 script が途中で死に、staging が `emergency_stop=true` のまま放置された場合:

```bash
# 本番 VPS で (staging stack に対して):
curl -sS -X POST http://127.0.0.1:8082/api/automation/emergency-stop/resume \
  -H "Authorization: Bearer <admin JWT>"

# JWT が無ければ /auth/login で再取得:
curl -sS -X POST http://127.0.0.1:8082/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"'"${ADMIN_EMAIL}"'","password":"'"${ADMIN_PASSWORD}"'"}' \
  | jq -r '.access_token'
```

---

## 関連

- 既存 L4_killswitch.sh (簡易版、1-2 項目のみ): `scripts/launch_gate/L4_killswitch.sh`
- §17 Launch ロードマップ: `docs/launch/roadmap_to_launch.md`
- staging admin 投入: `scripts/seed_staging_admin.sh`
- 関連エンドポイント定義: `backend/app/api/automation_dashboard.py`,
  `backend/app/automation/automation_router.py`
- emergency_stop 配線: `backend/app/automation/monitoring_service.py:activate_emergency_stop`,
  `clear_emergency_stop`
- workflow skip ロジック: `backend/app/automation/workflow.py:331` (`return False, "emergency_stop"`)
