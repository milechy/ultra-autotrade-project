# users.risk_mode マイグレーションプラン (F-3)

> 最終更新: 2026-04-25
> 関連: `docs/45_fee_model_v10_migration_plan.md` §1.3 / §4 F-3 行
> Asana: F-3 (1214120401362419)
> 実行タイミング: **F-16 本番リリース時** (本ドキュメントは設計のみ。F-3 では実行しない)
> F-2 (`docs/46`) と同じパターン

---

## 0. 前提

### 本番 DB 現状 (2026-04-25 read-only 調査)

| 項目 | 値 |
|------|-----|
| `users.risk_mode` 値分布 | conservative × 2、NULL × 4 |
| `users.risk_mode` 列型 | `VARCHAR(20)`, `NULL 許可`, `DEFAULT NULL` |

### 既存 6 ユーザー snapshot

| id | username | role | risk_mode (現状) |
|----|----------|------|------------------|
| 1  | hkobayashi   | admin   | conservative |
| 7  | admin-hk     | admin   | NULL |
| 8  | partner-test | editor  | NULL |
| 11 | yamamoto     | partner | NULL |
| 13 | 小林テスト   | viewer  | conservative |
| 14 | 小林テステス | viewer  | NULL |

### v10 要件 (F-3)

- 内部値 (conservative / balanced / aggressive) は **完全維持** (リネーム禁止)
  - Aave MDD / Optimizer Allocator / Aave Risk Profile が文字列リテラル直参照
- 表示は日本語ラベル (ローリスク / ミドルリスク / ハイリスク) を経由
- Phase 1 では CONSERVATIVE のみ選択可能 (BALANCED / AGGRESSIVE は API で 403)
- `users.risk_mode` を `NOT NULL DEFAULT 'conservative'` に変更したい

マイグレーション方針: 手動 `UPDATE` + `ALTER` (Alembic 自動マイグレーション未使用、`docs/ops/02_db_tables.md` 準拠)。

---

## 1. NULL 4 ユーザーの扱い

Phase 1 では CONSERVATIVE 一択のため、NULL は実質的に CONSERVATIVE と同等。
F-16 で全員 'conservative' に物理 UPDATE することで、
- アプリケーション側のフォールバック不要 (`get_risk_mode_label(None)` の利用箇所が消える)
- `NOT NULL` 制約導入が可能になる
- 監査ログ・通知文言が常に "ローリスク" を返す

### 影響範囲
- Aave Rebalance: 既に `_resolve_risk_mode(user_id, fallback="conservative")` で NULL を吸収済み → 挙動変化なし
- AI Judgment Scheduler: tier ベースで分岐するため影響なし
- 通知 / フロント表示: `risk_mode_label` が NULL 時も "ローリスク" を返すため変化なし

---

## 2. マイグレーション SQL (F-16 本番適用予定、本タスクでは実行しない)

### 2.1 事前チェック

```bash
# risk_mode 値分布の最終確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT risk_mode, COUNT(*) FROM users GROUP BY risk_mode ORDER BY risk_mode NULLS FIRST;
"

# valid 値以外が存在しないことを確認 (CHECK 相当)
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT risk_mode, COUNT(*) FROM users
WHERE risk_mode IS NOT NULL
  AND risk_mode NOT IN ('conservative', 'balanced', 'aggressive')
GROUP BY risk_mode;
"
# 期待: 0 行
```

### 2.2 バックアップ

```bash
docker exec ultra-autotrade-postgres-production pg_dump -U ultra -d ultra_autotrade \
  -t users \
  > /tmp/users_risk_mode_backup_$(date +%Y%m%d).sql
```

### 2.3 マイグレーション本体

```sql
BEGIN;

-- 1. NULL 4 ユーザーを 'conservative' に UPDATE (Phase 1 デフォルト)
UPDATE users
SET risk_mode = 'conservative'
WHERE risk_mode IS NULL;

-- 2. column DEFAULT 設定
ALTER TABLE users ALTER COLUMN risk_mode SET DEFAULT 'conservative';

-- 3. NOT NULL 制約付与
ALTER TABLE users ALTER COLUMN risk_mode SET NOT NULL;

-- 4. (任意) CHECK 制約追加 — 内部値の typo を防ぐ
ALTER TABLE users
ADD CONSTRAINT chk_users_risk_mode
CHECK (risk_mode IN ('conservative', 'balanced', 'aggressive'));

-- 5. 検証
SELECT risk_mode, COUNT(*) FROM users GROUP BY risk_mode ORDER BY risk_mode;
-- 期待: conservative=6 (NULL 0)

COMMIT;
```

### 2.4 適用後の追加検証

```bash
# Pydantic で読めることを確認 (バックエンド再起動後)
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool

# 各ユーザーの risk_mode 表示
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, username, role, risk_mode FROM users ORDER BY id;
"

# /auth/risk-modes エンドポイント
curl -sf -H "Authorization: Bearer <admin_token>" \
  https://api.ultra-auto-trade.com/auth/risk-modes | python3 -m json.tool
# 期待: 3 modes、conservative のみ allowed_in_phase_1=true
```

---

## 3. ロールバック手順

### 3.1 SQL レベル (F-16 当日のみ実行可)

```sql
BEGIN;

-- CHECK 制約 / NOT NULL / DEFAULT を v9 状態に戻す
ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_risk_mode;
ALTER TABLE users ALTER COLUMN risk_mode DROP NOT NULL;
ALTER TABLE users ALTER COLUMN risk_mode DROP DEFAULT;

-- 元の NULL 4 人を復元 (バックアップから対象 ID のみ復元)
-- 簡易復元: id IN (7, 8, 11, 14) を NULL に戻す
UPDATE users SET risk_mode = NULL WHERE id IN (7, 8, 11, 14);

COMMIT;
```

### 3.2 アプリケーションレベル

- F-3 PR を revert (`gh pr revert`) → main 再デプロイ
- enum / 辞書追加のみのため、revert で影響範囲は限定的
- Phase 1 制限 (PUT /auth/risk-mode の 403) も同時に消えるため、フロント側の UI 制限のみで対応

---

## 4. 実行タイミング (F-16)

1. F-15 山本さんレビュー完了
2. **山本さんへの事前周知 (24h 前 DM)**:
   - 「次回バックエンド更新時にリスクモード設定が必須化されます (Phase 1 はローリスクのみ選択可)」
   - 「未設定ユーザー 4 名は自動的に "ローリスク" 設定になります (操作変更なし)」
3. F-16 本番リリース時に本 SQL 実行
4. backend 再起動
5. 各ユーザーのダッシュボードで risk_mode が「ローリスク」と表示されることを確認

---

## 5. ロールアウト後監視

| チェック項目 | 方法 | 頻度 |
|--------------|------|------|
| risk_mode 値分布 | `SELECT risk_mode, COUNT(*) FROM users GROUP BY risk_mode;` | 直後 + 24h 後 |
| API `/auth/me` レスポンス | curl 6 回 (全ユーザー) → `risk_mode_label="ローリスク"` 確認 | 直後 |
| `/auth/risk-modes` | curl 1 回 → 3 modes 返却 + Phase 1 制限を確認 | 直後 |
| Aave Rebalance ログ | `docker logs ... \| grep -i 'risk_mode\|MDD'` | 24h 監視 |
| Phase 2 解禁試行のエラー | `docker logs ... \| grep -E '"Phase 2 以降で利用可能"'` | 1 週間監視 |
| 山本さん配下異常報告 | Slack `#ultra-auto-project` | 24h 監視 |

---

## 6. 設計判断 (F-3 で確定したこと)

| 項目 | 採用案 | 理由 |
|------|--------|------|
| enum 拡張方針 | **既存 v9 値を完全維持**、辞書だけ追加 | Aave/Optimizer/MDD が文字列リテラルで直参照しており、リネームすると 6 箇所同時修正が必要 |
| Phase 1 制限の実装層 | **API 層** (PUT /auth/risk-mode で 403) | DB 制約は将来 Phase 2 解禁時に剥がす必要があり、コードベースから外す方が容易 |
| 日本語ラベル | `RISK_MODE_JP_LABELS` 辞書を `auth/models.py` に集約 | F-2 (TIER_JP_LABELS) と同じ場所、一元化原則 |
| サブスク率 | `RISK_MODE_SUBSCRIPTION_RATES` 辞書 (Decimal) | F-1 で fee_configs.subscription_rates JSONB に投入する想定値と一致 (CONSERVATIVE=0, BALANCED=0.003, AGGRESSIVE=0.010) |
| プロトコル対応 | `RISK_MODE_PROTOCOLS` 辞書 (frozenset) | Phase 2 解禁時に Lido/Pendle 既存実装にそのまま接続できる設計 |
| /auth/risk-modes endpoint | **新規追加** (`/api/risk-modes` ではなく `/auth/risk-modes`) | 既存 `/auth/risk-mode` (singular) との co-location、auth router に集約 |
| `risk_mode_label` の API 露出 | UserResponse に **computed_field** で追加 | フロント側の翻訳辞書を持たずに済む、F-10 / F-11 の実装コスト削減 |

---

## 7. F-13 / F-16 への引き継ぎ

| タスク | 引き継ぎ事項 |
|--------|--------------|
| F-13 (v9 物理削除) | enum 値はそのまま維持 (Aave/Optimizer/MDD 直参照のため削除不可)。`get_risk_mode_label` の NULL フォールバックは F-16 後に削除可能 |
| F-16 (本番リリース) | 本ドキュメント §2 SQL を実行 |
| Phase 2 解禁時 | `PHASE_1_ALLOWED_RISK_MODES` を `frozenset({CONSERVATIVE, BALANCED, AGGRESSIVE})` に拡張 (本タスクの設計通り 1 行修正で完了) |
