-- ============================================================
-- Ultra AutoTrade ローンチ判断ダッシュボード
-- 参照: docs/launch_decision_criteria_v2.md
--
-- 実行方法 (Hetzner):
--   docker exec ultra-autotrade-postgres-production \
--     psql -U ultra -d ultra_autotrade -t -A \
--     -f /opt/ultra-autotrade/scripts/launch_dashboard.sql
-- ============================================================

WITH
now_jst AS (
  SELECT NOW() AT TIME ZONE 'Asia/Tokyo' AS ts
),

-- L3: 直近 14日の ai_decisions 日別集計
l3_daily AS (
  SELECT
    DATE(created_at AT TIME ZONE 'Asia/Tokyo') AS day,
    COUNT(*) AS cnt
  FROM ai_decisions
  WHERE created_at > NOW() - INTERVAL '14 days'
  GROUP BY DATE(created_at AT TIME ZONE 'Asia/Tokyo')
),
l3_summary AS (
  SELECT
    COUNT(*) FILTER (WHERE cnt >= 3)  AS green_days,
    COUNT(*) FILTER (WHERE cnt < 3)   AS red_days,
    COALESCE(MIN(cnt), 0)             AS min_daily,
    COALESCE(MAX(cnt), 0)             AS max_daily,
    COALESCE(SUM(cnt), 0)             AS total_14d
  FROM l3_daily
),

-- L4: 直近 14日の proposals 日別集計
l4_daily AS (
  SELECT
    DATE(created_at AT TIME ZONE 'Asia/Tokyo') AS day,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE status = 'expired') AS expired_cnt,
    COALESCE(
      ROUND(COUNT(*) FILTER (WHERE status='expired')::numeric / NULLIF(COUNT(*),0) * 100, 1),
      0
    ) AS expired_pct
  FROM proposals
  WHERE created_at > NOW() - INTERVAL '14 days'
  GROUP BY DATE(created_at AT TIME ZONE 'Asia/Tokyo')
),
l4_summary AS (
  SELECT
    COUNT(*) FILTER (WHERE total = 0 OR expired_pct < 50) AS green_days,
    COUNT(*) FILTER (WHERE total > 0 AND expired_pct >= 50) AS red_days
  FROM l4_daily
),

-- L5: 直近 14日の transactions 日別集計
l5_daily AS (
  SELECT
    DATE(created_at AT TIME ZONE 'Asia/Tokyo') AS day,
    COUNT(*) FILTER (WHERE is_dry_run = false) AS real_cnt,
    COUNT(*) FILTER (WHERE tx_hash IS NULL AND is_dry_run = false) AS failed_cnt,
    COALESCE(
      ROUND(
        COUNT(*) FILTER (WHERE tx_hash IS NULL AND is_dry_run = false)::numeric
        / NULLIF(COUNT(*) FILTER (WHERE is_dry_run = false), 0) * 100,
      1), 0) AS fail_pct
  FROM transactions
  WHERE created_at > NOW() - INTERVAL '14 days'
  GROUP BY DATE(created_at AT TIME ZONE 'Asia/Tokyo')
),
l5_summary AS (
  SELECT
    COUNT(*) FILTER (WHERE real_cnt = 0 OR fail_pct < 20) AS green_days,
    COUNT(*) FILTER (WHERE real_cnt > 0 AND fail_pct >= 20) AS red_days
  FROM l5_daily
),

-- 直近 24h スナップショット
recent AS (
  SELECT
    (SELECT COUNT(*) FROM ai_decisions
     WHERE created_at > NOW() - INTERVAL '24 hours')                         AS ai_24h,
    (SELECT COUNT(*) FROM proposals
     WHERE created_at > NOW() - INTERVAL '24 hours')                         AS proposals_24h,
    (SELECT COUNT(*) FROM transactions
     WHERE is_dry_run = false AND created_at > NOW() - INTERVAL '24 hours')  AS real_tx_24h,
    (SELECT COALESCE(SUM(CASE WHEN total_value_usd = 0 THEN 1 ELSE 0 END), 0)
       * 100.0 / NULLIF(COUNT(*), 0)
     FROM portfolio_snapshots
     WHERE recorded_at > NOW() - INTERVAL '24 hours')                        AS l6_zero_pct
),

-- 山本さん (user_id=11) UAT 状態
uat AS (
  SELECT
    COUNT(*)                                                                   AS total,
    COUNT(*) FILTER (WHERE status = 'executed')                               AS executed,
    COUNT(*) FILTER (WHERE status = 'expired')                                AS expired,
    COUNT(*) FILTER (WHERE status = 'rejected')                               AS rejected,
    COUNT(*) FILTER (WHERE status NOT IN ('executed','expired','rejected')
                     AND expires_at > NOW())                                   AS active_non_exec
  FROM proposals
  WHERE user_id = 11
)

SELECT '============================================' AS metric, '' AS value
UNION ALL SELECT 'ローンチ判断ダッシュボード', (SELECT ts::text FROM now_jst)
UNION ALL SELECT '============================================', ''

UNION ALL SELECT '--- DB 側指標 (L3-L5 過去 14日) ---', ''

UNION ALL SELECT 'L3 (AI判定) 14日緑日数',
  (SELECT green_days || '/14 日 PASS (要: 14/14) | min=' || min_daily || ' max=' || max_daily FROM l3_summary)
UNION ALL SELECT 'L3 RED 日数',
  (SELECT red_days || '日 (ai_decisions < 3/day)' FROM l3_summary)

UNION ALL SELECT 'L4 (user反応) 14日緑日数',
  (SELECT green_days || '/14 日 PASS (要: 14/14)' FROM l4_summary)
UNION ALL SELECT 'L4 RED 日数',
  (SELECT red_days || '日 (expired_rate >= 50%)' FROM l4_summary)

UNION ALL SELECT 'L5 (実取引) 14日緑日数',
  (SELECT green_days || '/14 日 PASS (要: 14/14)' FROM l5_summary)
UNION ALL SELECT 'L5 RED 日数',
  (SELECT red_days || '日 (real tx fail_rate >= 20%)' FROM l5_summary)

UNION ALL SELECT '--- 直近 24h ---', ''
UNION ALL SELECT 'L3 ai_decisions_24h', (SELECT ai_24h::text || ' 件 (要: >=3)' FROM recent)
UNION ALL SELECT 'L4 proposals_24h',    (SELECT proposals_24h::text || ' 件' FROM recent)
UNION ALL SELECT 'L5 real_tx_24h',      (SELECT real_tx_24h::text || ' 件 (0=UAT中正常)' FROM recent)
UNION ALL SELECT 'L6 zero_value_pct',   (SELECT ROUND(COALESCE(l6_zero_pct,0),1)::text || '% (100%=UAT常態)' FROM recent)

UNION ALL SELECT '--- 山本さん UAT (user_id=11) ---', ''
UNION ALL SELECT 'total_proposals',      (SELECT total::text FROM uat)
UNION ALL SELECT 'executed',             (SELECT executed::text FROM uat)
UNION ALL SELECT 'expired',              (SELECT expired::text FROM uat)
UNION ALL SELECT 'rejected',             (SELECT rejected::text FROM uat)
UNION ALL SELECT 'active_non_executed',  (SELECT active_non_exec::text || ' 件 (0=CANDIDATE)' FROM uat)
UNION ALL SELECT 'UAT 状態',
  (SELECT CASE
    WHEN total < 5         THEN 'WAITING (proposals 生成待ち, 要: total>=5)'
    WHEN active_non_exec = 0 THEN 'CANDIDATE (最終承認 DM 待ち)'
    ELSE                        'IN_PROGRESS (' || active_non_exec || ' 件 active)'
  END FROM uat)

UNION ALL SELECT '--- DB 外指標 (別途手動確認) ---', ''
UNION ALL SELECT 'L1/L2 14日緑',   'grep healthcheck_l1_l6.log で確認 (docs/launch_decision_criteria_v2.md §1.3)'
UNION ALL SELECT 'chaos test',     'id=10 タスク waiting (docs/launch_decision_criteria_v2.md §2)'
UNION ALL SELECT 'Tier S 承認率',  'gh pr list --state merged で確認 (docs/launch_decision_criteria_v2.md §3.3)'
UNION ALL SELECT '森先生 法務確認', 'id=9 A-5: 5/22 DM 予定 (docs/launch_decision_criteria_v2.md §5)'
UNION ALL SELECT '============================================', ''
;
