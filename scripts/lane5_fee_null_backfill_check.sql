-- Lane 5: proposals.fee_rate / fee_amount NULL バックフィル判定用 診断 SQL
-- 実行: 本番 VPS (Hetzner 5.223.88.14, ASSIST ONE) で hkobayashi が psql から実行する。
--        dev VPS からは本番 DB へ到達不可のため、ここでは SQL のみ用意 (実行しない)。
-- 目的: 2026-06-04 本番 proposal id=16 以外に fee_rate / fee_amount NULL の行が
--        残っているかを把握し、バックフィルの要否・対象件数を判断する。
--
-- 前提 (コード根拠):
--   - proposals.fee_rate / fee_amount は「proposal に記録するメタ情報」であり、
--     ユーザーへの実課金額ではない。実課金は月次バッチ F-7 が FeeConfigV10 から
--     独立再計算し fee_transactions.fee_amount_jpy に書く
--     (app/fees/calculator.py:_get_tier_fee_rate は proposals.fee_rate を参照しない)。
--   - 従って NULL 行があっても「取りこぼし課金」には直結しない。バックフィルは
--     監査メタの整合 (executed proposal に fee_rate が残っているか) の観点で判断する。
--   - app 配線 (router.py:994 _lookup_fee_rate_for_user) は 2026-06-05 以降の executed に対してのみ有効。
--     それ以前に executed 済みの行は NULL のまま → これがバックフィル候補。

\echo '===== [1] 全体: fee_rate / fee_amount が NULL の行数 (status 別) ====='
SELECT
    status,
    COUNT(*)                                            AS total_rows,
    COUNT(*) FILTER (WHERE fee_rate   IS NULL)          AS fee_rate_null,
    COUNT(*) FILTER (WHERE fee_amount IS NULL)          AS fee_amount_null,
    COUNT(*) FILTER (WHERE fee_rate IS NULL
                       OR fee_amount IS NULL)           AS either_null
FROM proposals
GROUP BY status
ORDER BY either_null DESC, status;

\echo '===== [2] 要注目: executed なのに fee_rate / fee_amount が NULL の行 (= バックフィル一次候補) ====='
SELECT
    id,
    user_id,
    execution_route,
    fee_rate,
    fee_amount,
    executed_at,
    tx_hash
FROM proposals
WHERE status = 'executed'
  AND (fee_rate IS NULL OR fee_amount IS NULL)
ORDER BY executed_at NULLS FIRST, id;

\echo '===== [3] id=16 が唯一かの確認 (executed かつ NULL の件数 / 最小最大 id) ====='
SELECT
    COUNT(*)        AS executed_null_count,
    MIN(id)         AS min_id,
    MAX(id)         AS max_id,
    MIN(executed_at) AS earliest_executed,
    MAX(executed_at) AS latest_executed
FROM proposals
WHERE status = 'executed'
  AND (fee_rate IS NULL OR fee_amount IS NULL);

\echo '===== [4] 経路別内訳 (non-custodial / submit-tx 経路に偏っているかの確認) ====='
SELECT
    execution_route,
    COUNT(*) FILTER (WHERE status = 'executed'
                       AND (fee_rate IS NULL OR fee_amount IS NULL)) AS executed_null,
    COUNT(*) FILTER (WHERE status = 'executed')                     AS executed_total
FROM proposals
GROUP BY execution_route
ORDER BY executed_null DESC;

-- バックフィル方針メモ (件数判明後に判断):
--   - [2]/[3] が id=16 のみ      → app 修正 (router.py:994) で再発防止済み。バックフィル不要 or 手動1行。
--   - [2] に複数の executed NULL → 各行の user_id tier から FeeConfigV10.tier_fee_rates を引いて
--       fee_rate を埋め、fee_amount=0 で UPDATE するバックフィルを別途用意 (本 PR スコープ外)。
--   - fee_amount は設計上常に 0 (per-trade fee は月次バッチが算定) のため、NULL→0 埋めは安全。
