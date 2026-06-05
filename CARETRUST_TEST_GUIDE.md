# CareTrust AI — Complete Test Guide

**What you will test:** 6 alerts/pre-alerts → 3 PDF uploads → 9 Ask AI questions → 1 image test → Timeline report → Notifications → Policy panel → Incident report

**Test files location:** All files are in the `test_docs/` folder in the project root:
- `test_docs/P2_Rahul_Prescription.pdf` — Rahul Kumar prescription
- `test_docs/P3_Meena_Sugar_Report.pdf` — Meena Devi lab report
- `test_docs/P4_James_Cardiac_Report.pdf` — James Carter cardiac report
- `test_docs/download__11_.jpg` — Amlodipine 10mg tablet image (for image test)

**Time needed:** ~45 minutes end to end

---

## SETUP — Run this first

```bash
# Step 1 — Drop old data and reseed fresh
python -m backend.services.seed

# Step 2 — Start the server
uvicorn main:app --reload

# Step 3 — Open browser
http://localhost:8000
```

**After seed runs, terminal will print:**
```
Seeded   8 docs → users
Seeded   8 docs → rooms
Seeded   6 docs → patients
Seeded   6 docs → log_fields
Seeded   6 docs → policies
Seeded  56 docs → care_logs
...
✓ Done. Seed loaded. alerts=0, pre_alerts=0

Today is 2026-06-02. Log these values to trigger alerts:
  NurseEmma  → Sarah Jenkins  : fluid < 1000ml   e.g. 250ml   → ALERT  Hydration SOP
  NurseEmma  → Rahul Kumar    : BP > 160         e.g. 174/102 → ALERT  Patient BP Watch
  NurseEmma  → Lakshmi Nair   : sleep < 8h       e.g. 6.0h    → PRE-ALERT  8-Hour Sleep SOP
  NurseSara  → Meena Devi     : sugar > 200      e.g. 240     → ALERT  Sugar SOP
  NurseSara  → James Carter   : oxygen < 95%     e.g. 91%     → ALERT  Oxygen SOP
  NurseSara  → David Roy      : confusion = Yes               → PRE-ALERT  Confusion Threshold
```

> The seed pre-loads 9 days of historical care logs per patient so the alert window
> is already set up. You just add today's log to complete the breach and fire the alert.

---

## PART 1 — ALERTS & PRE-ALERTS

### What is already seeded for each patient

| Patient | What seed pre-loaded | What you add today | Expected result |
|---|---|---|---|
| Sarah Jenkins | d(2) fluid 900ml ✗, d(1) fluid 860ml ✗ | fluid < 1000ml | ALERT |
| Rahul Kumar | d(2) BP 168 ✗, d(1) BP 172 ✗ | BP > 160 | ALERT |
| Meena Devi | d(1) sugar 218 ✗ | sugar > 200 | ALERT |
| James Carter | d(1) oxygen 93 ✗ | oxygen < 95 | ALERT |
| Lakshmi Nair | d(1) sleep 8.5h ✓ GOOD | sleep < 8h | PRE-ALERT only |
| David Roy | d(1) confusion False ✓ GOOD | confusion Yes | PRE-ALERT only |

---

### TEST 1 — Hydration ALERT (Sarah Jenkins)

**Login:** `NurseEmma` / `nurse123`

**Go to:** Patients → Sarah Jenkins → Add Care Log

Fill in these fields:

| Field | Value to enter |
|---|---|
| Meal type | Breakfast |
| Fluid intake | **250** |
| Notes | Refused fluids again this morning |

Click **Save Log**

**What you will see immediately:**

✅ Green toast at top: `New alert for Sarah Jenkins: Low Fluid Intake`

✅ Go to Dashboard → Alerts section → Sarah Jenkins card appears

**What the alert card shows:**

```
Low Fluid Intake                              HIGH  Confidence: 84%
─────────────────────────────────────────────────────────────────
Evidence ▾
  • Fluid intake below 1000ml for 3 consecutive days (yesterday-2 – today)
  • Lowest recorded: 250ml today — 75% below the 1000ml daily target
  • Daily totals: 900ml → 860ml → 250ml
  • Staff notes: Refused fluids again this morning · Patient refusing drinks

Reasoning: Fluid intake has dropped critically over 3 days and reached a
dangerous low today. Severe dehydration risk — immediate intervention needed.

Hydration SOP   Sarah Jenkins · Room 401
```

> **Note about Hydration SOP cutoff time:**
> This policy uses `end_of_day_cumulative` mode with cutoff `20:00`.
> It only counts today's fluid logs **after** the cutoff time passes.
> You don't need to wait until 8pm — change the cutoff time from the Manager UI:
>
> **Step 1 — Note your current time**
> Example: it is **12:44 PM** right now.
>
> **Step 2 — Login as ManagerPriya and edit the policy**
> Login: `ManagerPriya` / `manager123`
> Go to: **Clinical Policies** tab
> Find **Hydration SOP** → click **Edit**
> Change the `Cutoff Time` field from `20:00` to `12:55` (11 minutes from now)
> Click **Save** — this updates the database immediately and APScheduler reschedules.
>
> **Step 3 — Login as NurseEmma and submit the care log**
> Login: `NurseEmma` / `nurse123`
> Go to: Patients → Sarah Jenkins → Add Care Log → fluid **250ml** → Save
> Log saves but alert does NOT fire yet — current time 12:44 is before cutoff 12:55.
>
> **Step 4 — Wait until 12:55**
> At exactly 12:55 the APScheduler cron job fires automatically.
> Watch the server terminal — you will see:
> ```
> [scheduler] Running cumulative scan for cutoff 12:55
> [alert_service] Breach confirmed for p1 — calling Gemini
> [alert_service] Alert saved: Low Fluid Intake for Sarah Jenkins
> ```
>
> **Step 5 — Check the dashboard**
> Go to Dashboard → Alerts → Sarah Jenkins alert card appears automatically.
>
> ✅ This tests the full cumulative flow: log saves during the day, scheduler fires
> at cutoff time, alert generates automatically — no manual trigger needed.
>
> **After testing:** Login as ManagerPriya → Clinical Policies → Edit Hydration SOP
> → restore Cutoff Time back to `20:00` → Save.

---

### TEST 2 — BP ALERT (Rahul Kumar)

**Login:** `NurseEmma` (already logged in)

**Go to:** Patients → Rahul Kumar → Add Care Log

Fill in these fields:

| Field | Value to enter |
|---|---|
| Meal type | Breakfast |
| Blood pressure | **174/102** |
| Notes | BP high before breakfast again |

Click **Save Log**

**What you will see immediately:**

✅ Toast: `New alert for Rahul Kumar: Hypertensive Crisis`

✅ Dashboard → Alerts → Rahul Kumar alert appears

**What the alert card shows:**

```
Hypertensive Crisis                           HIGH  Confidence: 87%
─────────────────────────────────────────────────────────────────
Evidence ▾
  • Systolic BP above 160mmHg for 3 consecutive days (3 days ago – today)
  • Highest recorded: 174mmHg today — 9% above the 160mmHg threshold
  • Daily readings: 168mmHg → 172mmHg → 174mmHg
  • Staff notes: BP high before breakfast · BP 172 — 2nd consecutive day above 160

Reasoning: Blood pressure has risen each day for 3 consecutive days and is
now approaching a hypertensive emergency — urgent medication review needed.

Patient BP Watch   Rahul Kumar · Room 402
```

---

### TEST 3 — Sugar ALERT (Meena Devi)

**Logout NurseEmma → Login:** `NurseSara` / `nurse2123`

**Go to:** Patients → Meena Devi → Add Care Log

Fill in these fields:

| Field | Value to enter |
|---|---|
| Meal type | Lunch |
| Sugar level | **240** |
| Notes | Post-lunch sugar high again |

Click **Save Log**

**What you will see immediately:**

✅ Toast: `New alert for Meena Devi: High Blood Sugar`

✅ Dashboard → Alerts → Meena Devi alert appears

**What the alert card shows:**

```
High Blood Sugar                              HIGH  Confidence: 78%
─────────────────────────────────────────────────────────────────
Evidence ▾
  • Sugar level above 200mg/dL for 2 consecutive days (yesterday – today)
  • Highest recorded: 240mg/dL today — 20% above the 200mg/dL threshold
  • Daily readings: 218mg/dL (yesterday) → 240mg/dL (today)
  • Staff notes: Sugar crossed 200 after lunch · Post-lunch sugar high again

Reasoning: Post-meal blood sugar has exceeded the safe threshold two days
in a row and is rising — insulin review or dose adjustment may be needed.

Sugar SOP   Meena Devi · Room 403
```

---

### TEST 4 — Oxygen ALERT (James Carter)

**Login:** `NurseSara` (already logged in)

**Go to:** Patients → James Carter → Add Care Log

Fill in these fields:

| Field | Value to enter |
|---|---|
| Meal type | Breakfast |
| Oxygen level | **91** |
| Notes | Oxygen dropped to 91 this morning |

Click **Save Log**

**What you will see immediately:**

✅ Toast: `New alert for James Carter: Low Oxygen Saturation`

✅ Dashboard → Alerts → James Carter alert appears

**What the alert card shows:**

```
Low Oxygen Saturation                         HIGH  Confidence: 91%
─────────────────────────────────────────────────────────────────
Evidence ▾
  • Oxygen saturation below 95% for 2 consecutive days (yesterday – today)
  • Lowest recorded: 91% today — 4% below the 95% safe threshold
  • Daily readings: 93% (yesterday) → 91% (today)
  • Staff notes: Oxygen dropped to 93 — 1st breach day · Dropped to 91 this morning

Reasoning: Oxygen saturation has dropped further today and is now at a
clinically critical level — supplemental oxygen and immediate physician
review are required.

Oxygen SOP   James Carter · Room 404
```

---

### TEST 5 — Sleep PRE-ALERT (Lakshmi Nair)

**Logout NurseSara → Login:** `NurseEmma` / `nurse123`

**Go to:** Patients → Lakshmi Nair → Add Care Log

Fill in these fields:

| Field | Value to enter |
|---|---|
| Meal type | Breakfast |
| Fluid intake | **1100** |
| Sleep hours | **6.0** |
| Notes | Patient slept very poorly, restless all night |

Click **Save Log**

**What you will see:**

✅ Toast: `New pre-alert for Lakshmi Nair: Poor Sleep Quality`

✅ Dashboard — NurseEmma does NOT see pre-alerts yet
(Pre-alerts go to Chief Nurse and Doctor only until escalated)

**To see the pre-alert — Login as:** `ChiefMary` / `chiefnurse123`

Go to Dashboard → Pre-Alerts section

**What the pre-alert card shows:**

```
Poor Sleep Quality                            MEDIUM  Confidence: 58%
─────────────────────────────────────────────────────────────────
Evidence ▾
  • Sleep hours approaching threshold for 1 day (today)
  • Lowest recorded: 6.0 hours today — 25% below the 8-hour target
  • Today: 6.0 hours recorded
  • Staff notes: Patient slept very poorly, restless all night

Reasoning: Sleep has dropped below the 8-hour threshold for the first time —
this is an early warning that requires monitoring. Yesterday was fine at 8.5h.

8-Hour Sleep SOP   Lakshmi Nair · Room 405
```

**Why PRE-ALERT and not ALERT:**
- The 8-Hour Sleep SOP requires `alert_days=2` consecutive bad days
- Yesterday (d1) Lakshmi slept **8.5 hours** — that was GOOD
- Today is only 1 bad day → matches `prealert_days=1` → PRE-ALERT only
- If you log another bad sleep day tomorrow → full ALERT fires

**Escalate pre-alert to nurse (optional):**

ChiefMary can click **Trigger to Nurse** on the pre-alert card.
NurseEmma will then receive a notification bell alert.

---

### TEST 6 — Confusion PRE-ALERT (David Roy)

**Login:** `NurseSara` / `nurse2123`

**Go to:** Patients → David Roy → Add Care Log

Fill in these fields:

| Field | Value to enter |
|---|---|
| Meal type | Breakfast |
| Fluid intake | **1080** |
| Confusion | **Yes** (select from dropdown) |
| Notes | Patient confused this morning, disoriented |

Click **Save Log**

**What you will see:**

✅ Toast: `New pre-alert for David Roy: Confusion Observed`

**To see it — Login as:** `ChiefMary` / `chiefnurse123` → Dashboard → Pre-Alerts

**What the pre-alert card shows:**

```
Confusion Observed                            MEDIUM  Confidence: 55%
─────────────────────────────────────────────────────────────────
Evidence ▾
  • Confusion recorded on 1 day (today)
  • Today: confusion noted in 1 of 1 care logs
  • Staff notes: Patient confused this morning, disoriented

Reasoning: Confusion has been reported for the first time today — this is an
early warning that warrants monitoring and possible medication review.

Confusion Threshold   David Roy · Room 406
```

**Why PRE-ALERT and not ALERT:**
- `Confusion Threshold` policy requires `alert_days=2` consecutive days
- Yesterday (d1) David's confusion was **False** — that was GOOD
- Today is only 1 bad day → `prealert_days=1` → PRE-ALERT only

---

### TEST 7 — Control Test (No alert should fire)

**Login:** `NurseSara` (already logged in)

**Go to:** Patients → James Carter → Add Care Log (second log same day)

Fill in these fields:

| Field | Value to enter |
|---|---|
| Meal type | Lunch |
| Fluid intake | **1200** |
| Blood pressure | **128/80** |
| Notes | Stable after rest |

Click **Save Log**

**What you will see:**

✅ NO toast, NO new alert

✅ Check terminal — you will see:
```
[policy_checker] p4 — all policies clear
```
No Gemini call is made. The oxygen alert already fired today (dedup check prevents a second one).

---

## PART 2 — DOCUMENT UPLOAD & ASK AI SETUP

> Upload the 3 patient PDFs so Ask AI has clinical data to answer from.
> Without uploading, Ask AI will say "no document found for this patient."

---

### TEST 8 — Upload Rahul's Prescription

**Login:** `DrArun` / `doctor123`

**Go to:** Patients → Rahul Kumar → Docs tab

1. Click **Upload Document**
2. A file picker opens — select `P2_Rahul_Prescription.pdf` from the `test_docs/` folder
3. Click **Upload**

**What you will see:**

✅ Toast: `Document uploaded successfully`

✅ Document appears in Rahul's docs list

✅ Terminal:
```
[rag_service] Upserted 1 vector(s) for p2: ['p2::current_doc']
```

---

### TEST 9 — Upload Meena's Sugar Report

**Login:** `DrArun` (already logged in)

**Go to:** Patients → Meena Devi → Docs tab

1. Click **Upload Document**
2. A file picker opens — select `P3_Meena_Sugar_Report.pdf` from the `test_docs/` folder
3. Click **Upload**

**What you will see:**

✅ Terminal: `[rag_service] Upserted 1 vector(s) for p3: ['p3::current_doc']`

---

### TEST 10 — Upload James's Cardiac Report

**Go to:** Patients → James Carter → Docs tab

1. Click **Upload Document**
2. A file picker opens — select `P4_James_Cardiac_Report.pdf` from the `test_docs/` folder
3. Click **Upload**

**What you will see:**

✅ Terminal: `[rag_service] Upserted 1 vector(s) for p4: ['p4::current_doc']`

---

## PART 3 — ASK AI TESTS

> Login as **NurseEmma** or **ChiefMary** for Ask AI.
> Go to: Patients → [patient name] → Ask AI tab

---

### TEST 11 — Rahul Kumar (Prescription questions)

**Login:** `NurseEmma` / `nurse123`

**Go to:** Patients → Rahul Kumar → Ask AI tab

---

**Question 1 — List medicines**

Type exactly:
```
What medicines is Rahul currently on and what are the doses?
```

**Expected answer:**
```
Rahul is currently prescribed:
• Amlodipine 10mg — once daily morning after breakfast
• Telmisartan 80mg — once daily morning
• Atorvastatin 40mg — once daily at night
• Aspirin (EC) 75mg — once daily morning after food
• Metoprolol 25mg — twice daily morning and evening after food
```

---

**Question 2 — Target BP and emergency threshold**

Type:
```
What is the target BP for Rahul and what should I do if it goes above 180?
```

**Expected answer:**
```
Target BP for Rahul: below 130/80 mmHg.
If BP exceeds 180 systolic — escalate immediately and notify the doctor.
Do not wait for the next scheduled check.
```

---

**Question 3 — Aspirin crushing (safety check)**

Type:
```
Can I crush Rahul's Aspirin tablet to make it easier for him to swallow?
```

**Expected answer:**
```
No — Aspirin EC (enteric-coated) must NOT be crushed, chewed, or broken.
The enteric coating protects the stomach lining. Crushing it removes this
protection and can cause stomach irritation. Give it whole after food.
```

---

### TEST 12 — Meena Devi (Sugar management)

**Go to:** Patients → Meena Devi → Ask AI tab

---

**Question 1 — HbA1c result**

Type:
```
What is Meena's HbA1c result and what does it mean?
```

**Expected answer:**
```
Meena's HbA1c is 7.8%.
This indicates poor diabetes control. The target is below 7.0%.
At 7.8%, blood sugar has been consistently elevated over the past 2–3 months.
A repeat HbA1c is due after 4 weeks to monitor response to medication.
```

---

**Question 2 — Low sugar emergency**

Type:
```
Meena's sugar just dropped to 65 mg/dL right now — what should I do?
```

**Expected answer:**
```
Act immediately — this is hypoglycaemia (low blood sugar below 70 mg/dL).
Give 15g of fast-acting carbohydrates right now:
• A small glass of fruit juice, OR
• A glucose tablet
Recheck sugar after 15 minutes. If still below 70, repeat.
This is per Dr. Priya Venkat's instructions in Meena's care plan.
```

---

**Question 3 — Metformin timing**

Type:
```
What time should Meena take her Metformin?
```

**Expected answer:**
```
Metformin 500mg is to be taken TWICE daily:
• With breakfast
• With dinner
It must always be taken WITH food — never on an empty stomach as it
can cause nausea and stomach upset.
```

---

### TEST 13 — James Carter (Cardiac monitoring)

**Go to:** Patients → James Carter → Ask AI tab

---

**Question 1 — Ejection fraction**

Type:
```
What is James's ejection fraction and is it normal?
```

**Expected answer:**
```
James's ejection fraction (EF) is 48%.
The normal range is 55–70%. At 48% it is mildly reduced, indicating the
heart is not pumping as efficiently as expected. This is consistent with
the mild cardiomegaly noted on his chest X-ray.
```

---

**Question 2 — Weight gain concern**

Type:
```
James's weight went up by 3kg overnight. Is this a concern?
```

**Expected answer:**
```
Yes — this is a significant concern. Dr. Ramesh Nair's instructions state:
Report any weight gain above 2kg per day immediately.
Rapid weight gain in a cardiac patient usually indicates fluid retention,
which can be a sign of worsening heart failure. Alert the doctor now.
Do not wait.
```

---

**Question 3 — Banana for snack**

Type:
```
Can I give James a banana as a snack?
```

**Expected answer:**
```
No — bananas are high in potassium and should be avoided for James.
He is on Spironolactone 25mg, which can raise potassium levels.
Combining this with potassium-rich foods like bananas or orange juice
can cause dangerous hyperkalaemia (high potassium).
Avoid all high-potassium foods unless approved by the doctor.
```

---

## PART 4 — IMAGE + ASK AI TEST

### TEST 14 — Medicine image verification (Rahul Kumar)

>  **Image file location:** `test_docs/download__11_.jpg`
>
> The image shows: **Amlodipine 10mg Tablets by Teva** (Amlodipine Besylate 10mg, Oral use, 28 tablets)
> This is the same medicine as Rahul's prescription — Amlodipine 10mg.
>
> The 3 patient PDFs are also in the `test_docs/` folder:
> - `test_docs/P2_Rahul_Prescription.pdf`
> - `test_docs/P3_Meena_Sugar_Report.pdf`
> - `test_docs/P4_James_Cardiac_Report.pdf`

**Login:** `NurseEmma` / `nurse123`

**Go to:** Patients → Rahul Kumar → Ask AI tab

> Make sure you have already uploaded `P2_Rahul_Prescription.pdf` in Test 8.
> Ask AI reads from the uploaded prescription — without it, it cannot verify the medicine.

---

**Step 1 — Upload image + question**

1. Click the **camera icon** (📷) in the chat input area
2. A file picker opens — select `download__11_.jpg` from the `test_docs/` folder
3. Image preview appears above the input box
4. Type this question:

```
I have this medicine in my hand. Is this the right medicine for Rahul and is the dose correct?
```

Click **Send**

**What the AI reads from the image:**
- Brand: Amlodipine (Teva)
- Strength: 10mg
- Form: Tablets, Oral use

**Expected answer:**
```
VISUALLY CONFIRMED from the image:
Medicine: Amlodipine 10mg Tablets by Teva (Amlodipine Besylate 10mg, oral)

RECORD MATCHED from Rahul's prescription:
Prescription shows Amlodipine 10mg — once daily morning after breakfast.

✅ Correct medicine. ✅ Correct dose (10mg matches).
Safe to administer after breakfast with water as prescribed.
```

---

**Step 2 — Follow-up about timing (no new image needed)**

Type:
```
The tablet box says to take it with food. Is that correct for Rahul?
```

**Expected answer:**
```
Yes — correct.
Rahul's prescription specifically states:
Amlodipine 10mg: after breakfast with water.
Taking it with food is the right approach for this patient.
```

---

**Step 3 — Wrong dose test (type only, no image)**

Type:
```
I found another box of the same brand but it says 5mg. Can I give this instead?
```

**Expected answer:**
```
No — do NOT substitute without doctor approval.
Rahul's prescription is for Amlodipine 10mg.
The box you found is 5mg — half the prescribed dose.
Using a lower strength without the doctor's approval could result in
inadequate blood pressure control. Administer the 10mg as prescribed.
```

---

## PART 5 — NOTIFICATIONS TEST

### TEST 15 — Check notification bell

**Login:** `NurseEmma` / `nurse123`

Look at the bell icon (top right corner).

**What you will see:**

✅ Red badge showing unread count (at least 4 — one per alert fired)

Click the bell.

**What the notifications show:**

```
🔔 New alert for Sarah Jenkins: Low Fluid Intake        [unread, blue border]
🔔 New alert for Rahul Kumar: Hypertensive Crisis        [unread, blue border]
🔔 Sarah Jenkins fluid intake below 1000ml for 3 days   [info from seed]
🔔 Rahul Kumar BP above 160 for 3 days                  [info from seed]
```

Click **Mark all read** — badge disappears.

---

**Login:** `ChiefMary` / `chiefnurse123`

**What ChiefMary sees in bell:**

```
🔔 New alert for Sarah Jenkins: Low Fluid Intake
🔔 New alert for Rahul Kumar: Hypertensive Crisis
🔔 New alert for Meena Devi: High Blood Sugar
🔔 New alert for James Carter: Low Oxygen Saturation
🔔 New pre-alert for Lakshmi Nair: Poor Sleep Quality
🔔 New pre-alert for David Roy: Confusion Observed
```

ChiefMary sees all alerts and pre-alerts across all patients.

---

## PART 6 — TIMELINE REPORT TEST

### TEST 16 — Patient timeline (Manager view)

**Login:** `ManagerPriya` / `manager123`

**Go to:** Generate Report tab

1. Select patient: **James Carter**
2. Date range: select all available dates
3. Click **Generate Timeline**

**What you will see:**

A chronological timeline of all events for James Carter:

```
📋 CARE LOG  [9 days ago 10:00]  All vitals stable. Fluid 1200ml, O2 98%
📋 CARE LOG  [8 days ago 10:00]  Good. O2 97%
...
📋 CARE LOG  [yesterday 10:00]  Oxygen dropped to 93 — 1st breach day
📋 CARE LOG  [today 09:00]     Oxygen dropped to 91 this morning
🔴 ALERT     [today 09:01]     Low Oxygen Saturation — Confidence 91%
```

**Click Download PDF**

✅ PDF downloads with:
- James Carter patient header
- Colour-coded event cards (blue = care log, red = alert, amber = incident)
- All events in chronological order
- Confidence score and evidence on the alert card

---

## PART 7 — INCIDENT REPORT TEST

### TEST 17 — Submit an incident

**Login:** `NurseEmma` / `nurse123`

**Go to:** Submit Care Log tab

The page has two panels side by side:
- Left: Submit Care Log form
- Right: **⚠ Report Incident** panel

In the **Report Incident** panel:

| Field | Value to enter |
|---|---|
| Patient | Select **Lakshmi Nair — Room 405** |
| What happened? | Patient slipped near the bathroom at 2pm. Caught by nurse. No injury. Walking aid requested. |

Click **Submit Incident**

**What you will see:**

✅ Toast: `Incident INC-XXXXX reported` (amber/orange colour, stays 6 seconds)

**Verify in timeline:**

Login as `ManagerPriya` → Generate Report → Select Lakshmi Nair

The new incident appears in her timeline:

```
🟠 INCIDENT  [today 14:xx]
   Patient slipped near the bathroom at 2pm. Caught by nurse. No injury.
   Ref: INC-XXXXX | By: NurseEmma
```

---

## PART 8 — POLICY PANEL TEST

### TEST 18 — View and toggle a policy

**Login:** `ManagerPriya` / `manager123`

**Go to:** Clinical Policies tab

**What you will see:** 6 active policies listed

| Policy | Type | Scope | Status |
|---|---|---|---|
| Hydration SOP | Threshold below 1000ml | Organisation | ON |
| Confusion Threshold | Yes/No | Organisation | ON |
| 8-Hour Sleep SOP | Threshold below 8h | Organisation | ON |
| Sugar SOP | Threshold above 200 | Organisation | ON |
| Patient BP Watch | Threshold above 160 | Patient (Rahul) | ON |
| Oxygen SOP | Threshold below 95% | Organisation | ON |

**Test toggle OFF:**

1. Click the toggle switch on **Sugar SOP**
2. It turns grey (OFF)

✅ Toast or notification: `Policy 'Sugar SOP' switched OFF`

✅ Notification sent to DrArun and ChiefMary: *"Policy Sugar SOP switched OFF by ManagerPriya"*

**Test toggle ON again:**

Click the toggle → it turns green (ON)

✅ Notification: *"Policy Sugar SOP switched ON — retroactive scan running"*

A retroactive scan immediately checks existing data to see if any patient is already in breach.

---

## PART 9 — ADMIN VIEW AS TEST

### TEST 19 — Admin impersonation

**Login:** `AdminUser` / `admin123`

**Go to:** Admin tab

**What you will see:** All users listed as worker cards.

Click on **NurseEmma** card

✅ Yellow banner appears at top: `Viewing as NurseEmma — [Exit View]`

✅ Left nav changes to show NurseEmma's tabs: Dashboard, Patients, Submit Care Log, Tasks, Ask AI

Browse around — you see exactly what NurseEmma sees, including her patients and alerts.

Click **Exit View** in the yellow banner

✅ Returns to Admin view. Banner disappears.

> Note: Ask AI tab is visible when viewing as NurseEmma but NOT in Admin's own login.

---

## VERIFICATION CHECKLIST

After running all tests, check these in MongoDB Compass:

```js
// Should have 4 alerts
db.alerts.find({}).count()        // → 4

// Should have 2 pre-alerts
db.pre_alerts.find({}).count()    // → 2

// Should have 3 uploaded docs
db.docs.find({}).count()          // → 3

// Notifications should exist for multiple users
db.notifications.find({}).count() // → 10+
```

In Pinecone console (https://app.pinecone.io):

```
Namespace p2 → 2 vectors: p2::current_assessment, p2::current_doc
Namespace p3 → 2 vectors: p3::current_assessment, p3::current_doc
Namespace p4 → 2 vectors: p4::current_assessment, p4::current_doc
```

---

## QUICK REFERENCE — All logins

| Role | Username | Password | What they see |
|---|---|---|---|
| Nurse | NurseEmma | nurse123 | Sarah, Rahul, Lakshmi |
| Nurse | NurseSara | nurse2123 | Meena, James, David |
| Caretaker | CaretakerRavi | caretaker123 | Lakshmi only |
| Caretaker | CaretakerLatha | caretaker223 | David only |
| Doctor | DrArun | doctor123 | All patients, upload docs, policy requests |
| Chief Nurse | ChiefMary | chiefnurse123 | All patients, all alerts + pre-alerts |
| Manager | ManagerPriya | manager123 | Policies, timeline reports, worker management |
| Admin | AdminUser | admin123 | Admin panel + View As any user |

---

## QUICK REFERENCE — What triggers each alert

| Patient | Room | Nurse | Field | Threshold | Log value to use |
|---|---|---|---|---|---|
| Sarah Jenkins | 401 | NurseEmma | Fluid intake | Below 1000ml/day (3 days) | 250 ml |
| Rahul Kumar | 402 | NurseEmma | Blood pressure | Above 160 systolic (3 days) | 174/102 |
| Meena Devi | 403 | NurseSara | Sugar level | Above 200 mg/dL (2 days) | 240 |
| James Carter | 404 | NurseSara | Oxygen level | Below 95% (2 days) | 91 |
| Lakshmi Nair | 405 | NurseEmma | Sleep hours | Below 8h (2 days) | 6.0 → PRE-ALERT |
| David Roy | 406 | NurseSara | Confusion | Yes for 2 days | Yes → PRE-ALERT |

---

*CareTrust AI Test Guide — v5 — June 2026*
