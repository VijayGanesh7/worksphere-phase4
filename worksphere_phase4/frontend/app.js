/* WorkSphere HRMS - Phase 4 frontend (vanilla JS, no build step).
   All dynamic text is inserted with textContent/createTextNode, never innerHTML, to prevent XSS. */
"use strict";

const state = { token: sessionStorage.getItem("ws_token"), user: JSON.parse(sessionStorage.getItem("ws_user") || "null") };
const view = document.getElementById("view");
const isStaff = () => state.user && (state.user.role === "HR" || state.user.role === "ADMIN");
const today = () => new Date().toISOString().slice(0, 10);

// ---------- helpers ----------
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const fmtDate = (d) => (d ? new Date(d + "T00:00:00").toLocaleDateString() : "");
const fmtDateTime = (s) => new Date(/Z|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z").toLocaleString();
const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); };

let toastTimer;
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3500);
}

async function api(path, { method = "GET", body, blob } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = "Bearer " + state.token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch("/api" + path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  if (res.status === 401 && state.token) { logout(); throw new Error("Session expired. Please sign in again."); }
  if (!res.ok) {
    let msg = "Request failed (" + res.status + ")";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail)) msg = data.detail.map((e) => (e.loc || []).slice(1).join(".") + ": " + e.msg).join("; ");
    } catch (_) { /* keep default */ }
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return blob ? { blob: await res.blob(), res } : res.json();
}

async function download(path, fallbackName) {
  try {
    const { blob, res } = await api(path, { blob: true });
    const m = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "");
    const a = h("a", { href: URL.createObjectURL(blob), download: m ? m[1] : fallbackName });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  } catch (e) { toast(e.message); }
}

const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message); } };
const badge = (text, kind) => h("span", { class: "badge " + (kind || "") }, text);
const statusBadge = (s) => badge(s, { COMPLETED: "ok", APPROVED: "ok", PENDING: "warn", REJECTED: "bad" }[s]);
const progressBar = (pct) => { const i = h("i"); i.style.width = pct + "%"; return h("div", { class: "bar", role: "progressbar", "aria-valuenow": pct, "aria-valuemin": 0, "aria-valuemax": 100 }, i); };
const page = (title, sub) => [h("h1", {}, title), h("p", { class: "sub" }, sub || "")];
const empty = (t) => h("div", { class: "empty" }, t);

function field(label, input) { return h("div", {}, h("label", {}, label), input); }

// ---------- auth ----------
function logout() {
  state.token = null; state.user = null;
  sessionStorage.removeItem("ws_token"); sessionStorage.removeItem("ws_user");
  location.hash = "#/login"; route();
}

function renderLogin() {
  const err = h("div", { class: "err", role: "alert" });
  const email = h("input", { type: "email", required: true, autocomplete: "username" });
  const pw = h("input", { type: "password", required: true, autocomplete: "current-password" });
  const form = h("form", { class: "card login", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    try {
      const data = await api("/auth/login", { method: "POST", body: { email: email.value, password: pw.value } });
      state.token = data.access_token; state.user = data.user;
      sessionStorage.setItem("ws_token", state.token); sessionStorage.setItem("ws_user", JSON.stringify(state.user));
      location.hash = "#/dashboard"; route();
    } catch (ex) { err.textContent = ex.message; }
  } }, h("h1", {}, "Sign in"), h("p", { class: "sub" }, "WorkSphere HRMS"), field("Email", email), field("Password", pw), err, h("button", { class: "btn", type: "submit" }, "Sign in"));
  view.replaceChildren(form);
}

// ---------- shared widgets ----------
function checklist(items, { onToggle, onDelete }) {
  if (!items.length) return empty("No onboarding tasks yet.");
  return items.map((it) => {
    const cb = h("input", { type: "checkbox", checked: it.status === "COMPLETED", "aria-label": it.task_name, onchange: guard(() => onToggle(it, cb.checked)) });
    return h("div", { class: "check" + (it.status === "COMPLETED" ? " done" : "") }, cb,
      h("div", { class: "grow" }, h("div", { class: "t" }, it.task_name), h("div", { class: "muted" }, "Due " + fmtDate(it.due_date))),
      it.is_overdue ? badge("Overdue", "bad") : null,
      onDelete ? h("button", { class: "btn danger small", type: "button", onclick: guard(() => onDelete(it)) }, "Remove") : null);
  });
}

// ---------- Dashboard ----------
async function viewDashboard() {
  const root = h("div", {}, page("Welcome" + (state.user.full_name ? ", " + state.user.full_name : ""), "Here is what needs your attention."));
  view.replaceChildren(root);
  try {
    const s = await api("/tasks/summary");
    root.append(h("div", { class: "grid" }, ...[["Total tasks", s.total], ["Pending", s.pending], ["Completed", s.completed], ["Overdue", s.overdue]].map(([l, n]) => h("div", { class: "tile" }, h("b", {}, n), h("span", {}, l)))));
  } catch (_) { /* no employee profile */ }
  if (state.user.employee_id) {
    try {
      const p = await api("/onboarding/me/progress");
      if (p.total) root.append(h("div", { class: "card" }, h("h2", {}, "Onboarding progress: " + p.percent + "%"), progressBar(p.percent), h("p", { class: "muted" }, p.completed + " of " + p.total + " tasks complete. ", h("a", { href: "#/onboarding" }, "Open checklist"))));
    } catch (_) { /* ignore */ }
  }
  const anns = await api("/announcements?limit=3");
  root.append(h("div", { class: "card" }, h("h2", {}, "Latest announcements"), anns.length ? anns.map((a) => h("p", {}, h("a", { href: "#/announcements/" + a.id }, a.title), h("span", { class: "muted" }, " - " + fmtDateTime(a.created_at)))) : empty("Nothing posted yet."), h("a", { href: "#/announcements" }, "See all")));
}

// ---------- Module 21: Onboarding ----------
async function viewOnboarding() {
  const root = h("div", {}, page("Onboarding", "Checklist and progress for new employees."));
  view.replaceChildren(root);

  if (state.user.employee_id) {
    const mine = h("div", { class: "card" });
    root.append(mine);
    const load = async () => {
      const [items, p] = await Promise.all([api("/onboarding/me"), api("/onboarding/me/progress")]);
      mine.replaceChildren(h("h2", {}, "My checklist - " + p.percent + "% complete"), progressBar(p.percent),
        checklist(items, { onToggle: async (it, done) => { await api("/onboarding/" + it.id + "/status", { method: "PATCH", body: { status: done ? "COMPLETED" : "PENDING" } }); await load(); } }));
    };
    await load();
  }

  if (isStaff()) {
    const dir = await api("/auth/employees");
    const sel = h("select", {}, h("option", { value: "" }, "Select an employee..."), dir.map((e) => h("option", { value: e.id }, e.full_name + (e.department ? " (" + e.department + ")" : ""))));
    const area = h("div");
    const load = async () => {
      if (!sel.value) { area.replaceChildren(); return; }
      const id = sel.value;
      const [items, p] = await Promise.all([api("/onboarding/employee/" + id), api("/onboarding/employee/" + id + "/progress")]);
      const name = h("input", { required: true, maxlength: 200, placeholder: "Task name" });
      const due = h("input", { type: "date", required: true, min: today() });
      area.replaceChildren(h("h2", {}, p.completed + " of " + p.total + " done (" + p.percent + "%)"), progressBar(p.percent),
        checklist(items, {
          onToggle: async (it, done) => { await api("/onboarding/" + it.id + "/status", { method: "PATCH", body: { status: done ? "COMPLETED" : "PENDING" } }); await load(); },
          onDelete: async (it) => { await api("/onboarding/" + it.id, { method: "DELETE" }); await load(); },
        }),
        h("form", { class: "row", onsubmit: guard(async (e) => { e.preventDefault(); await api("/onboarding", { method: "POST", body: { employee_id: Number(id), task_name: name.value, due_date: due.value } }); toast("Task assigned"); await load(); }) },
          h("div", { class: "grow" }, name), due, h("button", { class: "btn", type: "submit" }, "Assign task"),
          h("button", { class: "btn ghost", type: "button", onclick: guard(async () => { const r = await api("/onboarding/employee/" + id + "/default-checklist", { method: "POST" }); toast(r.length + " default task(s) added"); await load(); }) }, "Add default checklist")));
    };
    sel.addEventListener("change", guard(load));
    root.append(h("div", { class: "card" }, h("h2", {}, "Assign and track (HR / Admin)"), sel, area));
  }
}

// ---------- Module 22: Resignation & exit ----------
const STAGES = [["UNDER_REVIEW", "Under review"], ["SERVING_NOTICE", "Serving notice"], ["EXITED", "Exited"]];
function exitStatus(r) {
  if (r.exit_stage === "REJECTED") return h("div", { class: "stage" }, h("span", { class: "on" }, "Rejected"));
  return h("div", { class: "stage" }, STAGES.map(([k, l]) => h("span", { class: r.exit_stage === k ? "on" : "" }, l)));
}
async function viewResignation() {
  const root = h("div", {}, page("Resignation & exit", "Submit a resignation and follow its status."));
  view.replaceChildren(root);

  if (state.user.employee_id) {
    const load = async () => {
      const mine = await api("/resignations/me");
      const active = mine.some((r) => r.status === "PENDING" || r.status === "APPROVED");
      const box = h("div", { class: "card" }, h("h2", {}, "My resignation"));
      if (!active) {
        const reason = h("textarea", { required: true, minlength: 10, maxlength: 2000 });
        const notice = h("input", { type: "number", min: 0, max: 180, value: 30, required: true });
        box.append(h("form", { onsubmit: guard(async (e) => { e.preventDefault(); await api("/resignations", { method: "POST", body: { reason: reason.value, notice_period: Number(notice.value) } }); toast("Resignation submitted"); await viewResignation(); }) },
          field("Reason (min. 10 characters)", reason), field("Notice period (days)", notice), h("p", {}, h("button", { class: "btn", type: "submit" }, "Submit resignation"))));
      }
      mine.forEach((r) => box.append(h("div", { class: "card" },
        h("div", { class: "row between" }, h("div", {}, statusBadge(r.status), " Submitted " + fmtDateTime(r.created_at)),
          r.status === "PENDING" ? h("button", { class: "btn danger small", type: "button", onclick: guard(async () => { await api("/resignations/" + r.id, { method: "DELETE" }); toast("Withdrawn"); await viewResignation(); }) }, "Withdraw") : null),
        exitStatus(r),
        h("p", { class: "muted" }, "Notice: " + r.notice_period + " days. Last working day: " + fmtDate(r.last_working_day) + (r.days_remaining != null ? " (" + r.days_remaining + " days left)" : "")),
        h("p", {}, r.reason))));
      root.replaceChildren(...page("Resignation & exit", "Submit a resignation and follow its status."), box);
      if (isStaff()) await staffPanel();
    };
    await load();
  } else if (isStaff()) await staffPanel();

  async function staffPanel() {
    const rows = await api("/resignations");
    const card = h("div", { class: "card" }, h("h2", {}, "All resignations (HR / Admin)"));
    if (!rows.length) card.append(empty("No resignations."));
    else {
      const decide = (r, status, msg) => guard(async () => {
        await api("/resignations/" + r.id + "/decision", { method: "PATCH", body: { status } });
        toast(msg);
        await viewResignation();
      });
      const actions = (r) => (r.status !== "PENDING" ? null : h("div", { class: "row" },
        h("button", { class: "btn ok small", type: "button", onclick: decide(r, "APPROVED", "Approved") }, "Approve"),
        h("button", { class: "btn danger small", type: "button", onclick: decide(r, "REJECTED", "Rejected") }, "Reject")));
      const tr = (r) => h("tr", {},
        h("td", {}, r.employee_name),
        h("td", {}, r.reason),
        h("td", {}, r.notice_period + "d"),
        h("td", {}, fmtDate(r.last_working_day)),
        h("td", {}, statusBadge(r.status), h("div", { class: "muted" }, r.exit_stage.replace("_", " ").toLowerCase())),
        h("td", {}, actions(r)));
      const head = h("thead", {}, h("tr", {}, ["Employee", "Reason", "Notice", "Last day", "Status", ""].map((t) => h("th", {}, t))));
      card.append(h("div", { class: "table-wrap" }, h("table", {}, head, h("tbody", {}, rows.map(tr)))));
    }
    root.append(card);
  }
}

// ---------- Module 23: Announcements ----------
async function viewAnnouncements() {
  const root = h("div", {}, page("Announcements", "News and updates from HR."));
  view.replaceChildren(root);
  if (isStaff()) {
    const title = h("input", { required: true, maxlength: 200 });
    const msg = h("textarea", { required: true, maxlength: 5000 });
    root.append(h("form", { class: "card", onsubmit: guard(async (e) => { e.preventDefault(); await api("/announcements", { method: "POST", body: { title: title.value, message: msg.value } }); toast("Announcement posted"); await viewAnnouncements(); }) },
      h("h2", {}, "Post an announcement"), field("Title", title), field("Message", msg), h("p", {}, h("button", { class: "btn", type: "submit" }, "Post"))));
  }
  const items = await api("/announcements");
  if (!items.length) root.append(empty("No announcements yet."));
  items.forEach((a) => root.append(h("div", { class: "card ann", tabindex: 0, role: "link", onclick: () => (location.hash = "#/announcements/" + a.id), onkeydown: (e) => { if (e.key === "Enter") location.hash = "#/announcements/" + a.id; } },
    h("h2", {}, a.title), h("div", { class: "muted" }, a.created_by_name + " - " + fmtDateTime(a.created_at)), h("p", {}, a.message.length > 160 ? a.message.slice(0, 160) + "..." : a.message))));
}
async function viewAnnouncementDetail(id) {
  const a = await api("/announcements/" + id);
  view.replaceChildren(h("a", { href: "#/announcements" }, "< Back to board"),
    h("div", { class: "card" }, h("h1", {}, a.title), h("div", { class: "muted" }, a.created_by_name + " - " + fmtDateTime(a.created_at)), h("p", { class: "detail-msg" }, a.message),
      isStaff() ? h("button", { class: "btn danger small", type: "button", onclick: guard(async () => { if (!confirm("Delete this announcement?")) return; await api("/announcements/" + id, { method: "DELETE" }); location.hash = "#/announcements"; }) }, "Delete") : null));
}

// ---------- Module 24: Tasks ----------
async function viewTasks() {
  const root = h("div", {}, page("Tasks", isStaff() ? "Assign work and track progress." : "Tasks assigned to you."));
  view.replaceChildren(root);
  const tiles = h("div", { class: "grid" });
  const listCard = h("div", { class: "card" });
  const filter = h("select", { "aria-label": "Filter by status" }, [["", "All statuses"], ["PENDING", "Pending"], ["COMPLETED", "Completed"]].map(([v, l]) => h("option", { value: v }, l)));
  const load = async () => {
    const [s, tasks] = await Promise.all([api("/tasks/summary"), api("/tasks" + (filter.value ? "?status=" + filter.value : ""))]);
    tiles.replaceChildren(...[["Total", s.total], ["Pending", s.pending], ["Completed", s.completed], ["Overdue", s.overdue]].map(([l, n]) => h("div", { class: "tile" }, h("b", {}, n), h("span", {}, l))));
    listCard.replaceChildren(h("div", { class: "row between" }, h("h2", {}, "Task list"), filter),
      tasks.length ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Task", isStaff() ? "Assignee" : null, "Due", "Status", ""].filter(Boolean).map((t) => h("th", {}, t)))),
        h("tbody", {}, tasks.map((t) => h("tr", {}, h("td", {}, h("b", {}, t.title), t.description ? h("div", { class: "muted" }, t.description) : null), isStaff() ? h("td", {}, t.assignee_name) : null,
          h("td", {}, fmtDate(t.due_date), t.is_overdue ? [" ", badge("Overdue", "bad")] : null), h("td", {}, statusBadge(t.status)),
          h("td", {}, h("div", { class: "row" },
            h("button", { class: "btn ghost small", type: "button", onclick: guard(async () => { await api("/tasks/" + t.id + "/status", { method: "PATCH", body: { status: t.status === "COMPLETED" ? "PENDING" : "COMPLETED" } }); await load(); }) }, t.status === "COMPLETED" ? "Reopen" : "Mark complete"),
            isStaff() ? h("button", { class: "btn danger small", type: "button", onclick: guard(async () => { if (!confirm("Delete this task?")) return; await api("/tasks/" + t.id, { method: "DELETE" }); await load(); }) }, "Delete") : null))))))) : empty("No tasks."));
  };
  filter.addEventListener("change", guard(load));
  root.append(tiles);
  if (isStaff()) {
    const dir = await api("/auth/employees");
    const who = h("select", { required: true }, h("option", { value: "" }, "Select..."), dir.map((e) => h("option", { value: e.id }, e.full_name)));
    const title = h("input", { required: true, maxlength: 200 });
    const desc = h("textarea", { maxlength: 2000 });
    const due = h("input", { type: "date", required: true, min: today() });
    root.append(h("form", { class: "card", onsubmit: guard(async (e) => { e.preventDefault(); await api("/tasks", { method: "POST", body: { assigned_to: Number(who.value), title: title.value, description: desc.value || null, due_date: due.value } }); toast("Task assigned"); title.value = ""; desc.value = ""; await load(); }) },
      h("h2", {}, "Assign a task"), h("div", { class: "grid" }, field("Assign to", who), field("Title", title), field("Due date", due)), field("Description", desc), h("p", {}, h("button", { class: "btn", type: "submit" }, "Assign"))));
  }
  root.append(listCard);
  await load();
}

// ---------- Module 26: Feedback ----------
async function viewFeedback() {
  const root = h("div", {}, page("Feedback", isStaff() ? "What employees are telling us." : "Share your thoughts with HR."));
  view.replaceChildren(root);
  if (state.user.employee_id) {
    const rating = h("select", { required: true }, [5, 4, 3, 2, 1].map((n) => h("option", { value: n }, n + " - " + ["", "Very poor", "Poor", "Okay", "Good", "Excellent"][n])));
    const msg = h("textarea", { required: true, maxlength: 2000 });
    root.append(h("form", { class: "card", onsubmit: guard(async (e) => { e.preventDefault(); await api("/feedback", { method: "POST", body: { message: msg.value, rating: Number(rating.value) } }); toast("Thanks for your feedback"); msg.value = ""; if (isStaff()) await viewFeedback(); }) },
      h("h2", {}, "Submit feedback"), field("Rating", rating), field("Message", msg), h("p", {}, h("button", { class: "btn", type: "submit" }, "Send feedback"))));
  }
  if (isStaff()) {
    const [s, rows] = await Promise.all([api("/feedback/stats"), api("/feedback")]);
    const max = Math.max(1, ...Object.values(s.distribution));
    root.append(h("div", { class: "grid" }, h("div", { class: "tile" }, h("b", {}, s.average_rating.toFixed(2)), h("span", {}, "Average rating")), h("div", { class: "tile" }, h("b", {}, s.count), h("span", {}, "Responses"))),
      h("div", { class: "card" }, h("h2", {}, "Rating distribution"), [5, 4, 3, 2, 1].map((n) => h("div", { class: "dist" }, h("span", {}, n + "*"), progressBar(Math.round((s.distribution[n] * 100) / max)), h("span", {}, s.distribution[n])))),
      h("div", { class: "card" }, h("h2", {}, "All feedback"), rows.length ? rows.map((f) => h("div", { class: "check" }, h("div", { class: "grow" }, h("b", {}, f.employee_name), " ", badge(f.rating + "/5", f.rating >= 4 ? "ok" : f.rating <= 2 ? "bad" : "warn"), h("div", {}, f.message), h("div", { class: "muted" }, fmtDateTime(f.created_at))))) : empty("No feedback yet.")));
  }
}

// ---------- Module 27: Profile & settings ----------
async function viewProfile() {
  const root = h("div", {}, page("Profile & settings", "Manage your details, password and notifications."));
  view.replaceChildren(root);
  const p = await api("/profile");
  const name = h("input", { value: p.full_name || "", maxlength: 120, disabled: !p.employee_id });
  const phone = h("input", { value: p.phone || "", maxlength: 20, placeholder: "+91 98765 43210", disabled: !p.employee_id });
  root.append(h("form", { class: "card", onsubmit: guard(async (e) => { e.preventDefault(); const body = { full_name: name.value }; if (phone.value.trim()) body.phone = phone.value; const u = await api("/profile", { method: "PUT", body }); state.user.full_name = u.full_name; sessionStorage.setItem("ws_user", JSON.stringify(state.user)); drawChrome(); toast("Profile updated"); }) },
    h("h2", {}, "Profile"), h("p", { class: "muted" }, p.email + " - " + p.role + (p.department ? " - " + p.department : "") + (p.designation ? " - " + p.designation : "")),
    field("Full name", name), field("Phone", phone), h("p", {}, h("button", { class: "btn", type: "submit", disabled: !p.employee_id }, "Save profile"))));

  const cur = h("input", { type: "password", required: true, autocomplete: "current-password" });
  const nw = h("input", { type: "password", required: true, minlength: 8, autocomplete: "new-password" });
  root.append(h("form", { class: "card", onsubmit: guard(async (e) => { e.preventDefault(); await api("/profile/change-password", { method: "POST", body: { current_password: cur.value, new_password: nw.value } }); cur.value = ""; nw.value = ""; toast("Password changed"); }) },
    h("h2", {}, "Change password"), field("Current password", cur), field("New password (8+ chars, upper, lower, digit)", nw), h("p", {}, h("button", { class: "btn", type: "submit" }, "Change password"))));

  const prefs = await api("/profile/preferences");
  const defs = [["email_notifications", "Email notifications"], ["in_app_notifications", "In-app notifications"], ["announcement_alerts", "Announcement alerts"], ["task_alerts", "Task alerts"]];
  root.append(h("div", { class: "card" }, h("h2", {}, "Notification preferences"), defs.map(([k, l]) => {
    const cb = h("input", { type: "checkbox", checked: prefs[k], id: "pref-" + k, onchange: guard(async () => { await api("/profile/preferences", { method: "PUT", body: { [k]: cb.checked } }); toast("Preference saved"); }) });
    return h("div", { class: "toggle" }, h("label", { for: "pref-" + k, style: null }, l), cb);
  })));
}

// ---------- Module 25: Integrations (exports & calendar) ----------
async function viewIntegrations() {
  const root = h("div", {}, page("Exports & calendar", "Download reports and sync deadlines to your calendar."));
  view.replaceChildren(root);
  if (state.user.employee_id) {
    const events = await api("/integrations/calendar/events");
    root.append(h("div", { class: "card" }, h("div", { class: "row between" }, h("h2", {}, "Calendar sync"), h("button", { class: "btn", type: "button", onclick: () => download("/integrations/calendar/ics", "worksphere.ics") }, "Download .ics (Google / Outlook / Apple)")),
      events.length ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Date", "Event", "Type", ""].map((t) => h("th", {}, t)))),
        h("tbody", {}, events.map((e) => h("tr", {}, h("td", {}, fmtDate(e.date)), h("td", {}, e.title), h("td", {}, badge(e.kind)),
          h("td", {}, e.google_calendar_url.startsWith("https://calendar.google.com/") ? h("a", { href: e.google_calendar_url, target: "_blank", rel: "noopener noreferrer" }, "Add to Google Calendar") : null)))))) : empty("No upcoming deadlines.")));
  }
  if (isStaff()) {
    const info = await api("/integrations/status");
    const sel = h("select", {}, info.reports.map((r) => h("option", { value: r }, r)));
    root.append(h("div", { class: "card" }, h("h2", {}, "Export reports"), h("p", { class: "muted" }, "Email notifications are " + (info.email_enabled ? "enabled." : "disabled (set EMAIL_ENABLED=true in .env).")),
      h("div", { class: "row" }, sel, ...info.formats.map((f) => h("button", { class: "btn" + (f === "pdf" ? " ghost" : ""), type: "button", onclick: () => download("/integrations/export/" + sel.value + "?format=" + f, sel.value + "." + f) }, "Export " + f.toUpperCase())))));
  }
}

// ---------- routing ----------
const ROUTES = [
  ["dashboard", "Dashboard", viewDashboard],
  ["onboarding", "Onboarding", viewOnboarding],
  ["tasks", "Tasks", viewTasks],
  ["announcements", "Announcements", viewAnnouncements],
  ["resignation", "Exit", viewResignation],
  ["feedback", "Feedback", viewFeedback],
  ["integrations", "Exports & Calendar", viewIntegrations],
  ["profile", "Profile", viewProfile],
];

function drawChrome() {
  const bar = document.getElementById("topbar");
  bar.hidden = !state.user;
  if (!state.user) return;
  document.getElementById("whoami").textContent = (state.user.full_name || state.user.email) + " (" + state.user.role + ")";
  const cur = (location.hash.split("/")[1] || "dashboard");
  document.getElementById("nav").replaceChildren(...ROUTES.map(([k, l]) => h("a", { href: "#/" + k, class: k === cur ? "active" : "", "aria-current": k === cur ? "page" : null }, l)));
}

async function route() {
  drawChrome();
  if (!state.token || !state.user) { renderLogin(); return; }
  const [, name = "dashboard", arg] = location.hash.split("/");
  try {
    if (name === "announcements" && arg && /^\d+$/.test(arg)) await viewAnnouncementDetail(arg);
    else { const r = ROUTES.find((x) => x[0] === name) || ROUTES[0]; await r[2](); }
    view.focus({ preventScroll: true });
  } catch (e) { view.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Something went wrong"), h("p", {}, e.message))); }
}

document.getElementById("logout").addEventListener("click", logout);
window.addEventListener("hashchange", route);
route();
