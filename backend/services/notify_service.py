"""
notify_service.py
SSE push notifications with graceful fallback.
- Uses MongoDB Change Streams when available (Atlas / replica set)
- Falls back to polling-style long-keep-alive when not available
- Sends keep-alive ping every 25s to prevent connection timeout
- to field is an array: ["NurseEmma", "ChiefMary"]
"""
import json, asyncio
from datetime import datetime, timedelta
from backend.services.db import get_db


def _s(doc):
    return {k: v for k, v in doc.items() if k != "_id"} if doc else {}


def _next_id(db):
    docs = list(db.notifications.find({}, {"id": 1}))
    nums = [int(d["id"][1:]) for d in docs
            if d.get("id", "").startswith("n") and d["id"][1:].isdigit()]
    return f"n{max(nums)+1 if nums else 1}"


def list_notifications(username, limit=20):
    """Return last 20 notifications newest first, max 30 days old."""
    db     = get_db()
    cutoff = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    docs   = list(
        db.notifications.find({
            "to":         username,          # MongoDB matches if username is in array
            "created_at": {"$gte": cutoff},
        })
        .sort("created_at", -1)
        .limit(limit)
    )
    return [_s(n) for n in docs]


def get_unread_count(username):
    db     = get_db()
    cutoff = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    return db.notifications.count_documents({
        "to":         username,
        "read_by":    {"$ne": username},
        "created_at": {"$gte": cutoff},
    })


def mark_all_read(username):
    db = get_db()
    db.notifications.update_many(
        {"to": username, "read_by": {"$ne": username}},
        {"$addToSet": {"read_by": username}}
    )
    return {"ok": True}


def ack_notification(notification_id, username):
    db   = get_db()
    note = db.notifications.find_one({"id": notification_id})
    if not note:
        return {}
    db.notifications.update_one(
        {"id": notification_id},
        {"$addToSet": {"acked_by": username, "read_by": username}}
    )
    if note.get("type") == "pre_alert_trigger":
        pre_alert_id = note.get("pre_alert_id")
        if pre_alert_id:
            db.pre_alerts.update_one(
                {"id": pre_alert_id},
                {"$set": {"trigger_message_active": False, "status": "acknowledged"}}
            )
    back_to = [u for u in note.get("notify_back_to", []) if u != username]
    if back_to:
        nid = _next_id(db)
        db.notifications.insert_one({
            "id":         nid,
            "to":         back_to,
            "message":    f"{username} acknowledged: {note.get('message', '')}",
            "type":       "info",
            "read_by":    [],
            "acked_by":   [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
    return _s(db.notifications.find_one({"id": notification_id}))


async def sse_notification_stream(username: str):
    """
    SSE async generator.
    1. Sends init payload immediately (existing notifications + unread count)
    2. Tries MongoDB Change Streams (needs replica set / Atlas)
    3. If Change Streams unavailable → falls back to poll every 15s
       (much better than client-side polling — server controls the interval,
        connection stays open, no repeated HTTP handshakes)
    4. Sends keep-alive comment every 25s to prevent proxy/browser timeout
    """
    db = get_db()

    # ── Step 1: Send initial state immediately on connect ─────────────────────
    initial_count = get_unread_count(username)
    initial_notes = list_notifications(username, limit=20)
    yield (
        f"data: {json.dumps({'type': 'init', 'unread_count': initial_count, 'notifications': initial_notes})}\n\n"
    )

    # ── Step 2: Try Change Streams ────────────────────────────────────────────
    # to field is an ARRAY in MongoDB — use $in to match username inside array
    pipeline = [
        {"$match": {
            "operationType": "insert",
            "$or": [
                {"fullDocument.to": username},           # scalar match (fallback)
                {"fullDocument.to": {"$in": [username]}}, # array match
            ]
        }}
    ]

    try:
        # Test if change streams are available
        with db.notifications.watch(pipeline, full_document="updateLookup") as stream:
            last_ping = datetime.now()
            # stream.try_next() is non-blocking — allows us to send keep-alive
            while True:
                change = stream.try_next()
                if change is not None:
                    doc    = _s(change.get("fullDocument", {}))
                    unread = get_unread_count(username)
                    yield (
                        f"data: {json.dumps({'type': 'new_notification', 'notification': doc, 'unread_count': unread})}\n\n"
                    )
                else:
                    # No new event — send keep-alive every 25s
                    if (datetime.now() - last_ping).seconds >= 25:
                        yield ": keep-alive\n\n"
                        last_ping = datetime.now()
                    await asyncio.sleep(1)  # check every 1 second

    except Exception:
        # ── Step 3: Fallback — server-side poll every 15s ─────────────────────
        # Much better than client polling: one open connection, server controls interval
        last_count = initial_count
        last_ping  = datetime.now()

        while True:
            await asyncio.sleep(15)

            try:
                new_count = get_unread_count(username)
                # Send keep-alive regardless
                yield ": keep-alive\n\n"

                if new_count != last_count:
                    # Count changed — fetch new notifications and push
                    notes = list_notifications(username, limit=5)
                    yield (
                        f"data: {json.dumps({'type': 'new_notification', 'notification': notes[0] if notes else {}, 'unread_count': new_count})}\n\n"
                    )
                    last_count = new_count
            except Exception:
                # DB error — send keep-alive and continue
                yield ": keep-alive\n\n"
