# soak 後 backend 協調 deploy runbook — #369/#373/#374 + R-6 (2026-05-23)

前提: 本番VPS 77.42.46.155 / /opt/ultra-autotrade / ultra。#367 は既 production 反映済(前段不要)。#369/#373/#374 は merge+pull 済。各ステップ HUMAN-REVIEW STOP。

**★実行ゲート**: soak PASS(5/22 21:19〜5/23 21:19 で ai_decisions の BUY+SELL>=1)。routine リマインド/手動集計で確認。FAIL なら本 runbook を実行せず #365 閾値再検討へ。

## ① pull 確認(merge+pull 済の確認のみ)
```bash
cd /opt/ultra-autotrade && git fetch origin && git log -1 --format='%h %ci %s'
git status -sb     # クリーン & HEAD が #374 merge 以降
```
★STOP

## ② DB 準備(backend 起動前)
### ②-a #369 backfill — 事前確定で「対象行ゼロ=実行不要」(2026-05-22 事前SELECT 確認済)
2026-05-22 の事前 SELECT 結果 = **0 rows**(既存 auto_execute なし。引継ぎ §2「6人全員 require_approval」を実機裏付け)。
→ **backfill UPDATE は対象行ゼロのため実行されない**。#369 migration は「今後の新規行」の DEFAULT 変更(予防措置)のみ。当日は alembic upgrade head を流すだけ。
当日も冒頭で同 SELECT を**再実行して 0件を再確認**(deploy 直前に状態が変わっていないことの確認):
```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "SELECT role,count(*) FROM users WHERE execution_policy='auto_execute' GROUP BY role;"
```
★STOP:
- **0 rows(想定)** → そのまま alembic へ(backfill UPDATE は対象なしで no-op)
- **viewer 以外が出た** → 想定外。STOP → claude.ai 報告(HUMAN-REVIEW)
```bash
cd backend && alembic current && alembic upgrade head --sql | tee /tmp/mig_g7h8.sql
```
★STOP: SQL が「SET DEFAULT 'require_approval'(UPDATE 句はあるが対象0件で no-op)」であること確認
```bash
alembic upgrade head && alembic current   # → g7h8i9j0k1l2 (head)
cd ..
```
### ②-b #374 列追加(冪等)
```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS execution_attempts INTEGER NOT NULL DEFAULT 0;"
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "\d proposals" | grep execution_attempts
```
★STOP: 列存在確認

## ③ R-6: production scheduler 解除(Asana 1215030941151577)
```bash
grep -nE 'DISABLE_AI_JUDGMENT_SCHEDULER|ENABLE_AI_JUDGMENT_SCHEDULER' .env.production
```
★STOP: 止めている実値を確認(DISABLE=1→削除/=0、ENABLE=0→=1/削除)
```bash
awk '{gsub(/^DISABLE_AI_JUDGMENT_SCHEDULER=1$/,"DISABLE_AI_JUDGMENT_SCHEDULER=0")}1' .env.production > /tmp/envp && mv /tmp/envp .env.production
grep -nE 'DISABLE_AI_JUDGMENT_SCHEDULER|ENABLE_AI_JUDGMENT_SCHEDULER' .env.production
```
★STOP: 解除確認

## ④ backend 協調 deploy(#373 修正済 script)
```bash
bash scripts/deploy_production.sh --backend-only
```
★STOP: deploy ログで ACTIVE_BACKEND_COLOR が起動前書込・ヘルス通過を確認

## ⑤ 検証
```bash
curl -sf http://127.0.0.1:8000/health | python3 -m json.tool | grep -iE 'status|scheduler_healthy|warning'
curl -sf http://127.0.0.1:8010/health -o /dev/null -w 'blue %{http_code}\n'; curl -sf http://127.0.0.1:8011/health -o /dev/null -w 'green %{http_code}\n'
docker logs ultra-autotrade-backend-<active>-production  2>&1 | grep -iE 'scheduler|judgment' | tail
docker logs ultra-autotrade-backend-<inactive>-production 2>&1 | grep -iE 'inactive color|scheduler skip' | tail
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "\d proposals" | grep execution_attempts
```
★STOP: scheduler_healthy=true / active のみ判定起動 / inactive は info skip(誤報なし)/ 列存在 → 完了

## ロールバック
- ③: .env.production を戻し backend recreate
- ②-a: `alembic downgrade -1`(既存行不変)/ ②-b: 列は残置(無害)
- ④: deploy_production.sh は旧 active を残す → upstream を旧 slot へ戻す
