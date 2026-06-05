# 🩺 CareTrust AI — Trust UI & Safety Governance System

A **Clinical AI assistant for care homes** that makes AI decisions transparent, configurable, and accountable. Built for nurses, caretakers, doctors, and managers — every alert explained, every policy configurable, every incident reviewable.

---

## 🎥 Demo

[![Watch Demo Video](https://img.shields.io/badge/▶%20Watch%20Demo-Google%20Drive-2ec4a0?style=for-the-badge&logo=googledrive&logoColor=white)](https://drive.google.com/file/d/1iVlyOk_90zpZRX4QFKYj8cwm4qD0_1gR/view?usp=sharing)

---


## 🎯 What This System Does

Care homes face a real problem: AI systems that flag risks without explaining why. Carers either over-trust or ignore alerts. Managers can't configure policies to match their SOPs. Incident reports take hours to compile manually.

CareTrust AI solves all three:

**Sub-Case 1 — Evidence & Confidence Layer**
Every AI alert shows exactly what triggered it, with evidence bullets and a confidence score so carers understand and trust the recommendation.

**Sub-Case 2 — Clinical Policy Configuration**
Managers define their own thresholds and SOPs. The AI aligns its alerts to those rules — not the other way around. Policies take effect immediately with no restart.

**Sub-Case 3 — Incident Review Pack**
One click generates a complete chronological patient timeline — care logs, alerts, pre-alerts, tasks, assessments, incidents — ready for audit or regulatory review, downloadable as a PDF.

---

## 👥 Roles & What Each Can Do

| Role | Access |
|---|---|
| **Nurse** | Dashboard, My Patients, Submit Care Log, Ask AI |
| **Caretaker** | Dashboard, My Patients, Submit Care Log |
| **Doctor** | Dashboard, Tasks & Assessments, Docs & Policies |
| **Chief Nurse** | Dashboard, All Patients, Transfer & Rooms, Ask AI |
| **Manager** | Dashboard, Policies & Incidents, Patient Policies, Custom Log Fields |
| **Admin** | Dashboard, Admin Panel, Ask AI |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          BROWSER  —  Single Page App                                │
│                    app.js  ·  index.html  ·  styles.css                             │
│         Role-based nav  ·  Real-time SSE  ·  Markdown chat  ·  Image upload         │
│                                                                                     │
│   Nurse/Caretaker          Doctor              Chief Nurse      Manager / Admin     │
│   Dashboard                Tasks &             Transfer &       Policies &          │
│   My Patients              Assessments         Rooms            Incidents           │
│   Submit Care Log          Docs & Policies     All Patients     Patient Policies    │
│   Ask AI                   Upload PDF          Ask AI           Custom Log Fields   │
└────────────────────────────────────┬────────────────────────────────────────────────┘
                                     │  HTTP requests  /  SSE stream
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI BACKEND  —  main.py  —  Port 8000                   │
│                                                                                     │
│  Auth · Patients · Care Logs · Tasks · Policies · Alerts · Pre-Alerts               │
│  Incidents · Ask AI · Notifications · Rooms · Admin · Log Fields · Policy Requests  │
│                                                                                     │
│  APScheduler lifespan  ·  RAG warmup at startup  ·  SSE endpoint                    │
└──────┬──────────────┬──────────────┬──────────────┬──────────────┬─────────────── ─ ┘
       │              │              │              │              │
       ▼              ▼              ▼              ▼              ▼
  Care Log        PDF Upload     Ask AI         Policy &       Notifications
    Flow            Flow          Flow          Timeline          Flow
       │              │              │            Flow              │
       │              │              │              │               │
       ▼              ▼              ▼              ▼               ▼
┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐
│patient_    │  │patient_  │  │rag_      │  │policy_   │  │notify_      │
│service.py  │  │service.py│  │service.py│  │service.py│  │service.py   │
│            │  │          │  │          │  │          │  │             │
│save care   │  │save      │  │embed     │  │save to   │  │SSE stream   │
│log to DB   │  │assess-   │  │question  │  │MongoDB   │  │Change       │
│            │  │ment +    │  │via       │  │          │  │Streams or   │
│run_auto_   │  │doc text  │  │PubMed-   │  │refresh_  │  │15s poll     │
│scan()      │  │to MongoDB│  │BERT      │  │scheduler │  │fallback     │
└─────┬──────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘
      │              │              │              │               │
      ▼              ▼              ▼              ▼               ▼
┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐
│policy_     │  │rag_      │  │Pinecone  │  │APScheduler  │nurse bell   │
│checker.py  │  │service.py│  │search    │  │          │  │dashboard    │
│            │  │          │  │top_k=2   │  │Cron-     │  │live refresh │
│Zero LLM    │  │PubMed-   │  │cosine    │  │Trigger   │  │if on        │
│Threshold:  │  │BERT      │  │similarity│  │per policy│  │Dashboard    │
│numeric     │  │768-dim   │  │          │  │cutoff    │  │tab          │
│comparison  │  │embed     │  │returns   │  │time      │  │             │
│Yes/No:     │  │          │  │vector IDs│  │          │  │             │
│majority    │  │Pinecone  │  │          │  │Fires     │  │             │
│vote/day    │  │upsert    │  │          │  │run_auto_ │  │             │
│Cumulative: │  │          │  │          │  │scan() for│  │             │
│skip before │  │current_  │  │          │  │all       │  │             │
│cutoff time │  │assess or │  │          │  │patients  │  │             │
│Window:     │  │current_  │  │          │  │          │  │             │
│last N days │  │doc vector│  │          │  │          │  │             │
└─────┬──────┘  └──────────┘  └────┬─────┘  └──────────┘  └─────────────┘
      │                             │
      │ Breach?                     │ rebuild text
      │                             ▼
      │ No ──► Log saved ✓    ┌──────────┐
      │        No Gemini call  │MongoDB   │
      │                        │_rebuild_ │
      │ Yes                    │text()    │
      ▼                        │latest    │
┌────────────┐                 │assess +  │
│alert_      │                 │latest doc│
│service.py  │                 └────┬─────┘
│            │                      │
│_already_   │                      │ + history if
│exists()    │                      │ "previous /
│check DB    │                      │  before /
│before LLM  │                      │  used to"
│            │                      ▼
│Duplicate?  │                 ┌──────────┐
│Yes→ skip   │                 │last 6    │
│No → call   │                 │chat msgs │
│Gemini      │                 │from      │
└─────┬──────┘                 │MongoDB   │
      │                        └────┬─────┘
      ▼                             │
┌────────────────────────────────── │ ─────────────────┐
│              GEMINI 2.5 FLASH LITE│                   │
│                                   ▼                   │
│  alert_service.py            rag_service.py           │
│                                                       │
│  _call_gemini_for_breach()   Build prompt:            │
│                              System prompt +          │
│  Generates per breach:       Patient context +        │
│  · title (max 6 words)       History context +        │
│  · severity high/med/low     Last 6 messages +        │
│  · confidence score          Image content            │
│  · evidence bullets          (if uploaded)            │
│  · clinical reasoning                                 │
│                              Answer rules:            │
│  Confidence scoring:         · Patient records only   │
│  Threshold: severity bands   · No general med knowledge│
│  Yes/No: vote ratio          · Short direct answers   │
│  Hard caps: 45–95            · No structured reports  │
│  Pre-alert max: 72           · Image: name+strength   │
│                                                       │
│  Throttle: pause 10s                                  │
│  after 8 calls per scan                               │
└──────┬────────────────────────────┬───────────────────┘
       │                            │
       ▼                            ▼
┌────────────┐                ┌──────────┐
│alert_      │                │rag_      │
│service.py  │                │service.py│
│            │                │          │
│Save Alert  │                │Save chat │
│or Pre-Alert│                │history   │
│to MongoDB  │                │to MongoDB│
│            │                │          │
│evidence +  │                │Answer →  │
│confidence  │                │browser   │
│stored      │                │Markdown  │
│            │                │rendered  │
│SSE push →  │                └──────────┘
│Nurse +     │
│ChiefMary   │
│            │
│Dashboard   │
│live refresh│
└────────────┘

                     Timeline & PDF Export
                     ─────────────────────
┌─────────────────────────────────────────────────────────────┐
│                  incident_service.py                        │
│                                                             │
│  GET /api/incidents/timeline/{patient_id}                   │
│                                                             │
│  Collects from MongoDB:                                     │
│  care_logs · alerts · pre_alerts · tasks                    │
│  assessments · incidents                                    │
│                                                             │
│  Sorted chronologically · Date filter (default last 3 days) │
│  Colour-coded: Blue=log Red=alert Amber=pre-alert           │
│                Green=task Purple=assessment                 │
│                                                             │
│  Download as PDF via ReportLab                              │
│  Coloured event cards · Patient header · Legend             │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐  ┌───────────────────┐  ┌──────────┐  ┌──────────────────┐
│   MongoDB    │  │     Pinecone      │  │  Gemini  │  │  APScheduler     │
│              │  │   Vector Store    │  │   LLM    │  │                  │
│ patients     │  │                   │  │          │  │ AsyncIOScheduler │
│ care_logs    │  │ current_assess    │  │ Alert    │  │                  │
│ alerts       │  │ current_doc       │  │ detail   │  │ CronTrigger per  │
│ pre_alerts   │  │                   │  │ Ask AI   │  │ policy cutoff    │
│ policies     │  │ per-patient       │  │ answers  │  │ time             │
│ tasks        │  │ namespace         │  │          │  │                  │
│ docs         │  │                   │  │ gemini-  │  │ Refreshed on     │
│ assessments  │  │ 768-dim vectors   │  │ 2.5-     │  │ every policy     │
│ notifications│  │ cosine similarity │  │ flash-   │  │ add/edit/toggle  │
│ chat_hist    │  │                   │  │ lite     │  │ delete           │
│ log_fields   │  │ Replace not       │  │          │  │                  │
│ policy_      │  │ accumulate        │  │ temp=0.2 │  │ No restart       │
│ requests     │  │                   │  │          │  │ needed           │
└──────────────┘  └───────────────────┘  └──────────┘  └──────────────────┘
```
---

## ⚙️ Setup & Installation

### Step 1 — Clone and create virtual environment

```bash
git clone <repo-url>
cd caretrust_ai

python -m venv venv

# Activate:
# Windows:
venv\Scripts\activate
# Mac / Linux:
source venv/bin/activate
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

> First install may take several minutes — PubMedBERT (~400MB) downloads automatically on first use.

### Step 3 — Create the `.env` file

```bash
# Windows:
copy .env.example .env
# Mac / Linux:
cp .env.example .env
```

Open `.env` and fill in all values:

```env
GEMINI_API_KEY=your_gemini_key_here
PINECONE_API_KEY=your_pinecone_key_here
PINECONE_INDEX_NAME=caretrust-index
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=caretrust_ai
SECRET_KEY=any_random_string_here
```

---

### 🔑 How to get each key

#### GEMINI_API_KEY
1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click **Create API key**
4. Copy the key and paste into `.env`

#### PINECONE_API_KEY
1. Go to [https://app.pinecone.io](https://app.pinecone.io)
2. Sign up or log in
3. In the left sidebar click **API Keys**
4. Click **Create API key**, give it a name
5. Copy the key and paste into `.env`

#### PINECONE_INDEX_NAME — Create the index
1. In Pinecone dashboard, click **Indexes** → **Create Index**
2. Set these values exactly:

| Setting | Value |
|---|---|
| Index name | `caretrust-index` |
| Dimensions | `768` |
| Metric | `cosine` |
| Cloud | Any (Serverless recommended) |

3. Click **Create Index**
4. Use the same name in `.env` as `PINECONE_INDEX_NAME`

#### MONGO_URI
- **Local MongoDB:** `mongodb://localhost:27017` (default, no change needed)
- **MongoDB Atlas (cloud):**
  1. Go to [https://cloud.mongodb.com](https://cloud.mongodb.com)
  2. Create a free cluster
  3. Click **Connect** → **Drivers**
  4. Copy the connection string — replace `<password>` with your DB user password
  5. Paste as `MONGO_URI` in `.env`

#### SECRET_KEY
Any random string — used for session security. Example:
```
SECRET_KEY=caretrust_secret_2026_xK9mP
```

---

### Step 4 — Seed demo data

```bash
python -m backend.services.seed
```

After seeding, terminal prints:

```
Seeded   8 docs → users
Seeded   8 docs → rooms
Seeded   6 docs → patients
Seeded   6 docs → log_fields
Seeded   6 docs → policies
Seeded  56 docs → care_logs
Seeded   6 docs → assessments
Seeded   8 docs → tasks
Seeded   0 docs → docs
...
✓ Done. Seed loaded. alerts=0, pre_alerts=0

Today is 2026-06-03. Log these values to trigger alerts:
  NurseEmma  → Sarah Jenkins  : fluid < 1000ml   e.g. 250ml      → ALERT  Hydration SOP
  NurseEmma  → Rahul Kumar    : BP > 160         e.g. 174/102    → ALERT  Patient BP Watch
  NurseEmma  → Lakshmi Nair   : sleep < 8h       e.g. 6.0h       → PRE-ALERT  8-Hour Sleep SOP
  NurseSara  → Meena Devi     : sugar > 200      e.g. 240        → ALERT  Sugar SOP
  NurseSara  → James Carter   : oxygen < 95%     e.g. 91%        → ALERT  Oxygen SOP
  NurseSara  → David Roy      : confusion = Yes                   → PRE-ALERT  Confusion Threshold
```

> Seed uses relative dates — run it any day and the window data is always correct for today.

### Step 5 — Start the server

```bash
uvicorn main:app --reload
```

Open **http://localhost:8000**

> On first startup, PubMedBERT embedding model preloads (~30 seconds). Subsequent starts are fast.

---

## 🔑 Demo Credentials

| Role | Username | Password | Patients they see |
|---|---|---|---|
| Nurse | NurseEmma | nurse123 | Sarah Jenkins, Rahul Kumar, Lakshmi Nair |
| Nurse | NurseSara | nurse2123 | Meena Devi, James Carter, David Roy |
| Caretaker | CaretakerRavi | caretaker123 | Lakshmi Nair only |
| Caretaker | CaretakerLatha | caretaker223 | David Roy only |
| Doctor | DrArun | doctor123 | All patients — upload docs, request policies |
| Chief Nurse | ChiefMary | chiefnurse123 | All patients — all alerts and pre-alerts |
| Manager | ManagerPriya | manager123 | Policies, timeline reports, worker management |
| Admin | AdminUser | admin123 | Admin panel + View As any role |

---

## 🧪 Quick Test — Trigger your first alert

1. Login as `NurseEmma` / `nurse123`
2. Go to **Submit Care Log**
3. Select **Sarah Jenkins**
4. Fill: Fluid intake = `250`, Notes = `Refused fluids`
5. Click **Save Log**
6. ✅ Red toast appears: *"New alert for Sarah Jenkins: Low Fluid Intake"*
7. ✅ Dashboard Alerts column updates live — no refresh needed

---

## 📁 Project Structure

```
caretrust_ai/
│
├── main.py                    ← FastAPI app, all routes, APScheduler lifespan
├── .env                       ← Your API keys (never commit this)
├── .env.example               ← Template — copy to .env
├── requirements.txt
├── README.md
├── CARETRUST_TEST_GUIDE.md    ← Full test guide with step-by-step scenarios
│
├── test_docs/                 ← Sample PDFs for testing Ask AI
│   ├── P2_Rahul_Prescription.pdf
│   ├── P3_Meena_Sugar_Report.pdf
│   ├── P4_James_Cardiac_Report.pdf
│   └── download__11_.jpg      ← Amlodipine tablet image for image test
│
├── backend/
|   ├── config.py              ← Env var loading
│   ├── models/
│   │   └── schemas.py         ← Pydantic request/response models
│   │
│   └── services/
│       ├── db.py              ← MongoDB singleton client
│       ├── auth_service.py    ← Login, user management
│       ├── patient_service.py ← Patients, care logs, tasks, assessments, docs
│       ├── policy_service.py  ← Policies, log fields, policy requests
│       ├── policy_checker.py  ← Zero-LLM breach detection (threshold + yes/no)
│       ├── alert_service.py   ← Gemini calls, alert/pre-alert save, dedup, throttle
│       ├── notify_service.py  ← SSE stream, notifications, change streams
│       ├── incident_service.py← Timeline compilation, PDF export
│       ├── rag_service.py     ← Pinecone indexing, Ask AI, chat history, warmup
│       └── seed.py            ← Demo data seeder (relative dates, 9-day window)
│
└── frontend/
    ├── templates/
    │   └── index.html         ← Single-page app shell, all view sections
    └── static/
        ├── app.js             ← All frontend logic, role nav, SSE, rendering
        └── styles.css         ← Full UI stylesheet
```

---

## ⚙️ How the Alert System Works

```
Nurse saves care log
        ↓
policy_checker.py — zero LLM, pure Python
  Reads all active policies from MongoDB
  Checks last N days of logs (window-based)
  Threshold: compares numeric values
  Yes/No: majority vote per day
  Cumulative: skips check before cutoff time
        ↓
Breach found?
  No  → done, no Gemini call
  Yes → _already_exists() check (dedup before LLM)
        ↓
Already exists today?
  Yes → skip (no wasted Gemini call)
  No  → _call_gemini_for_breach()
        ↓
Gemini generates:
  title · severity · confidence score · evidence bullets · reasoning
        ↓
Alert / Pre-Alert saved to MongoDB
        ↓
SSE push to assigned nurse + ChiefMary
        ↓
Dashboard live-refreshes if nurse is on Dashboard tab
```

### Confidence Scoring

**Threshold policies** (fluid, BP, oxygen, sugar, sleep):

| Severity | Below threshold | Above threshold | Confidence |
|---|---|---|---|
| Borderline | 0–15% away | 0–10% away | 52–62 |
| Moderate | 15–35% away | 10–25% away | 63–73 |
| Serious | 35–60% away | 25–45% away | 74–84 |
| Critical | 60%+ away | 45%+ away | 85–95 |

Multipliers: +3 per extra consecutive day (max +12) · +5 if all days bad · +4 for cumulative mode · −10 for pre-alert

**Yes/No policies** (confusion, appetite loss, custom fields):

| Consecutive days | Base confidence |
|---|---|
| 1 day | 45–52 |
| 2 days | 55–63 |
| 3 days | 65–73 |
| 4 days | 74–82 |
| 5+ days | 83–92 |

Vote ratio bonus: >50% yes → +3 · ≥75% yes → +5 per day (capped +10) · Tie penalty: −8 · Pre-alert: −10

Hard caps: min 45 · max 95 · pre-alert max 72 · full alert min 52

---

## 📋 Policy System

### Policy Types

**Threshold** — numeric comparison
Fields: fluid intake, blood pressure (systolic auto-extracted from 170/100 format), oxygen, sugar, sleep, any custom numeric field

**Yes/No** — majority vote per day
Fields: confusion, appetite loss, any custom boolean field

### Evaluation Modes

**Instant** — checks on every log save. Best for single-reading fields like BP, oxygen.

**End-of-Day Cumulative** — skips check before configured cutoff time (e.g. 20:00). After cutoff, sums or votes all day's logs together. APScheduler fires at cutoff to catch patients with no late log.

### Dynamic Custom Fields

Manager adds any new log field from **Custom Log Fields** screen. Field appears automatically in Submit Care Log form and Policy dropdown — no code change needed.

---

## 🤖 Ask AI (RAG)

**Single path: Query → Pinecone → MongoDB → Gemini → Answer**

- PubMedBERT embeddings (768-dimension, medical-domain tuned)
- Pinecone stores 2 vectors per patient: `current_assessment` and `current_doc`
- History questions detected by keywords → fetches older versions from MongoDB
- Models preloaded at startup — no delay on first query
- Shared chat history per patient — all nurses see same thread
- Image upload: up to 4 images per query
- Answers only from patient records — never from general medical knowledge

### To use Ask AI with documents

1. Login as **DrArun**
2. Go to **Docs & Policies** → select a patient
3. Upload a PDF (prescription, lab report, etc.)
4. PDF is indexed to Pinecone automatically
5. Login as **NurseEmma** → Ask AI → select same patient
6. Ask questions — answers come from the uploaded document

---

## 📊 Incident Review & Timeline

- Collects care logs, alerts, pre-alerts, tasks, assessments, incidents chronologically
- Default view: last 3 days
- Colour-coded: care log blue · alert red · pre-alert amber · task green · assessment purple
- Download as PDF — coloured event cards with patient header and legend

---

## 🔌 API Reference

### Auth & Users
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/login` | Login |
| GET | `/api/users` | List users |
| POST | `/api/users` | Create user |
| POST | `/api/users/delete` | Deactivate worker |

### Patients & Care
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/patients` | List patients (role-filtered) |
| POST | `/api/patients` | Create patient |
| GET | `/api/patients/{id}/logs` | Patient care logs |
| POST | `/api/logs` | Submit care log → triggers breach check |
| GET | `/api/tasks` | List tasks (role-filtered) |
| POST | `/api/tasks` | Create task |
| POST | `/api/tasks/{id}/done` | Mark task complete |
| POST | `/api/assign` | Assign patient to nurse/caretaker |

### Assessments & Docs
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/new-patient-assessment` | New patient + first assessment |
| POST | `/api/initial-assessment` | Add/update assessment or upload doc |
| GET | `/api/patients/{id}/assessment` | Assessment history |
| GET | `/api/docs` | List documents |
| POST | `/api/docs/delete` | Soft delete doc |
| POST | `/api/docs/restore` | Restore doc |
| POST | `/api/docs/permanent-delete` | Delete doc + Pinecone vector |

### Policies
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/policies` | List policies |
| POST | `/api/policies` | Add policy → refreshes scheduler |
| POST | `/api/policies/{id}/update` | Edit policy → refreshes scheduler |
| POST | `/api/policies/{id}/toggle` | Toggle ON/OFF → retroactive scan if ON |
| POST | `/api/policies/{id}/delete` | Delete → refreshes scheduler |
| GET | `/api/log-fields` | List care log fields |
| POST | `/api/log-fields` | Add custom field |
| POST | `/api/policy-requests/new` | Doctor requests new policy |
| POST | `/api/policy-requests/decision` | Manager approves/denies |

### Alerts & Notifications
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/alerts` | List alerts (role-filtered) |
| GET | `/api/pre-alerts` | List pre-alerts |
| POST | `/api/pre-alerts/trigger` | Chief nurse triggers pre-alert |
| POST | `/api/scan` | Manual scan trigger |
| GET | `/api/notifications/stream/{username}` | SSE stream |
| POST | `/api/notifications/ack` | Acknowledge notification |

### Incidents & Timeline
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/incidents/timeline/{id}` | Patient timeline events |
| GET | `/api/incidents/export/{id}` | Download PDF timeline |

### Ask AI
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/ask-ai` | Ask question (text + optional images) |
| GET | `/api/chat-history/{patient_id}` | Shared chat history |

---

## 🛠️ Common Issues

| Problem | Fix |
|---|---|
| Login does nothing | Check server is running on port 8000 |
| No alerts after seeding | Check `GEMINI_API_KEY` in `.env` |
| Ask AI returns no context | Upload a PDF via DrArun first — docs are not pre-seeded |
| Pinecone error on startup | Check `PINECONE_API_KEY` and index dimensions = 768 |
| PDF upload fails | `pip install reportlab` |
| SSE not updating dashboard | MongoDB standalone → falls back to 15s server poll — normal |
| PubMedBERT slow first time | Downloads ~400MB on first use — normal, subsequent starts fast |
| `AttributeError: NoneType strip` | Update `patient_service.py` — null field guard fix |

---

## ✅ What Was Built vs the Use Case

| Use Case Requirement | Status | How |
|---|---|---|
| Evidence display on alerts | ✅ | Evidence bullets + reasoning in every alert card |
| Confidence indicator | ✅ | Real-world heuristic: severity bands + vote ratios |
| Policy configuration panel | ✅ | Manager creates/edits/toggles threshold and yes/no policies |
| AI rule alignment | ✅ | policy_checker reads from DB at runtime — instant effect |
| Policy updates take effect immediately | ✅ | DB-driven — scheduler refreshes on every policy change |
| Incident timeline compilation | ✅ | Auto-collects logs, alerts, tasks, assessments, incidents |
| Chronological report | ✅ | Sorted timeline with date filter and colour coding |
| Audit-ready PDF | ✅ | ReportLab PDF with coloured event cards, legend, patient header |
| **Beyond the use case** | | |
| Pre-alert system | ✅ | Warning before full breach — Chief Nurse triggers to nurse |
| Dynamic custom log fields | ✅ | Manager adds fields → form and policy dropdown auto-update |
| Patient-scoped policies | ✅ | Doctor requests, Manager approves, applies to one patient |
| Cumulative evaluation mode | ✅ | End-of-day fluid tracking with APScheduler at cutoff time |
| Real-time SSE notifications | ✅ | Live alert push — dashboard refreshes without tab switch |
| Ask AI with image upload | ✅ | Medicine verification with patient record matching |
| Shared chat history | ✅ | All nurses share conversation thread per patient |
| Admin impersonation | ✅ | Admin views system as any role |
| Gemini dedup + throttle | ✅ | Skip if exists today · pause after 8 calls per scan run |
| Model warmup at startup | ✅ | PubMedBERT + Pinecone preloaded before first request |

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla JS + HTML + CSS (single-page app, no framework) |
| Backend | FastAPI (Python) |
| Database | MongoDB |
| Vector Store | Pinecone |
| Embedding Model | PubMedBERT (`NeuML/pubmedbert-base-embeddings`, 768-dim) |
| LLM | Google Gemini 2.5 Flash Lite |
| Scheduler | APScheduler (end-of-day cumulative policy scans) |
| PDF Export | ReportLab |
| Real-time | SSE via MongoDB Change Streams (polling fallback) |

---

## 👨‍💻 Author

**Prasanth**
Project: CareTrust AI — Trust UI & Safety Governance
Use Case: AI transparency, clinical policy configuration, and incident review for care homes.
