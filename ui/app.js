/* ═══════════════════════════════════════════════════════════════════════
   LedgerLoop Controller UI — Application Logic
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
"use strict";

const API = "";
let _overview = null;
let _exceptions = null;
let _transactions = null;
let _selectedExc = null;
let _selectedTxn = null;
let _qaInited = false;
let _qaHist = [];
let _currentPanel = "overview";
let _txSort = { field: null, dir: "asc" };
let _txFilter = "ALL";

/* ── Helpers ─────────────────────────────────────────────── */

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function chip(status) {
  const m = {
    MATCH: "match", MATCHED: "match", PARTIAL_MATCH: "match",
    PARTIAL_PAYMENT: "review",
    HUMAN_REVIEW: "review", AI_RETRY_REQUIRED: "review",
    UNRESOLVED: "unresolved", UNRESOLVED_FOR_TIER_1: "unresolved",
    AMBIGUOUS: "review",
  };
  const c = m[status] || "neutral";
  return '<span class="chip chip-' + c + '">' + esc(status) + '</span>';
}

function statusDot(status) {
  const m = { MATCH: "match", MATCHED: "match", PARTIAL_MATCH: "match",
    PARTIAL_PAYMENT: "review", HUMAN_REVIEW: "review",
    AI_RETRY_REQUIRED: "review", UNRESOLVED: "unresolved",
    UNRESOLVED_FOR_TIER_1: "unresolved", AMBIGUOUS: "review" };
  const c = m[status] || "neutral";
  return '<span class="status-dot ' + c + '"></span>' + esc(status);
}

function tierChip(t) { return '<span class="chip chip-tier">' + esc(t) + '</span>'; }

function fmtMoney(v) {
  if (v == null || v === "") return "—";
  var n = typeof v === "string" ? parseFloat(v) : v;
  if (!isFinite(n)) return "—";
  return "₹" + n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function pct(v) { return (v == null || isNaN(v)) ? "0.0" : Number(v).toFixed(1); }

function errHtml(msg) { return '<div class="error-msg">Could not load data — ' + esc(msg) + '</div>'; }
function loadingHtml(msg) { return '<div class="loading">' + esc(msg || "Loading…") + '</div>'; }

/* ── Theme ───────────────────────────────────────────────── */

function initTheme() {
  var saved = localStorage.getItem("ll-theme");
  if (saved) {
    document.documentElement.setAttribute("data-theme", saved);
  } else {
    // Default to dark for the premium fintech aesthetic
    document.documentElement.setAttribute("data-theme", "dark");
    localStorage.setItem("ll-theme", "dark");
  }
  updateThemeBtn();
}

function toggleTheme() {
  var cur = document.documentElement.getAttribute("data-theme");
  var next;
  if (cur === "dark") next = "light";
  else next = "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("ll-theme", next);
  updateThemeBtn();
}

function updateThemeBtn() {
  var cur = document.documentElement.getAttribute("data-theme");
  var dark = cur === "dark" || (!cur && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.getElementById("theme-icon").textContent = dark ? "☀️" : "🌙";
  document.getElementById("theme-label").textContent = dark ? "Light" : "Dark";
}

document.addEventListener("DOMContentLoaded", function () {
  document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
  initTheme();
});

/* ── Navigation ──────────────────────────────────────────── */

function switchPanel(pid) {
  document.querySelectorAll(".nav-item").forEach(function (n) {
    n.classList.toggle("active", n.dataset.panel === pid);
  });
  document.querySelectorAll(".panel").forEach(function (p) {
    p.classList.toggle("active", p.id === "panel-" + pid);
  });
  _currentPanel = pid;
  if (pid === "overview" && !_overview) loadOverview();
  if (pid === "exceptions" && !_exceptions) loadExceptions();
  if (pid === "transactions" && !_transactions) loadTransactions();
  if (pid === "qa" && !_qaInited) initQA();
}

document.addEventListener("DOMContentLoaded", function () {
  document.getElementById("nav").addEventListener("click", function (e) {
    var btn = e.target.closest(".nav-item");
    if (!btn) return;
    switchPanel(btn.dataset.panel);
  });
});

/* ════════════════════════════════════════════════════════════
   Overview
   ════════════════════════════════════════════════════════════ */

async function loadOverview() {
  var el = document.getElementById("overview-content");
  try {
    var res = await fetch(API + "/api/overview");
    if (!res.ok) throw new Error(res.statusText);
    _overview = await res.json();
  } catch (err) {
    el.innerHTML = errHtml(err.message);
    return;
  }
  renderOverview();
}

function renderOverview() {
  var d = _overview;
  var el = document.getElementById("overview-content");
  var sc = d.status_counts || {};
  var hr  = sc.HUMAN_REVIEW || 0;
  var unr = sc.UNRESOLVED || 0;
  var aiRetry = sc.AI_RETRY_REQUIRED || 0;
  var mt  = sc.MATCH || sc.MATCHED || 0;
  var prt = sc.PARTIAL_MATCH || 0;
  var uft = sc.UNRESOLVED_FOR_TIER_1 || 0;
  var total = d.total_transactions;

  // Nav badge
  var badgeCount = hr + unr + aiRetry;
  var badge = document.getElementById("exc-badge");
  if (badge) {
    if (badgeCount > 0) { badge.textContent = badgeCount; badge.style.display = ""; }
    else badge.style.display = "none";
  }

  // Subtitle with dataset info
  var sub = document.getElementById("overview-subtitle");
  if (sub) {
    var ds = d.dataset || "data";
    var gwR = d.gateway_rows || 0;
    var bnR = d.bank_rows || 0;
    var lgR = d.ledger_rows || 0;
    sub.textContent = "Dataset: " + ds + " · " + gwR + " gateway · " + bnR + " bank · " + lgR + " ledger rows";
  }

  var tc = d.tier_counts || {};
  var gw = d.gateway_value;
  var rv = d.reconciled_value;
  var rate = d.reconciliation_rate;
  var exc = d.exception_count;
  var variance = d.settlement_variance;
  var ratePct = pct(rate);
  var rateVal = Math.min(Math.max(parseFloat(ratePct), 0), 100);

  // ── KPI Grid ────────────────────────────────────────────
  var kpiHtml =
    '<div class="stats-grid">' +
      '<div class="stat-card"><div class="stat-accent match"></div><div class="label">Total Transactions</div><div class="value">' + total + '</div>' +
        '<div class="sub">' + tierChips(tc) + '</div></div>' +
      '<div class="stat-card"><div class="label">Gateway Value</div><div class="value">' + fmtMoney(gw) + '</div></div>' +
      '<div class="stat-card match"><div class="stat-accent match"></div><div class="label">Reconciled Value</div><div class="value">' + fmtMoney(rv) + '</div></div>' +
      '<div class="stat-card match"><div class="stat-accent match"></div><div class="label">Reconciliation Rate</div><div class="value">' + ratePct + '%</div>' +
        '<div class="sub"><div class="confidence-bar" style="flex:1"><div class="confidence-fill" style="width:' + rateVal + '%"></div></div></div></div>' +
      '<div class="stat-card unresolved"><div class="stat-accent unresolved"></div><div class="label">Exceptions</div><div class="value">' + exc + '</div>' +
        '<div class="sub">requiring attention</div></div>' +
      '<div class="stat-card review"><div class="stat-accent review"></div><div class="label">Human Review</div><div class="value">' + hr + '</div></div>' +
      '<div class="stat-card review"><div class="stat-accent review"></div><div class="label">AI Retry Required</div><div class="value">' + aiRetry + '</div></div>' +
      '<div class="stat-card"><div class="label">Settlement Variance</div><div class="value' + ((variance && Math.abs(variance) > 0.01) ? ' negative' : ' positive') + '">' + fmtMoney(variance) + '</div></div>' +
    '</div>';

  // ── Pipeline Funnel ──────────────────────────────────────
  var funnelHtml = '<div class="card" style="margin-bottom:1rem"><div class="card-head"><h3>Reconciliation Pipeline</h3></div><div class="card-body" style="padding:0.25rem 0.5rem">' +
    pipelineFunnelHtml(d) +
    '</div></div>';

  // ── Second row: Exception distribution + LLM ─────────────
  var secondRow =
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1rem">' +
      '<div class="card"><div class="card-head"><h3>Exception Distribution</h3></div><div class="card-body" style="padding:0.75rem">' +
        exceptionDistHtml(sc) +
      '</div></div>' +
      '<div class="card"><div class="card-head"><h3>LLM Usage</h3></div><div class="card-body" style="padding:0.75rem">' +
        '<table class="x-table"><tbody>' +
          '<tr><td>Gemini calls made</td><td class="num">' + (d.llm_calls_made || 0) + '</td></tr>' +
          '<tr><td>Recommendations validated</td><td class="num">' + (d.llm_recommendations_validated || 0) + '</td></tr>' +
          '<tr><td>Recommendations rejected</td><td class="num">' + (d.llm_recommendations_rejected || 0) + '</td></tr>' +
          (d.llm_models && d.llm_models.length ? '<tr><td>Model chain</td><td class="num" style="font-size:0.7rem;white-space:nowrap">' + d.llm_models.map(function (m) { return esc(m); }).join(' <span style="color:var(--text-4)">→</span> ') + '</td></tr>' : '') +
        '</tbody></table></div></div>' +
    '</div>';

  // ── Third row: Top Rules ─────────────────────────────────
  var thirdRow =
    '<div class="card"><div class="card-head"><h3>Top Reconciliation Rules</h3></div><div class="card-body" style="padding:0.75rem">' +
      rulesHtml(d) +
    '</div></div>';

  el.innerHTML = kpiHtml + funnelHtml + secondRow + thirdRow;
}

function tierChips(tc) {
  var out = [];
  ["TIER_1","TIER_2","TIER_3","STAGE_3"].forEach(function (t) {
    if (tc[t]) out.push('<span class="chip chip-tier">' + t + ': ' + tc[t] + '</span>');
  });
  return out.join("");
}

function pipelineFunnelHtml(d) {
  var t1 = d.tier1_summary || {};
  var t2 = d.tier2_summary || {};
  var t3 = d.tier3_summary || {};
  var t4 = d.stage3_summary || {};

  // Compute real input counts per tier from the summaries
  var t1Input = t1.total_input || (t1.matched_count + t1.partial_match_count + t1.unresolved_count);
  var t1Residue = t1.unresolved_count;
  var t2Residue = t2.total_residue || 0;
  var t3Residue = t3.total_residue || 0;

  var stages = [
    { label: "Tier 1 · Exact Match", value: t1.matched_count || 0, sub: (t1.partial_match_count || 0) + " partial", residue: t1Residue, input: t1Input },
    { label: "Tier 2 · Tolerance", value: t2.matched_count || 0, sub: "from residue", residue: t2Residue, input: t2.total_residue || 0 },
    { label: "Tier 3 · LLM-Assisted", value: t3.match_count || 0, sub: (t3.human_review_count || 0) + " review", residue: t3.total_residue || 0, input: t3.total_residue || 0 },
    { label: "Stage 3 · Split / Multi", value: t4.match_count || 0, sub: (t4.partial_count || 0) + " partial", residue: t4.unresolved_count || 0, input: t4.total_evaluated || 0 },
  ];

  var html = '<div class="pipeline-funnel">';
  stages.forEach(function (s) {
    html += '<div class="pipeline-stage">' +
      '<div class="pipeline-stage-label">' + esc(s.label) + '</div>' +
      '<div class="pipeline-stage-value">' + (s.value || 0) + '</div>' +
      '<div class="pipeline-stage-sub">' + esc(s.sub || "") + '</div>' +
      (s.residue ? '<div class="pipeline-stage-residue">' + s.residue + ' → next tier</div>' : '<div class="pipeline-stage-residue" style="visibility:hidden">—</div>') +
    '</div>';
  });
  html += '</div>';
  return html;
}

function exceptionDistHtml(sc) {
  var statuses = ["HUMAN_REVIEW","UNRESOLVED","AI_RETRY_REQUIRED","AMBIGUOUS","PARTIAL_PAYMENT","PARTIAL_MATCH","UNRESOLVED_FOR_TIER_1"];
  var colors = { HUMAN_REVIEW:"var(--amber)", UNRESOLVED:"var(--red)", AI_RETRY_REQUIRED:"var(--red)",
    AMBIGUOUS:"var(--amber)", PARTIAL_PAYMENT:"var(--amber)", PARTIAL_MATCH:"var(--amber)",
    UNRESOLVED_FOR_TIER_1:"var(--red)" };
  var total = 0;
  statuses.forEach(function (s) { total += (sc[s] || 0); });
  if (total === 0) return '<div class="empty-msg">No exceptions</div>';

  var html = '<div style="display:flex;flex-direction:column;gap:0.4rem">';
  statuses.forEach(function (s) {
    var c = sc[s] || 0;
    if (c === 0) return;
    var w = Math.round(c / total * 100);
    html += '<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.75rem">' +
      '<span class="status-dot" style="background:' + (colors[s] || "var(--text-4)") + '"></span>' +
      '<span style="min-width:120px;color:var(--text-2)">' + esc(s.replace(/_/g, " ")) + '</span>' +
      '<div style="flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden">' +
        '<div style="width:' + w + '%;height:100%;background:' + (colors[s] || "var(--text-4)") + ';border-radius:2px"></div></div>' +
      '<span class="num" style="min-width:28px">' + c + '</span></div>';
  });
  html += '</div>';
  return html;
}

function rulesHtml(d) {
  var rc = d.rule_counts || {};
  var entries = Object.entries(rc).sort(function (a,b) { return b[1] - a[1]; }).slice(0, 8);
  if (entries.length === 0) return '<div class="empty-msg">No rule data</div>';
  var html = '<table class="x-table"><thead><tr><th>Rule</th><th class="num">Count</th></tr></thead><tbody>';
  entries.forEach(function (e) {
    html += '<tr><td style="font-size:0.75rem">' + esc(e[0]) + '</td><td class="num">' + e[1] + '</td></tr>';
  });
  html += '</tbody></table>';
  return html;
}

/* ════════════════════════════════════════════════════════════
   Exceptions
   ════════════════════════════════════════════════════════════ */

async function loadExceptions() {
  var el = document.getElementById("exceptions-content");
  try {
    var res = await fetch(API + "/api/exceptions");
    if (!res.ok) throw new Error(res.statusText);
    _exceptions = await res.json();
  } catch (err) {
    el.innerHTML = errHtml(err.message);
    return;
  }
  _selectedExc = null;
  renderExceptions("ALL");
}

function renderExceptions(filter) {
  if (!_exceptions) return;
  var el = document.getElementById("exceptions-content");
  var items = _exceptions.exceptions || [];

  if (filter === "HUMAN_REVIEW") items = items.filter(function (e) { return e.status === "HUMAN_REVIEW"; });
  if (filter === "UNRESOLVED")   items = items.filter(function (e) { return e.status === "UNRESOLVED"; });
  if (filter === "AI_RETRY")     items = items.filter(function (e) { return e.status === "AI_RETRY_REQUIRED"; });
  if (filter === "PARTIAL")      items = items.filter(function (e) { return e.status === "PARTIAL_PAYMENT"; });

  var filters = [
    { key: "ALL", label: "All" },
    { key: "HUMAN_REVIEW", label: "Human Review" },
    { key: "UNRESOLVED", label: "Unresolved" },
    { key: "AI_RETRY", label: "AI Retry" },
    { key: "PARTIAL", label: "Partial Payment" },
  ];

  var html = '<div class="filter-bar">';
  filters.forEach(function (f) {
    html += '<button class="filter-btn ' + (filter === f.key ? "active" : "") + '" data-filter="' + f.key + '">' + f.label + '</button>';
  });
  html += '<span class="filter-count">' + items.length + ' exception' + (items.length !== 1 ? "s" : "") + '</span></div>';

  html += '<div class="exc-split"><div class="card exc-list"><div class="card-body" style="padding:0">';
  if (items.length === 0) {
    html += '<div class="empty-msg">No exceptions in this category</div>';
  } else {
    html += '<table class="x-table"><thead><tr><th>Transaction</th><th>Status</th><th>Rule</th></tr></thead><tbody>';
    items.forEach(function (e) {
      var sel = _selectedExc === e.transaction_id ? " selected" : "";
      html += '<tr data-tid="' + esc(e.transaction_id) + '" class="' + sel + '">' +
        '<td>' + esc(e.transaction_id) +
          (e.tier ? ' ' + tierChip(e.tier) : '') +
          (e.llm_consulted ? ' <span class="chip chip-tier" style="margin-left:2px">LLM</span>' : '') +
        '</td>' +
        '<td>' + chip(e.status) + '</td>' +
        '<td style="font-size:0.7rem;color:var(--text-3)">' + esc(e.rule || "—") + '</td></tr>';
    });
    html += '</tbody></table>';
  }
  html += '</div></div><div class="exc-detail-panel" id="exc-detail">';
  if (_selectedExc) { /* detail loaded via loadExcDetail */ }
  else { html += '<div class="empty-msg" style="padding:3rem 1rem">Select a transaction to view details</div>'; }
  html += '</div></div>';

  el.innerHTML = html;

  // Row clicks
  el.querySelectorAll(".x-table tbody tr[data-tid]").forEach(function (tr) {
    tr.addEventListener("click", function () {
      _selectedExc = tr.dataset.tid;
      renderExceptions(filter);
      loadExcDetail(_selectedExc);
    });
  });

  // Filter clicks
  el.querySelectorAll(".filter-btn").forEach(function (btn) {
    btn.addEventListener("click", function () { renderExceptions(btn.dataset.filter); });
  });

  if (_selectedExc) loadExcDetail(_selectedExc);
}

/* ── Exception Detail ────────────────────────────────────── */

async function loadExcDetail(tid) {
  var box = document.getElementById("exc-detail");
  if (!box) return;
  box.innerHTML = loadingHtml("Loading " + tid + "…");
  try {
    var res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid));
    if (!res.ok) {
      var err = await res.json().catch(function () { return {}; });
      box.innerHTML = '<div class="empty-msg">' + esc(err.error || "Not found") + '</div>';
      return;
    }
    box.innerHTML = renderDetail(await res.json());
    attachRetryListeners(tid, box);
  } catch (err) {
    box.innerHTML = '<div class="empty-msg">' + esc(err.message) + '</div>';
  }
}

/* ════════════════════════════════════════════════════════════
   Transactions (Full Explorer)
   ════════════════════════════════════════════════════════════ */

async function loadTransactions() {
  var el = document.getElementById("transactions-content");
  try {
    var res = await fetch(API + "/api/transactions");
    if (!res.ok) throw new Error(res.statusText);
    _transactions = await res.json();
  } catch (err) {
    el.innerHTML = errHtml(err.message);
    return;
  }
  _txSort = { field: null, dir: "asc" };
  _txFilter = "ALL";
  renderTransactionsPanel();
}

function renderTransactionsPanel() {
  if (!_transactions) return;
  var el = document.getElementById("transactions-content");
  var rows = _transactions.transactions || [];

  // Apply filter
  if (_txFilter === "MATCHED") rows = rows.filter(function (r) { return r.status === "MATCH" || r.status === "MATCHED"; });
  if (_txFilter === "EXCEPTIONS") rows = rows.filter(function (r) { return r.status !== "MATCH" && r.status !== "MATCHED"; });
  if (_txFilter === "SETTLEMENTS") rows = rows.filter(function (r) { return r.tier === "STAGE_3"; });

  // Apply sort
  if (_txSort.field) {
    rows = rows.slice().sort(function (a, b) {
      var av = a[_txSort.field], bv = b[_txSort.field];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return _txSort.dir === "asc" ? av - bv : bv - av;
      av = String(av); bv = String(bv);
      return _txSort.dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }

  var filters = [
    { key: "ALL", label: "All (" + _transactions.count + ")" },
    { key: "MATCHED", label: "Matched" },
    { key: "EXCEPTIONS", label: "Exceptions" },
    { key: "SETTLEMENTS", label: "Settlements" },
  ];

  function sortArrow(field) {
    if (_txSort.field !== field) return "";
    return _txSort.dir === "asc" ? " ↑" : " ↓";
  }

  var html = '<div class="tx-search">' +
    '<input class="field" id="txn-search-input" placeholder="Search by transaction ID…" autocomplete="off">' +
    '</div>';

  // Filter bar
  html += '<div class="filter-bar">';
  filters.forEach(function (f) {
    html += '<button class="filter-btn tx-filter-btn ' + (_txFilter === f.key ? "active" : "") + '" data-txf="' + f.key + '">' + f.label + '</button>';
  });
  html += '<span class="filter-count">' + rows.length + ' transaction' + (rows.length !== 1 ? "s" : "") + '</span></div>';

  // Table
  html += '<div class="tx-table-wrap"><div class="tx-table-scroll">';
  if (rows.length === 0) {
    html += '<div class="empty-msg">No transactions match this filter</div>';
  } else {
    html += '<table class="x-table"><thead><tr>' +
      '<th data-sort="transaction_id" style="cursor:pointer">ID' + sortArrow("transaction_id") + '</th>' +
      '<th data-sort="status" style="cursor:pointer">Status' + sortArrow("status") + '</th>' +
      '<th data-sort="tier" style="cursor:pointer">Tier' + sortArrow("tier") + '</th>' +
      '<th data-sort="amount" style="cursor:pointer;text-align:right">Amount' + sortArrow("amount") + '</th>' +
      '<th>Rule</th>' +
      '</tr></thead><tbody>';
    rows.forEach(function (r) {
      var isSelected = _selectedTxn === r.transaction_id;
      html += '<tr data-tid="' + esc(r.transaction_id) + '" class="' + (isSelected ? "selected" : "") + '">' +
        '<td style="font-family:var(--font-mono);font-weight:500;font-size:0.8rem">' + esc(r.transaction_id) + '</td>' +
        '<td>' + chip(r.status) + '</td>' +
        '<td>' + tierChip(r.tier) + '</td>' +
        '<td class="num">' + fmtMoney(r.amount) + '</td>' +
        '<td style="font-size:0.7rem;color:var(--text-3)">' + esc(r.rule || "—") + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
  }
  html += '</div></div>';

  // Detail panel
  html += '<div id="txn-detail-panel" class="tx-detail-panel"></div>';

  el.innerHTML = html;

  // ── Event listeners ──────────────────────────────────────

  // Search input
  var input = document.getElementById("txn-search-input");
  if (input) {
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      if (!q) { renderTransactionsPanel(); return; }
      var match = (_transactions.transactions || []).find(function (r) {
        return r.transaction_id.toLowerCase().indexOf(q) !== -1;
      });
      if (match) { loadTxnDetail(match.transaction_id); }
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        var v = input.value.trim().toUpperCase();
        if (v) loadTxnDetail(v);
      }
    });
  }

  // Filter buttons
  el.querySelectorAll(".tx-filter-btn").forEach(function (btn) {
    btn.addEventListener("click", function () { _txFilter = btn.dataset.txf; renderTransactionsPanel(); });
  });

  // Sort headers
  el.querySelectorAll("th[data-sort]").forEach(function (th) {
    th.addEventListener("click", function () {
      var field = th.dataset.sort;
      if (_txSort.field === field) { _txSort.dir = _txSort.dir === "asc" ? "desc" : "asc"; }
      else { _txSort.field = field; _txSort.dir = "asc"; }
      renderTransactionsPanel();
    });
  });

  // Row clicks
  el.querySelectorAll(".x-table tbody tr[data-tid]").forEach(function (tr) {
    tr.addEventListener("click", function () {
      _selectedTxn = tr.dataset.tid;
      loadTxnDetail(tr.dataset.tid);
      // Re-render to update selection highlight
      renderTransactionsPanel();
    });
  });

  // Load detail for pre-selected txn
  if (_selectedTxn) loadTxnDetail(_selectedTxn);
}

async function loadTxnDetail(tid) {
  var panel = document.getElementById("txn-detail-panel");
  if (!panel) return;
  panel.innerHTML = loadingHtml("Loading " + tid + "…");
  try {
    var res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid));
    if (!res.ok) {
      var err = await res.json().catch(function () { return {}; });
      panel.innerHTML = '<div class="error-msg">' + esc(err.error || "Transaction not found") + '</div>';
      return;
    }
    panel.innerHTML = renderDetail(await res.json());
    attachRetryListeners(tid, panel);
  } catch (err) {
    panel.innerHTML = '<div class="error-msg">' + esc(err.message) + '</div>';
  }
}

/* ════════════════════════════════════════════════════════════
   Transaction Detail Renderer
   ════════════════════════════════════════════════════════════ */

function attachRetryListeners(tid, box) {
  var retryT3 = box.querySelector("[data-retry-llm]");
  if (retryT3) retryT3.addEventListener("click", function () { retryGemini(tid, retryT3); });
  var retryS3 = box.querySelector("[data-retry-stage3]");
  if (retryS3) retryS3.addEventListener("click", function () { retryStage3(tid, retryS3); });
  var review = box.querySelector("[data-ai-review]");
  if (review) review.addEventListener("click", function () { requestAIReview(tid, review, box); });
}

async function requestAIReview(tid, button, box) {
  button.disabled = true;
  button.textContent = "Reviewing…";
  try {
    var res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid) + "/ai-review", {
      method: "POST", headers: {"Content-Type": "application/json"}
    });
    var data = await res.json();
    var target = box.querySelector("[data-ai-review-result]");
    if (!res.ok) throw new Error(data.error || "AI review failed");
    var review = data.review || {};
    var conf = review.confidence != null ? Math.round(review.confidence * 100) : null;
    var confCls = conf != null ? (conf >= 75 ? "high" : (conf >= 50 ? "medium" : "low")) : "";
    var heading = data.source === "DETERMINISTIC_FALLBACK"
      ? "Stored Evidence Review (Gemini unavailable)"
      : "AI Review (read-only)";
    target.innerHTML = '<div class="evidence-block"><h4>' + heading + '</h4>' +
      (conf != null ? '<div class="confidence-bar" style="margin-bottom:0.4rem"><div class="confidence-fill ' + confCls + '" style="width:' + conf + '%"></div></div>' : '') +
      '<div class="ev-row"><span class="ek">Decision</span><span class="ev">' + esc(review.decision || "—") + '</span></div>' +
      '<div class="ev-row"><span class="ek">Confidence</span><span class="ev">' + pct(conf) + '%</span></div>' +
      '<div class="ev-row"><span class="ek">Rationale</span><span class="ev">' + esc(review.rationale || "—") + '</span></div>' +
      '<div class="ev-row"><span class="ek">Evidence</span><span class="ev">' + esc(JSON.stringify(review.evidence || {})) + '</span></div>' +
      '</div>';
    button.textContent = "✓ Reviewed";
  } catch (err) {
    button.disabled = false;
    button.textContent = "AI Review";
    alert("AI review failed: " + err.message);
  }
}

async function retryGemini(tid, button) {
  button.disabled = true;
  button.textContent = "Retrying…";
  try {
    var res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid) + "/retry-llm", {
      method: "POST", headers: {"Content-Type": "application/json"}
    });
    var data = await res.json();
    if (res.status === 503) {
      var box = document.getElementById("exc-detail") || document.getElementById("txn-detail-panel");
      if (box) { box.innerHTML = renderDetail(data); attachRetryListeners(tid, box); }
      return;
    }
    await loadExceptions();
    loadExcDetail(tid);
  } catch (err) {
    button.disabled = false;
    button.textContent = "↻ Retry Gemini";
    alert("Retry failed: " + err.message);
  }
}

async function retryStage3(tid, button) {
  button.disabled = true;
  button.textContent = "Retrying…";
  try {
    var res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid) + "/retry-stage3", {
      method: "POST", headers: {"Content-Type": "application/json"}
    });
    var data = await res.json();
    if (res.status === 503) {
      var box = document.getElementById("exc-detail") || document.getElementById("txn-detail-panel");
      if (box) { box.innerHTML = renderDetail(data); attachRetryListeners(tid, box); }
      return;
    }
    await loadExceptions();
    loadExcDetail(tid);
  } catch (err) {
    button.disabled = false;
    button.textContent = "↻ Retry Stage 3";
    alert("Retry failed: " + err.message);
  }
}

function renderDetail(d) {
  var ev = d.evidence || {};
  var mr = d.matched_records || {};
  var evEntries = Object.entries(ev).filter(function (pair) { return pair[1] !== null && pair[1] !== undefined; });
  var gw = mr.gateway || "—";
  var bn = mr.bank || "—";
  var lg = mr.ledger || "—";
  var bankRowIds = d.bank_row_ids || [];
  var settlement = d.settlement || {};
  var isStage3 = d.tier === "STAGE_3";

  // Settlement breakdown
  var settlementBlock = "";
  if (isStage3 && settlement && Object.keys(settlement).length > 0) {
    settlementBlock = '<div class="settlement-block"><h4>Settlement Breakdown</h4><div class="settlement-grid">' +
      settlementItem("Gross", settlement.gross_amount, "") +
      settlementItem("GST", settlement.gst_amount, "positive") +
      settlementItem("TDS", settlement.tds_amount, "negative") +
      settlementItem("Fees", settlement.total_fee_amount, "negative") +
      settlementItem("Refund", settlement.refund_amount, "negative") +
      settlementItem("Expected Net", settlement.expected_net_amount, "") +
      settlementItem("Actual Bank", settlement.actual_bank_amount, "") +
      settlementItem("Variance", settlement.variance,
        (settlement.variance && Math.abs(settlement.variance) > 0.01) ? "negative" : "zero") +
    '</div></div>';
  }

  // Partial payment
  var partialBlock = "";
  if (isStage3 && d.status === "PARTIAL_PAYMENT") {
    partialBlock = detailField("Received", fmtMoney(d.received)) +
      '<div class="detail-field"><div class="df-label">Outstanding</div><div class="df-value negative">' + fmtMoney(d.outstanding) + '</div></div>' +
      detailField("Expected Net", fmtMoney(d.expected_net));
  }

  // Bank rows
  var bankHtml = "";
  if (isStage3 && bankRowIds.length > 0) {
    bankHtml = '<div class="detail-field"><div class="df-label">Bank Row(s)</div><div class="bank-rows">';
    bankRowIds.forEach(function (id) {
      bankHtml += '<div class="bank-row"><span class="id">' + esc(id) + '</span><span class="amount credit">credit</span></div>';
    });
    bankHtml += '</div></div>';
  } else {
    bankHtml = detailField("Bank Row", bn);
  }

  // LLM block
  var llmBlock = "";
  if (d.llm_consulted !== undefined) {
    var rec = d.llm_recommendation;
    llmBlock = '<div class="evidence-block"><h4>AI Adjudication</h4>' +
      '<div class="ev-row"><span class="ek">LLM Consulted</span><span class="ev">' + (d.llm_consulted ? "Yes" : "No") + '</span></div>' +
      (d.confidence != null ? '<div class="ev-row"><span class="ek">Confidence</span><span class="ev">' + pct(d.confidence * 100) + '%</span></div>' : '') +
      (rec ? '<div class="ev-row"><span class="ek">Recommendation</span><span class="ev">' +
        esc(rec.decision || "—") + ' — bank IDs: ' + esc(JSON.stringify(rec.bank_row_ids || [])) + '</span></div>' : '') +
      '</div>';
  }

  // Confidence bar
  var confHtml = "";
  if (d.confidence != null) {
    var p = Math.round(d.confidence * 100);
    var cls = p < 50 ? "critical" : (p < 75 ? "low" : "");
    confHtml = detailField("Confidence",
      '<div class="confidence-bar"><div class="confidence-fill ' + cls + '" style="width:' + p + '%"></div></div><span style="font-size:0.75rem;color:var(--text-3)">' + p + '%</span>');
  }

  // Retry button
  var retryBtn = "";
  if (d.status === "AI_RETRY_REQUIRED") {
    if (d.tier === "TIER_3")
      retryBtn = '<button class="retry-btn" data-retry-llm>↻ Retry Gemini</button>';
    else if (d.tier === "STAGE_3")
      retryBtn = '<button class="retry-btn" data-retry-stage3>↻ Retry Stage 3</button>';
  }
  var reviewBtn = '<button class="retry-btn" data-ai-review>AI Review</button>';

  return '<div class="detail-card">' +
    '<div class="detail-head">' +
      '<span class="detail-tid">' + esc(d.transaction_id || "—") + '</span>' +
      chip(d.status) + tierChip(d.tier) +
      retryBtn + reviewBtn +
    '</div>' +
    '<div class="detail-body"><div class="detail-grid"><div>' +
      detailField("Status", statusDot(d.status)) +
      detailField("Rule", d.rule || "—") +
      detailField("Reason", d.reason || "—") +
      confHtml +
      detailField("Gateway Row", gw) +
      bankHtml +
      detailField("Ledger Row", lg) +
      partialBlock +
    '</div><div>' +
      settlementBlock +
      (evEntries.length > 0 ?
        '<div class="evidence-block"><h4>Evidence</h4>' +
        evEntries.map(function (pair) {
          var val = typeof pair[1] === "object" ? JSON.stringify(pair[1]) : pair[1];
          return '<div class="ev-row"><span class="ek">' + esc(pair[0]) + '</span><span class="ev">' + esc(val) + '</span></div>';
        }).join("") + '</div>' : '') +
      llmBlock + '<div data-ai-review-result></div>' +
    '</div></div></div></div>';
}

function settlementItem(label, value, cls) {
  return '<div class="settlement-item"><span class="settlement-label">' + esc(label) +
    '</span><span class="settlement-value ' + cls + '">' + fmtMoney(value) + '</span></div>';
}

function detailField(label, content) {
  return '<div class="detail-field"><div class="df-label">' + esc(label) + '</div><div class="df-value">' + content + '</div></div>';
}

/* ════════════════════════════════════════════════════════════
   Q&A / Settlement Intelligence — Chat Interface
   ════════════════════════════════════════════════════════════ */

var _chatReviewMode = false;

var _chatSuggestions = [
  "Which transactions need human review?",
  "Show unresolved transactions.",
  "What happened to PAY109?",
  "Which matched by split settlement rule?",
];

var _followUpSuggestions = {
  LOOKUP:     ["What is the status?", "Why was it matched?", "Show evidence for this transaction"],
  STATUS:     ["What happened to it?", "Show evidence", "AI Review this transaction"],
  WHY:        ["What evidence supports this?", "View transaction detail", "Which tier resolved it?"],
  EVIDENCE:   ["AI Review this transaction", "View transaction detail"],
  FILTER_STATUS: ["Show unresolved transactions.", "Which have partial payments?"],
  FILTER_RULE:   ["Which transactions need human review?", "Show exceptions."],
};

function initQA() {
  if (_qaInited) return;
  _qaInited = true;
  var el = document.getElementById("qa-content");

  el.innerHTML =
    '<div class="qa-wrap">' +
      '<div class="chat-messages" id="chat-messages">' +
        chatWelcomeHtml() +
      '</div>' +
      '<div class="chat-input-bar">' +
        '<button class="chat-review-toggle" id="chat-review-toggle" title="Include AI Review in response">' +
          '<input type="checkbox" id="chat-review-cb">' +
          '<span>🤖 AI Review</span>' +
        '</button>' +
        '<textarea class="chat-input-field" id="chat-input" rows="1" placeholder="Ask about your reconciliation data…" autocomplete="off"></textarea>' +
        '<button class="chat-send-btn" id="chat-send-btn">Send</button>' +
      '</div>' +
    '</div>';

  var input = document.getElementById("chat-input");
  var btn = document.getElementById("chat-send-btn");
  var toggle = document.getElementById("chat-review-toggle");
  var cb = document.getElementById("chat-review-cb");

  toggle.addEventListener("click", function () {
    _chatReviewMode = !_chatReviewMode;
    cb.checked = _chatReviewMode;
    toggle.classList.toggle("active", _chatReviewMode);
  });

  function submit() {
    var q = input.value.trim();
    if (!q) return;
    input.value = "";
    autoResize(input);
    sendChat(q);
  }

  btn.addEventListener("click", submit);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  input.addEventListener("input", function () { autoResize(input); });

  // Suggestion chips in welcome
  el.querySelectorAll(".chat-suggestion").forEach(function (b) {
    b.addEventListener("click", function () {
      input.value = b.textContent;
      autoResize(input);
      submit();
    });
  });

  // ── Event-delegated action handler (fixes IIFE-scoped inline onclick bug)
  var chatMsgs = document.getElementById("chat-messages");
  if (chatMsgs) {
    chatMsgs.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-chat-action]");
      if (!btn) return;
      var action = btn.dataset.chatAction;
      var tid = btn.dataset.chatTid;
      if (!tid) return;
      if (action === "view-transaction") chatViewTransaction(tid);
      else if (action === "ai-review") chatAIReview(tid, btn);
      else if (action === "retry-llm") chatRetryLLM(tid, btn);
    });
  }
}

function autoResize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
}

function chatWelcomeHtml() {
  var chips = _chatSuggestions.map(function (s) {
    return '<button class="chat-suggestion">' + esc(s) + '</button>';
  }).join("");
  return '<div class="chat-welcome">' +
    '<h2>Settlement Intelligence</h2>' +
    '<p>Ask questions about your reconciliation data. The AI follows deterministic matching rules and explains decisions grounded in real pipeline results.</p>' +
    '<div class="chat-suggestions">' + chips + '</div>' +
  '</div>';
}

function addUserMessage(q) {
  var msgs = document.getElementById("chat-messages");
  var welcome = msgs.querySelector(".chat-welcome");
  if (welcome) welcome.remove();

  var div = document.createElement("div");
  div.className = "chat-msg user";
  div.innerHTML =
    '<div class="chat-avatar">👤</div>' +
    '<div class="chat-bubble">' + esc(q) + '</div>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addTypingIndicator() {
  var msgs = document.getElementById("chat-messages");
  var div = document.createElement("div");
  div.className = "chat-msg ai";
  div.id = "chat-typing";
  div.innerHTML =
    '<div class="chat-avatar">🤖</div>' +
    '<div class="chat-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function removeTypingIndicator() {
  var el = document.getElementById("chat-typing");
  if (el) el.remove();
}

async function sendChat(q) {
  var reviewMode = _chatReviewMode;
  addUserMessage(q);
  addTypingIndicator();

  try {
    var res = await fetch(API + "/api/qa", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q}),
    });
    var data = await res.json();
    removeTypingIndicator();
    addAIResponse(data, reviewMode);
    updateFollowUps(data);
  } catch (err) {
    removeTypingIndicator();
    addAIError(err.message);
  }
}

function addAIResponse(data, reviewMode) {
  var msgs = document.getElementById("chat-messages");
  var div = document.createElement("div");
  div.className = "chat-msg ai";

  var intent = (data.intent || "UNKNOWN").replace("INTENT_", "").toLowerCase();
  var intentClass = intent;
  if (intent === "filter_status" || intent === "filter_rule") intentClass = "filter";
  if (intent === "unsupported") intentClass = "unsupported";

  var answer = data.explanation || "No explanation returned.";
  var tid = (data.transaction_ids && data.transaction_ids[0]) || null;

  // Info rows
  var infoHtml = "";
  var rows = [];
  if (tid) rows.push(["Transaction", tid]);
  if (data.retrieved_data && data.retrieved_data.length > 0) {
    var rd = data.retrieved_data[0];
    if (rd.status) rows.push(["Status", rd.status]);
    if (rd.tier) rows.push(["Tier", rd.tier]);
    if (rd.rule) rows.push(["Rule", rd.rule]);
    if (rd.reason) rows.push(["Reason", rd.reason]);
    if (rd.confidence != null) rows.push(["Confidence", pct(Number(rd.confidence) * 100) + "%"]);
  }
  if (rows.length > 0) {
    infoHtml = '<div class="chat-info-rows">' +
      rows.map(function (r) {
        return '<div class="chat-info-row"><span class="chat-info-key">' + esc(r[0]) + '</span><span class="chat-info-val">' + esc(String(r[1])) + '</span></div>';
      }).join("") +
    '</div>';
  }

  // Confidence bar
  var confHtml = "";
  if (data.retrieved_data && data.retrieved_data[0] && data.retrieved_data[0].confidence != null) {
    var c = Math.round(Number(data.retrieved_data[0].confidence) * 100);
    var cls = c >= 75 ? "high" : (c >= 50 ? "medium" : "low");
    confHtml = '<div class="chat-confidence">' +
      '<span class="chat-confidence-label">Confidence</span>' +
      '<div class="chat-confidence-bar"><div class="chat-confidence-fill ' + cls + '" style="width:' + c + '%"></div></div>' +
      '<span class="chat-confidence-val">' + c + '%</span>' +
    '</div>';
  }

  // Meta tags
  var metaHtml = "";
  var meta = [];
  if (data.llm_used) meta.push("🤖 LLM used");
  if (data.llm_unavailable) meta.push("⚠️ LLM unavailable");
  if (data.found === false) meta.push("❓ Not found");
  if (data.supported === false) meta.push("🚫 Unsupported");
  if (meta.length) {
    metaHtml = '<div class="chat-meta">' +
      meta.map(function (m) { return '<span>' + m + '</span>'; }).join("") +
    '</div>';
  }

  // Action buttons — using data attributes instead of inline onclick (IIFE-safe)
  var actionsHtml = "";
  var actions = [];
  if (tid) {
    actions.push('<button class="chat-action-btn primary" data-chat-action="view-transaction" data-chat-tid="' + esc(tid) + '">📄 View Transaction</button>');
    actions.push('<button class="chat-action-btn" data-chat-action="ai-review" data-chat-tid="' + esc(tid) + '">🤖 AI Review</button>');
  }
  if (data.retrieved_data && data.retrieved_data[0] && data.retrieved_data[0].status === "AI_RETRY_REQUIRED") {
    if (tid) actions.push('<button class="chat-action-btn" data-chat-action="retry-llm" data-chat-tid="' + esc(tid) + '">↻ Retry Gemini</button>');
  }
  if (actions.length) {
    actionsHtml = '<div class="chat-actions">' + actions.join("") + '</div>';
  }

  div.innerHTML =
    '<div class="chat-avatar">🤖</div>' +
    '<div class="chat-bubble"><div class="chat-card">' +
      '<div class="chat-card-head">' +
        '<span class="intent-badge ' + intentClass + '">' + esc(intent.replace(/_/g, " ")) + '</span>' +
      '</div>' +
      '<div class="chat-card-body">' + esc(answer) + '</div>' +
      infoHtml + confHtml + metaHtml + actionsHtml +
    '</div></div>';

  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addAIError(msg) {
  var msgs = document.getElementById("chat-messages");
  var div = document.createElement("div");
  div.className = "chat-msg ai";
  div.innerHTML =
    '<div class="chat-avatar">🤖</div>' +
    '<div class="chat-bubble"><div class="chat-card">' +
      '<div class="chat-card-body" style="color:var(--red)">Error: ' + esc(msg) + '</div>' +
    '</div></div>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function updateFollowUps(data) {
  var intent = (data.intent || "").replace("INTENT_", "");
  var suggestions = _followUpSuggestions[intent] || _chatSuggestions;
  var container = document.querySelector(".chat-messages");
  if (!container) return;

  var existing = container.querySelector(".chat-follow-ups");
  if (existing) existing.remove();

  var div = document.createElement("div");
  div.className = "chat-follow-ups";
  div.style.cssText = "display:flex;flex-wrap:wrap;gap:0.35rem;padding:0.25rem 0 0.5rem 3.25rem;";
  suggestions.forEach(function (s) {
    var btn = document.createElement("button");
    btn.className = "chat-suggestion";
    btn.textContent = s;
    btn.addEventListener("click", function () {
      var input = document.getElementById("chat-input");
      if (input) { input.value = s; autoResize(input); input.focus(); }
    });
    div.appendChild(btn);
  });
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

/* ── Chat action handlers ─────────────────────────────────── */

function chatViewTransaction(tid) {
  switchPanel("transactions");
  setTimeout(function () { _selectedTxn = tid; loadTxnDetail(tid); }, 100);
}

async function chatAIReview(tid, button) {
  button.disabled = true;
  button.textContent = "Reviewing…";
  try {
    var res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid) + "/ai-review", {
      method: "POST", headers: {"Content-Type": "application/json"}
    });
    var data = await res.json();
    if (!res.ok) throw new Error(data.error || "AI review failed");
    var review = data.review || {};
    var conf = review.confidence != null ? Math.round(review.confidence * 100) : null;
    var confCls = conf != null ? (conf >= 75 ? "high" : (conf >= 50 ? "medium" : "low")) : "";
    var resultHtml =
      '<div class="chat-review-result">' +
        '<div class="chat-review-head">' +
          (data.source === "DETERMINISTIC_FALLBACK" ? "Stored Evidence Review" : "🤖 AI Review Result") +
        '</div>' +
        (conf != null ?
          '<div class="chat-confidence" style="border:none;padding:0.15rem 0">' +
            '<span class="chat-confidence-label">Confidence</span>' +
            '<div class="chat-confidence-bar"><div class="chat-confidence-fill ' + confCls + '" style="width:' + conf + '%"></div></div>' +
            '<span class="chat-confidence-val">' + conf + '%</span>' +
          '</div>' : '') +
        '<div class="chat-info-rows" style="border:none">' +
          (review.decision ? '<div class="chat-info-row"><span class="chat-info-key">Decision</span><span class="chat-info-val">' + esc(review.decision) + '</span></div>' : '') +
          (review.rationale ? '<div class="chat-info-row"><span class="chat-info-key">Rationale</span><span class="chat-info-val">' + esc(review.rationale) + '</span></div>' : '') +
          (review.evidence && Object.keys(review.evidence).length > 0 ?
            '<div class="chat-info-row"><span class="chat-info-key">Evidence</span><span class="chat-info-val" style="font-family:var(--font-mono);font-size:0.7rem">' + esc(JSON.stringify(review.evidence)) + '</span></div>' : '') +
        '</div>' +
      '</div>';

    var msgs = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "chat-msg ai";
    div.innerHTML = '<div class="chat-avatar">🤖</div><div class="chat-bubble">' + resultHtml + '</div>';
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    button.textContent = "✓ Reviewed";
  } catch (err) {
    button.disabled = false;
    button.textContent = "🤖 AI Review";
    alert("AI review failed: " + err.message);
  }
}

async function chatRetryLLM(tid, button) {
  button.disabled = true;
  button.textContent = "Retrying…";
  try {
    var res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid) + "/retry-llm", {
      method: "POST", headers: {"Content-Type": "application/json"}
    });
    var data = await res.json();
    var msgs = document.getElementById("chat-messages");
    var status = data.status || "UNKNOWN";
    var color = status === "MATCH" ? "var(--green)" : "var(--amber)";
    var div = document.createElement("div");
    div.className = "chat-msg ai";
    div.innerHTML =
      '<div class="chat-avatar">🤖</div>' +
      '<div class="chat-bubble"><div class="chat-card">' +
        '<div class="chat-card-head"><span class="intent-badge">RETRY RESULT</span></div>' +
        '<div class="chat-card-body">Transaction <strong>' + esc(tid) + '</strong> is now: <span style="color:' + color + ';font-weight:600">' + esc(status) + '</span></div>' +
      '</div></div>';
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    button.textContent = "✓ Done";
  } catch (err) {
    button.disabled = false;
    button.textContent = "↻ Retry Gemini";
    alert("Retry failed: " + err.message);
  }
}

/* ════════════════════════════════════════════════════════════
   Initial load
   ════════════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", function () {
  loadOverview();
});

})();
