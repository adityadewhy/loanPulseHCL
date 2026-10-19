// LoanPulse LoanMaster Frontend Single Page Application
let token = localStorage.getItem("loanpulse_token") || "";
let currentUser = null;
let currentTab = "dashboard";
let currentRepaymentLoanId = null;

const STATUS_BADGES = {
  PENDING: "bg-amber-500/15 text-amber-300 border border-amber-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(245,158,11,0.15)]",
  UNDER_REVIEW: "bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(99,102,241,0.15)]",
  APPROVED: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(16,185,129,0.15)]",
  REJECTED: "bg-rose-500/15 text-rose-300 border border-rose-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(244,63,94,0.15)]",
  DISBURSED: "bg-purple-500/15 text-purple-300 border border-purple-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(168,85,247,0.15)]",
  ACTIVE: "bg-sky-500/15 text-sky-300 border border-sky-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(14,165,233,0.15)]",
  CLOSED: "bg-slate-500/15 text-slate-300 border border-slate-500/30 backdrop-blur-md",
  DEFAULTED: "bg-red-950/40 text-red-300 border border-red-500/40 backdrop-blur-md shadow-[0_0_12px_rgba(239,68,68,0.2)]",
  PAID: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 backdrop-blur-md shadow-[0_0_12px_rgba(16,185,129,0.15)]",
  OVERDUE: "bg-rose-500/20 text-rose-300 border border-rose-500/40 backdrop-blur-md shadow-[0_0_12px_rgba(244,63,94,0.25)]",
};

// --- AUTH ---
async function apiFetch(endpoint, options = {}) {
  options.headers = options.headers || {};
  if (token) {
    options.headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(endpoint, options);
  if (res.status === 401) {
    handleLogout();
    throw new Error("Unauthorized");
  }
  return res;
}

async function handleLogin() {
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value.trim();
  const errBox = document.getElementById("authError");
  errBox.classList.add("hidden");

  const formData = new URLSearchParams();
  formData.append("username", email);
  formData.append("password", password);

  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");

    token = data.access_token;
    localStorage.setItem("loanpulse_token", token);
    document.getElementById("authModal").classList.add("hidden");
    await checkAuth();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
}

function handleLogout() {
  token = "";
  localStorage.removeItem("loanpulse_token");
  currentUser = null;
  document.getElementById("authModal").classList.remove("hidden");
}

async function checkAuth() {
  if (!token) {
    document.getElementById("authModal").classList.remove("hidden");
    return;
  }
  try {
    const res = await apiFetch("/auth/me");
    if (!res.ok) throw new Error("Auth failed");
    currentUser = await res.json();
    document.getElementById("authModal").classList.add("hidden");
    
    // Set user badge in sidebar
    const nameEl = document.getElementById("userName");
    const roleEl = document.getElementById("userRole");
    const avatarEl = document.getElementById("userAvatar");
    if (nameEl) nameEl.textContent = currentUser.full_name;
    if (roleEl) roleEl.textContent = currentUser.role;
    if (avatarEl) avatarEl.textContent = currentUser.full_name.substring(0, 2).toUpperCase();
    
    // Initial data load
    switchTab(currentTab);
    loadNotificationsCount();
  } catch (e) {
    handleLogout();
  }
}

// --- TABS & RESPONSIVE NAVIGATION ---
function switchTab(tabId) {
  currentTab = tabId;
  const tabs = ["dashboard", "applications", "new-application", "repayments", "notifications"];
  
  tabs.forEach(t => {
    const view = document.getElementById(`view-${t}`);
    const nav = document.getElementById(`nav-${t}`);
    const mob = document.getElementById(`mob-${t}`);

    if (t === tabId) {
      if (view) view.classList.remove("hidden");
      
      // Desktop nav active styling
      if (nav) {
        nav.classList.add("glass-card", "border-white/20", "text-white", "shadow-lg");
        nav.classList.remove("text-slate-400", "hover:bg-white/5");
      }
      
      // Mobile bottom dock active styling
      if (mob) {
        mob.classList.add("text-sky-400", "scale-105");
        mob.classList.remove("text-slate-400");
      }
    } else {
      if (view) view.classList.add("hidden");
      
      // Desktop nav inactive styling
      if (nav) {
        nav.classList.remove("glass-card", "border-white/20", "text-white", "shadow-lg");
        nav.classList.add("text-slate-400", "hover:bg-white/5");
      }
      
      // Mobile bottom dock inactive styling
      if (mob) {
        mob.classList.remove("text-sky-400", "scale-105");
        mob.classList.add("text-slate-400");
      }
    }
  });

  const titles = {
    dashboard: ["Portfolio Dashboard", "Real-time credit portfolio performance and risk metrics"],
    applications: ["Loan Applications", "Origination pipeline, AI risk scoring, and officer decisions"],
    "new-application": ["New Loan Application", "Submit new applicant details directly to async risk pipeline"],
    repayments: ["Repayment Tracking", "Amortization schedules, monthly installment servicing, and arrears"],
    notifications: ["Notifications Audit", "Dispatched email and in-app alert log"],
  };

  const titleEl = document.getElementById("viewTitle");
  const subEl = document.getElementById("viewSubtitle");
  if (titleEl && titles[tabId]) titleEl.textContent = titles[tabId][0];
  if (subEl && titles[tabId]) subEl.textContent = titles[tabId][1];

  if (tabId === "dashboard") loadDashboard();
  if (tabId === "applications") loadApplications();
  if (tabId === "repayments") loadRepaymentLoans();
  if (tabId === "notifications") loadNotifications();
}

function refreshCurrentTab() {
  switchTab(currentTab);
}

// --- DASHBOARD ---
async function loadDashboard() {
  try {
    const res = await apiFetch("/dashboard/kpis");
    const data = await res.json();

    document.getElementById("kpiTotalApps").textContent = data.total_applications;
    document.getElementById("kpiDisbursed").textContent = `$${data.total_disbursed_amount.toLocaleString()}`;
    document.getElementById("kpiOverdue").textContent = data.total_overdue_installments;
    document.getElementById("kpiCollection").textContent = `${data.collection_rate}%`;

    const stats = [
      { label: "Pending Review", count: data.pending, color: "text-amber-400" },
      { label: "Under AI Review", count: data.under_review, color: "text-indigo-400" },
      { label: "Approved", count: data.approved, color: "text-emerald-400" },
      { label: "Disbursed / Active", count: data.disbursed + data.active, color: "text-purple-400" },
      { label: "Rejected", count: data.rejected, color: "text-rose-400" },
      { label: "Closed / Paid Off", count: data.closed, color: "text-slate-400" },
      { label: "In Default", count: data.defaulted, color: "text-red-500" },
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

// --- APPLICATIONS ---
async function loadApplications() {
  const search = document.getElementById("appSearchInput")?.value || "";
  const statusFilter = document.getElementById("appStatusFilter")?.value || "";

  let url = `/applications/?limit=50`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  if (statusFilter) url += `&status=${encodeURIComponent(statusFilter)}`;

  try {
    const res = await apiFetch(url);
    const data = await res.json();
    const tbody = document.getElementById("applicationsTableBody");

    if (data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-8 text-slate-500 font-mono">No loan applications found</td></tr>`;
      return;
    }

    tbody.innerHTML = data.map(app => {
      const dti = ((app.requested_amount / app.annual_income) * 100).toFixed(1);
      const statusClass = STATUS_BADGES[app.status] || "bg-slate-800 text-slate-300";

      let actionButtons = `<button onclick="event.stopPropagation(); openLoanDetailModal(${app.id})" class="px-2.5 py-1 rounded-lg bg-sky-500/20 hover:bg-sky-500/35 text-sky-300 border border-sky-500/30 backdrop-blur-md text-[10px] font-semibold mr-1 transition shadow-sm">Details</button>`;
      
      if (app.status === "PENDING" || app.status === "UNDER_REVIEW") {
        actionButtons += `<button onclick="event.stopPropagation(); updateStatus(${app.id}, 'APPROVED')" class="px-2.5 py-1 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/35 text-emerald-300 border border-emerald-500/30 backdrop-blur-md text-[10px] font-semibold mr-1 transition shadow-sm">Approve</button>`;
        actionButtons += `<button onclick="event.stopPropagation(); updateStatus(${app.id}, 'REJECTED')" class="px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/35 text-rose-300 border border-rose-500/30 backdrop-blur-md text-[10px] font-semibold mr-1 transition shadow-sm">Reject</button>`;
      }
      if (app.status === "APPROVED") {
        actionButtons += `<button onclick="event.stopPropagation(); openDisburseModal(${app.id}, ${app.requested_amount})" class="px-3 py-1 rounded-lg glass-btn-primary text-white font-bold text-[10px] shadow-sm">Disburse</button>`;
      }

      return `
        <tr onclick="openLoanDetailModal(${app.id})" class="hover:bg-white/[0.04] transition border-b border-white/[0.04] cursor-pointer">
          <td class="py-3 px-4 font-mono text-slate-400">#${app.id}</td>
          <td class="py-3 px-4">
            <div class="font-bold text-white">${app.applicant_name}</div>
            <div class="text-[10px] text-slate-400">${app.applicant_email || "no email"}</div>
          </td>
          <td class="py-3 px-4 font-mono text-slate-300">$${app.annual_income.toLocaleString()}</td>
          <td class="py-3 px-4 font-mono text-white font-semibold">$${app.requested_amount.toLocaleString()}</td>
          <td class="py-3 px-4 font-mono ${dti > 60 ? 'text-rose-400 font-bold' : dti > 40 ? 'text-amber-400' : 'text-emerald-400'}">${dti}%</td>
          <td class="py-3 px-4">
            <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${statusClass}">${app.status}</span>
          </td>
          <td class="py-3 px-4 font-mono">
            ${app.risk_score !== null ? `<span class="font-bold ${app.risk_score > 60 ? 'text-rose-400' : 'text-emerald-400'}">${app.risk_score}/100</span>` : '<span class="text-slate-500">—</span>'}
          </td>
          <td class="py-3 px-4 text-right whitespace-nowrap">
            ${actionButtons}
          </td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    console.error("Applications load error:", e);
  }
}

async function updateStatus(appId, newStatus) {
  try {
    const res = await apiFetch(`/applications/${appId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) throw new Error("Failed to update status");
    loadApplications();
  } catch (e) {
    alert("Error updating status: " + e.message);
  }
}

// --- LOAN APPLICATION DETAIL & AUDIT MODAL ---
async function openLoanDetailModal(loanId) {
  try {
    const res = await apiFetch(`/applications/${loanId}/details`);
    if (!res.ok) throw new Error("Could not load application details");
    const app = await res.json();

    document.getElementById("docUploadLoanId").value = loanId;
    document.getElementById("modalLoanId").textContent = `Loan Application #${app.id}`;
    const statusClass = STATUS_BADGES[app.status] || "bg-slate-800 text-slate-300";
    const badgeEl = document.getElementById("modalLoanStatusBadge");
    badgeEl.textContent = app.status;
    badgeEl.className = `px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${statusClass}`;

    document.getElementById("modalApplicantSub").textContent = `${app.applicant_name} • ${app.applicant_email || 'No email'} • ${app.applicant_phone || 'No phone'}`;
    document.getElementById("modalIncome").textContent = `$${app.annual_income.toLocaleString()}`;
    document.getElementById("modalAmount").textContent = `$${app.requested_amount.toLocaleString()}`;
    document.getElementById("modalTerm").textContent = `${app.requested_term_months || 12} Mos`;
    document.getElementById("modalPurpose").textContent = app.loan_purpose || "General";

    // AI Risk
    const riskEl = document.getElementById("modalRiskScore");
    if (app.risk_score !== null) {
      riskEl.textContent = `${app.risk_score}/100`;
      riskEl.className = `font-mono font-extrabold text-xs px-2.5 py-0.5 rounded-full ${app.risk_score > 60 ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : app.risk_score > 40 ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'}`;
    } else {
      riskEl.textContent = "Pending Evaluation";
      riskEl.className = "font-mono text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400";
    }
    document.getElementById("modalRiskReasoning").textContent = app.risk_reasoning || "Autonomous evaluation memo in progress or deterministic rules applied.";

    // KYC Documents
    const docList = document.getElementById("modalDocumentsList");
    const docs = app.documents || [];
    document.getElementById("modalDocCount").textContent = `${docs.length} attached`;
    if (docs.length === 0) {
      docList.innerHTML = `<div class="text-slate-500 font-mono text-[11px] py-1">No KYC or financial proofs attached yet.</div>`;
    } else {
      docList.innerHTML = docs.map(d => `
        <div class="glass-card p-2.5 rounded-xl flex items-center justify-between gap-3 text-[11px]">
          <div class="flex items-center gap-2 overflow-hidden">
            <span class="px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-sky-300 font-mono text-[10px] uppercase">${d.document_type}</span>
            <span class="text-white font-medium truncate">${d.file_name}</span>
            <span class="text-slate-500 font-mono text-[10px]">(${Math.round(d.file_size_bytes / 1024)} KB)</span>
          </div>
          <div class="flex items-center gap-1.5 flex-shrink-0">
            <a href="/documents/${d.id}/download" target="_blank" class="px-2 py-1 rounded bg-sky-500/20 hover:bg-sky-500/35 text-sky-300 border border-sky-500/30 text-[10px] font-semibold transition">View</a>
            <button onclick="handleDeleteDocument(${d.id}, ${app.id})" class="px-2 py-1 rounded bg-rose-500/20 hover:bg-rose-500/35 text-rose-300 border border-rose-500/30 text-[10px] font-semibold transition">Delete</button>
          </div>
        </div>
      `).join("");
    }

    // Audit Trail Timeline
    const timeline = document.getElementById("modalAuditTimeline");
    const logs = app.audit_log || [];
    if (logs.length === 0) {
      timeline.innerHTML = `<div class="text-slate-500 text-[11px]">No audit logs recorded.</div>`;
    } else {
      timeline.innerHTML = logs.map(a => `
        <div class="relative pb-2">
          <div class="flex items-center gap-2 font-mono text-[10px] text-slate-400">
            <span class="font-bold text-white uppercase">${a.action}</span>
            <span>•</span>
            <span>${new Date(a.timestamp).toLocaleString()}</span>
          </div>
          ${a.notes ? `<div class="text-[11px] text-slate-300 mt-0.5">${a.notes}</div>` : ''}
        </div>
      `).join("");
    }

    // Action Buttons in Footer
    const actBox = document.getElementById("modalActionButtons");
    actBox.innerHTML = "";
    if (app.status === "PENDING" || app.status === "UNDER_REVIEW") {
      actBox.innerHTML += `<button onclick="updateStatus(${app.id}, 'APPROVED'); closeLoanDetailModal();" class="px-3 py-1.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/35 text-emerald-300 border border-emerald-500/30 font-semibold text-xs">Approve</button>`;
      actBox.innerHTML += `<button onclick="updateStatus(${app.id}, 'REJECTED'); closeLoanDetailModal();" class="px-3 py-1.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/35 text-rose-300 border border-rose-500/30 font-semibold text-xs">Reject</button>`;
    }
    if (app.status === "APPROVED") {
      actBox.innerHTML += `<button onclick="closeLoanDetailModal(); openDisburseModal(${app.id}, ${app.requested_amount});" class="px-4 py-1.5 rounded-xl glass-btn-primary text-white font-bold text-xs">Disburse Capital</button>`;
    }

    document.getElementById("loanDetailModal").classList.remove("hidden");
  } catch (err) {
    alert("Error viewing loan details: " + err.message);
  }
}

function closeLoanDetailModal() {
  document.getElementById("loanDetailModal").classList.add("hidden");
}

async function handleDocumentUpload(e) {
  e.preventDefault();
  const loanId = document.getElementById("docUploadLoanId").value;
  const docType = document.getElementById("docUploadType").value;
  const fileInput = document.getElementById("docUploadFile");
  if (!fileInput.files || fileInput.files.length === 0) return;

  const formData = new FormData();
  formData.append("document_type", docType);
  formData.append("file", fileInput.files[0]);

  try {
    const res = await apiFetch(`/applications/${loanId}/documents`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Upload failed");
    }
    fileInput.value = "";
    openLoanDetailModal(loanId);
  } catch (err) {
    alert("Upload error: " + err.message);
  }
}

async function handleDeleteDocument(docId, loanId) {
  if (!confirm("Are you sure you want to delete this document?")) return;
  try {
    const res = await apiFetch(`/documents/${docId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Delete failed");
    openLoanDetailModal(loanId);
  } catch (err) {
    alert("Delete error: " + err.message);
  }
}

// --- NEW LOAN FORM ---
function updateDtiPreview() {
  const inc = parseFloat(document.getElementById("formIncome").value) || 0;
  const amt = parseFloat(document.getElementById("formAmount").value) || 0;
  const badge = document.getElementById("dtiPreviewBadge");
  if (inc <= 0 || amt <= 0) {
    badge.textContent = "—";
    badge.className = "text-xs font-mono font-bold text-slate-500";
    return;
  }
  const ratio = (amt / inc) * 100;
  badge.textContent = `${ratio.toFixed(1)}%`;
  if (ratio > 60) {
    badge.className = "text-xs font-mono font-bold text-rose-400";
  } else if (ratio > 40) {
    badge.className = "text-xs font-mono font-bold text-amber-400";
  } else {
    badge.className = "text-xs font-mono font-bold text-emerald-400";
  }
}

async function handleNewApplication(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  const payload = {
    applicant_name: formData.get("applicant_name"),
    applicant_email: formData.get("applicant_email") || null,
    applicant_phone: formData.get("applicant_phone") || null,
    employment_type: formData.get("employment_type") || null,
    annual_income: parseFloat(formData.get("annual_income")),
    requested_amount: parseFloat(formData.get("requested_amount")),
    requested_term_months: parseInt(formData.get("requested_term_months")) || 12,
    loan_purpose: formData.get("loan_purpose") || null,
  };

  try {
    const res = await apiFetch("/applications/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error submitting application");

    // Upload initial document if attached
    const initialFile = document.getElementById("initialDocFile")?.files?.[0];
    const initialDocType = document.getElementById("initialDocType")?.value || "ID_PROOF";
    if (initialFile) {
      const docFormData = new FormData();
      docFormData.append("document_type", initialDocType);
      docFormData.append("file", initialFile);
      try {
        await apiFetch(`/applications/${data.id}/documents`, {
          method: "POST",
          body: docFormData,
        });
      } catch (docErr) {
        console.warn("Initial document upload error:", docErr);
      }
    }

    alert(`Application #${data.id} submitted! AI risk evaluation dispatched in background.`);
    form.reset();
    updateDtiPreview();
    switchTab("applications");
  } catch (err) {
    alert("Submission error: " + err.message);
  }
}

// --- DISBURSE MODAL ---
function openDisburseModal(loanId, amount) {
  document.getElementById("disburseLoanId").value = loanId;
  document.getElementById("disburseAmount").value = amount;
  document.getElementById("disburseDate").value = new Date().toISOString().split("T")[0];
  document.getElementById("disburseLoanSubtitle").textContent = `Disbursing Loan Application #${loanId}`;
  document.getElementById("disburseModal").classList.remove("hidden");
}

function closeDisburseModal() {
  document.getElementById("disburseModal").classList.add("hidden");
}

async function handleDisburseSubmit(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  const payload = {
    loan_id: parseInt(formData.get("loan_id")),
    disbursed_amount: parseFloat(formData.get("disbursed_amount")),
    interest_rate: parseFloat(formData.get("interest_rate")),
    disbursement_date: formData.get("disbursement_date"),
    payment_method: formData.get("payment_method"),
    bank_reference: formData.get("bank_reference") || null,
  };

  try {
    const res = await apiFetch("/disbursements/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Disbursement failed");

    alert(`Loan #${payload.loan_id} disbursed! Amortization schedule generated.`);
    closeDisburseModal();
    loadApplications();
  } catch (err) {
    alert("Disbursement error: " + err.message);
  }
}

// --- REPAYMENTS ---
async function loadRepaymentLoans() {
  try {
    const res = await apiFetch("/applications/?limit=100");
    const data = await res.json();
    const select = document.getElementById("repaymentLoanSelect");
    const disbursed = data.filter(d => ["DISBURSED", "ACTIVE", "CLOSED", "DEFAULTED"].includes(d.status));

    select.innerHTML = '<option value="">Select a Disbursed Loan...</option>' + disbursed.map(d =>
      `<option value="${d.id}">#${d.id} — ${d.applicant_name} ($${d.requested_amount.toLocaleString()}) [${d.status}]</option>`
    ).join("");
  } catch (e) {
    console.error("Error loading loans for repayment:", e);
  }
}

async function loadRepaymentSchedule(loanId) {
  currentRepaymentLoanId = loanId || null;
  const exportBtn = document.getElementById("exportCsvBtn");
  if (exportBtn) exportBtn.disabled = !loanId;

  const card = document.getElementById("repaymentSummaryCard");
  const tbody = document.getElementById("repaymentsTableBody");
  if (!loanId) {
    card.classList.add("hidden");
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-slate-500">Select a loan above to view schedule</td></tr>`;
    return;
  }

  try {
    const res = await apiFetch(`/repayments/${loanId}`);
    if (!res.ok) throw new Error("Could not load repayments");
    const data = await res.json();

    card.classList.remove("hidden");
    document.getElementById("repTotalEmi").textContent = `$${data.total_emi.toLocaleString()}`;
    document.getElementById("repTotalPaid").textContent = `$${data.total_paid.toLocaleString()}`;
    document.getElementById("repOutstanding").textContent = `$${data.outstanding_balance.toLocaleString()}`;
    document.getElementById("repOverdueCount").textContent = data.overdue_count;

    if (data.schedule.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-slate-500">No installments found</td></tr>`;
      return;
    }

    tbody.innerHTML = data.schedule.map(s => {
      const statusClass = STATUS_BADGES[s.status] || "bg-slate-800 text-slate-400";
      const payBtn = s.status !== "PAID"
        ? `<button onclick="payInstallment(${loanId}, ${s.id}, ${s.emi_amount})" class="px-2.5 py-1 rounded-lg bg-emerald-500/25 hover:bg-emerald-500/40 text-emerald-200 border border-emerald-400/30 backdrop-blur-md font-semibold text-[10px] shadow-sm transition">Record Pay</button>`
        : `<span class="text-emerald-400 text-[10px] font-mono">Paid ${s.paid_date || ''}</span>`;

      return `
        <tr class="hover:bg-white/[0.04] transition border-b border-white/[0.04]">
          <td class="py-2.5 px-3 text-slate-400 font-mono">#${s.installment_number}</td>
          <td class="py-2.5 px-3 font-semibold text-white">${s.due_date}</td>
          <td class="py-2.5 px-3 font-bold text-white font-mono">$${s.emi_amount.toLocaleString()}</td>
          <td class="py-2.5 px-3 text-slate-400 font-mono">$${s.principal_component.toLocaleString()}</td>
          <td class="py-2.5 px-3 text-slate-400 font-mono">$${s.interest_component.toLocaleString()}</td>
          <td class="py-2.5 px-3 font-mono ${s.penalty_amount > 0 ? 'text-rose-400 font-bold' : 'text-slate-500'}">${s.penalty_amount > 0 ? `$${s.penalty_amount}` : '$0'}</td>
          <td class="py-2.5 px-3">
            <span class="px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${statusClass}">${s.status}</span>
          </td>
          <td class="py-2.5 px-3 text-right">
            ${payBtn}
          </td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    alert("Error loading schedule: " + e.message);
  }
}

async function payInstallment(loanId, installmentId, amount) {
  const confirmPay = confirm(`Record payment of $${amount.toFixed(2)} for installment?`);
  if (!confirmPay) return;

  try {
    const res = await apiFetch(`/repayments/${loanId}/pay/${installmentId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paid_amount: amount }),
    });
    if (!res.ok) throw new Error("Payment failed");
    loadRepaymentSchedule(loanId);
  } catch (e) {
    alert("Payment error: " + e.message);
  }
}

async function exportRepaymentCsv() {
  if (!currentRepaymentLoanId) {
    alert("Please select a loan first");
    return;
  }
  try {
    const res = await apiFetch(`/repayments/${currentRepaymentLoanId}/export-csv`);
    if (!res.ok) throw new Error("Could not export CSV");
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `loan_${currentRepaymentLoanId}_amortization.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    alert("CSV Export error: " + e.message);
  }
}

async function triggerOverdueCheck() {
  try {
    const res = await apiFetch("/repayments/batch/trigger-overdue-check", { method: "POST" });
    const data = await res.json();
    alert(`Batch check completed!\nMarked Overdue: ${data.overdue_check.marked_overdue}\nReminders: ${data.upcoming_reminders.reminders_sent}`);
    refreshCurrentTab();
  } catch (e) {
    alert("Batch check failed: " + e.message);
  }
}

// --- NOTIFICATIONS ---
async function loadNotifications() {
  try {
    const res = await apiFetch("/notifications/?limit=30");
    const data = await res.json();
    const container = document.getElementById("notificationsList");

    if (data.length === 0) {
      container.innerHTML = `<div class="text-center py-8 text-slate-500 font-mono text-xs">No notifications recorded yet</div>`;
      return;
    }

    container.innerHTML = data.map(n => `
      <div class="glass-card p-4 rounded-2xl flex items-start justify-between gap-4">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-300 border border-purple-500/30 font-bold backdrop-blur-md">${n.event}</span>
            <span class="text-xs font-semibold text-white">${n.subject}</span>
          </div>
          <p class="text-xs text-slate-300 whitespace-pre-line leading-relaxed">${n.body}</p>
          <div class="text-[10px] text-slate-400 mt-2 font-mono">To: ${n.recipient_email} • ${new Date(n.created_at).toLocaleString()}</div>
        </div>
        ${!n.read_at ? `<button onclick="markNotificationRead(${n.id})" class="glass-btn-subtle text-slate-300 hover:text-white px-2.5 py-1.5 rounded-xl text-[10px] whitespace-nowrap transition">Mark read</button>` : '<span class="text-[10px] text-slate-500 font-mono">Read</span>'}
      </div>
    `).join("");
  } catch (e) {
    console.error("Notifications error:", e);
  }
}

async function loadNotificationsCount() {
  try {
    const res = await apiFetch("/notifications/unread-count");
    const data = await res.json();
    const count = data.unread_count || 0;
    
    // Desktop badge
    const deskBadge = document.getElementById("unreadBadge");
    if (deskBadge) deskBadge.textContent = count;
    
    // Mobile bottom dock dot
    const mobDot = document.getElementById("mobUnreadDot");
    if (mobDot) {
      if (count > 0) {
        mobDot.classList.remove("hidden");
      } else {
        mobDot.classList.add("hidden");
      }
    }
  } catch (e) {}
}

async function markNotificationRead(id) {
  try {
    await apiFetch(`/notifications/${id}/read`, { method: "PATCH" });
    loadNotifications();
    loadNotificationsCount();
  } catch (e) {}
}

// Boot
window.addEventListener("DOMContentLoaded", () => {
  checkAuth();
});
