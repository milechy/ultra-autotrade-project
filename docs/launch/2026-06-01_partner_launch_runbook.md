# 6/1 両 partner production launch runbook (v1)

> **対象**: 2026-06-01 (月) の両 partner (山本 id=11 / 橋口 id=18) production launch 当日運用手順
>
> **状態**: SKELETON v1 (Lane M / 2026-05-28 起票)
>
> **正本責務**: 本 runbook は **当日 (D-day) の時系列手順 + 朝チェックリスト + 緊急停止 + Slack 監視 + 14 日カウント起算記録** に絞る。判定基準・条件詳細は別 docs 正本へ link する (重複定義しない)。
>
> **判定基準正本**: [`docs/launch_decision_criteria_v2.md`](../launch_decision_criteria_v2.md) §17 (5 条件) / [`docs/uat_completion_criteria.md`](../uat_completion_criteria.md) (UAT 完走 SQL / 2 partner 体制)
>
> **roadmap**: [`docs/launch/roadmap_to_launch.md`](roadmap_to_launch.md) §1 / §2.1 起算点

---

## 0. メタ情報

| 項目 | 値 |
|---|---|
| D-day | **2026-06-01 (月)** |
| 起算イベント | **partner UAT 14 日連続観察カウント開始** (`docs/launch_decision_criteria_v2.md` §17 条件 4) |
| 対象 partner | 山本さん (id=11 / wallet `0x2064...cc66` 登録済) + 橋口さん (id=18 / wallet 2026-06-01 朝までに登録予定) |
| production URL | frontend: `https://app.ultra-auto-trade.com` / backend: `https://api.ultra-auto-trade.com` |
| Slack 監視 ch | `#ultra-auto-project` (`C0ACS09FMGC`) |
| 担当 | 小林さん (代表 / on-call) — CLAUDE.md §オンコールポリシー (1 人プロジェクト) |
| Lane | M (本 runbook) |
| Tier | **B** (`docs/launch/` 新規 markdown のみ) |

---

## 1. D-1 前日チェック (2026-05-31 21:00 JST までに完了)

> 当日朝に発覚すると遅れる項目を前日のうちに潰す。

### 1.1 partner ユーザー状態 (両者)

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
SELECT id, email, role, is_active, wallet_address, created_at
  FROM users
 WHERE role = 'partner' AND is_active = TRUE
 ORDER BY id;
"
ENDSSH
```

- [ ] 2 行返ってくる (id=11 山本 / id=18 橋口)
- [ ] 両者とも `is_active = TRUE`
- [ ] **山本** `wallet_address` が `0x2064` で始まる
- [ ] **橋口** `wallet_address` が登録済 (NULL でない) — 未登録なら D-day 朝 09:00 までに本人連絡

### 1.2 緊急停止フラグが OFF か

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
  "curl -s http://localhost:8000/api/automation/status | jq '.emergency_stop, .is_trading_allowed'"
```

- [ ] `emergency_stop: false`
- [ ] `is_trading_allowed: true`

OFF でなければ `docs/33_emergency_stop_governance.md` §6 (解除手順) に従う。

### 1.3 launch_decision dashboard 集計 (5 条件まとめ)

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
  "docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
    -t -A -f /opt/ultra-autotrade/scripts/launch_dashboard.sql"
```

- [ ] L1-L6 / chaos / approval_rate / UAT / 森先生 5 条件の現在値を確認、本 runbook §6 「14 日カウント起算記録」に貼付

### 1.4 healthcheck L1-L6 過去 24h

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
  "bash /opt/ultra-autotrade/scripts/l1_l6_daily_summary.sh --since 24h"
```

- [ ] `overall=PASS` が 95% 以上、`daily_total ≥ 240` ラン
- [ ] FAIL があれば内容を Slack `#ultra-auto-project` にスレッド共有

### 1.5 backend / DB / nginx active 状態

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 "docker ps --format 'table {{.Names}}\t{{.Status}}'"
```

確認対象 (`ultra-autotrade-*-production` suffix):
- [ ] `ultra-autotrade-postgres-production` Up
- [ ] `ultra-autotrade-backend-blue-production` または `backend-green-production` のどちらか Up (Blue/Green)
- [ ] `ultra-autotrade-nginx-production` Up
- [ ] `ultra-autotrade-frontend-production` Up
- [ ] cloudflared コンテナ Up

### 1.6 Pushover / Slack 通知の到達確認

```bash
WEBHOOK=$(ssh ultra@77.42.46.155 "grep SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production | cut -d= -f2-")
curl -s -X POST "$WEBHOOK" -H "Content-Type: application/json" \
  -d '{"text": "🧪 D-1 通知到達確認 (6/1 launch runbook)"}'
```

- [ ] Slack `#ultra-auto-project` に通知が届く
- [ ] Pushover にも届く (admin Push 設定済の場合)

### 1.7 Frozen window 宣言 (Tier S 編集禁止)

- [ ] **2026-05-31 21:00 JST 〜 2026-06-01 22:00 JST は Tier S ファイルへの PR merge 禁止** (CLAUDE.md §並列開発フロー v4 鉄則 5 / 凍結期限)
- [ ] Slack `#ultra-auto-project` に「6/1 launch frozen window 開始」を pin

---

## 2. D-day 朝チェックリスト (2026-06-01 08:30〜09:30 JST)

> Step 順序固定。前 Step が PASS してから次 Step に進む。

### Step A. 環境疎通 (08:30〜08:45)

#### A-1. frontend 到達

```bash
curl -sI https://app.ultra-auto-trade.com | head -1
# 期待: HTTP/2 200 (cloudflared)
```

- [ ] 200 OK

#### A-2. backend `/health` (cloudflared 経由)

```bash
curl -s https://api.ultra-auto-trade.com/health | jq .
```

- [ ] `status: "ok"` 相当

#### A-3. backend `/health` (内部直接)

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
  "curl -s http://localhost:8000/health"
```

- [ ] 200

#### A-4. `REBALANCE_SHADOW_MODE` 現状値確認 (切替前 baseline)

> 2026-05-28 以降、production は scheduler 稼働 + 実 tx 停止の safety valve として `REBALANCE_SHADOW_MODE=true` に戻している。
> 6/1 運用開始時に **§3.0 で `false` に切替** しないと実 tx が走らない。本 Step では切替前の現状値を記録するだけ。
>
> 定義元: `docker-compose.production.yml` L143 (blue) / L195 (green) の `environment:` 直書き (`.env.production` ではない)。

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
docker exec ultra-autotrade-backend-blue-production printenv 2>/dev/null | grep REBALANCE_SHADOW_MODE || echo 'blue not running'
docker exec ultra-autotrade-backend-green-production printenv 2>/dev/null | grep REBALANCE_SHADOW_MODE || echo 'green not running'
grep -nE "REBALANCE_SHADOW_MODE" /opt/ultra-autotrade/docker-compose.production.yml
ENDSSH
```

- [ ] active backend (blue または green) の値を記録 (期待値: `REBALANCE_SHADOW_MODE=true`)
- [ ] `docker-compose.production.yml` L143 / L195 の値も記録
- [ ] **`true` のまま §3 launch 宣言してはならない** — §3.0 で必ず `false` に切替

### Step B. 両 partner login (08:45〜09:00)

> partner 本人ではなく **小林さんが代理で確認** する。partner 本人 login 確認は 09:00 以降に partner 自身で実施。

#### B-1. 山本さん login 動線確認

1. `https://app.ultra-auto-trade.com/auth/login` を opens
2. 山本さんの招待 / 登録 link が有効
3. login 後 `/partner/dashboard` (App Router route group: `(partner)/partner/dashboard`) が 200 で表示される

- [ ] login → dashboard 遷移 OK

#### B-2. 橋口さん login 動線確認

同上 (橋口さん招待 link)。

- [ ] login → dashboard 遷移 OK

> 注意 (CLAUDE.md §Next.js App Router route group): URL は **`/partner/dashboard`** (`(partner)` は URL に含まれない)。E2E spec で `/admin/...` 等の route group 誤りに注意。

### Step C. wallet 残高確認 (09:00〜09:15)

> partner 自身に画面で表示される wallet 残高 (USDC / WETH 等) を確認。実際の金額は partner と事前合意のもの。

#### C-1. 山本さん wallet 残高 (Base mainnet)

```bash
# basescan.org で確認
open "https://basescan.org/address/0x2064...cc66"
```

または backend 側 API:

```bash
curl -s https://api.ultra-auto-trade.com/api/partner/wallet/balance \
  -H "Authorization: Bearer <SESSION_TOKEN>" | jq .
```

- [ ] USDC / WETH 残高が partner 合意の初期 deposit と一致
- [ ] Health Factor が **1.6 以上** (HF < 1.6 は HARD_STOP 発動)

#### C-2. 橋口さん wallet 残高

同上 (橋口さん wallet)。

- [ ] USDC / WETH 残高が partner 合意の初期 deposit と一致
- [ ] Health Factor が **1.6 以上**

### Step D. proposals 生成テスト (09:15〜09:30)

> 「production 稼働中に proposals が新規生成される」ことを実機確認する。

#### D-1. 直近 24h proposals 件数

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
SELECT u.id, u.email,
       COUNT(p.id) AS proposals_24h,
       MAX(p.created_at) AS last_proposal_at
  FROM users u
  LEFT JOIN proposals p
    ON p.user_id = u.id
   AND p.created_at > NOW() - INTERVAL '24 hours'
 WHERE u.role = 'partner' AND u.is_active = TRUE
 GROUP BY u.id, u.email
 ORDER BY u.id;
"
ENDSSH
```

- [ ] 両 partner で `last_proposal_at` が直近 24h 以内、または process_news_loop が直近 1h 内に走った形跡あり

#### D-2. ai_decisions 直近 24h

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
SELECT final_action, COUNT(*)
  FROM ai_decisions
 WHERE created_at > NOW() - INTERVAL '24 hours'
 GROUP BY final_action
 ORDER BY final_action;
"
ENDSSH
```

- [ ] HOLD / BUY / SELL の分布が出る (全て HOLD なら HOLD bias 残存 → §5 緊急停止判断要)
- [ ] `final_action='HOLD'` 100% の場合は CLAUDE.md §2026-05-19 教訓 / PR #302 確認後、partner に通知

---

## 3. D-day Launch 宣言 (10:00 JST)

朝チェックリスト Step A〜D 全 PASS 後、以下を実施。

### 3.0 `REBALANCE_SHADOW_MODE` 切替 (`true` → `false`) ⚠️ Tier S 本番操作

> **CLAUDE.md §13 3 段プロトコル準拠**。実 tx を解放する最終ゲート。partner 通知 (§3.1) の **直前** に実施。
>
> 背景: 2026-05-28 に scheduler は稼働させつつ実 tx を止める safety valve として `REBALANCE_SHADOW_MODE=true` に戻している。6/1 運用開始時に `false` に戻さないと実 tx が走らない。
>
> 定義元: `docker-compose.production.yml` L143 (blue) / L195 (green) の `environment:` 直書き (`.env.production` **ではない**)。
>
> **`sed -i` 禁止** (`.claude/CLAUDE.md` ファイル編集ルール / 前行連結バグ防止) — `awk + tmpfile + mv` を使う。
>
> **§3 3 段プロトコル適用**: ① 本 §3.0 に基づき小林さんが手順を読み上げ → ② 実機 1 行ずつ実行 + 各 step 結果を Slack `#ultra-auto-project` thread に貼る → ③ §3.0.5 記録欄を埋めて commit。

#### 3.0.1 切替前 backup + md5 記録

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
cd /opt/ultra-autotrade
TS=$(date +%Y%m%d-%H%M%S)
cp docker-compose.production.yml docker-compose.production.yml.bak-${TS}
md5sum docker-compose.production.yml docker-compose.production.yml.bak-${TS}
grep -nE "REBALANCE_SHADOW_MODE" docker-compose.production.yml
ENDSSH
```

- [ ] backup ファイル名 (`docker-compose.production.yml.bak-YYYYMMDD-HHMMSS`) を §3.0.5 にメモ
- [ ] 切替前 md5sum を §3.0.5 にメモ (rollback 時の照合用)
- [ ] L143 / L195 の両方が `"true"` であることを確認 (L番号は yml 編集で前後する可能性あり、行番号より値で判定)

#### 3.0.2 `awk + tmpfile + mv` で `"true"` → `"false"` 置換 (blue + green 両方)

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
cd /opt/ultra-autotrade
awk '/REBALANCE_SHADOW_MODE/ { gsub(/"true"/, "\"false\""); print; next } { print }' \
  docker-compose.production.yml > /tmp/docker-compose.production.yml.new
mv /tmp/docker-compose.production.yml.new docker-compose.production.yml
echo "--- after replace ---"
grep -nE "REBALANCE_SHADOW_MODE" docker-compose.production.yml
echo "--- diff against backup (REBALANCE_SHADOW_MODE 行のみ変化していることを確認) ---"
diff docker-compose.production.yml.bak-* docker-compose.production.yml | head -20
md5sum docker-compose.production.yml
ENDSSH
```

- [ ] L143 / L195 (相当行) の両方が `"false"` に変わっていることを確認
- [ ] `diff` 出力が REBALANCE_SHADOW_MODE 行 2 件のみ (他行への副作用ゼロ)
- [ ] 切替後 md5sum を §3.0.5 にメモ

#### 3.0.3 blue / green コンテナを force-recreate

> `docker compose restart` は `environment:` の再読み込みが効かない場合がある (CLAUDE.lessons.md 2026-04-01 教訓)。`up -d --force-recreate --no-deps` を使う。

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
cd /opt/ultra-autotrade
docker compose -f docker-compose.production.yml up -d --force-recreate --no-deps backend-blue backend-green
sleep 15
docker ps --filter name=ultra-autotrade-backend --format 'table {{.Names}}\t{{.Status}}'
ENDSSH
```

- [ ] blue / green 両方が `Up X seconds (healthy)` になるまで待つ (15-30 秒)
- [ ] active backend (nginx upstream が向いている側) の `/health` が 200
- [ ] healthy 表示にならない場合は §5.5 で即時 rollback、原因特定後に再実行

#### 3.0.4 `printenv` で `false` が反映されているか確認

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
docker exec ultra-autotrade-backend-blue-production printenv | grep REBALANCE_SHADOW_MODE
docker exec ultra-autotrade-backend-green-production printenv | grep REBALANCE_SHADOW_MODE
ENDSSH
```

- [ ] blue: `REBALANCE_SHADOW_MODE=false`
- [ ] green: `REBALANCE_SHADOW_MODE=false`
- [ ] **どちらかが `true` のまま** なら force-recreate が効いていない → §5.5 rollback して §3.0.3 から再実行

#### 3.0.5 切替記録 (§6.6 にも貼付)

| 項目 | 値 |
|---|---|
| 切替実施時刻 (JST) | TBD (例: 2026-06-01 09:55) |
| backup ファイル名 | TBD (例: `docker-compose.production.yml.bak-20260601-095512`) |
| 切替前 md5 | TBD |
| 切替後 md5 | TBD |
| blue `printenv` 結果 | TBD (期待: `REBALANCE_SHADOW_MODE=false`) |
| green `printenv` 結果 | TBD (期待: `REBALANCE_SHADOW_MODE=false`) |
| 実施者 | 小林さん |

- [ ] 上記すべて埋めて §6.6 に転記
- [ ] Slack `#ultra-auto-project` に「REBALANCE_SHADOW_MODE: true → false 切替完了 (実 tx 解放)」を投稿

### 3.1 partner 本人通知 (小林さん本人送信)

> CLAUDE.md §10 (claude.ai 文面禁止 / 小林さん本人送信ルール) 遵守。

通知文 (草案 — 必要に応じて小林さん編集):

```
山本さん / 橋口さん

本日 2026-06-01 (月) より Ultra AutoTrade の partner 運用を開始します。

- ご自身の wallet 残高・proposals 生成状況は https://app.ultra-auto-trade.com/partner/dashboard でご確認ください
- 提案承認は wallet 接続後、proposal 画面の「承認」ボタンから
- 不明な点・違和感あれば即 Slack #ultra-auto-project または小林直接連絡

本日から 14 日連続観察 (6/14 まで) で問題なければ正式ローンチ判定とします。
```

- [ ] 山本さんへ送信済
- [ ] 橋口さんへ送信済

### 3.2 Slack `#ultra-auto-project` launch 宣言

```bash
WEBHOOK=$(ssh ultra@77.42.46.155 "grep SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production | cut -d= -f2-")
curl -s -X POST "$WEBHOOK" -H "Content-Type: application/json" -d '{
  "text": "🚀 2026-06-01 両 partner production launch 開始\n- partner: 山本 (id=11) + 橋口 (id=18)\n- 14日連続観察カウント開始 → 完了予定 2026-06-14\n- runbook: docs/launch/2026-06-01_partner_launch_runbook.md\n- 朝チェックリスト: 全 PASS (詳細 thread)"
}'
```

- [ ] Slack 通知送信済

### 3.3 14 日カウント起算日記録

本 runbook §6 「14 日カウント起算記録」セクションに以下を追記:

- 起算日: 2026-06-01 10:00 JST
- 完了予定日: **2026-06-14 23:59 JST** (14 日連続観察完了)
- 起算時の 5 条件状態スナップショット (§1.3 launch_dashboard.sql の出力を貼付)

---

## 4. D-day 監視 (10:00〜22:00 JST)

### 4.1 Slack `#ultra-auto-project` 常時 watch

| 通知種別 | 想定発火元 | 対応 SLA |
|---|---|---|
| `❌` / `⚠️` プレフィックス | scheduled_tasks.py / monitoring_service.py | コアタイム 30 分以内に確認 |
| `🚨 HARD_STOP` | HF < 1.6 自動発動 | **即時** (5 分以内に §5 緊急停止フロー突入) |
| partner 直接連絡 (Slack DM / メール) | 山本 / 橋口 | コアタイム 30 分以内に応答 |
| Pushover High | HF / 緊急停止 | 即時 (寝ていれば起きる) |

### 4.2 1 時間ごとの dashboard 確認 (10:00 / 11:00 / 12:00 ... / 22:00)

```bash
# proposals 増加確認
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
SELECT u.id, u.email,
       COUNT(p.id) FILTER (WHERE p.created_at > NOW() - INTERVAL '1 hour') AS new_1h,
       COUNT(p.id) FILTER (WHERE p.created_at::date = CURRENT_DATE) AS today_total,
       COUNT(p.id) FILTER (WHERE p.status = 'executed' AND p.created_at::date = CURRENT_DATE) AS executed_today
  FROM users u
  LEFT JOIN proposals p ON p.user_id = u.id
 WHERE u.role = 'partner' AND u.is_active = TRUE
 GROUP BY u.id, u.email
 ORDER BY u.id;
"
ENDSSH
```

- [ ] 10:00 値: new_1h=__ / today_total=__ / executed_today=__
- [ ] 11:00 値: ...
- [ ] (以下省略 — 22:00 まで毎時)

### 4.3 HF / wallet drift 監視

```bash
curl -s https://api.ultra-auto-trade.com/api/automation/status | jq '.health_factor, .emergency_stop'
```

- [ ] HF が常時 1.6 以上を維持

---

## 5. 緊急停止判断フロー

> CLAUDE.md §Security Rules / `docs/33_emergency_stop_governance.md` 正本。本セクションは「6/1 当日 small Decision Tree」のみ。

### 5.1 自動発動 (HF < 1.6)

`MonitoringService.record_health_factor()` が自動発動する。**人間操作不要**。

- 1. Slack `🚨 HARD_STOP` 通知が来る
- 2. partner 両者に状況連絡 (小林さん本人 / 5 分以内)
- 3. HF 回復まで自動取引停止のまま
- 4. HF が 1.8 以上に回復してから手動で `clear_emergency_stop` を実行 (admin のみ)

### 5.2 手動発動 (異常検知時)

partner / admin から発動可能。

```bash
# admin として
SESSION_TOKEN=<admin token>
curl -X POST https://api.ultra-auto-trade.com/api/automation/emergency-stop \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "6/1 launch day manual stop: <理由>"}'
```

- [ ] `status: "stopped"` 返却確認
- [ ] Slack `#ultra-auto-project` に通知

### 5.3 解除 (admin のみ可)

```bash
curl -X POST https://api.ultra-auto-trade.com/api/automation/emergency-stop/resume \
  -H "Authorization: Bearer $SESSION_TOKEN"
```

- [ ] HF が 1.8 以上を 30 分維持していることを §1.2 で確認してから実行
- [ ] partner 両者に通知

### 5.4 launch 中止判定 (last resort)

以下の条件のいずれかが朝チェックリスト〜午前中に発生したら **launch 中止 → 6/2 以降に再判定**:

| 中止条件 | 判定 |
|---|---|
| 朝 Step A〜D のいずれかが PASS しない | 即中止 |
| HF < 1.6 が D-day 中に 1 回以上発生 | 中止 + 原因究明 |
| partner どちらかから「やめてほしい」連絡 | 即中止 |
| Slack `#ultra-auto-project` に 30 分以上応答不可な障害発生 | 中止 |
| L2/L4 healthcheck が午前中に 3 回以上 FAIL | 中止 + 14日カウントは延期 |

中止する場合:

1. 緊急停止フラグを ON (§5.2)
2. partner 両者に中止連絡 (小林さん本人)
3. 14 日カウント起算日を 6/2 以降に postpone する旨を §6 に記録
4. Slack `#ultra-auto-project` に中止理由 + 再判定予定日を投稿
5. roadmap §1 条件 4 の起算点を更新

### 5.5 `REBALANCE_SHADOW_MODE` rollback (`false` → `true`) ⚠️ Tier S 本番操作

> §3.0 で切替した `REBALANCE_SHADOW_MODE` を即座に `true` に戻す (実 tx 停止 + scheduler は稼働継続)。
> 緊急停止フラグ ON (§5.2) と組み合わせると二重防御。**手順は §3.0 と同一・置換方向のみ逆**。
> §13 3 段プロトコル準拠 (緊急時も skip しない)。

#### 5.5.1 rollback 実行

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
cd /opt/ultra-autotrade
TS=$(date +%Y%m%d-%H%M%S)
cp docker-compose.production.yml docker-compose.production.yml.bak-rollback-${TS}
md5sum docker-compose.production.yml docker-compose.production.yml.bak-rollback-${TS}

awk '/REBALANCE_SHADOW_MODE/ { gsub(/"false"/, "\"true\""); print; next } { print }' \
  docker-compose.production.yml > /tmp/docker-compose.production.yml.new
mv /tmp/docker-compose.production.yml.new docker-compose.production.yml
grep -nE "REBALANCE_SHADOW_MODE" docker-compose.production.yml

docker compose -f docker-compose.production.yml up -d --force-recreate --no-deps backend-blue backend-green
sleep 15
docker ps --filter name=ultra-autotrade-backend --format 'table {{.Names}}\t{{.Status}}'
docker exec ultra-autotrade-backend-blue-production printenv | grep REBALANCE_SHADOW_MODE
docker exec ultra-autotrade-backend-green-production printenv | grep REBALANCE_SHADOW_MODE
ENDSSH
```

- [ ] blue / green 両方が `REBALANCE_SHADOW_MODE=true` に戻っていることを確認
- [ ] rollback 後 md5 を §6.6 にメモ
- [ ] Slack `#ultra-auto-project` に rollback 理由 + 時刻 + md5 を投稿
- [ ] partner 両者に状況連絡 (小林さん本人送信 / 5 分以内)
- [ ] 14 日カウントは中断 — 再開条件は §5.4 launch 中止判定の再判定ルートを準用

#### 5.5.2 緊急停止フラグも併用する場合

> tx 発生中の取引異常など、shadow mode rollback だけでは間に合わない時は §5.2 を **先に** 実行してから §5.5.1。

1. §5.2 緊急停止 ON (実 tx を強制停止)
2. §5.5.1 shadow=true rollback (scheduler が次サイクルで dry-run になる)
3. 両方反映確認後、原因究明 → 24h 以内に方針判断 (再 launch / launch 中止)

---

## 6. 14 日カウント起算記録 (D-day 実施後に埋める)

> 本 runbook の最重要セクション。**6/1 当日に実際に埋めて commit する**。

### 6.1 起算日

| 項目 | 値 |
|---|---|
| 起算日時 | TBD (例: 2026-06-01 10:00 JST) |
| 完了予定日時 | TBD (例: 2026-06-14 23:59 JST) |
| 起算時の判定 | TBD (例: 全朝チェックリスト PASS / launch 実施) |
| 中止/延期の場合の新起算日 | N/A |

### 6.2 起算時 5 条件スナップショット

`docs/launch_decision_criteria_v2.md` §7 形式で記録。`scripts/launch_dashboard.sql` 出力を貼付:

```text
[6/1 朝 §1.3 で取得した実機出力をここに貼付]
```

### 6.3 起算時 UAT SQL スナップショット (`docs/uat_completion_criteria.md` § 判定 SQL)

```text
[6/1 朝に実機で取得した結果を貼付]
```

### 6.4 14 日連続観察ログ (daily / 6/1〜6/14)

| 日付 | proposals (山本/橋口) | executed (山本/橋口) | HF 最低値 | L1-L6 daily | Slack 異常 | 備考 |
|---|---|---|---|---|---|---|
| 6/1 | / | / | | | | launch 実施 |
| 6/2 | / | / | | | | |
| 6/3 | / | / | | | | |
| 6/4 | / | / | | | | |
| 6/5 | / | / | | | | |
| 6/6 | / | / | | | | |
| 6/7 | / | / | | | | |
| 6/8 | / | / | | | | |
| 6/9 | / | / | | | | |
| 6/10 | / | / | | | | |
| 6/11 | / | / | | | | |
| 6/12 | / | / | | | | |
| 6/13 | / | / | | | | |
| 6/14 | / | / | | | | 完了判定 |

### 6.5 完了判定 (6/14 23:59 JST 以降に実施)

- [ ] `docs/uat_completion_criteria.md` § 完走条件 5 件すべて PASS
- [ ] Slack 異常報告 0 件 (条件 5)
- [ ] basescan.org で代表 tx_hash 1 件を目視確認
- [ ] 両 partner から「継続 OK」明示承認 (DM)
- [ ] Asana 「Partner UAT 完走判定」タスク close
- [ ] roadmap §1 条件 4 を ✅ に更新

### 6.6 `REBALANCE_SHADOW_MODE` 切替記録 (§3.0.5 / §5.5 の転記先)

> §3.0 実施後・§5.5 rollback 実施後にそれぞれ追記。複数回 rollback した場合は行追加。

| 時刻 (JST) | 方向 | backup ファイル名 | 切替前 md5 | 切替後 md5 | blue printenv | green printenv | 実施者 | 備考 |
|---|---|---|---|---|---|---|---|---|
| TBD | true→false (§3.0) | TBD | TBD | TBD | TBD | TBD | 小林さん | launch 宣言直前 |
| (rollback 発生時のみ) | false→true (§5.5) | TBD | TBD | TBD | TBD | TBD | 小林さん | rollback 理由: TBD |

- [ ] §3.0 切替記録を 1 行目に転記
- [ ] §5.5 rollback が発生した場合は 2 行目以降に追記

---

## 7. D-day 終業手順 (22:00 JST)

### 7.1 当日サマリー Slack 投稿

```bash
WEBHOOK=$(ssh ultra@77.42.46.155 "grep SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production | cut -d= -f2-")
curl -s -X POST "$WEBHOOK" -H "Content-Type: application/json" -d '{
  "text": "📊 6/1 launch D-day サマリー\n- HF 最低: __ / 最高: __\n- proposals (山本/橋口): __ / __\n- executed: __ / __\n- 緊急停止発動: 0回 / __回\n- Slack 異常通知: __件\n- 14日カウント残: 13 日\n- 詳細: docs/launch/2026-06-01_partner_launch_runbook.md §6.4"
}'
```

### 7.2 §6.4 daily log の 6/1 行を埋めて commit

```bash
cd /opt/ultra-autotrade/main
git add docs/launch/2026-06-01_partner_launch_runbook.md
git commit -m "docs(launch): 6/1 D-day daily log 記録"
git push origin <branch>
```

### 7.3 翌朝 (6/2) の引継ぎ

- [ ] 6/2 09:00 朝プロトコルで本 runbook §6.4 を update
- [ ] §4.2 dashboard 監視を継続 (毎時 → 4h ごとに緩和可)
- [ ] L1-L6 healthcheck が継続 PASS であることを §1.4 で確認

---

## 8. References

| ファイル | 関連章 |
|---|---|
| `docs/launch_decision_criteria_v2.md` | §17 5 条件 (正本) / §6 dashboard SQL |
| `docs/uat_completion_criteria.md` | UAT 完走 SQL (2 partner 体制) |
| `docs/launch/roadmap_to_launch.md` | §1 5 条件・§2.1 起算点・§4.5 dashboard |
| `docs/l1_l6_evaluation_v1.md` | L1-L6 評価方法 / 14日連続緑定義 |
| `docs/33_emergency_stop_governance.md` | 緊急停止ガバナンス正本 |
| `docs/22_production_release_checklist.md` | production release 共通 checklist |
| `docs/24_partner_test_guide.md` | partner 操作画面 / URL 一覧 |
| `docs/sales/incident_response_for_sales.md` | 障害対応 (営業視点) |
| `CLAUDE.md §Security Rules` | HF < 1.6 / cooldown / OR logic |
| `CLAUDE.md §オンコールポリシー` | 1 人プロジェクト on-call ルール |
| `scripts/launch_dashboard.sql` | 1 コマンド集計 SQL |
| `scripts/l1_l6_daily_summary.sh` | L1-L6 日次集計 |

---

## 9. 改訂履歴

| 日付 | 版 | 変更 | 担当 |
|---|---|---|---|
| 2026-05-28 | v1 | 初版 (Lane M / 6/1 launch runbook skeleton) | Claude Code (dev VPS / Lane M) |
| 2026-06-01 | v1.1 | §6.1〜§6.3 D-day 実機データ埋め | 小林さん (当日) |
| 2026-06-14 | v1.2 | §6.4 daily log 完了 + §6.5 完了判定 | 小林さん |
