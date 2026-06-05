from fastapi import FastAPI, Request, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from typing import Optional
import io, os
from dotenv import load_dotenv
load_dotenv()

try:
    import PIL.Image
except ImportError:
    PIL = None

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    _scheduler_available = True
except ImportError:
    _scheduler_available = False
    print("[scheduler] apscheduler not installed — nightly cumulative scan disabled. Run: pip install apscheduler")


def _run_cumulative_scans():
    """
    Called at each policy's cutoff_time via scheduler.
    Scans all patients for end_of_day_cumulative policies only.
    Runs at the earliest cutoff_time across all active cumulative policies.
    If multiple policies have different cutoff times, scheduler fires at each.
    """
    try:
        from backend.services.db import get_db
        from backend.services.alert_service import run_auto_scan
        db = get_db()
        patients = list(db.patients.find({"status": {"$ne": "deleted"}}))
        print(f"[scheduler] Running nightly cumulative scan for {len(patients)} patients...")
        total_alerts = 0
        total_pre    = 0
        for patient in patients:
            result = run_auto_scan(patient_id=patient["id"])
            total_alerts += len(result.get("created_alerts",    []))
            total_pre    += len(result.get("created_prealerts", []))
        print(f"[scheduler] Done — {total_alerts} alert(s), {total_pre} pre-alert(s) generated")
    except Exception as e:
        print(f"[scheduler] Cumulative scan error: {e}")


def _get_cumulative_cutoff_times():
    """
    Read all active end_of_day_cumulative policies from DB.
    Return unique cutoff times as (hour, minute) tuples.
    Falls back to (20, 0) if DB not reachable or no cumulative policies found.
    """
    try:
        from backend.services.db import get_db
        db       = get_db()
        policies = list(db.policies.find({
            "active":          True,
            "evaluation_mode": "end_of_day_cumulative",
        }))
        times = set()
        for p in policies:
            ct = p.get("cutoff_time", "20:00")
            try:
                h, m = map(int, ct.split(":"))
                times.add((h, m))
            except Exception:
                times.add((20, 0))
        return list(times) if times else [(20, 0)]
    except Exception:
        return [(20, 0)]


# Global scheduler reference — allows endpoints to refresh jobs without restart
_scheduler = None


def refresh_cumulative_scheduler_jobs():
    """
    Rebuild all cumulative APScheduler jobs from current MongoDB state.
    Called after every policy add/update/toggle/delete so changes take
    effect immediately without server restart.
    """
    global _scheduler
    if not _scheduler_available or _scheduler is None:
        return
    try:
        # Remove all existing cumulative jobs
        for job in _scheduler.get_jobs():
            if job.id.startswith("cumulative_scan_"):
                _scheduler.remove_job(job.id)
        # Rebuild from DB current state
        cutoff_times = _get_cumulative_cutoff_times()
        for (h, m) in cutoff_times:
            _scheduler.add_job(
                _run_cumulative_scans,
                CronTrigger(hour=h, minute=m),
                id=f"cumulative_scan_{h:02d}{m:02d}",
                replace_existing=True,
            )
            print(f"[scheduler] Cumulative scan scheduled at {h:02d}:{m:02d}")
    except Exception as e:
        print(f"[scheduler] Refresh error: {e}")


@asynccontextmanager
async def lifespan(app):
    global _scheduler
    # ── Startup ───────────────────────────────────────────────────────────────

    # Preload RAG embedding model + Pinecone at startup so first user request
    # does not pay the model-load cost
    try:
        from backend.services.rag_service import warmup_rag_models
        warmup_rag_models()
    except Exception as e:
        print(f"[startup] RAG warmup error (non-fatal): {e}")

    if _scheduler_available:
        _scheduler = AsyncIOScheduler()
        refresh_cumulative_scheduler_jobs()   # read DB and schedule all cutoff jobs
        _scheduler.start()
        print("[scheduler] APScheduler started")
    else:
        _scheduler = None

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    if _scheduler:
        _scheduler.shutdown()
        print("[scheduler] APScheduler stopped")

from backend.models.schemas import *
from backend.services.auth_service      import login, list_users, create_user, set_worker_active
from backend.services.patient_service   import (
    list_patients, add_patient, assign_patient, discharge_or_transfer, delete_patient,
    list_patient_logs, get_assessment, add_care_log, list_tasks, add_task,
    send_task_notice, ack_task_notice, delete_task, complete_task, list_tasks_for_patient_with_handler,
    get_current_handler, list_rooms, add_room, available_rooms,
    add_initial_assessment, add_new_patient_assessment, assign_new_patient,
    list_docs, delete_doc, restore_doc, permanent_delete_doc,
)
from backend.services.policy_service    import (
    list_policies, add_policy, toggle_policy, delete_policy, update_policy,
    list_policy_requests, request_remove_policy, request_new_policy, decide_policy_request,
    list_log_fields, add_log_field,
)
from backend.services.alert_service     import (
    list_alerts, list_pre_alerts, trigger_pre_alert, run_auto_scan,
)
from backend.services.incident_service  import (
    list_incidents, add_incident, export_incident_pdf,
    list_all_patients_for_timeline, get_patient_date_range,
    get_patient_timeline, export_patient_timeline_pdf,
)
from backend.services.rag_service       import ask_ai, get_chat_history
from backend.services.notify_service    import (
    list_notifications, mark_all_read, ack_notification,
    sse_notification_stream, get_unread_count,
)

app = FastAPI(title="CareTrust AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# ── pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})

# ── auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/login")
def api_login(payload: LoginRequest):
    user = login(payload.username, payload.password)
    return {"success": bool(user), "user": user, "message": "Login failed" if not user else "OK"}

@app.get("/api/users")
def api_users():
    return list_users()

@app.post("/api/users")
def api_create_user(payload: UserCreate):
    return create_user(payload.name, payload.age, payload.password, payload.role)

@app.post("/api/users/inactive")
def api_inactive_user(payload: WorkerDelete):
    return set_worker_active(payload.username, active=False, transfer_to=payload.transfer_to)

# ── admin impersonation ───────────────────────────────────────────────────────

@app.get("/api/users/{username}/profile")
def api_user_profile(username: str):
    """Return a single user's profile for impersonation."""
    users = list_users()
    match = next((u for u in users if u["username"] == username), None)
    return match or {}

# ── patients ──────────────────────────────────────────────────────────────────

@app.get("/api/patients")
def api_patients(
    worker: Optional[str] = None,
    role:   Optional[str] = None,
    include_deleted: bool  = False,
):
    return list_patients(worker=worker, role=role, include_deleted=include_deleted)

@app.post("/api/patients")
def api_add_patient(payload: PatientCreate):
    return add_patient(payload.model_dump())

@app.post("/api/patients/assign")
def api_assign(payload: AssignPatient):
    return assign_patient(payload.patient_id, payload.worker_username, payload.mode)

@app.post("/api/patients/discharge")
def api_discharge(payload: AssignPatient):
    return discharge_or_transfer(
        payload.patient_id,
        caretaker=(payload.worker_username if payload.mode == "caretaker" else None),
    )

@app.post("/api/patients/delete")
def api_delete_patient(payload: PatientAction):
    return delete_patient(payload.patient_id)

@app.get("/api/patients/{patient_id}/logs")
def api_logs(patient_id: str):
    return list_patient_logs(patient_id)

@app.get("/api/patients/{patient_id}/assessment")
def api_assessment(patient_id: str):
    return get_assessment(patient_id) or {}

@app.get("/api/patients/{patient_id}/handler")
def api_patient_handler(patient_id: str):
    return get_current_handler(patient_id)

# ── care logs — local check → LLM only on breach ─────────────────────────────

@app.post("/api/logs")
def api_add_log(payload: CareLogCreate):
    result = add_care_log(payload.model_dump())
    scan   = run_auto_scan(patient_id=payload.patient_id)
    result["new_alerts"]     = scan.get("created_alerts",    [])
    result["new_pre_alerts"] = scan.get("created_prealerts", [])
    return result

# ── tasks ─────────────────────────────────────────────────────────────────────

@app.get("/api/tasks")
def api_tasks(
    worker:        Optional[str] = None,
    role:          Optional[str] = None,
    patient_id:    Optional[str] = None,
    worker_filter: Optional[str] = None,
):
    return list_tasks(worker=worker, role=role, patient_id=patient_id, worker_filter=worker_filter)

@app.post("/api/tasks")
def api_add_task(payload: TaskCreate):
    return add_task(payload.model_dump())

@app.post("/api/tasks/send/{task_id}")
def api_send_task(task_id: str, sent_by: str):
    return send_task_notice(task_id, sent_by)

@app.post("/api/tasks/ack")
def api_ack_task(payload: TaskAckRequest):
    return ack_task_notice(payload.notification_id, payload.username)

@app.post("/api/tasks/delete")
def api_delete_task(payload: DeleteTaskRequest):
    return delete_task(payload.task_id, payload.deleted_by)

@app.post("/api/tasks/complete")
def api_complete_task(payload: TaskCompleteRequest):
    return complete_task(payload.task_id, payload.completed_by)

@app.get("/api/tasks/by-patient/{patient_id}")
def api_tasks_by_patient(patient_id: str):
    return list_tasks_for_patient_with_handler(patient_id)

# ── assessments ───────────────────────────────────────────────────────────────

@app.post("/api/new-patient-assessment")
async def api_new_patient_assessment(
    name:               str            = Form(...),
    age:                int            = Form(...),
    gender:             str            = Form(...),
    created_by:         str            = Form(...),
    symptom_duration:   Optional[str]  = Form(None),
    summary:            Optional[str]  = Form(None),
    doctor_instruction: Optional[str]  = Form(None),
    room_no:            str            = Form(...),
    pdf_file:           Optional[UploadFile] = File(None),
):
    doc_text, doc_names = "", []
    if pdf_file and pdf_file.filename:
        doc_names = [pdf_file.filename]
        content   = await pdf_file.read()
        try:
            from pypdf import PdfReader
            reader   = PdfReader(io.BytesIO(content))
            doc_text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            doc_text = "PDF uploaded but text extraction failed."
    payload = {
        "name": name, "age": age, "gender": gender, "created_by": created_by,
        "symptom_duration": symptom_duration, "summary": summary,
        "doctor_instruction": doctor_instruction, "doc_text": doc_text,
    }
    return add_new_patient_assessment(payload, room_no=room_no, doc_names=doc_names)

@app.post("/api/new-patient-assign")
def api_new_patient_assign(payload: NewPatientAssignRequest):
    return assign_new_patient(payload.patient_id, payload.worker_username, payload.mode)

@app.post("/api/initial-assessment")
async def api_initial_assessment(
    patient_id:         str            = Form(...),
    created_by:         str            = Form(...),
    symptom_duration:   Optional[str]  = Form(None),
    summary:            Optional[str]  = Form(None),
    doctor_instruction: Optional[str]  = Form(None),
    pdf_file:           Optional[UploadFile] = File(None),
):
    doc_text, doc_names = "", []
    if pdf_file and pdf_file.filename:
        doc_names = [pdf_file.filename]
        content   = await pdf_file.read()
        try:
            from pypdf import PdfReader
            reader   = PdfReader(io.BytesIO(content))
            doc_text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            doc_text = "PDF uploaded but text extraction failed."
    payload = {
        "patient_id": patient_id, "created_by": created_by,
        "symptom_duration": symptom_duration, "summary": summary,
        "doctor_instruction": doctor_instruction, "doc_text": doc_text,
    }
    return add_initial_assessment(payload, doc_names=doc_names)

# ── rooms ─────────────────────────────────────────────────────────────────────

@app.get("/api/rooms")
def api_rooms():
    return list_rooms()

@app.get("/api/rooms/available")
def api_rooms_available():
    return available_rooms()

@app.post("/api/rooms")
def api_add_room(payload: RoomCreate):
    return add_room(payload.room_no)

# ── policies ──────────────────────────────────────────────────────────────────

@app.get("/api/policies")
def api_policies(patient_id: Optional[str] = None):
    return list_policies(patient_id=patient_id)

@app.post("/api/policies")
def api_add_policy(payload: PolicyCreate):
    result = add_policy(payload.model_dump())
    refresh_cumulative_scheduler_jobs()
    return result

@app.post("/api/policies/{policy_id}/toggle")
def api_toggle_policy(
    policy_id:  str,
    toggled_by: Optional[str] = Query(default="Manager"),
):
    result = toggle_policy(policy_id, toggled_by=toggled_by)
    refresh_cumulative_scheduler_jobs()
    return result

@app.post("/api/policies/{policy_id}/delete")
def api_delete_policy(policy_id: str):
    result = delete_policy(policy_id)
    refresh_cumulative_scheduler_jobs()
    return result

@app.post("/api/policies/{policy_id}/update")
def api_update_policy(policy_id: str, payload: PolicyUpdate):
    result = update_policy(policy_id, payload.model_dump(exclude_none=True))
    refresh_cumulative_scheduler_jobs()
    return result

@app.get("/api/log-fields")
def api_list_log_fields():
    return list_log_fields()

@app.post("/api/log-fields")
def api_add_log_field(payload: LogFieldCreate):
    return add_log_field(payload.model_dump())

@app.get("/api/policy-requests")
def api_policy_requests():
    return list_policy_requests()

@app.post("/api/policy-requests")
def api_policy_request(payload: PolicyRemoveRequest):
    return request_remove_policy(payload.patient_id, payload.policy_id, payload.requested_by)

@app.post("/api/policy-requests/new")
def api_new_policy_request(payload: PolicyRequestCreate):
    return request_new_policy(
        payload.patient_id, payload.requested_by,
        payload.name, payload.threshold, payload.description,
    )

@app.post("/api/policy-requests/decision")
def api_policy_decision(payload: PolicyDecision):
    result = decide_policy_request(payload.request_id, payload.decision_by, payload.decision)
    refresh_cumulative_scheduler_jobs()
    return result

# ── alerts ────────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
def api_alerts(worker: Optional[str] = None, role: Optional[str] = None):
    return list_alerts(worker=worker, role=role)

@app.get("/api/pre-alerts")
def api_prealerts(worker: Optional[str] = None, role: Optional[str] = None):
    return list_pre_alerts(worker=worker, role=role)

@app.post("/api/pre-alerts/trigger")
def api_trigger(payload: TriggerPreAlert):
    return trigger_pre_alert(payload.pre_alert_id, payload.triggered_by)

@app.post("/api/scan")
def api_scan(patient_id: Optional[str] = Query(default=None)):
    return run_auto_scan(patient_id=patient_id)

# ── incidents / timeline ──────────────────────────────────────────────────────

@app.get("/api/incidents")
def api_incidents():
    return list_incidents()

@app.get("/api/incidents/patients")
def api_incident_patients():
    return list_all_patients_for_timeline()

@app.get("/api/incidents/date-range/{patient_id}")
def api_date_range(patient_id: str):
    return get_patient_date_range(patient_id)

@app.post("/api/incidents")
def api_add_incident(payload: IncidentCreate):
    return add_incident(payload.model_dump())

@app.get("/api/incidents/timeline/{patient_id}")
def api_timeline(
    patient_id: str,
    from_date:  Optional[str] = Query(default=None),
    to_date:    Optional[str] = Query(default=None),
):
    events, total = get_patient_timeline(patient_id, from_date, to_date)
    return {
        "patient_id": patient_id,
        "from_date":  from_date,
        "to_date":    to_date,
        "total":      total,
        "events":     events,
    }

@app.get("/api/incidents/export/{patient_id}")
def api_export_timeline(
    patient_id: str,
    from_date:  Optional[str] = Query(default=None),
    to_date:    Optional[str] = Query(default=None),
):
    pdf_bytes = export_patient_timeline_pdf(patient_id, from_date, to_date)
    filename  = f"timeline_{patient_id}_{from_date or 'start'}_{to_date or 'end'}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )

@app.get("/api/incidents/{incident_id}/export")
def api_export_incident(incident_id: str):
    pdf_bytes = export_incident_pdf(incident_id)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="incident_{incident_id}.pdf"'},
    )

# ── docs ──────────────────────────────────────────────────────────────────────

@app.get("/api/docs")
def api_docs(patient_id: Optional[str] = None, include_deleted: bool = False):
    return list_docs(patient_id, include_deleted)

@app.post("/api/docs/delete")
def api_del_doc(payload: DocAction):
    return delete_doc(payload.doc_id)

@app.post("/api/docs/restore")
def api_restore_doc(payload: DocAction):
    return restore_doc(payload.doc_id)

@app.post("/api/docs/permanent-delete")
def api_perm_doc(payload: DocAction):
    return permanent_delete_doc(payload.doc_id)

# ── ask AI ────────────────────────────────────────────────────────────────────

@app.post("/api/ask-ai")
async def api_ask_ai(
    patient_id: str           = Form(...),
    question:   str           = Form(...),
    session_id: Optional[str] = Form(None),
    asked_by:   Optional[str] = Form(None),
    image:      Optional[UploadFile] = File(None),
):
    image_text = None
    if image and image.filename:
        try:
            import google.generativeai as genai
            key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if key:
                genai.configure(api_key=key)
                model    = genai.GenerativeModel("gemini-2.5-flash-lite")
                contents = await image.read()
                if PIL is not None:
                    pil_img    = PIL.Image.open(io.BytesIO(contents))
                    resp       = model.generate_content([
                        "Extract medicine name, strength, dosage, frequency, and any visible label or pack details from this image concisely.",
                        pil_img,
                    ])
                    image_text = resp.text
                else:
                    image_text = "Image uploaded but Pillow not installed."
            else:
                image_text = "No Gemini API key set."
        except Exception as e:
            image_text = f"Image analysis error: {e}"
    return ask_ai(patient_id, question, image_text=image_text,
                  session_id=session_id, asked_by=asked_by or "")

@app.get("/api/chat-history/{patient_id}")
def api_chat_history(patient_id: str):
    return get_chat_history(patient_id)

# ── notifications — SSE push ──────────────────────────────────────────────────

@app.get("/api/notifications/{username}")
def api_notifications(username: str):
    return list_notifications(username, limit=20)

@app.get("/api/notifications/stream/{username}")
async def api_notifications_stream(username: str):
    """SSE endpoint — pushes notifications the moment they are inserted."""
    return StreamingResponse(
        sse_notification_stream(username),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

@app.get("/api/notifications/count/{username}")
def api_notif_count(username: str):
    return {"unread": get_unread_count(username)}

@app.post("/api/notifications/{username}/read")
def api_notifications_read(username: str):
    return mark_all_read(username)

@app.post("/api/notifications/ack")
def api_notifications_ack(payload: NotificationAckRequest):
    return ack_notification(payload.notification_id, payload.username)
