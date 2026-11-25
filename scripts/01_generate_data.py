"""
Step 1: Generate a realistic SIMULATED dataset for a truck-operator super-app
(FASTag recharges, tolling, fuel payments, GPS telematics, freight loads),
modelled on how platforms like BlackBuck work. All data is synthetic.

Built-in patterns the analysis should discover:
  * Onboarding funnel with the biggest leak at KYC submission, worse for paid-ad
    and single-truck operators.
  * Retention that is much higher for operators using 2+ services.
  * Monsoon seasonality (Jul-Sep) in toll and recharge volumes.
  * An incident: 8-21 Aug 2026, a "Bank C" payment-gateway outage for operators in
    North & West India (Delhi NCR, Mumbai, Pune, Ahmedabad, Jaipur, Indore).
  * An A/B test (Sep 2026) of an auto-recharge feature, with a retention lift
    and a small rise in failed auto-debits (guardrail).

Writes CSVs to data/ and a SQLite database data/superapp.db.
Run from the project root:  python scripts/01_generate_data.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
rng = np.random.default_rng(42)

N_OPS = 40_000
START, END = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-10-31")   # reporting window
MONTHS = pd.period_range("2025-01", "2026-10", freq="M")             # simulated history
FIRST_REPORTED = pd.Period("2026-01", "M")
SEASON = {1: 1.00, 2: 1.00, 3: 1.05, 4: 1.02, 5: 1.00, 6: 0.97, 7: 0.94, 8: 0.92, 9: 0.93, 10: 1.03}

CITIES = ["Delhi NCR", "Mumbai", "Bengaluru", "Chennai", "Hyderabad", "Pune",
          "Ahmedabad", "Kolkata", "Jaipur", "Indore"]
CITY_P = [0.17, 0.13, 0.11, 0.10, 0.10, 0.09, 0.09, 0.08, 0.07, 0.06]
INCIDENT_CITIES = {"Delhi NCR", "Mumbai", "Pune", "Ahmedabad", "Jaipur", "Indore"}  # North & West
INCIDENT = (pd.Timestamp("2026-08-08"), pd.Timestamp("2026-08-21 23:59"))
BANKS, BANK_P = ["Bank A", "Bank B", "Bank C", "Bank D", "Bank E"], [0.22, 0.18, 0.32, 0.16, 0.12]
CHANNELS, CHANNEL_P = ["Field agent", "App organic", "Referral", "Paid ads"], [0.35, 0.25, 0.15, 0.25]
FLEETS, FLEET_P = ["1", "2-5", "6-20", "21+"], [0.42, 0.33, 0.18, 0.07]

# ---------------------------------------------------------------- operators
# Signups grow over time (more signups in later months)
signup_periods = pd.period_range("2025-01", "2026-09", freq="M")
month_w = np.linspace(1.0, 1.6, len(signup_periods))
month_w /= month_w.sum()
pick = rng.choice(len(signup_periods), size=N_OPS, p=month_w)
sp = signup_periods[pick]
signup_day = np.array([rng.integers(1, p.days_in_month + 1) for p in sp])
signup_ts = pd.to_datetime({"year": sp.year, "month": sp.month, "day": signup_day}) + \
    pd.to_timedelta(rng.integers(7 * 60, 22 * 60, N_OPS), unit="m")

ops = pd.DataFrame({
    "operator_id": np.arange(100001, 100001 + N_OPS),
    "signup_ts": signup_ts,
    "city": rng.choice(CITIES, N_OPS, p=CITY_P),
    "fleet_band": rng.choice(FLEETS, N_OPS, p=FLEET_P),
    "acquisition_channel": rng.choice(CHANNELS, N_OPS, p=CHANNEL_P),
    "primary_bank": rng.choice(BANKS, N_OPS, p=BANK_P),
})
lo = ops.fleet_band.map({"1": 1, "2-5": 2, "6-20": 6, "21+": 21})
hi = ops.fleet_band.map({"1": 1, "2-5": 5, "6-20": 20, "21+": 60})
ops["trucks"] = [int(rng.integers(a, b + 1)) for a, b in zip(lo, hi)]

# ---------------------------------------------------------------- onboarding funnel
p_kyc = (ops.acquisition_channel.map({"Field agent": 0.90, "App organic": 0.76, "Referral": 0.84, "Paid ads": 0.62})
         + ops.fleet_band.map({"1": -0.06, "2-5": 0.0, "6-20": 0.04, "21+": 0.06})).clip(0, 0.98)
p_approve = 0.87
p_activate = ops.fleet_band.map({"1": 0.86, "2-5": 0.89, "6-20": 0.92, "21+": 0.94})
p_first_toll = 0.93
p_second = ops.fleet_band.map({"1": 0.30, "2-5": 0.42, "6-20": 0.56, "21+": 0.64})

def stage(prev_ok, p):
    return prev_ok & (rng.random(N_OPS) < p)

ok_kyc = stage(np.ones(N_OPS, bool), p_kyc)
ok_appr = stage(ok_kyc, p_approve)
ok_act = stage(ok_appr, p_activate)
ok_toll = stage(ok_act, p_first_toll)
ok_sec = stage(ok_toll, p_second)

def delay(days_lo, days_hi):
    return pd.to_timedelta(rng.uniform(days_lo, days_hi, N_OPS) * 24 * 60, unit="m").round("min")

t_kyc = ops.signup_ts + delay(0.02, 6)
t_appr = t_kyc + delay(0.2, 3)
t_act = t_appr + delay(0.5, 5)
t_toll = t_act + delay(0.1, 10)
t_sec = t_toll + delay(3, 60)

events = []
for name, ok, t in [("signup", np.ones(N_OPS, bool), ops.signup_ts), ("kyc_submitted", ok_kyc, t_kyc),
                    ("kyc_approved", ok_appr, t_appr), ("fastag_activated", ok_act, t_act),
                    ("first_toll", ok_toll, t_toll)]:
    keep = ok & (t <= END)
    events.append(pd.DataFrame({"operator_id": ops.operator_id[keep], "stage": name, "event_ts": t[keep]}))
onboarding = pd.concat(events).sort_values(["operator_id", "event_ts"]).reset_index(drop=True)
first_toll = onboarding[onboarding.stage == "first_toll"].set_index("operator_id").event_ts

second_service = rng.choice(["fuel", "gps", "loads"], N_OPS, p=[0.45, 0.35, 0.20])
third_service = np.where(rng.random(N_OPS) < 0.25,
                         [rng.choice([s for s in ["fuel", "gps", "loads"] if s != x]) for x in second_service], None)
ops["second_service"] = np.where(ok_sec & (t_sec <= END), second_service, None)
ops["second_service_ts"] = pd.Series(t_sec).where(ok_sec & (t_sec <= END))
ops["third_service"] = np.where(ops.second_service.notna(), third_service, None)

# ---------------------------------------------------------------- A/B test (auto-recharge), Sep 2026
# Assignment happens after we know who was active in Aug, so we simulate month by month.

# ---------------------------------------------------------------- monthly activity + recharges
recharge_rows, activity_rows, ab_rows = [], [], []
ops_idx = ops.set_index("operator_id")
incident_hit = set()
rid = 1
for op in ops.itertuples(index=False):
    if op.operator_id not in first_toll.index:
        continue
    start_ts = first_toll[op.operator_id]
    if start_ts > END:
        continue
    multi_ts = op.second_service_ts if pd.notna(op.second_service_ts) else None
    churn_mult = {"1": 1.15, "2-5": 1.0, "6-20": 0.8, "21+": 0.65}[op.fleet_band]
    churn_mult *= 1.2 if op.acquisition_channel == "Paid ads" else 1.0
    variant, adopter = None, False
    tenure = 0
    for m in MONTHS:
        if m < start_ts.to_period("M"):
            continue
        m_start = max(m.start_time, start_ts)
        m_end = m.end_time.floor("min")
        # ---- A/B assignment on 1 Sep for operators active in Aug
        if m == pd.Period("2026-09") and tenure > 0:
            variant = "treatment" if rng.random() < 0.5 else "control"
            adopter = variant == "treatment" and rng.random() < 0.70
            ab_rows.append((op.operator_id, variant, "2026-09-01", int(adopter)))
        # ---- churn check at month boundary (not in the first month)
        if tenure > 0:
            multi = multi_ts is not None and multi_ts < m.start_time
            base = 0.24 if tenure == 1 else 0.075
            p_churn = base * churn_mult * (0.45 if multi else 1.0)
            if m == pd.Period("2026-09") and op.operator_id in incident_hit:
                p_churn *= 1.8
            if m == pd.Period("2026-10") and adopter:
                p_churn *= 0.45
            if rng.random() < p_churn:
                break
        tenure += 1
        if m < FIRST_REPORTED:          # history before the reporting window: simulate churn only
            continue
        frac = (m_end - m_start) / (m_end - m.start_time) if m_start > m.start_time else 1.0
        season = SEASON[m.month]
        toll_txns = int(rng.poisson(20 * op.trucks * season * frac))
        if toll_txns == 0:
            toll_txns = 1
        toll_gtv = round(toll_txns * 385 * rng.normal(1, 0.08), 2)
        multi_now = multi_ts is not None and multi_ts <= m_end
        services = {op.second_service, op.third_service} if multi_now else set()
        fuel_spend = round(op.trucks * 38000 * season * frac * rng.normal(1, 0.15), 2) if "fuel" in services else 0.0
        gps_devices = min(op.trucks, int(rng.integers(1, op.trucks + 1))) if "gps" in services else 0
        loads_booked = int(rng.poisson(2.5 * np.sqrt(op.trucks) * frac)) if "loads" in services else 0
        activity_rows.append((op.operator_id, str(m), toll_txns, toll_gtv, fuel_spend, gps_devices, loads_booked))

        # ---- FASTag recharges to fund the month's tolls
        ticket = max(800, round(2400 * np.sqrt(op.trucks) * rng.lognormal(0, 0.25), -2))
        n = max(1, int(np.ceil(toll_gtv / ticket)))
        span = (m_end - m_start).total_seconds()
        times = m_start + pd.to_timedelta(np.sort(rng.uniform(0, span, n)), unit="s")
        for t in times:
            bank = op.primary_bank
            is_auto = adopter and t >= pd.Timestamp("2026-09-01") and rng.random() < 0.8
            channel = "Auto-recharge" if is_auto else rng.choice(["App - UPI", "App - Netbanking", "Agent"], p=[0.62, 0.18, 0.20])
            p_fail = 0.035 + (0.015 if is_auto else 0.0)
            in_incident = (bank == "Bank C" and op.city in INCIDENT_CITIES and INCIDENT[0] <= t <= INCIDENT[1])
            if in_incident:
                p_fail = 0.88
            failed = rng.random() < p_fail
            amt = float(ticket)
            recharge_rows.append((rid, op.operator_id, t.floor("s"), amt, bank, channel, int(is_auto),
                                  "failed" if failed else "success"))
            rid += 1
            if failed:
                if in_incident:
                    incident_hit.add(op.operator_id)
                retry_p = 0.15 if in_incident else 0.55
                if rng.random() < retry_p:
                    t2 = t + pd.Timedelta(minutes=int(rng.integers(5, 2 * 24 * 60)))
                    if t2 <= END:
                        ok2 = rng.random() > (0.6 if in_incident else 0.035)
                        recharge_rows.append((rid, op.operator_id, t2.floor("s"), amt, bank, channel, int(is_auto),
                                              "success" if ok2 else "failed"))
                        rid += 1

recharges = pd.DataFrame(recharge_rows, columns=["recharge_id", "operator_id", "recharge_ts", "amount", "bank",
                                                 "channel", "is_auto", "status"])
activity = pd.DataFrame(activity_rows, columns=["operator_id", "month", "toll_txns", "toll_gtv", "fuel_spend",
                                                "gps_devices", "loads_booked"])
ab = pd.DataFrame(ab_rows, columns=["operator_id", "variant", "assigned_date", "auto_recharge_enabled"])

# Simulated net revenue (assumed take rates, for ARPU analysis)
activity["net_revenue"] = (activity.toll_gtv * 0.004 + activity.fuel_spend * 0.006
                           + activity.gps_devices * 300 + activity.loads_booked * 150).round(2)

ops_out = ops.drop(columns=["second_service_ts"]).copy()
ops_out["second_service_ts"] = ops["second_service_ts"]
for c in ["signup_ts", "second_service_ts"]:
    ops_out[c] = ops_out[c].dt.strftime("%Y-%m-%d %H:%M:%S")
onboarding["event_ts"] = onboarding.event_ts.dt.strftime("%Y-%m-%d %H:%M:%S")
recharges["recharge_ts"] = recharges.recharge_ts.dt.strftime("%Y-%m-%d %H:%M:%S")

tables = {"operators": ops_out, "onboarding_events": onboarding, "fastag_recharges": recharges,
          "monthly_activity": activity, "ab_test_assignments": ab}
with sqlite3.connect(DATA / "superapp.db") as con:
    for name, df in tables.items():
        df.to_csv(DATA / f"{name}.csv", index=False)
        df.to_sql(name, con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS ix_rc_op ON fastag_recharges(operator_id)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_act_op ON monthly_activity(operator_id, month)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_act_month ON monthly_activity(month)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ev_op ON onboarding_events(operator_id, stage)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_rc_ts ON fastag_recharges(recharge_ts)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ab_op ON ab_test_assignments(operator_id)")
for name, df in tables.items():
    print(f"{name:<22}{len(df):>10,} rows")
with sqlite3.connect(DATA / "superapp.db") as con:
    con.execute("VACUUM")
