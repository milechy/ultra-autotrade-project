# Chaos Test 3 日連続実行 plan (5/29-31)

> ローンチ条件 2 (staging で chaos test 3 日連続失敗ゼロ) の **計画 doc**。
> 本日 (2026-05-28) は plan + script のみ準備し、**実 chaos 実行は #436 soak 判定後**。
> Lane L (chaos test 計画 + スクリプト準備) アウトプット。

---

## 1. 目的

`docs/launch_decision_criteria_v2.md` §2 / `docs/launch/roadmap_to_launch.md` §1 条件 2 の達成。

**staging 環境のコンテナ (Loki / postgres / backend / nginx / frontend) を意図的に kill し、
3 日連続で以下 4 軸を全てクリアすることを実証する。**

| 軸 | PASS 判定基準 | 検証手段 |
|---|---|---|
| ① 自動再起動 | kill 後 **5 分以内**に container が `running` 復帰 | `chaos_test_staging.sh` の `_wait_for_recovery` |
| ② health 復活 | 再起動後 **2 分以内**に `/health` 200 | `chaos_test_staging.sh` の `_check_health` |
| ③ ライフサイクル記録 | Loki に `Exited` + `Started` イベント記録 | `chaos_test_3day_runner.sh` の `_grep_docker_events_in_window` + Loki /ready |
| ④ ai_decisions 継続 | chaos 前後で `ai_decisions` 件数 0 件減少なし、かつ post > 0 | `chaos_test_3day_runner.sh` の `_query_ai_decisions_count_last_30min` |

---

## 2. 実行スケジュール

| Day | 日付 (JST) | 担当 | 実行コマンド | 結果ファイル |
|---|---|---|---|---|
| Day 1 | 2026-05-29 (金) 14:00 JST | claude.ai 指示 + 小林さん実行 | `bash scripts/chaos_test_3day_runner.sh` | `docs/launch/chaos_test_results/2026-05-29_run1.md` |
| Day 2 | 2026-05-30 (土) 14:00 JST | 同上 | `RUN_INDEX=2 bash scripts/chaos_test_3day_runner.sh` | `docs/launch/chaos_test_results/2026-05-30_run2.md` |
| Day 3 | 2026-05-31 (日) 14:00 JST | 同上 | `RUN_INDEX=3 bash scripts/chaos_test_3day_runner.sh` | `docs/launch/chaos_test_results/2026-05-31_run3.md` |

> **前提**: PR #436 (soak/SUPPLY) 判定が **PASS** であること。FAIL の場合は本 plan を後ろ倒し。
> Asana 親タスクで #436 判定結果と本 plan の go/no-go を紐付ける。

### 時刻選定理由

- **14:00 JST**: 山本さん / 橋口さん の UAT 時間帯 (主に夜) と被らないよう昼に実施。
- **30 分窓**: ai_decisions の継続生成判定 (条件④) は scheduled_tasks の interval に依存するため、chaos 前 30 分窓と post 30 分窓を比較する仕様。
- **間隔 24h**: 3 連続日に分けることで「flaky 1 日緑」ではなく「再現性のある緑」を担保。

---

## 3. 実行手順

### Pre-check (実行 30 分前)

```bash
# 本番 Hetzner VPS で実行 (staging compose が同居)
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155

cd /opt/ultra-autotrade

# 1. staging 全コンテナが Up であること
docker compose -f docker-compose.staging.yml ps

# 2. /health が 200 であること
curl -fsS -o /dev/null -w "[%{http_code}]\n" http://127.0.0.1:8082/health

# 3. ai_decisions が直近 30 分で生成されていること (条件 ④ baseline)
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade_staging -c \
  "SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '30 minutes';"
```

### 本実行 (Day N、N=1/2/3)

```bash
# 本番 Hetzner VPS で実行
RUN_INDEX=N bash /opt/ultra-autotrade/scripts/chaos_test_3day_runner.sh
```

スクリプトが自動で:
1. 既存 `chaos_test_staging.sh` を呼んで全 staging コンテナを順次 kill + 復旧待機
2. chaos 前後の ai_decisions 件数比較 (条件 ④)
3. docker events で staging-new コンテナの die/start を取得 (条件 ③)
4. 結果を `docs/launch/chaos_test_results/YYYY-MM-DD_runN.md` に Markdown で書き出し
5. Slack `#ultra-auto-project` に開始/終了通知

### Post-check (実行 10 分後)

```bash
# 1. 結果ファイル確認
cat /opt/ultra-autotrade/docs/launch/chaos_test_results/$(date '+%Y-%m-%d')_runN.md

# 2. staging 全コンテナが復帰していること
docker compose -f docker-compose.staging.yml ps

# 3. /health 200 持続
curl -fsS -o /dev/null -w "[%{http_code}]\n" http://127.0.0.1:8082/health

# 4. Slack 通知が来ていること
```

---

## 4. 期待 safe-degrade 挙動 (kill 対象別)

| kill 対象コンテナ | 期待挙動 | NG パターン |
|---|---|---|
| `ultra-autotrade-loki-staging-new` | promtail はバッファ continuing、loki 復帰後にログ転送再開 | json-file 未設定で他サービスが道連れ落ち (P0-2 2026-05-21 教訓再発) |
| `ultra-autotrade-postgres-staging-new` | backend が接続エラー → retry → DB 復帰後に自然回復 | backend が exit して上がってこない / scheduled_tasks 停止 |
| `ultra-autotrade-backend-blue-staging-new` | nginx upstream が green を引き続き使用 (ゼロダウンタイム想定) | nginx 502 / green が同時 down |
| `ultra-autotrade-backend-green-staging-new` | nginx upstream が blue を引き続き使用 | 同上 |
| `ultra-autotrade-nginx-staging-new` | restart: always で 1 分以内復帰 | upstream IP 固着 (PR #338 RCA 教訓) |
| `ultra-autotrade-frontend-staging-new` | UI 一時 503 → restart: always で復帰 | OOM Loop |

---

## 5. FAIL 時の対応

1. **Day 1 FAIL** → 真因確定 (compose / restart policy / healthcheck / scheduled_tasks ログ) してから rerun。3 日 streak は **Day 1 から再カウント**。
2. **Day 2 FAIL** → 同上、Day 1 から再カウント。
3. **Day 3 FAIL** → 同上。
4. **3 軸 (①②③) PASS だが ④ ai_decisions FAIL** → scheduled_tasks の interval / cognitive_state injection を疑う。`backend/app/automation/scheduled_tasks.py` のログを確認するが、ファイル変更は別 PR (Tier S)。

---

## 6. Asana 連携

| Asana タスク | 内容 |
|---|---|
| 親タスク (本 plan のハブ) | 「chaos test 3 日連続実行 (5/29-31) — 条件 2 達成」 |
| サブ Day 1 | 「Day 1 chaos test 実行 + 結果記録 (2026-05-29)」 |
| サブ Day 2 | 「Day 2 chaos test 実行 + 結果記録 (2026-05-30)」 |
| サブ Day 3 | 「Day 3 chaos test 実行 + 結果記録 (2026-05-31)」 |

各サブタスクの notes に:
- 実行コマンド
- 結果ファイルパス
- Slack 通知 timestamp
- PASS/FAIL 4 軸判定

を貼り戻す。

---

## 7. 参照

- `scripts/chaos_test_staging.sh` — 既存 kill スクリプト (PR #253 merge 済 + 後続改修済)
- `scripts/chaos_test_3day_runner.sh` — 本 Lane L で新規追加された 3 日連続 wrapper
- `docs/launch/chaos_test_results/` — 実行結果ファイル格納先
- `docs/launch_decision_criteria_v2.md` §2 — 条件 2 詳細仕様
- `docs/launch/roadmap_to_launch.md` §1 条件 2 — ローンチ条件本文
- `docs/launch/lanes/lane1_chaos_test.md` — 過去の Lane 1 設計 (API outage 系、本 plan とは別物)
- `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` — nginx upstream 固着 RCA
- 2026-05-21 P0-2 loki cascade postmortem — json-file 移行教訓

---

*Lane L 2026-05-28 起票 / chaos 実行は #436 soak 判定後 (go/no-go は親 Asana で管理)*
