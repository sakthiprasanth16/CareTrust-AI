from datetime import datetime
from backend.services.db import get_db

def _s(doc):
    return {k: v for k, v in doc.items() if k != "_id"} if doc else {}

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

def _notif(db, data):
    nid = _next_id(db, "notifications", "n")
    n = {"id": nid, "read_by": [], "acked_by": [],
         "created_at": datetime.now().isoformat(timespec="seconds")}
    n.update(data)
    db.notifications.insert_one(n)

# ── Log Fields ────────────────────────────────────────────────────────────────

def list_log_fields():
    db = get_db()
    return _sl(db.log_fields.find({"active": {"$ne": False}}))

def add_log_field(data):
    """Add a new field to the log_fields registry."""
    db = get_db()
    # Check not duplicate
    existing = db.log_fields.find_one({"field": data.get("field")})
    if existing:
        return {"error": f"Field '{data.get('field')}' already exists"}
    lid = _next_id(db, "log_fields", "lf")
    doc = {
        "id":          lid,
        "field":       data.get("field"),
        "label":       data.get("label"),
        "type":        data.get("type"),
        "unit":        data.get("unit"),
        "description": data.get("description", ""),
        "extract":     data.get("extract"),
        "active":      True,
    }
    db.log_fields.insert_one(doc)
    _notif(db, {
        "to":      ["DrArun", "ChiefMary"],
        "message": f"New log field added: '{doc['label']}' ({doc['type']}) — available in care log form and policy dropdown.",
        "type":    "policy_info",
    })
    return _s(doc)

# ── Policies ──────────────────────────────────────────────────────────────────

def list_policies(patient_id=None):
    db = get_db()
    if patient_id:
        return _sl(db.policies.find({"$or": [
            {"scope": "organization"},
            {"scope": "patient", "patient_id": patient_id},
        ]}))
    return _sl(db.policies.find())

def add_policy(data):
    db  = get_db()
    pid = _next_id(db, "policies", "pol")
    # Build full policy document from data
    doc = {
        "id":           pid,
        "name":         data.get("name"),
        "policy_type":  data.get("policy_type", "none"),
        "log_field":    data.get("log_field"),
        "threshold":    data.get("threshold", ""),
        "check_value":  data.get("check_value"),
        "alert_days":   int(data.get("alert_days", 3)),
        "prealert_days":int(data.get("prealert_days", 2)),
        "description":  data.get("description", ""),
        "direction":    data.get("direction", "below"),
        "tie_rule":     data.get("tie_rule", "breach"),
        "active":       True,
        "scope":        data.get("scope", "organization"),
        "patient_id":   data.get("patient_id"),
        "evaluation_mode": data.get("evaluation_mode", "instant"),
        "cutoff_time":     data.get("cutoff_time", None),
    }
    db.policies.insert_one(doc)
    _notif(db, {
        "to":      ["DrArun", "ChiefMary"],
        "message": f"New policy added: '{doc['name']}' (type: {doc['policy_type']}, field: {doc['log_field']}) — active now.",
        "type":    "policy_info",
    })
    return _s(doc)

def update_policy(policy_id, updates):
    """Update policy fields — changes take effect on next log save immediately."""
    db = get_db()
    p  = db.policies.find_one({"id": policy_id})
    if not p:
        return {}
    allowed = {"name","check_value","threshold","alert_days","prealert_days",
               "tie_rule","direction","description","log_field",
               "evaluation_mode","cutoff_time"}
    safe = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if safe:
        db.policies.update_one({"id": policy_id}, {"$set": safe})
    updated = _s(db.policies.find_one({"id": policy_id}))
    _notif(db, {
        "to":      ["DrArun", "ChiefMary"],
        "message": f"Policy '{updated.get('name','')}' updated — changes take effect on next care log save.",
        "type":    "policy_info",
    })
    return updated

def toggle_policy(policy_id, toggled_by="Manager"):
    db = get_db()
    p  = db.policies.find_one({"id": policy_id})
    if not p:
        return {}
    new_active = not p.get("active", True)
    db.policies.update_one({"id": policy_id}, {"$set": {"active": new_active}})
    state = "ON" if new_active else "OFF"
    _notif(db, {
        "to":      ["DrArun", "ChiefMary"],
        "message": f"Policy '{p['name']}' switched {state} by {toggled_by}. AI alerts {'active' if new_active else 'paused'} for this policy.",
        "type":    "policy_toggle",
    })
    result = _s(db.policies.find_one({"id": policy_id}))
    if new_active:
        try:
            from backend.services.alert_service import run_retroactive_scan
            retro = run_retroactive_scan(policy_id)
            result["retroactive_scan"] = retro
        except Exception as e:
            print(f"[policy_service] retroactive scan error: {e}")
    return result

def delete_policy(policy_id):
    db = get_db()
    p  = db.policies.find_one({"id": policy_id})
    if not p:
        return {}
    db.policies.delete_one({"id": policy_id})
    _notif(db, {
        "to":      ["DrArun", "ChiefMary"],
        "message": f"Policy '{p['name']}' permanently deleted.",
        "type":    "policy_info",
    })
    return _s(p)

# ── Policy Requests ───────────────────────────────────────────────────────────

def list_policy_requests():
    db = get_db()
    return _sl(db.policy_requests.find())

def request_remove_policy(patient_id, policy_id, requested_by):
    db  = get_db()
    rid = _next_id(db, "policy_requests", "pr")
    req = {
        "id": rid, "patient_id": patient_id, "policy_id": policy_id,
        "requested_by": requested_by, "request_type": "remove",
        "status": "requested", "decision_by": None,
    }
    db.policy_requests.insert_one(req)
    _notif(db, {
        "to":        ["ManagerPriya"],
        "message":   f"{requested_by} requested removal of policy '{policy_id}' for patient {patient_id}.",
        "type":      "policy_request", "request_id": rid,
    })
    return _s(req)

def request_new_policy(patient_id, requested_by, name, threshold, description,
                       policy_type="none", log_field=None, check_value=None,
                       alert_days=3, prealert_days=2, tie_rule="breach", direction="below"):
    db  = get_db()
    rid = _next_id(db, "policy_requests", "pr")
    req = {
        "id": rid, "patient_id": patient_id, "policy_id": None,
        "requested_by": requested_by, "request_type": "create",
        "status": "requested", "decision_by": None,
        "draft_policy": {
            "name": name, "threshold": threshold, "description": description,
            "scope": "patient", "patient_id": patient_id,
            "policy_type": policy_type, "log_field": log_field,
            "check_value": check_value, "alert_days": alert_days,
            "prealert_days": prealert_days, "tie_rule": tie_rule,
            "direction": direction,
        },
    }
    db.policy_requests.insert_one(req)
    _notif(db, {
        "to":        ["ManagerPriya"],
        "message":   f"{requested_by} requested new policy '{name}' for patient {patient_id}. Awaiting approval.",
        "type":      "policy_request", "request_id": rid,
    })
    return _s(req)

def decide_policy_request(request_id, decision_by, decision):
    db = get_db()
    r  = db.policy_requests.find_one({"id": request_id})
    if not r:
        return {}
    status = "accepted" if decision == "approved" else "denied"
    db.policy_requests.update_one({"id": request_id},
                                  {"$set": {"status": status, "decision_by": decision_by}})
    if decision == "approved":
        if r.get("request_type") == "remove" and r.get("policy_id"):
            delete_policy(r["policy_id"])
        elif r.get("request_type") == "create" and r.get("draft_policy"):
            new_pol = dict(r["draft_policy"])
            add_policy(new_pol)
            db.policy_requests.update_one({"id": request_id},
                                          {"$set": {"policy_id": new_pol.get("id")}})
    name = r.get("draft_policy", {}).get("name", "") or r.get("policy_id", "")
    _notif(db, {
        "to":      [r["requested_by"]],
        "message": f"Your policy request '{name}' was {status} by {decision_by}.",
        "type":    "policy_decision",
    })
    return _s(db.policy_requests.find_one({"id": request_id}))
