# Power BI Dashboard — Build Guide

Build time: about 2–3 hours in Power BI Desktop (free). All files are in this folder, produced by section 9 of the notebook.

| File | Rows | What it is |
|---|---|---|
| `fact_monthly_activity.csv` | 96,211 | One row per operator per month: toll txns, toll GTV, fuel spend, GPS devices, loads, net revenue, services used, city, fleet band, channel |
| `fact_recharges_daily.csv` | 67,196 | Daily recharge attempts and amount by bank, city, channel and status |
| `dim_operator.csv` | 40,000 | One row per operator: signup, city, fleet, channel, bank, KYC submitted, activated |
| `onboarding_funnel.csv` | 5 | Funnel stages with counts and step conversion |
| `cohort_retention.csv` | ~80 | Cohort × months-since-first-transaction retention % |
| `ab_test_results.csv` | 8 | A/B test scorecard |

## 1. Load and model
1. **Get data → Text/CSV** for each file. Set types: dates (`date`, `signup_ts`) → Date; amounts → Decimal; counts → Whole number; `month` → Text (sorts correctly as YYYY-MM).
2. Create a date table: **Modeling → New table**
   ```dax
   Calendar = ADDCOLUMNS(CALENDAR(DATE(2026,1,1), DATE(2026,10,31)),
       "Month", FORMAT([Date], "YYYY-MM"), "Week start", [Date] - WEEKDAY([Date], 3))
   ```
   Mark it as the date table.
3. Relationships (single direction, many-to-one):
   - `fact_recharges_daily[date]` → `Calendar[Date]`
   - `fact_monthly_activity[operator_id]` → `dim_operator[operator_id]`

## 2. Measures (`_Measures` table)
```dax
Transacting Operators = DISTINCTCOUNT(fact_monthly_activity[operator_id])
Multi-service Operators = CALCULATE([Transacting Operators], fact_monthly_activity[services] >= 2)
Multi-service % = DIVIDE([Multi-service Operators], [Transacting Operators])
Toll GTV (Cr) = DIVIDE(SUM(fact_monthly_activity[toll_gtv]), 1e7)
Net Revenue (Lakh) = DIVIDE(SUM(fact_monthly_activity[net_revenue]), 1e5)
ARPU = DIVIDE(SUM(fact_monthly_activity[net_revenue]), [Transacting Operators])

Recharge Attempts = SUM(fact_recharges_daily[recharges])
Failed Recharges = CALCULATE([Recharge Attempts], fact_recharges_daily[status] = "failed")
Failure Rate = DIVIDE([Failed Recharges], [Recharge Attempts])
Successful TPV (Lakh) = DIVIDE(CALCULATE(SUM(fact_recharges_daily[amount]), fact_recharges_daily[status] = "success"), 1e5)

KYC Submit Rate = DIVIDE(SUM(dim_operator[kyc_submitted]), COUNTROWS(dim_operator))
Activation Rate = DIVIDE(SUM(dim_operator[activated]), COUNTROWS(dim_operator))
```
Format rates as %, money with 1 decimal.

## 3. Pages

**Page 1 — Product health (North Star).** Cards: Transacting Operators, Multi-service Operators, Toll GTV (Cr), ARPU. Column chart of Transacting Operators by `month`; line chart of Multi-service % by `month`. Slicers: city, fleet_band.

**Page 2 — Activation funnel.** Funnel visual from `onboarding_funnel` (stage, operators). Matrix: rows `acquisition_channel`, columns `fleet_band`, value KYC Submit Rate, with background-colour conditional formatting. This is the "assisted KYC" story.

**Page 3 — Retention & cross-sell.** Matrix from `cohort_retention` (rows cohort, columns months_since_first, values retention_pct) with a colour gradient. Clustered bar: ARPU by `services`. Card: Multi-service %.

**Page 4 — Payments reliability (root cause).** Line chart: Successful TPV (Lakh) by `Calendar[Date]`, plus a second line chart of Failure Rate by date (two charts, not a dual axis). Bar chart: Failure Rate by `bank`. Bar chart: Failure Rate by `city`, filtered to Bank C. Date slicer set to 1 Jul–15 Sep.

**Page 5 — Experiment.** Table of `ab_test_results`; cards for Lift (pts) and p-value; a text box with the decision: "Launch auto-recharge; fix mandate failures."

## 4. Sanity checks
| Check | Expected |
|---|---|
| Transacting Operators, Oct 2026 | 11,047 |
| Toll GTV, Oct 2026 | ₹76.0 Cr |
| Multi-service %, Oct 2026 | 48.3% |
| Failure Rate, Bank C, 8–21 Aug | ≈55% |
| KYC Submit Rate, Paid ads + fleet "1" (signups before 1 Sep) | ≈56% |

Use only this simulated data when publishing to Power BI Service or sharing screenshots.
