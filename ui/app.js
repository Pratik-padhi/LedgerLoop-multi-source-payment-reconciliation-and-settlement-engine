/* ═══════════════════════════════════════════════════════════════════════
   LedgerLoop Controller UI — Application Logic
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
"use strict";

const API = "";
let _overview = null;
let _exceptions = null;
let _selected = null;
let _qaInited = false;
let _qaHist = [];

/* ── Helpers ─────────────────────────────────────────────── */

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/&/g,"&").replace(/</g,"<").replace(/>/g,">").replace(/"/g,""");
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
  return `<span class="chip chip-${c}">${esc(status)}</span>`;
}

function tierChip(t) {
  return `<span class="chip chip-tier">${esc(t)}</span>`;
}

function llmChip(v) {
  return v ? `<span class="chip chip-yes">Yes</span>` : `<span class="chip chip-no">No</span>`;
}

function fmtMoney(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  return "₹" + n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

/* ── Theme ───────────────────────────────────────────────── */

function initTheme() {
  const saved = localStorage.getItem("ll-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  updateThemeBtn();
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme");
  let next;
  if (cur === "dark") next = "light";
  else if (cur === "light") next = "";
  else next = "dark";
  if (next) document.documentElement.setAttribute("data-theme", next);
  else document.documentElement.removeAttribute("data-theme");
  localStorage.setItem("ll-theme", next);
  updateThemeBtn();
}

function updateThemeBtn() {
  const cur = document.documentElement.getAttribute("data-theme");
  const dark = cur === "dark" || (!cur && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.getElementById("theme-icon").textContent = dark ? "☀️" : "🌙";
  document.getElementById("theme-label").textContent = dark ? "Light" : "Dark";
}

document.addEventListener("DOMContentLoaded", function () {
  document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
  initTheme();
});

/* ── Navigation ──────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", function () {
  document.getElementById("nav").addEventListener("click", function (e) {
    const btn = e.target.closest(".nav-item");
    if (!btn) return;
    const pid = "panel-" + btn.dataset.panel;
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    document.getElementById(pid).classList.add("active");
    if (pid === "panel-overview" && !_overview) loadOverview();
    if (pid === "panel-exceptions" && !_exceptions) loadExceptions();
    if (pid === "panel-qa" && !_qaInited) initQA();
  });
});

/* ════════════════════════════════════════════════════════════
   Overview
   ════════════════════════════════════════════════════════════ */

async function loadOverview() {
  const el = document.getElementById("overview-content");
  try {
    const res = await fetch(API + "/api/overview");
    if (!res.ok) throw new Error(res.statusText);
    _overview = await res.json();
  } catch (err) {
    el.innerHTML = `<div class="empty-msg">Could not load overview — ${esc(err.message)}</div>`;
    return;
  }
  renderOverview();
}

function renderOverview() {
  const d = _overview;
  const el = document.getElementById("overview-content");
  const sc = d.status_counts || {};
  const hr  = sc.HUMAN_REVIEW || 0;
  const unr = sc.UNRESOLVED || 0;
  const mt  = sc.MATCH || sc.MATCHED || 0;
  const prt = sc.PARTIAL_MATCH || 0;
  const uft = sc.UNRESOLVED_FOR_TIER_1 || 0;
  const total = d.total_transactions;

  // nav badge (human review + unresolved)
  const badgeCount = hr + unr;
  const badge = document.getElementById("exc-badge");
  if (badgeCount > 0) {
    badge.textContent = badgeCount;
    badge.style.display = "";
  } else {
    badge.style.display = "none";
  }

  // Tier counts
  const tc = d.tier_counts || {};

  // Rule counts
  const rc = d.rule_counts || {};
  const ruleEntries = Object.entries(rc).sort((a,b) => b[1]-a[1]).slice(0, 10);

  el.innerHTML = `
    <div class="card" style="margin-bottom:1.5rem">
      <div class="card-head"><h2>Reconciliation Overview</h2></div>
      <div class="card-body">
        <div class="stats-grid">
          <div class="stat-card match">
            <div class="label">Matched</div>
            <div class="value">${mt}</div>
            <div class="tier">
              ${tc.TIER_1 ? `<span class="chip chip-tier">TIER_1: ${tc.TIER_1}</span>` : ""}
              ${tc.TIER_2 ? `<span class="chip chip-tier">TIER_2: ${tc.TIER_2}</span>` : ""}
              ${tc.TIER_3 ? `<span class="chip chip-tier">TIER_3: ${tc.TIER_3}</span>` : ""}
              ${tc.STAGE_3 ? `<span class="chip chip-tier">STAGE_3: ${tc.STAGE_3}</span>` : ""}
            </div>
          </div>
          <div class="stat-card review">
            <div class="label">Human Review</div>
            <div class="value">${hr}</div>
            <div class="tier">${chip("HUMAN_REVIEW")}</div>
          </div>
          <div class="stat-card unresolved">
            <div class="label">Unresolved</div>
            <div class="value">${unr}</div>
            <div class="tier">${chip("UNRESOLVED")}</div>
          </div>
          <div class="stat-card">
            <div class="label">Total Transactions</div>
            <div class="value">${total}</div>
            <div class="tier">Partial: ${prt} · Tier1 Unres: ${uft}</div>
          </div>
        </div>

        ${d.stage3_summary ? `
        <div class="card" style="margin-top:1rem">
          <div class="card-head"><h3>Stage 3 — Split / Multi-Payment Pass</h3></div>
          <div class="card-body">
            <div class="stats-grid">
              <div class="stat-card match">
                <div class="label">Split Matched</div>
                <div class="value">${d.stage3_summary.match_count || 0}</div>
              </div>
              <div class="stat-card review">
                <div class="label">Partial Payments</div>
                <div class="value">${d.stage3_summary.partial_count || 0}</div>
              </div>
              <div class="stat-card review">
                <div class="label">Ambiguous</div>
                <div class="value">${d.stage3_summary.ambiguous_count || 0}</div>
              </div>
              <div class="stat-card review">
                <div class="label">AI Retry Required</div>
                <div class="value">${d.stage3_summary.ai_retry_count || 0}</div>
              </div>
              <div class="stat-card unresolved">
                <div class="label">Unresolved</div>
                <div class="value">${d.stage3_summary.unresolved_count || 0}</div>
              </div>
              <div class="stat-card">
                <div class="label">Evaluated</div>
                <div class="value">${d.stage3_summary.total_evaluated || 0}</div>
              </div>
            </div>
          </div>
        </div>
        ` : ""}

        <div class="card">
          <div class="card-head"><h3>Top Rules</h3></div>
          <div class="card-body">
            ${ruleEntries.length === 0
              ? '<div class="empty-msg">No rule data</div>'
              : `
            <table class="x-table">
              <thead><tr><th>Rule</th><th style="font-variant-numeric:tabular-nums;font-weight:600">Count</th></tr></thead>
              <tbody>
                ${ruleEntries.map(([k,v]) => `
                  <tr><td>${esc(k)}</td><td style="font-variant-numeric:tabular-nums;font-weight:600">${v}</td></tr>`).join("")}
              </tbody>
            </table>
            `}
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3>LLM Usage</h3></div>
          <div class="card-body">
            <table class="x-table">
              <thead><tr><th>Metric</th><th style="font-variant-numeric:tabular-nums;font-weight:600">Value</th></tr></thead>
              <tbody>
                <tr><td>Gemini calls made</td><td style="font-variant-numeric:tabular-nums;font-weight:600">${d.llm_calls_made || 0}</td></tr>
                <tr><td>Recommendations validated</td><td style="font-variant-numeric:tabular-nums;font-weight:600">${d.llm_recommendations_validated || 0}</td></tr>
                <tr><td>Recommendations rejected</td><td style="font-variant-numeric:tabular-nums;font-weight:600">${d.llm_recommendations_rejected || 0}</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `;
}

/* ════════════════════════════════════════════════════════════
   Exceptions
   ════════════════════════════════════════════════════════════ */

async function loadExceptions() {
  const el = document.getElementById("exceptions-content");
  try {
    const res = await fetch(API + "/api/exceptions");
    if (!res.ok) throw new Error(res.statusText);
    _exceptions = await res.json();
  } catch (err) {
    el.innerHTML = `<div class="empty-msg">Could not load exceptions — ${esc(err.message)}</div>`;
    return;
  }
  _selected = null;
  renderExceptions("ALL");
}

function renderExceptions(filter) {
  if (!_exceptions) return;
  const el = document.getElementById("exceptions-content");
  let items = _exceptions.exceptions || [];

  if (filter === "HUMAN_REVIEW") items = items.filter(e => e.status === "HUMAN_REVIEW");
  if (filter === "UNRESOLVED")   items = items.filter(e => e.status === "UNRESOLVED");
  if (filter === "AI_RETRY")     items = items.filter(e => e.status === "AI_RETRY_REQUIRED");
  if (filter === "AMBIGUOUS")    items = items.filter(e => e.status === "AMBIGUOUS");
  if (filter === "PARTIAL")      items = items.filter(e => e.status === "PARTIAL_PAYMENT");

  el.innerHTML = `
    <div class="filter-bar">
      <button class="filter-btn ${filter === "ALL" ? "active" : ""}" data-filter="ALL">All</button>
      <button class="filter-btn ${filter === "HUMAN_REVIEW" ? "active" : ""}" data-filter="HUMAN_REVIEW">Human Review</button>
      <button class="filter-btn ${filter === "UNRESOLVED" ? "active" : ""}" data-filter="UNRESOLVED">Unresolved</button>
      <button class="filter-btn ${filter === "AI_RETRY" ? "active" : ""}" data-filter="AI_RETRY">AI Retry Required</button>
      <button class="filter-btn ${filter === "AMBIGUOUS" ? "active" : ""}" data-filter="AMBIGUOUS">Ambiguous</button>
      <button class="filter-btn ${filter === "PARTIAL" ? "active" : ""}" data-filter="PARTIAL">Partial Payment</button>
    </div>
    <div class="exc-split">
      <div>
        <div class="card" style="margin-bottom:0;height:100%">
          <div class="card-head"><h3>${items.length} exception${items.length !== 1 ? "s" : ""}</h3></div>
          <div class="card-body" style="padding:0;overflow:auto">
            <table class="x-table">
              <thead><tr><th>Transaction</th><th>Status</th><th>Rule</th></tr></thead>
              <tbody>
              ${items.length === 0
                ? `<tr><td colspan="3" class="empty">No exceptions in this category</td></tr>`
                : items.map(e => `
                  <tr data-tid="${esc(e.transaction_id)}" class="${_selected === e.transaction_id ? "selected" : ""}">
                    <td>${esc(e.transaction_id)} ${e.llm_consulted ? '<span class="chip chip-tier" style="margin-left:4px">LLM</span>' : ""}</td>
                    <td>${chip(e.status)}</td>
                    <td style="font-size:11px;color:var(--text-3)">${esc(e.rule || "—")}</td>
                  </tr>`).join("")}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <div id="exc-detail">
        ${_selected ? "" : `<div class="empty-msg" style="padding:50px 20px">Select a transaction to view details</div>`}
      </div>
    </div>
  `;

  // Row clicks
  el.querySelectorAll(".x-table tbody tr[data-tid]").forEach(tr => {
    tr.addEventListener("click", () => {
      _selected = tr.dataset.tid;
      renderExceptions(filter);
      loadDetail(_selected);
    });
  });

  // Filter clicks
  el.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => renderExceptions(btn.dataset.filter));
  });

  if (_selected) loadDetail(_selected);
}

/* ════════════════════════════════════════════════════════════
   Detail View
   ════════════════════════════════════════════════════════════ */

async function loadDetail(tid) {
  const box = document.getElementById("exc-detail");
  if (!box) return;
  box.innerHTML = `<div class="loading" style="padding:30px">Loading ${esc(tid)}…</div>`;
  try {
    const res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid));
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      box.innerHTML = `<div class="empty-msg">${esc(err.error || "Not found")}</div>`;
      return;
    }
    box.innerHTML = renderDetail(await res.json());
    attachRetryListeners(tid, box);
  } catch (err) {
    box.innerHTML = `<div class="empty-msg">${esc(err.message)}</div>`;
  }
}

function attachRetryListeners(tid, box) {
  // Tier 3 retry (AI_RETRY_REQUIRED)
  const retryT3 = box.querySelector("[data-retry-llm]");
  if (retryT3) {
    retryT3.addEventListener("click", () => retryGemini(tid, retryT3));
  }

  // Stage 3 retry (AI_RETRY_REQUIRED)
  const retryS3 = box.querySelector("[data-retry-stage3]");
  if (retryS3) {
    retryS3.addEventListener("click", () => retryStage3(tid, retryS3));
  }
}

async function retryGemini(tid, button) {
  button.disabled = true;
  button.textContent = "Retrying Gemini...";
  try {
    const res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid) + "/retry-llm", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
    });
    const data = await res.json();
    if (res.status === 503) {
      const box = document.getElementById("exc-detail");
      box.innerHTML = renderDetail(data);
      attachRetryListeners(tid, box);
      return;
    }
    // Refresh exception list & detail
    await loadExceptions();
    loadDetail(tid);
  } catch (err) {
    button.disabled = false;
    button.textContent = "Retry Gemini";
    alert("Retry failed: " + err.message);
  }
}

async function retryStage3(tid, button) {
  button.disabled = true;
  button.textContent = "Retrying Stage 3...";
  try {
    const res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid) + "/retry-stage3", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
    });
    const data = await res.json();
    if (res.status === 503) {
      const box = document.getElementById("exc-detail");
      box.innerHTML = renderDetail(data);
      attachRetryListeners(tid, box);
      return;
    }
    // Refresh exception list & detail
    await loadExceptions();
    loadDetail(tid);
  } catch (err) {
    button.disabled = false;
    button.textContent = "Retry Stage 3";
    alert("Retry failed: " + err.message);
  }
}

function renderDetail(d) {
  const ev = d.evidence || {};
  const mr = d.matched_records || {};
  const evEntries = Object.entries(ev).filter(([,v]) => v !== null && v !== undefined);
  const gw = mr.gateway || "—";
  const bn = mr.bank || "—";
  const lg = mr.ledger || "—";

  // Stage 3 specific fields
  const bankRowIds = d.bank_row_ids || [];
  const received = d.received;
  const outstanding = d.outstanding;
  const settlement = d.settlement || {};
  const isStage3 = d.tier === "STAGE_3";

  // LLM block
  let llmBlock = "";
  if (d.llm_consulted !== undefined) {
    const rec = d.llm_recommendation;
    llmBlock = `
      <div class="detail-field"><div class="df-label">LLM Consulted</div><div class="df-value">${llmChip(d.llm_consulted)}</div></div>
      ${d.confidence !== null && d.confidence !== undefined ? `<div class="detail-field"><div class="df-label">Confidence</div><div class="df-value">${esc(d.confidence)}</div></div>` : ""}
      ${rec ? `<div class="detail-field"><div class="df-label">LLM Recommendation</div>
        <div class="df-value mono">${esc(rec.decision || "—")} — bank IDs: ${esc(JSON.stringify(rec.bank_row_ids || []))}</div>
      </div>` : ""}`;
  }

  // Settlement breakdown for Stage 3
  let settlementBlock = "";
  if (isStage3 && Object.keys(settlement).length > 0) {
    const se = settlement;
    settlementBlock = `
      <div class="settlement-block">
        <h4>Settlement Breakdown</h4>
        <div class="settlement-grid">
          <div class="settlement-item">
            <span class="settlement-label">Gross</span>
            <span class="settlement-value">${fmtMoney(se.gross_amount)}</span>
          </div>
          <div class="settlement-item">
            <span class="settlement-label">GST (additive)</span>
            <span class="settlement-value positive">${fmtMoney(se.gst_amount)}</span>
          </div>
          <div class="settlement-item">
            <span class="settlement-label">TDS</span>
            <span class="settlement-value negative">${fmtMoney(se.tds_amount)}</span>
          </div>
          <div class="settlement-item">
            <span class="settlement-label">Total Fees</span>
            <span class="settlement-value negative">${fmtMoney(se.total_fee_amount)}</span>
          </div>
          <div class="settlement-item">
            <span class="settlement-label">Refund</span>
            <span class="settlement-value negative">${fmtMoney(se.refund_amount)}</span>
          </div>
          <div class="settlement-item">
            <span class="settlement-label">Expected Net</span>
            <span class="settlement-value">${fmtMoney(se.expected_net_amount)}</span>
          </div>
          <div class="settlement-item">
            <span class="settlement-label">Actual Bank</span>
            <span class="settlement-value">${fmtMoney(se.actual_bank_amount)}</span>
          </div>
          <div class="settlement-item">
            <span class="settlement-label">Variance</span>
            <span class="settlement-value ${(se.variance || 0) > 0.01 ? 'negative' : (se.variance || 0) < -0.01 ? 'positive' : 'zero'}">${fmtMoney(se.variance)}</span>
          </div>
        </div>
      </div>`;
  }

  // Partial payment indicator
  let partialBlock = "";
  if (isStage3 && d.status === "PARTIAL_PAYMENT") {
    partialBlock = `
      <div class="detail-field">
        <div class="df-label">Received</div>
        <div class="df-value">${fmtMoney(received)}</div>
      </div>
      <div class="detail-field">
        <div class="df-label">Outstanding</div>
        <div class="df-value negative">${fmtMoney(outstanding)}</div>
      </div>
      <div class="detail-field">
        <div class="df-label">Expected Net</div>
        <div class="df-value">${fmtMoney(d.expected_net)}</div>
      </div>`;
  }

  // Bank rows display for Stage 3
  let bankRowsHtml = "";
  if (isStage3 && bankRowIds.length > 0) {
    bankRowsHtml = `
      <div class="detail-field">
        <div class="df-label">Bank Row(s)</div>
        <div class="bank-rows">
          ${bankRowIds.map(id => `
            <div class="bank-row">
              <span class="id">${esc(id)}</span>
              <span class="amount credit">credit</span>
            </div>
          `).join("")}
        </div>
      </div>`;
  } else if (!isStage3) {
    bankRowsHtml = `
      <div class="detail-field"><div class="df-label">Bank Row</div><div class="df-value mono">${esc(bn)}</div></div>`;
  }

  // Confidence bar
  let confidenceHtml = "";
  if (d.confidence !== null && d.confidence !== undefined) {
    const pct = Math.round(d.confidence * 100);
    let cls = "";
    if (pct < 50) cls = "critical";
    else if (pct < 75) cls = "low";
    confidenceHtml = `
      <div class="detail-field">
        <div class="df-label">Confidence</div>
        <div class="df-value">
          <div class="confidence-bar"><div class="confidence-fill ${cls}" style="width:${pct}%"></div></div>
          <span>${pct}%</span>
        </div>
      </div>`;
  }

  // Retry button
  let retryBtn = "";
  if (d.status === "AI_RETRY_REQUIRED") {
    if (d.tier === "TIER_3") {
      retryBtn = '<button class="retry-btn" data-retry-llm>Retry Gemini</button>';
    } else if (d.tier === "STAGE_3") {
      retryBtn = '<button class="retry-btn" data-retry-stage3>Retry Stage 3</button>';
    }
  }

  return `
    <div class="detail-card">
      <div class="detail-head">
        <span class="detail-tid">${esc(d.transaction_id)}</span>
        ${chip(d.status)} ${tierChip(d.tier)}
        ${retryBtn}
      </div>
      <div class="detail-body">
        <div class="detail-grid">
          <div>
            <div class="detail-field"><div class="df-label">Status</div><div class="df-value">${chip(d.status)}</div></div>
            <div class="detail-field"><div class="df-label">Tier</div><div class="df-value">${tierChip(d.tier)}</div></div>
            <div class="detail-field"><div class="df-label">Rule</div><div class="df-value">${esc(d.rule || "—")}</div></div>
            <div class="detail-field"><div class="df-label">Reason</div><div class="df-value">${esc(d.reason || "—")}</div></div>
            ${confidenceHtml}
            <div class="detail-field"><div class="df-label">Gateway Row</div><div class="df-value mono">${esc(gw)}</div></div>
            ${bankRowsHtml}
            <div class="detail-field"><div class="df-label">Ledger Row</div><div class="df-value mono">${esc(lg)}</div></div>
            ${partialBlock}
            ${llmBlock}
          </div>
          <div>
            ${settlementBlock}
            ${evEntries.length > 0 ? `
              <div class="evidence-block">
                <h4>Evidence</h4>
                ${evEntries.map(([k,v]) => `
                  <div class="ev-row">
                    <span class="ek">${esc(k)}</span>
                    <span class="ev">${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>
                  </div>`).join("")}
              </div>` : ""}
            ${Object.keys(mr).length > 0 ? `
              <div class="evidence-block" style="margin-top:10px">
                <h4>Matched Source Records</h4>
                ${Object.entries(mr).filter(([,v]) => v).map(([src,rid]) => `
                  <div class="ev-row">
                    <span class="ek">${esc(src)}</span>
                    <span class="ev">${esc(String(rid))}</span>
                  </div>`).join("")}
              </div>` : ""}
          </div>
        </div>
      </div>
    </div>
  `;
}

/* ════════════════════════════════════════════════════════════
   Q&A
   ════════════════════════════════════════════════════════════ */

function initQA() {
  if (_qaInited) return;
  _qaInited = true;
  const el = document.getElementById("qa-content");

  const examples = [
    "What happened to PAY109?",
    "Why is PAY109 matched?",
    "Reconciliation status of PAY109?",
    "What evidence supports PAY109?",
    "Which transactions need human review?",
    "Show unresolved transactions.",
    "Which matched by split settlement rule?",
  ];

  el.innerHTML = `
    <div class="qa-wrap">
      <div class="qa-input-card">
        <div class="qa-input-head"><h3>Ask a question</h3></div>
        <div class="qa-input-row">
          <input class="qa-field field" id="qa-input" placeholder="e.g. What happened to PAY109?" autocomplete="off">
          <button class="qa-send btn btn-primary" id="qa-btn">Ask</button>
        </div>
        <div class="qa-chips">
          <span class="ch-label">Try:</span>
          ${examples.map(e => `<button class="qa-chip">${esc(e)}</button>`).join("")}
        </div>
      </div>
      <div class="qa-history" id="qa-history"></div>
    </div>
  `;

  const input = document.getElementById("qa-input");
  const btn   = document.getElementById("qa-btn");
  const hist  = document.getElementById("qa-history");

  function submit() {
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    askQA(q, hist);
  }

  btn.addEventListener("click", submit);
  input.addEventListener("keydown", e => { if (e.key === "Enter") submit(); });

  el.querySelectorAll(".qa-chip").forEach(b => {
    b.addEventListener("click", () => { input.value = b.textContent; submit(); });
  });
}

async function askQA(q, hist) {
  const turn = document.createElement("div");
  turn.className = "qa-turn";
  turn.innerHTML = `
    <div class="qa-turn-q">${esc(q)}</div>
    <div class="qa-turn-a"><div class="loading" style="padding:1rem 1.25rem">Thinking…</div></div>
  `;
  hist.prepend(turn);

  try {
    const res = await fetch(API + "/api/qa", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q}),
    });
    const data = await res.json();
    const answer = data.explanation || "No explanation returned.";
    const meta = [];
    if (data.llm_used) meta.push("🤖 LLM used");
    if (data.llm_unavailable) meta.push("⚠️ LLM unavailable");
    if (data.found === false) meta.push("❓ Not found");
    if (data.supported === false) meta.push("🚫 Unsupported question");
    turn.innerHTML = `
      <div class="qa-turn-q">${esc(q)}</div>
      <div class="qa-turn-a">
        <div class="answer-text">${esc(answer)}</div>
        ${meta.length ? `<div class="answer-meta">${meta.join(" · ")}</div>` : ""}
      </div>
    `;
  } catch (err) {
    turn.innerHTML = `
      <div class="qa-turn-q">${esc(q)}</div>
      <div class="qa-turn-a"><div class="answer-text" style="color:var(--red)">Error: ${esc(err.message)}</div></div>
    `;
  }
}

/* ════════════════════════════════════════════════════════════
   Initial load
   ════════════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", function () {
  loadOverview();
});

})();