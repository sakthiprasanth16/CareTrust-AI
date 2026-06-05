from backend.services.db import get_db

def _clean(u):
    return {k: v for k, v in u.items() if k not in ("password", "_id")}

def login(username, password):
    db = get_db()
    u = db.users.find_one({"username": username, "password": password, "active": True})
    return _clean(u) if u else None

def list_users():
    db = get_db()
    return [_clean(u) for u in db.users.find()]

def create_user(name, age, password, role):
    db = get_db()
    username = name.strip().replace(" ", "")
    count = db.users.count_documents({})
    user = {"id": f"u{count+1}", "username": username, "password": password,
            "role": role, "name": name, "age": age, "active": True}
    db.users.insert_one(user)
    return _clean(user)

def set_worker_active(username, active=False, transfer_to=None):
    db = get_db()
    worker = db.users.find_one({"username": username})
    if not worker:
        return {}
    if not active and transfer_to:
        db.patients.update_many({"assigned_nurse": username}, {"$set": {"assigned_nurse": transfer_to}})
        db.patients.update_many({"caretaker": username},      {"$set": {"caretaker": transfer_to}})
    db.users.update_one({"username": username}, {"$set": {"active": active}})
    return _clean(db.users.find_one({"username": username}))
