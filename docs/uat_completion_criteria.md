# 山本さん UAT 完走判定基準

> 作成: 2026-05-18 / Lane A-4
> 対象ユーザー: 山本さん (user_id=11, m.yamamoto1017@gmail.com, role=partner, execution_policy=require_approval)

---

## 概要

「UAT 完走」を客観的に判定するため、以下 5 条件をすべて満たした時点を完走とする。
条件は本番 PostgreSQL から 1 コマンドで検証できる SQL を提供する（§ SQL セクション参照）。

---

## 完走条件 5 件

### 条件 1: 実行済み提案 5 件以上

```
proposals.user_id = 11
AND proposals.status = 'executed'
COUNT ≥ 5
```

- **根拠**: 1 回の成功では一過性の可能性がある。5 件のフルサイクル（AI 判定 → 提案生成 → 承認 → Aave 実行）完走で業務フロー安定を確認。
- **上限なし**: 5 件を超えた分はすべてカウント対象。

### 条件 2: 実行済み提案の合計 amount_usd ≥ $500

```
SUM(proposals.amount_usd) WHERE status='executed' AND user_id=11 ≥ 500
```

- **根拠**: 合計 $500 は実運用の最小有意水準。テスト用少額（$1 等）が大量に通過するだけでは不十分。
- **注意**: 1 件あたりの金額は問わない（合計値で判定）。

### 条件 3: proposal → transaction 中央値 < 10 分

```
PERCENTILE_CONT(0.5) WITHIN GROUP (
  ORDER BY EXTRACT(EPOCH FROM (proposals.executed_at - proposals.approved_at)) / 60
) < 10
WHERE proposals.status='executed'
  AND proposals.approved_at IS NOT NULL
  AND proposals.executed_at IS NOT NULL
```

- **根拠**: approved_at（山本さんが承認押下）から executed_at（Aave 実行完了）まで。10 分超は Aave 実行遅延・ガス詰まり等の異常シグナル。
- **中央値**: 外れ値（ガス高騰時の 1 件）に引きずられないよう中央値を採用。

### 条件 4: 実行済み提案に tx_hash あり（Base Mainnet 確認可能）

```
COUNT(tx_hash IS NOT NULL) WHERE status='executed' = 条件1のCOUNT
```

- **根拠**: `tx_hash` が NULL の `executed` 提案は dry_run または実行失敗の可能性がある。
- **Blockscan 確認**: `https://basescan.org/tx/<tx_hash>` で 1 confirmation 以上を手動確認する（自動化対象外）。
- **実行方法**: 代表 1 件の tx_hash を取得して手動確認すること。

### 条件 5: Slack #ultra-auto-project 異常報告ゼロ（過去 14 日）

- **判定方法**: Slack MCP または手動検索で `山本` / `エラー` / `動かない` / `壊れた` を検索。
- **期間**: 完走判定日の 14 日前まで。
- **除外**: テスト用のエラーログ通知（`⚠️` プレフィックス）は正常動作の証左として除外。

---

## 判定 SQL（1 コマンド）

以下を本番サーバーで実行して PASS/FAIL を確認する:

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
WITH
executed AS (
  SELECT
    COUNT(*) AS cnt,
    COALESCE(SUM(amount_usd), 0) AS total_usd,
    COUNT(tx_hash) AS with_tx_hash,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
      ORDER BY EXTRACT(EPOCH FROM (executed_at - approved_at)) / 60
    ) AS median_minutes
  FROM proposals
  WHERE user_id = 11
    AND status = 'executed'
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
  SELECT 1 ord, '条件1: executed≥5件'    AS condition, c1 AS result FROM checks
  UNION ALL
  SELECT 2,     '条件2: 合計≥\$500',                  c2         FROM checks
  UNION ALL
  SELECT 3,     '条件3: 中央値<10分',                  c3         FROM checks
  UNION ALL
  SELECT 4,     '条件4: tx_hash全件あり',              c4         FROM checks
  UNION ALL
  SELECT 5,     '条件5: Slack異常報告',               '手動確認要'
  UNION ALL
  SELECT 6,     '--- 集計値 ---',                      '---'
  UNION ALL
  SELECT 7,     'executed件数',          cnt::text              FROM checks
  UNION ALL
  SELECT 8,     '合計USD',              '\$' || total_usd       FROM checks
  UNION ALL
  SELECT 9,     '中央値(分)',            COALESCE(ROUND(median_minutes::numeric,1)::text, 'N/A') FROM checks
  UNION ALL
  SELECT 10,    'tx_hash有件数',         with_tx_hash::text     FROM checks
) t ORDER BY ord;
"
ENDSSH
```

---

## 現在値（2026-05-18 時点）

本番 DB クエリ実行結果:

| 条件 | 設定値 | 現在値 | 判定 |
|------|--------|--------|------|
| 条件1: executed 件数 | ≥ 5件 | **0件** | **FAIL (未達)** |
| 条件2: 合計 amount_usd | ≥ $500 | **$0** | **FAIL (未達)** |
| 条件3: 承認→実行 中央値 | < 10分 | **N/A** (executed=0件) | **FAIL (未達)** |
| 条件4: tx_hash 有件数 | 全 executed 件 | **0件** | **FAIL (未達)** |
| 条件5: Slack 異常報告 | 0件/14日 | 手動確認要 | **未確認** |

### 現状サマリー

- proposals テーブル: 2件 (`expired` のみ、2026-05-06 / 2026-05-07)
- transactions テーブル: 0件
- 実行済み提案: 0件（全件 expired で承認前に期限切れ）
- ブロッカー: 山本さん (execution_policy=`require_approval`) が提案を承認しないまま期限切れになっている

### ブロッカー原因候補

1. proposals の `expires_at` が短すぎる（提案が承認前に期限切れ）
2. 山本さんへの提案通知（Slack / LINE / Push）が届いていない
3. 山本さんのフロントエンドで承認ボタンが機能していない（UI バグ）

---

## blockscan 手動確認手順（条件4補足）

`executed` 提案が出たら以下で tx_hash を取得して確認する:

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<'ENDSSH'
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "
SELECT id, tx_hash, executed_at, amount_usd
FROM proposals
WHERE user_id=11 AND status='executed' AND tx_hash IS NOT NULL
ORDER BY executed_at DESC LIMIT 5;
"
ENDSSH
```

取得した `tx_hash` を `https://basescan.org/tx/<tx_hash>` で開き、
`Status: Success` かつ `Block Confirmations ≥ 1` を目視確認する。

---

## 完走後の手続き

5 条件が全 PASS になったら:

1. 本 SQL を実行してスクリーンショット取得
2. basescan.org で代表 1 件の tx_hash を確認してスクリーンショット取得
3. Asana の「山本さん UAT 完走判定」タスクを close
4. 小林さんが山本さんへ完走報告（CLAUDE.md §10 文面禁止・本人送信ルール遵守）
