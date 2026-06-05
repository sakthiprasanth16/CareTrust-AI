from datetime import datetime
from backend.services.db import get_db

def _s(doc):
    if doc and "_id" in doc:
        return {k: v for k, v in doc.items() if k != "_id"}
    return doc

def _sl(docs):
    return [_s(d) for d in docs]

def _next_id(db, col, prefix):
    docs = list(db[col].find({}, {"id": 1}))
    nums = []
    for d in docs:
        raw = str(d.get("id", "")).replace(prefix, "")
        if raw.isdigit():
            nums.append(int(raw))
    return f"{prefix}{max(nums)+1 if nums else 1}"

# ── patients ──────────────────────────────────────────────────────────────────

def list_patients(worker=None, role=None, include_deleted=False):
    db = get_db()
    q  = {} if include_deleted else {"status": {"$ne": "deleted"}}
    if worker and role == "nurse":
        q["assigned_nurse"] = worker
    elif worker and role == "caretaker":
        q["caretaker"] = worker
    return _sl(db.patients.find(q))

def get_patient(pid):
    db = get_db()
    return _s(db.patients.find_one({"id": pid}))

def add_patient(data):
    db     = get_db()
    new_id = _next_id(db, "patients", "p")
    data.update({"id": new_id, "pinned": False, "status": "active"})
    db.patients.insert_one(data)
    db.rooms.update_one(
        {"room_no": data["room_no"]},
        {"$set": {"status": "admitted", "patient_id": new_id}}
    )
    return _s(data)

def list_patient_logs(patient_id):
    db = get_db()
    return _sl(db.care_logs.find({"patient_id": patient_id}).sort("created_at", 1))

def get_current_handler(patient_id):
    p = get_patient(patient_id)
    if not p:
        return {"label": "-", "username": None}
    if p.get("assigned_nurse"):
        return {"label": f"Nurse: {p['assigned_nurse']}", "username": p["assigned_nurse"]}
    if p.get("caretaker"):
        return {"label": f"Caretaker: {p['caretaker']}", "username": p["caretaker"]}
    return {"label": "Unassigned", "username": None}

def assign_patient(patient_id, worker_username, mode):
    db = get_db()
    p  = get_patient(patient_id)
    if not p:
        return {}
    if mode == "nurse":
        db.patients.update_one({"id": patient_id}, {"$set": {"assigned_nurse": worker_username}})
    elif mode == "caretaker":
        db.patients.update_one({"id": patient_id}, {"$set": {"caretaker": worker_username, "assigned_nurse": None}})
    db.tasks.update_many(
        {"patient_id": patient_id, "deleted": {"$ne": True}},
        {"$set": {"assigned_to": worker_username}}
    )
    return {"patient": get_patient(patient_id), "previous": p.get("assigned_nurse"), "new": worker_username}

def discharge_or_transfer(patient_id, caretaker=None):
    db = get_db()
    p  = get_patient(patient_id)
    if not p:
        return {}
    if caretaker:
        db.patients.update_one({"id": patient_id}, {"$set": {"caretaker": caretaker, "assigned_nurse": None}})
        db.tasks.update_many({"patient_id": patient_id, "deleted": {"$ne": True}}, {"$set": {"assigned_to": caretaker}})
    else:
        db.patients.update_one({"id": patient_id}, {"$set": {"status": "discharged", "assigned_nurse": None, "caretaker": None}})
    db.rooms.update_one({"room_no": p["room_no"]}, {"$set": {"status": "available", "patient_id": None}})
    return _s(db.patients.find_one({"id": patient_id}))

def delete_patient(patient_id):
    db = get_db()
    p  = get_patient(patient_id)
    if not p:
        return {}
    db.patients.delete_one({"id": patient_id})
    for col in ["care_logs", "tasks", "assessments", "docs", "alerts", "pre_alerts"]:
        db[col].delete_many({"patient_id": patient_id})
    db.policies.delete_many({"patient_id": patient_id, "scope": "patient"})
    db.rooms.update_one({"room_no": p.get("room_no")}, {"$set": {"status": "available", "patient_id": None}})
    return {"deleted_patient_id": patient_id}

# ── care logs ─────────────────────────────────────────────────────────────────

_BUILTIN_FIELD_MEAL = {"meal_breakfast", "meal_lunch", "meal_dinner"}

def _infer_linked_field_from_title(title: str) -> str:
    """Legacy fallback only — used for old seeded tasks without linked_field set."""
    t = (title or "").lower()
    if "sugar"                 in t: return "sugar_level"
    if "bp" in t or "pressure" in t: return "blood_pressure"
    if "sleep"                 in t: return "sleep_hours"
    if "fluid" in t or "water" in t: return "fluid_intake_ml"
    if "breakfast"             in t: return "meal_breakfast"
    if "lunch"                 in t: return "meal_lunch"
    if "dinner"                in t: return "meal_dinner"
    if "oxygen"                in t: return "oxygen_level"
    return ""  # blank = manual

def _resolve_linked_field(db, provided: str) -> str:
    """
    Validate provided field key against DB log_fields.
    Returns the field key if valid (built-in or custom), else "" (manual).
    Meal modes meal_breakfast/lunch/dinner are synthetic — always valid.
    """
    if not provided:
        return ""
    if provided in _BUILTIN_FIELD_MEAL:
        return provided
    # Check DB log_fields for built-in or manager-added fields
    exists = db.log_fields.find_one({"field": provided, "active": {"$ne": False}})
    return provided if exists else ""

def _task_matches_log(task, data):
    """
    Check if a care log satisfies a task's linked_field.
    1. Use linked_field (DB-driven, new tasks)
    2. Fall back to title inference (legacy tasks without linked_field)
    3. manual (empty linked_field after resolution) → never auto-complete
    """
    linked = task.get("linked_field") or ""

    # Legacy fallback — old seeded tasks without linked_field
    if not linked and task.get("completion_mode") not in ("manual", None, ""):
        linked = task.get("completion_mode", "")
    if not linked:
        linked = _infer_linked_field_from_title(task.get("title", ""))

    if not linked:
        return False  # manual — never auto-complete

    # Built-in care-log fields
    if linked == "sugar_level":     return bool(data.get("sugar_level"))
    if linked == "blood_pressure":  return bool(data.get("blood_pressure"))
    if linked == "sleep_hours":     return data.get("sleep_hours") is not None
    if linked == "fluid_intake_ml": return data.get("fluid_intake_ml") is not None
    if linked == "oxygen_level":    return data.get("oxygen_level") is not None
    if linked == "meal_breakfast":  return data.get("meal_type") == "breakfast"
    if linked == "meal_lunch":      return data.get("meal_type") == "lunch"
    if linked == "meal_dinner":     return data.get("meal_type") == "dinner"
    if linked == "confusion":       return data.get("confusion") is True

    # Dynamic extra_fields — manager-added custom fields
    extra = data.get("extra_fields") or {}
    if linked in extra and extra[linked] not in (None, "", False):
        return True

    return False

def add_care_log(data):
    db           = get_db()
    data["id"]   = _next_id(db, "care_logs", "l")
    data["created_at"] = datetime.now().isoformat(timespec="seconds")
    db.care_logs.insert_one(data)

    completed  = []
    open_tasks = list(db.tasks.find({
        "patient_id":  data["patient_id"],
        "assigned_to": data["created_by"],
        "done":        {"$ne": True},
        "deleted":     {"$ne": True},
    }))
    for t in open_tasks:
        if _task_matches_log(t, data):
            db.tasks.update_one({"id": t["id"]}, {"$set": {"done": True}})
            completed.append(t["title"])

    return {"log": _s(data), "completed_tasks": completed}

# ── tasks ─────────────────────────────────────────────────────────────────────

def list_tasks(worker=None, role=None, patient_id=None, worker_filter=None):
    db = get_db()
    q  = {"deleted": {"$ne": True}}
    if worker and role in ("nurse", "caretaker"):
        q["assigned_to"] = worker
    if patient_id:
        q["patient_id"] = patient_id
    if worker_filter and worker_filter != "all":
        q["assigned_to"] = worker_filter
    return _sl(db.tasks.find(q))

def add_task(data):
    db      = get_db()
    handler = get_current_handler(data["patient_id"])
    data["assigned_to"] = handler.get("username")
    data["id"]      = _next_id(db, "tasks", "t")
    data["done"]    = False
    data["deleted"] = False
    data["status"]  = "created"
    data.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    # Resolve linked_field from DB log_fields — blank means manual
    provided = (data.get("linked_field") or "").strip().lower()
    data["linked_field"]    = _resolve_linked_field(db, provided)
    data["completion_mode"] = data["linked_field"] if data["linked_field"] else "manual"
    db.tasks.insert_one(data)
    recipients = [u for u in [data.get("assigned_to"), "ChiefMary"] if u]
    _insert_notif(db, {
        "to":      recipients,
        "message": f"New task '{data['title']}' assigned for patient {data['patient_id']}.",
        "type":    "task_notice",
    })
    return _s(data)

def send_task_notice(task_id, sent_by):
    db = get_db()
    t  = db.tasks.find_one({"id": task_id})
    if not t:
        return {}
    db.tasks.update_one({"id": task_id}, {"$set": {"status": "sent"}})
    _insert_notif(db, {
        "to":      [t["assigned_to"]],
        "message": f"Task '{t['title']}' sent by {sent_by} for patient {t['patient_id']}.",
        "type":    "task_notice",
        "task_id": task_id,
    })
    return _s(db.tasks.find_one({"id": task_id}))

def ack_task_notice(notification_id, username):
    db   = get_db()
    note = db.notifications.find_one({"id": notification_id})
    if not note:
        return {}
    db.notifications.update_one({"id": notification_id}, {"$addToSet": {"acked_by": username, "read_by": username}})
    _insert_notif(db, {"to": ["ChiefMary"], "message": f"{username} accepted task notification.", "type": "info"})
    return _s(db.notifications.find_one({"id": notification_id}))

def delete_task(task_id, deleted_by):
    db = get_db()
    t  = db.tasks.find_one({"id": task_id})
    if not t:
        return {}
    db.tasks.update_one({"id": task_id}, {"$set": {"deleted": True, "status": "deleted"}})
    _insert_notif(db, {
        "to":      [t["assigned_to"], "ChiefMary"],
        "message": f"Task '{t['title']}' for patient {t['patient_id']} removed by {deleted_by}.",
        "type":    "info",
    })
    return _s(db.tasks.find_one({"id": task_id}))

def complete_task(task_id, completed_by):
    db = get_db()
    t  = db.tasks.find_one({"id": task_id})
    if not t:
        return {}
    if t.get("completion_mode") != "manual":
        return {"error": "Only manual tasks can be completed this way"}
    db.tasks.update_one({"id": task_id}, {"$set": {
        "done":         True,
        "status":       "completed",
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "completed_by": completed_by,
    }})
    return _s(db.tasks.find_one({"id": task_id}))

def list_tasks_for_patient_with_handler(patient_id):
    db = get_db()
    return _sl(db.tasks.find({"patient_id": patient_id, "deleted": {"$ne": True}}))

# ── rooms ─────────────────────────────────────────────────────────────────────

def list_rooms():
    db = get_db()
    return _sl(db.rooms.find())

def add_room(room_no):
    db  = get_db()
    rid = _next_id(db, "rooms", "r")
    room = {"id": rid, "room_no": room_no, "status": "available", "patient_id": None}
    db.rooms.insert_one(room)
    return _s(room)

def available_rooms():
    db = get_db()
    return _sl(db.rooms.find({"status": "available"}))

# ── assessments ───────────────────────────────────────────────────────────────

def add_initial_assessment(data, doc_names=None):
    """
    Option B upsert logic:
    - Assessment text provided AND doc provided  → create version + save doc → upsert both vectors
    - Assessment text provided, no doc           → create version only       → upsert assessment vector only
    - No assessment text, doc provided           → save doc only, no version → upsert doc vector only
    - Nothing provided                           → do nothing
    Last upserted vector in Pinecone always remains unchanged if not provided.
    """
    from backend.services.rag_service import index_patient_context

    db        = get_db()
    doc_names = doc_names or []
    patient   = get_patient(data["patient_id"])

    # ── Determine what was actually provided ──────────────────────────────────
    # Use 'or ""' to guard against explicit null values from frontend
    has_text = any([
        (data.get("symptom_duration") or "").strip(),
        (data.get("summary") or "").strip(),
        (data.get("doctor_instruction") or "").strip(),
    ])
    has_doc  = bool(doc_names and (data.get("doc_text") or "").strip())

    if not has_text and not has_doc:
        return get_assessment(data["patient_id"]) or {}

    # ── Create assessment version only if text was provided ───────────────────
    target = None
    if has_text:
        existing = db.assessments.find_one({"patient_id": data["patient_id"]})
        version  = {
            "version":            1,
            "created_by":         data["created_by"],
            "symptom_duration":   data.get("symptom_duration") or "",
            "summary":            data.get("summary") or "",
            "doctor_instruction": data.get("doctor_instruction") or "",
            "doc_text":           data.get("doc_text") or "",
            "docs":               doc_names,
            "created_at":         datetime.now().isoformat(timespec="seconds"),
        }
        if existing:
            version["version"] = len(existing.get("versions", [])) + 1
            db.assessments.update_one(
                {"patient_id": data["patient_id"]},
                {"$push": {"versions": version}}
            )
            target = _s(db.assessments.find_one({"patient_id": data["patient_id"]}))
        else:
            aid   = _next_id(db, "assessments", "a")
            new_a = {"id": aid, "patient_id": data["patient_id"], "versions": [version]}
            db.assessments.insert_one(new_a)
            target = _s(new_a)

    # ── Save doc record if doc was provided ───────────────────────────────────
    if has_doc:
        for doc_name in doc_names:
            did = _next_id(db, "docs", "d")
            db.docs.insert_one({
                "id":         did,
                "patient_id": data["patient_id"],
                "name":       doc_name,
                "kind":       "assessment_report",
                "pinned":     False,
                "deleted":    False,
                "text":       data.get("doc_text") or "",
            })

    # ── Notifications ─────────────────────────────────────────────────────────
    if patient and has_text:
        db.patients.update_one({"id": data["patient_id"]}, {"$set": {"status": "admitted"}})
        db.rooms.update_one(
            {"room_no": patient["room_no"]},
            {"$set": {"status": "admitted", "patient_id": patient["id"]}}
        )
        assigned = [x for x in [patient.get("assigned_nurse"), patient.get("caretaker")] if x]
        v_num    = target["versions"][-1]["version"] if target and target.get("versions") else "?"
        _insert_notif(db, {
            "to":      ["ChiefMary"] + assigned,
            "message": f"Assessment saved for {patient['name']} (v{v_num}) — status updated to admitted.",
            "type":    "assessment",
        })

    # ── Pinecone upsert — only upsert what was provided ──────────────────────
    try:
        index_patient_context(
            data["patient_id"],
            upsert_assessment=has_text,   # only if assessment text given
            upsert_doc=has_doc,           # only if doc uploaded
        )
    except Exception as e:
        print(f"[patient_service] RAG index warning: {e}")

    return target or get_assessment(data["patient_id"]) or {}


def get_assessment(patient_id):
    db = get_db()
    return _s(db.assessments.find_one({"patient_id": patient_id}))


def add_new_patient_assessment(data, room_no, doc_names=None):
    patient = add_patient({
        "name":           data.get("name"),
        "age":            int(data.get("age") or 0),
        "gender":         data.get("gender") or "Unknown",
        "room_no":        room_no,
        "diagnosis":      data.get("summary") or "Assessment Pending",
        "assigned_nurse": None,
        "caretaker":      None,
    })
    assess = add_initial_assessment({
        "patient_id":         patient["id"],
        "created_by":         data["created_by"],
        "symptom_duration":   data.get("symptom_duration"),
        "summary":            data.get("summary"),
        "doctor_instruction": data.get("doctor_instruction"),
        "doc_text":           data.get("doc_text") or "",
    }, doc_names=doc_names or [])
    db = get_db()
    _insert_notif(db, {
        "to":        ["ChiefMary"],
        "message":   f"New patient: {patient['name']} | Room {patient['room_no']} | Problem: {data.get('summary') or '-'}",
        "type":      "new_patient_assignment",
        "patient_id": patient["id"],
    })
    return {"patient": patient, "assessment": assess}


def assign_new_patient(patient_id, worker_username, mode="nurse"):
    result = assign_patient(patient_id, worker_username, mode)
    p      = get_patient(patient_id)
    db     = get_db()
    if p:
        _insert_notif(db, {
            "to":        [worker_username],
            "message":   f"Patient assigned to you: {p['name']} (Room {p['room_no']})",
            "type":      "patient_assignment",
            "patient_id": patient_id,
        })
    return result

# ── docs ──────────────────────────────────────────────────────────────────────

def list_docs(patient_id=None, include_deleted=False):
    db = get_db()
    q  = {} if include_deleted else {"deleted": {"$ne": True}}
    if patient_id:
        q["patient_id"] = patient_id
    return _sl(db.docs.find(q))

def delete_doc(doc_id):
    db = get_db()
    db.docs.update_one({"id": doc_id}, {"$set": {"deleted": True}})
    return _s(db.docs.find_one({"id": doc_id}))

def restore_doc(doc_id):
    db = get_db()
    db.docs.update_one({"id": doc_id}, {"$set": {"deleted": False}})
    return _s(db.docs.find_one({"id": doc_id}))

def permanent_delete_doc(doc_id):
    db  = get_db()
    doc = db.docs.find_one({"id": doc_id})
    db.docs.delete_one({"id": doc_id})
    if doc:
        try:
            from backend.services.rag_service import delete_doc_vector
            delete_doc_vector(doc["patient_id"], doc_id)
        except Exception as e:
            print(f"[patient_service] RAG delete warning: {e}")
    return {"deleted": doc_id}

# ── internal notification helper ──────────────────────────────────────────────

def _insert_notif(db, data):
    docs = list(db.notifications.find({}, {"id": 1}))
    nums = []
    for d in docs:
        raw = str(d.get("id", ""))[1:]
        if raw.isdigit():
            nums.append(int(raw))
    nid   = f"n{max(nums)+1 if nums else 1}"
    notif = {
        "id":         nid,
        "read_by":    [],
        "acked_by":   [],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    notif.update(data)
    db.notifications.insert_one(notif)
    return notif
