-- =====================================================================
-- Truck Operator Super-App — Product Analytics in SQL
-- Database: data/superapp.db (SQLite). Simulated data, Jan–Oct 2026.
-- Tables: operators, onboarding_events, fastag_recharges,
--         monthly_activity, ab_test_assignments
-- Run all queries:  python scripts/02_run_sql.py
-- MySQL notes: replace julianday() with DATEDIFF/TIMESTAMPDIFF and
-- strftime('%Y-%m', x) with DATE_FORMAT(x, '%Y-%m').
-- =====================================================================

-- Q01. Business snapshot for October 2026
SELECT
  (SELECT COUNT(*) FROM operators)                                         AS total_signups,
  (SELECT COUNT(DISTINCT operator_id) FROM onboarding_events
    WHERE stage = 'fastag_activated')                                     AS activated_operators,
  (SELECT COUNT(*) FROM monthly_activity WHERE month = '2026-10')          AS monthly_transacting_operators,
  (SELECT ROUND(SUM(toll_gtv) / 1e7, 2) FROM monthly_activity
    WHERE month = '2026-10')                                              AS toll_gtv_cr,
  (SELECT ROUND(SUM(net_revenue) / 1e5, 2) FROM monthly_activity
    WHERE month = '2026-10')                                              AS net_revenue_lakh,
  (SELECT ROUND(100.0 * AVG(status = 'success'), 2) FROM fastag_recharges
    WHERE recharge_ts >= '2026-10-01')                                    AS recharge_success_pct;

-- Q02. Onboarding funnel (operators who signed up before 1 Sep 2026, so all had time to finish)
WITH cohort AS (SELECT operator_id FROM operators WHERE signup_ts < '2026-09-01'),
reached AS (
  SELECT e.stage, COUNT(DISTINCT e.operator_id) AS operators
  FROM onboarding_events e JOIN cohort c USING (operator_id)
  GROUP BY e.stage
),
ordered AS (
  SELECT stage, operators,
         CASE stage WHEN 'signup' THEN 1 WHEN 'kyc_submitted' THEN 2 WHEN 'kyc_approved' THEN 3
                    WHEN 'fastag_activated' THEN 4 WHEN 'first_toll' THEN 5 END AS step
  FROM reached
)
SELECT step, stage, operators,
       ROUND(100.0 * operators / FIRST_VALUE(operators) OVER (ORDER BY step), 1)      AS pct_of_signups,
       ROUND(100.0 * operators / LAG(operators) OVER (ORDER BY step), 1)              AS step_conversion_pct,
       LAG(operators) OVER (ORDER BY step) - operators                                AS dropped
FROM ordered
ORDER BY step;

-- Q03. KYC submission rate by acquisition channel and fleet size (where the biggest leak is)
SELECT o.acquisition_channel, o.fleet_band,
       COUNT(*) AS signups,
       ROUND(100.0 * AVG(EXISTS (SELECT 1 FROM onboarding_events e
                                 WHERE e.operator_id = o.operator_id AND e.stage = 'kyc_submitted')), 1) AS kyc_submit_pct
FROM operators o
WHERE o.signup_ts < '2026-09-01'
GROUP BY o.acquisition_channel, o.fleet_band
ORDER BY kyc_submit_pct;

-- Q04. Average days from signup to each stage (activated operators)
WITH s AS (
  SELECT operator_id,
         MAX(CASE WHEN stage = 'signup'           THEN event_ts END) AS signup,
         MAX(CASE WHEN stage = 'kyc_submitted'    THEN event_ts END) AS kyc,
         MAX(CASE WHEN stage = 'kyc_approved'     THEN event_ts END) AS approved,
         MAX(CASE WHEN stage = 'fastag_activated' THEN event_ts END) AS activated,
         MAX(CASE WHEN stage = 'first_toll'       THEN event_ts END) AS first_toll
  FROM onboarding_events GROUP BY operator_id
)
SELECT ROUND(AVG(julianday(kyc) - julianday(signup)), 1)          AS days_to_kyc,
       ROUND(AVG(julianday(approved) - julianday(kyc)), 1)        AS days_kyc_to_approval,
       ROUND(AVG(julianday(activated) - julianday(approved)), 1)  AS days_approval_to_activation,
       ROUND(AVG(julianday(first_toll) - julianday(signup)), 1)   AS days_signup_to_first_toll
FROM s
WHERE first_toll IS NOT NULL;

-- Q05. Monthly KPIs: transacting operators, toll GTV, revenue, ARPU, multi-service share
SELECT month,
       COUNT(*)                                                         AS transacting_operators,
       ROUND(SUM(toll_gtv) / 1e7, 2)                                     AS toll_gtv_cr,
       ROUND(SUM(net_revenue) / 1e5, 2)                                  AS net_revenue_lakh,
       ROUND(SUM(net_revenue) / COUNT(*), 0)                             AS arpu_rs,
       ROUND(100.0 * AVG((fuel_spend > 0) + (gps_devices > 0) + (loads_booked > 0) >= 1), 1) AS multi_service_pct
FROM monthly_activity
GROUP BY month
ORDER BY month;

-- Q06. Cohort retention: % of each first-active-month cohort still transacting N months later
--      (blank = that month is after October 2026, so not observable yet)
WITH m AS (
  SELECT operator_id,
         CAST(substr(month, 1, 4) AS INT) * 12 + CAST(substr(month, 6, 2) AS INT) AS mi
  FROM monthly_activity
),
f AS (SELECT operator_id, MIN(mi) AS cohort_mi FROM m GROUP BY operator_id),
a AS (SELECT m.operator_id, f.cohort_mi, m.mi - f.cohort_mi AS k FROM m JOIN f USING (operator_id))
SELECT printf('%d-%02d', (cohort_mi - 1) / 12, (cohort_mi - 1) % 12 + 1)  AS cohort,
       SUM(k = 0)                                                       AS cohort_size,
       CASE WHEN cohort_mi + 1 <= 2026 * 12 + 10 THEN ROUND(100.0 * SUM(k = 1) / SUM(k = 0), 1) END AS m1_pct,
       CASE WHEN cohort_mi + 2 <= 2026 * 12 + 10 THEN ROUND(100.0 * SUM(k = 2) / SUM(k = 0), 1) END AS m2_pct,
       CASE WHEN cohort_mi + 3 <= 2026 * 12 + 10 THEN ROUND(100.0 * SUM(k = 3) / SUM(k = 0), 1) END AS m3_pct
FROM a
WHERE cohort_mi > 2026 * 12 + 1          -- Jan-2026 "cohort" includes older operators, so start from Feb
GROUP BY cohort_mi
ORDER BY cohort_mi;

-- Q07. Service mix in October: how many services each transacting operator uses
SELECT 1 + (fuel_spend > 0) + (gps_devices > 0) + (loads_booked > 0) AS services_used,
       COUNT(*)                                                     AS operators,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)           AS pct_operators,
       ROUND(SUM(net_revenue) / COUNT(*), 0)                        AS arpu_rs,
       ROUND(100.0 * SUM(net_revenue) / SUM(SUM(net_revenue)) OVER (), 1) AS pct_revenue
FROM monthly_activity
WHERE month = '2026-10'
GROUP BY services_used
ORDER BY services_used;

-- Q08. Next-month retention: single-service vs multi-service operators (Jan–Sep)
WITH cur AS (
  SELECT operator_id, month,
         CASE WHEN (fuel_spend > 0) + (gps_devices > 0) + (loads_booked > 0) >= 1
              THEN 'Multi-service' ELSE 'FASTag only' END AS segment,
         CAST(substr(month, 1, 4) AS INT) * 12 + CAST(substr(month, 6, 2) AS INT) AS mi
  FROM monthly_activity
  WHERE month <= '2026-09'
),
nxt AS (
  SELECT operator_id, CAST(substr(month, 1, 4) AS INT) * 12 + CAST(substr(month, 6, 2) AS INT) AS mi
  FROM monthly_activity
)
SELECT c.segment,
       COUNT(*)                                                    AS operator_months,
       ROUND(100.0 * AVG(n.operator_id IS NOT NULL), 1)             AS next_month_retention_pct
FROM cur c
LEFT JOIN nxt n ON n.operator_id = c.operator_id AND n.mi = c.mi + 1
GROUP BY c.segment;

-- Q09. Weekly successful recharge value (TPV) around the August drop
SELECT date(recharge_ts, 'weekday 0', '-6 days')                AS week_start,
       COUNT(*)                                                  AS attempts,
       ROUND(SUM(CASE WHEN status = 'success' THEN amount END) / 1e7, 2) AS success_tpv_cr,
       ROUND(100.0 * AVG(status = 'failed'), 1)                   AS failure_pct
FROM fastag_recharges
WHERE recharge_ts >= '2026-07-06' AND recharge_ts < '2026-09-14'
GROUP BY week_start
ORDER BY week_start;

-- Q10. Root cause: recharge failure rate by bank, before vs during 8–21 Aug
SELECT bank,
       ROUND(100.0 * AVG(CASE WHEN recharge_ts >= '2026-07-25' AND recharge_ts < '2026-08-08'
                              THEN status = 'failed' END), 1)    AS fail_pct_2wk_before,
       ROUND(100.0 * AVG(CASE WHEN recharge_ts >= '2026-08-08' AND recharge_ts < '2026-08-22'
                              THEN status = 'failed' END), 1)    AS fail_pct_incident
FROM fastag_recharges
GROUP BY bank
ORDER BY fail_pct_incident DESC;

-- Q11. Root cause: Bank C failure rate by city during the incident (where the problem is)
SELECT o.city,
       COUNT(*)                                       AS bank_c_attempts,
       ROUND(100.0 * AVG(r.status = 'failed'), 1)     AS fail_pct
FROM fastag_recharges r
JOIN operators o USING (operator_id)
WHERE r.bank = 'Bank C' AND r.recharge_ts >= '2026-08-08' AND r.recharge_ts < '2026-08-22'
GROUP BY o.city
ORDER BY fail_pct DESC;

-- Q12. Impact sizing: lost successful TPV vs the same two weeks' expected run-rate
WITH base AS (
  SELECT SUM(CASE WHEN status = 'success' THEN amount END) / 14.0 AS daily
  FROM fastag_recharges WHERE recharge_ts >= '2026-07-25' AND recharge_ts < '2026-08-08'
),
inc AS (
  SELECT SUM(CASE WHEN status = 'success' THEN amount END) / 14.0 AS daily
  FROM fastag_recharges WHERE recharge_ts >= '2026-08-08' AND recharge_ts < '2026-08-22'
)
SELECT ROUND(base.daily / 1e5, 2)                         AS baseline_daily_tpv_lakh,
       ROUND(inc.daily / 1e5, 2)                          AS incident_daily_tpv_lakh,
       ROUND(100.0 * (inc.daily - base.daily) / base.daily, 1) AS change_pct,
       ROUND((base.daily - inc.daily) * 14 / 1e7, 2)      AS lost_tpv_cr_over_14_days
FROM base, inc;

-- Q13. Did the incident hurt retention? September retention of operators hit by a failed Bank C recharge
WITH hit AS (
  SELECT DISTINCT r.operator_id FROM fastag_recharges r JOIN operators o USING (operator_id)
  WHERE r.bank = 'Bank C' AND r.status = 'failed'
    AND r.recharge_ts >= '2026-08-08' AND r.recharge_ts < '2026-08-22'
    AND o.city IN ('Delhi NCR','Mumbai','Pune','Ahmedabad','Jaipur','Indore')
)
SELECT CASE WHEN h.operator_id IS NULL THEN 'Not affected' ELSE 'Hit by failed recharge' END AS grp,
       COUNT(*)                                                                         AS aug_operators,
       ROUND(100.0 * AVG(EXISTS (SELECT 1 FROM monthly_activity s
                                 WHERE s.operator_id = a.operator_id AND s.month = '2026-09')), 1) AS sep_retention_pct
FROM monthly_activity a
LEFT JOIN hit h ON h.operator_id = a.operator_id
WHERE a.month = '2026-08'
GROUP BY grp;

-- Q14. A/B test (auto-recharge, Sep 2026): sample ratio, retention, guardrail
WITH t AS (
  SELECT a.operator_id, a.variant,
         EXISTS (SELECT 1 FROM monthly_activity m
                 WHERE m.operator_id = a.operator_id AND m.month = '2026-10') AS retained_oct
  FROM ab_test_assignments a
),
g AS (
  SELECT a.variant, AVG(r.status = 'failed') AS fail_rate, COUNT(*) AS recharges
  FROM ab_test_assignments a
  JOIN fastag_recharges r ON r.operator_id = a.operator_id AND r.recharge_ts >= '2026-09-01'
  GROUP BY a.variant
)
SELECT t.variant,
       COUNT(*)                                     AS operators,
       ROUND(100.0 * AVG(t.retained_oct), 2)        AS oct_retention_pct,
       ROUND(100.0 * g.fail_rate, 2)                AS recharge_fail_pct,
       g.recharges
FROM t JOIN g USING (variant)
GROUP BY t.variant;

-- Q15. Toll GTV by city in October with share of total
SELECT o.city,
       COUNT(*)                                                           AS operators,
       ROUND(SUM(a.toll_gtv) / 1e7, 2)                                     AS toll_gtv_cr,
       ROUND(100.0 * SUM(a.toll_gtv) / SUM(SUM(a.toll_gtv)) OVER (), 1)    AS gtv_share_pct
FROM monthly_activity a
JOIN operators o USING (operator_id)
WHERE a.month = '2026-10'
GROUP BY o.city
ORDER BY toll_gtv_cr DESC;

-- Q16. Win-back list: highest-value operators active in September but not in October
SELECT s.operator_id, o.city, o.fleet_band, ROUND(s.toll_gtv) AS sep_toll_gtv, ROUND(s.net_revenue) AS sep_revenue
FROM monthly_activity s
JOIN operators o USING (operator_id)
WHERE s.month = '2026-09'
  AND NOT EXISTS (SELECT 1 FROM monthly_activity x WHERE x.operator_id = s.operator_id AND x.month = '2026-10')
ORDER BY s.toll_gtv DESC
LIMIT 10;
