# Partner UAT 完走判定基準

> 作成: 2026-05-18 / Lane A-4 (PR #251)
> 2026-05-28 改訂: 2 partner 体制（山本+橋口）対応 / Asana 1215185448109917
>
> **対象 partner (2026-05-28 時点)**:
>
> | id | email | role | wallet_address | execution_policy |
> |---|---|---|---|---|
> | 11 | m.yamamoto1017@gmail.com | partner | `0x2064...cc66` 登録済 | require_approval |
> | 18 | (橋口さん) | partner | 2026-06-01 までに登録予定 | require_approval |
>
> 新規 partner が追加された場合も自動で対象に含めるため、SQL は **`WHERE role='partner' AND is_active = TRUE`** を採用する（id ハードコードしない）。

---

## 概要

「Partner UAT 完走」を客観的に判定するため、以下 5 条件をすべて満たした時点を完走とする。
条件は本番 PostgreSQL から 1 コマンドで検証できる SQL を提供する（§ SQL セクション参照）。

**判定単位**:
- **合算判定**: 全 partner (`role='partner' AND is_active = TRUE`) の executed 提案を合算して 5 条件を評価する（業務フロー安定の最終判定）。
- **partner 別内訳**: 各 partner ごとの件数・金額・中央値も補助的に表示し、偏りがあれば気付けるようにする（合算で達成しても 1 partner に集中していたら追加観察する）。

---

## 完走条件 5 件（閾値は PR #251 から変更なし）

### 条件 1: 実行済み提案 5 件以上

```
proposals.status = 'executed'
JOIN users ON users.id = proposals.user_id
WHERE users.role = 'partner' AND users.is_active = TRUE
COUNT ≥ 5
```

- **根拠**: 1 回の成功では一過性の可能性がある。5 件のフルサイクル（AI 判定 → 提案生成 → 承認 → Aave 実行）完走で業務フロー安定を確認。
- **上限なし**: 5 件を超えた分はすべてカウント対象。
- **対象拡張理由 (2026-05-28)**: 2 partner 体制になるため、partner を id ハードコードせず `role='partner' AND is_active=TRUE` で集計する。山本さん単独前提だと橋口さん側の executed 提案が漏れる。

### 条件 2: 実行済み提案の合計 amount_usd ≥ $500

```
SUM(proposals.amount_usd)
  WHERE status='executed' AND user_id IN (partner ids)
  ≥ 500
```

- **根拠**: 合計 $500 は実運用の最小有意水準。テスト用少額（$1 等）が大量に通過するだけでは不十分。
- **注意**: 1 件あたりの金額は問わない（合計値で判定）。partner 横断合算。

### 条件 3: proposal → transaction 中央値 < 10 分

```
PERCENTILE_CONT(0.5) WITHIN GROUP (
  ORDER BY EXTRACT(EPOCH FROM (proposals.executed_at - proposals.approved_at)) / 60
) < 10
WHERE proposals.status='executed'
  AND proposals.approved_at IS NOT NULL
  AND proposals.executed_at IS NOT NULL
  AND user_id IN (partner ids)
```

- **根拠**: approved_at（partner が承認押下）から executed_at（Aave 実行完了）まで。10 分超は Aave 実行遅延・ガス詰まり等の異常シグナル。
- **中央値**: 外れ値（ガス高騰時の 1 件）に引きずられないよう中央値を採用。partner 横断で集計。

### 条件 4: 実行済み提案に tx_hash あり（Base Mainnet 確認可能）

```
COUNT(tx_hash IS NOT NULL) WHERE status='executed' = 条件1のCOUNT
```

- **根拠**: `tx_hash` が NULL の `executed` 提案は dry_run または実行失敗の可能性がある。
- **Blockscan 確認**: `https://basescan.org/tx/<tx_hash>` で 1 confirmation 以上を手動確認する（自動化対象外）。
- **実行方法**: 代表 1 件の tx_hash を取得して手動確認すること。

### 条件 5: Slack #ultra-auto-project 異常報告ゼロ（過去 14 日）

- **判定方法**: Slack MCP または手動検索で `山本` / `橋口` / `エラー` / `動かない` / `壊れた` を検索。
- **期間**: 完走判定日の 14 日前まで。
- **除外**: テスト用のエラーログ通知（`⚠️` プレフィックス）は正常動作の証左として除外。

---

## 判定 SQL（1 コマンド）

以下を本番サーバーで実行して PASS/FAIL を確認する:

```bash
ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
WITH
partners AS (
  SELECT id, email FROM users
   WHERE role = 'partner' AND is_active = TRUE
),
executed AS (
  SELECT
    COUNT(*) AS cnt,
    COALESCE(SUM(p.amount_usd), 0) AS total_usd,
    COUNT(p.tx_hash) AS with_tx_hash,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
      ORDER BY EXTRACT(EPOCH FROM (p.executed_at - p.approved_at)) / 60
    ) AS median_minutes
  FROM proposals p
  JOIN partners ON partners.id = p.user_id
  WHERE p.status = 'executed'
),
checks AS (
  SELECT
    cnt,
    total_usd,
    with_tx_hash,
    median_minutes,
    CASE WHEN cnt >= 5 THEN 'PASS' ELSE 'FAIL (未達: ' || cnt || '/5件)' END AS c1,
    CASE WHEN total_usd >= 500 THEN 'PASS' ELSE 'FAIL (未達: \$' || total_usd || '/\$500)' END AS c2,
    CASE
      WHEN median_minutes IS NULL THEN 'N/A (executed=0件)'
      WHEN median_minutes < 10   THEN 'PASS (' || ROUND(median_minutes::numeric,1) || '分)'
      ELSE                            'FAIL (' || ROUND(median_minutes::numeric,1) || '分 ≥ 10分)'
    END AS c3,
    CASE
      WHEN cnt = 0            THEN 'N/A (executed=0件)'
      WHEN with_tx_hash = cnt THEN 'PASS (全' || cnt || '件に tx_hash あり)'
      ELSE                         'FAIL (' || with_tx_hash || '/' || cnt || '件に tx_hash)'
    END AS c4
  FROM executed
)
SELECT condition, result FROM (
  SELECT 1 ord, '条件1: executed≥5件 (partner 合算)'    AS condition, c1 AS result FROM checks
  UNION ALL
  SELECT 2,     '条件2: 合計≥\$500 (partner 合算)',     c2         FROM checks
  UNION ALL
  SELECT 3,     '条件3: 中央値<10分 (partner 合算)',    c3         FROM checks
  UNION ALL
  SELECT 4,     '条件4: tx_hash全件あり',               c4         FROM checks
  UNION ALL
  SELECT 5,     '条件5: Slack異常報告',                 '手動確認要'
  UNION ALL
  SELECT 6,     '--- 合算 集計値 ---',                   '---'
  UNION ALL
  SELECT 7,     'executed件数 (全 partner 合算)',         cnt::text   FROM checks
  UNION ALL
  SELECT 8,     '合計USD (全 partner 合算)',             '\$' || total_usd                                            FROM checks
  UNION ALL
  SELECT 9,     '中央値(分)',                            COALESCE(ROUND(median_minutes::numeric,1)::text, 'N/A')      FROM checks
  UNION ALL
  SELECT 10,    'tx_hash有件数',                         with_tx_hash::text                                           FROM checks
) t ORDER BY ord;
"
ENDSSH
```

### partner 別内訳 SQL（補助 / 偏り検知用）

```bash
ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
SELECT
  u.id,
  u.email,
  COUNT(p.id) FILTER (WHERE p.status = 'executed') AS executed_count,
  COALESCE(SUM(p.amount_usd) FILTER (WHERE p.status = 'executed'), 0) AS executed_total_usd,
  COUNT(p.tx_hash) FILTER (WHERE p.status = 'executed' AND p.tx_hash IS NOT NULL) AS with_tx_hash,
  ROUND(
    PERCENTILE_CONT(0.5) WITHIN GROUP (
      ORDER BY EXTRACT(EPOCH FROM (p.executed_at - p.approved_at)) / 60
    ) FILTER (WHERE p.status = 'executed')
  ::numeric, 1) AS median_minutes
FROM users u
LEFT JOIN proposals p ON p.user_id = u.id
WHERE u.role = 'partner' AND u.is_active = TRUE
GROUP BY u.id, u.email
ORDER BY u.id;
"
ENDSSH
```

partner 別の executed 件数・合計 USD・中央値を見て、どちらかの partner に極端に偏っていないか確認する（例: 山本さん 5 件 / 橋口さん 0 件 でも合算 5 件で条件1 PASS になるが、業務安定性としては不十分）。

---

## 現在値（2026-05-28 改訂時点 / 2 partner 化後 初回 baseline）

実機 baseline は本 PR マージ後に本番で SQL を再実行して取得する。
2 partner 化以前 (2026-05-18 PR #251 時点) の値は以下:

| 条件 | 設定値 | 2026-05-18 値 (旧山本さん単独) | 判定 |
|------|--------|--------|------|
| 条件1: executed 件数 (合算) | ≥ 5件 | 0件 | FAIL (未達) |
| 条件2: 合計 amount_usd (合算) | ≥ $500 | $0 | FAIL (未達) |
| 条件3: 承認→実行 中央値 (合算) | < 10分 | N/A (executed=0件) | FAIL (未達) |
| 条件4: tx_hash 有件数 | 全 executed 件 | 0件 | FAIL (未達) |
| 条件5: Slack 異常報告 | 0件/14日 | 手動確認要 | 未確認 |

### 現状サマリー (2026-05-28 改訂時点で既知の情報)

- 2026-05-28 朝、`users` テーブルに橋口さん (id=18, role=partner) を INSERT 済。
- 山本さん (id=11) は wallet_address `0x2064...cc66` 登録済。
- 橋口さん (id=18) は 2026-06-01 までに wallet_address 登録予定。
- PR #251 (2026-05-18) 時点での山本さん単独 proposals: 2件 (`expired` のみ / 2026-05-06, 2026-05-07 作成)。橋口さん側 proposals: 未生成。
- 本 PR マージ後、上記 SQL を本番で再実行して 2 partner 合算 baseline を取得し本セクションを更新する。

### ブロッカー原因候補 (2026-05-18 時点・以後の改善状況は別途追跡)

1. proposals の `expires_at` が短すぎる（提案が承認前に期限切れ）
2. partner への提案通知（Slack / LINE / Push）が届いていない
3. partner のフロントエンドで承認ボタンが機能していない（UI バグ）

---

## blockscan 手動確認手順（条件4補足）

`executed` 提案が出たら以下で tx_hash を取得して確認する:

```bash
ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
SELECT p.id, p.user_id, u.email, p.tx_hash, p.executed_at, p.amount_usd
FROM proposals p
JOIN users u ON u.id = p.user_id
WHERE u.role = 'partner' AND u.is_active = TRUE
  AND p.status='executed' AND p.tx_hash IS NOT NULL
ORDER BY p.executed_at DESC LIMIT 5;
"
ENDSSH
```

取得した `tx_hash` を `https://basescan.org/tx/<tx_hash>` で開き、
`Status: Success` かつ `Block Confirmations ≥ 1` を目視確認する。

---

## 完走後の手続き

5 条件が全 PASS になったら:

1. 本 SQL（合算判定 + partner 別内訳の両方）を実行してスクリーンショット取得
2. basescan.org で代表 1 件の tx_hash を確認してスクリーンショット取得
3. Asana の「Partner UAT 完走判定」タスクを close
4. 小林さんが各 partner（山本さん・橋口さん）へ完走報告（CLAUDE.md §10 文面禁止・本人送信ルール遵守）

---

## 変更履歴

| 日付 | 変更 | PR / Asana |
|------|------|------------|
| 2026-05-18 | 初版（山本さん user_id=11 単独前提） | PR #251 |
| 2026-05-28 | 2 partner 体制（山本+橋口）対応 / `role='partner' AND is_active=TRUE` 一般化 / wallet_address 状況更新。**5 条件の閾値（5件 / $500 / 10分 / tx_hash / 14日異常ゼロ）は変更なし**、対象 user_id のみ拡張。 | Asana 1215185448109917 |
