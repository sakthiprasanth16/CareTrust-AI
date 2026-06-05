"""
alert_service.py
Flow:
  1. Log saved → policy_checker.local_policy_check() (zero LLM, pure Python)
  2. If breach found → _call_gemini_for_breach() (one focused LLM call per breach)
  3. Save alert/pre_alert to MongoDB
  4. Return new alerts to frontend for toast display
"""
import os, json, re, time
from datetime import datetime
from backend.services.db import get_db
from backend.services.policy_checker import local_policy_check, retroactive_check_on_toggle
import google.generativeai as genai


# ── Gemini throttle constants ────────────────────────────────────────────────
GEMINI_CALLS_BEFORE_PAUSE = 8   # pause after this many real Gemini calls per scan run
GEMINI_PAUSE_SECONDS      = 10  # seconds to pause

# ── helpers ───────────────────────────────────────────────────────────────────

def _s(doc):
    if doc and "_id" in doc:
        return {k: v for k, v in doc.items() if k != "_id"}
    return doc

def _gemini():
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-2.5-flash-lite")

def _next_id(collection, prefix):
    docs = list(collection.find({}, {"id": 1}))
    nums = []
    for d in docs:
        raw = re.sub(r"[^0-9]", "", str(d.get("id", "")))
        if raw:
            nums.append(int(raw))
    return f"{prefix}{max(nums)+1 if nums else 1}"

def _today():
    return datetime.now().strftime("%Y-%m-%d")


# ── duplicate pre-check (before Gemini) ──────────────────────────────────────

def _already_exists(db, patient_id, policy_name, breach_type):
    """
    Check DB BEFORE calling Gemini.
    Returns True if an alert/pre_alert for this patient+policy already exists today.
    _save_alert/_save_pre_alert keep their own dedup check as a safety backup.
    """
    today = _today()
    if breach_type == "alert":
        return bool(db.alerts.find_one({
            "patient_id":       patient_id,
            "policy_triggered": policy_name,
            "created_at":       {"$gte": today},
        }))
    elif breach_type == "pre_alert":
        return bool(db.pre_alerts.find_one({
            "patient_id":       patient_id,
            "policy_triggered": policy_name,
            "created_at":       {"$gte": today},
        }))
    return False


# ── Gemini prompt — focused, minimal, accurate confidence ─────────────────────

BREACH_SYSTEM_PROMPT = """You are a clinical risk AI for a care home system.
A policy breach has been CONFIRMED by local data analysis. Your job is to generate
clear, professional alert details for the care team.

═══════════════════════════════════════════════════════
CONFIDENCE SCORING — follow these rules exactly
═══════════════════════════════════════════════════════

STEP 1 — Choose base score by policy_type:

A. THRESHOLD policies (fluid, BP, oxygen, sugar, sleep, any numeric field):
   Use the actual_values sent in the payload. For multi-day breaches, use the
   worst (most extreme) value from actual_values for severity calculation.

   For direction = "below" (fluid, sleep, oxygen — lower is worse):
     breach_severity = (threshold_value - worst_actual) / threshold_value * 100
     0% to <15% below  → borderline → base 52–62
     15% to <35% below → moderate   → base 63–73
     35% to <60% below → serious    → base 74–84
     60%+ below        → critical   → base 85–95

   For direction = "above" (BP, sugar — higher is worse):
     breach_severity = (worst_actual - threshold_value) / threshold_value * 100
     0% to <10% above  → borderline → base 52–62
     10% to <25% above → moderate   → base 63–73
     25% to <45% above → serious    → base 74–84
     45%+ above        → critical   → base 85–95

   Threshold multipliers (apply after base):
   + each extra consecutive day beyond minimum alert_days: +3, max +12
   + if all days in window are bad with no gap: +5
   + if evaluation_mode is end_of_day_cumulative: +4 (full day data available)
   - if breach_type is PRE_ALERT: -10

B. YES_NO policies (confusion, appetite_loss, any boolean field):
   No numeric distance. Use consecutive_days as base:
     1 day  → base 45–52
     2 days → base 55–63
     3 days → base 65–73
     4 days → base 74–82
     5+ days → base 83–92

   Yes/No multipliers (apply after base):
   For each day in per_day_votes:
     - if yes_ratio > 0.50 and < 0.75: +3 for that day
     - if yes_ratio >= 0.75: +5 for that day
   Total daily majority bonus capped at +10 across all days.
   - if tie_rule is "breach" and any day had equal yes/no: -8
   - if breach_type is PRE_ALERT: -10

STEP 2 — Apply hard caps (always):
   - Never below 45
   - Never above 95
   - PRE_ALERT never above 72
   - ALERT never below 52
   - Final confidence must be an integer

STEP 3 — Write reasoning as a clinical observation, not a scoring explanation.
   - Write as if a senior nurse is explaining the concern to a doctor
   - Never mention evaluation_mode, multipliers, confidence bands, or any
     internal system terms — these are backend mechanics, not clinical facts
   - Focus on: what is the clinical risk, why it matters for this specific
     patient given their diagnosis, what could happen if not addressed
   - If the policy scope is "patient" (patient-specific), mention it is per
     the patient's individual care plan or doctor's instruction
   - Keep it 1–2 sentences, plain English that any care staff can understand

═══════════════════════════════════════════════════════
EVIDENCE RULES — follow exactly
═══════════════════════════════════════════════════════
Always produce exactly 3 or 4 bullets. Never more, never fewer (unless notes
are absent — then 3 bullets only). Follow this fixed structure:

BULLET 1 — Run summary (always required):
  State the field name, how many consecutive days breached, and the date range.
  For PRE_ALERT use "approaching threshold" instead of "below/above threshold".
  Examples:
    "Fluid intake below 1000ml for 3 consecutive days (30 May – 01 Jun)"
    "Systolic BP above 160mmHg for 5 consecutive days (27 May – 31 May)"
    "Confusion recorded on 2 consecutive days (31 May – 01 Jun)"
    "Oxygen saturation approaching threshold for 2 days (31 May – 01 Jun)"

BULLET 2 — Worst reading (always required):
  For THRESHOLD policies:
    Show the single worst value across all breached days, its date, and the
    % deviation from threshold.
    For direction "below": worst = lowest value.
    For direction "above": worst = highest value.
    Use the unit from the policy threshold label if available.
    Examples:
      "Lowest recorded: 370ml on 01 Jun — 63% below the 1000ml daily target"
      "Highest recorded: 182mmHg on 31 May — 14% above the 160mmHg threshold"
      "Lowest SpO2: 91% on 30 May — 4% below the 95% safe threshold"
  For YES_NO policies:
    Show the date with the highest yes count and how many logs confirmed it.
    If tie_rule is "breach" and that day was a tie, note it clearly.
    Examples:
      "Strongest confirmation: 01 Jun — confusion noted in 3 of 4 care logs"
      "31 May — confusion recorded in 2 of 2 logs (all entries confirmed)"
      "30 May — equal yes/no votes (2 of 4 logs), counted as breach per policy"

BULLET 3 — Trend or per-day breakdown (always required):
  For THRESHOLD policies:
    Show how values changed across all breached days oldest to newest using
    actual dates. Use → between values.
    For end_of_day_cumulative fields (e.g. fluid_intake_ml where day value
    is a daily total): label as daily totals.
    For instant fields (e.g. BP, oxygen where day value is worst reading):
    label as daily readings.
    Examples:
      "Daily totals: 980ml (30 May) → 860ml (31 May) → 370ml (01 Jun)"
      "Daily readings: 168mmHg (29 May) → 174mmHg (30 May) → 182mmHg (31 May)"
      "SpO2 readings: 93% (30 May) → 92% (31 May)"
    For 5+ day breaches, show all dates and values in the same → format —
    do not truncate or summarise — the trend line is the full evidence.
  For YES_NO policies:
    Show each breached date and the log count for that day.
    Examples:
      "30 May: 2 of 3 logs confirmed · 31 May: 3 of 4 logs confirmed"
      "31 May: 1 of 2 logs confirmed · 01 Jun: 3 of 4 logs confirmed"

BULLET 4 — Nurse notes (only if real notes exist in breached_logs[].notes):
  Combine all non-empty, non-generic notes from ALL breached days into one
  bullet. Separate multiple notes with " · " between them.
  Never invent, paraphrase, or generalise notes.
  Never include empty strings or notes like "none", "n/a", "-".
  If no real notes exist across any breached day, omit this bullet entirely
  (output only 3 bullets).
  Examples:
    "Staff notes: patient refusing drinks · refused evening fluids"
    "Staff notes: patient disoriented during morning round · unable to
     recognise family member on 31 May"

IMPORTANT: Return ONLY valid JSON. No markdown, no backticks, no explanation.

JSON schema:
{
  "title": "short alert title (max 6 words)",
  "severity": "high" | "medium" | "low",
  "confidence": 0-100,
  "evidence": [
    "bullet 1 — run summary",
    "bullet 2 — worst reading or strongest yes/no day",
    "bullet 3 — trend line or per-day yes/no breakdown",
    "bullet 4 — staff notes combined (omit if no real notes)"
  ],
  "reasoning": "1-2 sentences clinical observation, plain English, no system jargon"
}"""

def _call_gemini_for_breach(patient, breach):
    """
    Focused LLM call — only sends the confirmed breach data.
    No extra logs, no other policies.
    Extended payload includes policy direction, evaluation_mode, alert_days,
    tie_rule, and per_day_votes so Gemini can apply real-world confidence scoring.
    """
    policy = breach["policy"]

    # Build per_day_votes for yes/no policies so Gemini can calc majority bonus
    per_day_votes = []
    if policy.get("policy_type") == "yes_no":
        log_field = policy.get("log_field", "")
        for log_entry in breach.get("breached_logs", []):
            date = log_entry.get("date", "")
            # breached_logs carry notes but not raw votes — reconstruct from value
            # actual_values for yes_no are always "Yes" strings, so use note context
            # We pass a simplified structure; day_logs not available here so
            # indicate unanimous (True) since checker already confirmed majority
            per_day_votes.append({
                "date":      date,
                "yes":       1,
                "no":        0,
                "yes_ratio": 1.0,
                "note":      "majority confirmed by local checker"
            })

    user_payload = {
        "patient": {
            "name":      patient.get("name"),
            "age":       patient.get("age"),
            "gender":    patient.get("gender"),
            "diagnosis": patient.get("diagnosis"),
        },
        "breach_type":      breach["breach_type"].upper(),
        "policy": {
            "name":            policy.get("name"),
            "description":     policy.get("description"),
            "policy_type":     policy.get("policy_type"),
            "threshold":       policy.get("threshold"),
            "direction":       policy.get("direction", "below"),
            "evaluation_mode": policy.get("evaluation_mode", "instant"),
            "alert_days":      policy.get("alert_days", 3),
            "tie_rule":        policy.get("tie_rule", "breach"),
        },
        "breached_logs":    breach["breached_logs"],
        "consecutive_days": breach["consecutive_days"],
        "actual_values":    breach["actual_values"],
        "threshold_value":  breach["threshold_value"],
        "per_day_votes":    per_day_votes if per_day_votes else None,
    }

    try:
        model = _gemini()
        raw   = model.generate_content(
            [BREACH_SYSTEM_PROMPT, json.dumps(user_payload, indent=2)],
            generation_config={"temperature": 0.2},
        ).text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        print(f"[alert_service] Gemini error: {e}")
        return None


# ── save helpers ──────────────────────────────────────────────────────────────

def _save_alert(db, patient, breach, gemini_result):
    title = gemini_result.get("title", "Clinical Alert")
    today = _today()
    # Dedup: same patient + same policy + same day
    if db.alerts.find_one({
        "patient_id":       patient["id"],
        "policy_triggered": breach["policy"].get("name"),
        "created_at":       {"$gte": today},
    }):
        return None

    now = datetime.now().isoformat(timespec="seconds")
    doc = {
        "id":               _next_id(db.alerts, "al"),
        "patient_id":       patient["id"],
        "patient_name":     patient.get("name", ""),
        "room_no":          patient.get("room_no", ""),
        "nurse_assigned":   patient.get("assigned_nurse"),
        "title":            title,
        "severity":         gemini_result.get("severity", "medium"),
        "confidence":       gemini_result.get("confidence", 70),
        "evidence":         gemini_result.get("evidence", []),
        "reasoning":        gemini_result.get("reasoning", ""),
        "status":           "new",
        "policy_triggered": breach["policy"].get("name", ""),
        "type":             "alert",
        "triggered_by":     "system",
        "created_at":       now,
    }
    db.alerts.insert_one(doc)
    return _s(doc)


def _save_pre_alert(db, patient, breach, gemini_result):
    title = gemini_result.get("title", "Pre-Alert")
    today = _today()
    if db.pre_alerts.find_one({
        "patient_id":       patient["id"],
        "policy_triggered": breach["policy"].get("name"),
        "created_at":       {"$gte": today},
    }):
        return None

    now = datetime.now().isoformat(timespec="seconds")
    doc = {
        "id":                     _next_id(db.pre_alerts, "pa"),
        "patient_id":             patient["id"],
        "patient_name":           patient.get("name", ""),
        "room_no":                patient.get("room_no", ""),
        "nurse_assigned":         patient.get("assigned_nurse"),
        "title":                  title if title.startswith("Pre-Alert") else f"Pre-Alert: {title}",
        "severity":               gemini_result.get("severity", "medium"),
        "confidence":             gemini_result.get("confidence", 60),
        "evidence":               gemini_result.get("evidence", []),
        "reasoning":              gemini_result.get("reasoning", ""),
        "status":                 "new",
        "policy_triggered":       breach["policy"].get("name", ""),
        "type":                   "pre_alert",
        "triggered_by":           None,
        "visible_to_nurse":       False,
        "trigger_message_active": False,
        "created_at":             now,
    }
    db.pre_alerts.insert_one(doc)
    return _s(doc)


# ── public: run scan for one patient ─────────────────────────────────────────

def run_auto_scan(patient_id=None):
    """
    Called after every log save.
    1. Local checker finds breaches (zero LLM)
    2. For each breach → one focused Gemini call
    3. Save and return results
    """
    db = get_db()
    created_alerts    = []
    created_prealerts = []

    if patient_id:
        patients = [p for p in [db.patients.find_one({"id": patient_id})] if p]
    else:
        patients = list(db.patients.find({"status": {"$ne": "deleted"}}))

    gemini_call_count = 0  # resets to 0 every time run_auto_scan is called

    for patient in patients:
        pid = patient["id"]
        breaches = local_policy_check(pid)

        for breach in breaches:
            policy_name  = breach["policy"].get("name", "")
            breach_type  = breach["breach_type"]

            # Pre-check DB BEFORE calling Gemini — skip if already exists today
            if _already_exists(db, pid, policy_name, breach_type):
                print(f"[alert_service] skip Gemini — {breach_type} already exists today for {pid} / {policy_name}")
                continue

            # Throttle: pause after every GEMINI_CALLS_BEFORE_PAUSE real calls
            gemini_call_count += 1
            print(f"[alert_service] Gemini call {gemini_call_count} for {pid} / {policy_name}")
            if gemini_call_count > 1 and (gemini_call_count - 1) % GEMINI_CALLS_BEFORE_PAUSE == 0:
                print(f"[alert_service] Gemini throttle pause {GEMINI_PAUSE_SECONDS}s after {GEMINI_CALLS_BEFORE_PAUSE} calls")
                time.sleep(GEMINI_PAUSE_SECONDS)

            gemini_result = _call_gemini_for_breach(patient, breach)
            if not gemini_result:
                continue

            if breach_type == "alert":
                saved = _save_alert(db, patient, breach, gemini_result)
                if saved:
                    created_alerts.append(saved)
                    _push_notification(db, patient, saved, "alert")

            elif breach_type == "pre_alert":
                saved = _save_pre_alert(db, patient, breach, gemini_result)
                if saved:
                    created_prealerts.append(saved)

    return {
        "created_alerts":    created_alerts,
        "created_prealerts": created_prealerts,
    }


def run_retroactive_scan(policy_id):
    """
    Called when a policy is toggled ON.
    Checks all patients' existing logs against this policy.
    """
    db = get_db()
    created_alerts    = []
    created_prealerts = []

    patient_breaches   = retroactive_check_on_toggle(policy_id)
    gemini_call_count  = 0  # resets to 0 every time run_retroactive_scan is called

    for patient_id, breach in patient_breaches:
        patient = db.patients.find_one({"id": patient_id})
        if not patient:
            continue

        policy_name = breach["policy"].get("name", "")
        breach_type = breach["breach_type"]

        # Pre-check DB BEFORE calling Gemini — skip if already exists today
        if _already_exists(db, patient_id, policy_name, breach_type):
            print(f"[alert_service] skip Gemini — {breach_type} already exists today for {patient_id} / {policy_name}")
            continue

        # Throttle: pause after every GEMINI_CALLS_BEFORE_PAUSE real calls
        gemini_call_count += 1
        print(f"[alert_service] Gemini call {gemini_call_count} for {patient_id} / {policy_name}")
        if gemini_call_count > 1 and (gemini_call_count - 1) % GEMINI_CALLS_BEFORE_PAUSE == 0:
            print(f"[alert_service] Gemini throttle pause {GEMINI_PAUSE_SECONDS}s after {GEMINI_CALLS_BEFORE_PAUSE} calls")
            time.sleep(GEMINI_PAUSE_SECONDS)

        gemini_result = _call_gemini_for_breach(patient, breach)
        if not gemini_result:
            continue

        if breach_type == "alert":
            saved = _save_alert(db, patient, breach, gemini_result)
            if saved:
                created_alerts.append(saved)
                _push_notification(db, patient, saved, "alert")
        elif breach_type == "pre_alert":
            saved = _save_pre_alert(db, patient, breach, gemini_result)
            if saved:
                created_prealerts.append(saved)

    return {
        "created_alerts":    created_alerts,
        "created_prealerts": created_prealerts,
        "retroactive":       True,
    }


def _push_notification(db, patient, alert_doc, kind):
    """Push notification to assigned nurse and ChiefMary when alert created."""
    recipients = [u for u in [patient.get("assigned_nurse"), "ChiefMary"] if u]
    if not recipients:
        return
    nid = _next_id(db.notifications, "n")
    db.notifications.insert_one({
        "id":         nid,
        "to":         recipients,
        "message":    f"New {kind} for {patient.get('name','')}: {alert_doc.get('title','')}",
        "type":       "alert",
        "alert_id":   alert_doc.get("id"),
        "read_by":    [],
        "acked_by":   [],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })


# ── public list endpoints ─────────────────────────────────────────────────────

def list_alerts(worker=None, role=None):
    db = get_db()
    q  = {}
    if role in ("nurse", "caretaker"):
        q["nurse_assigned"] = worker
    return [_s(d) for d in db.alerts.find(q).sort("created_at", -1)]


def list_pre_alerts(worker=None, role=None):
    db = get_db()
    if role == "caretaker":
        return []
    q = {}
    if role == "nurse":
        q["nurse_assigned"]   = worker
        q["visible_to_nurse"] = True
    return [_s(d) for d in db.pre_alerts.find(q).sort("created_at", -1)]


def trigger_pre_alert(pre_alert_id, triggered_by):
    db  = get_db()
    pa  = db.pre_alerts.find_one({"id": pre_alert_id})
    if not pa:
        return {}
    db.pre_alerts.update_one({"id": pre_alert_id}, {"$set": {
        "triggered_by":           triggered_by,
        "visible_to_nurse":       True,
        "status":                 "triggered",
        "trigger_message_active": True,
    }})
    recipients = [
        u for u in [pa.get("nurse_assigned"), "ChiefMary", "DrArun"]
        if u and u != triggered_by
    ]
    nid = _next_id(db.notifications, "n")
    db.notifications.insert_one({
        "id":             nid,
        "to":             recipients,
        "message":        f"Pre-alert triggered for {pa['patient_name']} ({pa['title']})",
        "type":           "pre_alert_trigger",
        "pre_alert_id":   pre_alert_id,
        "notify_back_to": [triggered_by],
        "read_by":        [],
        "acked_by":       [],
        "created_at":     datetime.now().isoformat(timespec="seconds"),
    })
    return _s(db.pre_alerts.find_one({"id": pre_alert_id}))
