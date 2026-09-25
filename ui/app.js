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
let _currentPanel = "overview";
let _runsLoaded = false;
let _txSort = { field: "transaction_id", dir: "asc" };
let _txFilter = "ALL";
let _txSearch = "";
let _excFilter = "ALL";
let _excSearch = "";

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

function tierChip(t) { return '<span class="chip chip-tier">' + esc(t) + '</span>'; }

function fmtMoney(v) {
  if (v == null || v === "") return "—";
  var n = typeof v === "string" ? parseFloat(v) : v;
  if (!isFinite(n)) return "—";
  return "₹" + n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function pct(v) { return (v == null || isNaN(v)) ? "0.0" : Number(v).toFixed(1); }
function count(n) { return Number(n || 0); }
function isMatched(status) { return status === "MATCH" || status === "MATCHED"; }
function moneyClass(value) {
  var n = typeof value === "number" ? value : parseFloat(value);
  if (!isFinite(n) || Math.abs(n) <= 0.01) return "";
  return n < 0 ? "negative" : "positive";
}
function fmtDate(value) {
  if (!value) return "—";
  var date = new Date(value);
  if (isNaN(date.getTime())) return esc(value);
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
function firstValue() {
  for (var i = 0; i < arguments.length; i++) {
    if (arguments[i] !== null && arguments[i] !== undefined && arguments[i] !== "") return arguments[i];
  }
  return null;
}
function sourceReference(row) {
  return row.gateway_row || (row.matched_records && row.matched_records.gateway) || "—";
}
function matchState(rowOrStatus, tier) {
  var status = typeof rowOrStatus === "string" ? rowOrStatus : rowOrStatus.status;
  return isMatched(status) ? "Matched" : "Exception";
}
function settlementState(row) {
  if (!row || row.tier !== "STAGE_3") return "Not evaluated";
  if (isMatched(row.status)) return "Settled";
  if (row.status === "PARTIAL_PAYMENT") return "Partial";
  return row.status ? row.status.replace(/_/g, " ") : "Unknown";
}
function exceptionState(rowOrStatus) {
  var status = typeof rowOrStatus === "string" ? rowOrStatus : rowOrStatus.status;
  return isMatched(status) ? "None" : (status ? status.replace(/_/g, " ") : "Unknown");
}
function triageFor(status) {
  if (status === "AI_RETRY_REQUIRED" || status === "UNRESOLVED" || status === "UNRESOLVED_FOR_TIER_1") {
    return { label: "High", tone: "urgent" };
  }
  if (status === "HUMAN_REVIEW" || status === "AMBIGUOUS") return { label: "Review", tone: "review" };
  return { label: "Settlement", tone: "settlement" };
}
function nextActionFor(status) {
  if (status === "AI_RETRY_REQUIRED") return "Retry adjudication only when authorized; keep the result unchanged until the retry completes.";
  if (status === "PARTIAL_PAYMENT") return "Compare received funds with expected net and inspect the settlement breakdown.";
  if (status === "HUMAN_REVIEW" || status === "AMBIGUOUS") return "Review the source rows and matching evidence before taking action.";
  if (status === "UNRESOLVED" || status === "UNRESOLVED_FOR_TIER_1") return "Confirm source coverage; no sufficient match evidence is currently available.";
  return "No exception action is required.";
}

function loadingHtml(msg) { return '<div class="loading" role="status" aria-live="polite">' + esc(msg || "Loading…") + '</div>'; }

async function fetchJson(path, options) {
  var res = await fetch(API + path, options);
  var data = null;
  try { data = await res.json(); } catch (_) { /* response may not be JSON */ }
  if (!res.ok) {
    var message = (data && data.error) || res.statusText || "Request failed (" + res.status + ")";
    var error = new Error(message);
    error.status = res.status;
    error.payload = data;
    throw error;
  }
  return data;
}

function retryErrorHtml(msg, action) {
  return '<div class="error-state" role="alert">' +
    '<div class="error-state-copy"><strong>Data unavailable</strong><span>' + esc(msg) + '</span></div>' +
    '<button class="btn btn-secondary btn-sm" data-retry-action="' + esc(action) + '">Retry</button>' +
  '</div>';
}

function setPipelineStatus(text, state) {
  var wrap = document.getElementById("header-run-status");
  var label = document.getElementById("header-run-status-text");
  if (label) label.textContent = text;
  if (wrap) wrap.className = "run-status state-" + (state || "ready");
}

function attachRetryAction(action, handler) {
  var button = document.querySelector("[data-retry-action=" + action + "]");
  if (button) button.addEventListener("click", handler);
}

function attachOverviewRetry() {
  attachRetryAction("overview", loadOverview);
}

/* ── Theme ───────────────────────────────────────────────── */

var THEME_STORAGE_KEY = "ledgerloop-theme-v3";

function initTheme() {
  var saved = localStorage.getItem(THEME_STORAGE_KEY);
  var theme = saved === "dark" || saved === "light" ? saved : "light";
  document.documentElement.setAttribute("data-theme", theme);
  updateThemeBtn();
}

function toggleTheme() {
  var current = document.documentElement.getAttribute("data-theme");
  var next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem(THEME_STORAGE_KEY, next);
  updateThemeBtn();
}

function updateThemeBtn() {
  var current = document.documentElement.getAttribute("data-theme");
  var dark = current === "dark";
  var toggle = document.getElementById("theme-toggle");
  var label = document.getElementById("theme-label");
  var themeColor = document.querySelector('meta[name="theme-color"]');
  if (label) label.textContent = dark ? "Light" : "Dark";
  if (toggle) toggle.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
  if (themeColor) themeColor.setAttribute("content", dark ? "#0b1722" : "#f2f0e9");
}

document.addEventListener("DOMContentLoaded", function () {
  var toggle = document.getElementById("theme-toggle");
  if (toggle) toggle.addEventListener("click", toggleTheme);
  initTheme();
});

/* ── Navigation / header context ─────────────────────────── */

var PANEL_META = {
  overview:     { title: "Overview", context: "Current reconciliation run and project evidence" },
  runs:         { title: "Pipeline Trace", context: "Current run, architecture, and control boundaries" },
  exceptions:   { title: "Exception Investigation", context: "Evidence-led discrepancy review" },
  transactions: { title: "Transaction Ledger", context: "Searchable source-of-truth index" },
  qa:           { title: "Settlement Intelligence", context: "Grounded questions over completed run evidence" },
};

function updateHeader(pid) {
  var meta = PANEL_META[pid] || PANEL_META.overview;
  var crumb = document.getElementById("header-page-title");
  var context = document.getElementById("header-context");
  if (crumb) crumb.textContent = meta.title;
  if (context) context.textContent = meta.context;
  document.title = meta.title + " — LedgerLoop";
}

function switchPanel(pid) {
  if (!PANEL_META[pid]) pid = "overview";
  document.querySelectorAll(".nav-item").forEach(function (item) {
    var active = item.dataset.panel === pid;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  document.querySelectorAll(".panel").forEach(function (panel) {
    var active = panel.id === "panel-" + pid;
    panel.classList.toggle("active", active);
    if (active) panel.removeAttribute("aria-hidden");
    else panel.setAttribute("aria-hidden", "true");
  });
  _currentPanel = pid;
  updateHeader(pid);
  if (window.history && window.history.replaceState) {
    window.history.replaceState(null, "", "#" + pid);
  }
  window.scrollTo({top: 0, behavior: "auto"});
  if (pid === "overview") { if (_overview) renderOverview(); else loadOverview(); }
  if (pid === "runs") { if (_overview) renderRuns(); else loadRuns(); }
  if (pid === "exceptions" && !_exceptions) loadExceptions();
  if (pid === "transactions" && !_transactions) loadTransactions();
  if (pid === "qa" && !_qaInited) initQA();
}

document.addEventListener("DOMContentLoaded", function () {
  var nav = document.getElementById("nav");
  if (nav) {
    nav.addEventListener("click", function (event) {
      var button = event.target.closest(".nav-item");
      if (!button) return;
      switchPanel(button.dataset.panel);
    });
  }

  document.addEventListener("click", function (event) {
    var jump = event.target.closest("[data-jump-panel]");
    if (!jump) return;
    event.preventDefault();
    switchPanel(jump.dataset.jumpPanel);
  });

  window.addEventListener("hashchange", function () {
    var panel = window.location.hash.replace(/^#/, "");
    if (PANEL_META[panel] && panel !== _currentPanel) switchPanel(panel);
  });
});

/* ════════════════════════════════════════════════════════════
   Overview
   ════════════════════════════════════════════════════════════ */

async function loadOverview() {
  var el = document.getElementById("overview-content");
  el.innerHTML = loadingHtml("Preparing reconciliation data…");
  setPipelineStatus("Loading data", "loading");
  try {
    _overview = await fetchJson("/api/overview");
    setPipelineStatus("Run ready", "ready");
  } catch (err) {
    setPipelineStatus("Data unavailable", "error");
    el.innerHTML = retryErrorHtml(err.message, "overview");
    attachOverviewRetry();
    return;
  }
  renderOverview();
  if (_runsLoaded) renderRuns();
}

function renderOverview() {
  var d = _overview || {};
  var el = document.getElementById("overview-content");
  var sc = d.status_counts || {};
  var total = count(d.total_transactions);
  var matched = count(sc.MATCH) + count(sc.MATCHED);
  var attention = Math.max(total - matched, 0);
  var exc = count(d.exception_count || attention);
  var rate = Number(d.reconciliation_rate || 0);
  var rateValue = Math.min(Math.max(rate, 0), 100);
  var stage3 = d.stage3_summary || {};
  var runStatus = d.run_status || "Snapshot ready";
  var runTime = d.run_created_at ? fmtDate(d.run_created_at) : "Current in-memory run";

  var badge = document.getElementById("exc-badge");
  if (badge) {
    badge.textContent = exc;
    badge.hidden = exc <= 0;
  }
  var ctaCount = document.getElementById("overview-exception-cta-count");
  if (ctaCount) ctaCount.textContent = exc > 0 ? "(" + exc + ")" : "";

  var outcomeRows = Object.keys(sc).sort(function (a, b) { return count(sc[b]) - count(sc[a]); });
  var outcomeLedger = outcomeRows.length ? outcomeRows.map(function (status) {
    var share = total ? count(sc[status]) / total * 100 : 0;
    return '<div class="outcome-row"><div>' + chip(status) + '</div><strong>' + count(sc[status]) + '</strong><span>' + pct(share) + '%</span></div>';
  }).join("") : '<div class="empty-state"><strong>No outcome data</strong><span>The current run returned no transaction statuses.</span></div>';

  var settlementRows = [
    ["Settled", count(stage3.match_count)],
    ["Partial", count(stage3.partial_count)],
    ["Unresolved", count(stage3.unresolved_count)],
    ["Ambiguous", count(stage3.ambiguous_count)]
  ];
  var settlementTotal = settlementRows.reduce(function (sum, row) { return sum + row[1]; }, 0);
  var settlementLedger = settlementTotal ? settlementRows.map(function (row) {
    return '<div class="outcome-row"><span>' + row[0] + '</span><strong>' + row[1] + '</strong><span>' + pct(row[1] / settlementTotal * 100) + '%</span></div>';
  }).join("") : '<div class="empty-state"><strong>No Stage 3 results</strong><span>No split-settlement cases were evaluated.</span></div>';

  el.innerHTML =
    '<section class="run-brief" aria-labelledby="run-brief-title">' +
      '<div class="run-brief-head">' +
        '<div class="run-brief-title"><span class="run-seal" aria-hidden="true">RUN<br>01</span><div><h2 id="run-brief-title">Current reconciliation report</h2><p>' + esc(runStatus) + ' · ' + esc(runTime) + '</p></div></div>' +
        '<div class="run-metadata" aria-label="Run context"><div><span>Dataset</span><strong>' + esc(d.dataset || "data") + '</strong></div><div><span>Source rows</span><strong>' + count(d.gateway_rows) + ' / ' + count(d.bank_rows) + ' / ' + count(d.ledger_rows) + '</strong></div><div><span>Engine</span><strong>Deterministic-first</strong></div></div>' +
      '</div>' +
      '<div class="metric-ledger" aria-label="Current run summary">' +
        '<div class="metric-cell"><div class="metric-label"><span>Reconciliation rate</span><span class="metric-code">RATE</span></div><div><span class="metric-value serif positive">' + pct(rate) + '%</span><div class="metric-track" aria-hidden="true"><span style="width:' + rateValue + '%"></span></div></div><div class="metric-meta"><span><strong>' + matched + '</strong> resolved</span><span><strong>' + attention + '</strong> open</span></div></div>' +
        '<div class="metric-cell"><div class="metric-label"><span>Logical transactions</span><span class="metric-code">VOL</span></div><span class="metric-value">' + total + '</span><div class="metric-meta"><span>Across three source systems</span></div></div>' +
        '<div class="metric-cell"><div class="metric-label"><span>Gateway value</span><span class="metric-code">VAL</span></div><span class="metric-value">' + fmtMoney(d.gateway_value) + '</span><div class="metric-meta"><span>Signed gateway scope · reconciled <strong>' + fmtMoney(d.reconciled_value) + '</strong></span></div></div>' +
        '<div class="metric-cell"><div class="metric-label"><span>Exception queue</span><span class="metric-code">EXC</span></div><span class="metric-value negative">' + exc + '</span><div class="metric-meta"><span>Stage 3 variance <strong class="' + moneyClass(d.settlement_variance) + '">' + fmtMoney(d.settlement_variance) + '</strong></span></div></div>' +
      '</div>' +
    '</section>' +

    '<div class="overview-layout">' +
      '<section class="ledger-card" aria-labelledby="resolution-path-title">' +
        '<div class="ledger-card-head"><div><h2 id="resolution-path-title">Resolution path</h2><p>Each stage receives only the residue it can safely evaluate.</p></div><button class="text-action" type="button" data-jump-panel="runs">Open run trace</button></div>' +
        '<div class="ledger-card-body">' + pipelineFunnelHtml(d) + '</div>' +
      '</section>' +
      '<section class="ledger-card" aria-labelledby="authority-title">' +
        '<div class="ledger-card-head"><div><h2 id="authority-title">Why a result is trustworthy</h2><p>Authority stays explicit at every handoff.</p></div></div>' +
        '<ol class="proof-list">' +
          '<li><span class="proof-index">01</span><div><strong>Evidence before automation</strong><p>Exact and bounded rules resolve routine matches before any provider is considered.</p></div></li>' +
          '<li><span class="proof-index">02</span><div><strong>Validated recommendations</strong><p>Gemini can recommend a linked match, but Python checks candidates, consumed rows, and financial invariants.</p></div></li>' +
          '<li><span class="proof-index">03</span><div><strong>Unresolved is a valid outcome</strong><p>Ambiguous or contradictory evidence stays visible for human review instead of becoming a forced match.</p></div></li>' +
        '</ol>' +
      '</section>' +
    '</div>' +

    '<div class="overview-layout">' +
      '<section class="ledger-card" aria-labelledby="outcomes-title">' +
        '<div class="ledger-card-head"><div><h2 id="outcomes-title">Final outcome distribution</h2><p>Authoritative status across every logical transaction.</p></div><button class="text-action" type="button" data-jump-panel="transactions">Open ledger</button></div>' +
        '<div class="ledger-card-body">' + outcomeLedger + '</div>' +
      '</section>' +
      '<section class="ledger-card" aria-labelledby="settlement-pass-title">' +
        '<div class="ledger-card-head"><div><h2 id="settlement-pass-title">Settlement pass</h2><p>Stage 3 split-settlement outcomes.</p></div><button class="text-action" type="button" data-jump-panel="qa">Inspect position</button></div>' +
        '<div class="ledger-card-body">' + settlementLedger + '</div>' +
      '</section>' +
    '</div>' +

    '<section class="governance-ledger" aria-label="AI governance metrics">' +
      '<div><span>Control boundary</span><strong>AI is advisory, not authoritative</strong></div>' +
      '<div><span>Provider calls</span><b>' + count(d.llm_calls_made) + '</b></div>' +
      '<div><span>Validated</span><b>' + count(d.llm_recommendations_validated) + '</b></div>' +
      '<div><span>Rejected</span><b>' + count(d.llm_recommendations_rejected) + '</b></div>' +
    '</section>' +

    '<section class="review-path" aria-label="Recruiter review path">' +
      '<button class="review-step" type="button" data-jump-panel="runs"><span>01</span><div><strong>Understand the architecture</strong><small>Trace normalization, tiers, and the final snapshot.</small></div><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 10h12M11 5l5 5-5 5"/></svg></button>' +
      '<button class="review-step" type="button" data-jump-panel="exceptions"><span>02</span><div><strong>Investigate a real exception</strong><small>Inspect reason, source rows, evidence, and next action.</small></div><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 10h12M11 5l5 5-5 5"/></svg></button>' +
      '<button class="review-step" type="button" data-jump-panel="qa"><span>03</span><div><strong>Test grounded intelligence</strong><small>Ask a bounded question and verify its citations.</small></div><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 10h12M11 5l5 5-5 5"/></svg></button>' +
    '</section>';
}

function pipelineFunnelHtml(d) {
  var t1 = d.tier1_summary || {};
  var t2 = d.tier2_summary || {};
  var t3 = d.tier3_summary || {};
  var t4 = d.stage3_summary || {};
  var stages = [
    {
      name: "Exact evidence",
      rule: "Reference + amount",
      input: count(firstValue(t1.total_logical_transactions, t1.total_input)),
      resolved: count(t1.matched_count),
      note: count(t1.partial_match_count) + " partial",
      forward: count(t1.unresolved_count),
      forwardLabel: "Forwarded"
    },
    {
      name: "Bounded tolerance",
      rule: "Amount + reference transforms",
      input: count(firstValue(t2.total_residue_evaluated, t2.total_residue)),
      resolved: count(t2.matched_count),
      note: count(t2.ambiguous_count) + " ambiguous",
      forward: count(firstValue(t3.total_residue, t2.unresolved_count)),
      forwardLabel: "Forwarded"
    },
    {
      name: "Linked evidence",
      rule: "Supported links / guarded AI",
      input: count(firstValue(t3.total_residue_evaluated, t3.total_residue)),
      resolved: count(t3.match_count),
      note: count(t3.human_review_count) + " review",
      forward: count(firstValue(t4.total_evaluated, t3.unresolved_count)),
      forwardLabel: "Forwarded"
    },
    {
      name: "Split settlement",
      rule: "Credits, tax, fees, refund",
      input: count(t4.total_evaluated),
      resolved: count(t4.match_count),
      note: count(t4.partial_count) + " partial",
      forward: count(t4.unresolved_count),
      forwardLabel: "Open result"
    }
  ];

  return '<div class="stage-ledger">' + stages.map(function (stage, index) {
    var share = stage.input ? Math.min(Math.max(stage.resolved / stage.input * 100, 0), 100) : 0;
    return '<div class="stage-row">' +
      '<span class="stage-index">' + String(index + 1).padStart(2, "0") + '</span>' +
      '<div class="stage-copy"><strong>' + esc(stage.name) + '</strong><span>' + esc(stage.rule) + ' · ' + esc(stage.note) + '</span></div>' +
      '<div class="stage-result"><strong>' + stage.resolved + '</strong><span>resolved</span></div>' +
      '<div class="stage-forward"><div><span>' + esc(stage.forwardLabel) + '</span><strong>' + stage.forward + ' / ' + stage.input + '</strong></div><div class="stage-bar" aria-hidden="true"><span style="width:' + share + '%"></span></div></div>' +
    '</div>';
  }).join("") + '</div>';
}

/* ════════════════════════════════════════════════════════════
   Reconciliation Runs — current run context (read-only)
   ════════════════════════════════════════════════════════════ */

async function loadRuns() {
  var el = document.getElementById("runs-content");
  el.innerHTML = loadingHtml("Loading current run…");
  setPipelineStatus("Loading data", "loading");
  try {
    if (!_overview) _overview = await fetchJson("/api/overview");
  } catch (err) {
    setPipelineStatus("Data unavailable", "error");
    el.innerHTML = retryErrorHtml(err.message, "runs");
    attachRetryAction("runs", loadRuns);
    return;
  }
  _runsLoaded = true;
  setPipelineStatus("Run ready", "ready");
  renderRuns();
}

function renderRuns() {
  if (!_overview) return;
  var d = _overview;
  var el = document.getElementById("runs-content");
  var sub = document.getElementById("runs-subtitle");
  if (sub) {
    sub.textContent = "Dataset " + (d.dataset || "Not exposed") + " · " +
      count(d.gateway_rows) + " gateway rows · " + count(d.bank_rows) + " bank rows · " +
      count(d.ledger_rows) + " ledger rows · deterministic-first";
  }

  var t1 = d.tier1_summary || {};
  var t2 = d.tier2_summary || {};
  var t3 = d.tier3_summary || {};
  var t4 = d.stage3_summary || {};
  var sc = d.status_counts || {};
  var tc = d.tier_counts || {};
  var total = count(d.total_transactions);
  var matched = count(sc.MATCH) + count(sc.MATCHED);
  var attention = Math.max(total - matched, 0);
  var runReference = d.run_id == null ? "Run ID not exposed" : "Run #" + d.run_id;
  var runStatus = d.run_status || "Snapshot ready";
  var runTime = d.run_created_at ? fmtDate(d.run_created_at) : "Current in-memory run";

  var stages = [
    { name: "Tier 1 · Exact evidence", note: count(t1.partial_match_count) + " partial match", evaluated: t1.total_logical_transactions, matched: t1.matched_count, forward: t1.unresolved_count },
    { name: "Tier 2 · Bounded tolerance", note: count(t2.ambiguous_count) + " ambiguous", evaluated: firstValue(t2.total_residue_evaluated, t2.total_residue), matched: t2.matched_count, forward: t2.unresolved_count },
    { name: "Tier 3 · Linked evidence", note: count(t3.human_review_count) + " human review", evaluated: firstValue(t3.total_residue_evaluated, t3.total_residue), matched: t3.match_count, forward: t3.unresolved_count },
    { name: "Stage 3 · Split settlement", note: count(t4.partial_count) + " partial settlement", evaluated: t4.total_evaluated, matched: t4.match_count, forward: t4.unresolved_count }
  ];
  var stageRows = stages.map(function (stage) {
    return '<tr><td><span class="table-primary">' + esc(stage.name) + '</span><div class="table-reason">' + esc(stage.note) + '</div></td><td class="num">' + count(stage.evaluated) + '</td><td class="num">' + count(stage.matched) + '</td><td class="num">' + count(stage.forward) + '</td></tr>';
  }).join("");

  var outcomeKeys = Object.keys(sc).sort(function (a, b) { return count(sc[b]) - count(sc[a]); });
  var outcomeRows = outcomeKeys.length ? outcomeKeys.map(function (status) {
    return '<tr><td>' + chip(status) + '</td><td class="num">' + count(sc[status]) + '</td><td class="num">' + pct(total ? count(sc[status]) / total * 100 : 0) + '%</td></tr>';
  }).join("") : '<tr><td colspan="3"><div class="empty-state"><strong>No outcome data</strong><span>The run returned no status counts.</span></div></td></tr>';

  var tierDefinitions = [
    ["TIER_1", "Tier 1 · exact evidence"],
    ["TIER_2", "Tier 2 · bounded tolerance"],
    ["TIER_3", "Tier 3 · linked evidence"],
    ["STAGE_3", "Stage 3 · split settlement"]
  ];
  var tierRows = tierDefinitions.filter(function (row) { return count(tc[row[0]]) > 0; }).map(function (row) {
    return '<tr><td><span class="table-primary">' + esc(row[1]) + '</span></td><td class="num">' + count(tc[row[0]]) + '</td><td class="num">' + pct(total ? count(tc[row[0]]) / total * 100 : 0) + '%</td></tr>';
  }).join("");

  el.innerHTML =
    '<section class="run-record" aria-labelledby="run-record-title">' +
      '<div class="run-record-main"><span class="eyebrow">Current run · ' + esc(runReference) + '</span><h2 id="run-record-title">Reconciliation snapshot</h2><p>' + esc(runStatus) + ' · ' + esc(runTime) + '</p></div>' +
      '<div class="run-record-metrics"><div><span>Transactions</span><strong>' + total + '</strong></div><div><span>Resolved</span><strong>' + matched + '</strong></div><div><span>Open</span><strong>' + attention + '</strong></div><div><span>Rate</span><strong>' + pct(d.reconciliation_rate) + '%</strong></div></div>' +
    '</section>' +

    '<section class="architecture-flow" aria-label="Reconciliation architecture">' +
      '<div class="architecture-node"><span>01 · INGEST</span><strong>Source normalization</strong><small>CSV rows → canonical records</small></div>' +
      '<div class="architecture-node"><span>02 · RESOLVE</span><strong>Tiered matching</strong><small>Exact → bounded → linked → split</small></div>' +
      '<div class="architecture-node"><span>03 · CONTROL</span><strong>Python validation</strong><small>One-to-one and financial invariants</small></div>' +
      '<div class="architecture-node"><span>04 · SERVE</span><strong>Read-only snapshot</strong><small>Flask API → evidence workspace</small></div>' +
    '</section>' +

    '<div class="run-columns">' +
      '<section class="surface-card" aria-labelledby="pipeline-run-title"><div class="surface-head"><div><h2 id="pipeline-run-title">Pipeline stages</h2><p>Evaluated volume, resolved outcomes, and forwarded residue.</p></div></div><div class="table-scroll"><table class="x-table runs-table"><thead><tr><th scope="col">Stage</th><th scope="col" class="num">Evaluated</th><th scope="col" class="num">Resolved</th><th scope="col" class="num">Forwarded</th></tr></thead><tbody>' + stageRows + '</tbody></table></div></section>' +
      '<section class="surface-card" aria-labelledby="sources-run-title"><div class="surface-head"><div><h2 id="sources-run-title">Source coverage</h2><p>Rows available to the current reconciliation run.</p></div></div><dl class="source-coverage"><div><dt>Gateway</dt><dd>' + count(d.gateway_rows) + '</dd></div><div><dt>Bank</dt><dd>' + count(d.bank_rows) + '</dd></div><div><dt>Ledger</dt><dd>' + count(d.ledger_rows) + '</dd></div></dl><ul class="control-list"><li><div><strong>Ground truth is isolated</strong><span>Evaluation data is never imported by matching code.</span></div></li><li><div><strong>One-to-one consumption</strong><span>A settled bank row cannot support a second match.</span></div></li><li><div><strong>Read-only review</strong><span>AI explanations never replace the stored result.</span></div></li></ul><div class="run-actions"><button class="btn btn-secondary btn-sm" type="button" data-jump-panel="transactions">Explore source index</button><button class="btn btn-primary btn-sm" type="button" data-jump-panel="exceptions">Open queue</button></div></section>' +
    '</div>' +

    '<div class="run-columns">' +
      '<section class="surface-card" aria-labelledby="outcomes-run-title"><div class="surface-head"><div><h2 id="outcomes-run-title">Outcome distribution</h2><p>Final status across all authoritative tiers.</p></div></div><div class="table-scroll"><table class="x-table"><thead><tr><th scope="col">Status</th><th scope="col" class="num">Transactions</th><th scope="col" class="num">Share</th></tr></thead><tbody>' + outcomeRows + '</tbody></table></div></section>' +
      '<section class="surface-card" aria-labelledby="authority-run-title"><div class="surface-head"><div><h2 id="authority-run-title">Resolution authority</h2><p>Authoritative tier for each transaction.</p></div></div><div class="table-scroll"><table class="x-table"><thead><tr><th scope="col">Tier</th><th scope="col" class="num">Transactions</th><th scope="col" class="num">Share</th></tr></thead><tbody>' + (tierRows || '<tr><td colspan="3"><div class="empty-state"><strong>No tier data</strong><span>The run returned no authoritative tier counts.</span></div></td></tr>') + '</tbody></table></div><p class="surface-note">Deterministic tiers own routine matching. Any provider recommendation remains advisory until application-level validation succeeds.</p></section>' +
    '</div>';
}

/* ════════════════════════════════════════════════════════════
   Exceptions
   ════════════════════════════════════════════════════════════ */

async function loadExceptions() {
  var el = document.getElementById("exceptions-content");
  el.innerHTML = loadingHtml("Loading exception queue…");
  try {
    _exceptions = await fetchJson("/api/exceptions");
  } catch (err) {
    el.innerHTML = retryErrorHtml(err.message, "exceptions");
    attachRetryAction("exceptions", loadExceptions);
    return;
  }
  var queue = _exceptions.exceptions || [];
  _selectedExc = queue.length ? queue[0].transaction_id : null;
  _excFilter = "ALL";
  _excSearch = "";
  renderExceptions("ALL");
}

function exceptionMatches(e, query) {
  if (!query) return true;
  var source = [e.transaction_id, e.status, e.rule, e.reason, e.tier,
    e.gateway_amount, e.expected_net, e.received, e.outstanding,
    (e.matched_records || {}).gateway, (e.matched_records || {}).bank,
    (e.matched_records || {}).ledger].concat(e.bank_row_ids || []).join(" ").toLowerCase();
  return source.indexOf(query.toLowerCase()) !== -1;
}

function renderExceptions(filter) {
  if (!_exceptions) return;
  var el = document.getElementById("exceptions-content");
  _excFilter = filter || _excFilter;
  var allItems = _exceptions.exceptions || [];
  var items = allItems.slice();

  if (_excFilter === "HUMAN_REVIEW") items = items.filter(function (e) { return e.status === "HUMAN_REVIEW"; });
  if (_excFilter === "UNRESOLVED") items = items.filter(function (e) { return e.status === "UNRESOLVED" || e.status === "UNRESOLVED_FOR_TIER_1"; });
  if (_excFilter === "AI_RETRY") items = items.filter(function (e) { return e.status === "AI_RETRY_REQUIRED"; });
  if (_excFilter === "PARTIAL") items = items.filter(function (e) { return e.status === "PARTIAL_PAYMENT" || e.status === "AMBIGUOUS"; });
  if (_excSearch) items = items.filter(function (e) { return exceptionMatches(e, _excSearch); });

  var visibleSelected = items.some(function (e) { return e.transaction_id === _selectedExc; });
  var html = '<div class="queue-toolbar"><div class="queue-search"><label for="exception-search">Search queue</label><input class="field" id="exception-search" type="search" value="' + esc(_excSearch) + '" placeholder="Transaction, reason, source row…" autocomplete="off"></div><div class="filter-bar" role="group" aria-label="Exception filters">';
  var filters = [
    { key: "ALL", label: "All" },
    { key: "HUMAN_REVIEW", label: "Human review" },
    { key: "UNRESOLVED", label: "Unresolved" },
    { key: "AI_RETRY", label: "AI retry" },
    { key: "PARTIAL", label: "Partial / ambiguous" },
  ];
  filters.forEach(function (f) {
    html += '<button class="filter-btn ' + (_excFilter === f.key ? "active" : "") + '" data-exc-filter="' + f.key + '" aria-pressed="' + (_excFilter === f.key) + '">' + f.label + '</button>';
  });
  html += '<span class="filter-count">' + items.length + ' of ' + allItems.length + ' exceptions</span></div></div>';

  html += '<div class="investigation-layout"><section class="queue-surface" aria-labelledby="queue-heading"><div class="queue-head"><h2 id="queue-heading">Investigation queue</h2><span>Priority is calculated from supported status</span></div><div class="table-scroll">';
  if (items.length === 0) {
    html += '<div class="empty-state"><strong>No exceptions found</strong><span>Adjust the filter or search query.</span></div>';
  } else {
    html += '<table class="x-table exc-table"><thead><tr><th scope="col">Priority</th><th scope="col">Transaction</th><th scope="col">Status</th><th scope="col" class="num">Amount</th><th scope="col">Mismatch reason</th></tr></thead><tbody>';
    items.forEach(function (e) {
      var triage = triageFor(e.status);
      var sel = _selectedExc === e.transaction_id ? " selected" : "";
      html += '<tr data-tid="' + esc(e.transaction_id) + '" tabindex="0" class="' + sel + '"><td><span class="priority-chip priority-' + triage.tone + '">' + triage.label + '</span></td><td><span class="table-primary">' + esc(e.transaction_id) + '</span><div class="table-reason">' + esc(e.tier || "—") + '</div></td><td>' + chip(e.status) + '</td><td class="num">' + fmtMoney(firstValue(e.gateway_amount, e.expected_net, e.received)) + '</td><td class="table-reason reason-cell"><span>' + esc(e.reason || e.rule || "—") + '</span></td></tr>';
    });
    html += '</tbody></table>';
  }
  html += '</div></section><aside class="investigation-panel" id="exc-detail" aria-live="polite">';
  if (_selectedExc && visibleSelected) {
    html += loadingHtml("Loading investigation…");
  } else if (_selectedExc) {
    html += '<div class="empty-state"><strong>Selection not visible</strong><span>Choose a transaction from the current queue.</span></div>';
  } else {
    html += '<div class="empty-state"><strong>Select an exception</strong><span>Financial evidence and next actions will appear here.</span></div>';
  }
  html += '</aside></div>';

  el.innerHTML = html;

  var search = document.getElementById("exception-search");
  if (search) {
    search.addEventListener("input", function () {
      _excSearch = search.value;
      renderExceptions(_excFilter);
      var next = document.getElementById("exception-search");
      if (next) { next.focus(); next.setSelectionRange(next.value.length, next.value.length); }
    });
  }
  el.querySelectorAll("[data-exc-filter]").forEach(function (btn) {
    btn.addEventListener("click", function () { renderExceptions(btn.dataset.excFilter); });
  });
  el.querySelectorAll(".exc-table tbody tr[data-tid]").forEach(function (tr) {
    function open() {
      _selectedExc = tr.dataset.tid;
      renderExceptions(_excFilter);
    }
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  });

  if (_selectedExc && visibleSelected) loadExcDetail(_selectedExc);
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
      if (res.status === 404) {
        box.innerHTML = '<div class="empty-msg">' + esc(err.error || "Not found") + '</div>';
      } else {
        box.innerHTML = retryErrorHtml(err.error || res.statusText || "Unable to load transaction", "exc-detail");
        attachRetryAction("exc-detail", function () { loadExcDetail(tid); });
      }
      return;
    }
    box.innerHTML = renderDetail(await res.json());
    attachRetryListeners(tid, box);
  } catch (err) {
    box.innerHTML = retryErrorHtml(err.message, "exc-detail");
    attachRetryAction("exc-detail", function () { loadExcDetail(tid); });
  }
}

/* ════════════════════════════════════════════════════════════
   Transactions (Full Explorer)
   ════════════════════════════════════════════════════════════ */

async function loadTransactions() {
  var el = document.getElementById("transactions-content");
  el.innerHTML = loadingHtml("Loading transaction explorer…");
  try {
    _transactions = await fetchJson("/api/transactions");
  } catch (err) {
    el.innerHTML = retryErrorHtml(err.message, "transactions");
    attachRetryAction("transactions", loadTransactions);
    return;
  }
  _txSort = { field: "transaction_id", dir: "asc" };
  _txFilter = "ALL";
  _txSearch = "";
  var rows = _transactions.transactions || [];
  var settlementCase = rows.filter(function (row) {
    return row.tier === "STAGE_3" && row.settlement && Object.keys(row.settlement).length > 0;
  })[0];
  _selectedTxn = settlementCase ? settlementCase.transaction_id : (rows.length ? rows[0].transaction_id : null);
  renderTransactionsPanel();
}

function transactionSearchText(r) {
  return [r.transaction_id, r.status, r.tier, r.rule, r.reason, r.amount,
    r.gateway_row, r.ledger_row].concat(r.bank_row_ids || []).join(" ").toLowerCase();
}

function renderTransactionsPanel() {
  if (!_transactions) return;
  var el = document.getElementById("transactions-content");
  var rows = (_transactions.transactions || []).map(function (r) {
    var amountValue = r.amount;
    if (amountValue == null) amountValue = firstValue(r.gateway_amount, r.expected_net, r.received);
    return Object.assign({}, r, {
      _source: sourceReference(r),
      _timestamp: firstValue(r.timestamp, r.transaction_timestamp, r.evidence && r.evidence.timestamp),
      _amount: amountValue,
      _matchState: matchState(r),
      _settlementState: settlementState(r),
      _exceptionState: exceptionState(r)
    });
  });

  if (_txFilter === "MATCHED") rows = rows.filter(function (r) { return isMatched(r.status); });
  if (_txFilter === "EXCEPTIONS") rows = rows.filter(function (r) { return !isMatched(r.status); });
  if (_txFilter === "SETTLEMENTS") rows = rows.filter(function (r) { return r.tier === "STAGE_3"; });
  if (_txSearch) {
    var query = _txSearch.toLowerCase();
    rows = rows.filter(function (r) { return transactionSearchText(r).indexOf(query) !== -1; });
  }

  if (_txSort.field) {
    rows = rows.slice().sort(function (a, b) {
      var av = _txSort.field === "amount" ? a._amount : a[_txSort.field];
      var bv = _txSort.field === "amount" ? b._amount : b[_txSort.field];
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
  function sortButton(field, label) {
    return '<button type="button" class="sort-control" data-tx-sort="' + field + '">' + label + '<span aria-hidden="true">' + sortArrow(field) + '</span></button>';
  }

  var html = '<div class="explorer-toolbar"><div class="tx-search"><label for="txn-search-input">Search transactions</label><input class="field" id="txn-search-input" type="search" value="' + esc(_txSearch) + '" placeholder="ID, source row, rule, status…" autocomplete="off"></div><div class="filter-bar" role="group" aria-label="Transaction filters">';
  filters.forEach(function (f) {
    html += '<button class="filter-btn tx-filter-btn ' + (_txFilter === f.key ? "active" : "") + '" data-txf="' + f.key + '" aria-pressed="' + (_txFilter === f.key) + '">' + f.label + '</button>';
  });
  html += '<span class="filter-count">' + rows.length + ' of ' + _transactions.count + ' transactions</span></div></div>';

  html += '<div class="explorer-layout"><section class="explorer-surface" aria-labelledby="transaction-table-title"><div class="table-scroll"><table class="x-table transaction-table"><thead><tr>' +
    '<th scope="col" aria-sort="' + (_txSort.field === "transaction_id" ? (_txSort.dir === "asc" ? "ascending" : "descending") : "none") + '">' + sortButton("transaction_id", "Transaction") + '</th>' +
    '<th scope="col">Source row</th>' +
    '<th scope="col">Timestamp</th>' +
    '<th scope="col" class="num" aria-sort="' + (_txSort.field === "amount" ? (_txSort.dir === "asc" ? "ascending" : "descending") : "none") + '">' + sortButton("amount", "Amount") + '</th>' +
    '<th scope="col">Match state</th>' +
    '<th scope="col">Settlement state</th>' +
    '<th scope="col">Exception state</th>' +
    '<th scope="col">' + sortButton("tier", "Tier") + '</th>' +
    '</tr></thead><tbody>';
  if (rows.length === 0) {
    html += '<tr><td colspan="8"><div class="empty-state"><strong>No transactions found</strong><span>Adjust the search or filter.</span></div></td></tr>';
  } else {
    rows.forEach(function (r) {
      var isSelected = _selectedTxn === r.transaction_id;
      html += '<tr data-tid="' + esc(r.transaction_id) + '" tabindex="0" class="' + (isSelected ? "selected" : "") + '">' +
        '<td><span class="table-primary">' + esc(r.transaction_id) + '</span><div class="table-reason">' + esc(r.rule || "—") + '</div></td>' +
        '<td><span class="source-ref">' + esc(r._source) + '</span></td>' +
        '<td><span class="timestamp">' + (r._timestamp ? fmtDate(r._timestamp) : "—") + '</span></td>' +
        '<td class="num">' + fmtMoney(r._amount) + '</td>' +
        '<td><span class="state-label state-' + (isMatched(r.status) ? "match" : "attention") + '">' + esc(r._matchState) + '</span></td>' +
        '<td><span class="state-label">' + esc(r._settlementState) + '</span></td>' +
        '<td><span class="state-label state-' + (isMatched(r.status) ? "clear" : "attention") + '">' + esc(r._exceptionState) + '</span></td>' +
        '<td>' + tierChip(r.tier) + '</td></tr>';
    });
  }
  html += '</tbody></table></div></section><aside class="transaction-detail-panel" id="txn-detail-panel" aria-live="polite">';
  if (_selectedTxn) html += loadingHtml("Loading transaction…");
  else html += '<div class="empty-state"><strong>Select a transaction</strong><span>Financial context, matching state, settlement state, and evidence will appear here.</span></div>';
  html += '</aside></div>';

  el.innerHTML = html;

  var input = document.getElementById("txn-search-input");
  if (input) {
    input.addEventListener("input", function () {
      _txSearch = input.value;
      renderTransactionsPanel();
      var next = document.getElementById("txn-search-input");
      if (next) { next.focus(); next.setSelectionRange(next.value.length, next.value.length); }
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        var exact = (_transactions.transactions || []).filter(function (r) { return r.transaction_id.toLowerCase() === input.value.trim().toLowerCase(); })[0];
        if (exact) { _selectedTxn = exact.transaction_id; renderTransactionsPanel(); loadTxnDetail(_selectedTxn); }
      }
    });
  }
  el.querySelectorAll("[data-txf]").forEach(function (btn) {
    btn.addEventListener("click", function () { _txFilter = btn.dataset.txf; renderTransactionsPanel(); });
  });
  el.querySelectorAll("[data-tx-sort]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var field = btn.dataset.txSort;
      if (_txSort.field === field) _txSort.dir = _txSort.dir === "asc" ? "desc" : "asc";
      else { _txSort.field = field; _txSort.dir = "asc"; }
      renderTransactionsPanel();
    });
  });
  el.querySelectorAll(".transaction-table tbody tr[data-tid]").forEach(function (tr) {
    function open() {
      _selectedTxn = tr.dataset.tid;
      renderTransactionsPanel();
    }
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  });

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
      '<div class="ev-row"><span class="ek">Confidence</span><span class="ev">' + (conf == null ? "Unavailable" : pct(conf) + "%") + '</span></div>' +
      '<div class="ev-row"><span class="ek">Rationale</span><span class="ev">' + esc(review.rationale || "—") + '</span></div>' +
      '<div class="ev-row"><span class="ek">Evidence</span><span class="ev">' + esc(JSON.stringify(review.evidence || {})) + '</span></div>' +
      '</div>';
    button.textContent = "Reviewed";
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
    button.textContent = "Retry adjudication";
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
    button.textContent = "Retry split adjudication";
    alert("Retry failed: " + err.message);
  }
}

function humanizeKey(key) {
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
}

function evidenceText(value) {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return "[" + value.map(evidenceText).join(", ") + "]";
  if (typeof value === "object") {
    return Object.entries(value).map(function (pair) {
      return humanizeKey(pair[0]) + ": " + evidenceText(pair[1]);
    }).join(" · ");
  }
  return String(value);
}

function evidenceValueHtml(value) {
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    return '<div class="evidence-list">' + value.map(function (item) {
      return '<span class="evidence-chip">' + esc(evidenceText(item)) + "</span>";
    }).join("") + "</div>";
  }
  if (value !== null && typeof value === "object") {
    return '<div class="evidence-nested">' + Object.entries(value).map(function (pair) {
      return "<div><strong>" + esc(humanizeKey(pair[0])) + ":</strong> " + esc(evidenceText(pair[1])) + "</div>";
    }).join("") + "</div>";
  }
  return esc(evidenceText(value));
}

function sourceRowsHtml(matchedRecords, bankRowIds) {
  var rows = [];
  var seen = {};
  function add(source, id) {
    if (!id) return;
    var key = source + ":" + id;
    if (seen[key]) return;
    seen[key] = true;
    rows.push([source, id]);
  }
  add("Gateway", matchedRecords.gateway);
  add("Bank", matchedRecords.bank);
  add("Ledger", matchedRecords.ledger);
  (bankRowIds || []).forEach(function (id) { add("Bank", id); });
  if (!rows.length) return "";
  return '<section class="detail-section" aria-labelledby="source-rows-heading"><div class="section-kicker">Source trace</div><h3 id="source-rows-heading">Source rows</h3><div class="source-row-chips">' +
    rows.map(function (row) {
      return '<span class="source-row-chip"><strong>' + esc(row[0]) + "</strong> " + esc(row[1]) + "</span>";
    }).join("") + "</div></section>";
}

function renderDetail(d) {
  var ev = d.evidence || {};
  var mr = d.matched_records || {};
  var evEntries = Object.entries(ev).filter(function (pair) { return pair[1] !== null && pair[1] !== undefined; });
  var bankRowIds = d.bank_row_ids || [];
  var settlement = d.settlement || {};
  var isStage3 = d.tier === "STAGE_3";
  var gw = mr.gateway || "—";
  var bn = mr.bank || "—";
  var lg = mr.ledger || "—";
  var amount = firstValue(d.gateway_amount, settlement.gross_amount, d.amount, d.received);
  var expected = firstValue(settlement.expected_net_amount, d.expected_net);
  var actual = settlement.actual_bank_amount;
  var variance = settlement.variance;
  var status = d.status || "UNKNOWN";

  var settlementBlock = "";
  if (isStage3 && settlement && Object.keys(settlement).length > 0) {
    settlementBlock = '<section class="detail-section settlement-section" aria-labelledby="settlement-heading"><div class="section-kicker">Settlement analysis</div><h3 id="settlement-heading">Expected vs actual</h3><div class="expected-actual"><div><span>Expected net</span><strong>' + fmtMoney(expected) + '</strong></div><div><span>Actual bank</span><strong>' + fmtMoney(actual) + '</strong></div><div class="variance-value"><span>Variance</span><strong class="' + moneyClass(variance) + '">' + fmtMoney(variance) + '</strong></div></div><div class="settlement-grid settlement-grid-detail">' +
      settlementItem("Gross", settlement.gross_amount, "") +
      settlementItem("GST", settlement.gst_amount, "positive") +
      settlementItem("TDS", settlement.tds_amount, "negative") +
      settlementItem("MDR", settlement.mdr_amount, "negative") +
      settlementItem("Fees", settlement.total_fee_amount, "negative") +
      settlementItem("Refund", settlement.refund_amount, "negative") +
      settlementItem("Expected net", settlement.expected_net_amount, "") +
      settlementItem("Actual bank", settlement.actual_bank_amount, "") +
    '</div></section>';
  } else {
    settlementBlock = '<section class="detail-section muted-section" aria-labelledby="settlement-heading"><div class="section-kicker">Settlement analysis</div><h3 id="settlement-heading">Not evaluated at this tier</h3><p>Settlement breakdown is available only for transactions resolved by the Stage 3 split-settlement pass.</p></section>';
  }

  var partialBlock = "";
  if (isStage3 && status === "PARTIAL_PAYMENT") {
    partialBlock = '<div class="partial-summary"><div><span>Received</span><strong>' + fmtMoney(d.received) + '</strong></div><div><span>Outstanding</span><strong class="negative">' + fmtMoney(d.outstanding) + '</strong></div></div>';
  }

  var bankHtml = "";
  if (isStage3 && bankRowIds.length > 0) {
    bankHtml = '<div class="detail-field"><div class="df-label">Bank row evidence</div><div class="bank-rows">';
    bankRowIds.forEach(function (id) {
      bankHtml += '<div class="bank-row"><span class="id">' + esc(id) + '</span><span class="amount credit">credit</span></div>';
    });
    bankHtml += '</div></div>';
  } else {
    bankHtml = detailField("Bank row", esc(bn));
  }

  var sourceHtml = sourceRowsHtml(mr, bankRowIds);
  var evidenceHtml = evEntries.length > 0 ?
    '<section class="detail-section evidence-section" aria-labelledby="evidence-heading"><div class="section-kicker">Matching evidence</div><h3 id="evidence-heading">Evidence</h3>' +
    evEntries.map(function (pair) {
      return '<div class="ev-row"><span class="ek">' + esc(humanizeKey(pair[0])) + '</span><span class="ev">' + evidenceValueHtml(pair[1]) + "</span></div>";
    }).join("") + '</section>' :
    '<section class="detail-section muted-section" aria-labelledby="evidence-heading"><div class="section-kicker">Matching evidence</div><h3 id="evidence-heading">No structured evidence returned</h3><p>The transaction detail contains no additional evidence fields.</p></section>';

  var timelineHtml = '<section class="detail-section timeline-section" aria-labelledby="timeline-heading"><div class="section-kicker">Investigation sequence</div><h3 id="timeline-heading">What happened</h3><ol class="timeline-list"><li><span>Source records</span><strong>Gateway, bank, and ledger rows indexed</strong></li><li><span>Resolution tier</span><strong>' + esc(d.tier || "—") + '</strong></li><li><span>Authoritative result</span><strong>' + chip(status) + '</strong></li>' + (isStage3 ? '<li><span>Settlement pass</span><strong>Split settlement evaluated</strong></li>' : '') + '</ol><p class="surface-note">Timestamps and queue age are not exposed by the current transaction API; no values are inferred.</p></section>';

  var llmBlock = "";
  if (d.llm_consulted !== undefined) {
    var rec = d.llm_recommendation;
    llmBlock = '<section class="detail-section ai-history" aria-labelledby="ai-history-heading"><div class="section-kicker">Advisory history</div><h3 id="ai-history-heading">AI history</h3><div class="ev-row"><span class="ek">AI consulted</span><span class="ev">' + (d.llm_consulted ? "Yes" : "No") + '</span></div>' +
      (d.confidence != null ? '<div class="ev-row"><span class="ek">Advisory confidence</span><span class="ev">' + pct(d.confidence * 100) + '%</span></div>' : '') +
      (rec ? '<div class="ev-row"><span class="ek">Recommendation</span><span class="ev">' + esc(rec.decision || "—") + " · bank IDs: " + evidenceValueHtml(rec.bank_row_ids || []) + "</span></div>" : '') + '</section>';
  }

  var confHtml = "";
  if (d.confidence != null) {
    var p = Math.round(d.confidence * 100);
    var cls = p < 50 ? "critical" : (p < 75 ? "low" : "");
    confHtml = detailField("Advisory confidence", '<div class="confidence-bar"><div class="confidence-fill ' + cls + '" style="width:' + p + '%"></div></div><span style="font-size:0.75rem;color:var(--text-3)">' + p + '%</span>');
  }

  var retryBtn = "";
  if (status === "AI_RETRY_REQUIRED") {
    if (d.tier === "TIER_3") retryBtn = '<button class="retry-btn" data-retry-llm>Retry adjudication</button>';
    else if (d.tier === "STAGE_3") retryBtn = '<button class="retry-btn" data-retry-stage3>Retry split adjudication</button>';
  }
  var reviewBtn = '<button class="retry-btn review-btn" data-ai-review>Explain with AI · read-only</button>';

  return '<article class="detail-card"><div class="detail-head"><div class="detail-title-group"><span class="detail-tid">' + esc(d.transaction_id || "—") + '</span><span class="detail-subtitle">Financial investigation</span></div><div class="detail-actions">' + chip(status) + tierChip(d.tier) + retryBtn + reviewBtn + '</div></div><div class="detail-body"><div class="next-action"><span>Next action</span><strong>' + esc(nextActionFor(status)) + '</strong></div><div class="detail-grid"><div><section class="detail-section" aria-labelledby="financial-heading"><div class="section-kicker">Financial context</div><h3 id="financial-heading">Transaction position</h3><div class="financial-summary"><div><span>Amount</span><strong>' + fmtMoney(amount) + '</strong></div><div><span>Match state</span><strong>' + esc(matchState(status)) + '</strong></div><div><span>Exception state</span><strong>' + esc(exceptionState(status)) + '</strong></div></div>' + detailField("Rule", esc(d.rule || "—")) + detailField("Reason", esc(d.reason || "—")) + confHtml + detailField("Gateway row", esc(gw)) + bankHtml + detailField("Ledger row", esc(lg)) + partialBlock + '</section>' + timelineHtml + '</div><div>' + settlementBlock + sourceHtml + evidenceHtml + llmBlock + '<div data-ai-review-result></div></div></div></div></article>';
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

var _chatSuggestions = [
  "Which transactions need human review?",
  "Show unresolved transactions.",
  "Show partial payments.",
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
  el.innerHTML = loadingHtml("Loading deterministic settlement position…");

  Promise.all([
    fetchJson("/api/overview"),
    fetchJson("/api/transactions")
  ]).then(function (responses) {
    renderSettlementWorkspace(responses[0], responses[1]);
    setupQAComposer();
  }).catch(function (err) {
    el.innerHTML = retryErrorHtml(err.message, "settlement");
    attachRetryAction("settlement", function () {
      _qaInited = false;
      initQA();
    });
  });
}

function renderSettlementWorkspace(overview, transactionData) {
  var el = document.getElementById("qa-content");
  var t4 = overview.stage3_summary || {};
  var rows = (transactionData.transactions || []).filter(function (r) {
    return r.tier === "STAGE_3" && r.settlement && Object.keys(r.settlement).length > 0;
  });
  var promptTransaction = rows.length ? rows[0].transaction_id : null;
  var lookupPrompt = promptTransaction ? "What happened to " + promptTransaction + "?" : "Show unresolved transactions.";
  var variancePrompt = promptTransaction ? "What is the variance for " + promptTransaction + "?" : "Which transactions need human review?";
  var promptLabel = promptTransaction || "the current queue";
  function sum(key) {
    return rows.reduce(function (total, r) {
      var n = Number(r.settlement[key] || 0);
      return total + (isFinite(n) ? n : 0);
    }, 0);
  }
  var expected = sum("expected_net_amount");
  var actual = sum("actual_bank_amount");
  var variance = sum("variance");
  var fees = sum("total_fee_amount") + sum("mdr_amount");
  var taxes = sum("gst_amount") + sum("tds_amount");
  var refunds = sum("refund_amount");
  var evaluated = count(t4.total_evaluated);
  var statusRows = [
    ["Settled", count(t4.match_count), "match"],
    ["Partial", count(t4.partial_count), "review"],
    ["Unresolved / ambiguous", count(t4.unresolved_count) + count(t4.ambiguous_count), "attention"]
  ];
  var reasons = rows.filter(function (r) {
    return !isMatched(r.status) || (r.settlement.variance && Math.abs(Number(r.settlement.variance)) > 0.01);
  }).slice(0, 8);
  var evidence = rows.slice(0, 8);

  var reasonRows = reasons.length ? reasons.map(function (r) {
    return '<li><span class="table-primary">' + esc(r.transaction_id) + '</span><span>' + esc(r.reason || r.status) + '</span><span class="num">' + fmtMoney(r.settlement.variance) + '</span></li>';
  }).join("") : '<li class="empty-list">No settlement mismatches in the current data.</li>';
  var evidenceRows = evidence.length ? evidence.map(function (r) {
    var ids = [r.gateway_row].concat(r.bank_row_ids || [], r.ledger_row || []).filter(Boolean);
    return '<li><span class="table-primary">' + esc(r.transaction_id) + '</span><span>' + esc(ids.join(" · ") || "Source rows not exposed") + '</span></li>';
  }).join("") : '<li class="empty-list">No Stage 3 evidence rows.</li>';

  el.innerHTML =
    '<div class="settlement-workspace">' +
      '<section class="settlement-position" aria-labelledby="position-title"><div class="settlement-position-head"><div><span class="eyebrow">Current financial position</span><h2 id="position-title">Settlement position</h2><p>Expected net, actual bank settlement, and calculated variance from Stage 3 results.</p></div><span class="settlement-scope-note">' + rows.length + ' Stage 3 transactions with settlement detail</span></div><div class="position-metrics"><div><span>Expected net</span><strong>' + fmtMoney(expected) + '</strong></div><div><span>Actual bank</span><strong>' + fmtMoney(actual) + '</strong></div><div><span>Variance</span><strong class="' + moneyClass(variance) + '">' + fmtMoney(variance) + '</strong></div><div><span>Fees + MDR</span><strong>' + fmtMoney(fees) + '</strong></div><div><span>Taxes</span><strong>' + fmtMoney(taxes) + '</strong></div><div><span>Refunds</span><strong>' + fmtMoney(refunds) + '</strong></div></div></section>' +
      '<div class="settlement-grid-layout"><section class="surface-card" aria-labelledby="settlement-status-title"><div class="surface-head"><div><h2 id="settlement-status-title">Settlement status</h2><p>Stage 3 outcomes</p></div></div><div class="table-scroll"><table class="x-table"><thead><tr><th scope="col">State</th><th scope="col" class="num">Transactions</th><th scope="col" class="num">Share</th></tr></thead><tbody>' +
        statusRows.map(function (r) { return '<tr><td><span class="state-label state-' + r[2] + '">' + r[0] + '</span></td><td class="num">' + r[1] + '</td><td class="num">' + pct(evaluated ? r[1] / evaluated * 100 : 0) + '%</td></tr>'; }).join("") +
      '</tbody></table></div></section><section class="surface-card" aria-labelledby="settlement-reasons-title"><div class="surface-head"><div><h2 id="settlement-reasons-title">Mismatch reasons</h2><p>Supported reasons from settlement results</p></div><button class="text-action" data-jump-panel="exceptions">Open queue</button></div><ul class="reason-list">' + reasonRows + '</ul></section></div>' +
      '<div class="settlement-grid-layout"><section class="surface-card" aria-labelledby="settlement-evidence-title"><div class="surface-head"><div><h2 id="settlement-evidence-title">Settlement evidence</h2><p>Source rows attached to Stage 3 results</p></div><button class="text-action" data-jump-panel="transactions">Open explorer</button></div><ul class="evidence-list-table">' + evidenceRows + '</ul></section><section class="surface-card contextual-ai-surface" aria-labelledby="contextual-ai-title"><div class="surface-head"><div><h2 id="contextual-ai-title">Supported questions</h2><p>Grounded prompts for ' + esc(promptLabel) + '</p></div></div><div class="context-actions"><button class="btn btn-secondary btn-sm" data-qa-prompt="' + esc(lookupPrompt) + '">Explain transaction</button><button class="btn btn-secondary btn-sm" data-qa-prompt="' + esc(variancePrompt) + '">Show variance</button><button class="btn btn-secondary btn-sm" data-qa-prompt="Show unresolved transactions.">Show unresolved</button></div><p class="surface-note">AI is not invoked until you submit a question. Deterministic values and source evidence remain authoritative.</p></section></div>' +
      '<section class="qa-workspace" aria-labelledby="qa-title"><div class="qa-workspace-head"><div><span class="eyebrow">Grounded question</span><h2 id="qa-title">Ask about this run</h2></div><span>Deterministic answer first · citations retained · AI optional</span></div><div class="chat-messages" id="chat-messages"><div class="qa-empty-state"><strong>No question asked yet</strong><span>Use a contextual action or enter a bounded question below.</span></div></div><div class="chat-input-bar"><label class="sr-only" for="chat-input">Question about settlement evidence</label><textarea class="chat-input-field" id="chat-input" rows="1" placeholder="Ask about a transaction, variance, or settlement state…" autocomplete="off"></textarea><button class="chat-send-btn" id="chat-send-btn">Send</button></div></section>' +
    '</div>';
}

function setupQAComposer() {
  var el = document.getElementById("qa-content");
  var input = document.getElementById("chat-input");
  var btn = document.getElementById("chat-send-btn");
  if (!input || !btn) return;

  function submit() {
    var q = input.value.trim();
    if (!q || !q.trim()) return;
    input.value = "";
    autoResize(input);
    sendChat(q);
  }
  btn.addEventListener("click", submit);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  input.addEventListener("input", function () { autoResize(input); });
  el.querySelectorAll("[data-qa-prompt]").forEach(function (button) {
    button.addEventListener("click", function () {
      input.value = button.dataset.qaPrompt;
      autoResize(input);
      input.focus();
    });
  });
  var chatMsgs = document.getElementById("chat-messages");
  if (chatMsgs) {
    chatMsgs.addEventListener("click", function (e) {
      var actionButton = e.target.closest("[data-chat-action]");
      if (!actionButton) return;
      var action = actionButton.dataset.chatAction;
      var tid = actionButton.dataset.chatTid;
      if (!tid) return;
      if (action === "view-transaction") chatViewTransaction(tid);
      else if (action === "ai-review") chatAIReview(tid, actionButton);
      else if (action === "retry-llm") chatRetryLLM(tid, actionButton);
    });
  }
}

function autoResize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
}

function addUserMessage(q) {
  var msgs = document.getElementById("chat-messages");
  if (!msgs) return;
  var welcome = msgs.querySelector(".qa-empty-state");
  if (welcome) welcome.remove();

  var div = document.createElement("div");
  div.className = "chat-msg user";
  div.innerHTML = '<div class="chat-bubble">' + esc(q) + "</div>";
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addTypingIndicator() {
  var msgs = document.getElementById("chat-messages");
  if (!msgs) return;
  var div = document.createElement("div");
  div.className = "chat-msg ai";
  div.id = "chat-typing";
  div.setAttribute("role", "status");
  div.setAttribute("aria-label", "Checking the grounded answer");
  div.innerHTML = '<div class="chat-bubble"><div class="typing-indicator"><span class="sr-only">Checking the grounded answer…</span><span class="typing-label">Checking grounded evidence</span></div></div>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function removeTypingIndicator() {
  var el = document.getElementById("chat-typing");
  if (el) el.remove();
}

async function sendChat(q) {
  addUserMessage(q);
  addTypingIndicator();

  try {
    var res = await fetch(API + "/api/qa", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q}),
    });
    var data = await res.json();
    if (!res.ok) throw new Error(data.error || "Question could not be answered");
    removeTypingIndicator();
    addAIResponse(data);
    updateFollowUps(data);
  } catch (err) {
    removeTypingIndicator();
    addAIError(err.message);
  }
}

function chatCitationsHtml(citations) {
  if (!Array.isArray(citations) || citations.length === 0) return "";
  return '<div class="chat-citations"><span>Evidence</span>' +
    citations.map(function (citation) {
      var source = citation.source || "source";
      var rowId = citation.source_row_id || "—";
      return '<span class="chat-citation">' + esc(source) + " " + esc(rowId) + "</span>";
    }).join("") + "</div>";
}

function addAIResponse(data) {
  var msgs = document.getElementById("chat-messages");
  var div = document.createElement("div");
  div.className = "chat-msg ai";

  var isFinancial = data.source === "DETERMINISTIC_SETTLEMENT" && data.field && data.value !== undefined;
  var intent = isFinancial ? "settlement value" : (data.intent || "UNKNOWN").replace("INTENT_", "").toLowerCase();
  var intentClass = isFinancial ? "filter" : intent;
  if (intent === "filter_status" || intent === "filter_rule") intentClass = "filter";
  if (intent === "unsupported") intentClass = "unsupported";

  var answer = data.explanation || (isFinancial ? "This value comes from the completed deterministic settlement result." : "No explanation returned.");
  var tid = (data.transaction_ids && data.transaction_ids[0]) || null;
  var firstRetrieved = data.retrieved_data && data.retrieved_data.length > 0 ? data.retrieved_data[0] : null;
  var actionStatus = firstRetrieved ? firstRetrieved.status : data.status;
  var actionTier = firstRetrieved ? firstRetrieved.tier : data.tier;

  var rows = [];
  if (tid) rows.push(["Transaction", tid]);
  if (isFinancial) {
    rows.push(["Field", humanizeKey(data.field)]);
    rows.push(["Value", fmtMoney(data.value)]);
    rows.push(["Source", "Deterministic settlement"]);
  } else if (firstRetrieved) {
    if (firstRetrieved.status) rows.push(["Status", firstRetrieved.status]);
    if (firstRetrieved.tier) rows.push(["Tier", firstRetrieved.tier]);
    if (firstRetrieved.rule) rows.push(["Rule", firstRetrieved.rule]);
    if (firstRetrieved.reason) rows.push(["Reason", firstRetrieved.reason]);
  }
  var infoHtml = rows.length > 0 ? '<div class="chat-info-rows">' + rows.map(function (row) {
    return '<div class="chat-info-row"><span class="chat-info-key">' + esc(row[0]) + '</span><span class="chat-info-val">' + esc(String(row[1])) + "</span></div>";
  }).join("") + "</div>" : "";

  var confHtml = "";
  if (firstRetrieved && firstRetrieved.confidence != null) {
    var confidence = Math.round(Number(firstRetrieved.confidence) * 100);
    var confClass = confidence >= 75 ? "high" : (confidence >= 50 ? "medium" : "low");
    confHtml = '<div class="chat-confidence"><span class="chat-confidence-label">Advisory confidence</span>' +
      '<div class="chat-confidence-bar"><div class="chat-confidence-fill ' + confClass + '" style="width:' + confidence + '%"></div></div>' +
      '<span class="chat-confidence-val">' + confidence + "%</span></div>";
  }

  var meta = [];
  if (isFinancial) meta.push("Deterministic answer");
  else if (data.llm_used) meta.push("AI-assisted explanation");
  else meta.push("Stored evidence answer");
  if (data.llm_unavailable) meta.push("AI unavailable · deterministic fallback");
  if (data.found === false) meta.push("Not found");
  if (data.supported === false) meta.push("Unsupported");
  var metaHtml = meta.length > 0 ? '<div class="chat-meta">' + meta.map(function (item) { return "<span>" + esc(item) + "</span>"; }).join("") + "</div>" : "";

  var actions = [];
  if (tid) {
    actions.push('<button class="chat-action-btn primary" data-chat-action="view-transaction" data-chat-tid="' + esc(tid) + '">View transaction</button>');
    actions.push('<button class="chat-action-btn" data-chat-action="ai-review" data-chat-tid="' + esc(tid) + '">Review with AI · read-only</button>');
  }
  if (actionStatus === "AI_RETRY_REQUIRED" && actionTier === "TIER_3" && tid) {
    actions.push('<button class="chat-action-btn" data-chat-action="retry-llm" data-chat-tid="' + esc(tid) + '">Retry adjudication</button>');
  }
  var actionsHtml = actions.length > 0 ? '<div class="chat-actions">' + actions.join("") + "</div>" : "";
  var valueHtml = isFinancial ? '<div class="deterministic-value"><span>Deterministic value</span><strong>' + fmtMoney(data.value) + "</strong></div>" : "";

  div.innerHTML =
    '<div class="chat-bubble"><div class="chat-card">' +
      '<div class="chat-card-head"><span class="intent-badge ' + intentClass + '">' + esc(intent.replace(/_/g, " ")) + "</span></div>" +
      '<div class="chat-card-body">' + esc(answer) + "</div>" +
      valueHtml + infoHtml + confHtml + chatCitationsHtml(data.citations) + metaHtml + actionsHtml +
    "</div></div>";

  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addAIError(msg) {
  var msgs = document.getElementById("chat-messages");
  var div = document.createElement("div");
  div.className = "chat-msg ai";
  div.innerHTML =
    '<div class="chat-bubble"><div class="chat-card">' +
      '<div class="chat-card-body error-response">Error: ' + esc(msg) + '</div>' +
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
  _selectedTxn = tid;
  switchPanel("transactions");
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
          (data.source === "DETERMINISTIC_FALLBACK" ? "Stored Evidence Review" : "AI Review Result") +
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
    div.innerHTML = '<div class="chat-bubble">' + resultHtml + "</div>";
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    button.textContent = "Reviewed";
  } catch (err) {
    button.disabled = false;
    button.textContent = "AI Review";
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
      '<div class="chat-bubble"><div class="chat-card">' +
        '<div class="chat-card-head"><span class="intent-badge">RETRY RESULT</span></div>' +
        '<div class="chat-card-body">Transaction <strong>' + esc(tid) + '</strong> is now: <span style="color:' + color + ';font-weight:600">' + esc(status) + '</span></div>' +
      '</div></div>';
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    button.textContent = "Done";
  } catch (err) {
    button.disabled = false;
    button.textContent = "Retry adjudication";
    alert("Retry failed: " + err.message);
  }
}

/* ════════════════════════════════════════════════════════════
   Initial load
   ════════════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", function () {
  var initialPanel = window.location.hash.replace(/^#/, "");
  switchPanel(PANEL_META[initialPanel] ? initialPanel : "overview");
});

})();
