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
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  updateThemeBtn();
}

function toggleTheme() {
  var cur = document.documentElement.getAttribute("data-theme");
  var next;
  if (cur === "dark") next = "light";
  else if (cur === "light") next = "";
  else next = "dark";
  if (next) document.documentElement.setAttribute("data-theme", next);
  else document.documentElement.removeAttribute("data-theme");
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

  // Subtitle
  var sub = document.getElementById("overview-subtitle");
  if (sub) sub.textContent = total + " transactions processed";

  var tc = d.tier_counts || {};
  var gw = d.gateway_value;
  var rv = d.reconciled_value;
  var rate = d.reconciliation_rate;
  var exc = d.exception_count;
  var variance = d.settlement_variance;

  // Status counts for recent exceptions
  var recentItems = (_exceptions && _exceptions.exceptions) || [];

  el.innerHTML =
    '<div class="stats-grid">' +
      '<div class="stat-card"><div class="label">Total Transactions</div><div class="value">' + total + '</div>' +
        '<div class="sub">' + tierChips(tc) + '</div></div>' +
      '<div class="stat-card"><div class="label">Gateway Value</div><div class="value">' + fmtMoney(gw) + '</div></div>' +
      '<div class="stat-card match"><div class="label">Reconciled Value</div><div class="value">' + fmtMoney(rv) + '</div></div>' +
      '<div class="stat-card match"><div class="label">Reconciliation Rate</div><div class="value">' + pct(rate) + '%</div>' +
        '<div class="sub">' + mt + ' matched / ' + total + '</div></div>' +
      '<div class="stat-card unresolved"><div class="label">Exceptions</div><div class="value">' + exc + '</div>' +
        '<div class="sub">requiring attention</div></div>' +
      '<div class="stat-card review"><div class="label">Human Review</div><div class="value">' + hr + '</div></div>' +
      '<div class="stat-card review"><div class="label">AI Retry Required</div><div class="value">' + aiRetry + '</div></div>' +
      '<div class="stat-card"><div class="label">Settlement Variance</div><div class="value' + ((variance && Math.abs(variance) > 0.01) ? ' negative' : ' positive') + '">' + fmtMoney(variance) + '</div></div>' +
    '</div>' +

    // Pipeline
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.85rem;margin-bottom:0.85rem">' +
      '<div class="card"><div class="card-head"><h3>Reconciliation Pipeline</h3></div><div class="card-body" style="padding:0.75rem">' +
        pipelineHtml(d) +
      '</div></div>' +
      '<div class="card"><div class="card-head"><h3>Exception Distribution</h3></div><div class="card-body" style="padding:0.75rem">' +
        exceptionDistHtml(sc) +
      '</div></div>' +
    '</div>' +

    // LLM + Rules
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.85rem">' +
      '<div class="card"><div class="card-head"><h3>LLM Usage</h3></div><div class="card-body" style="padding:0.75rem">' +
        '<table class="x-table"><tbody>' +
          '<tr><td>Gemini calls made</td><td class="num">' + (d.llm_calls_made || 0) + '</td></tr>' +
          '<tr><td>Recommendations validated</td><td class="num">' + (d.llm_recommendations_validated || 0) + '</td></tr>' +
          '<tr><td>Recommendations rejected</td><td class="num">' + (d.llm_recommendations_rejected || 0) + '</td></tr>' +
        '</tbody></table></div></div>' +
      '<div class="card"><div class="card-head"><h3>Top Rules</h3></div><div class="card-body" style="padding:0.75rem">' +
        rulesHtml(d) +
      '</div></div>' +
    '</div>';
}

function tierChips(tc) {
  var out = [];
  ["TIER_1","TIER_2","TIER_3","STAGE_3"].forEach(function (t) {
    if (tc[t]) out.push('<span class="chip chip-tier">' + t + ': ' + tc[t] + '</span>');
  });
  return out.join("");
}

function pipelineHtml(d) {
  var t1 = d.tier1_summary || {};
  var t2 = d.tier2_summary || {};
  var t3 = d.tier3_summary || {};
  var t4 = d.stage3_summary || {};
  var steps = [
    { label: "Tier 1 — Exact", matched: t1.matched_count, partial: t1.partial_match_count, residue: t1.unresolved_count },
    { label: "Tier 2 — Tolerance", matched: t2.matched_count, from: t2.total_residue },
    { label: "Tier 3 — LLM-Assisted", matched: t3.match_count, hr: t3.human_review_count, unr: t3.unresolved_count },
    { label: "Stage 3 — Split/Multi", matched: t4.match_count, partial: t4.partial_count, unr: t4.unresolved_count },
  ];
  var html = '<table class="x-table"><thead><tr><th>Stage</th><th class="num">Matched</th><th class="num">Other</th></tr></thead><tbody>';
  steps.forEach(function (s) {
    var other = [];
    if (s.partial) other.push(s.partial + " partial");
    if (s.hr) other.push(s.hr + " review");
    if (s.unr) other.push(s.unr + " unresolved");
    if (s.from != null && s.from !== s.matched && !other.length) other.push(s.from + " input");
    html += '<tr><td>' + esc(s.label) + '</td><td class="num">' + (s.matched || 0) + '</td><td class="num">' + (other.join(", ") || "—") + '</td></tr>';
  });
  html += '</tbody></table>';
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
    html += '<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.78rem">' +
      '<span class="status-dot" style="background:' + (colors[s] || "var(--text-4)") + '"></span>' +
      '<span style="min-width:120px;color:var(--text-2)">' + esc(s.replace(/_/g, " ")) + '</span>' +
      '<div style="flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden">' +
        '<div style="width:' + w + '%;height:100%;background:' + (colors[s] || "var(--text-4)") + ';border-radius:2px"></div></div>' +
      '<span class="num" style="min-width:30px">' + c + '</span></div>';
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
    html += '<tr><td style="font-size:0.78rem">' + esc(e[0]) + '</td><td class="num">' + e[1] + '</td></tr>';
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
        '<td style="font-size:0.72rem;color:var(--text-3)">' + esc(e.rule || "—") + '</td></tr>';
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
   Transactions
   ════════════════════════════════════════════════════════════ */

async function loadTransactions() {
  var el = document.getElementById("transactions-content");
  // Fetch overview to get transaction index, then build the full table
  try {
    if (!_overview) {
      var res = await fetch(API + "/api/overview");
      if (!res.ok) throw new Error(res.statusText);
      _overview = await res.json();
    }
  } catch (err) {
    el.innerHTML = errHtml(err.message);
    return;
  }

  // Fetch exceptions to get which txns are exceptions
  var excMap = {};
  if (_exceptions && _exceptions.exceptions) {
    _exceptions.exceptions.forEach(function (e) { excMap[e.transaction_id] = e; });
  }

  // Build a combined transaction list from the index by fetching each one
  // Actually, the API doesn't have a list-all endpoint. Use the overview
  // tier counts to derive total, but we need individual transactions.
  // Best approach: build from what we know and use /api/transaction/<id>.
  // However, without a list endpoint, the Transactions panel should let users
  // search/lookup specific IDs, and display recent exceptions as a starting point.
  renderTransactionsPanel();
}

function renderTransactionsPanel() {
  var el = document.getElementById("transactions-content");
  var html =
    '<div class="tx-search">' +
      '<input class="field" id="txn-search-input" placeholder="Enter transaction ID (e.g. PAY001)" autocomplete="off">' +
    '</div>' +
    '<div id="txn-search-result"></div>' +
    '<div id="txn-detail-panel" class="tx-detail-panel"></div>';

  el.innerHTML = html;

  var input = document.getElementById("txn-search-input");
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { var v = input.value.trim(); if (v) loadTxnDetail(v); }
  });

  // Also show recent exceptions as a starting point
  if (_exceptions && _exceptions.exceptions && _exceptions.exceptions.length > 0) {
    var rp = document.getElementById("txn-search-result");
    var recent = _exceptions.exceptions.slice(0, 10);
    var html2 = '<div style="margin-top:0.75rem"><div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-3);margin-bottom:0.4rem;font-weight:500">Recent exceptions</div>';
    html2 += '<table class="x-table"><thead><tr><th>Transaction</th><th>Status</th><th>Tier</th><th>Rule</th></tr></thead><tbody>';
    recent.forEach(function (e) {
      html2 += '<tr class="txn-row" data-tid="' + esc(e.transaction_id) + '" style="cursor:pointer">' +
        '<td class="mono">' + esc(e.transaction_id) + '</td>' +
        '<td>' + chip(e.status) + '</td>' +
        '<td>' + tierChip(e.tier) + '</td>' +
        '<td style="font-size:0.72rem;color:var(--text-3)">' + esc(e.rule || "—") + '</td></tr>';
    });
    html2 += '</tbody></table></div>';
    rp.innerHTML = html2;

    rp.querySelectorAll(".txn-row").forEach(function (tr) {
      tr.addEventListener("click", function () { loadTxnDetail(tr.dataset.tid); });
    });
  }
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
    button.textContent = "Retry Gemini";
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
    button.textContent = "Retry Stage 3";
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
      '<div class="confidence-bar"><div class="confidence-fill ' + cls + '" style="width:' + p + '%"></div></div><span style="font-size:0.78rem;color:var(--text-3)">' + p + '%</span>');
  }

  // Retry button
  var retryBtn = "";
  if (d.status === "AI_RETRY_REQUIRED") {
    if (d.tier === "TIER_3")
      retryBtn = '<button class="retry-btn" data-retry-llm>↻ Retry Gemini</button>';
    else if (d.tier === "STAGE_3")
      retryBtn = '<button class="retry-btn" data-retry-stage3>↻ Retry Stage 3</button>';
  }

  return '<div class="detail-card">' +
    '<div class="detail-head">' +
      '<span class="detail-tid">' + esc(d.transaction_id || "—") + '</span>' +
      chip(d.status) + tierChip(d.tier) +
      retryBtn +
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
      llmBlock +
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
   Q&A / Settlement Intelligence
   ════════════════════════════════════════════════════════════ */

function initQA() {
  if (_qaInited) return;
  _qaInited = true;
  var el = document.getElementById("qa-content");

  var examples = [
    "Which transactions need human review?",
    "Show unresolved transactions.",
    "Which transactions have partial payments?",
    "Which matched by split settlement rule?",
    "What happened to this transaction?",
    "How was the settlement amount calculated?",
    "Which bank rows make up this settlement?",
    "Why was the Gemini recommendation rejected?",
  ];

  el.innerHTML =
    '<div class="qa-wrap">' +
      '<div class="qa-input-card">' +
        '<div class="qa-input-head"><h3>Ask a question about your reconciliation data</h3></div>' +
        '<div class="qa-input-row">' +
          '<input class="qa-field field" id="qa-input" placeholder="e.g. Which transactions need human review?" autocomplete="off">' +
          '<button class="qa-send btn btn-primary" id="qa-btn">Ask</button>' +
        '</div>' +
        '<div class="qa-chips">' +
          '<span class="ch-label" style="font-size:0.72rem;color:var(--text-3);margin-right:0.3rem">Try:</span>' +
          examples.map(function (e) { return '<button class="qa-chip">' + esc(e) + '</button>'; }).join("") +
        '</div>' +
      '</div>' +
      '<div class="qa-history" id="qa-history"></div>' +
    '</div>';

  var input = document.getElementById("qa-input");
  var btn   = document.getElementById("qa-btn");
  var hist  = document.getElementById("qa-history");

  function submit() {
    var q = input.value.trim();
    if (!q) return;
    input.value = "";
    askQA(q, hist);
  }

  btn.addEventListener("click", submit);
  input.addEventListener("keydown", function (e) { if (e.key === "Enter") submit(); });

  el.querySelectorAll(".qa-chip").forEach(function (b) {
    b.addEventListener("click", function () { input.value = b.textContent; submit(); });
  });
}

async function askQA(q, hist) {
  var turn = document.createElement("div");
  turn.className = "qa-turn";
  turn.innerHTML =
    '<div class="qa-turn-q">' + esc(q) + '</div>' +
    '<div class="qa-turn-a">' + loadingHtml("Thinking…") + '</div>';
  hist.prepend(turn);

  try {
    var res = await fetch(API + "/api/qa", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q}),
    });
    var data = await res.json();
    var answer = data.explanation || "No explanation returned.";
    var meta = [];
    if (data.llm_used) meta.push("🤖 LLM used");
    if (data.llm_unavailable) meta.push("⚠️ LLM unavailable");
    if (data.found === false) meta.push("❓ Not found");
    if (data.supported === false) meta.push("🚫 Unsupported question");
    turn.innerHTML =
      '<div class="qa-turn-q">' + esc(q) + '</div>' +
      '<div class="qa-turn-a">' +
        '<div class="answer-text">' + esc(answer) + '</div>' +
        (meta.length ? '<div class="answer-meta">' + meta.join(' · ') + '</div>' : "") +
      '</div>';
  } catch (err) {
    turn.innerHTML =
      '<div class="qa-turn-q">' + esc(q) + '</div>' +
      '<div class="qa-turn-a"><div class="answer-text" style="color:var(--red)">Error: ' + esc(err.message) + '</div></div>';
  }
}

/* ════════════════════════════════════════════════════════════
   Initial load
   ════════════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", function () {
  loadOverview();
});

})();
