/* CareTrust AI — app.js
   All roles wired. All fixes applied.
   Login: SSE connect after nav built — no blocking.
   Tasks: Combined nurse+caretaker grouped dropdown for doctor/manager/chief.
   Ask AI: Removed from doctor and manager.
   Impersonation: Admin can view as any worker.
   SSE: stream_unavailable handled gracefully — no login interference.
*/

const API = 'http://localhost:8000';
let currentUser      = null;
let _adminUser       = null;
let _sseSource       = null;
let pendingImageFile = [];  // Change 6: array, max 4 images per query
let _timelinePatientId   = null;
let _timelinePatientName = null;
let _timelineTotal       = 0;

// ── styles injected ───────────────────────────────────────────────────────────
(function injectStyles() {
  const s = document.createElement("style");
  s.textContent = `
    @keyframes slideIn{from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:translateX(0)}}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    .row-between{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
    .patient-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
    .chat-messages{height:400px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;
      padding:12px;background:#f7f9fd;border:1px solid #e1e7f0;border-radius:14px;margin-bottom:10px}
    .chat-msg{display:flex}.chat-msg.user{justify-content:flex-end}.chat-msg.assistant{justify-content:flex-start}
    .chat-bubble{max-width:80%;padding:10px 14px;border-radius:16px;font-size:14px;line-height:1.5}
    .chat-msg.user .chat-bubble{background:#2d7ff9;color:#fff;border-bottom-right-radius:5px}
    .chat-msg.assistant .chat-bubble{background:#fff;color:#1a2333;border:1px solid #e2e8f0;border-bottom-left-radius:5px}
    .typing-dots{display:inline-flex;align-items:center;gap:5px;padding:2px 4px}
    .typing-dots span{width:8px;height:8px;border-radius:50%;background:#9ab0c8;display:inline-block;animation:typingBounce 1.2s infinite ease-in-out}
    .typing-dots span:nth-child(1){animation-delay:0s}
    .typing-dots span:nth-child(2){animation-delay:0.2s}
    .typing-dots span:nth-child(3){animation-delay:0.4s}
    @keyframes typingBounce{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-6px);opacity:1}}
    .chat-input-row{display:flex;gap:8px;align-items:flex-end}
    .chat-input-row textarea{flex:1;min-height:44px;max-height:120px;resize:vertical;
      padding:10px 13px;border:1px solid #d7dce5;border-radius:11px;font-size:14px;background:#fafbfc}
    .upload-btn-label{padding:10px 14px;border:1px solid #d7dce5;border-radius:11px;
      background:#f7f9fd;cursor:pointer;font-size:18px;line-height:1}
    .img-preview{display:flex;align-items:center;gap:8px;padding:8px;background:#f4f7ff;
      border-radius:8px;margin-bottom:8px}
    .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  `;
  document.head.appendChild(s);
})();

// ── toast ─────────────────────────────────────────────────────────────────────
function showToast(message, type = "success", duration = 4500) {
  let c = document.getElementById("toastContainer");
  if (!c) {
    c = document.createElement("div");
    c.id = "toastContainer";
    c.style.cssText = "position:fixed;top:22px;right:22px;z-index:9999;display:flex;flex-direction:column;gap:10px;max-width:360px;pointer-events:none";
    document.body.appendChild(c);
  }
  const cols  = {success:"#0b8a69",error:"#d94c4c",warning:"#f59e0b",info:"#2d7ff9",alert:"#d94c4c",prealert:"#f59e0b"};
  const icons = {success:"✓",error:"✗",warning:"⚡",info:"ℹ",alert:"🚨",prealert:"⚠"};
  const col   = cols[type]  || cols.info;
  const icon  = icons[type] || "ℹ";
  const t = document.createElement("div");
  t.style.cssText = `background:${col};color:#fff;padding:12px 16px;border-radius:12px;font-size:13px;
    font-weight:500;box-shadow:0 4px 16px rgba(0,0,0,.18);display:flex;align-items:flex-start;
    gap:10px;animation:slideIn .25s ease;line-height:1.4;pointer-events:auto`;
  t.innerHTML = `<span style="font-size:16px;flex-shrink:0">${icon}</span><span>${message}</span>`;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, duration);
}

function showSaving(btn) { if (btn) { btn._orig = btn.textContent; btn.textContent = "Saving…"; btn.disabled = true; } }
function doneSaving(btn) { if (btn) { btn.textContent = btn._orig || "Save"; btn.disabled = false; } }

// ── api ───────────────────────────────────────────────────────────────────────
async function api(url, method = "GET", body = null, isForm = false) {
  const opts = { method, headers: {} };
  if (body && !isForm) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  if (body && isForm)  { opts.body = body; }
  try {
    const r = await fetch(API + url, opts);
    if (!r.ok && r.status !== 200) { console.warn(`API ${url} → ${r.status}`); }
    return await r.json();
  } catch (e) { console.error(url, e); return {}; }
}

// ── auth ──────────────────────────────────────────────────────────────────────
async function doLogin() {
  const u = document.getElementById("loginUser").value.trim();
  const p = document.getElementById("loginPass").value.trim();
  if (!u || !p) return;
  try {
    const res = await api("/api/login", "POST", { username: u, password: p });
    if (res.success) {
      currentUser = res.user;
      document.getElementById("loginScreen").classList.add("hidden");
      document.getElementById("appShell").classList.remove("hidden");
      document.getElementById("loginError").classList.add("hidden");
      buildNav();         // build UI first
      startSSE();         // then connect SSE — non-blocking
    } else {
      document.getElementById("loginError").classList.remove("hidden");
    }
  } catch (e) {
    document.getElementById("loginError").classList.remove("hidden");
    console.error("Login error:", e);
  }
}

function quickLogin(u, p) {
  document.getElementById("loginUser").value = u;
  document.getElementById("loginPass").value = p;
  doLogin();
}

function doLogout() {
  endImpersonation(true);
  stopSSE();
  currentUser = null;
  document.getElementById("appShell").classList.add("hidden");
  document.getElementById("loginScreen").classList.remove("hidden");
  document.getElementById("loginUser").value = "";
  document.getElementById("loginPass").value = "";
  document.getElementById("loginError").classList.add("hidden");
}

document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeModal("simpleModal");
  const ls = document.getElementById("loginScreen");
  if (e.key === "Enter" && ls && !ls.classList.contains("hidden")) doLogin();
});

// ── SSE ───────────────────────────────────────────────────────────────────────
function startSSE() {
  if (!currentUser) return;
  stopSSE();
  try {
    _sseSource = new EventSource(`${API}/api/notifications/stream/${currentUser.username}`);
    _sseSource.onmessage = (e) => {
      if (!e.data || e.data.trim() === "") return;  // ignore keep-alive comments
      try {
        const data = JSON.parse(e.data);
        if (data.type === "init") {
          updateBellCount(data.unread_count);
          _renderNotifList(data.notifications || []);
        } else if (data.type === "new_notification") {
          updateBellCount(data.unread_count);
          prependNotif(data.notification);
          const n = data.notification;
          if (n && n.message) {
            const tt = n.type === "alert" ? "alert" : n.type === "pre_alert_trigger" ? "prealert" : "info";
            showToast(n.message, tt, 6000);
          }
        } else if (data.type === "stream_unavailable") {
          // Change streams not available — fallback is already running server-side
          console.info("SSE: server-side poll fallback active");
        }
      } catch (err) { /* ignore malformed keep-alive lines */ }
    };
    _sseSource.onerror = () => {
      // Browser auto-reconnects EventSource — just log it
      console.info("SSE connection interrupted, browser will retry…");
    };
  } catch (e) {
    console.warn("SSE not supported, notifications will not push:", e);
  }
}

function stopSSE() {
  if (_sseSource) { try { _sseSource.close(); } catch (_) {} _sseSource = null; }
}

function updateBellCount(count) {
  const bell = document.getElementById("bellCount");
  if (!bell) return;
  if (count > 0) { bell.textContent = count; bell.classList.remove("hidden"); }
  else           { bell.classList.add("hidden"); }
}

function prependNotif(n) {
  if (!n) return;
  const list  = document.getElementById("notificationList");
  const panel = document.getElementById("notificationPanel");
  if (!list || !panel || panel.classList.contains("hidden")) return;
  const div = document.createElement("div");
  div.innerHTML = _notifCard(n);
  if (div.firstChild) list.insertBefore(div.firstChild, list.firstChild);
}

function _notifCard(n) {
  if (!n) return "";
  const unread = !n.read_by?.includes(currentUser?.username);
  const icons  = { assessment:"📋", task_notice:"✅", pre_alert_trigger:"⚠️",
                   policy_toggle:"🔀", policy_request:"📝", policy_decision:"✔️",
                   info:"ℹ️", alert:"🚨" };
  return `<div class="bell-note ${unread ? "unread" : ""}">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap">
      <span>${icons[n.type] || "🔔"} ${n.message || ""}</span>
      ${n.type === "pre_alert_trigger" && !n.acked_by?.includes(currentUser?.username)
        ? `<button class="btn btn-sm btn-primary" onclick="ackNotif('${n.id}')">Acknowledge</button>` : ""}
    </div>
    <small class="muted">${(n.created_at || "").replace("T", " ")}</small>
  </div>`;
}

function _renderNotifList(notes) {
  const list = document.getElementById("notificationList");
  if (!list) return;
  list.innerHTML = notes.length
    ? notes.map(_notifCard).join("")
    : `<p class="muted" style="padding:12px">No notifications.</p>`;
}

function toggleNotifications() {
  const panel = document.getElementById("notificationPanel");
  panel.classList.toggle("hidden");
  if (!panel.classList.contains("hidden")) loadNotifications();
}

async function loadNotifications() {
  if (!currentUser) return;
  const notes = await api(`/api/notifications/${currentUser.username}`);
  _renderNotifList(notes || []);
  const unread = (notes || []).filter(n => !n.read_by?.includes(currentUser.username)).length;
  updateBellCount(unread);
}

async function markNotificationsRead() {
  if (!currentUser) return;
  await api(`/api/notifications/${currentUser.username}/read`, "POST");
  updateBellCount(0);
  loadNotifications();
}

async function ackNotif(nid) {
  await api("/api/notifications/ack", "POST", { notification_id: nid, username: currentUser.username });
  showToast("Acknowledged ✓", "success");
  loadNotifications();
}

// ── nav map ───────────────────────────────────────────────────────────────────
const NAV_MAP = {
  nurse:            [["worker-dashboard","Dashboard"],["my-patients","My Patients"],["care-log","Submit Care Log"],["ask-ai","Ask AI"]],
  caretaker:        [["worker-dashboard","Dashboard"],["my-patients","My Patients"],["care-log","Submit Care Log"]],
  doctor_assistant: [["worker-dashboard","Dashboard"],["doctor-management","Tasks & Assessments"],["doctor-docs","Docs & Policies"]],
  chief_nurse:      [["worker-dashboard","Dashboard"],["my-patients","All Patients"],["chief","Transfer & Rooms"],["ask-ai","Ask AI"]],
  manager:          [["worker-dashboard","Dashboard"],["manager","Policies & Incidents"],["policies","Patient Policies"],["log-fields","Custom Log Fields"]],
  admin:            [["worker-dashboard","Dashboard"],["admin","Admin"]],
};

function buildNav() {
  if (!currentUser) return;
  document.getElementById("userAvatar").textContent    = (currentUser.name || "U")[0].toUpperCase();
  document.getElementById("userNameLabel").textContent = currentUser.name || "";
  document.getElementById("userRoleLabel").textContent = currentUser.role || "";
  const items = NAV_MAP[currentUser.role] || NAV_MAP.nurse;
  document.getElementById("sideNav").innerHTML = items.map(([id, label]) =>
    `<button class="nav-item" onclick="showView('${id}')">${label}</button>`
  ).join("");
  showView(items[0][0]);
}

function showView(viewId) {
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
  const el = document.getElementById(`view-${viewId}`);
  if (el) el.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach(b => {
    const match = (NAV_MAP[currentUser?.role] || []).find(x => x[0] === viewId);
    if (match && b.textContent === match[1]) b.classList.add("active");
  });
  const titles = {
    "worker-dashboard": "Dashboard", "my-patients": "My Patients",
    "care-log": "Submit Care Log",   "ask-ai": "Ask AI",
    "doctor-management": "Tasks & Assessments", "doctor-docs": "Docs & Policies",
    "chief": "Transfer & Rooms",     "manager": "Policies & Incidents",
    "policies": "Patient Policies",  "admin": "Admin",
    "log-fields": "Custom Log Fields",
  };
  document.getElementById("pageTitle").textContent = titles[viewId] || viewId;
  const loaders = {
    "worker-dashboard": renderWorkerDashboard,
    "my-patients":      renderMyPatients,
    "care-log":         populateCareLog,
    "ask-ai":           populateAskAI,
    "doctor-management":populateDoctorTools,
    "doctor-docs":      populateDoctorDocs,
    "chief":            populateChief,
    "manager":          renderManager,
    "policies":         renderPoliciesView,
    "log-fields":       loadLogFields,
    "admin":            renderAdmin,
  };
  if (loaders[viewId]) loaders[viewId]();
}

// ── dashboard ─────────────────────────────────────────────────────────────────
async function renderWorkerDashboard() {
  if (!currentUser) return;
  const role   = currentUser.role;
  const worker = currentUser.username;
  const isPrivileged = ["doctor_assistant", "manager", "chief_nurse", "admin"].includes(role);

  const [alerts, preAlerts, tasks, patients] = await Promise.all([
    api(`/api/alerts?worker=${worker}&role=${role}`),
    api(`/api/pre-alerts?worker=${worker}&role=${role}`),
    api(`/api/tasks?worker=${worker}&role=${role}`),
    api(`/api/patients?worker=${worker}&role=${role}`),
  ]);

  // Date filters — alerts show today only, pre-alerts show today + yesterday
  const today     = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const visibleAlerts    = (alerts    || []).filter(a  => (a.created_at  || "").slice(0, 10) === today);
  const visiblePreAlerts = (preAlerts || []).filter(pa => {
    const d = (pa.created_at || "").slice(0, 10);
    return d === today || d === yesterday;
  });

  // Stats
  const grid = document.getElementById("workerStats");
  if (grid) {
    const pending = (tasks || []).filter(t => !t.done).length;
    grid.innerHTML = [
      ["Patients",      (patients || []).length,          "#2d7ff9"],
      ["Active Alerts", visibleAlerts.length,             "#d94c4c"],
      ["Pre-Alerts",    visiblePreAlerts.length,          "#f59e0b"],
      ["Pending Tasks", pending,                          "#0b8a69"],
    ].map(([l, v, c]) => `<div class="stat-card"><span>${l}</span><strong style="color:${c}">${v}</strong></div>`).join("");
  }

  // Alerts — today only
  const al = document.getElementById("workerAlertList");
  if (al) al.innerHTML = visibleAlerts.length
    ? visibleAlerts.map(renderAlertCard).join("")
    : `<p class="empty-state">No alerts today</p>`;

  // Pre-alerts — today + yesterday
  const pal = document.getElementById("workerPreAlertList");
  if (pal) {
    const canTrigger = ["chief_nurse", "manager", "doctor_assistant"].includes(role);
    pal.innerHTML = visiblePreAlerts.length
      ? visiblePreAlerts.map(pa => renderPreAlertCard(pa, canTrigger)).join("")
      : `<p class="empty-state">No pre-alerts</p>`;
  }

  // Tasks — role-based, no dropdown
  const tl = document.getElementById("workerTaskList");
  const wfEl = document.getElementById("doctorTaskWorkerFilter");
  if (wfEl) wfEl.style.display = "none";
  if (tl) {
    let show = [];
    if (isPrivileged) {
      // Doctor / Chief / Manager — fetch ALL tasks ordered by patient then worker
      const allTasks = await api("/api/tasks");
      show = (allTasks || []).sort((a, b) => {
        if (a.patient_id < b.patient_id) return -1;
        if (a.patient_id > b.patient_id) return  1;
        return (a.assigned_to || "").localeCompare(b.assigned_to || "");
      });
    } else {
      // Nurse / Caretaker — only their own tasks (API already filters)
      show = tasks || [];
    }
    tl.innerHTML = show.length
      ? show.map(t => renderTaskCard(t, isPrivileged)).join("")
      : `<p class="empty-state">No tasks</p>`;
  }
}


function renderAlertCard(a) {
  const sevCol = { high: "#d94c4c", medium: "#f59e0b", low: "#6b7888" }[a.severity] || "#6b7888";
  return `<div class="alert-card" style="border-left:4px solid ${sevCol}">
    <div class="alert-top">
      <span style="width:10px;height:10px;border-radius:50%;background:${sevCol};flex-shrink:0;animation:pulse 1.5s infinite"></span>
      <strong style="flex:1">${a.title}</strong>
      <span class="badge" style="background:${sevCol}22;color:${sevCol}">${(a.severity || "").toUpperCase()}</span>
    </div>
    <div class="confidence-row">
      <small>Confidence</small>
      <div class="confidence-bar-wrap"><div class="confidence-bar" style="width:${a.confidence || 0}%;background:${sevCol}"></div></div>
      <small><b>${a.confidence || 0}%</b></small>
    </div>
    ${(a.evidence || []).length ? `<details class="evidence-box"><summary>Evidence (${a.evidence.length})</summary><ul>${a.evidence.map(e => `<li>${e}</li>`).join("")}</ul></details>` : ""}
    ${a.reasoning ? `<p style="font-size:13px;color:#4b5562;font-style:italic">${a.reasoning}</p>` : ""}
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      ${a.policy_triggered ? `<span class="badge">${a.policy_triggered}</span>` : ""}
      <span class="badge">${a.patient_name || ""} · Room ${a.room_no || ""}</span>
    </div>
  </div>`;
}

function renderPreAlertCard(pa, canTrigger) {
  const triggered = pa.status === "triggered" || pa.triggered_by;
  return `<div class="alert-card" style="border-left:4px solid #f59e0b">
    <div class="alert-top">
      <span style="width:10px;height:10px;border-radius:50%;background:#f59e0b;flex-shrink:0"></span>
      <strong style="flex:1">${pa.title}</strong>
      <span class="badge badge-pre">${(pa.severity || "").toUpperCase()}</span>
    </div>
    <div class="confidence-row">
      <small>Confidence</small>
      <div class="confidence-bar-wrap"><div class="confidence-bar" style="width:${pa.confidence || 0}%;background:#f59e0b"></div></div>
      <small><b>${pa.confidence || 0}%</b></small>
    </div>
    ${(pa.evidence || []).length ? `<details class="evidence-box"><summary>Evidence</summary><ul>${pa.evidence.map(e => `<li>${e}</li>`).join("")}</ul></details>` : ""}
    ${pa.reasoning ? `<p style="font-size:13px;color:#4b5562;font-style:italic">${pa.reasoning}</p>` : ""}
    <div style="display:flex;gap:8px;justify-content:space-between;align-items:center;flex-wrap:wrap">
      <span class="badge">${pa.patient_name || ""} · Room ${pa.room_no || ""}</span>
      ${canTrigger && !triggered
        ? `<button class="btn btn-sm btn-primary" onclick="triggerPreAlert('${pa.id}')">⚡ Trigger to Nurse</button>`
        : triggered ? `<span class="badge" style="background:#d4edda;color:#155724">✓ Triggered</span>` : ""}
    </div>
  </div>`;
}

function renderTaskCard(t, canManage) {
  const isNurseOrCaretaker = currentUser && (currentUser.role === "nurse" || currentUser.role === "caretaker");
  // Show Complete button when task is manual (no linked field) and not yet done
  const isManual       = !t.linked_field || t.completion_mode === "manual";
  const showCompleteBtn = isNurseOrCaretaker && isManual && !t.done;
  const modeLabel       = t.linked_field
    ? `Auto: ${t.linked_field}`
    : (t.completion_mode === "manual" ? "Manual" : "");
  return `<div class="task-item">
    <div class="row-between">
      <span><span class="task-tick ${t.done ? "done" : "pending"}">${t.done ? "✓" : "○"}</span><strong>${t.title}</strong></span>
      <span class="muted" style="font-size:12px">${t.due_time || ""}</span>
    </div>
    ${t.instruction ? `<span class="task-instr">${t.instruction}</span>` : ""}
    <div style="font-size:12px;color:#6b7888">Patient: ${t.patient_id} · Assigned: ${t.assigned_to || "—"}</div>
    ${modeLabel ? `<span style="font-size:11px;color:#9aa3af">${modeLabel}</span>` : ""}
    ${showCompleteBtn ? `<div class="task-actions">
      <button class="btn btn-sm btn-active" onclick="completeTask('${t.id}')">✓ Complete</button>
    </div>` : ""}
    ${canManage && !t.done ? `<div class="task-actions">
      <button class="btn btn-sm btn-secondary" onclick="sendTaskNotice('${t.id}')">Send Notice</button>
      <button class="btn btn-sm btn-danger" onclick="deleteTask('${t.id}')">Delete</button>
    </div>` : ""}
  </div>`;
}

async function triggerPreAlert(paId) {
  const res = await api("/api/pre-alerts/trigger", "POST", { pre_alert_id: paId, triggered_by: currentUser.username });
  if (res.id) { showToast("Pre-alert triggered — nurse notified", "warning"); renderWorkerDashboard(); }
}
async function sendTaskNotice(taskId) { await api(`/api/tasks/send/${taskId}?sent_by=${currentUser.username}`, "POST"); showToast("Task notice sent ✓", "success"); renderWorkerDashboard(); }
async function deleteTask(taskId)     { if (!confirm("Delete this task?")) return; await api("/api/tasks/delete", "POST", { task_id: taskId, deleted_by: currentUser.username }); showToast("Task deleted", "info"); renderWorkerDashboard(); }
async function completeTask(taskId)   { const res = await api("/api/tasks/complete", "POST", { task_id: taskId, completed_by: currentUser.username }); if (res.id) { showToast("Task marked complete ✓", "success"); renderWorkerDashboard(); } else { showToast(res.error || "Could not complete task", "error"); } }

// ── my patients ────────────────────────────────────────────────────────────────
async function renderMyPatients() {
  const patients = await api(`/api/patients?worker=${currentUser.username}&role=${currentUser.role}`);
  const grid     = document.getElementById("patientGrid");
  if (!patients?.length) { grid.innerHTML = `<p class="empty-state">No patients assigned.</p>`; return; }
  grid.innerHTML = patients.map(p => `
    <div class="patient-card">
      <div class="patient-top">
        <div><strong>${p.name}</strong><div class="patient-meta">${p.age}y · ${p.gender} · Room ${p.room_no}</div></div>
        <span class="badge">${p.diagnosis}</span>
      </div>
      <div class="patient-meta-row"><span>Nurse: ${p.assigned_nurse || "—"}</span><span>Caretaker: ${p.caretaker || "—"}</span></div>
    </div>`).join("");
}

// ── care log ──────────────────────────────────────────────────────────────────
async function populateCareLog() {
  const patients = await api(`/api/patients?worker=${currentUser.username}&role=${currentUser.role}`);
  const opts    = (patients || []).map(p => `<option value="${p.id}">${p.name} (${p.room_no})</option>`).join("");
  const incOpts = (patients || []).map(p => `<option value="${p.id}">${p.name} — Room ${p.room_no}</option>`).join("");

  const sel = document.getElementById("logPatientSelect");
  if (sel) sel.innerHTML = opts;

  // Render dynamic custom fields from Manager log_fields registry
  const fields    = await getLogFields();
  const container = document.getElementById("extraFieldsContainer");

  // Populate incident dropdown AFTER getLogFields so nothing overwrites it
  const incSel = document.getElementById("incidentPatientSelect");
  if (incSel) incSel.innerHTML = incOpts;

  if (!container) return;
  // Only show custom fields (not built-in fixed fields)
  const builtIn   = ["fluid_intake_ml","food_intake","blood_pressure","oxygen_level",
                     "sugar_level","sleep_hours","confusion","notes","meal_type"];
  const custom    = (fields || []).filter(f => !builtIn.includes(f.field));
  if (!custom.length) { container.innerHTML = ""; return; }

  container.innerHTML = `
    <div style="margin-top:8px;margin-bottom:4px;font-size:12px;font-weight:700;color:#6b7888;text-transform:uppercase;letter-spacing:.05em">
      Custom Fields
    </div>
    <div class="grid-2">` +
    custom.map(f => {
      const unit = f.unit ? ` (${f.unit})` : "";
      if (f.type === "yes_no") {
        return `<div class="form-group">
          <label>${f.label}${unit}</label>
          <select id="extra_${f.field}">
            <option value="">-- optional --</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        </div>`;
      } else {
        return `<div class="form-group">
          <label>${f.label}${unit}</label>
          <input id="extra_${f.field}" type="number" step="any" placeholder="e.g. ${f.unit||"value"}">
        </div>`;
      }
    }).join("") +
    `</div>`;
}

async function submitCareLog() {
  const btn      = document.querySelector("#view-care-log .btn-primary");
  showSaving(btn);
  const sleepVal = document.getElementById("logSleep")?.value;
  const payload  = {
    patient_id:      document.getElementById("logPatientSelect")?.value,
    created_by:      currentUser.username,
    role:            currentUser.role,
    meal_type:       document.getElementById("logMeal")?.value      || null,
    fluid_intake_ml: parseInt(document.getElementById("logFluid")?.value)   || null,
    food_intake:     document.getElementById("logFood")?.value      || null,
    blood_pressure:  document.getElementById("logBP")?.value        || null,
    oxygen_level:    parseInt(document.getElementById("logOxygen")?.value)  || null,
    sugar_level:     document.getElementById("logSugar")?.value     || null,
    sleep_hours:     sleepVal !== "" && sleepVal != null ? parseFloat(sleepVal) : null,
    confusion:       document.getElementById("logConfusion")?.value === "true"  ? true
                   : document.getElementById("logConfusion")?.value === "false" ? false : null,
    notes:           document.getElementById("logNotes")?.value     || null,
  };
  // Collect custom extra_fields from dynamic inputs
  const extraFields = {};
  const builtIn     = ["fluid_intake_ml","food_intake","blood_pressure","oxygen_level",
                       "sugar_level","sleep_hours","confusion","notes","meal_type"];
  const container   = document.getElementById("extraFieldsContainer");
  if (container) {
    container.querySelectorAll("[id^=extra_]").forEach(el => {
      const fieldKey = el.id.replace("extra_", "");
      const val      = el.value;
      if (val === "" || val == null) return;
      if (val === "true")  { extraFields[fieldKey] = true;  return; }
      if (val === "false") { extraFields[fieldKey] = false; return; }
      const num = parseFloat(val);
      extraFields[fieldKey] = isNaN(num) ? val : num;
    });
  }
  if (Object.keys(extraFields).length) payload.extra_fields = extraFields;

  const res = await api("/api/logs", "POST", payload);
  doneSaving(btn);
  if (!res.log) { showToast("Failed to save log", "error"); return; }
  showToast("✓ Care log saved successfully", "success");
  if (res.completed_tasks?.length) showToast(`Tasks completed: ${res.completed_tasks.join(", ")}`, "info", 5000);
  if (res.new_alerts?.length)      res.new_alerts.forEach(al => showToast(`🚨 Alert: ${al.title} (${al.confidence}%)`, "alert", 8000));
  if (res.new_pre_alerts?.length)  res.new_pre_alerts.forEach(pa => showToast(`⚠ Pre-Alert: ${pa.title}`, "prealert", 7000));
  ["logMeal","logFood","logConfusion","logBP","logOxygen","logSugar","logNotes","logFluid","logSleep"]
    .forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
  // Clear custom fields
  if (container) container.querySelectorAll("[id^=extra_]").forEach(el => { el.value = ""; });
}

async function submitIncidentReport() {
  const btn = document.querySelector('#incidentReportForm .btn-primary');
  showSaving(btn);
  const patientId = document.getElementById('incidentPatientSelect')?.value;
  const summary   = document.getElementById('incidentSummary')?.value?.trim();
  if (!patientId || !summary) {
    showToast('Select a patient and enter a summary', 'error');
    doneSaving(btn);
    return;
  }
  const patients = await api(`/api/patients?worker=${currentUser.username}&role=${currentUser.role}`);
  const patient  = (patients || []).find(p => p.id === patientId);
  const res = await api('/api/incidents', 'POST', {
    patient_id:   patientId,
    patient_name: patient?.name || patientId,
    reported_by:  currentUser.username,
    summary,
  });
  doneSaving(btn);
  if (res.id) {
    showToast(`Incident ${res.ref} reported`, 'warning', 6000);
    document.getElementById('incidentSummary').value = '';
  } else {
    showToast('Failed to submit incident', 'error');
  }
}

// ── ask AI ────────────────────────────────────────────────────────────────────
async function populateAskAI() {
  const role = currentUser.role;
  // Chief nurse sees all patients; nurse/caretaker/admin see their assigned patients
  let patients;
  if (role === "chief_nurse" || role === "admin") {
    patients = await api("/api/patients");
  } else {
    patients = await api(`/api/patients?worker=${currentUser.username}&role=${role}`);
  }
  const sel = document.getElementById("askPatientSelect");
  if (sel) {
    sel.innerHTML = (patients || []).map(p => `<option value="${p.id}">${p.name} (${p.room_no})</option>`).join("");
    loadChatHistory();
  }
}

async function loadChatHistory() {
  const pid   = document.getElementById("askPatientSelect")?.value;
  if (!pid) return;
  const hist  = await api(`/api/chat-history/${pid}`);
  const box   = document.getElementById("chatMessages");
  const label = document.getElementById("chatHistoryLabel");
  if (!box) return;
  box.innerHTML = "";
  if (hist?.length) {
    if (label) label.textContent = `Continuing from previous conversation (${hist.length} messages)`;
    hist.forEach(m => appendChatMsg(m.role === "user" ? "user" : "assistant", m.content));
  } else {
    if (label) label.textContent = "New conversation";
  }
}

function _renderMarkdown(text) {
  // Escape HTML first, then apply safe controlled formatting
  let s = (text || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  // Bold: **text**
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Split into lines and process
  const lines = s.split('\n');
  let html = '', inUl = false, inOl = false;
  lines.forEach((line, idx) => {
    const ulMatch  = line.match(/^[\*\-]\s+(.+)/);
    const olMatch  = line.match(/^(\d+)\.\s+(.+)/);
    const hMatch   = line.match(/^(#{1,3})\s+(.+)/);
    if (ulMatch) {
      if (inOl) { html += '</ol>'; inOl = false; }
      if (!inUl) { html += '<ul style="margin:8px 0;padding:0;list-style:none">'; inUl = true; }
      html += `<li style="display:flex;gap:8px;align-items:flex-start;margin-bottom:5px"><span style="color:#2d7ff9;flex-shrink:0;font-size:15px;line-height:1.5">•</span><span style="line-height:1.6">${ulMatch[1]}</span></li>`;
    } else if (olMatch) {
      if (inUl) { html += '</ul>'; inUl = false; }
      if (!inOl) { html += '<ol style="margin:8px 0;padding:0;list-style:none;counter-reset:li">'; inOl = true; }
      html += `<li style="display:flex;gap:8px;align-items:flex-start;margin-bottom:5px"><span style="color:#2d7ff9;font-weight:700;flex-shrink:0;min-width:20px;line-height:1.5">${olMatch[1]}.</span><span style="line-height:1.6">${olMatch[2]}</span></li>`;
    } else {
      if (inUl) { html += '</ul>'; inUl = false; }
      if (inOl) { html += '</ol>'; inOl = false; }
      if (hMatch) {
        const sz = hMatch[1].length === 1 ? '15px' : hMatch[1].length === 2 ? '14px' : '13px';
        html += `<div style="font-weight:700;color:#18263d;font-size:${sz};margin:10px 0 4px;border-bottom:1px solid #e5e7eb;padding-bottom:3px">${hMatch[2]}</div>`;
      } else if (line.trim() === '') {
        html += '<div style="height:7px"></div>';
      } else {
        html += `<div style="line-height:1.65;margin-bottom:2px">${line}</div>`;
      }
    }
  });
  if (inUl) html += '</ul>';
  if (inOl) html += '</ol>';
  return html;
}

function _buildUserMsgHTML(text, images) {
  // Build user message with optional images above text — like ChatGPT/Claude
  let html = '';
  if (images && images.length) {
    html += `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:${text ? '8px' : '0'}">`;
    images.forEach(f => {
      html += `<img src="${URL.createObjectURL(f)}" style="max-height:120px;max-width:160px;border-radius:8px;object-fit:cover;border:1px solid rgba(255,255,255,0.3)">`;
    });
    html += '</div>';
  }
  if (text) {
    const safe = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    html += `<span style="line-height:1.6">${safe}</span>`;
  }
  return html;
}

function appendChatMsg(role, text, images) {
  const box = document.getElementById('chatMessages');
  if (!box) return;
  const d = document.createElement('div');
  d.className = `chat-msg ${role}`;
  let inner;
  if (role === 'user') {
    inner = _buildUserMsgHTML(text, images);
  } else {
    // If text is raw HTML (e.g. typing-dots indicator) skip markdown escaping
    inner = text.startsWith('<') ? text : _renderMarkdown(text);
  }
  d.innerHTML = `<div class="chat-bubble">${inner}</div>`;
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
}

function onImageSelected(input) {
  const files = Array.from(input.files || []);
  if (!files.length) return;
  // Change 6: max 4 images per query
  if (pendingImageFile.length >= 4) {
    showToast('Maximum 4 images per query — send first before adding more', 'warning');
    input.value = '';
    return;
  }
  const remaining = 4 - pendingImageFile.length;
  const toAdd     = files.slice(0, remaining);
  if (files.length > remaining) {
    showToast(`Only ${remaining} more image(s) allowed — ${files.length - remaining} skipped`, 'warning');
  }
  pendingImageFile = pendingImageFile.concat(toAdd);
  input.value = '';  // reset so same file can be re-selected
  _renderImagePreview();
}

function _renderImagePreview() {
  const p = document.getElementById('imgPreview');
  if (!p) return;
  if (!pendingImageFile.length) { p.classList.add('hidden'); p.innerHTML = ''; return; }
  p.classList.remove('hidden');
  p.innerHTML =
    `<span style="font-size:12px;font-weight:600;color:#2d7ff9;margin-right:6px">${pendingImageFile.length}/4 images</span>` +
    pendingImageFile.map((f, i) =>
      `<span style="display:inline-flex;align-items:center;gap:4px;background:#f0f4ff;border-radius:8px;padding:4px 8px;font-size:12px;margin-right:4px">
        <img src="${URL.createObjectURL(f)}" style="max-height:40px;max-width:50px;border-radius:4px">
        <button onclick="removeImage(${i})" style="background:none;border:none;cursor:pointer;color:#d94c4c;font-size:14px;line-height:1">✕</button>
      </span>`
    ).join('');
}

function removeImage(index) {
  pendingImageFile.splice(index, 1);
  _renderImagePreview();
  const inp = document.getElementById('chatImageInput');
  if (inp) inp.value = '';
}

function clearImage() {
  pendingImageFile = [];
  const p = document.getElementById('imgPreview');
  if (p) { p.classList.add('hidden'); p.innerHTML = ''; }
  const inp = document.getElementById('chatImageInput');
  if (inp) inp.value = '';
}

async function sendChatMessage() {
  const pid   = document.getElementById('askPatientSelect')?.value;
  const input = document.getElementById('chatInput');
  const q     = input?.value?.trim();
  if (!pid || (!q && !pendingImageFile.length)) return;

  // Snapshot images and text before clearing anything
  const imageSnapshot = [...pendingImageFile];
  const questionText  = q || '';

  // Clear composer immediately — image moves into the sent bubble
  input.value = '';
  clearImage();

  // Build user message with images inside the bubble
  appendChatMsg('user', questionText, imageSnapshot);

  // Build form with snapshotted images
  const form = new FormData();
  form.append('patient_id', pid);
  form.append('question',   questionText);
  form.append('asked_by',   currentUser.username);
  imageSnapshot.forEach(f => form.append('image', f));

  // Show typing indicator
  appendChatMsg('assistant', '<div class="typing-dots"><span></span><span></span><span></span></div>');

  const res  = await api('/api/ask-ai', 'POST', form, true);
  const box  = document.getElementById('chatMessages');
  const last = box?.lastChild;
  if (last) last.querySelector('.chat-bubble').innerHTML = _renderMarkdown(res.answer || 'Sorry, I could not get a response.');
  box.scrollTop = box.scrollHeight;
}

// ── doctor tools ──────────────────────────────────────────────────────────────
async function populateDoctorTools() {
  const [patients, rooms, logFields] = await Promise.all([
    api("/api/patients"), api("/api/rooms/available"), api("/api/log-fields")
  ]);
  const po = (id, items, vf, lf) => { const el = document.getElementById(id); if (el) el.innerHTML = items.map(i => `<option value="${vf(i)}">${lf(i)}</option>`).join(""); };
  po("taskPatientSelect",       patients || [], p => p.id,     p => `${p.name} (${p.room_no})`);
  po("assessmentPatientSelect", patients || [], p => p.id,     p => `${p.name} (${p.room_no})`);
  po("newAssessRoom",           rooms    || [], r => r.room_no, r => `Room ${r.room_no}`);

  // Populate linked field dropdown from DB log_fields + meal synthetic options
  const lf = document.getElementById("taskLinkedField");
  if (lf) {
    const mealOpts = [
      {field:"meal_breakfast",label:"Meal — Breakfast"},
      {field:"meal_lunch",   label:"Meal — Lunch"},
      {field:"meal_dinner",  label:"Meal — Dinner"},
    ];
    const dbOpts = (logFields || []).map(f => ({field: f.field, label: f.label}));
    const allOpts = [...dbOpts, ...mealOpts];
    lf.innerHTML = `<option value="">— Manual (nurse completes manually) —</option>` +
      allOpts.map(f => `<option value="${f.field}">${f.label} (${f.field})</option>`).join("");
  }

  const tps = document.getElementById("taskPatientSelect");
  if (tps) {
    tps.onchange = async () => {
      const h  = await api(`/api/patients/${tps.value}/handler`);
      const el = document.getElementById("taskAssignedAuto");
      if (el) el.value = h?.label || "Unassigned";
    };
    if (tps.value) tps.onchange();
  }
  loadAssessmentHistory();
}

async function loadAssessmentHistory() {
  const pid = document.getElementById("assessmentPatientSelect")?.value;
  if (!pid) return;
  const [assess, handler] = await Promise.all([api(`/api/patients/${pid}/assessment`), api(`/api/patients/${pid}/handler`)]);
  const hEl = document.getElementById("assessmentCurrentHandler");
  if (hEl) hEl.value = handler?.label || "—";
  const hist = document.getElementById("assessmentHistory");
  if (!hist) return;
  const versions = assess?.versions || [];
  hist.innerHTML = versions.length
    ? versions.slice().reverse().map(v => `<div class="helper-box" style="margin-bottom:8px"><strong>v${v.version}</strong> by ${v.created_by} · ${(v.created_at || "").slice(0, 10)}<br><span class="muted">${v.summary || ""}</span></div>`).join("")
    : `<p class="muted">No assessments yet.</p>`;
}

async function createTask() {
  const btn = document.querySelector("#view-doctor-management .btn-primary");
  showSaving(btn);
  const res = await api("/api/tasks", "POST", {
    patient_id:   document.getElementById("taskPatientSelect")?.value,
    created_by:   currentUser.username,
    title:        document.getElementById("taskTitle")?.value,
    due_time:     document.getElementById("taskDue")?.value,
    instruction:  document.getElementById("taskInstruction")?.value,
    linked_field: document.getElementById("taskLinkedField")?.value || null,
  });
  doneSaving(btn);
  if (res.id) {
    const mode = res.linked_field ? `auto: ${res.linked_field}` : "manual complete";
    showToast(`Task assigned ✓ (${mode})`, "success");
    document.getElementById("taskTitle").value        = "";
    document.getElementById("taskDue").value          = "";
    document.getElementById("taskInstruction").value  = "";
    document.getElementById("taskLinkedField").value  = "";
  } else {
    showToast("Failed to create task", "error");
  }
}

// PDF chip helpers — compact selected-file card with inline remove
function validatePdfInput(input, msgId) {
  const chip = document.getElementById(msgId);
  if (!chip) return;
  if (!input.files[0]) { chip.innerHTML = ''; chip.style.display = 'none'; return; }
  const file  = input.files[0];
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
  if (!isPdf) {
    input.value = '';
    chip.style.display = 'flex';
    chip.style.alignItems = 'center';
    chip.style.gap = '8px';
    chip.style.padding = '8px 12px';
    chip.style.background = '#fef2f2';
    chip.style.border = '1px solid #fca5a5';
    chip.style.borderRadius = '10px';
    chip.style.fontSize = '13px';
    chip.innerHTML = `<span style="color:#d94c4c">⚠ Only PDF files accepted — please choose a .pdf file.</span>`;
  } else {
    const safeN = file.name.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    chip.style.display = 'flex';
    chip.style.alignItems = 'center';
    chip.style.gap = '8px';
    chip.style.padding = '8px 12px';
    chip.style.background = '#f0fdf4';
    chip.style.border = '1px solid #86efac';
    chip.style.borderRadius = '10px';
    chip.style.fontSize = '13px';
    chip.style.marginTop = '6px';
    chip.innerHTML =
      `<span style="font-size:18px">📄</span>` +
      `<span style="flex:1;color:#166534;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${safeN}</span>` +
      `<button onclick="clearPdfInput('${input.id}','${msgId}')" style="background:none;border:none;cursor:pointer;color:#6b7280;font-size:16px;line-height:1;flex-shrink:0" title="Remove file">✕</button>`;
  }
}

function clearPdfInput(inputId, msgId) {
  const inp  = document.getElementById(inputId);
  const chip = document.getElementById(msgId);
  if (inp)  inp.value = '';
  if (chip) { chip.innerHTML = ''; chip.style.display = 'none'; }
}

function _showPdfSavedChip(msgId, fileName) {
  // Show a brief "saved" chip after successful upload, then fade out
  const chip = document.getElementById(msgId);
  if (!chip) return;
  const safeN = (fileName||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  chip.style.display = 'flex';
  chip.style.alignItems = 'center';
  chip.style.gap = '8px';
  chip.style.padding = '8px 12px';
  chip.style.background = '#f0fdf4';
  chip.style.border = '1px solid #86efac';
  chip.style.borderRadius = '10px';
  chip.style.fontSize = '13px';
  chip.style.marginTop = '6px';
  chip.innerHTML =
    `<span style="font-size:16px">✅</span>` +
    `<span style="flex:1;color:#166534;font-weight:500">${safeN} — uploaded successfully</span>`;
  // Auto-clear after 4 seconds
  setTimeout(() => { if (chip) { chip.innerHTML = ''; chip.style.display = 'none'; } }, 4000);
}

async function submitAssessment() {
  const btns = document.querySelectorAll("#view-doctor-management .btn-primary");
  const btn  = btns[btns.length - 1];
  showSaving(btn);
  const pid  = document.getElementById("assessmentPatientSelect")?.value;
  const form = new FormData();
  form.append("patient_id",         pid);
  form.append("created_by",         currentUser.username);
  form.append("symptom_duration",   document.getElementById("assessDuration")?.value    || "");
  form.append("summary",            document.getElementById("assessSummary")?.value     || "");
  form.append("doctor_instruction", document.getElementById("assessInstruction")?.value || "");
  const pdfInput = document.getElementById("assessmentPdf");
  const pdf      = pdfInput?.files[0];
  const pdfName  = pdf?.name || null;
  if (pdf) form.append("pdf_file", pdf);
  const res = await api("/api/initial-assessment", "POST", form, true);
  doneSaving(btn);
  if (res.patient_id || res.id || res.versions) {
    showToast("Assessment saved ✓ — indexing to AI memory…", "success", 5000);
    // Clear all fields so user knows it was submitted
    ["assessDuration","assessSummary","assessInstruction"].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = "";
    });
    // Clear PDF chip and show brief saved confirmation
    clearPdfInput("assessmentPdf", "assessmentPdfMsg");
    if (pdfName) _showPdfSavedChip("assessmentPdfMsg", pdfName);
    loadAssessmentHistory();
  } else {
    showToast("Failed to save assessment", "error");
  }
}

async function submitNewPatientAssessment() {
  const btn  = document.querySelectorAll("#view-doctor-management .btn-primary")[0];
  showSaving(btn);
  const form = new FormData();
  form.append("name",               document.getElementById("newPatientName")?.value    || "");
  form.append("age",                document.getElementById("newPatientAge")?.value     || "0");
  form.append("gender",             document.getElementById("newPatientGender")?.value  || "");
  form.append("created_by",         currentUser.username);
  form.append("symptom_duration",   document.getElementById("newAssessDuration")?.value || "");
  form.append("summary",            document.getElementById("newAssessSummary")?.value  || "");
  form.append("doctor_instruction", document.getElementById("newAssessInstruction")?.value || "");
  form.append("room_no",            document.getElementById("newAssessRoom")?.value     || "");
  const pdfInput = document.getElementById("newAssessmentPdf");
  const pdf      = pdfInput?.files[0];
  const pdfName  = pdf?.name || null;
  if (pdf) form.append("pdf_file", pdf);
  const res = await api("/api/new-patient-assessment", "POST", form, true);
  doneSaving(btn);
  if (res.patient) {
    showToast(`New patient ${res.patient.name} added ✓`, "success");
    // Clear all fields so user knows it was submitted
    ["newPatientName","newPatientAge","newAssessDuration",
     "newAssessSummary","newAssessInstruction","newAssessRoom"].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = "";
    });
    const gSel = document.getElementById("newPatientGender");
    if (gSel) gSel.selectedIndex = 0;
    // Clear PDF chip and show brief saved confirmation
    clearPdfInput("newAssessmentPdf", "newAssessmentPdfMsg");
    if (pdfName) _showPdfSavedChip("newAssessmentPdfMsg", pdfName);
    populateDoctorTools();
  } else {
    showToast("Failed to add patient", "error");
  }
}

// ── doctor docs ───────────────────────────────────────────────────────────────
async function populateDoctorDocs() {
  const patients = await api("/api/patients");
  const opts     = (patients || []).map(p => `<option value="${p.id}">${p.name} (${p.room_no})</option>`).join("");
  const s1 = document.getElementById("docPatientSelect");
  const s2 = document.getElementById("doctorPolicyPatientSelect");
  if (s1) { s1.innerHTML = opts; s1.onchange = loadDocs; loadDocs(); }
  if (s2) { s2.innerHTML = opts; s2.onchange = loadDoctorPolicyList; loadDoctorPolicyList(); }
}

async function loadDocs() {
  const pid = document.getElementById("docPatientSelect")?.value;
  if (!pid) return;
  const [docs, all] = await Promise.all([api(`/api/docs?patient_id=${pid}`), api(`/api/docs?patient_id=${pid}&include_deleted=true`)]);
  const dl = document.getElementById("docList");
  if (dl) dl.innerHTML = (docs || []).length
    ? docs.map(d => `<div class="helper-box" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><span>📄 ${d.name} <small class="muted">${d.kind}</small></span><button class="btn btn-sm btn-danger" onclick="softDeleteDoc('${d.id}')">Delete</button></div>`).join("")
    : `<p class="muted">No documents.</p>`;
  const rl = document.getElementById("recycleList");
  const bin = (all || []).filter(d => d.deleted);
  if (rl) rl.innerHTML = bin.length
    ? bin.map(d => `<div class="helper-box" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><span style="color:#888">📄 ${d.name}</span><div style="display:flex;gap:6px"><button class="btn btn-sm btn-secondary" onclick="restoreDoc('${d.id}')">Restore</button><button class="btn btn-sm btn-danger" onclick="permDeleteDoc('${d.id}')">Delete Forever</button></div></div>`).join("")
    : `<p class="muted">Recycle bin empty.</p>`;
}

async function softDeleteDoc(id) { await api("/api/docs/delete","POST",{doc_id:id}); showToast("Moved to recycle bin","info"); loadDocs(); }
async function restoreDoc(id)    { await api("/api/docs/restore","POST",{doc_id:id}); showToast("Restored ✓","success"); loadDocs(); }
async function permDeleteDoc(id) { if (!confirm("Permanently delete? Removes from AI memory too.")) return; await api("/api/docs/permanent-delete","POST",{doc_id:id}); showToast("Permanently deleted","warning"); loadDocs(); }

async function loadDoctorPolicyList() {
  const pid = document.getElementById("doctorPolicyPatientSelect")?.value;
  if (!pid) return;
  const [policies, requests] = await Promise.all([
    api(`/api/policies?patient_id=${pid}`),
    api("/api/policy-requests"),
  ]);
  const myReqs = (requests || []).filter(r => r.patient_id === pid);
  const c      = document.getElementById("doctorPolicyList");
  if (!c) return;

  // Active policies list
  const polHtml = (policies || []).map(pol => {
    const typeIcon = pol.policy_type === "threshold" ? "📊" : pol.policy_type === "yes_no" ? "✅" : "📋";
    return `<div class="helper-box" style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <span>${typeIcon}</span> <strong>${pol.name}</strong>
          <span class="badge" style="margin-left:6px;background:${pol.active?"#d4edda":"#f8d7da"};color:${pol.active?"#155724":"#721c24"}">${pol.active?"Active":"Off"}</span>
          <div class="muted" style="font-size:12px">${pol.threshold||""}</div>
          <div style="font-size:11px;color:#6b7888">Pre-alert: ${pol.prealert_days||"?"}d · Alert: ${pol.alert_days||"?"}d</div>
        </div>
        ${pol.scope === "patient"
          ? `<button class="btn btn-sm btn-danger" onclick="requestRemovePolicy('${pid}','${pol.id}')">Request Remove</button>`
          : ""}
      </div>
    </div>`;
  }).join("") || `<p class="muted">No policies for this patient.</p>`;

  // My pending requests
  const reqHtml = myReqs.length
    ? `<hr><h3 style="font-size:13px;font-weight:600;margin:8px 0">My Requests</h3>` +
      myReqs.map(r => `<div class="helper-box" style="margin-bottom:6px;font-size:13px">
        ${r.draft_policy?.name || r.policy_id || "Request"} —
        <span class="badge">${r.status}</span>
        ${r.decision_by ? " by " + r.decision_by : ""}
      </div>`).join("")
    : "";

  c.innerHTML = polHtml +
    `<hr style="margin:12px 0">
    <button class="btn btn-primary btn-sm btn-block" onclick="openPolicyTypeDialog('patient','${pid}')">
      + Request New Policy
    </button>` +
    reqHtml;
}


async function requestRemovePolicy(pid, polId) { const res = await api("/api/policy-requests","POST",{patient_id:pid,policy_id:polId,requested_by:currentUser.username}); if(res.id){showToast("Removal request sent ✓","info");loadDoctorPolicyList();} }
async function requestNewPolicy(pid) {
  const name=document.getElementById("reqPolName")?.value?.trim();
  const thr =document.getElementById("reqPolThreshold")?.value?.trim();
  const desc=document.getElementById("reqPolDesc")?.value?.trim();
  if(!name||!thr){showToast("Name and threshold required","error");return;}
  const res=await api("/api/policy-requests/new","POST",{patient_id:pid,requested_by:currentUser.username,name,threshold:thr,description:desc});
  if(res.id){showToast("Policy request sent ✓","info");loadDoctorPolicyList();}
}

// ── chief nurse ────────────────────────────────────────────────────────────────
async function populateChief() {
  const [patients, users, rooms] = await Promise.all([api("/api/patients"), api("/api/users"), api("/api/rooms")]);
  const cps = document.getElementById("chiefPatientSelect");
  if (cps) {
    cps.innerHTML = (patients || []).map(p => `<option value="${p.id}">${p.name} (${p.room_no})</option>`).join("");
    cps.onchange  = showCurrentAssigned;
    showCurrentAssigned();
  }
  // Combined nurse + caretaker dropdown
  const tt      = document.getElementById("chiefTransferTarget");
  const nurses  = (users || []).filter(u => u.role === "nurse"      && u.active);
  const carers  = (users || []).filter(u => u.role === "caretaker"  && u.active);
  if (tt) {
    tt.innerHTML =
      `<optgroup label="── Nurses ──">${nurses.map(u => `<option value="${u.username}|nurse">${u.name}</option>`).join("")}</optgroup>` +
      `<optgroup label="── Caretakers ──">${carers.map(u => `<option value="${u.username}|caretaker">${u.name}</option>`).join("")}</optgroup>`;
  }
  const rg = document.getElementById("chiefRoomGrid");
  if (rg) rg.innerHTML = (rooms || []).map(r => `<div class="room-card ${r.status === "admitted" ? "admitted" : "vacant"}"><strong>Room ${r.room_no}</strong><div>${r.status === "admitted" ? `Patient: ${r.patient_id}` : "Available"}</div></div>`).join("");
}

async function showCurrentAssigned() {
  const pid = document.getElementById("chiefPatientSelect")?.value;
  if (!pid) return;
  const h  = await api(`/api/patients/${pid}/handler`);
  const el = document.getElementById("currentAssignedNurse");
  if (el) el.value = h?.label || "Unassigned";
}

async function transferPatient() {
  const pid = document.getElementById("chiefPatientSelect")?.value;
  const val = document.getElementById("chiefTransferTarget")?.value;
  if (!pid || !val) return;
  const [worker, mode] = val.split("|");
  const res = await api("/api/patients/assign", "POST", { patient_id: pid, worker_username: worker, mode });
  if (res.patient) { showToast(`Transferred to ${worker} ✓`, "success"); populateChief(); }
}

async function dischargePatient() {
  const pid = document.getElementById("chiefPatientSelect")?.value;
  if (!pid || !confirm("Discharge this patient?")) return;
  await api("/api/patients/discharge", "POST", { patient_id: pid, worker_username: "", mode: "discharge" });
  showToast("Patient discharged", "info");
  populateChief();
}

async function openAddRoom() {
  const no = prompt("Enter new room number:");
  if (!no) return;
  const res = await api("/api/rooms", "POST", { room_no: no });
  if (res.id) { showToast(`Room ${no} added ✓`, "success"); populateChief(); }
}

// ── manager ───────────────────────────────────────────────────────────────────
// ── Care Log Fields (Manager) ─────────────────────────────────────────────────

async function loadLogFields() {
  const fields = await getLogFields();
  const list   = document.getElementById("logFieldsList");
  if (!list) return;
  const builtIn = ["fluid_intake_ml","food_intake","blood_pressure","oxygen_level",
                   "sugar_level","sleep_hours","confusion","notes","meal_type"];
  const all = (fields || []);
  if (!all.length) {
    list.innerHTML = `<p class="muted">No custom fields yet. Add one from the form.</p>`;
    return;
  }
  list.innerHTML = all.map(f => {
    const isBuiltIn = builtIn.includes(f.field);
    return `<div class="helper-box" style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="display:flex;align-items:center;gap:6px">
            <strong>${f.label}</strong>
            <span class="badge" style="font-size:10px;background:${f.type==='threshold'?'#e8f0ff':'#e8fff3'};color:${f.type==='threshold'?'#2d5be3':'#0b8a69'}">${f.type}</span>
            ${isBuiltIn ? `<span class="badge" style="font-size:10px">built-in</span>` : `<span class="badge" style="font-size:10px;background:#fff3e0;color:#e65100">custom</span>`}
          </div>
          <div class="muted" style="font-size:12px">key: <code>${f.field}</code>${f.unit ? ` · unit: ${f.unit}` : ""}</div>
          ${f.description ? `<div class="muted" style="font-size:11px;margin-top:2px">${f.description}</div>` : ""}
        </div>
      </div>
    </div>`;
  }).join("");
}

async function addLogField() {
  const key   = document.getElementById("lfKey")?.value?.trim().replace(/\s+/g,"_").toLowerCase();
  const label = document.getElementById("lfLabel")?.value?.trim();
  const type  = document.getElementById("lfType")?.value;
  const unit  = document.getElementById("lfUnit")?.value?.trim() || null;
  const desc  = document.getElementById("lfDesc")?.value?.trim() || "";
  const msg   = document.getElementById("lfMsg");

  if (!key || !label) {
    if (msg) { msg.style.color="#d94c4c"; msg.textContent="Field key and label are required."; }
    return;
  }
  if (!/^[a-z][a-z0-9_]*$/.test(key)) {
    if (msg) { msg.style.color="#d94c4c"; msg.textContent="Key must be lowercase letters/numbers/underscore, starting with a letter."; }
    return;
  }
  const res = await api("/api/log-fields", "POST", { field: key, label, type, unit, description: desc });
  if (res.error) {
    if (msg) { msg.style.color="#d94c4c"; msg.textContent=res.error; }
    return;
  }
  if (msg) { msg.style.color="#0b8a69"; msg.textContent=`✓ Field "${label}" added — appears in care log form and policy dropdown.`; }
  // Clear form
  ["lfKey","lfLabel","lfUnit","lfDesc"].forEach(id => { const el=document.getElementById(id); if(el) el.value=""; });
  // Invalidate cache so care log form and policy dropdown refresh
  _logFieldsCache = null;
  loadLogFields();
}

async function renderManager() {
  const [policies, incidents] = await Promise.all([api("/api/policies"), api("/api/incidents/patients")]);
  const pl = document.getElementById("managerPolicyList");
  if (pl) {
    const orgPols = (policies || []).filter(p => p.scope === "organization");
    pl.innerHTML = orgPols.map(pol => {
      const typeIcon  = pol.policy_type === "threshold" ? "📊" : pol.policy_type === "yes_no" ? "✅" : "📋";
      const fieldInfo = pol.log_field ? ` · Field: ${pol.log_field}` : "";
      const valInfo   = pol.check_value != null ? ` · Value: ${pol.check_value}` : "";
      return `<div class="helper-box" style="margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
          <div style="flex:1">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
              <span>${typeIcon}</span>
              <strong>${pol.name}</strong>
            </div>
            <div class="muted" style="font-size:12px">${pol.threshold||""}${fieldInfo}${valInfo}</div>
            <div class="muted" style="font-size:11px;margin-top:2px">Pre-alert: ${pol.prealert_days||"?"}d · Alert: ${pol.alert_days||"?"}d${pol.tie_rule?" · Tie: "+pol.tie_rule:""}</div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end">
            <div class="toggle-wrap">
              <label class="toggle-switch">
                <input type="checkbox" ${pol.active ? "checked" : ""} onchange="togglePol('${pol.id}',this)">
                <span class="toggle-slider"></span>
              </label>
              <span class="toggle-label ${pol.active ? "on" : "off"}" id="toggleLabel_${pol.id}">${pol.active ? "ON" : "OFF"}</span>
            </div>
            <button class="btn btn-sm btn-secondary" onclick="editPolicy('${pol.id}')">Edit</button>
            <button class="btn btn-sm btn-danger" onclick="deletePol('${pol.id}')">Delete</button>
          </div>
        </div>
      </div>`;
    }).join("") || `<p class="muted">No policies.</p>`;
  }
  const il = document.getElementById("managerIncidentList");
  if (il) il.innerHTML = (incidents || []).length
    ? incidents.map(p => `<div class="patient-card" style="cursor:pointer" onclick="openPatientTimeline('${p.id}','${encodeURIComponent(p.name)}')">
        <div class="patient-top"><div><strong>${p.name}</strong><div class="patient-meta">${p.age}y · ${p.gender} · Room ${p.room_no}</div></div><span class="badge">${p.diagnosis}</span></div>
        <button class="btn btn-sm btn-secondary" style="margin-top:8px">📋 View Timeline</button>
      </div>`).join("")
    : `<p class="empty-state">No patients.</p>`;
}

async function togglePol(polId, checkbox) {
  const res = await api(`/api/policies/${polId}/toggle?toggled_by=${currentUser.username}`, "POST");
  if (!res.id) { checkbox.checked = !checkbox.checked; return; }
  const label = document.getElementById(`toggleLabel_${polId}`);
  if (label) { label.textContent = res.active ? "ON" : "OFF"; label.className = `toggle-label ${res.active ? "on" : "off"}`; }
  showToast(`Policy '${res.name}' is now ${res.active ? "ON ✓" : "OFF ✗"}`, res.active ? "success" : "warning", 5000);
  if (res.active && res.retroactive_scan) {
    const r = res.retroactive_scan;
    if ((r.created_alerts?.length || 0) + (r.created_prealerts?.length || 0) > 0)
      showToast(`Retroactive scan: ${r.created_alerts?.length || 0} alert(s), ${r.created_prealerts?.length || 0} pre-alert(s) generated`, "alert", 8000);
  }
}

async function deletePol(polId) {
  if (!confirm("Delete this policy permanently?")) return;
  const res = await api(`/api/policies/${polId}/delete`, "POST");
  if (res.id) { showToast(`Policy '${res.name}' deleted`, "warning"); renderManager(); }
}

// ── Policy type selector ─────────────────────────────────────────────────────
let _logFieldsCache = null;

async function getLogFields() {
  if (!_logFieldsCache) {
    _logFieldsCache = await api("/api/log-fields");
  }
  return _logFieldsCache || [];
}

function toggleCutoffTime(mode) {
  const row = document.getElementById("cutoffTimeRow");
  if (row) row.style.display = mode === "end_of_day_cumulative" ? "flex" : "none";
}

function openPolicyTypeDialog(scope, patientId) {
  // scope = 'organization' or 'patient'
  document.getElementById("simpleModalBody").innerHTML = `
    <h3 style="font-size:15px;font-weight:600;margin-bottom:16px">
      ${scope === "organization" ? "Add Organisation Policy" : "Request New Patient Policy"}
    </h3>
    <p style="font-size:13px;color:#6b7888;margin-bottom:16px">Choose the policy type:</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div onclick="openPolicyForm('threshold','${scope}','${patientId||''}')"
           style="border:2px solid #2d7ff9;border-radius:14px;padding:20px;cursor:pointer;text-align:center;transition:background .15s"
           onmouseover="this.style.background='#eff6ff'" onmouseout="this.style.background='#fff'">
        <div style="font-size:28px;margin-bottom:8px">📊</div>
        <div style="font-weight:600;font-size:14px;color:#2d7ff9">Threshold</div>
        <div style="font-size:12px;color:#6b7888;margin-top:4px">Numeric value check<br>e.g. Fluid below 1000ml</div>
      </div>
      <div onclick="openPolicyForm('yes_no','${scope}','${patientId||''}')"
           style="border:2px solid #0b8a69;border-radius:14px;padding:20px;cursor:pointer;text-align:center;transition:background .15s"
           onmouseover="this.style.background='#f0fdf4'" onmouseout="this.style.background='#fff'">
        <div style="font-size:28px;margin-bottom:8px">✅</div>
        <div style="font-weight:600;font-size:14px;color:#0b8a69">Yes / No</div>
        <div style="font-size:12px;color:#6b7888;margin-top:4px">Observation check<br>e.g. Confusion noted</div>
      </div>
    </div>`;
  document.getElementById("simpleModal").classList.remove("hidden");
}

// Alias for manager button onclick
function openPolicyModal() { openPolicyTypeDialog("organization", null); }

async function openPolicyForm(policyType, scope, patientId, existingPolicy) {
  const fields    = await getLogFields();
  const typeFields= fields.filter(f => f.type === policyType);
  const isEdit    = !!existingPolicy;
  const ep        = existingPolicy || {};
  const isRequest = scope === "patient" && !isEdit;

  const fieldOpts = typeFields.map(f =>
    `<option value="${f.field}" ${ep.log_field === f.field ? "selected" : ""}>${f.label}${f.unit ? " ("+f.unit+")" : ""}</option>`
  ).join("");

  let formHtml = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
      <button onclick="openPolicyTypeDialog('${scope}','${patientId}')"
        style="background:none;border:none;cursor:pointer;color:#2d7ff9;font-size:13px">← Back</button>
      <h3 style="font-size:15px;font-weight:600">${isEdit ? "Edit" : "Add"} ${policyType === "threshold" ? "📊 Threshold" : "✅ Yes/No"} Policy</h3>
    </div>
    <div class="form-group"><label>Policy Name</label>
      <input id="mPolName" placeholder="e.g. Hydration SOP" value="${ep.name||''}"></div>
    <div class="form-group"><label>${policyType === "threshold" ? "Measure Field" : "Observe Field"}</label>
      <select id="mPolField">${fieldOpts}</select>
    </div>`;

  if (policyType === "threshold") {
    formHtml += `
    <div class="grid-2">
      <div class="form-group"><label>Threshold Value</label>
        <input id="mPolValue" type="number" step="0.1" placeholder="e.g. 1000" value="${ep.check_value||''}"></div>
      <div class="form-group"><label>Direction</label>
        <select id="mPolDir">
          <option value="below" ${(ep.direction||'below')==='below'?'selected':''}>Below threshold = bad</option>
          <option value="above" ${ep.direction==='above'?'selected':''}>Above threshold = bad</option>
        </select>
      </div>
    </div>
    <div class="form-group"><label>Evaluation Mode</label>
      <select id="mPolEvalMode" onchange="toggleCutoffTime(this.value)">
        <option value="instant"               ${(ep.evaluation_mode||'instant')==='instant'?'selected':''}>Instant — check on every log save</option>
        <option value="end_of_day_cumulative" ${ep.evaluation_mode==='end_of_day_cumulative'?'selected':''}>Cumulative at day end — sum all logs then check</option>
      </select>
    </div>
    <div class="form-group" id="cutoffTimeRow" style="display:${ep.evaluation_mode==='end_of_day_cumulative'?'flex':'none'};flex-direction:column;gap:7px">
      <label>Cutoff Time (24hr) — evaluate after this time each day</label>
      <input id="mPolCutoff" type="time" value="${ep.cutoff_time||'20:00'}">
    </div>`;
  } else {
    formHtml += `
    <div class="form-group"><label>When votes are equal (tie)</label>
      <select id="mPolTie">
        <option value="breach"    ${(ep.tie_rule||'breach')==='breach'?'selected':''}>Count as breach (strict)</option>
        <option value="no_breach" ${ep.tie_rule==='no_breach'?'selected':''}>Do not count (lenient)</option>
      </select>
    </div>
    <div class="form-group"><label>Evaluation Mode</label>
      <select id="mPolEvalMode" onchange="toggleCutoffTime(this.value)">
        <option value="instant"               ${(ep.evaluation_mode||'instant')==='instant'?'selected':''}>Instant — check on every log save</option>
        <option value="end_of_day_cumulative" ${ep.evaluation_mode==='end_of_day_cumulative'?'selected':''}>Cumulative at day end — majority vote after cutoff</option>
      </select>
    </div>
    <div class="form-group" id="cutoffTimeRow" style="display:${ep.evaluation_mode==='end_of_day_cumulative'?'flex':'none'};flex-direction:column;gap:7px">
      <label>Cutoff Time (24hr) — evaluate after this time each day</label>
      <input id="mPolCutoff" type="time" value="${ep.cutoff_time||'20:00'}">
    </div>`;
  }

  formHtml += `
    <div class="grid-2">
      <div class="form-group"><label>Pre-Alert after (days)</label>
        <input id="mPolPre" type="number" min="1" value="${ep.prealert_days||1}"></div>
      <div class="form-group"><label>Full Alert after (days)</label>
        <input id="mPolAlert" type="number" min="1" value="${ep.alert_days||3}"></div>
    </div>
    <div class="form-group"><label>Description</label>
      <textarea id="mPolDesc">${ep.description||''}</textarea></div>`;

  if (isEdit) {
    formHtml += `<button class="btn btn-primary btn-block" onclick="saveEditPolicy('${ep.id}','${policyType}')">Save Changes</button>`;
  } else if (isRequest) {
    formHtml += `<button class="btn btn-primary btn-block" onclick="submitPolicyRequest('${patientId}','${policyType}')">Send Request to Manager</button>`;
  } else {
    formHtml += `<button class="btn btn-primary btn-block" onclick="submitNewPolicy('${policyType}','${scope}','${patientId||''}')">Add Policy</button>`;
  }

  document.getElementById("simpleModalBody").innerHTML = formHtml;
  document.getElementById("simpleModal").classList.remove("hidden");
}

async function submitNewPolicy(policyType, scope, patientId) {
  const name   = document.getElementById("mPolName")?.value?.trim();
  const field  = document.getElementById("mPolField")?.value;
  const preD   = parseInt(document.getElementById("mPolPre")?.value)   || 2;
  const alrtD  = parseInt(document.getElementById("mPolAlert")?.value) || 3;
  const desc   = document.getElementById("mPolDesc")?.value?.trim()    || "";

  if (!name || !field) { showToast("Name and field required", "error"); return; }
  if (preD >= alrtD)   { showToast("Alert days must be more than pre-alert days", "error"); return; }

  const payload = {
    name, policy_type: policyType, log_field: field, scope,
    patient_id: patientId || null,
    alert_days: alrtD, prealert_days: preD, description: desc,
  };

  if (policyType === "threshold") {
    const val      = parseFloat(document.getElementById("mPolValue")?.value);
    const dir      = document.getElementById("mPolDir")?.value || "below";
    const evalMode = document.getElementById("mPolEvalMode")?.value || "instant";
    const cutoff   = document.getElementById("mPolCutoff")?.value || null;
    if (isNaN(val)) { showToast("Threshold value required", "error"); return; }
    const fields = await getLogFields();
    payload.check_value     = val;
    payload.direction       = dir;
    payload.evaluation_mode = evalMode;
    payload.cutoff_time     = evalMode === "end_of_day_cumulative" ? cutoff : null;
    payload.threshold       = dir === "below" ? `Below ${val} ${fields.find(f=>f.field===field)?.unit||""}` : `Above ${val} ${fields.find(f=>f.field===field)?.unit||""}`;

  } else {
    const evalMode = document.getElementById("mPolEvalMode")?.value || "instant";
    const cutoff   = document.getElementById("mPolCutoff")?.value  || null;
    payload.tie_rule        = document.getElementById("mPolTie")?.value || "breach";
    payload.threshold       = `${alrtD} consecutive days`;
    payload.evaluation_mode = evalMode;
    payload.cutoff_time     = evalMode === "end_of_day_cumulative" ? cutoff : null;
  }

  const res = await api("/api/policies", "POST", payload);
  if (res.id) {
    _logFieldsCache = null; // reset cache
    showToast(`Policy '${name}' added ✓ — active immediately`, "success");
    closeModal("simpleModal");
    renderManager();
  } else {
    showToast("Failed to add policy", "error");
  }
}

async function saveEditPolicy(policyId, policyType) {
  const name  = document.getElementById("mPolName")?.value?.trim();
  const preD  = parseInt(document.getElementById("mPolPre")?.value)   || 2;
  const alrtD = parseInt(document.getElementById("mPolAlert")?.value) || 3;
  const desc  = document.getElementById("mPolDesc")?.value?.trim()    || "";

  if (!name) { showToast("Name required", "error"); return; }
  if (preD >= alrtD) { showToast("Alert days must be more than pre-alert days", "error"); return; }

  const payload = { name, alert_days: alrtD, prealert_days: preD, description: desc };

  if (policyType === "threshold") {
    const val      = parseFloat(document.getElementById("mPolValue")?.value);
    const dir      = document.getElementById("mPolDir")?.value || "below";
    const evalMode = document.getElementById("mPolEvalMode")?.value || "instant";
    const cutoff   = document.getElementById("mPolCutoff")?.value || null;
    if (!isNaN(val)) {
      payload.check_value     = val;
      payload.direction       = dir;
      payload.evaluation_mode = evalMode;
      payload.cutoff_time     = evalMode === "end_of_day_cumulative" ? cutoff : null;
    }
  } else {
    const evalMode = document.getElementById("mPolEvalMode")?.value || "instant";
    const cutoff   = document.getElementById("mPolCutoff")?.value  || null;
    payload.tie_rule        = document.getElementById("mPolTie")?.value || "breach";
    payload.evaluation_mode = evalMode;
    payload.cutoff_time     = evalMode === "end_of_day_cumulative" ? cutoff : null;
  }

  const res = await api(`/api/policies/${policyId}/update`, "POST", payload);
  if (res.id) {
    showToast(`Policy '${res.name}' updated ✓ — takes effect on next log save`, "success");
    closeModal("simpleModal");
    renderManager();
  } else {
    showToast("Failed to update policy", "error");
  }
}

async function editPolicy(policyId) {
  // Fetch current policy data then open edit form
  const policies = await api("/api/policies");
  const pol      = (policies || []).find(p => p.id === policyId);
  if (!pol) { showToast("Policy not found", "error"); return; }
  openPolicyForm(pol.policy_type || "threshold", pol.scope, pol.patient_id, pol);
}

async function submitPolicyRequest(patientId, policyType) {
  const name   = document.getElementById("mPolName")?.value?.trim();
  const field  = document.getElementById("mPolField")?.value;
  const preD   = parseInt(document.getElementById("mPolPre")?.value)   || 1;
  const alrtD  = parseInt(document.getElementById("mPolAlert")?.value) || 2;
  const desc   = document.getElementById("mPolDesc")?.value?.trim()    || "";

  if (!name || !field) { showToast("Name and field required", "error"); return; }
  if (preD >= alrtD)   { showToast("Alert days must be more than pre-alert days", "error"); return; }

  const payload = {
    patient_id: patientId, requested_by: currentUser.username,
    name, threshold: `${alrtD} days`, description: desc,
    policy_type: policyType, log_field: field,
    alert_days: alrtD, prealert_days: preD,
  };

  if (policyType === "threshold") {
    const val      = parseFloat(document.getElementById("mPolValue")?.value);
    const dir      = document.getElementById("mPolDir")?.value      || "below";
    const evalMode = document.getElementById("mPolEvalMode")?.value || "instant";
    const cutoff   = document.getElementById("mPolCutoff")?.value   || null;
    if (!isNaN(val)) {
      payload.check_value     = val;
      payload.direction       = dir;
      payload.evaluation_mode = evalMode;
      payload.cutoff_time     = evalMode === "end_of_day_cumulative" ? cutoff : null;
    }
  } else {
    const evalMode = document.getElementById("mPolEvalMode")?.value || "instant";
    const cutoff   = document.getElementById("mPolCutoff")?.value   || null;
    payload.tie_rule        = document.getElementById("mPolTie")?.value || "breach";
    payload.evaluation_mode = evalMode;
    payload.cutoff_time     = evalMode === "end_of_day_cumulative" ? cutoff : null;
  }

  const res = await api("/api/policy-requests/new", "POST", payload);
  if (res.id) {
    showToast("Policy request sent to Manager ✓", "info");
    closeModal("simpleModal");
    loadDoctorPolicyList();
  } else {
    showToast("Failed to send request", "error");
  }
}

// ── policies view ─────────────────────────────────────────────────────────────
async function renderPoliciesView() {
  const [patients, requests] = await Promise.all([api("/api/patients"), api("/api/policy-requests")]);
  const sel = document.getElementById("managerPatientPolicySelect");
  if (sel) { sel.innerHTML = (patients || []).map(p => `<option value="${p.id}">${p.name}</option>`).join(""); sel.onchange = loadManagerAllPoliciesForPatient; loadManagerAllPoliciesForPatient(); }
  const rl  = document.getElementById("policyRequestList");
  if (rl) {
    const pending = (requests || []).filter(r => r.status === "requested");
    rl.innerHTML  = pending.length
      ? pending.map(r => `<div class="helper-box" style="margin-bottom:10px">
          <div><strong>${r.request_type === "create" ? "New Policy" : "Remove Policy"}</strong><span class="muted"> by ${r.requested_by}</span></div>
          ${r.draft_policy ? `<div class="muted" style="font-size:12px">${r.draft_policy.name} — ${r.draft_policy.threshold}</div>` : `<div class="muted" style="font-size:12px">Policy: ${r.policy_id}</div>`}
          <div style="display:flex;gap:8px;margin-top:8px">
            <button class="btn btn-sm btn-active" onclick="decidePol('${r.id}','approved')">Approve</button>
            <button class="btn btn-sm btn-danger" onclick="decidePol('${r.id}','denied')">Deny</button>
          </div>
        </div>`).join("")
      : `<p class="muted">No pending requests.</p>`;
  }
}

async function loadManagerAllPoliciesForPatient() {
  const pid = document.getElementById("managerPatientPolicySelect")?.value;
  if (!pid) return;
  const policies = await api(`/api/policies?patient_id=${pid}`);
  const c        = document.getElementById("managerPatientPolicyList");
  if (!c) return;
  c.innerHTML = (policies || []).map(pol => `
    <div class="helper-box" style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap">
        <div style="flex:1">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
            <strong>${pol.name}</strong>
            <span class="badge" style="font-size:10px">${pol.scope}</span>
            <span class="badge" style="font-size:10px;background:${pol.policy_type==='threshold'?'#e8f0ff':'#e8fff3'};color:${pol.policy_type==='threshold'?'#2d5be3':'#0b8a69'}">${pol.policy_type}</span>
          </div>
          <div class="muted" style="font-size:12px;margin-top:2px">${pol.threshold || ''}</div>
          <div class="muted" style="font-size:11px;margin-top:1px">Pre-alert: ${pol.prealert_days}d · Alert: ${pol.alert_days}d${pol.evaluation_mode==='end_of_day_cumulative'?' · Cumulative ⏱'+pol.cutoff_time:''}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <div class="toggle-wrap">
            <label class="toggle-switch">
              <input type="checkbox" ${pol.active ? "checked" : ""} onchange="togglePol('${pol.id}',this)">
              <span class="toggle-slider"></span>
            </label>
            <span class="toggle-label ${pol.active ? "on" : "off"}">${pol.active ? "ON" : "OFF"}</span>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="editPolicy('${pol.id}')">✏ Edit</button>
          <button class="btn btn-sm btn-danger"    onclick="deletePol('${pol.id}')">🗑 Delete</button>
        </div>
      </div>
    </div>`).join("") || `<p class="muted">No policies for this patient.</p>`;
}

async function decidePol(reqId, decision) {
  const res = await api("/api/policy-requests/decision", "POST", { request_id: reqId, decision_by: currentUser.username, decision });
  if (res.id) { showToast(`Request ${decision === "approved" ? "approved ✓" : "denied"}`, decision === "approved" ? "success" : "warning"); renderPoliciesView(); }
}

// ── timeline (UC3) ────────────────────────────────────────────────────────────
function _isoDate(d) {
  // Returns YYYY-MM-DD string for a Date object
  return d.toISOString().slice(0, 10);
}

function openPatientTimeline(patientId, encodedName) {
  _timelinePatientId   = patientId;
  _timelinePatientName = decodeURIComponent(encodedName);
  api(`/api/incidents/date-range/${patientId}`).then(range => {
    const today        = new Date();
    const threeDaysAgo = new Date(today); threeDaysAgo.setDate(today.getDate() - 2);

    // dataMin from DB, dataMax always TODAY so today logs are always included
    const dataMin    = range.min_date || _isoDate(threeDaysAgo);
    const dataMax    = _isoDate(today);

    // defaultFrom = 3 days ago, clamped to earliest available data
    const defaultFrom = _isoDate(threeDaysAgo) < dataMin ? dataMin : _isoDate(threeDaysAgo);
    const defaultTo   = dataMax;

    document.getElementById("simpleModalBody").innerHTML = `
      <h3 style="font-size:15px;font-weight:600;margin-bottom:4px">📋 Timeline Report</h3>
      <p style="font-size:13px;color:#6b7888;margin-bottom:10px"><strong>${_timelinePatientName}</strong></p>
      <div style="background:#f4f7ff;border-radius:10px;padding:10px;margin-bottom:14px;font-size:13px">
        📅 Showing last 3 days by default — earliest data from <strong>${dataMin}</strong>
      </div>
      <div class="grid-2" style="margin-bottom:14px">
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;font-weight:600;color:#4b5562">From Date</label>
          <input type="date" id="tlFromDate" value="${defaultFrom}" min="${dataMin}" max="${dataMax}">
        </div>
        <div class="form-group" style="margin:0">
          <label style="font-size:12px;font-weight:600;color:#4b5562">To Date</label>
          <input type="date" id="tlToDate" value="${defaultTo}" min="${dataMin}" max="${dataMax}">
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-primary" onclick="generateTimeline()">🔍 Generate Timeline</button>
        <button class="btn btn-secondary" onclick="downloadTimelinePDF()">⬇ Download PDF</button>
      </div>
      <div id="timelineResult" style="max-height:440px;overflow-y:auto">
        <p style="text-align:center;padding:20px;color:#6b7888">Loading…</p>
      </div>`;
    document.getElementById("simpleModal").classList.remove("hidden");
    // Always auto-generate regardless of has_data — setTimeout lets DOM paint first
    setTimeout(() => generateTimeline(), 50);
  });
}

async function generateTimeline() {
  const from = document.getElementById("tlFromDate")?.value || "";
  const to   = document.getElementById("tlToDate")?.value   || "";
  const pid  = _timelinePatientId;
  if (!pid) return;
  const result = document.getElementById("timelineResult");
  if (!result) return;
  result.innerHTML = `<p style="text-align:center;padding:20px;color:#6b7888">⏳ Loading events…</p>`;
  const p = [];
  if (from) p.push(`from_date=${encodeURIComponent(from)}`);
  if (to)   p.push(`to_date=${encodeURIComponent(to)}`);
  const url = `/api/incidents/timeline/${pid}` + (p.length ? "?" + p.join("&") : "");
  const res    = await api(url);
  const events = res.events || [];
  _timelineTotal = res.total || events.length;

  if (!events.length) {
    result.innerHTML = `
      <div style="text-align:center;padding:30px;color:#6b7888">
        <div style="font-size:32px;margin-bottom:10px">📭</div>
        <div style="font-weight:600;margin-bottom:4px">No events found</div>
        <div style="font-size:12px">Try widening the date range — data exists outside the selected window</div>
      </div>`;
    return;
  }

  const TYPE = {
    care_log:    {icon:"📋",label:"Care Log",   color:"#2d7ff9",bg:"#eff6ff"},
    alert:       {icon:"🚨",label:"Alert",       color:"#d94c4c",bg:"#fef2f2"},
    pre_alert:   {icon:"⚠️", label:"Pre-Alert",  color:"#f59e0b",bg:"#fffbeb"},
    task:        {icon:"✅",label:"Task",        color:"#0b8a69",bg:"#f0fdf4"},
    assessment:  {icon:"🩺",label:"Assessment", color:"#7c3aed",bg:"#f5f3ff"},
    incident:    {icon:"🟠",label:"Incident",   color:"#b45309",bg:"#fef3c7"},
    notification:{icon:"🔔",label:"Notification",color:"#6b7280",bg:"#f9fafb"},
  };

  // Build legend from types present
  const typesPresent = [...new Set(events.map(e => e.type))];
  const legend = typesPresent.map(t => {
    const cfg = TYPE[t] || TYPE.notification;
    return `<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;
      background:${cfg.bg};color:${cfg.color};border:1px solid ${cfg.color}40;
      border-radius:999px;padding:3px 10px">${cfg.icon} ${cfg.label}</span>`;
  }).join("");

  result.innerHTML =
    `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #e5e7eb">
       ${legend}
     </div>
     <div style="font-size:12px;color:#6b7888;margin-bottom:10px">
       Showing <strong>${events.length}</strong> events
       ${from || to ? `from <strong>${from||"start"}</strong> to <strong>${to||"today"}</strong>` : ""}
       (${_timelineTotal} total for patient)
     </div>` +
    events.map(ev => {
      const cfg  = TYPE[ev.type] || TYPE.notification;
      const time = ev.time ? ev.time.replace("T"," ").slice(0,16) : "—";
      return `
        <div style="border-radius:10px;border:1px solid ${cfg.color}28;background:${cfg.bg};
          padding:12px 14px;border-left:4px solid ${cfg.color};margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap;margin-bottom:4px">
            <div style="display:flex;gap:6px;align-items:center">
              <span style="font-size:15px">${cfg.icon}</span>
              <span style="font-weight:700;font-size:13px;color:${cfg.color}">${ev.label}</span>
            </div>
            <span style="font-size:11px;color:#6b7888;background:#fff;padding:2px 8px;border-radius:6px;border:1px solid #e5e7eb">⏱ ${time}</span>
          </div>
          <div style="font-size:13px;color:#1a2333;line-height:1.5">${ev.text || ""}</div>
          ${ev.detail ? `<div style="font-size:11px;color:#6b7888;margin-top:5px;padding-top:5px;border-top:1px solid ${cfg.color}20;line-height:1.5">${ev.detail}</div>` : ""}
        </div>`;
    }).join("");
}

async function downloadTimelinePDF() {
  const from = document.getElementById("tlFromDate")?.value || "";
  const to   = document.getElementById("tlToDate")?.value   || "";
  const pid  = _timelinePatientId;
  if (!pid) return;
  showToast("Generating PDF…", "info", 3000);
  const p = [];
  if (from) p.push(`from_date=${from}`);
  if (to)   p.push(`to_date=${to}`);
  const url = `/api/incidents/export/${pid}` + (p.length ? "?" + p.join("&") : "");
  try {
    const resp = await fetch(API + url);
    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      showToast("PDF failed: " + (txt.slice(0,80) || resp.status), "error", 6000);
      return;
    }
    const blob     = await resp.blob();
    const blobUrl  = URL.createObjectURL(blob);
    const a        = document.createElement("a");
    a.href         = blobUrl;
    a.download     = `timeline_${(_timelinePatientName||"patient").replace(/\s+/g,"_")}_${from||"all"}_${to||"dates"}.pdf`;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(blobUrl); }, 1000);
    showToast("PDF downloaded ✓", "success");
  } catch (e) {
    showToast("Download error: " + e.message, "error");
  }
}

// ── admin impersonation ───────────────────────────────────────────────────────
async function renderAdmin() {
  const users = await api("/api/users");
  const list  = document.getElementById("adminUserList");
  if (list) {
    list.innerHTML = (users || []).map(u => `
      <div class="helper-box worker-card-clickable" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div>
          <strong>${u.name}</strong> <span class="badge">${u.role}</span>
          <span class="badge" style="background:${u.active?"#d4edda":"#f8d7da"};color:${u.active?"#155724":"#721c24"}">${u.active?"Active":"Inactive"}</span>
          <div class="muted" style="font-size:12px">@${u.username}</div>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="impersonateUser('${u.username}')">👁 View as</button>
      </div>`).join("");
  }
  const opts = (users || []).filter(u => u.active).map(u => `<option value="${u.username}">${u.name} (${u.role})</option>`).join("");
  const ds   = document.getElementById("deleteWorkerSelect");
  const ts   = document.getElementById("transferWorkerSelect");
  if (ds) ds.innerHTML = opts;
  if (ts) ts.innerHTML = opts;
}

async function impersonateUser(username) {
  const profile = await api(`/api/users/${username}/profile`);
  if (!profile?.username) { showToast("Could not load user profile", "error"); return; }
  _adminUser   = currentUser;
  currentUser  = profile;
  const banner = document.getElementById("impersonationBanner");
  const label  = document.getElementById("impersonationLabel");
  if (banner) { banner.classList.remove("hidden"); document.querySelector(".main-area").style.paddingTop = "62px"; }
  if (label)  label.textContent = `👁 Viewing as ${profile.name} (${profile.role})`;
  stopSSE();
  buildNav();
  startSSE();
  showToast(`Now viewing as ${profile.name}`, "info", 4000);
}

function endImpersonation(silent = false) {
  if (!_adminUser) return;
  currentUser = _adminUser;
  _adminUser  = null;
  const banner = document.getElementById("impersonationBanner");
  if (banner) { banner.classList.add("hidden"); document.querySelector(".main-area").style.paddingTop = ""; }
  stopSSE();
  buildNav();
  startSSE();
  if (!silent) showToast("Back to Admin view", "info");
}

async function createWorker() {
  const name = document.getElementById("newWorkerName")?.value?.trim();
  const age  = parseInt(document.getElementById("newWorkerAge")?.value)  || 25;
  const role = document.getElementById("newWorkerRole")?.value;
  const pass = document.getElementById("newWorkerPassword")?.value?.trim();
  if (!name || !pass) { showToast("Name and password required", "error"); return; }
  const res = await api("/api/users", "POST", { name, age, password: pass, role });
  if (res.id) { showToast(`Worker ${name} created ✓`, "success"); renderAdmin(); }
}

async function inactiveWorker() {
  const del  = document.getElementById("deleteWorkerSelect")?.value;
  const tran = document.getElementById("transferWorkerSelect")?.value;
  if (!del) return;
  if (!confirm(`Set ${del} inactive and transfer patients to ${tran}?`)) return;
  const res = await api("/api/users/inactive", "POST", { username: del, transfer_to: tran });
  if (res.username) { showToast(`${del} set inactive ✓`, "info"); renderAdmin(); }
}

// ── modal ─────────────────────────────────────────────────────────────────────
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("hidden");
  const body = document.getElementById("simpleModalBody");
  if (body) body.innerHTML = "";
}
