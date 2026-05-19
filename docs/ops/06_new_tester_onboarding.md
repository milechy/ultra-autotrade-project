# 新テスター追加チェックリスト

> **docs/ops/06_new_tester_onboarding.md**
> 更新: 2026-05-20
> 関連タスク: GID 1214952534815791

---

## 概要

新しいテスターを追加する際、`fund_allocations` への INSERT を忘れると
AI 判定スケジューラが提案を生成できず、Slack に警告が送信され続ける。
本チェックリストを担当者が全項目チェックしてから「追加完了」と宣言すること。

---

## 前提確認

```bash
# 1. Postgres production コンテナ名を確認
docker ps | grep postgres

# 2. DB ユーザー・DB 名を確認
docker exec ultra-autotrade-postgres-production env | grep POSTGRES
```

---

## Step 1: テスターユーザー登録（registration API 経由）

通常は /auth/register API または partner 紹介リンク (/r/<referral_code>) から自動登録される。

```bash
# 登録済み確認 (email は実際のテスターメールアドレスに置換)
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, email, username, role, tier, execution_policy, is_active
FROM users WHERE email = '<tester_email>';
"
```

**確認ポイント:**
- [ ] `is_active = true`
- [ ] `role = 'viewer'` (テスターは viewer ロール)
- [ ] `execution_policy = 'require_approval'` (提案確認 → 承認フロー)
- [ ] `tier` が `LOWER` / `MIDDLE` / `UPPER` のいずれか (NULL の場合は F-16 マイグレーション後に更新)

---

## Step 2: fund_allocations INSERT（3段プロトコル必須）

> **HUMAN-REVIEW-REQUIRED**: production DB への INSERT は小林さん専権。

### Step 2-1: バックアップ取得

```bash
docker exec ultra-autotrade-postgres-production pg_dump \
  -U ultra -d ultra_autotrade -t fund_allocations \
  > /tmp/fund_allocations_backup_$(date +%Y%m%d_%H%M%S).sql

ls -lh /tmp/fund_allocations_backup_*.sql
```

バックアップファイルが 0 バイトでないことを確認してから次へ進む。

### Step 2-2: partner_id の確認

```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, email, username FROM users WHERE role = 'partner' AND is_active = true;
"
```

### Step 2-3: INSERT 実行

```bash
# 変数を実際の値に置換してから実行
PARTNER_ID=<partner_id>
TESTER_USER_ID=<tester_user_id>
TESTER_NAME="<tester_display_name>"
ALLOCATED_USD=<amount>   # 例: 4600.00

docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
INSERT INTO fund_allocations
  (partner_id, tester_name, tester_user_id, allocated_amount_usd, status, allocated_at)
VALUES
  (${PARTNER_ID}, '${TESTER_NAME}', ${TESTER_USER_ID}, ${ALLOCATED_USD}, 'active', NOW())
RETURNING id, partner_id, tester_user_id, allocated_amount_usd, status, allocated_at;
"
```

### Step 2-4: 検証

```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, partner_id, tester_name, tester_user_id, allocated_amount_usd, status, allocated_at
FROM fund_allocations
WHERE tester_user_id = ${TESTER_USER_ID};
"
```

**確認ポイント:**
- [ ] `status = 'active'`
- [ ] `tester_user_id` が正しいユーザー ID
- [ ] `allocated_amount_usd` が合意した金額（例: 4600.00）
- [ ] バックアップ取得確認済み

---

## Step 3: partner ダッシュボードで表示確認

1. https://app.ultra-auto-trade.com/partner/referral にアクセス
2. 紹介ユーザー一覧に新しいテスターのメール（マスク表示）が出現することを確認

**確認ポイント:**
- [ ] `/partner/referral` でテスターの行が表示される
- [ ] 「取引履歴」リンクをクリックして詳細ページ (`/partner/referral/<id>`) に遷移できる

---

## Step 4: AI 判定スケジューラの提案生成確認

`fund_allocations` INSERT 後、スケジューラの次サイクル（最長 1 時間）で提案が生成される。

### 提案金額の計算式

```
提案金額 = allocated_amount_usd × PROPOSAL_AMOUNT_RATIO (デフォルト 10%)
           ただし MIN $50 〜 MAX $2,000 にクランプ

例: $4,600 × 10% = $460 → $460 (MIN/MAX 範囲内)
    $400 × 10%  = $40  → $50 (MIN $50 にクランプ)
    $25,000 × 10% = $2,500 → $2,000 (MAX $2,000 にクランプ)
```

環境変数（`.env.production`）:
```
PROPOSAL_AMOUNT_RATIO=0.10
PROPOSAL_AMOUNT_MIN_USD=50
PROPOSAL_AMOUNT_MAX_USD=2000
```

### 提案生成確認 SQL

```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, user_id, action, amount_usd, status, created_at
FROM proposals
WHERE user_id = ${TESTER_USER_ID}
ORDER BY created_at DESC LIMIT 5;
"
```

### Slack 通知確認

`fund_allocations` が空のままスケジューラが動くと Slack #ultra-auto-project に以下が届く:

```
⚠️ fund_allocations 未設定
user_id=<id> に active な fund_allocations がありません。
ACTION REQUIRED: production DB に INSERT してください。
提案生成をスキップしました。
```

Insert 後にこの警告が止まれば正常。

**確認ポイント:**
- [ ] スケジューラの次サイクル後、`proposals` テーブルに当該テスターの行が生成される
- [ ] `amount_usd` が期待計算値（例: `$4,600 × 10% = $460`）と一致
- [ ] Slack に「fund_allocations 未設定」警告が届かなくなる

---

## Step 5: Slack 完了通知

全項目完了後、Slack #ultra-auto-project に通知:

```bash
WEBHOOK=$(grep SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production | cut -d= -f2-)
curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"✅ 新テスター追加完了\n- tester_user_id: ${TESTER_USER_ID}\n- allocated_amount_usd: ${ALLOCATED_USD}\n- 期待提案金額: $(echo "${ALLOCATED_USD} * 0.10" | bc) USD\"}"
```

---

## チェックリスト（完了宣言前に全チェック）

```
[ ] Step 1: users テーブルで is_active=true, role=viewer, execution_policy=require_approval 確認
[ ] Step 2: バックアップ取得済み
[ ] Step 2: fund_allocations INSERT 完了 + status=active 確認
[ ] Step 3: /partner/referral でテスター一覧に表示確認
[ ] Step 4: スケジューラ次サイクル後に proposals 生成確認
[ ] Step 4: Slack 警告が止まったことを確認
[ ] Step 5: Slack #ultra-auto-project に完了通知送信
```

---

## トラブルシューティング

### Slack に「fund_allocations 未設定」警告が届き続ける場合

```bash
# active な allocation が存在するか確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, tester_user_id, allocated_amount_usd, status
FROM fund_allocations
WHERE tester_user_id = <user_id> AND status = 'active';
"
# 0 件 → INSERT が失敗しているか tester_user_id が NULL → Step 2 をやり直す
```

### proposals が生成されない場合

```bash
# スケジューラが動いているか確認
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool | grep scheduler

# ai_decisions が 24h 以内に存在するか確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT COUNT(*), MAX(created_at) FROM ai_decisions
WHERE created_at > NOW() - INTERVAL '24 hours';
"
```

---

## 関連ドキュメント

| ドキュメント | 内容 |
|---|---|
| `docs/ops/01_api_endpoints.md` | /partner/referral エンドポイント一覧 |
| `docs/ops/02_db_tables.md` | fund_allocations / proposals スキーマ |
| `docs/ops/03_deploy_procedures.md` | Docker コンテナ名・DB 接続情報 |
| `CLAUDE.md §2026-05-02` | テストデータ投入制限ルール（production DB 3段プロトコル） |
