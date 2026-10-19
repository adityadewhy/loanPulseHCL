// LoanPulse — Production SPA
"use strict";

const previousToken = localStorage.getItem("loanpulse_token");
if (previousToken) localStorage.removeItem("loanpulse_token");
let token = sessionStorage.getItem("loanpulse_token") || "";
let currentUser = null;
let currentTab = "dashboard";
let currentRepaymentLoanId = null;
const LTI_REVIEW_THRESHOLD = Number(document.body.dataset.ltiReviewThreshold || 40);
const LTI_REJECTION_THRESHOLD = Number(document.body.dataset.ltiRejectionThreshold || 60);

// ── Status badge class map ─────────────────────────────────────────────────
const STATUS_BADGES = {
  PENDING:      "bg-amber-500/15 text-amber-300 border border-amber-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(245,158,11,0.15)]",
  UNDER_REVIEW: "bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(99,102,241,0.15)]",
  APPROVED:     "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(16,185,129,0.15)]",
  REJECTED:     "bg-rose-500/15 text-rose-300 border border-rose-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(244,63,94,0.15)]",
  DISBURSED:    "bg-purple-500/15 text-purple-300 border border-purple-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(168,85,247,0.15)]",
  ACTIVE:       "bg-sky-500/15 text-sky-300 border border-sky-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(14,165,233,0.15)]",
  CLOSED:       "bg-slate-500/15 text-slate-300 border border-slate-500/30 backdrop-blur-md",
  DEFAULTED:    "bg-red-950/40 text-red-300 border border-red-500/40 backdrop-blur-md shadow-[0_0_12px_rgba(239,68,68,0.2)]",
  PAID:         "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(16,185,129,0.15)]",
  OVERDUE:      "bg-rose-500/20 text-rose-300 border border-rose-500/40 backdrop-blur-md shadow-[0_0_12px_rgba(244,63,94,0.25)]",
};

// ── Toast Notification System ──────────────────────────────────────────────
const TOAST_ICONS = {
  success: "✓",
  error:   "✕",
  info:    "ℹ",
  warn:    "⚠",
};

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function hasWriteAccess() {
  return Boolean(currentUser && ["ADMIN", "OFFICER"].includes(currentUser.role));
}

/**
 * Show a non-blocking glass toast notification.
 * @param {string} message  — Message text
 * @param {"success"|"error"|"info"|"warn"} type — Visual variant
 * @param {number} duration — Auto-dismiss delay in ms (default 4000)
 */
function showToast(message, type = "info", duration = 4000) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const icon = document.createElement("span");
  icon.textContent = TOAST_ICONS[type] || "ℹ";
  icon.setAttribute("aria-hidden", "true");
  icon.style.cssText = "font-size:15px;line-height:1;flex-shrink:0";
  const label = document.createElement("span");
  label.textContent = message;
  label.style.cssText = "flex:1;line-height:1.4";
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "✕";
  close.setAttribute("aria-label", "Dismiss notification");
  close.style.cssText = "opacity:0.7;background:none;border:none;color:inherit;cursor:pointer;font-size:14px;flex-shrink:0;padding:0";
  close.addEventListener("click", () => toast.remove());
  toast.append(icon, label, close);
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-exit");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
  }, duration);
}

// ── API Fetch Helper ───────────────────────────────────────────────────────
async function apiFetch(endpoint, options = {}) {
  options.headers = options.headers || {};
  if (token) options.headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(endpoint, options);
  if (res.status === 401) {
    handleLogout();
    throw new Error("Session expired. Please log in again.");
  }
  return res;
}

// ── Authentication ─────────────────────────────────────────────────────────
async function handleLogin() {
  const email    = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  const errBox   = document.getElementById("authError");
  errBox.classList.add("hidden");

  const formData = new URLSearchParams();
  formData.append("username", email);
  formData.append("password", password);

  try {
    const res  = await fetch("/auth/login", {
      method:  "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body:    formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");

    token = data.access_token;
    sessionStorage.setItem("loanpulse_token", token);
    document.getElementById("authModal").classList.add("hidden");
    await checkAuth();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
}

function showSignupForm() {
  document.getElementById("loginForm").classList.add("hidden");
  document.getElementById("signupForm").classList.remove("hidden");
  document.getElementById("authError").classList.add("hidden");
}

function showLoginForm() {
  document.getElementById("signupForm").classList.add("hidden");
  document.getElementById("loginForm").classList.remove("hidden");
  document.getElementById("authError").classList.add("hidden");
}

async function handleSignup(event) {
  event?.preventDefault();
  const fullName = document.getElementById("signupFullName").value.trim();
  const email = document.getElementById("signupEmail").value.trim();
  const password = document.getElementById("signupPassword").value;
  const confirmation = document.getElementById("signupPasswordConfirm").value;
  const accountType = document.getElementById("signupAccountType").value;
  const errBox = document.getElementById("authError");
  errBox.classList.add("hidden");
  errBox.classList.remove("text-emerald-300");
  errBox.classList.add("text-rose-300");
  if (password !== confirmation) {
    errBox.textContent = "Passwords do not match.";
    errBox.classList.remove("hidden");
    return;
  }
  try {
    const res = await fetch("/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: fullName, email, password, account_type: accountType }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Account creation failed.");
    if (accountType === "STAFF") {
      errBox.textContent = data.detail;
      errBox.classList.remove("hidden");
      errBox.classList.remove("text-rose-300");
      errBox.classList.add("text-emerald-300");
      ["signupFullName", "signupEmail", "signupPassword", "signupPasswordConfirm"].forEach(id => { document.getElementById(id).value = ""; });
      return;
    }
    token = data.access_token;
    sessionStorage.setItem("loanpulse_token", token);
    ["signupFullName", "signupEmail", "signupPassword", "signupPasswordConfirm"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("authModal").classList.add("hidden");
    errBox.classList.remove("text-emerald-300");
    errBox.classList.add("text-rose-300");
    await checkAuth();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
}

function handleLogout() {
  token       = "";
  currentUser = null;
  sessionStorage.removeItem("loanpulse_token");
  showLoginForm();
  document.getElementById("loginPassword").value = "";
  document.getElementById("authModal").classList.remove("hidden");
}

async function checkAuth() {
  if (!token) { document.getElementById("authModal").classList.remove("hidden"); return; }
  try {
    const res = await apiFetch("/auth/me");
    if (!res.ok) throw new Error("Auth failed");
    currentUser = await res.json();
    document.getElementById("authModal").classList.add("hidden");
    const borrower = currentUser.role === "CUSTOMER";
    const isBoss = currentUser.role === "ADMIN" && currentUser.email.toLowerCase() === document.body.dataset.bossEmail;
    document.querySelectorAll("[data-staff-only]").forEach(el => el.classList.toggle("role-hidden", borrower));
    document.querySelectorAll("[data-borrower-only]").forEach(el => el.classList.toggle("role-hidden", !borrower));
    document.querySelectorAll("[data-boss-only]").forEach(el => el.classList.toggle("hidden", !isBoss));
    document.querySelectorAll("[data-write-only]").forEach(el => {
      el.classList.toggle("hidden", !hasWriteAccess());
    });
    document.querySelectorAll("[data-loan-submit-form]").forEach(el => {
      el.classList.toggle("hidden", !borrower && !hasWriteAccess());
    });

    const nameEl   = document.getElementById("userName");
    const roleEl   = document.getElementById("userRole");
    const avatarEl = document.getElementById("userAvatar");
    if (nameEl)   nameEl.textContent   = currentUser.full_name;
    if (roleEl)   roleEl.textContent   = currentUser.role === "CUSTOMER" ? "BORROWER" : currentUser.role;
    if (avatarEl) avatarEl.textContent = currentUser.full_name.substring(0, 2).toUpperCase();

    if (borrower) {
      const name = document.querySelector('[name="applicant_name"]');
      const email = document.querySelector('[name="applicant_email"]');
      if (name) { name.value = currentUser.full_name; name.readOnly = true; }
      if (email) { email.value = currentUser.email; email.readOnly = true; }
    } else {
      const name = document.querySelector('[name="applicant_name"]');
      const email = document.querySelector('[name="applicant_email"]');
      if (name) { name.value = ""; name.readOnly = false; }
      if (email) { email.value = ""; email.readOnly = false; }
    }

    switchTab(borrower ? "borrower" : currentTab);
    loadNotificationsCount();
  } catch (e) {
    handleLogout();
  }
}

// ── Tabs & Navigation ──────────────────────────────────────────────────────
function switchTab(tabId) {
  const borrower = currentUser?.role === "CUSTOMER";
  if (borrower && !["borrower", "new-application"].includes(tabId)) tabId = "borrower";
  const isBoss = currentUser?.role === "ADMIN" && currentUser.email.toLowerCase() === document.body.dataset.bossEmail;
  if (!borrower && (tabId === "borrower" || (tabId === "new-application" && !hasWriteAccess()) || (tabId === "staff-registrations" && !isBoss))) tabId = "dashboard";
  currentTab = tabId;
  const tabs = ["borrower", "dashboard", "applications", "new-application", "repayments", "notifications", "staff-registrations"];
  const borrowerBack = document.querySelector("#view-new-application [data-borrower-only]");
  if (borrowerBack) borrowerBack.classList.toggle("hidden", !borrower || tabId !== "new-application");

  tabs.forEach(t => {
    const view = document.getElementById(`view-${t}`);
    const nav  = document.getElementById(`nav-${t}`);
    const mob  = document.getElementById(`mob-${t}`);

    if (t === tabId) {
      if (view) view.classList.remove("hidden");
      if (nav)  { nav.classList.add("glass-card","border-white/20","text-white","shadow-lg"); nav.classList.remove("text-slate-400","hover:bg-white/5"); }
      if (mob)  { mob.classList.add("text-sky-400","scale-105"); mob.classList.remove("text-slate-400"); }
    } else {
      if (view) view.classList.add("hidden");
      if (nav)  { nav.classList.remove("glass-card","border-white/20","text-white","shadow-lg"); nav.classList.add("text-slate-400","hover:bg-white/5"); }
      if (mob)  { mob.classList.remove("text-sky-400","scale-105"); mob.classList.add("text-slate-400"); }
    }
  });

  const titles = {
    borrower:          ["My loan applications", "Track each request and its latest status"],
    dashboard:         ["Portfolio Dashboard",      "Real-time credit portfolio performance and risk metrics"],
    applications:      ["Loan Applications",        "Origination, risk assessment, and officer decisions"],
    "new-application": ["New Loan Application",     "Submit details for an advisory risk assessment"],
    repayments:        ["Repayment Tracking",       "Amortization schedules, monthly installment servicing, and arrears"],
    notifications:     ["Notifications",            "In-app notification log"],
    "staff-registrations": ["Staff registrations", "Review staff account requests"],
  };

  const titleEl = document.getElementById("viewTitle");
  const subEl   = document.getElementById("viewSubtitle");
  if (titleEl && titles[tabId]) titleEl.textContent = titles[tabId][0];
  if (subEl   && titles[tabId]) subEl.textContent   = titles[tabId][1];

  if (tabId === "dashboard")       loadDashboard();
  if (tabId === "applications")    loadApplications();
  if (tabId === "borrower")        loadBorrowerApplications();
  if (tabId === "repayments")      loadRepaymentLoans();
  if (tabId === "notifications")   loadNotifications();
  if (tabId === "staff-registrations") loadStaffRegistrations("PENDING");
}

async function loadStaffRegistrations(state = "PENDING") {
  const target = document.getElementById("staffRegistrationsList");
  try {
    const response = await apiFetch(`/auth/staff-registrations?status=${encodeURIComponent(state)}`);
    const rows = await response.json();
    if (!response.ok) throw new Error(rows.detail || "Could not load registrations.");
    target.innerHTML = rows.length ? rows.map(row => `<article class="glass-card rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div><div class="font-semibold text-white">${escapeHTML(row.full_name)}</div><div class="text-xs text-slate-400">${escapeHTML(row.email)} · ${new Date(row.created_at).toLocaleDateString()}</div></div><div class="flex gap-2">${state !== "APPROVED" ? `<button onclick="setStaffRegistration(${row.id}, 'APPROVED')" class="glass-btn-primary px-3 py-2 rounded-lg text-xs">Approve</button>` : ""}${state !== "DISAPPROVED" ? `<button onclick="setStaffRegistration(${row.id}, 'DISAPPROVED')" class="glass-btn-subtle px-3 py-2 rounded-lg text-xs text-rose-300">Disapprove</button>` : ""}${state !== "PENDING" ? `<button onclick="setStaffRegistration(${row.id}, 'PENDING')" class="glass-btn-subtle px-3 py-2 rounded-lg text-xs">Revert to pending</button>` : ""}</div></article>`).join("") : `<div class="glass-card rounded-2xl p-6 text-center text-sm text-slate-400">No ${state.toLowerCase()} staff registrations.</div>`;
  } catch (error) {
    target.innerHTML = `<div class="text-sm text-rose-300">${escapeHTML(error.message)}</div>`;
  }
}

async function setStaffRegistration(userId, nextStatus) {
  const response = await apiFetch("/auth/staff-registrations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, status: nextStatus }) });
  const data = await response.json();
  if (!response.ok) return showToast(data.detail || "Could not update registration.", "error");
  showToast(`Staff registration ${nextStatus.toLowerCase()}.`, "success");
  loadStaffRegistrations(nextStatus);
}

function refreshCurrentTab() { switchTab(currentTab); }

// ── Dashboard ──────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const res  = await apiFetch("/dashboard/kpis");
    const data = await res.json();

    document.getElementById("kpiTotalApps").textContent   = data.total_applications;
    document.getElementById("kpiDisbursed").textContent   = `$${data.total_disbursed_amount.toLocaleString()}`;
    document.getElementById("kpiOverdue").textContent     = data.total_overdue_installments;
    document.getElementById("kpiCollection").textContent  = `${data.collection_rate}%`;

    const stats = [
      { label: "Pending Review",     count: data.pending,                   color: "text-amber-400"  },
      { label: "Under Review",       count: data.under_review,              color: "text-indigo-400" },
      { label: "Approved",           count: data.approved,                  color: "text-emerald-400"},
      { label: "Disbursed / Active", count: data.disbursed + data.active,   color: "text-purple-400" },
      { label: "Rejected",           count: data.rejected,                  color: "text-rose-400"   },
      { label: "Closed / Paid Off",  count: data.closed,                    color: "text-slate-400"  },
      { label: "In Default",         count: data.defaulted,                 color: "text-red-500"    },
    ];

    document.getElementById("lifecycleStats").innerHTML = stats.map(s => `
      <div class="glass-card p-3.5 rounded-2xl">
        <span class="text-[11px] text-slate-400 block">${s.label}</span>
        <span class="text-xl font-bold font-mono ${s.color}">${s.count}</span>
      </div>
    `).join("");
  } catch (e) {
    console.error("Dashboard error:", e);
  }
}

// ── Applications ───────────────────────────────────────────────────────────
async function loadApplications() {
  const search       = document.getElementById("appSearchInput")?.value || "";
  const statusFilter = document.getElementById("appStatusFilter")?.value || "";

  let url = "/applications/?limit=50";
  if (search)       url += `&search=${encodeURIComponent(search)}`;
  if (statusFilter) url += `&status=${encodeURIComponent(statusFilter)}`;

  try {
    const res   = await apiFetch(url);
    const data  = await res.json();
    const tbody = document.getElementById("applicationsTableBody");

    if (data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-500 font-mono">No loan applications found</td></tr>`;
      return;
    }

    tbody.innerHTML = data.map(app => {
      const lti         = (Number(app.requested_amount) / Number(app.annual_income) * 100).toFixed(1);
      const statusClass = STATUS_BADGES[app.status] || "bg-slate-800 text-slate-300";

      let actionButtons = `<button onclick="event.stopPropagation(); openLoanDetailModal(${app.id})" class="px-2.5 py-1 rounded-lg bg-sky-500/20 hover:bg-sky-500/35 text-sky-300 border border-sky-500/30 backdrop-blur-md text-[10px] font-semibold mr-1 transition shadow-sm">Details</button>`;

      if (hasWriteAccess() && (app.status === "PENDING" || app.status === "UNDER_REVIEW")) {
        actionButtons += `<button onclick="event.stopPropagation(); updateStatus(${app.id}, 'APPROVED')" class="px-2.5 py-1 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/35 text-emerald-300 border border-emerald-500/30 backdrop-blur-md text-[10px] font-semibold mr-1 transition shadow-sm">Approve</button>`;
        actionButtons += `<button onclick="event.stopPropagation(); updateStatus(${app.id}, 'REJECTED')" class="px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/35 text-rose-300 border border-rose-500/30 backdrop-blur-md text-[10px] font-semibold mr-1 transition shadow-sm">Reject</button>`;
      }
      if (hasWriteAccess() && app.status === "APPROVED") {
        actionButtons += `<button onclick="event.stopPropagation(); openDisburseModal(${app.id}, ${app.requested_amount})" class="px-3 py-1 rounded-lg glass-btn-primary text-white font-bold text-[10px] shadow-sm">Disburse</button>`;
      }

      return `
        <tr onclick="openLoanDetailModal(${app.id})" class="hover:bg-white/[0.04] transition border-b border-white/[0.04] cursor-pointer">
          <td class="py-3 px-4 font-mono text-slate-400">#${app.id}</td>
          <td class="py-3 px-4">
            <div class="font-bold text-white">${escapeHTML(app.applicant_name)}</div>
            <div class="text-[10px] text-slate-400">${escapeHTML(app.applicant_email || "no email")}</div>
          </td>
          <td class="py-3 px-4 font-mono text-slate-300">$${app.annual_income.toLocaleString()}</td>
          <td class="py-3 px-4 font-mono text-white font-semibold">$${app.requested_amount.toLocaleString()}</td>
          <td class="py-3 px-4 font-mono ${lti > LTI_REJECTION_THRESHOLD ? "text-rose-400 font-bold" : lti > LTI_REVIEW_THRESHOLD ? "text-amber-400" : "text-emerald-400"}">${lti}%</td>
          <td class="py-3 px-4">
            <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${statusClass}">${escapeHTML(app.status)}</span>
          </td>
          <td class="py-3 px-4 font-mono">
            ${app.risk_score !== null ? `<span class="font-bold ${app.risk_score > 60 ? "text-rose-400" : "text-emerald-400"}">${app.risk_score}/100</span>` : '<span class="text-slate-500">—</span>'}
          </td>
          <td class="py-3 px-4 text-right whitespace-nowrap">${actionButtons}</td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    console.error("Applications load error:", e);
  }
}

async function loadBorrowerApplications() {
  const container = document.getElementById("borrowerApplications");
  if (!container) return;
  try {
    const res = await apiFetch("/applications/?limit=100");
    if (!res.ok) throw new Error("Could not load your applications.");
    const loans = await res.json();
    const counts = loans.reduce((result, loan) => {
      result[loan.status] = (result[loan.status] || 0) + 1;
      return result;
    }, {});
    const statusSummary = [
      ["All requests", loans.length],
      ["In review", (counts.PENDING || 0) + (counts.UNDER_REVIEW || 0)],
      ["Approved / servicing", (counts.APPROVED || 0) + (counts.DISBURSED || 0) + (counts.ACTIVE || 0)],
      ["Resolved", (counts.REJECTED || 0) + (counts.CLOSED || 0) + (counts.DEFAULTED || 0)],
    ];
    document.getElementById("borrowerApplicationStats").innerHTML = statusSummary.map(([label, count]) => `
      <div class="glass-card rounded-2xl p-4"><div class="text-xs text-slate-400">${label}</div><div class="text-2xl font-bold text-white mt-1">${count}</div></div>
    `).join("");
    if (!loans.length) {
      container.innerHTML = `<div class="glass-card rounded-2xl p-8 text-center"><p class="text-slate-300">You have not submitted a loan application yet.</p><button onclick="switchTab('new-application')" class="glass-btn-primary text-sm text-white font-bold px-4 py-2.5 rounded-xl mt-4">Start an application</button></div>`;
      return;
    }
    const loanNames = { HOME: "Home loan", VEHICLE: "Vehicle loan", EDUCATION: "Education loan", PERSONAL: "Personal loan", BUSINESS: "Business loan" };
    container.innerHTML = loans.map(loan => {
      const statusClass = STATUS_BADGES[loan.status] || "bg-slate-800 text-slate-300";
      return `<article class="glass-card rounded-2xl p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div class="flex items-center gap-2 flex-wrap"><h2 class="font-bold text-white">${escapeHTML(loanNames[loan.loan_purpose] || "Loan application")}</h2><span class="px-2 py-0.5 rounded-full text-[10px] font-semibold ${statusClass}">${escapeHTML(loan.status.replaceAll("_", " "))}</span></div>
          <div class="text-xs text-slate-400 mt-2">Request #${loan.id} · $${Number(loan.requested_amount).toLocaleString()} · ${loan.requested_term_months} months</div>
          <div class="text-[11px] text-slate-500 mt-1">Submitted ${new Date(loan.created_at).toLocaleDateString()}</div>
        </div>
        <button onclick="openBorrowerApplication(${loan.id})" class="glass-btn-subtle text-xs font-semibold text-sky-200 px-3 py-2 rounded-xl">Track application</button>
      </article>`;
    }).join("");
  } catch (err) {
    container.innerHTML = `<div class="glass-card rounded-2xl p-6 text-sm text-rose-300">${escapeHTML(err.message)}</div>`;
  }
}

async function openBorrowerApplication(loanId) {
  try {
    const res = await apiFetch(`/applications/${loanId}/details`);
    if (!res.ok) throw new Error("Application details are unavailable.");
    const loan = await res.json();
    document.getElementById("borrowerDetailTitle").textContent = `Application #${loan.id}`;
    document.getElementById("borrowerDetailStatus").textContent = loan.status.replaceAll("_", " ");
    const loanNames = { HOME: "Home loan", VEHICLE: "Vehicle loan", EDUCATION: "Education loan", PERSONAL: "Personal loan", BUSINESS: "Business loan" };
    document.getElementById("borrowerDetailSummary").innerHTML = [
      ["Loan type", loanNames[loan.loan_purpose] || "Loan application"],
      ["Amount requested", `$${Number(loan.requested_amount).toLocaleString()}`],
      ["Term", `${loan.requested_term_months} months`],
      ["Last updated", new Date(loan.updated_at).toLocaleDateString()],
    ].map(([label, value]) => `<div class="glass-card rounded-xl p-3"><div class="text-[10px] text-slate-400">${escapeHTML(label)}</div><div class="text-sm text-white mt-1">${escapeHTML(value)}</div></div>`).join("");
    const history = loan.status_history || [];
    document.getElementById("borrowerDetailHistory").innerHTML = history.length
      ? history.map(event => `<li class="border-l border-sky-400/40 pl-3"><span class="font-semibold text-white">${escapeHTML(String(event.status || "Update").replaceAll("_", " "))}</span><span class="ml-2 text-slate-400">${new Date(event.timestamp).toLocaleString()}</span></li>`).join("")
      : `<li class="text-slate-400">Application received.</li>`;
    const documentsSection = document.getElementById("borrowerDetailDocumentsSection");
    const documentsBox = document.getElementById("borrowerDetailDocuments");
    const documents = loan.documents || [];
    documentsSection.classList.toggle("hidden", documents.length === 0);
    documentsBox.innerHTML = documents.map(doc => {
      const reviewableType = ["application/pdf", "image/png", "image/jpeg", "image/webp"].includes(doc.content_type);
      const reviewableSize = Number(doc.file_size_bytes) <= 5 * 1024 * 1024;
      return `
        <div class="glass-card rounded-xl p-3 flex items-center justify-between gap-3 text-xs">
          <span class="min-w-0 truncate text-slate-200">${escapeHTML(doc.file_name)} <span class="text-slate-500">· ${escapeHTML(doc.document_type)}</span></span>
          ${reviewableType && reviewableSize ? `<button onclick="requestKycReview(${doc.id})" class="glass-btn-subtle flex-shrink-0 px-2.5 py-1.5 rounded-lg text-sky-200">AI check</button>` : `<span class="text-slate-500 text-[10px]">AI check unavailable</span>`}
        </div>`;
    }).join("");
    const scheduleSection = document.getElementById("borrowerDetailScheduleSection");
    const scheduleBox = document.getElementById("borrowerDetailSchedule");
    if (loan.schedule?.length) {
      scheduleSection.classList.remove("hidden");
      scheduleBox.innerHTML = loan.schedule.map(row => `<div class="flex justify-between gap-3 border-b border-white/5 py-2"><span>Payment ${row.installment_number} · due ${escapeHTML(row.due_date)}</span><span>$${Number(row.emi_amount).toLocaleString()} · ${escapeHTML(row.status)}</span></div>`).join("");
    } else {
      scheduleSection.classList.add("hidden");
      scheduleBox.innerHTML = "";
    }
    document.getElementById("borrowerDetailModal").classList.remove("hidden");
  } catch (err) {
    showToast(err.message, "error");
  }
}

function closeBorrowerDetail() {
  document.getElementById("borrowerDetailModal").classList.add("hidden");
}

function openBorrowerFeedback(data) {
  const status = String(data.status || "UNDER_REVIEW").replaceAll("_", " ");
  document.getElementById("borrowerFeedbackTitle").textContent = data.status === "REJECTED" ? "Application assessment" : "Application received";
  document.getElementById("borrowerFeedbackStatus").textContent = `Application #${data.id} · ${status}`;
  document.getElementById("borrowerFeedbackText").textContent = data.borrower_feedback || "Your application is in the lending review process. Check My loan applications for updates.";
  document.getElementById("borrowerFeedbackModal").classList.remove("hidden");
}

function closeBorrowerFeedback() {
  document.getElementById("borrowerFeedbackModal").classList.add("hidden");
}

function toggleKarzai(forceOpen) {
  const panel = document.getElementById("karzaiPanel");
  const open = typeof forceOpen === "boolean" ? forceOpen : panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !open);
  if (open) document.getElementById("karzaiInput").focus();
}

function appendKarzaiMessage(text, fromBorrower) {
  const message = document.createElement("div");
  message.className = fromBorrower
    ? "ml-8 rounded-2xl rounded-tr-sm bg-sky-500/20 p-3 text-sky-50"
    : "mr-6 rounded-2xl rounded-tl-sm bg-white/5 p-3 text-slate-200";
  message.textContent = text;
  const messages = document.getElementById("karzaiMessages");
  messages.appendChild(message);
  messages.scrollTop = messages.scrollHeight;
}

async function sendKarzaiMessage(event) {
  event.preventDefault();
  const input = document.getElementById("karzaiInput");
  const button = document.getElementById("karzaiSend");
  const question = input.value.trim();
  if (!question || button.disabled) return;
  appendKarzaiMessage(question, true);
  input.value = "";
  button.disabled = true;
  button.textContent = "…";
  try {
    const res = await apiFetch("/karzai/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "KARZai is unavailable.");
    appendKarzaiMessage(data.answer || "I couldn't answer that right now.", false);
  } catch (err) {
    appendKarzaiMessage(err.message, false);
  } finally {
    button.disabled = false;
    button.textContent = "Send";
    input.focus();
  }
}

function closeKarzaiInfo() {
  document.getElementById("karzaiInfoModal").classList.add("hidden");
}

async function requestKycReview(documentId) {
  const consent = window.confirm("This sends the selected document, which may contain sensitive personal information, to Google Gemini for a preliminary quality check. It will not verify identity or authenticity. Continue?");
  if (!consent) return;
  try {
    const res = await apiFetch(`/karzai/documents/${documentId}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent: true }),
    });
    const review = await res.json();
    if (!res.ok) throw new Error(review.detail || "AI document review failed.");
    const lines = [
      `Document type: ${review.document_type}`,
      `Readability: ${review.readability}`,
      `Visible expiry: ${review.visible_expiry}`,
      ...(review.missing_items || []).map(item => `• ${item}`),
      `Next step: ${review.next_step}`,
      review.disclaimer,
    ];
    document.getElementById("karzaiInfoBody").textContent = lines.join("\n");
    document.getElementById("karzaiInfoModal").classList.remove("hidden");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function updateStatus(appId, newStatus) {
  try {
    const res = await apiFetch(`/applications/${appId}/status`, {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) throw new Error("Failed to update status");
    showToast(`Application #${appId} marked as ${newStatus}`, "success");
    loadApplications();
  } catch (e) {
    showToast("Error updating status: " + e.message, "error");
  }
}

// ── Loan Detail & Audit Modal ──────────────────────────────────────────────
async function openLoanDetailModal(loanId) {
  try {
    const res = await apiFetch(`/applications/${loanId}/details`);
    if (!res.ok) throw new Error("Could not load application details");
    const app = await res.json();

    document.getElementById("docUploadLoanId").value = loanId;
    document.getElementById("modalLoanId").textContent = `Loan Application #${app.id}`;
    const statusClass = STATUS_BADGES[app.status] || "bg-slate-800 text-slate-300";
    const badgeEl     = document.getElementById("modalLoanStatusBadge");
    badgeEl.textContent = app.status;
    badgeEl.className   = `px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${statusClass}`;

    document.getElementById("modalApplicantSub").textContent = `${app.applicant_name} • ${app.applicant_email || "No email"} • ${app.applicant_phone || "No phone"}`;
    document.getElementById("modalIncome").textContent       = `$${app.annual_income.toLocaleString()}`;
    document.getElementById("modalAmount").textContent       = `$${app.requested_amount.toLocaleString()}`;
    document.getElementById("modalTerm").textContent         = `${app.requested_term_months || 12} Mos`;
    document.getElementById("modalPurpose").textContent      = app.loan_purpose || "General";

    // AI Risk section
    const riskEl = document.getElementById("modalRiskScore");
    if (app.risk_score !== null) {
      riskEl.textContent = `${app.risk_score}/100`;
      riskEl.className   = `font-mono font-extrabold text-xs px-2.5 py-0.5 rounded-full ${
        app.risk_score > 60
          ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
          : app.risk_score > 40
            ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
            : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
      }`;
    } else {
      riskEl.textContent = "Pending Evaluation";
      riskEl.className   = "font-mono text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400";
    }
    document.getElementById("modalRiskReasoning").textContent = app.risk_reasoning || "No risk assessment is available.";

    // KYC Documents
    const docList = document.getElementById("modalDocumentsList");
    const docs    = app.documents || [];
    document.getElementById("modalDocCount").textContent = `${docs.length} attached`;
    docList.innerHTML = docs.length === 0
      ? `<div class="text-slate-500 font-mono text-[11px] py-1">No KYC or financial proofs attached yet.</div>`
      : docs.map(d => `
          <div class="glass-card p-2.5 rounded-xl flex items-center justify-between gap-3 text-[11px]">
            <div class="flex items-center gap-2 overflow-hidden">
              <span class="px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-sky-300 font-mono text-[10px] uppercase">${escapeHTML(d.document_type)}</span>
              <span class="text-white font-medium truncate">${escapeHTML(d.file_name)}</span>
              <span class="text-slate-500 font-mono text-[10px]">(${Math.round(d.file_size_bytes / 1024)} KB)</span>
            </div>
            <div class="flex items-center gap-1.5 flex-shrink-0">
              <button onclick="downloadDocument(${d.id})" class="px-2 py-1 rounded bg-sky-500/20 hover:bg-sky-500/35 text-sky-300 border border-sky-500/30 text-[10px] font-semibold transition">Download</button>
              ${hasWriteAccess() ? `<button onclick="handleDeleteDocument(${d.id}, ${app.id})" class="px-2 py-1 rounded bg-rose-500/20 hover:bg-rose-500/35 text-rose-300 border border-rose-500/30 text-[10px] font-semibold transition">Delete</button>` : ""}
            </div>
          </div>
        `).join("");

    // Audit Trail Timeline
    const timeline = document.getElementById("modalAuditTimeline");
    const logs     = app.audit_log || [];
    timeline.innerHTML = logs.length === 0
      ? `<div class="text-slate-500 text-[11px]">No audit logs recorded.</div>`
      : logs.map(a => `
          <div class="relative pb-2">
            <div class="flex items-center gap-2 font-mono text-[10px] text-slate-400">
              <span class="font-bold text-white uppercase">${escapeHTML(a.action)}</span>
              <span>•</span>
              <span>${new Date(a.timestamp).toLocaleString()}</span>
            </div>
            ${a.notes ? `<div class="text-[11px] text-slate-300 mt-0.5">${escapeHTML(a.notes)}</div>` : ""}
          </div>
        `).join("");

    // Modal Action Buttons
    const actBox = document.getElementById("modalActionButtons");
    actBox.innerHTML = "";
    if (hasWriteAccess() && (app.status === "PENDING" || app.status === "UNDER_REVIEW")) {
      actBox.innerHTML += `<button onclick="updateStatus(${app.id}, 'APPROVED'); closeLoanDetailModal();" class="px-3 py-1.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/35 text-emerald-300 border border-emerald-500/30 font-semibold text-xs">Approve</button>`;
      actBox.innerHTML += `<button onclick="updateStatus(${app.id}, 'REJECTED'); closeLoanDetailModal();" class="px-3 py-1.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/35 text-rose-300 border border-rose-500/30 font-semibold text-xs">Reject</button>`;
    }
    if (hasWriteAccess() && app.status === "APPROVED") {
      actBox.innerHTML += `<button onclick="closeLoanDetailModal(); openDisburseModal(${app.id}, ${app.requested_amount});" class="px-4 py-1.5 rounded-xl glass-btn-primary text-white font-bold text-xs">Disburse Capital</button>`;
    }

    document.getElementById("loanDetailModal").classList.remove("hidden");
  } catch (err) {
    showToast("Error loading loan details: " + err.message, "error");
  }
}

function closeLoanDetailModal() {
  document.getElementById("loanDetailModal").classList.add("hidden");
}

async function handleDocumentUpload(e) {
  e.preventDefault();
  const loanId    = document.getElementById("docUploadLoanId").value;
  const docType   = document.getElementById("docUploadType").value;
  const fileInput = document.getElementById("docUploadFile");
  if (!fileInput.files || fileInput.files.length === 0) return;

  const formData = new FormData();
  formData.append("document_type", docType);
  formData.append("file", fileInput.files[0]);

  try {
    const res = await apiFetch(`/applications/${loanId}/documents`, { method: "POST", body: formData });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Upload failed"); }
    fileInput.value = "";
    showToast("Document uploaded successfully", "success");
    openLoanDetailModal(loanId);
  } catch (err) {
    showToast("Upload error: " + err.message, "error");
  }
}

async function downloadDocument(documentId) {
  try {
    const res = await apiFetch(`/documents/${documentId}/download`);
    if (!res.ok) throw new Error("Could not download document");
    const objectUrl = URL.createObjectURL(await res.blob());
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = (match?.[1] || `loanpulse-document-${documentId}`).replace(/[^\w.\-]/g, "_");
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function handleDeleteDocument(docId, loanId) {
  if (!confirm("Delete this document? This cannot be undone.")) return;
  try {
    const res = await apiFetch(`/documents/${docId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Delete failed");
    showToast("Document deleted", "success");
    openLoanDetailModal(loanId);
  } catch (err) {
    showToast("Delete error: " + err.message, "error");
  }
}

// ── New Loan Application Form ──────────────────────────────────────────────
function updateLtiPreview() {
  const inc   = parseFloat(document.getElementById("formIncome").value) || 0;
  const amt   = parseFloat(document.getElementById("formAmount").value) || 0;
  const badge = document.getElementById("ltiPreviewBadge");
  if (inc <= 0 || amt <= 0) {
    badge.textContent = "—";
    badge.className   = "text-xs font-mono font-bold text-slate-500";
    return;
  }
  const ratio = (amt / inc) * 100;
  badge.textContent = `${ratio.toFixed(1)}%`;
  badge.className   = `text-xs font-mono font-bold ${ratio > LTI_REJECTION_THRESHOLD ? "text-rose-400" : ratio > LTI_REVIEW_THRESHOLD ? "text-amber-400" : "text-emerald-400"}`;
}

async function handleNewApplication(e) {
  e.preventDefault();
  const form     = e.target;
  if (form.dataset.submitting === "true") return;
  form.dataset.submitting = "true";
  const submitButton = form.querySelector('button[type="submit"]');
  const submitLabel = submitButton?.textContent;
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "Submitting…";
  }
  const formData = new FormData(form);
  const payload  = {
    applicant_name:        formData.get("applicant_name"),
    applicant_email:       formData.get("applicant_email")       || null,
    applicant_phone:       formData.get("applicant_phone")       || null,
    employment_type:       formData.get("employment_type")       || null,
    annual_income:         parseFloat(formData.get("annual_income")),
    requested_amount:      parseFloat(formData.get("requested_amount")),
    requested_term_months: parseInt(formData.get("requested_term_months")) || 12,
    loan_purpose:          formData.get("loan_purpose")          || null,
  };

  try {
    const res  = await apiFetch("/applications/", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error submitting application");

    // Upload initial document if attached
    const initialFile    = document.getElementById("initialDocFile")?.files?.[0];
    const initialDocType = document.getElementById("initialDocType")?.value || "ID_PROOF";
    if (initialFile) {
      const docFormData = new FormData();
      docFormData.append("document_type", initialDocType);
      docFormData.append("file", initialFile);
      try {
        const docRes = await apiFetch(`/applications/${data.id}/documents`, { method: "POST", body: docFormData });
        if (!docRes.ok) {
          const docError = await docRes.json();
          throw new Error(docError.detail || "Document upload failed.");
        }
      } catch (docErr) {
        showToast(`Application submitted, but the document could not be uploaded: ${docErr.message}`, "warn", 7000);
      }
    }

    if (currentUser?.role === "CUSTOMER") openBorrowerFeedback(data);
    showToast(`Application #${data.id} submitted.`, "success", 5000);
    form.reset();
    if (currentUser?.role === "CUSTOMER") {
      form.elements.applicant_name.value = currentUser.full_name;
      form.elements.applicant_email.value = currentUser.email;
    }
    updateLtiPreview();
    switchTab(currentUser?.role === "CUSTOMER" ? "borrower" : "applications");
  } catch (err) {
    showToast("Submission error: " + err.message, "error");
  } finally {
    delete form.dataset.submitting;
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = submitLabel;
    }
  }
}

// ── Disbursement Modal ─────────────────────────────────────────────────────
function openDisburseModal(loanId, amount) {
  document.getElementById("disburseLoanId").value        = loanId;
  document.getElementById("disburseAmount").value        = amount;
  document.getElementById("disburseDate").value          = new Date().toISOString().split("T")[0];
  document.getElementById("disburseLoanSubtitle").textContent = `Disbursing Loan Application #${loanId}`;
  document.getElementById("disburseModal").classList.remove("hidden");
}

function closeDisburseModal() {
  document.getElementById("disburseModal").classList.add("hidden");
}

async function handleDisburseSubmit(e) {
  e.preventDefault();
  const form     = e.target;
  const formData = new FormData(form);
  const payload  = {
    loan_id:           parseInt(formData.get("loan_id")),
    disbursed_amount:  parseFloat(formData.get("disbursed_amount")),
    interest_rate:     parseFloat(formData.get("interest_rate")),
    disbursement_date: formData.get("disbursement_date"),
    payment_method:    formData.get("payment_method"),
    bank_reference:    formData.get("bank_reference") || null,
  };

  try {
    const res  = await apiFetch("/disbursements/", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Disbursement failed");

    showToast(`Loan #${payload.loan_id} disbursed — amortization schedule generated.`, "success", 6000);
    closeDisburseModal();
    loadApplications();
  } catch (err) {
    showToast("Disbursement error: " + err.message, "error");
  }
}

// ── Repayments ─────────────────────────────────────────────────────────────
async function loadRepaymentLoans() {
  try {
    const res      = await apiFetch("/applications/?limit=100");
    const data     = await res.json();
    const select   = document.getElementById("repaymentLoanSelect");
    const disbursed = data.filter(d => ["DISBURSED","ACTIVE","CLOSED","DEFAULTED"].includes(d.status));

    select.innerHTML = '<option value="">Select a Disbursed Loan...</option>' + disbursed.map(d =>
      `<option value="${d.id}">#${d.id} — ${escapeHTML(d.applicant_name)} ($${d.requested_amount.toLocaleString()}) [${escapeHTML(d.status)}]</option>`
    ).join("");
  } catch (e) {
    console.error("Error loading loans for repayment:", e);
  }
}

async function loadRepaymentSchedule(loanId) {
  currentRepaymentLoanId = loanId || null;
  const exportBtn = document.getElementById("exportCsvBtn");
  if (exportBtn) exportBtn.disabled = !loanId;

  const card  = document.getElementById("repaymentSummaryCard");
  const tbody = document.getElementById("repaymentsTableBody");

  if (!loanId) {
    card.style.display = "none";
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-slate-500">Select a loan above to view schedule</td></tr>`;
    return;
  }

  try {
    const res  = await apiFetch(`/repayments/${loanId}`);
    if (!res.ok) throw new Error("Could not load repayments");
    const data = await res.json();

    card.style.display = "grid";
    document.getElementById("repTotalEmi").textContent    = `$${data.total_emi.toLocaleString()}`;
    document.getElementById("repTotalPaid").textContent   = `$${data.total_paid.toLocaleString()}`;
    document.getElementById("repOutstanding").textContent = `$${data.outstanding_balance.toLocaleString()}`;
    document.getElementById("repOverdueCount").textContent = data.overdue_count;

    if (data.schedule.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-slate-500">No installments found</td></tr>`;
      return;
    }

    tbody.innerHTML = data.schedule.map(s => {
      const statusClass = STATUS_BADGES[s.status] || "bg-slate-800 text-slate-400";
      const payBtn = hasWriteAccess() && s.status !== "PAID"
        ? `<button onclick="payInstallment(${loanId}, ${s.id}, ${s.emi_amount})" class="px-2.5 py-1 rounded-lg bg-emerald-500/25 hover:bg-emerald-500/40 text-emerald-200 border border-emerald-400/30 backdrop-blur-md font-semibold text-[10px] shadow-sm transition">Record Pay</button>`
        : s.status === "PAID"
          ? `<span class="text-emerald-400 text-[10px] font-mono">Paid ${s.paid_date || ""}</span>`
          : `<span class="text-slate-500 text-[10px] font-mono">${escapeHTML(s.status)}</span>`;

      return `
        <tr class="hover:bg-white/[0.04] transition border-b border-white/[0.04]">
          <td class="py-2.5 px-3 text-slate-400 font-mono">#${s.installment_number}</td>
          <td class="py-2.5 px-3 font-semibold text-white">${s.due_date}</td>
          <td class="py-2.5 px-3 font-bold text-white font-mono">$${s.emi_amount.toLocaleString()}</td>
          <td class="py-2.5 px-3 text-slate-400 font-mono">$${s.principal_component.toLocaleString()}</td>
          <td class="py-2.5 px-3 text-slate-400 font-mono">$${s.interest_component.toLocaleString()}</td>
          <td class="py-2.5 px-3 font-mono ${s.penalty_amount > 0 ? "text-rose-400 font-bold" : "text-slate-500"}">${s.penalty_amount > 0 ? `$${s.penalty_amount}` : "$0"}</td>
          <td class="py-2.5 px-3">
            <span class="px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${statusClass}">${escapeHTML(s.status)}</span>
          </td>
          <td class="py-2.5 px-3 text-right">${payBtn}</td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    showToast("Error loading schedule: " + e.message, "error");
  }
}

async function payInstallment(loanId, installmentId, amount) {
  if (!confirm(`Record payment of $${amount.toFixed(2)} for this installment?`)) return;

  try {
    const res = await apiFetch(`/repayments/${loanId}/pay/${installmentId}`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ paid_amount: amount }),
    });
    if (!res.ok) throw new Error("Payment failed");
    showToast("Payment recorded successfully", "success");
    loadRepaymentSchedule(loanId);
  } catch (e) {
    showToast("Payment error: " + e.message, "error");
  }
}

async function exportRepaymentCsv() {
  if (!currentRepaymentLoanId) {
    showToast("Please select a loan first", "warn");
    return;
  }
  try {
    const res = await apiFetch(`/repayments/${currentRepaymentLoanId}/export-csv`);
    if (!res.ok) throw new Error("Could not export CSV");
    const blob = await res.blob();
    const url  = window.URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `loan_${currentRepaymentLoanId}_amortization.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    showToast("CSV export downloaded", "success");
  } catch (e) {
    showToast("CSV Export error: " + e.message, "error");
  }
}

async function triggerOverdueCheck() {
  try {
    const res  = await apiFetch("/repayments/batch/trigger-overdue-check", { method: "POST" });
    const data = await res.json();
    showToast(
      `Overdue scan complete — ${data.overdue_check.marked_overdue} installment(s) updated.`,
      "info",
      7000
    );
    refreshCurrentTab();
  } catch (e) {
    showToast("Batch check failed: " + e.message, "error");
  }
}

// ── Notifications ──────────────────────────────────────────────────────────
async function loadNotifications() {
  try {
    const res       = await apiFetch("/notifications/?limit=30");
    const data      = await res.json();
    const container = document.getElementById("notificationsList");

    if (data.length === 0) {
      container.innerHTML = `<div class="text-center py-8 text-slate-500 font-mono text-xs">No notifications recorded yet</div>`;
      return;
    }

    container.innerHTML = data.map(n => `
      <div class="glass-card p-4 rounded-2xl flex items-start justify-between gap-4">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-300 border border-purple-500/30 font-bold backdrop-blur-md">${escapeHTML(n.event)}</span>
            <span class="text-xs font-semibold text-white">${escapeHTML(n.subject)}</span>
          </div>
          <p class="text-xs text-slate-300 whitespace-pre-line leading-relaxed">${escapeHTML(n.body)}</p>
          <div class="text-[10px] text-slate-400 mt-2 font-mono">To: ${escapeHTML(n.recipient_email)} • ${new Date(n.created_at).toLocaleString()}</div>
        </div>
        ${!n.read_at
          ? `<button onclick="markNotificationRead(${n.id})" class="glass-btn-subtle text-slate-300 hover:text-white px-2.5 py-1.5 rounded-xl text-[10px] whitespace-nowrap transition">Mark read</button>`
          : '<span class="text-[10px] text-slate-500 font-mono">Read</span>'}
      </div>
    `).join("");
  } catch (e) {
    console.error("Notifications error:", e);
  }
}

async function loadNotificationsCount() {
  try {
    const res   = await apiFetch("/notifications/unread-count");
    const data  = await res.json();
    const count = data.unread_count || 0;

    const deskBadge = document.getElementById("unreadBadge");
    if (deskBadge) deskBadge.textContent = count;

    const mobDot = document.getElementById("mobUnreadDot");
    if (mobDot) mobDot.classList.toggle("hidden", count === 0);
  } catch (e) { /* silent */ }
}

async function markNotificationRead(id) {
  try {
    await apiFetch(`/notifications/${id}/read`, { method: "PATCH" });
    loadNotifications();
    loadNotificationsCount();
  } catch (e) { /* silent */ }
}

// ── Bootstrap ──────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => { checkAuth(); });
