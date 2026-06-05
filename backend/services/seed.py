"""
seed.py — Run once: python -m backend.services.seed

d() calculates relative to TODAY automatically — works any day you run it.

Today = d(0) → NO logs → add manually to trigger alerts/pre-alerts
d(1)  = yesterday
d(2)  = day before yesterday

ALERT patients (add today's bad log → alert fires immediately):
  p1 Sarah   → Hydration SOP   (alert_days=3, cumulative 20:00)
               d(2) fluid 650+250=900ml ✗  d(1) fluid 600+260=860ml ✗
               → add today fluid < 1000ml → 3 consecutive bad days → ALERT
               NOTE: cumulative mode — fires after 20:00 or on next log if past cutoff

  p2 Rahul   → Patient BP Watch (alert_days=3)
               d(2) BP 168 ✗  d(1) BP 172 ✗
               → add today BP > 160 → ALERT

  p3 Meena   → Sugar SOP       (alert_days=2)
               d(1) sugar 218 ✗
               → add today sugar > 200 → ALERT

  p4 James   → Oxygen SOP      (alert_days=2)
               d(1) oxygen 93 ✗
               → add today oxygen < 95 → ALERT

PRE-ALERT patients (add today's bad log → pre-alert fires, NOT full alert):
  p5 Lakshmi → 8-Hour Sleep SOP (prealert_days=1, alert_days=2)
               d(1) sleep 8.5h ✓ GOOD  ← keeps it as pre-alert only
               → add today sleep < 8h → PRE-ALERT only

  p6 David   → Confusion Threshold (prealert_days=1, alert_days=2)
               d(1) confusion False ✓ GOOD  ← keeps it as pre-alert only
               → add today confusion=True → PRE-ALERT only

alerts=[]  pre_alerts=[]  — both start empty, generated when you log today.
"""
from datetime import datetime, timedelta
from backend.services.db import get_db


def d(days_ago, hour=8, minute=0):
    dt = datetime.now() - timedelta(days=days_ago)
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


USERS = [
    {"id":"u1","username":"NurseEmma",     "password":"nurse123",      "role":"nurse",           "name":"Nurse Emma",       "age":29,"active":True},
    {"id":"u2","username":"DrArun",         "password":"doctor123",     "role":"doctor_assistant","name":"Dr. Arun",         "age":34,"active":True},
    {"id":"u3","username":"ManagerPriya",   "password":"manager123",    "role":"manager",         "name":"Manager Priya",    "age":41,"active":True},
    {"id":"u4","username":"AdminUser",      "password":"admin123",      "role":"admin",           "name":"Admin User",       "age":38,"active":True},
    {"id":"u5","username":"NurseSara",      "password":"nurse2123",     "role":"nurse",           "name":"Nurse Sara",       "age":31,"active":True},
    {"id":"u6","username":"ChiefMary",      "password":"chiefnurse123", "role":"chief_nurse",     "name":"Chief Nurse Mary", "age":45,"active":True},
    {"id":"u7","username":"CaretakerRavi",  "password":"caretaker123",  "role":"caretaker",       "name":"Caretaker Ravi",  "age":27,"active":True},
    {"id":"u8","username":"CaretakerLatha", "password":"caretaker223",  "role":"caretaker",       "name":"Caretaker Latha", "age":30,"active":True},
]

ROOMS = [
    {"id":"r1","room_no":"401","status":"admitted", "patient_id":"p1"},
    {"id":"r2","room_no":"402","status":"admitted", "patient_id":"p2"},
    {"id":"r3","room_no":"403","status":"admitted", "patient_id":"p3"},
    {"id":"r4","room_no":"404","status":"admitted", "patient_id":"p4"},
    {"id":"r5","room_no":"405","status":"admitted", "patient_id":"p5"},
    {"id":"r6","room_no":"406","status":"admitted", "patient_id":"p6"},
    {"id":"r7","room_no":"407","status":"available","patient_id":None},
    {"id":"r8","room_no":"408","status":"available","patient_id":None},
]

PATIENTS = [
    {"id":"p1","name":"Sarah Jenkins","age":78,"gender":"Female","room_no":"401","diagnosis":"UTI Risk",           "assigned_nurse":"NurseEmma","caretaker":None,            "pinned":True, "status":"active"},
    {"id":"p2","name":"Rahul Kumar",  "age":58,"gender":"Male",  "room_no":"402","diagnosis":"Hypertension",       "assigned_nurse":"NurseEmma","caretaker":None,            "pinned":False,"status":"active"},
    {"id":"p3","name":"Meena Devi",   "age":65,"gender":"Female","room_no":"403","diagnosis":"Diabetes Type 2",    "assigned_nurse":"NurseSara", "caretaker":None,            "pinned":False,"status":"active"},
    {"id":"p4","name":"James Carter", "age":71,"gender":"Male",  "room_no":"404","diagnosis":"Cardiac Monitoring", "assigned_nurse":"NurseSara", "caretaker":None,            "pinned":False,"status":"active"},
    {"id":"p5","name":"Lakshmi Nair", "age":74,"gender":"Female","room_no":"405","diagnosis":"Fall Risk",          "assigned_nurse":"NurseEmma","caretaker":"CaretakerRavi", "pinned":False,"status":"active"},
    {"id":"p6","name":"David Roy",    "age":69,"gender":"Male",  "room_no":"406","diagnosis":"Medication Review",  "assigned_nurse":"NurseSara", "caretaker":"CaretakerLatha","pinned":False,"status":"active"},
]

LOG_FIELDS = [
    {"id":"lf1","field":"fluid_intake_ml","label":"Fluid Intake",   "type":"threshold","unit":"ml",   "description":"Total fluid consumed per day","active":True},
    {"id":"lf2","field":"sugar_level",    "label":"Sugar Level",    "type":"threshold","unit":"mg/dL","description":"Blood sugar reading","active":True},
    {"id":"lf3","field":"blood_pressure", "label":"Blood Pressure", "type":"threshold","unit":"mmHg", "description":"Systolic blood pressure","extract":"systolic","active":True},
    {"id":"lf4","field":"sleep_hours",    "label":"Sleep Hours",    "type":"threshold","unit":"hours","description":"Hours slept last night","active":True},
    {"id":"lf5","field":"oxygen_level",   "label":"Oxygen Level",   "type":"threshold","unit":"%",    "description":"Blood oxygen saturation","active":True},
    {"id":"lf6","field":"confusion",      "label":"Confusion Noted","type":"yes_no",   "unit":None,   "description":"Whether patient showed confusion","active":True},
]

POLICIES = [
    # pol1 — Hydration SOP: alert_days=3, prealert_days=2
    # window = last 3 days. p1 has bad days 3,2,1 → ALERT on today's log
    {
        "id":"pol1","name":"Hydration SOP",
        "policy_type":"threshold","log_field":"fluid_intake_ml",
        "threshold":"Below 1000ml/day","check_value":1000.0,
        "alert_days":3,"prealert_days":2,
        "description":"Alert if fluid intake below 1000ml for 3 consecutive days in window",
        "active":True,"scope":"organization","patient_id":None,"direction":"below",
        "evaluation_mode":"end_of_day_cumulative","cutoff_time":"20:00",
    },
    # pol2 — Confusion Threshold: alert_days=2, prealert_days=1
    # window = last 2 days. p6 has bad day1 only, good day2 → PRE-ALERT on today's log
    {
        "id":"pol2","name":"Confusion Threshold",
        "policy_type":"yes_no","log_field":"confusion",
        "threshold":"2 consecutive days","check_value":None,
        "alert_days":2,"prealert_days":1,"tie_rule":"breach",
        "description":"Alert if confusion majority-reported for 2 consecutive days in window",
        "active":True,"scope":"organization","patient_id":None,
        "evaluation_mode":"instant","cutoff_time":None,
    },
    # pol3 — 8-Hour Sleep SOP: alert_days=2, prealert_days=1
    # window = last 2 days. p5 has bad day1 only, good day2 → PRE-ALERT on today's log
    {
        "id":"pol3","name":"8-Hour Sleep SOP",
        "policy_type":"threshold","log_field":"sleep_hours",
        "threshold":"Below 8 hours/night","check_value":8.0,
        "alert_days":2,"prealert_days":1,
        "description":"Alert if sleep below 8 hours for 2 consecutive days in window",
        "active":True,"scope":"organization","patient_id":None,"direction":"below",
        "evaluation_mode":"instant","cutoff_time":None,
    },
    # pol4 — Sugar SOP: alert_days=2, prealert_days=1
    # window = last 2 days. p3 has bad days 2,1 → ALERT on today's log
    {
        "id":"pol4","name":"Sugar SOP",
        "policy_type":"threshold","log_field":"sugar_level",
        "threshold":"Above 200 mg/dL","check_value":200.0,
        "alert_days":2,"prealert_days":1,
        "description":"Alert if post-meal sugar exceeds 200mg/dL for 2 consecutive days in window",
        "active":True,"scope":"organization","patient_id":None,"direction":"above",
        "evaluation_mode":"instant","cutoff_time":None,
    },
    # pol5 — Patient BP Watch (p2 only): alert_days=3, prealert_days=2
    # window = last 3 days. p2 has bad days 3,2,1 → ALERT on today's log
    {
        "id":"pol5","name":"Patient BP Watch",
        "policy_type":"threshold","log_field":"blood_pressure",
        "threshold":"Systolic above 160 mmHg","check_value":160.0,
        "alert_days":3,"prealert_days":2,
        "description":"Alert if systolic BP exceeds 160mmHg for 3 consecutive days — Rahul Kumar",
        "active":True,"scope":"patient","patient_id":"p2","direction":"above",
        "extract":"systolic","evaluation_mode":"instant","cutoff_time":None,
    },
    # pol6 — Oxygen SOP: alert_days=2, prealert_days=1
    # window = last 2 days. p4 has bad days 2,1 → ALERT on today's log
    {
        "id":"pol6","name":"Oxygen SOP",
        "policy_type":"threshold","log_field":"oxygen_level",
        "threshold":"Below 95%","check_value":95.0,
        "alert_days":2,"prealert_days":1,
        "description":"Alert if oxygen saturation drops below 95% for 2 consecutive days in window",
        "active":True,"scope":"organization","patient_id":None,"direction":"below",
        "evaluation_mode":"instant","cutoff_time":None,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# CARE LOGS
#
# Today = d(0) — NO logs, you add manually
# Yesterday = d(1), day before = d(2)
#
# Window logic (checker takes last alert_days dates ending today):
#
# p1 Sarah  — Hydration ALERT (pol1, alert_days=3, cumulative 20:00)
#   window = [d(2), d(1), d(0)]
#   seed: d(2) fluid 650+250=900ml ✗  d(1) fluid 600+260=860ml ✗
#   today: add fluid < 1000ml → 3rd bad day → ALERT (after 20:00)
#
# p2 Rahul  — BP Watch ALERT (pol5, alert_days=3)
#   window = [d(2), d(1), d(0)]
#   seed: d(2) BP 168 ✗  d(1) BP 172 ✗
#   today: add BP > 160 → 3rd bad day → ALERT
#
# p3 Meena  — Sugar ALERT (pol4, alert_days=2)
#   window = [d(1), d(0)]
#   seed: d(1) sugar 218 ✗
#   today: add sugar > 200 → 2nd bad day → ALERT
#
# p4 James  — Oxygen ALERT (pol6, alert_days=2)
#   window = [d(1), d(0)]
#   seed: d(1) oxygen 93 ✗
#   today: add oxygen < 95 → 2nd bad day → ALERT
#
# p5 Lakshmi — Sleep PRE-ALERT (pol3, alert_days=2, prealert_days=1)
#   window = [d(1), d(0)]
#   seed: d(1) sleep 8.5h ✓ GOOD  ← must be good to prevent alert
#   today: add sleep < 8h → only 1 bad day in window → PRE-ALERT only
#
# p6 David  — Confusion PRE-ALERT (pol2, alert_days=2, prealert_days=1)
#   window = [d(1), d(0)]
#   seed: d(1) confusion False ✓ GOOD  ← must be good to prevent alert
#   today: add confusion=True → only 1 bad day in window → PRE-ALERT only
#
CARE_LOGS = [

    # ── p1 Sarah Jenkins — Hydration ALERT ───────────────────────────────────
    # Days 9→3: healthy (outside window)
    {"id":"l01","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1200,"food_intake":"Good","blood_pressure":"130/82","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Good intake.",      "created_at":d(9,8)},
    {"id":"l02","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1150,"food_intake":"Good","blood_pressure":"129/81","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Stable.",           "created_at":d(8,8)},
    {"id":"l03","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"131/82","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"All fine.",         "created_at":d(7,8)},
    {"id":"l04","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1180,"food_intake":"Good","blood_pressure":"130/81","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Good hydration.",   "created_at":d(6,8)},
    {"id":"l05","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1200,"food_intake":"Good","blood_pressure":"130/82","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Drinking well.",    "created_at":d(5,8)},
    {"id":"l06","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1150,"food_intake":"Good","blood_pressure":"131/83","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"On target.",        "created_at":d(4,8)},
    {"id":"l07","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"130/82","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Good.",             "created_at":d(3,8)},
    # d(2): BAD — fluid < 1000ml (650+250=900ml total)
    {"id":"l08","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":650, "food_intake":"Low", "blood_pressure":"131/83","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Fluid dropping — patient refusing drinks. Day 1 of concern.",  "created_at":d(2,8)},
    {"id":"l09","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"dinner",   "fluid_intake_ml":250, "food_intake":"Low", "blood_pressure":"132/83","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":None,"notes":"Refused evening fluids.",                                        "created_at":d(2,19)},
    # d(1): BAD — fluid < 1000ml (600+260=860ml total)
    {"id":"l10","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":600, "food_intake":"Low", "blood_pressure":"130/82","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Still low — 2nd consecutive day below threshold.",               "created_at":d(1,8)},
    {"id":"l11","patient_id":"p1","created_by":"NurseEmma","role":"nurse","meal_type":"dinner",   "fluid_intake_ml":260, "food_intake":"Low", "blood_pressure":"131/82","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":None,"notes":"Minimal evening intake again.",                                  "created_at":d(1,19)},

    # ── p2 Rahul Kumar — BP Watch ALERT ──────────────────────────────────────
    # Days 9→3: healthy BP (outside window)
    {"id":"l12","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"128/80","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"BP good.",          "created_at":d(9,9)},
    {"id":"l13","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"130/82","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"Stable BP.",        "created_at":d(8,9)},
    {"id":"l14","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"132/83","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"Within range.",     "created_at":d(7,9)},
    {"id":"l15","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1090,"food_intake":"Good","blood_pressure":"129/81","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"Good.",             "created_at":d(6,9)},
    {"id":"l16","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"131/82","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"All normal.",       "created_at":d(5,9)},
    {"id":"l17","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"130/81","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"Controlled.",       "created_at":d(4,9)},
    {"id":"l18","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"133/84","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"Stable.",           "created_at":d(3,9)},
    # d(2): BAD — BP 168 > 160
    {"id":"l19","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"168/99", "oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"BP 168 — rising trend. Day 1 of concern.","created_at":d(2,9)},
    # d(1): BAD — BP 172 > 160
    {"id":"l20","patient_id":"p2","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1060,"food_intake":"Good","blood_pressure":"172/102","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":7.5,"notes":"BP 172 — 2nd consecutive day above 160.","created_at":d(1,9)},

    # ── p3 Meena Devi — Sugar ALERT ───────────────────────────────────────────
    # Days 9→2: sugar healthy (outside window, pol4 window=2 so only d(1) and today matter)
    {"id":"l21","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"128/80","oxygen_level":98,"sugar_level":"165","confusion":False,"sleep_hours":8.0,"notes":"Sugar normal.",   "created_at":d(9,13)},
    {"id":"l22","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"127/79","oxygen_level":98,"sugar_level":"158","confusion":False,"sleep_hours":8.0,"notes":"Good control.",   "created_at":d(8,13)},
    {"id":"l23","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1050,"food_intake":"Good","blood_pressure":"129/81","oxygen_level":98,"sugar_level":"172","confusion":False,"sleep_hours":8.0,"notes":"Within range.",   "created_at":d(7,13)},
    {"id":"l24","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1090,"food_intake":"Good","blood_pressure":"128/80","oxygen_level":98,"sugar_level":"180","confusion":False,"sleep_hours":8.0,"notes":"Borderline ok.",  "created_at":d(6,13)},
    {"id":"l25","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"130/82","oxygen_level":98,"sugar_level":"168","confusion":False,"sleep_hours":8.0,"notes":"Back down.",      "created_at":d(5,13)},
    {"id":"l26","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"129/81","oxygen_level":98,"sugar_level":"175","confusion":False,"sleep_hours":8.0,"notes":"Stable.",         "created_at":d(4,13)},
    {"id":"l27","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1060,"food_intake":"Good","blood_pressure":"128/80","oxygen_level":98,"sugar_level":"182","confusion":False,"sleep_hours":8.0,"notes":"Still fine.",     "created_at":d(3,13)},
    {"id":"l28","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"129/81","oxygen_level":98,"sugar_level":"188","confusion":False,"sleep_hours":8.0,"notes":"Slightly high but ok.","created_at":d(2,13)},
    # d(1): BAD — sugar 218 > 200
    {"id":"l29","patient_id":"p3","created_by":"NurseSara","role":"nurse","meal_type":"lunch","fluid_intake_ml":1040,"food_intake":"Moderate","blood_pressure":"130/82","oxygen_level":98,"sugar_level":"218","confusion":False,"sleep_hours":8.0,"notes":"Sugar crossed 200 after lunch — 1st breach day.","created_at":d(1,13)},

    # ── p4 James Carter — Oxygen ALERT ───────────────────────────────────────
    # Days 9→2: oxygen healthy (outside window, pol6 window=2)
    {"id":"l30","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1200,"food_intake":"Good","blood_pressure":"126/78","oxygen_level":98,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"All vitals stable.","created_at":d(9,10)},
    {"id":"l31","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1180,"food_intake":"Good","blood_pressure":"127/79","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Good.",             "created_at":d(8,10)},
    {"id":"l32","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1150,"food_intake":"Good","blood_pressure":"128/80","oxygen_level":98,"sugar_level":None,"confusion":False,"sleep_hours":8.5,"notes":"Resting well.",     "created_at":d(7,10)},
    {"id":"l33","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1200,"food_intake":"Good","blood_pressure":"127/79","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Stable cardiac.",   "created_at":d(6,10)},
    {"id":"l34","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1180,"food_intake":"Good","blood_pressure":"128/80","oxygen_level":98,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"No issues.",        "created_at":d(5,10)},
    {"id":"l35","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1160,"food_intake":"Good","blood_pressure":"126/78","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Good oxygen.",      "created_at":d(4,10)},
    {"id":"l36","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1200,"food_intake":"Good","blood_pressure":"127/79","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Stable.",           "created_at":d(3,10)},
    {"id":"l37","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1180,"food_intake":"Good","blood_pressure":"128/80","oxygen_level":96,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Oxygen 96 — still fine.","created_at":d(2,10)},
    # d(1): BAD — oxygen 93 < 95
    {"id":"l38","patient_id":"p4","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1150,"food_intake":"Good","blood_pressure":"129/81","oxygen_level":93,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Oxygen dropped to 93 — 1st breach day. Monitoring closely.","created_at":d(1,10)},

    # ── p5 Lakshmi Nair — Sleep PRE-ALERT ────────────────────────────────────
    # Days 9→2: all healthy including good sleep
    # d(1): GOOD sleep (8.5h) — CRITICAL, keeps today as only bad day → PRE-ALERT not ALERT
    {"id":"l39","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1200,"food_intake":"Good","blood_pressure":"138/84","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.5,"notes":"Good sleep and intake.","created_at":d(9,8)},
    {"id":"l40","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1180,"food_intake":"Good","blood_pressure":"139/85","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Stable.",             "created_at":d(8,8)},
    {"id":"l41","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1150,"food_intake":"Good","blood_pressure":"140/85","oxygen_level":96,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Good.",              "created_at":d(7,8)},
    {"id":"l42","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1200,"food_intake":"Good","blood_pressure":"139/84","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.5,"notes":"Slept well.",         "created_at":d(6,8)},
    {"id":"l43","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1180,"food_intake":"Good","blood_pressure":"140/85","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"No issues.",          "created_at":d(5,8)},
    {"id":"l44","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1160,"food_intake":"Good","blood_pressure":"138/84","oxygen_level":96,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Steady.",             "created_at":d(4,8)},
    {"id":"l45","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1200,"food_intake":"Good","blood_pressure":"139/85","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Good rest.",          "created_at":d(3,8)},
    {"id":"l46","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1150,"food_intake":"Good","blood_pressure":"140/85","oxygen_level":97,"sugar_level":None,"confusion":False,"sleep_hours":8.0,"notes":"Slept well.",         "created_at":d(2,8)},
    # d(1): GOOD sleep — keeps window at 1 bad day when today is logged bad
    {"id":"l47","patient_id":"p5","created_by":"NurseEmma","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"140/86","oxygen_level":96,"sugar_level":None,"confusion":False,"sleep_hours":8.5,"notes":"Slept fine last night. All stable.","created_at":d(1,8)},

    # ── p6 David Roy — Confusion PRE-ALERT ───────────────────────────────────
    # Days 9→2: all healthy, confusion=False
    # d(1): GOOD — confusion False — CRITICAL, keeps today as only bad day → PRE-ALERT not ALERT
    {"id":"l48","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"136/83","oxygen_level":97,"sugar_level":"142","confusion":False,"sleep_hours":8.0,"notes":"Alert and oriented.",  "created_at":d(9,9)},
    {"id":"l49","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"137/84","oxygen_level":97,"sugar_level":"138","confusion":False,"sleep_hours":8.0,"notes":"Good compliance.",     "created_at":d(8,9)},
    {"id":"l50","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1050,"food_intake":"Good","blood_pressure":"136/83","oxygen_level":98,"sugar_level":"145","confusion":False,"sleep_hours":8.0,"notes":"Oriented to time.",    "created_at":d(7,9)},
    {"id":"l51","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"135/82","oxygen_level":97,"sugar_level":"140","confusion":False,"sleep_hours":8.0,"notes":"Good day.",            "created_at":d(6,9)},
    {"id":"l52","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1090,"food_intake":"Good","blood_pressure":"137/84","oxygen_level":97,"sugar_level":"148","confusion":False,"sleep_hours":8.0,"notes":"No confusion.",        "created_at":d(5,9)},
    {"id":"l53","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"136/83","oxygen_level":98,"sugar_level":"142","confusion":False,"sleep_hours":8.0,"notes":"On medication.",       "created_at":d(4,9)},
    {"id":"l54","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1100,"food_intake":"Good","blood_pressure":"135/82","oxygen_level":97,"sugar_level":"145","confusion":False,"sleep_hours":8.0,"notes":"Stable.",              "created_at":d(3,9)},
    {"id":"l55","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1060,"food_intake":"Good","blood_pressure":"136/83","oxygen_level":97,"sugar_level":"143","confusion":False,"sleep_hours":8.0,"notes":"Good morning.",        "created_at":d(2,9)},
    # d(1): GOOD — confusion False — window will have only today as bad day
    {"id":"l56","patient_id":"p6","created_by":"NurseSara","role":"nurse","meal_type":"breakfast","fluid_intake_ml":1080,"food_intake":"Good","blood_pressure":"137/84","oxygen_level":97,"sugar_level":"148","confusion":False,"sleep_hours":8.0,"notes":"Oriented — no confusion noted today.","created_at":d(1,9)},
]

ASSESSMENTS = [
    {"id":"a1","patient_id":"p1","versions":[{"version":1,"created_by":"DrArun","symptom_duration":"3 days","summary":"UTI Risk. Fluid intake dropping for last 3 days — below 1000ml threshold.","doctor_instruction":"Encourage oral fluids at every meal. Minimum 1 litre daily. Alert if fluid below 800ml.","doc_text":"","docs":[],"created_at":d(3,9)}]},
    {"id":"a2","patient_id":"p2","versions":[{"version":1,"created_by":"DrArun","symptom_duration":"3 days","summary":"Hypertension. BP above 160 systolic for 3 consecutive days. Medication adjustment may be needed.","doctor_instruction":"BP before every meal. Continue Amlodipine 10mg. Escalate if above 180 systolic.","doc_text":"Amlodipine 10mg once daily morning. Telmisartan 80mg once daily morning. Target BP below 130/80.","docs":["P2_Rahul_Prescription.pdf"],"created_at":d(3,9)}]},
    {"id":"a3","patient_id":"p3","versions":[{"version":1,"created_by":"DrArun","symptom_duration":"2 days","summary":"Diabetes Type 2. Post-lunch sugar above 200 for last 2 days.","doctor_instruction":"Monitor sugar after every meal. Continue Metformin 500mg twice daily. Alert if sugar exceeds 250.","doc_text":"Fasting sugar 148 mg/dL. HbA1c 7.8%. Continue Metformin 500mg twice daily.","docs":["P3_Meena_Sugar_Report.pdf"],"created_at":d(2,11)}]},
    {"id":"a4","patient_id":"p4","versions":[{"version":1,"created_by":"DrArun","symptom_duration":"2 days","summary":"Cardiac Monitoring. Oxygen saturation below 95% for last 2 consecutive days.","doctor_instruction":"Monitor oxygen every morning. Alert immediately if below 92%. Respiratory support if trend continues.","doc_text":"Cardiac rhythm stable. Continue oxygen monitoring.","docs":["P4_Cardiac_Report.pdf"],"created_at":d(2,11)}]},
    {"id":"a5","patient_id":"p5","versions":[{"version":1,"created_by":"DrArun","symptom_duration":"1 day","summary":"Fall Risk. First episode of poor sleep noted yesterday. Fluid intake good.","doctor_instruction":"Monitor sleep quality daily. Ensure comfortable environment. Mobility support throughout day.","doc_text":"","docs":[],"created_at":d(1,10)}]},
    {"id":"a6","patient_id":"p6","versions":[{"version":1,"created_by":"DrArun","symptom_duration":"1 day","summary":"Medication Review. First confusion episode noted yesterday. All other vitals stable.","doctor_instruction":"Monitor for further confusion. Check medication interactions. Report any repeat episode immediately.","doc_text":"","docs":[],"created_at":d(1,10)}]},
]

TASKS = [
    {"id":"t1","patient_id":"p1","assigned_to":"NurseEmma","created_by":"DrArun","title":"Fluid Intake Check",    "due_time":"08:30 AM","instruction":"Record fluid intake at every meal — minimum 1 litre daily",    "linked_field":"fluid_intake_ml","completion_mode":"fluid_intake_ml","done":False,"deleted":False,"status":"sent","created_at":d(1,7)},
    {"id":"t2","patient_id":"p2","assigned_to":"NurseEmma","created_by":"DrArun","title":"BP Before Breakfast",   "due_time":"08:00 AM","instruction":"Measure BP before food every morning — record systolic carefully","linked_field":"blood_pressure",  "completion_mode":"blood_pressure",  "done":False,"deleted":False,"status":"sent","created_at":d(1,7)},
    {"id":"t3","patient_id":"p3","assigned_to":"NurseSara", "created_by":"DrArun","title":"Post-Lunch Sugar Check","due_time":"01:30 PM","instruction":"Measure blood sugar 1 hour after lunch every day",             "linked_field":"sugar_level",       "completion_mode":"sugar_level",     "done":False,"deleted":False,"status":"sent","created_at":d(1,7)},
    {"id":"t4","patient_id":"p4","assigned_to":"NurseSara", "created_by":"DrArun","title":"Oxygen Level Check",   "due_time":"09:00 AM","instruction":"Record oxygen saturation every morning — alert if below 92%",  "linked_field":"oxygen_level",      "completion_mode":"oxygen_level",    "done":False,"deleted":False,"status":"sent","created_at":d(1,7)},
    {"id":"t5","patient_id":"p5","assigned_to":"NurseEmma","created_by":"DrArun","title":"Sleep Quality Record",  "due_time":"08:30 AM","instruction":"Ask Lakshmi how many hours she slept — note any restlessness",  "linked_field":"sleep_hours",       "completion_mode":"sleep_hours",     "done":False,"deleted":False,"status":"sent","created_at":d(1,7)},
    {"id":"t6","patient_id":"p5","assigned_to":"CaretakerRavi","created_by":"DrArun","title":"Mobility Support",  "due_time":"All Day","instruction":"Assist Lakshmi with movement — do not leave unassisted near bed","linked_field":"",                  "completion_mode":"manual",          "done":False,"deleted":False,"status":"sent","created_at":d(1,7)},
    {"id":"t7","patient_id":"p6","assigned_to":"NurseSara", "created_by":"DrArun","title":"Confusion Monitoring", "due_time":"09:00 AM","instruction":"Check orientation — ask name, date, location. Record confusion", "linked_field":"confusion",         "completion_mode":"confusion",       "done":False,"deleted":False,"status":"sent","created_at":d(1,7)},
    {"id":"t8","patient_id":"p6","assigned_to":"NurseSara", "created_by":"DrArun","title":"Medication Compliance","due_time":"09:00 AM","instruction":"Confirm David has taken morning medications",                    "linked_field":"",                  "completion_mode":"manual",          "done":True, "deleted":False,"status":"sent","created_at":d(1,7)},
]

# DOCS intentionally empty — RAG uses Pinecone only.
# Doctor uploads real PDFs via the assessment form which indexes them to Pinecone.
# Seeding raw text docs here would bypass Pinecone and break Ask AI.
DOCS = []

POLICY_REQUESTS = [
    {"id":"pr1","patient_id":"p1","policy_id":None,"requested_by":"DrArun","request_type":"create","status":"requested","decision_by":None,
     "draft_policy":{"name":"UTI Hydration Watch","policy_type":"threshold","log_field":"fluid_intake_ml","threshold":"Below 1000ml","check_value":1000.0,"alert_days":3,"prealert_days":2,"direction":"below","description":"Escalate when fluid below threshold","scope":"patient","patient_id":"p1"}},
]

NOTIFICATIONS = [
    {"id":"n1","to":["NurseEmma","ChiefMary"],"message":"Sarah Jenkins fluid intake below 1000ml for 3 days (window). Log today to trigger alert.","type":"info","read_by":[],"acked_by":[],"created_at":d(1,7)},
    {"id":"n2","to":["NurseEmma","ChiefMary"],"message":"Rahul Kumar BP above 160 for 3 days (window). Log today to trigger alert.","type":"info","read_by":[],"acked_by":[],"created_at":d(1,7)},
    {"id":"n3","to":["NurseSara","ChiefMary"],"message":"Meena Devi sugar above 200 for 2 days (window). Log today to trigger alert.","type":"info","read_by":[],"acked_by":[],"created_at":d(1,7)},
    {"id":"n4","to":["NurseSara","ChiefMary"],"message":"James Carter oxygen below 95% for 2 days (window). Log today to trigger alert.","type":"info","read_by":[],"acked_by":[],"created_at":d(1,7)},
    {"id":"n5","to":["ManagerPriya"],"message":"New policy request from DrArun for patient p1: UTI Hydration Watch","type":"policy_request","request_id":"pr1","read_by":[],"acked_by":[],"created_at":d(1,8)},
]

INCIDENTS = [
    {"id":"i1","patient_id":"p5","patient_name":"Lakshmi Nair","ref":"#FALL-99201","reported_by":"CaretakerRavi",
     "summary":"Near-fall near bedside — fatigue from poor sleep suspected","created_at":d(1,16)},
]

COLLECTIONS = {
    "users":           USERS,
    "rooms":           ROOMS,
    "patients":        PATIENTS,
    "log_fields":      LOG_FIELDS,
    "policies":        POLICIES,
    "care_logs":       CARE_LOGS,
    "assessments":     ASSESSMENTS,
    "tasks":           TASKS,
    "docs":            DOCS,          # empty — real docs uploaded via doctor form
    "policy_requests": POLICY_REQUESTS,
    "notifications":   NOTIFICATIONS,
    "incidents":       INCIDENTS,
    "alerts":          [],
    "pre_alerts":      [],
    "chat_histories":  [],
}


def seed():
    db = get_db()
    for col_name, docs in COLLECTIONS.items():
        db[col_name].drop()
        if docs:
            db[col_name].insert_many([dict(d) for d in docs])
        print(f"  Seeded {len(docs):3d} docs → {col_name}")

    from datetime import datetime, timedelta
    today     = datetime.now().date()
    yesterday = today - timedelta(days=1)

    print(f"\n✓ Done. Seed loaded. alerts=0, pre_alerts=0")
    print(f"\nToday is {today}. Log these values to trigger alerts:\n")
    print(f"  NurseEmma  → Sarah Jenkins  : fluid < 1000ml   e.g. 250ml      → ALERT  Hydration SOP (fires after 20:00)")
    print(f"  NurseEmma  → Rahul Kumar    : BP > 160         e.g. 174/102    → ALERT  Patient BP Watch")
    print(f"  NurseEmma  → Lakshmi Nair   : sleep < 8h       e.g. 6.0h       → PRE-ALERT  8-Hour Sleep SOP")
    print(f"  NurseSara  → Meena Devi     : sugar > 200      e.g. 240        → ALERT  Sugar SOP")
    print(f"  NurseSara  → James Carter   : oxygen < 95%     e.g. 91%        → ALERT  Oxygen SOP")
    print(f"  NurseSara  → David Roy      : confusion = Yes                   → PRE-ALERT  Confusion Threshold")
    print(f"\n  Window data seeded: {yesterday} (bad) + {today} you add manually")


if __name__ == "__main__":
    print("Seeding CareTrust AI — 9-day demo data (window-based logic)...\n")
    seed()
