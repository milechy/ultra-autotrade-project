# 15_rollback_procedures.md
Ultra AutoTrade – ロールバック手順

最終更新: 2026-04-19  
主要変更: OctoBot削除、F-17a反映、Phase 1例外期間対応、OR ロジック emergency stop

---

## 0. 改訂履歴

| 日付 | 変更内容 |
|------|---------|
| 2026-04-19 | 全面改訂。OctoBot廃止対応、F-17aカスタムリミッター追加、OR logic emergency stop反映、Phase 1例外期間の注意事項追加、デプロイフロー刷新（deploy_production.sh基準） |
| 2026-01（旧版） | 初版。Notion→AI→OctoBot→Aaveフロー前提 |

---

## 1. ロールバックの目的

誤作動・暴落・通信障害などで資金損失を防ぐための"即時復旧"手順。

優先順位:
1. 緊急停止フラグを ON にして自動取引を止める（数秒）
2. コードをロールバックする（数分）
3. DBを復元する（最終手段。DB保護ルール参照）

---

## 2. 取引ステップ別ロールバック

### 2.1 情報収集 → AI判定 失敗時

AI判定（`POST /ai/analyze`）が失敗した場合:

- 自動的に `HOLD` 判定に切り替わる（fail-closed 設計）
- Claude API 障害時: GPT-4o クロス検証もタイムアウトし HOLD 維持
- ログ確認: `docker logs ultra-autotrade-backend-staging 2>&1 | grep -i "ai.*error\|claude.*fail"`

### 2.2 AI → Aave 連携 失敗時

`POST /aave/rebalance` エラー発生時:

- deposit / withdraw 実行前に HF を取得し、取得失敗なら **NOOP** で終了
- クライアント例外が発生した場合: `status="error"`, `amount=0` を返す。資金移動は行われない
- 連続エラー時: 緊急停止フラグを手動 ON にして調査

### 2.3 Aave 操作失敗時（/aave/rebalance）

**失敗パターンと対応:**

| パターン | 自動挙動 | 手動対応 |
|---------|---------|---------|
| RPC 断 / レスポンス異常 | NOOP（資金未移動） | RPC URL 疎通確認後 restart |
| HF 取得失敗 | NOOP | Aave ダッシュボードで HF 手動確認 |
| HF < 1.6（strictモード）または HF < 1.3（F-17a カスタムモード） | HARD_STOP 発動 | `clear_emergency_stop()` まで停止維持 |
| Gas 高騰 | 自動キャンセル（fee_calculator.py） | 通常は不要 |

**F-17a カスタムリミッター有効時の注意:**
- CUSTOM_LIMITER_ENABLED=true の期間中は HF 警戒ラインが 1.3 まで緩和（hard floor は 1.2 で変わらない）
- 2026-05-15 以降は自動的に strict モード（HF < 1.6 = HARD_STOP）に戻る
- ロールバック手順: 下記 5. F-17a ロールバック 参照

**運用側での対応:**
1. 緊急停止フラグ ON
2. 必要に応じて Aave ダッシュボードから手動 withdraw
3. 原因調査 → コードロールバック（下記 4. 参照）

---

## 3. 本番環境ロールバック（アプリケーションコード）

### 3.1 基本方針

- **Hetzner は pull-only**。直接 nano / git commit / git merge 禁止
- 正規フロー: ローカル Mac → `git push` → Hetzner で `git pull origin main` → `scripts/deploy_production.sh`
- 参照: `docs/22_production_release_checklist.md`

### 3.2 コードロールバック手順

```bash
# === ローカル Mac で実施 ===

# 1. 巻き戻し先コミットを確認
git log --oneline -10 main

# 2. revert コミットを作成（squash merge 済みなら 1 コミット revert で OK）
git revert <target-commit-sha> --no-edit
git push origin main

# === Hetzner で実施 ===
ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155

cd /opt/ultra-autotrade
git pull origin main

# ロールバック対象: backend のみ
bash scripts/deploy_production.sh --backend-only

# ヘルスチェック
curl -s https://api.ultra-auto-trade.com/health | python3 -m json.tool
```

### 3.3 イメージ再ビルドが必要な変更のロールバック

新しい Python ファイルが追加された変更をロールバックする場合（例: risk_limiter.py）は、
`--backend-only` では不十分なケースがある。その場合:

```bash
# Hetzner で実施
cd /opt/ultra-autotrade

# ① イメージ再ビルド
docker compose -f docker-compose.production.yml --env-file .env.production build backend

# ② コンテナ再起動
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate backend

# ③ 稼働確認
sleep 20
docker ps --filter "name=ultra-autotrade-backend-staging$" --format "{{.Names}}: {{.Status}}"
curl -s https://api.ultra-auto-trade.com/health | python3 -m json.tool
```

### 3.4 フロントエンドのみロールバック

CSSやテキスト修正など API 変更を伴わない場合のみ:

```bash
bash scripts/deploy_production.sh --frontend-only
```

新しい API エンドポイントを参照するフロントエンド変更は **必ずフルデプロイ**（`--frontend-only` 不可）。

---

## 4. バージョン管理ロールバック

### 4.1 通常の revert フロー（推奨）

```bash
# main に revert コミットを積む（force push / reset --hard 禁止）
git revert <sha> --no-edit
git push origin main
```

### 4.2 PR ベースのロールバック

CI を通じて revert を確認したい場合:

```bash
# feature/revert-XXXX ブランチで revert → dev → main PR
git checkout -b feature/revert-f17a main
git revert <sha> --no-edit
git push origin feature/revert-f17a
gh pr create --title "revert: rollback <feature>" --base dev
```

### 4.3 PR #91 以降の CI ガードレールとの連携

PR マージ時に以下が自動実行される:
- `check-env-separation.yml` — .env ファイルの環境分離チェック
- `path-check.yml` — 凍結ファイル変更の承認確認（`docs/integration/backend_deps.md` 更新必須）

緊急時に CI をバイパスする場合: `gh pr merge --admin`（Asana タスクで記録必須）

---

## 5. F-17a カスタムリミッターのロールバック

### 5.1 通常ロールバック（env var 削除のみ）

F-17a は `.env.production` の env var のみで制御。DB に変更なし。

```bash
ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155

cd /opt/ultra-autotrade

# バックアップ確認
ls -la backups/backup_pre_f17a_*.sql backups/RESTORE_COMMAND_f17a_*.md

# .env.production から CUSTOM_LIMITER_* を削除
# （バックアップから復元する方法）
LATEST_BACKUP=$(ls -t .env.production.backup.pre_f17a_* | head -1)
echo "Restoring from: $LATEST_BACKUP"
cp "$LATEST_BACKUP" .env.production

# backend 再起動
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate backend

sleep 20
curl -s https://api.ultra-auto-trade.com/health | python3 -m json.tool
```

### 5.2 実効値確認（ロールバック後）

strict モードに戻っていることを確認:

```bash
docker cp /tmp/check_f17a.py ultra-autotrade-backend-staging:/tmp/check_f17a.py 2>/dev/null || true
docker exec -e PYTHONPATH=/app/backend --workdir /app/backend ultra-autotrade-backend-staging \
  python3 -c "
from app.aave.risk_limiter import get_effective_limits
limits = get_effective_limits()
print(f'is_custom={limits.is_custom}  hf_min={limits.hf_min}  cooldown={limits.cooldown_seconds}')
assert not limits.is_custom, 'ROLLBACK FAILED: still in custom mode'
print('OK: strict mode restored')
"
```

### 5.3 自動失効（ops 不要）

`CUSTOM_LIMITER_EXPIRES_ON=2026-05-15` を過ぎると、`get_effective_limits()` が自動的に strict defaults を返す。
手動ロールバック不要。Slack への WARNING ログが出ることで確認可能。

---

## 6. 本番環境（インフラ視点）でのロールバック手順

### 6.1 コンテナ構成（2026-04-19 時点）

| コンテナ名 | 役割 | 備考 |
|-----------|------|------|
| `ultra-autotrade-backend-staging` | 本番 backend | 命名は `-staging` だが中身は本番（Phase 1 期間中） |
| `ultra-autotrade-frontend-staging` | 本番 frontend | 同上 |
| `ultra-autotrade-postgres-staging` | 本番 PostgreSQL | 本番 DB |
| `ultra-autotrade-cloudflared-staging` | Cloudflare Tunnel | |

compose ファイル: `docker-compose.production.yml`  
env ファイル: `.env.production`

### 6.2 デプロイ前の確認

```bash
cd /opt/ultra-autotrade

# 1. 現在の状態確認
docker ps --format "table {{.Names}}\t{{.Status}}"
git log --oneline -5
curl -s https://api.ultra-auto-trade.com/health | python3 -m json.tool

# 2. env 分離チェック（CI と同じ）
bash scripts/check_env_separation.sh
# ※ Phase 1 例外期間中は APP_ENV=staging 等の違反が既知問題として出る（下記 6.3 参照）
```

### 6.3 Phase 1 例外期間の注意事項（2026-04-19 〜 2026-09-30）

**現時点で `.env.production` に意図的に含まれる staging 値:**

| 変数 | 現在値 | あるべき値 | 許容理由 |
|------|--------|-----------|---------|
| `APP_ENV` | `staging` | `production` | Phase 1 移行期間中の意図的設定 |
| `BYBIT_SANDBOX` | `true` | `false` | テスト段階のため |
| `AAVE_NETWORK` | `base_sepolia` | mainnet 系 | Phase 1 はテストネット運用 |
| `DATABASE_URL` | staging と同値 | 別 DB | Phase 1 は DB 共用 |

`check_env_separation.sh` の違反として検出されるが、**これらは既知・意図的なもの**。
F-17a や他の変更によって新たに追加された違反ではないことを毎回確認すること。

Phase 1 終了（本番フル移行）時に別タスクで修正予定。

### 6.4 コンテナ単体のロールバック（backend のみ）

```bash
# 直前イメージへの切り戻し（git revert 済みの場合）
cd /opt/ultra-autotrade
git pull origin main
docker compose -f docker-compose.production.yml --env-file .env.production build backend
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate backend
```

### 6.5 ロールバックの記録

ロールバック実施時は以下を Asana + Slack に記録:
- 実施日時
- 対象環境と対象コンテナ
- ロールバックしたコミット ID
- 障害概要と影響範囲
- 回復確認コマンドの出力

---

## 7. 緊急停止（Emergency Mode）

詳細: `docs/33_emergency_stop_governance.md`

### 7.1 発火条件（OR ロジック）

緊急停止は以下のいずれか一つでも True になると発動:

| 条件 | 閾値 | 自動/手動 |
|------|------|---------|
| HF 異常 | HF < 1.6（strict）/ HF < 1.3（F-17a カスタム期間中） | 自動（MonitoringService） |
| 価格変動異常 | 24h 変動 > 20% | 自動（StressController） |
| Oracle 異常 | Chainlink 更新停止 / 乖離 10% 超 | 推奨実装（手動昇格） |
| AI API 失敗率 | > 20% | 運用判断（手動） |
| 手動発動 | — | ADMIN/PARTNER ロール |

**OR ロジックの意味**: `emergency_stop=True` OR `circuit_closed=True` のいずれかが True であれば、
自動取引は全停止。`clear_emergency_stop()` を明示的に呼び出すまで True は維持される。

### 7.2 緊急停止の発動

```bash
# API 経由（認証必須）
curl -X POST https://api.ultra-auto-trade.com/api/automation/emergency-stop \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "手動緊急停止: <理由>"}'
```

### 7.3 発動後の確認

```bash
curl -s https://api.ultra-auto-trade.com/health | python3 -m json.tool
# → "status": "degraded" または warnings に emergency_stop 理由が表示される

docker logs ultra-autotrade-backend-staging --tail 50 2>&1 | grep -i "emergency\|HARD_STOP"
```

### 7.4 解除（ADMIN ロールのみ）

```bash
curl -X POST https://api.ultra-auto-trade.com/api/automation/resume \
  -H "Authorization: Bearer <admin-token>"
```

解除前確認チェックリスト:
- [ ] HF が安全圏（strict: > 1.6 / F-17a カスタム期間中: > 1.3）に回復
- [ ] 障害原因が特定・解消済み
- [ ] `/health` が異常なし
- [ ] Slack に解除理由を記録

---

## ⚠️ DB保護ルール（テスター投入後は絶対遵守）

### 禁止事項
- `docker compose down -v` は絶対に使わない（`-v` はボリューム削除 = テスター全データ消失）
- `docker volume rm` は絶対に使わない
- `DROP TABLE` / `TRUNCATE` は絶対に使わない
- `ALTER TABLE DROP COLUMN` は事前にバックアップ取得後のみ

### ロールバック時のDB保護手順
1. バックアップ取得: `bash scripts/backup_db.sh`
2. コード巻き戻し: `git revert <sha>` → `git push origin main`
3. Hetzner: `git pull origin main`
4. イメージ再ビルド + 再起動（上記 3.3 参照）
5. **DB は触らない**（コードだけ戻る）

### DB復元が必要な場合のみ

```bash
# バックアップから復元（F-17a 前バックアップの例）
gunzip -c /opt/ultra-autotrade/backups/backup_pre_f17a_20260419_142646.sql | \
  docker exec -i ultra-autotrade-postgres-staging psql -U ultra -d ultra_autotrade

# 汎用
gunzip -c /opt/ultra-autotrade/backups/<backup-file>.sql.gz | \
  docker exec -i ultra-autotrade-postgres-staging psql -U ultra -d ultra_autotrade
```

### バックアップ一覧確認
```bash
ls -lh /opt/ultra-autotrade/backups/
```

---

## 関連ドキュメント

| ドキュメント | 内容 |
|------------|------|
| `docs/13_security_design.md` | セキュリティ設計（HF 閾値・hard limits・private key 管理） |
| `docs/22_production_release_checklist.md` | 本番デプロイ手順・Hetzner pull-only フロー |
| `docs/33_emergency_stop_governance.md` | 緊急停止の発動権限・条件・OR ロジック詳細 |
| `docs/integration/backend_deps.md` | 凍結ファイル変更申請記録（main.py 等） |
| `backups/RESTORE_COMMAND_f17a_20260419_142646.md` | F-17a 前 DB バックアップのリストア手順 |
