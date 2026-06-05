"""
incident_service.py — Use Case 3 Timeline Reports
PDF fix: hardcoded hex colors (no hexval()), StreamingResponse-ready bytes output.
Event range filter: from_event / to_event slice.
"""
import io
from datetime import datetime
from backend.services.db import get_db

def _s(doc):
    return {k: v for k, v in doc.items() if k != "_id"} if doc else {}

TYPE_COLORS_HEX = {
    "care_log":    "#2d7ff9",
    "alert":       "#d94c4c",
    "pre_alert":   "#f59e0b",
    "task":        "#0b8a69",
    "assessment":  "#7c3aed",
    "incident":    "#b45309",
    "notification":"#6b7280",
}

def _parse_dt(s):
    if not s:
        return datetime.min
    # Use actual date string lengths NOT format string lengths
    # len("%Y-%m-%d") = 8 but "2026-05-20" = 10 chars — wrong slice breaks parsing
    for fmt, length in (
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%dT%H:%M",    16),
        ("%Y-%m-%d",          10),
    ):
        try:
            return datetime.strptime(str(s)[:length], fmt)
        except Exception:
            continue
    return datetime.min

def _in_range(dt_str, from_date, to_date):
    dt = _parse_dt(dt_str)
    if dt == datetime.min:
        return False
    if from_date:
        if dt < _parse_dt(from_date):
            return False
    if to_date:
        if dt > _parse_dt(to_date + "T23:59:59"):
            return False
    return True

def list_incidents():
    db = get_db()
    return [_s(i) for i in db.incidents.find()]

def add_incident(data: dict) -> dict:
    db = get_db()
    import random, re
    def _next_id_inc():
        docs = list(db.incidents.find({}, {"id": 1}))
        nums = []
        for d in docs:
            raw = re.sub(r"[^0-9]", "", str(d.get("id", "")))
            if raw:
                nums.append(int(raw))
        return f"idi{max(nums)+1 if nums else 1}"

    now = datetime.now().isoformat(timespec="seconds")
    ref = f"INC-{random.randint(10000, 99999)}"
    doc = {
        "id":           _next_id_inc(),
        "patient_id":   data["patient_id"],
        "patient_name": data["patient_name"],
        "ref":          ref,
        "reported_by":  data["reported_by"],
        "summary":      data["summary"],
        "created_at":   now,
    }
    db.incidents.insert_one(doc)
    return _s(doc)

def list_all_patients_for_timeline():
    db = get_db()
    return [_s(p) for p in db.patients.find({"status": {"$ne": "deleted"}})]

def get_patient_date_range(patient_id: str):
    db    = get_db()
    dates = []
    for log in db.care_logs.find({"patient_id": patient_id}, {"created_at": 1}):
        if log.get("created_at"):
            dates.append(log["created_at"])
    for a in db.alerts.find({"patient_id": patient_id}, {"created_at": 1}):
        if a.get("created_at"):
            dates.append(a["created_at"])
    for pa in db.pre_alerts.find({"patient_id": patient_id}, {"created_at": 1}):
        if pa.get("created_at"):
            dates.append(pa["created_at"])
    for t in db.tasks.find({"patient_id": patient_id}, {"created_at": 1}):
        if t.get("created_at"):
            dates.append(t["created_at"])
    assess = db.assessments.find_one({"patient_id": patient_id})
    if assess:
        for v in assess.get("versions", []):
            if v.get("created_at"):
                dates.append(v["created_at"])
    for inc in db.incidents.find({"patient_id": patient_id}):
        if inc.get("created_at"):
            dates.append(inc["created_at"])
    if not dates:
        today = datetime.now().strftime("%Y-%m-%d")
        return {"min_date": today, "max_date": today, "has_data": False}
    dates.sort()
    return {"min_date": dates[0][:10], "max_date": dates[-1][:10], "has_data": True}

def get_patient_timeline(patient_id: str, from_date=None, to_date=None,
                          from_event: int = None, to_event: int = None):
    db     = get_db()
    events = []

    for log in db.care_logs.find({"patient_id": patient_id}):
        ts = log.get("created_at", "")
        if not _in_range(ts, from_date, to_date):
            continue
        parts = []
        if log.get("meal_type"):         parts.append(f"Meal: {log['meal_type']}")
        if log.get("fluid_intake_ml") is not None:
            parts.append(f"Fluid: {log['fluid_intake_ml']}ml")
        if log.get("food_intake"):       parts.append(f"Food: {log['food_intake']}")
        if log.get("blood_pressure"):    parts.append(f"BP: {log['blood_pressure']}")
        if log.get("oxygen_level"):      parts.append(f"O2: {log['oxygen_level']}%")
        if log.get("sugar_level"):       parts.append(f"Sugar: {log['sugar_level']}")
        if log.get("sleep_hours") is not None:
            parts.append(f"Sleep: {log['sleep_hours']}h")
        if log.get("confusion") is True: parts.append("Confusion: Yes")
        events.append({
            "time":     ts,
            "type":     "care_log",
            "label":    "Care Log",
            "text":     f"By {log.get('created_by','')} — {log.get('notes','No notes')}",
            "detail":   " | ".join(parts),
            "severity": "info",
        })

    for al in db.alerts.find({"patient_id": patient_id}):
        ts = al.get("created_at", "")
        if not _in_range(ts, from_date, to_date):
            continue
        events.append({
            "time":     ts,
            "type":     "alert",
            "label":    f"Alert — {(al.get('severity','') or '').upper()}",
            "text":     al.get("title", "Alert"),
            "detail":   f"Evidence: {'; '.join(al.get('evidence',[]))} | Confidence: {al.get('confidence',0)}% | Policy: {al.get('policy_triggered','')}",
            "severity": al.get("severity", "medium"),
        })

    for pa in db.pre_alerts.find({"patient_id": patient_id}):
        ts = pa.get("created_at", "")
        if not _in_range(ts, from_date, to_date):
            continue
        events.append({
            "time":     ts,
            "type":     "pre_alert",
            "label":    "Pre-Alert",
            "text":     pa.get("title", "Pre-Alert"),
            "detail":   f"Evidence: {'; '.join(pa.get('evidence',[]))} | Confidence: {pa.get('confidence',0)}%",
            "severity": pa.get("severity", "medium"),
        })

    for t in db.tasks.find({"patient_id": patient_id}):
        ts = t.get("created_at", "")
        if not ts or not _in_range(ts, from_date, to_date):
            continue
        status = "Done" if t.get("done") else "Pending"
        events.append({
            "time":     ts,
            "type":     "task",
            "label":    "Task",
            "text":     f"{t.get('title','')} — assigned to {t.get('assigned_to','')} | Due: {t.get('due_time','')}",
            "detail":   f"Instruction: {t.get('instruction','')} | Status: {status}",
            "severity": "info",
        })

    assess = db.assessments.find_one({"patient_id": patient_id})
    if assess:
        for v in assess.get("versions", []):
            ts = v.get("created_at", "")
            if not _in_range(ts, from_date, to_date):
                continue
            events.append({
                "time":     ts,
                "type":     "assessment",
                "label":    f"Doctor Assessment v{v.get('version',1)}",
                "text":     f"By {v.get('created_by','')} — {v.get('summary','')}",
                "detail":   f"Instruction: {v.get('doctor_instruction','')} | Duration: {v.get('symptom_duration','')}",
                "severity": "info",
            })

    for inc in db.incidents.find({"patient_id": patient_id}):
        ts = inc.get("created_at", "")
        if not _in_range(ts, from_date, to_date):
            continue
        events.append({
            "time":     ts,
            "type":     "incident",
            "label":    "Incident",
            "text":     inc.get("summary", ""),
            "detail":   f"Ref: {inc.get('ref','')} | By: {inc.get('reported_by','')}",
            "severity": "high",
        })

    events.sort(key=lambda e: _parse_dt(e["time"]))

    # Apply event range filter (1-based index)
    total = len(events)
    if from_event is not None or to_event is not None:
        start = max(0, (from_event or 1) - 1)
        end   = min(total, to_event or total)
        events = events[start:end]

    return events, total

def export_patient_timeline_pdf(patient_id: str, from_date=None, to_date=None,
                                 from_event: int = None, to_event: int = None) -> bytes:
    """Returns PDF as bytes (for StreamingResponse). Table-based colored layout."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
    )

    db      = get_db()
    patient = _s(db.patients.find_one({"id": patient_id})) or {
        "name": patient_id, "age": "-", "room_no": "-", "diagnosis": "-"
    }
    events, total = get_patient_timeline(patient_id, from_date, to_date, from_event, to_event)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    styles = getSampleStyleSheet()

    # ── styles ────────────────────────────────────────────────────────────────
    title_style  = ParagraphStyle("TT", parent=styles["Title"],
                                  fontSize=17, spaceAfter=2,
                                  textColor=colors.HexColor("#18263d"))
    sub_style    = ParagraphStyle("SS", parent=styles["Normal"],
                                  fontSize=9, textColor=colors.HexColor("#6b7888"),
                                  spaceAfter=2, leading=14)
    label_style  = ParagraphStyle("LS", parent=styles["Normal"],
                                  fontSize=10, fontName="Helvetica-Bold",
                                  textColor=colors.white, leading=13)
    body_style   = ParagraphStyle("BS", parent=styles["Normal"],
                                  fontSize=9, textColor=colors.HexColor("#1a2333"),
                                  leading=13, spaceAfter=2)
    detail_style = ParagraphStyle("DS", parent=styles["Normal"],
                                  fontSize=8, textColor=colors.HexColor("#6b7888"),
                                  leading=12)
    time_style   = ParagraphStyle("TS", parent=styles["Normal"],
                                  fontSize=8, textColor=colors.HexColor("#6b7888"),
                                  leading=12)

    TYPE_COLORS = {
        "care_log":    "#2d7ff9",
        "alert":       "#d94c4c",
        "pre_alert":   "#e07b00",
        "task":        "#0b8a69",
        "assessment":  "#7c3aed",
        "incident":    "#b45309",
        "notification":"#6b7280",
    }
    TYPE_ICONS = {
        "care_log":    "CARE LOG",
        "alert":       "ALERT",
        "pre_alert":   "PRE-ALERT",
        "task":        "TASK",
        "assessment":  "ASSESSMENT",
        "incident":    "INCIDENT",
        "notification":"NOTIFICATION",
    }

    story = []

    # ── header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("CareTrust AI — Patient Timeline", title_style))
    story.append(HRFlowable(width="100%", thickness=2,
                            color=colors.HexColor("#2d7ff9"), spaceAfter=8))

    # Patient info table
    p_name  = str(patient.get("name","")).replace("<","&lt;").replace(">","&gt;")
    p_age   = str(patient.get("age",""))
    p_room  = str(patient.get("room_no",""))
    p_diag  = str(patient.get("diagnosis","")).replace("<","&lt;").replace(">","&gt;")
    info_data = [[
        Paragraph(f"<b>Patient:</b> {p_name}", sub_style),
        Paragraph(f"<b>Age:</b> {p_age}  <b>Room:</b> {p_room}", sub_style),
        Paragraph(f"<b>Diagnosis:</b> {p_diag}", sub_style),
    ]]
    info_table = Table(info_data, colWidths=["40%","25%","35%"])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f4f7ff")),
        ("ROUNDEDCORNERS", [6]),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.3*cm))

    date_range  = f"{from_date or 'Start'}  →  {to_date or 'Today'}"
    event_range = f"Events {from_event or 1}–{to_event or total} of {total} total"
    story.append(Paragraph(
        f"<b>Period:</b> {date_range}  &nbsp;|&nbsp;  <b>{event_range}</b>  &nbsp;|&nbsp;  "
        f"<b>Generated:</b> {datetime.now().strftime('%d %b %Y  %H:%M')}",
        sub_style
    ))
    story.append(Spacer(1, 0.4*cm))

    def _tint(hex_c, factor=0.12):
        """Blend color with white — ReportLab HexColor does not support alpha."""
        h = hex_c.lstrip("#")
        r, g, b = (int(h[i:i+2], 16)/255 for i in (0, 2, 4))
        tr = int((r*factor + 1*(1-factor)) * 255)
        tg = int((g*factor + 1*(1-factor)) * 255)
        tb = int((b*factor + 1*(1-factor)) * 255)
        return f"#{tr:02x}{tg:02x}{tb:02x}"

    # ── legend ────────────────────────────────────────────────────────────────
    types_present = list(dict.fromkeys(ev["type"] for ev in events))  # preserve order
    if types_present:
        legend_cells = []
        for t in types_present:
            hex_c = TYPE_COLORS.get(t, "#6b7280")
            lbl   = TYPE_ICONS.get(t, t.upper())
            legend_cells.append(
                Paragraph(f"<b>{lbl}</b>",
                          ParagraphStyle("LC", parent=styles["Normal"],
                                         fontSize=7, fontName="Helvetica-Bold",
                                         textColor=colors.HexColor(hex_c)))
            )
        # Pad to multiple of 4
        while len(legend_cells) % 4:
            legend_cells.append(Paragraph("", sub_style))
        legend_rows = [legend_cells[i:i+4] for i in range(0, len(legend_cells), 4)]
        leg_table = Table(legend_rows, colWidths=["25%","25%","25%","25%"])
        leg_style_cmds = [
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ]
        for i, t in enumerate(types_present[:len(legend_cells)]):
            col = i % 4
            row = i // 4
            hex_c = TYPE_COLORS.get(t, "#6b7280")
            leg_style_cmds.append(
                ("BACKGROUND", (col, row), (col, row), colors.HexColor(_tint(hex_c, 0.15)))
            )
            leg_style_cmds.append(
                ("LINEBELOW", (col, row), (col, row), 2,
                 colors.HexColor(hex_c))
            )
        leg_table.setStyle(TableStyle(leg_style_cmds))
        story.append(leg_table)
        story.append(Spacer(1, 0.4*cm))

    # ── events ────────────────────────────────────────────────────────────────
    if not events:
        story.append(Paragraph("No events found for the selected filters.", body_style))
    else:
        for ev in events:
            hex_c     = TYPE_COLORS.get(ev["type"], "#6b7280")
            color_obj = colors.HexColor(hex_c)
            bg_hex    = _tint(hex_c)   # proper white-blended tint
            time_str  = _parse_dt(ev["time"]).strftime("%d %b %Y  %H:%M") if ev["time"] else "—"
            lbl_str   = TYPE_ICONS.get(ev["type"], ev.get("label","").upper())

            safe_text   = (ev.get("text","")   or "").replace("<","&lt;").replace(">","&gt;")
            safe_detail = (ev.get("detail","") or "").replace("<","&lt;").replace(">","&gt;")

            # Left colour strip + content
            label_cell = Paragraph(f"<b>{lbl_str}</b>", label_style)
            time_cell  = Paragraph(time_str, time_style)
            text_cell  = Paragraph(safe_text, body_style)

            # Row 1: type badge + timestamp
            # Row 2: main text
            # Row 3: detail (if any)
            inner_rows = [
                [Paragraph(f"<b>{lbl_str}</b>",
                           ParagraphStyle("IH", parent=styles["Normal"],
                                          fontSize=9, fontName="Helvetica-Bold",
                                          textColor=color_obj)),
                 Paragraph(time_str,
                           ParagraphStyle("IT", parent=styles["Normal"],
                                          fontSize=8, textColor=colors.HexColor("#6b7888"),
                                          alignment=2))],
                [Paragraph(safe_text, body_style), ""],
            ]
            if safe_detail:
                inner_rows.append([
                    Paragraph(safe_detail, detail_style), ""
                ])

            inner_table = Table(inner_rows, colWidths=["68%","32%"])
            inner_cmds  = [
                ("SPAN",          (0,1), (1,1)),
                ("TOPPADDING",    (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ("LEFTPADDING",   (0,0), (-1,-1), 0),
                ("RIGHTPADDING",  (0,0), (-1,-1), 0),
                ("VALIGN",        (0,0), (-1,-1), "TOP"),
                ("LINEBELOW",     (0,0), (1,0), 0.4,
                 colors.HexColor(hex_c + "50")),
            ]
            if safe_detail:
                inner_cmds.append(("SPAN", (0,2), (1,2)))
            inner_table.setStyle(TableStyle(inner_cmds))

            # Outer card: colour strip | content
            card_data = [[
                "",   # left strip column (empty, coloured)
                inner_table,
            ]]
            card = Table(card_data, colWidths=[0.25*cm, None])
            card.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (0,0), color_obj),
                ("BACKGROUND",    (1,0), (1,0), colors.HexColor(bg_hex)),
                ("TOPPADDING",    (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ("LEFTPADDING",   (1,0), (1,0), 10),
                ("RIGHTPADDING",  (1,0), (1,0), 8),
                ("LEFTPADDING",   (0,0), (0,0), 0),
                ("RIGHTPADDING",  (0,0), (0,0), 0),
                ("VALIGN",        (0,0), (-1,-1), "TOP"),
                ("ROUNDEDCORNERS", [4]),
            ]))
            story.append(card)
            story.append(Spacer(1, 0.18*cm))

    doc.build(story)
    return buf.getvalue()

def export_incident_pdf(incident_id: str) -> bytes:
    """Legacy — export full timeline for the patient of this incident."""
    db  = get_db()
    inc = _s(db.incidents.find_one({"id": incident_id}))
    if not inc:
        raise FileNotFoundError("Incident not found")
    return export_patient_timeline_pdf(inc.get("patient_id", ""))
