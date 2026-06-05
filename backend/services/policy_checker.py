"""
policy_checker.py
Window-based check — reads last alert_days calendar dates only.
Missing log on any day in window = that day is NOT bad (run broken).
Zero LLM calls. Called on every care log save.
"""
from datetime import datetime, timedelta
from collections import defaultdict
from backend.services.db import get_db


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _extract_numeric(log, field, extract=None):
    # Check top-level first, then extra_fields for custom manager-added fields
    raw = log.get(field)
    if raw is None:
        raw = (log.get("extra_fields") or {}).get(field)
    if raw is None:
        return None
    if extract == "systolic" and "/" in str(raw):
        try:
            return float(str(raw).split("/")[0])
        except Exception:
            return None
    # Also auto-detect BP format
    if field == "blood_pressure" and "/" in str(raw):
        try:
            return float(str(raw).split("/")[0])
        except Exception:
            return None
    try:
        return float(str(raw).replace(",", "."))
    except Exception:
        return None


def _clean(doc):
    return {k: v for k, v in doc.items() if k != "_id"}


def _window_dates(alert_days):
    """
    Return list of alert_days dates ending today (inclusive), oldest first.
    e.g. alert_days=3, today=May 28 → [May 26, May 27, May 28]
    """
    today = datetime.now().date()
    return [today - timedelta(days=i) for i in range(alert_days - 1, -1, -1)]


# ── Threshold policy ──────────────────────────────────────────────────────────

def check_threshold_policy(logs_by_date, policy):
    """
    1. Build window of last alert_days dates ending today
    2. For each date in window:
         - no log on that date  → not bad (missing = break)
         - log exists, value OK → not bad
         - log exists, value bad → bad
    3. Count how many of the LAST consecutive dates (from today backwards) are bad
    4. ALL alert_days bad  → alert
       last prealert_days bad → pre_alert
       anything else       → None
    """
    log_field       = policy.get("log_field", "")
    extract         = policy.get("extract")
    threshold       = float(policy.get("check_value") or 0)
    alert_days      = int(policy.get("alert_days", 3))
    pre_days        = int(policy.get("prealert_days", 2))
    direction       = policy.get("direction", "below")
    eval_mode       = policy.get("evaluation_mode", "instant")
    cutoff_time_str = policy.get("cutoff_time", "20:00")

    # For end_of_day_cumulative: if current time is before cutoff_time,
    # remove today from logs so it counts as a missing day — no breach yet.
    # After cutoff_time, today's logs are included and summed normally.
    if eval_mode == "end_of_day_cumulative":
        try:
            ch, cm = map(int, cutoff_time_str.split(":"))
            now    = datetime.now()
            past_cutoff = (now.hour, now.minute) >= (ch, cm)
        except Exception:
            past_cutoff = True
        if not past_cutoff:
            today        = datetime.now().date()
            logs_by_date = {k: v for k, v in logs_by_date.items() if k != today}

    window     = _window_dates(alert_days)
    daily_vals = {}

    # Step 1 — classify each date in window
    bad_dates = []          # ordered oldest→newest, only bad ones at the tail
    for dt in window:
        logs   = logs_by_date.get(dt, [])
        values = [_extract_numeric(lg, log_field, extract) for lg in logs]
        values = [v for v in values if v is not None]

        if not values:
            # no log or field missing on this date → not bad
            bad_dates = []  # reset — missing breaks the run
            continue

        if direction == "above":
            day_val = max(values)
            is_bad  = day_val > threshold
        else:
            day_val = sum(values) if log_field == "fluid_intake_ml" else min(values)
            is_bad  = day_val < threshold

        if is_bad:
            daily_vals[dt] = day_val
            bad_dates.append(dt)
        else:
            bad_dates = []  # good day resets the run

    # Step 2 — bad_dates now holds the most recent unbroken run
    run_len   = len(bad_dates)
    run_dates = bad_dates

    if run_len >= alert_days:
        return "alert",     run_dates, daily_vals
    if run_len >= pre_days:
        return "pre_alert", run_dates, daily_vals
    return None, [], {}


# ── Yes/No policy ─────────────────────────────────────────────────────────────

def check_yes_no_policy(logs_by_date, policy):
    """
    Same window logic for boolean fields.
    Majority vote per day → bad or not.
    Missing log resets the run.
    """
    log_field  = policy.get("log_field", "confusion")
    tie_rule   = policy.get("tie_rule", "breach")
    alert_days = int(policy.get("alert_days", 2))
    pre_days   = int(policy.get("prealert_days", 1))

    window    = _window_dates(alert_days)
    bad_dates = []

    for dt in window:
        logs     = logs_by_date.get(dt, [])
        # Check top-level first, then extra_fields for custom fields
        def _bv(lg, f):
            v = lg.get(f)
            if v is None:
                v = (lg.get("extra_fields") or {}).get(f)
            return v

        relevant = [lg for lg in logs if _bv(lg, log_field) is not None]

        if not relevant:
            bad_dates = []  # missing → reset run
            continue

        yes = sum(1 for lg in relevant if _bv(lg, log_field) is True)
        no  = sum(1 for lg in relevant if _bv(lg, log_field) is False)

        if yes > no or (yes == no and tie_rule == "breach"):
            bad_dates.append(dt)
        else:
            bad_dates = []  # good day → reset run

    run_len   = len(bad_dates)
    run_dates = bad_dates

    if run_len >= alert_days:
        return "alert",     run_dates
    if run_len >= pre_days:
        return "pre_alert", run_dates
    return None, []


# ── Main entry point ──────────────────────────────────────────────────────────

def local_policy_check(patient_id):
    """
    Called on every log save. Zero LLM.
    Fetches only logs within the max window across all active policies.
    Policy edits in MongoDB take effect immediately on next log save.
    """
    db = get_db()

    policies = list(db.policies.find({
        "active": True,
        "$or": [
            {"scope": "organization"},
            {"scope": "patient", "patient_id": patient_id},
        ]
    }))
    if not policies:
        return []

    # Fetch logs from start of oldest required date (not current clock time)
    # e.g. alert_days=3, today=May 28 → window=[May 26,27,28] → cutoff=May 26 00:00:00
    max_window  = max(int(p.get("alert_days", 3)) for p in policies)
    cutoff_date = datetime.now().date() - timedelta(days=max_window - 1)
    cutoff      = datetime.combine(cutoff_date, datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S")

    all_logs = list(
        db.care_logs.find({
            "patient_id": patient_id,
            "created_at": {"$gte": cutoff},
        }).sort("created_at", 1)
    )
    if not all_logs:
        return []

    logs_by_date = defaultdict(list)
    for lg in all_logs:
        dt = _parse_date(lg.get("created_at", ""))
        if dt:
            logs_by_date[dt].append(lg)

    breaches = []

    for policy in policies:
        ptype = policy.get("policy_type", "none")

        if ptype == "threshold":
            result, run_dates, daily_vals = check_threshold_policy(logs_by_date, policy)
            if result:
                relevant_logs = []
                for dt in run_dates:
                    day_logs = logs_by_date.get(dt, [])
                    notes    = "; ".join(lg.get("notes", "") for lg in day_logs if lg.get("notes"))
                    relevant_logs.append({
                        "date":  str(dt),
                        "value": daily_vals.get(dt, 0),
                        "field": policy.get("log_field", ""),
                        "notes": notes,
                    })
                breaches.append({
                    "breach_type":      result,
                    "policy":           _clean(policy),
                    "breached_logs":    relevant_logs,
                    "consecutive_days": len(run_dates),
                    "actual_values":    [daily_vals.get(d, 0) for d in run_dates],
                    "threshold_value":  float(policy.get("check_value") or 0),
                })

        elif ptype == "yes_no":
            result, run_dates = check_yes_no_policy(logs_by_date, policy)
            if result:
                relevant_logs = []
                for dt in run_dates:
                    day_logs = logs_by_date.get(dt, [])
                    notes    = "; ".join(lg.get("notes", "") for lg in day_logs if lg.get("notes"))
                    relevant_logs.append({
                        "date":  str(dt),
                        "value": True,
                        "field": policy.get("log_field", ""),
                        "notes": notes,
                    })
                breaches.append({
                    "breach_type":      result,
                    "policy":           _clean(policy),
                    "breached_logs":    relevant_logs,
                    "consecutive_days": len(run_dates),
                    "actual_values":    ["Yes"] * len(run_dates),
                    "threshold_value":  int(policy.get("alert_days", 2)),
                })

    return breaches


# ── Retroactive check when policy toggled ON ──────────────────────────────────

def retroactive_check_on_toggle(policy_id):
    """
    Called when a policy is toggled ON.
    Same window logic — checks last alert_days days for all active patients.
    """
    db     = get_db()
    policy = db.policies.find_one({"id": policy_id})
    if not policy:
        return []

    alert_days  = int(policy.get("alert_days", 3))
    cutoff_date = datetime.now().date() - timedelta(days=alert_days - 1)
    cutoff      = datetime.combine(cutoff_date, datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S")
    patients   = list(db.patients.find({"status": {"$ne": "deleted"}}))
    results    = []

    for patient in patients:
        pid      = patient["id"]
        all_logs = list(db.care_logs.find({
            "patient_id": pid,
            "created_at": {"$gte": cutoff},
        }).sort("created_at", 1))
        if not all_logs:
            continue

        logs_by_date = defaultdict(list)
        for lg in all_logs:
            dt = _parse_date(lg.get("created_at", ""))
            if dt:
                logs_by_date[dt].append(lg)

        ptype = policy.get("policy_type", "none")

        if ptype == "threshold":
            result, run_dates, daily_vals = check_threshold_policy(logs_by_date, policy)
            if result:
                relevant_logs = [{"date": str(d), "value": daily_vals.get(d, 0)} for d in run_dates]
                results.append((pid, {
                    "breach_type":      result,
                    "policy":           _clean(policy),
                    "breached_logs":    relevant_logs,
                    "consecutive_days": len(run_dates),
                    "actual_values":    [daily_vals.get(d, 0) for d in run_dates],
                    "threshold_value":  float(policy.get("check_value") or 0),
                }))

        elif ptype == "yes_no":
            result, run_dates = check_yes_no_policy(logs_by_date, policy)
            if result:
                results.append((pid, {
                    "breach_type":      result,
                    "policy":           _clean(policy),
                    "breached_logs":    [{"date": str(d), "value": True} for d in run_dates],
                    "consecutive_days": len(run_dates),
                    "actual_values":    ["Yes"] * len(run_dates),
                    "threshold_value":  int(policy.get("alert_days", 2)),
                }))

    return results
