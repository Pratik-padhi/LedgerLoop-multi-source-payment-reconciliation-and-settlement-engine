/* ═══════════════════════════════════════════════════════════════════════════
   LedgerLoop — The Settlement Terminal
   One application file, two surfaces:
     data-surface="pitch"    → the project page (/)
     data-surface="console"  → the operator console (/app)

   Every endpoint is read-only. The only stateful calls are the explicit
   retry / review actions, and those never mutate a stored result except by
   re-running the pipeline's own adjudication for one transaction.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var API = "";
  var surface = document.body.getAttribute("data-surface");

  /* ── State ─────────────────────────────────────────────────────────── */

  var _overview = null;
  var _exceptions = null;
  var _transactions = null;
  var _selectedExc = null;
  var _selectedTxn = null;
  var _qaInited = false;
  var _qaReady = null;
  var _runsLoaded = false;
  var _currentPanel = "overview";
  var _txSort = { field: "transaction_id", dir: "asc" };
  var _txFilter = "ALL";
  var _txSearch = "";
  var _excFilter = "ALL";
  var _excSearch = "";
  var _trace = null;

  function setSourceScope() {
    var scope = document.getElementById("source-scope");
    if (!scope || !_overview) return;
    scope.textContent = "Synthetic dataset · " + num(count(_overview.gateway_rows) + count(_overview.bank_rows) + count(_overview.ledger_rows)) + " source rows, no upload";
  }

  /* ── Formatting and small helpers ──────────────────────────────────── */

  function esc(s) {
    if (s == null) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  /* Machine vocabulary wraps at its own delimiter. A rule name like
     EXACT_REFERENCE_AND_AMOUNT must break at an underscore, never mid-word, so
     a soft break opportunity goes after each one. */
  function softTokens(s) {
    return esc(s).replace(/_/g, "_&#8203;");
  }

  function count(n) { return Number(n || 0); }

  function num(n) {
    return count(n).toLocaleString("en-IN");
  }

  /* Money is printed as a code, not a glyph: the terminal's unit. */
  function inr(v) {
    if (v == null || v === "") return "—";
    var n = typeof v === "string" ? parseFloat(v) : v;
    if (!isFinite(n)) return "—";
    return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function pct(v) { return (v == null || isNaN(v)) ? "0.0" : Number(v).toFixed(1); }
  function isMatched(status) { return status === "MATCH" || status === "MATCHED"; }
  function signedClass(value) {
    var n = typeof value === "number" ? value : parseFloat(value);
    if (!isFinite(n) || Math.abs(n) <= 0.01) return "";
    return n < 0 ? "oxide" : "";
  }
  function firstValue() {
    for (var i = 0; i < arguments.length; i++) {
      if (arguments[i] !== null && arguments[i] !== undefined && arguments[i] !== "") return arguments[i];
    }
    return null;
  }
  function humanizeKey(key) {
    return String(key || "").replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
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

  var STATUS_TONE = {
    MATCH: "ink", MATCHED: "ink", PARTIAL_MATCH: "ink",
    PARTIAL_PAYMENT: "quiet", HUMAN_REVIEW: "oxide", AI_RETRY_REQUIRED: "oxide",
    UNRESOLVED: "oxide", UNRESOLVED_FOR_TIER_1: "oxide", AMBIGUOUS: "oxide"
  };

  /* Status vocabulary is shown compactly in the table, exactly as the tier tags
     abbreviate their prefix. The raw token is kept on the tag itself and is
     always printed in full in the detail panel. */
  var STATUS_LABEL = { PARTIAL_PAYMENT: "PARTIAL", UNRESOLVED_FOR_TIER_1: "UNRESOLVED" };

  function statusTag(status) {
    if (!status) return '<span class="tag tag--quiet">—</span>';
    var tone = STATUS_TONE[status] || "quiet";
    var label = STATUS_LABEL[status] || status;
    return '<span class="tag' + (tone === "quiet" ? " tag--quiet" : tone === "oxide" ? " tag--oxide" : " tag--ink") +
      '" title="' + esc(status) + '">' + esc(label) + "</span>";
  }

  function tierTag(tier) {
    if (!tier) return "";
    return '<span class="tag tag--quiet">' + esc(String(tier).replace("TIER_", "T").replace("STAGE_", "S")) + "</span>";
  }

  function nextActionFor(status) {
    if (status === "AI_RETRY_REQUIRED") return "Retry adjudication only when authorized. The stored result stays unchanged until the retry completes.";
    if (status === "PARTIAL_PAYMENT") return "Compare received funds with expected net and read the settlement breakdown.";
    if (status === "HUMAN_REVIEW" || status === "AMBIGUOUS") return "Read the source rows and matching evidence before taking any action.";
    if (status === "UNRESOLVED" || status === "UNRESOLVED_FOR_TIER_1") return "Confirm source coverage. No sufficient match evidence is available for this transaction.";
    return "No exception action is required.";
  }

  function skeletonHtml(rows) {
    var n = rows || 4;
    var out = '<div class="skeleton" role="status" aria-label="Loading">';
    for (var i = 0; i < n; i++) out += "<span></span>";
    return out + "</div>";
  }

  function errorState(message, retryKey, retryFn) {
    var el = document.createElement("div");
    el.className = "notice notice--oxide";
    el.setAttribute("role", "alert");
    el.innerHTML = '<span><strong>Data unavailable.</strong> ' + esc(message) +
      " The run is computed on first request, so a cold start can take a moment.</span>";
    if (retryFn) {
      var btn = document.createElement("button");
      btn.className = "btn btn--sm btn--oxide";
      btn.type = "button";
      btn.textContent = "Retry";
      btn.addEventListener("click", retryFn);
      el.appendChild(btn);
    }
    if (retryKey) el.setAttribute("data-retry-key", retryKey);
    return el;
  }

  async function fetchJson(path, options) {
    var res = await fetch(API + path, options);
    var data = null;
    try { data = await res.json(); } catch (_) { /* not JSON */ }
    if (!res.ok) {
      var message = (data && data.error) || res.statusText || "Request failed (" + res.status + ")";
      var error = new Error(message);
      error.status = res.status;
      error.payload = data;
      throw error;
    }
    return data;
  }

  function setRunStatus(text, state) {
    var wrap = document.getElementById("header-run-status");
    var label = document.getElementById("header-run-status-text");
    if (label) label.textContent = text;
    if (wrap) wrap.className = "run-status state-" + (state || "neutral");
  }

  /* ── Theme ─────────────────────────────────────────────────────────── */

  var THEME_STORAGE_KEY = "ledgerloop-theme-v1";

  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem(THEME_STORAGE_KEY); } catch (_) { /* private mode */ }
    var theme = saved === "dark" || saved === "light" ? saved : "light";
    document.documentElement.setAttribute("data-theme", theme);
    updateThemeBtn();
  }

  function toggleTheme() {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch (_) { /* private mode */ }
    updateThemeBtn();
  }

  function updateThemeBtn() {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    var toggle = document.getElementById("theme-toggle");
    var label = document.getElementById("theme-label");
    var themeColor = document.querySelector('meta[name="theme-color"]');
    if (label) label.textContent = dark ? "Light" : "Dark";
    if (toggle) toggle.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    if (themeColor) themeColor.setAttribute("content", dark ? "#0d0e0f" : "#f0f1f1");
  }

  /* ═══════════════════════════════════════════════════════════════════════
     SHARED — the settlement identity, printed as arithmetic
     ═══════════════════════════════════════════════════════════════════════ */

  function ledgerLine(label, value, kind) {
    var cls = "ledger__line" + (kind ? " ledger__line--" + kind : "");
    return '<div class="' + cls + '"><span>' + esc(label) + "</span><span>" + esc(inr(value)) + "</span></div>";
  }

  function settlementLedger(settlement, opts) {
    var s = settlement || {};
    var o = opts || {};
    var lines = "";
    lines += ledgerLine("gross", s.gross_amount);
    /* Every term is printed, including zeros: the identity must be checkable. */
    if (count(s.gst_amount) || o.all) lines += ledgerLine("gst", s.gst_amount, "plus");
    if (count(s.tds_amount) || o.all) lines += ledgerLine("tds", s.tds_amount, "minus");
    if (count(s.mdr_amount) || o.all) lines += ledgerLine("mdr", s.mdr_amount, "minus");
    if (count(s.mdr_gst_amount) || o.all) lines += ledgerLine("mdr gst", s.mdr_gst_amount, "minus");
    if (count(s.total_fee_amount) || o.all) lines += ledgerLine("fees", s.total_fee_amount, "minus");
    if (count(s.refund_amount) || o.all) lines += ledgerLine("refund", s.refund_amount, "minus");
    lines += ledgerLine("= expected net", firstValue(s.expected_net_amount, s.expected_net), "sum");
    if (o.actual !== false) lines += ledgerLine("actual bank", s.actual_bank_amount);
    if (s.variance !== undefined && s.variance !== null) {
      lines += ledgerLine("variance", s.variance, "total");
    }
    if (s.explained_variance !== undefined && s.explained_variance !== null) {
      lines += ledgerLine("  explained", s.explained_variance);
    }
    if (s.remaining_variance !== undefined && s.remaining_variance !== null) {
      lines += ledgerLine("  remaining", s.remaining_variance);
    }
    return '<div class="ledger">' + lines + "</div>";
  }

  function evidenceRows(ev) {
    var keys = Object.keys(ev || {}).filter(function (k) { return ev[k] !== null && ev[k] !== undefined; });
    if (!keys.length) return '<div class="empty"><strong>No structured evidence</strong>This result carries no evidence fields.</div>';
    return '<dl class="facts">' + keys.map(function (k) {
      return "<div><dt>" + esc(humanizeKey(k)) + "</dt><dd class=\"mono\">" + esc(evidenceText(ev[k])) + "</dd></div>";
    }).join("") + "</dl>";
  }

  /* ═══════════════════════════════════════════════════════════════════════
     SHARED — the resolution path (four passes, live counts)
     ═══════════════════════════════════════════════════════════════════════ */

  function passDefinitions(d, short) {
    var t1 = d.tier1_summary || {};
    var t2 = d.tier2_summary || {};
    var t3 = d.tier3_summary || {};
    var t4 = d.stage3_summary || {};
    return [
      {
        code: "T1", name: "Exact evidence",
        rule: short ? "Reference + amount" : "Reference + amount, date differences are evidence not a gate",
        evaluated: count(firstValue(t1.total_logical_transactions, t1.total_input)),
        resolved: count(t1.matched_count),
        forwarded: count(t1.unresolved_count)
      },
      {
        code: "T2", name: "Bounded tolerance",
        rule: short ? "Amount tolerance + transforms" : "Documented amount tolerance, closed set of reference transforms",
        evaluated: count(firstValue(t2.total_residue_evaluated, t2.total_residue)),
        resolved: count(t2.matched_count),
        forwarded: count(t2.unresolved_count)
      },
      {
        code: "T3", name: "Linked evidence",
        rule: short ? "Linked refund, TDS, description" : "Refund, TDS, description links — then guarded AI adjudication",
        evaluated: count(firstValue(t3.total_residue_evaluated, t3.total_residue)),
        resolved: count(t3.match_count),
        forwarded: count(t3.unresolved_count)
      },
      {
        code: "S3", name: "Split settlement",
        rule: short ? "Multiple credits, tax, fees" : "Multiple credits, tax, fees, refund — Decimal arithmetic",
        evaluated: count(t4.total_evaluated),
        resolved: count(t4.match_count),
        forwarded: count(t4.unresolved_count)
      }
    ];
  }

  function passRow(pass) {
    return '<div class="path__row">' +
      '<span class="path__index">' + esc(pass.code) + "</span>" +
      '<div><span class="path__name">' + esc(pass.name) + '</span><span class="path__rule">' + esc(pass.rule) + "</span></div>" +
      '<div class="path__nums">' +
        '<div class="path__num">' + pass.evaluated + "<span>evaluated</span></div>" +
        '<div class="path__num">' + pass.resolved + "<span>resolved</span></div>" +
        '<div class="path__num path__num--muted">' + pass.forwarded + "<span>forwarded</span></div>" +
      "</div>" +
      "</div>";
  }

  function renderPasses(d, short) {
    return passDefinitions(d, short).map(passRow).join("");
  }

  /* ═══════════════════════════════════════════════════════════════════════
     SHARED — Grounded Q&A
     ═══════════════════════════════════════════════════════════════════════ */

  var _followUps = {
    LOOKUP: ["What is the status?", "What is the variance for it?", "Which tier resolved it?"],
    STATUS: ["What evidence supports this?", "View the transaction"],
    WHY: ["What evidence supports this?", "Which tier resolved it?"],
    EVIDENCE: ["View the transaction", "What is the variance for it?"],
    FILTER_STATUS: ["Which transactions need human review?", "Show partial payments."],
    FILTER_RULE: ["Which transactions need human review?", "Show exceptions."]
  };

  function citationsHtml(citations) {
    if (!Array.isArray(citations) || !citations.length) return "";
    return '<div class="command__cites">' + citations.map(function (c) {
      return '<span class="tag tag--quiet">' + esc(c.source || "source") + " " + esc(c.source_row_id || "—") + "</span>";
    }).join("") + "</div>";
  }

  function answerMeta(data) {
    var meta = [];
    if (data.source === "DETERMINISTIC_SETTLEMENT") meta.push("deterministic settlement");
    else if (data.llm_used) meta.push("ai-assisted explanation");
    else meta.push("stored evidence answer");
    if (data.llm_unavailable) meta.push("ai unavailable · deterministic fallback");
    if (data.found === false) meta.push("not found");
    if (data.supported === false) meta.push("unsupported");
    return meta;
  }

  function answerLogItem(data, question) {
    var isFinancial = data.source === "DETERMINISTIC_SETTLEMENT" && data.field && data.value !== undefined;
    var tid = (data.transaction_ids && data.transaction_ids[0]) || null;
    var first = data.retrieved_data && data.retrieved_data.length ? data.retrieved_data[0] : null;
    var text = data.explanation || (isFinancial ? "This value comes from the completed deterministic settlement result." : "No explanation returned.");

    var facts = [];
    if (tid) facts.push(["transaction", tid]);
    if (isFinancial) {
      facts.push(["field", humanizeKey(data.field)]);
      facts.push(["value", "INR " + inr(data.value)]);
    } else if (first) {
      if (first.status) facts.push(["status", first.status]);
      if (first.tier) facts.push(["tier", first.tier]);
      if (first.rule) facts.push(["rule", first.rule]);
      if (first.reason) facts.push(["reason", first.reason]);
    }
    var actionStatus = first ? first.status : data.status;
    var actionTier = first ? first.tier : data.tier;

    var actions = "";
    if (tid) {
      actions += '<button class="btn btn--sm btn--quiet" type="button" data-answer-action="view" data-tid="' + esc(tid) + '">View transaction</button>';
      actions += '<button class="btn btn--sm btn--quiet" type="button" data-answer-action="review" data-tid="' + esc(tid) + '">AI review · read-only</button>';
    }
    if (tid && actionStatus === "AI_RETRY_REQUIRED" && actionTier === "TIER_3") {
      actions += '<button class="btn btn--sm btn--oxide" type="button" data-answer-action="retry" data-tid="' + esc(tid) + '">Retry adjudication</button>';
    }

    return '<div class="log__item">' +
      '<span class="log__q">' + esc(question) + "</span>" +
      '<p class="log__a">' + esc(text) + "</p>" +
      (isFinancial ? '<div class="log__value"><span class="label">Deterministic value</span><b>INR ' + esc(inr(data.value)) + "</b></div>" : "") +
      (facts.length ? '<div class="facts">' + facts.map(function (f) {
        return "<div><dt>" + esc(f[0]) + "</dt><dd>" + esc(String(f[1])) + "</dd></div>";
      }).join("") + "</div>" : "") +
      citationsHtml(data.citations) +
      '<div class="log__meta">' + answerMeta(data).map(function (m) { return "<span>" + esc(m) + "</span>"; }).join("") + "</div>" +
      (actions ? '<div class="log__actions">' + actions + "</div>" : "") +
      "</div>";
  }

  async function askQuestion(question, mount) {
    var target = typeof mount === "string"
      ? (mount.charAt(0) === "#" ? document.querySelector(mount) : document.getElementById(mount))
      : mount;
    if (!target) return;
    var log = target.querySelector(".log") || target;
    var empty = log.querySelector(".empty");
    if (empty) empty.remove();

    var pending = document.createElement("div");
    pending.className = "log__item";
    pending.innerHTML = '<span class="log__q">' + esc(question) + '</span><p class="log__a dim">Checking the grounded answer…</p>';
    log.appendChild(pending);

    try {
      var data = await fetchJson("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question })
      });
      var item = document.createElement("div");
      item.innerHTML = answerLogItem(data, question);
      var node = item.firstElementChild;
      pending.replaceWith(node);
      bindAnswerActions(node);
    } catch (err) {
      pending.innerHTML = '<span class="log__q">' + esc(question) + '</span><p class="log__a oxide">' + esc(err.message) + "</p>";
    }
  }

  function bindAnswerActions(root) {
    if (!root) return;
    root.querySelectorAll("[data-answer-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tid = btn.dataset.tid;
        var action = btn.dataset.answerAction;
        if (action === "view") { openTransaction(tid); return; }
        btn.disabled = true;
        var label = btn.textContent;
        btn.textContent = "Working…";
        var scope = btn.closest(".log__item") || btn.parentNode;
        if (action === "review") reviewTransaction(tid, btn, label, scope);
        else if (action === "retry") retryTransaction(tid, btn, label, "retry-llm", scope);
      });
    });
  }

  /* ═══════════════════════════════════════════════════════════════════════
     PITCH — the first viewport is the run
     ═══════════════════════════════════════════════════════════════════════ */

  var FIGURES = {
    rate: {
      label: "Reconciliation rate", code: "rate", lead: true,
      foot: function (d) {
        var sc = d.status_counts || {};
        var matched = count(sc.MATCH) + count(sc.MATCHED);
        return matched + " resolved · " + Math.max(count(d.total_transactions) - matched, 0) + " open";
      },
      figure: function (d) { return pct(d.reconciliation_rate); },
      /* The unit is authored apart from the figure so it can be set at the
         figure's own proportion; a full-size "%" in a mono advance reads as a
         second number. tone is the same 0-100 the density bar measures: the
         surface reads it as a hue, red to green, on the number alone. */
      unit: "%",
      tone: function (d) {
        var v = Number(d.reconciliation_rate);
        return isFinite(v) ? Math.max(0, Math.min(v, 100)) : 0;
      },
      density: function (d) { return Math.max(0, Math.min(Number(d.reconciliation_rate || 0), 100)); },
      note: "Share of logical transactions whose authoritative tier result is a match. Computed from the run, not stored.",
      rows: function (d) {
        var sc = d.status_counts || {};
        var matched = count(sc.MATCH) + count(sc.MATCHED);
        return [
          ["resolved (MATCH / MATCHED)", matched],
          ["open (everything else)", Math.max(count(d.total_transactions) - matched, 0)],
          ["logical transactions", count(d.total_transactions)],
          ["profile", d.dataset || "data"]
        ];
      }
    },
    rows: {
      label: "Source rows", code: "src",
      foot: function (d) {
        return count(d.gateway_rows) + " gateway · " + count(d.bank_rows) + " bank · " + count(d.ledger_rows) + " ledger";
      },
      figure: function (d) { return num(count(d.gateway_rows) + count(d.bank_rows) + count(d.ledger_rows)); },
      note: "Rows normalized into canonical records for this run. Source-row IDs and raw values are preserved end to end.",
      rows: function (d) {
        return [
          ["gateway rows", count(d.gateway_rows)],
          ["bank rows", count(d.bank_rows)],
          ["ledger rows", count(d.ledger_rows)],
          ["logical transactions", count(d.total_transactions)]
        ];
      }
    },
    gateway: {
      label: "Gateway value", code: "inr",
      foot: function () { return "normalized gateway amount"; },
      figure: function (d) { return inr(d.gateway_value); },
      note: "Signed sum of every normalized gateway amount, refunds included as negative rows.",
      rows: function (d) {
        return [
          ["gateway value", "INR " + inr(d.gateway_value)],
          ["gateway rows", count(d.gateway_rows)],
          ["logical transactions", count(d.total_transactions)],
          ["profile", d.dataset || "data"]
        ];
      }
    },
    reconciled: {
      label: "Reconciled value", code: "inr",
      foot: function (d) { return "gateway value of matched transactions"; },
      figure: function (d) { return inr(d.reconciled_value); },
      note: "Gateway value of transactions resolved by a match. It cannot exceed the gateway value; the difference is value still open.",
      rows: function (d) {
        var sc = d.status_counts || {};
        var matched = count(sc.MATCH) + count(sc.MATCHED);
        var diff = Number(d.gateway_value || 0) - Number(d.reconciled_value || 0);
        return [
          ["reconciled value", "INR " + inr(d.reconciled_value)],
          ["matched transactions", matched],
          ["value still open", "INR " + inr(diff)],
          ["gateway value", "INR " + inr(d.gateway_value)]
        ];
      }
    },
    exceptions: {
      label: "Exceptions", code: "exc", alert: function (d) { return count(d.exception_count) > 0; },
      foot: function (d) { return "Stage 3 variance INR " + inr(d.settlement_variance); },
      figure: function (d) { return num(d.exception_count); },
      note: "Transactions the pipeline declined to resolve automatically. Each one keeps its reason, evidence, and next action.",
      rows: function (d) {
        var sc = d.status_counts || {};
        var rows = Object.keys(sc).filter(function (k) { return !isMatched(k); })
          .sort(function (a, b) { return count(sc[b]) - count(sc[a]); })
          .map(function (k) { return [k.toLowerCase().replace(/_/g, " "), count(sc[k])]; });
        rows.push(["stage 3 variance", "INR " + inr(d.settlement_variance)]);
        rows.push(["total exceptions", count(d.exception_count)]);
        return rows;
      }
    }
  };

  function readoutCell(key, fig, d) {
    var alert = fig.alert && fig.alert(d);
    return '<button class="readout-cell' + (fig.lead ? " readout-cell--lead" : "") + (alert ? " readout-cell--alert" : "") +
      (fig.tone ? " readout-cell--tone" : "") +
      '" type="button" data-figure="' + key + '" aria-expanded="false" aria-controls="figure-drawer">' +
      '<span class="readout-cell__label"><span>' + esc(fig.label) + '</span><span class="readout-cell__code">' + esc(fig.code) + "</span></span>" +
      '<span class="readout-cell__figure"' + (fig.tone ? ' style="--tone:' + fig.tone(d) + '"' : "") + ">" +
        esc(fig.figure(d)) + (fig.unit ? '<span class="readout-cell__unit">' + esc(fig.unit) + "</span>" : "") + "</span>" +
      (fig.density ? '<div class="density" aria-hidden="true"><span style="transform:scaleX(' + (fig.density(d) / 100) + ')"></span></div>' : "") +
      '<span class="readout-cell__foot">' + esc(fig.foot(d)) + "</span>" +
      "</button>";
  }

  function renderReadout(d) {
    var host = document.getElementById("readout-cells");
    if (!host) return;
    host.innerHTML = Object.keys(FIGURES).map(function (key) { return readoutCell(key, FIGURES[key], d); }).join("");

    var identity = document.getElementById("readout-identity");
    if (identity) {
      identity.textContent = "profile " + (d.dataset || "data") + " · " + count(d.gateway_rows) + "/" +
        count(d.bank_rows) + "/" + count(d.ledger_rows) + " rows gw/bank/ledger · " +
        ((d.llm_models || [])[0] || "no model chain");
    }
    setSourceScope();
    host.querySelectorAll("[data-figure]").forEach(function (btn) {
      btn.addEventListener("click", function () { toggleDrawer(btn); });
    });
  }

  function closeDrawer() {
    var drawer = document.getElementById("figure-drawer");
    if (!drawer) return;
    drawer.hidden = true;
    document.querySelectorAll(".readout-cell").forEach(function (c) {
      c.classList.remove("is-led");
      c.setAttribute("aria-expanded", "false");
    });
  }

  function toggleDrawer(btn) {
    var drawer = document.getElementById("figure-drawer");
    var key = btn.dataset.figure;
    var fig = FIGURES[key];
    if (!drawer || !fig || !_overview) return;
    if (btn.getAttribute("aria-expanded") === "true") { closeDrawer(); return; }

    var wasOpen = !drawer.hidden;
    closeDrawer();

    document.getElementById("drawer-title").textContent = fig.label + " — derivation";
    document.getElementById("drawer-note").textContent = fig.note;
    document.getElementById("drawer-rows").innerHTML = fig.rows(_overview).map(function (row) {
      return '<div class="drawer-row"><span>' + esc(row[0]) + "</span><span>" + esc(String(row[1])) + "</span></div>";
    }).join("");

    drawer.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    btn.classList.add("is-led");
    if (wasOpen) return;

    /* The leader: a hairline drops from the pressed column to the evidence.
       Reading the rects forces layout, so this needs no animation frame — and
       must not depend on one, or the leader can be missing in a paused or
       headless renderer. */
    var gap = drawer.getBoundingClientRect().top - btn.getBoundingClientRect().bottom;
    var height = Math.max(0, Math.round(gap + drawer.offsetHeight + 1));
    btn.style.setProperty("--leader", height + "px");
  }

  function renderGovernanceCounters(d) {
    var host = document.getElementById("governance-counters");
    if (!host) return;
    var items = [
      ["Provider calls", count(d.llm_calls_made)],
      ["Validated", count(d.llm_recommendations_validated)],
      ["Rejected", count(d.llm_recommendations_rejected)]
    ];
    host.innerHTML = items.map(function (item) {
      return '<div class="counter"><b class="counter__n">' + item[1] + '</b><span class="label counter__k">' + esc(item[0]) + "</span></div>";
    }).join("");
  }

  /* ── Evidence trace: one transaction, end to end ─────────────────── */

  function traceChip(index, source, id, role) {
    return '<button class="row-chip" type="button" data-role="' + esc(role) + '" aria-expanded="false">' +
      '<span class="row-chip__src">' + esc(source) + "</span>" +
      '<span class="row-chip__id">' + esc(id) + "</span>" +
      '<span class="row-chip__n" aria-hidden="true">' + esc(index) + "</span></button>";
  }

  function renderTrace(d) {
    var host = document.getElementById("evidence-trace");
    if (!host) return;
    _trace = d;
    var mr = d.matched_records || {};
    var gatewayId = mr.gateway || d.gateway_row_id || null;
    var ledgerId = mr.ledger || d.ledger_row_id || null;
    var bankIds = (d.bank_row_ids || []).slice();
    if (!bankIds.length && mr.bank) bankIds = [mr.bank];
    var s = d.settlement || {};
    var id = d.transaction_id;
    var creditCount = bankIds.length;

    var roles = {
      gateway: "Anchors logical transaction " + id + ". The settlement was evaluated against gross INR " +
        inr(firstValue(s.gross_amount, d.gateway_amount)) + " and expected net INR " +
        inr(firstValue(s.expected_net_amount, s.expected_net, d.expected_net)) + ".",
      bank: (creditCount > 1
        ? "One of " + creditCount + " bank credits consumed together by this split settlement. "
        : "Bank credit consumed by this result. ") +
        "Bank rows are claimed one-to-one: once consumed, this row is not offered to any other transaction.",
      ledger: "Internal-ledger row linked to " + id + " by the pipeline. It carries the ledger-side expectation behind the " +
        (d.tier || "") + " result."
    };

    var chips = "";
    var plate = 0;
    function plateIndex() { plate += 1; return String(plate).padStart(2, "0"); }
    if (gatewayId) chips += traceChip(plateIndex(), "Gateway", gatewayId, roles.gateway);
    bankIds.forEach(function (bid) { chips += traceChip(plateIndex(), "Bank", bid, roles.bank); });
    if (ledgerId) chips += traceChip(plateIndex(), "Ledger", ledgerId, roles.ledger);

    var residue = "";
    if (s.remaining_variance !== undefined && s.remaining_variance !== null && Math.abs(Number(s.remaining_variance)) > 0.005) {
      residue = " The engine reports the remaining INR " + inr(s.remaining_variance) + " as " +
        esc(String(s.status || "unexplained").toLowerCase().replace(/_/g, " ")) + " instead of absorbing it.";
    }

    var ruleTag = d.rule && d.rule !== d.status ? '<span class="tag tag--quiet">' + esc(d.rule) + "</span>" : "";

    host.dataset.state = "ready";
    host.innerHTML =
      '<div class="trace__head">' +
        '<span class="trace__id">' + esc(id) + "</span>" +
        '<div class="tag-row">' + statusTag(d.status) + tierTag(d.tier) + ruleTag + "</div>" +
      "</div>" +
      '<div class="trace__body">' +
        '<div class="trace__col">' +
          '<p class="label trace__label">Source rows</p>' +
          '<div class="rows">' + chips + "</div>" +
          '<p class="drawer__note" id="trace-role">Press a row to read the role it played in this decision.</p>' +
          '<div class="subhead" style="margin-top:1rem">' +
            '<span class="label subhead__label">Reason · ' + esc(d.reason || "none recorded") + "</span>" +
            evidenceRows(d.evidence) +
            (residue ? '<p class="drawer__note" style="margin-top:.5rem">' + residue + "</p>" : "") +
          "</div>" +
        "</div>" +
        '<div class="trace__col">' +
          '<p class="label trace__label">Settlement identity</p>' +
          settlementLedger(s, { all: true }) +
          '<p class="drawer__note">Computed in <span class="mono">Decimal</span> as gross + gst − tds − mdr − mdr gst − fees − refund. ' +
          (s.gst_consistency ? "GST consistency: " + esc(String(s.gst_consistency).toLowerCase().replace(/_/g, " ")) + ". " : "") +
          "Variance is reported, never forced to zero.</p>" +
          '<a class="btn btn--sm btn--quiet" style="margin-top:1rem" href="/app?txn=' + encodeURIComponent(id) + '">Open in the console' +
            '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="square" aria-hidden="true"><path d="M2.5 8h11M9.5 4l4 4-4 4"/></svg></a>' +
        "</div>" +
      "</div>";

    host.querySelectorAll("[data-role]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var note = document.getElementById("trace-role");
        var open = btn.getAttribute("aria-expanded") === "true";
        host.querySelectorAll("[data-role]").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
        btn.setAttribute("aria-expanded", open ? "false" : "true");
        note.textContent = open ? "Press a row to read the role it played in this decision." : btn.dataset.role;
      });
    });
  }

  /* ── Command line (pitch) ─────────────────────────────────────────── */

  function initPitchCommand() {
    var form = document.getElementById("pitch-command");
    var input = document.getElementById("pitch-command-input");
    var out = document.getElementById("pitch-command-out");
    if (!form || !input || !out) return;

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var question = input.value.trim();
      if (!question) return;
      input.value = "";
      out.hidden = false;
      out.innerHTML = '<div class="command__q">' + esc(question) + '</div><p class="command__a dim" style="margin-top:.4rem">Checking the grounded answer…</p>';
      fetchJson("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question })
      }).then(function (data) {
        var facts = [];
        if (data.transaction_ids && data.transaction_ids.length) facts.push("transaction " + data.transaction_ids.join(", "));
        if (data.source === "DETERMINISTIC_SETTLEMENT" && data.value !== undefined) facts.push("INR " + inr(data.value));
        out.innerHTML = '<div class="command__q">' + esc(question) + "</div>" +
          '<p class="command__a" style="margin-top:.4rem">' + esc(data.explanation || "No explanation returned.") + "</p>" +
          (data.source === "DETERMINISTIC_SETTLEMENT" && data.value !== undefined
            ? '<div class="log__value" style="margin-top:.5rem"><span class="label">Deterministic value</span><b>INR ' + esc(inr(data.value)) + "</b></div>"
            : "") +
          citationsHtml(data.citations) +
          '<div class="command__meta">' + answerMeta(data).map(function (m) { return "<span>" + esc(m) + "</span>"; }).join("") +
          (facts.length ? "<span>" + esc(facts.join(" · ")) + "</span>" : "") + "</div>";
      }).catch(function (err) {
        out.innerHTML = '<div class="command__q">' + esc(question) + '</div><p class="command__a oxide" style="margin-top:.4rem">' + esc(err.message) + "</p>";
      });
    });

    document.querySelectorAll("[data-ask]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var question = btn.dataset.ask;
        if (!question) return;
        input.value = question;
        input.focus();
        form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true }));
      });
    });
  }

  /* ── Scroll spy for the pitch nav ─────────────────────────────────── */

  function initScrollSpy() {
    var links = document.querySelectorAll('.masthead__nav a[href^="#"]');
    if (!links.length || !("IntersectionObserver" in window)) return;
    var sections = [];
    links.forEach(function (link) {
      var target = document.querySelector(link.getAttribute("href"));
      if (target) sections.push({ id: target.id, link: link });
    });
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        sections.forEach(function (s) { s.link.removeAttribute("aria-current"); });
        var match = sections.filter(function (s) { return s.id === entry.target.id; })[0];
        if (match) match.link.setAttribute("aria-current", "true");
      });
    }, { rootMargin: "-45% 0px -50% 0px", threshold: 0 });
    sections.forEach(function (s) { observer.observe(document.getElementById(s.id)); });
  }

  async function loadTrace() {
    var host = document.getElementById("evidence-trace");
    if (!host) return null;
    try {
      var index = await fetchJson("/api/transactions");
      _transactions = index;
      var rows = (index.transactions || []).filter(function (r) {
        return r.tier === "STAGE_3" && r.settlement && Object.keys(r.settlement).length > 0;
      });
      /* Prefer a genuine multi-credit split: the strongest evidence the run holds. */
      var chosen = rows.filter(function (r) {
        return (r.bank_row_ids || []).length > 1 && isMatched(r.status);
      })[0] || rows[0] || (index.transactions || [])[0];
      if (!chosen) {
        host.innerHTML = '<div class="empty"><strong>No transactions in this run</strong>The run returned no rows to trace.</div>';
        return null;
      }
      var detail = await fetchJson("/api/transaction/" + encodeURIComponent(chosen.transaction_id));
      detail.settlement = detail.settlement || chosen.settlement;
      detail.bank_row_ids = (detail.bank_row_ids || []).length ? detail.bank_row_ids : (chosen.bank_row_ids || []);
      renderTrace(detail);
      var hint = document.getElementById("hint-variance");
      if (hint) {
        hint.dataset.ask = "What is the variance for " + chosen.transaction_id + "?";
        hint.textContent = "What is the variance for " + chosen.transaction_id + "?";
      }
      return detail;
    } catch (err) {
      host.innerHTML = "";
      host.appendChild(errorState(err.message, "trace", loadTrace));
      return null;
    }
  }

  async function initPitch() {
    setRunStatus("Resolving run", "loading");
    initPitchCommand();
    initScrollSpy();
    try {
      _overview = await fetchJson("/api/overview");
      setRunStatus("Run ready", "ready");
      setSourceScope();
      renderReadout(_overview);
      var path = document.getElementById("resolution-path");
      if (path) path.innerHTML = renderPasses(_overview);
      renderGovernanceCounters(_overview);
    } catch (err) {
      setRunStatus("Data unavailable", "error");
      var cells = document.getElementById("readout-cells");
      if (cells) {
        cells.innerHTML = "";
        cells.appendChild(errorState(err.message, "overview", initPitch));
      }
      var pathHost = document.getElementById("resolution-path");
      if (pathHost) {
        pathHost.innerHTML = "";
        pathHost.appendChild(errorState(err.message, "path", initPitch));
      }
    }
    await loadTrace();
  }

  /* ═══════════════════════════════════════════════════════════════════════
     CONSOLE — panels
     ═══════════════════════════════════════════════════════════════════════ */

  var PANEL_META = {
    overview: "Overview",
    runs: "Reconciliation Runs",
    exceptions: "Exceptions",
    transactions: "Transactions",
    qa: "Settlement Intelligence"
  };

  function updateHeader(pid) {
    var title = PANEL_META[pid] || PANEL_META.overview;
    document.title = title + " — LedgerLoop console";
  }

  function switchPanel(pid) {
    if (!PANEL_META[pid]) pid = "overview";
    document.querySelectorAll(".rail__item").forEach(function (item) {
      var active = item.dataset.panel === pid;
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    document.querySelectorAll(".panel").forEach(function (panel) {
      var active = panel.id === "panel-" + pid;
      panel.classList.toggle("is-active", active);
      if (active) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    });
    _currentPanel = pid;
    updateHeader(pid);
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "#" + pid);
    }
    window.scrollTo({ top: 0, behavior: "auto" });
    var active = document.getElementById("panel-" + pid);
    if (active) active.focus({ preventScroll: true });

    if (pid === "overview") { if (_overview) renderOverview(); else loadOverview(); }
    if (pid === "runs") { if (_overview) renderRuns(); else loadRuns(); }
    if (pid === "exceptions" && !_exceptions) loadExceptions();
    if (pid === "transactions" && !_transactions) loadTransactions();
    if (pid === "qa" && !_qaInited) initQA();
  }

  function openTransaction(tid) {
    var go = function () {
      _selectedTxn = tid;
      _txSearch = tid;
      switchPanel("transactions");
      if (_currentPanel === "transactions") {
        renderTransactionsPanel();
        loadTxnDetail(tid);
      }
    };
    if (_transactions && (_transactions.transactions || []).length) { go(); return; }
    loadTransactions().then(go).catch(function () { switchPanel("transactions"); });
  }

  function updateBadges(d) {
    var badge = document.getElementById("exc-badge");
    if (badge) {
      var n = count(d.exception_count);
      badge.textContent = n;
      badge.hidden = n <= 0;
    }
    var cta = document.getElementById("overview-exception-cta-count");
    if (cta) cta.textContent = count(d.exception_count) > 0 ? "(" + count(d.exception_count) + ")" : "";
  }

  /* ── Overview ─────────────────────────────────────────────────────── */

  async function loadOverview() {
    var host = document.getElementById("overview-content");
    if (host) host.innerHTML = skeletonHtml(5);
    setRunStatus("Resolving run", "loading");
    try {
      _overview = await fetchJson("/api/overview");
      setRunStatus("Run ready", "ready");
      updateBadges(_overview);
      setSourceScope();
      renderOverview();
      if (_runsLoaded) renderRuns();
    } catch (err) {
      setRunStatus("Data unavailable", "error");
      if (host) { host.innerHTML = ""; host.appendChild(errorState(err.message, "overview", loadOverview)); }
    }
  }

  function outcomeRows(d) {
    var sc = d.status_counts || {};
    var total = count(d.total_transactions);
    var keys = Object.keys(sc).sort(function (a, b) { return count(sc[b]) - count(sc[a]); });
    if (!keys.length) return '<tr><td colspan="3"><div class="empty"><strong>No outcome data</strong>This run returned no statuses.</div></td></tr>';
    return keys.map(function (status) {
      return "<tr><td>" + statusTag(status) + '</td><td class="num">' + count(sc[status]) +
        '</td><td class="num">' + pct(total ? count(sc[status]) / total * 100 : 0) + "%</td></tr>";
    }).join("");
  }

  function renderOverview() {
    var host = document.getElementById("overview-content");
    if (!host || !_overview) return;
    var d = _overview;
    var sc = d.status_counts || {};
    var t4 = d.stage3_summary || {};
    var total = count(d.total_transactions);
    var matched = count(sc.MATCH) + count(sc.MATCHED);
    var open = Math.max(total - matched, 0);
    var settlement = [
      ["Settled", count(t4.match_count)],
      ["Partial", count(t4.partial_count)],
      ["Unresolved", count(t4.unresolved_count)],
      ["Ambiguous", count(t4.ambiguous_count)]
    ];
    var settlementTotal = settlement.reduce(function (sum, row) { return sum + row[1]; }, 0);

    var metrics = [
      ["Reconciliation rate", pct(d.reconciliation_rate) + "%", matched + " of " + total + " resolved"],
      ["Open exceptions", num(d.exception_count), "declined automatically"],
      ["Gateway value", "INR " + inr(d.gateway_value), count(d.gateway_rows) + " gateway rows"],
      ["Reconciled value", "INR " + inr(d.reconciled_value), "matched transactions only"],
      ["Stage 3 variance", "INR " + inr(d.settlement_variance), count(t4.total_evaluated) + " settlements evaluated"],
      ["Profile", d.dataset || "data", count(d.ledger_rows) + " ledger rows"]
    ];

    host.innerHTML =
      '<div class="block"><div class="block__head"><h2>Current run</h2><p>Read-only snapshot · profile ' + esc(d.dataset || "data") + "</p></div>" +
        '<div class="metrics">' + metrics.map(function (m) {
          return '<div class="metric"><span class="label metric__k">' + esc(m[0]) + '</span><span class="metric__v">' + esc(m[1]) +
            '</span><span class="metric__note">' + esc(m[2]) + "</span></div>";
        }).join("") + "</div></div>" +

      '<div class="split-panel split-panel--wide">' +
        '<div class="block"><div class="block__head"><h2>Resolution path</h2><p>Each pass sees only the previous residue</p></div>' +
          '<div class="block__body block__body--flush"><div class="path">' + renderPasses(d, true) + "</div></div></div>" +
        '<div class="block"><div class="block__head"><h2>Outcome distribution</h2><p>Authoritative status per transaction</p></div>' +
          '<div class="block__body block__body--flush"><div class="table-scroll" style="border:0"><table class="grid-table"><thead><tr>' +
            '<th scope="col">Status</th><th scope="col" class="num">Count</th><th scope="col" class="num">Share</th></tr></thead><tbody>' +
            outcomeRows(d) + "</tbody></table></div></div></div>" +
      "</div>" +

      '<div class="stack stack--2">' +
        '<div class="block"><div class="block__head"><h2>Settlement pass</h2><p>Stage 3 outcomes</p></div>' +
          '<div class="block__body block__body--flush"><div class="table-scroll" style="border:0"><table class="grid-table"><thead><tr>' +
            '<th scope="col">Outcome</th><th scope="col" class="num">Count</th><th scope="col" class="num">Share</th></tr></thead><tbody>' +
            (settlementTotal ? settlement.map(function (row) {
              return "<tr><td>" + esc(row[0]) + '</td><td class="num">' + row[1] + '</td><td class="num">' +
                pct(settlementTotal ? row[1] / settlementTotal * 100 : 0) + "%</td></tr>";
            }).join("") : '<tr><td colspan="3"><div class="empty"><strong>No Stage 3 results</strong>No split settlement was evaluated.</div></td></tr>') +
            "</tbody></table></div></div></div>" +
        '<div class="block"><div class="block__head"><h2>AI governance</h2><p>Advisory only, validated in Python</p></div>' +
          '<div class="metrics metrics--governance">' +
            '<div class="metric"><span class="label metric__k">Provider calls</span><span class="metric__v">' + count(d.llm_calls_made) + "</span></div>" +
            '<div class="metric"><span class="label metric__k">Validated</span><span class="metric__v">' + count(d.llm_recommendations_validated) + "</span></div>" +
            '<div class="metric"><span class="label metric__k">Rejected</span><span class="metric__v">' + count(d.llm_recommendations_rejected) + "</span></div>" +
            '<div class="metric metric--wide"><span class="label metric__k">Model chain</span><span class="metric__v metric__v--wrap">' + esc((d.llm_models || []).join(", ") || "—") + "</span></div>" +
          "</div>" +
          '<div class="block__foot">Without <span class="mono">LEDGERLOOP_ENABLE_AI=1</span> and a key, every figure above is still produced by the deterministic tiers.</div>' +
        "</div>" +
      "</div>";
  }

  /* ── Pipeline ─────────────────────────────────────────────────────── */

  async function loadRuns() {
    var host = document.getElementById("runs-content");
    if (host) host.innerHTML = skeletonHtml(5);
    setRunStatus("Resolving run", "loading");
    try {
      if (!_overview) _overview = await fetchJson("/api/overview");
      _runsLoaded = true;
      setRunStatus("Run ready", "ready");
      setSourceScope();
      renderRuns();
    } catch (err) {
      setRunStatus("Data unavailable", "error");
      if (host) { host.innerHTML = ""; host.appendChild(errorState(err.message, "runs", loadRuns)); }
    }
  }

  function renderRuns() {
    var host = document.getElementById("runs-content");
    if (!host || !_overview) return;
    var d = _overview;
    var sub = document.getElementById("runs-subtitle");
    if (sub) {
      sub.textContent = "Profile " + (d.dataset || "not exposed") + " · " + count(d.gateway_rows) + " gateway rows · " +
        count(d.bank_rows) + " bank rows · " + count(d.ledger_rows) + " ledger rows · deterministic-first";
    }

    var tierDefinitions = [
      ["TIER_1", "Tier 1 · exact evidence"],
      ["TIER_2", "Tier 2 · bounded tolerance"],
      ["TIER_3", "Tier 3 · linked evidence"],
      ["STAGE_3", "Stage 3 · split settlement"]
    ];
    var tc = d.tier_counts || {};
    var total = count(d.total_transactions);
    var tierRows = tierDefinitions.filter(function (row) { return count(tc[row[0]]) > 0; }).map(function (row) {
      return "<tr><td>" + esc(row[1]) + '</td><td class="num">' + count(tc[row[0]]) + '</td><td class="num">' +
        pct(total ? count(tc[row[0]]) / total * 100 : 0) + "%</td></tr>";
    }).join("");

    var ruleKeys = Object.keys(d.rule_counts || {}).filter(function (k) { return k !== "NONE"; })
      .sort(function (a, b) { return count(d.rule_counts[b]) - count(d.rule_counts[a]); });

    var architecture = [
      ["Ingest", "Source normalization", "Explicit SourceSchema header mapping per source; raw values and source-row IDs preserved."],
      ["Resolve", "Tiered matching", "Exact → bounded tolerance → linked evidence → split settlement, each on the previous residue."],
      ["Control", "Python validation", "One-to-one bank-row consumption and Decimal settlement invariants, enforced in the application."],
      ["Serve", "Read-only snapshot", "Flask JSON endpoints and this console. Importing the app runs nothing; the first API request builds the run."]
    ];

    host.innerHTML =
      '<div class="block"><div class="block__head"><h2>Pipeline stages</h2><p>Evaluated volume, resolved outcomes, forwarded residue</p></div>' +
        '<div class="block__body block__body--flush"><div class="path">' + renderPasses(d, true) + "</div></div></div>" +

      '<div class="split-panel">' +
        '<div class="block"><div class="block__head"><h2>Resolution authority</h2><p>Authoritative tier per transaction</p></div>' +
          '<div class="block__body block__body--flush"><div class="table-scroll" style="border:0"><table class="grid-table"><thead><tr>' +
            '<th scope="col">Tier</th><th scope="col" class="num">Transactions</th><th scope="col" class="num">Share</th></tr></thead><tbody>' +
            (tierRows || '<tr><td colspan="3"><div class="empty"><strong>No tier data</strong>The run returned no tier counts.</div></td></tr>') +
            "</tbody></table></div></div></div>" +
        '<div class="block"><div class="block__head"><h2>Source coverage</h2><p>Rows available to this run</p></div>' +
          '<div class="metrics metrics--pair">' +
            '<div class="metric"><span class="label metric__k">Gateway</span><span class="metric__v">' + count(d.gateway_rows) + "</span></div>" +
            '<div class="metric"><span class="label metric__k">Bank</span><span class="metric__v">' + count(d.bank_rows) + "</span></div>" +
            '<div class="metric"><span class="label metric__k">Ledger</span><span class="metric__v">' + count(d.ledger_rows) + "</span></div>" +
            '<div class="metric"><span class="label metric__k">Transactions</span><span class="metric__v">' + total + "</span></div>" +
          "</div>" +
          '<div class="block__body"><ul class="controls">' +
            '<li class="control"><span class="control__mark" aria-hidden="true"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="square"><rect x="3" y="3" width="10" height="10"/><path d="M3 13 13 3"/></svg></span><div><strong>Ground truth is isolated</strong><p>Evaluation data is never imported by matching code or the server.</p></div></li>' +
            '<li class="control"><span class="control__mark" aria-hidden="true"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="square"><rect x="3" y="3" width="10" height="10"/><path d="M3 13 13 3"/></svg></span><div><strong>One-to-one consumption</strong><p>A settled bank row cannot support a second match.</p></div></li>' +
            '<li class="control"><span class="control__mark" aria-hidden="true"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="square"><rect x="3" y="3" width="10" height="10"/><path d="M3 13 13 3"/></svg></span><div><strong>Read-only review</strong><p>An AI review never replaces the stored result.</p></div></li>' +
          "</ul></div></div>" +
      "</div>" +

      '<div class="block"><div class="block__head"><h2>Rules that fired</h2><p>' + ruleKeys.length + " named rules produced a result in this run</p></div>" +
        '<div class="block__body block__body--flush"><div class="table-scroll" style="border:0;max-height:none"><table class="grid-table"><thead><tr>' +
          '<th scope="col">Rule</th><th scope="col" class="num">Transactions</th></tr></thead><tbody>' +
          (ruleKeys.length ? ruleKeys.map(function (rule) {
            return '<tr><td class="mono" style="font-size:.75rem">' + esc(rule) + '</td><td class="num">' + count(d.rule_counts[rule]) + "</td></tr>";
          }).join("") : '<tr><td colspan="2"><div class="empty"><strong>No rules recorded</strong>This run recorded no rule labels.</div></td></tr>') +
          "</tbody></table></div></div></div>" +

      '<div class="block"><div class="block__head"><h2>Architecture</h2><p>Four boundaries, in order</p></div>' +
        '<div class="block__body block__body--flush"><div class="path">' +
          architecture.map(function (node, i) {
            return '<div class="path__row"><span class="path__index">' + String(i + 1).padStart(2, "0") + "</span>" +
              '<div><span class="path__name">' + esc(node[0]) + " · " + esc(node[1]) + '</span><span class="path__rule">' + esc(node[2]) + "</span></div></div>";
          }).join("") +
        "</div></div></div>";
  }

  /* ── Exceptions ───────────────────────────────────────────────────── */

  async function loadExceptions(keepSelection) {
    var host = document.getElementById("exceptions-content");
    if (host) host.innerHTML = skeletonHtml(6);
    try {
      _exceptions = await fetchJson("/api/exceptions");
      var queue = (_exceptions.exceptions || []);
      var stillThere = _selectedExc && queue.some(function (e) { return e.transaction_id === _selectedExc; });
      if (!keepSelection || !stillThere) _selectedExc = queue.length ? queue[0].transaction_id : null;
      if (!keepSelection) { _excFilter = "ALL"; _excSearch = ""; }
      if (_overview) updateBadges(_overview);
      renderExceptions();
    } catch (err) {
      if (host) { host.innerHTML = ""; host.appendChild(errorState(err.message, "exceptions", function () { loadExceptions(false); })); }
    }
  }

  function exceptionMatches(e, query) {
    if (!query) return true;
    var mr = e.matched_records || {};
    var source = [e.transaction_id, e.status, e.rule, e.reason, e.tier, e.gateway_amount, e.expected_net,
      e.received, e.outstanding, mr.gateway, mr.bank, mr.ledger].concat(e.bank_row_ids || []).join(" ").toLowerCase();
    return source.indexOf(query.toLowerCase()) !== -1;
  }

  function renderExceptions() {
    var host = document.getElementById("exceptions-content");
    if (!host || !_exceptions) return;
    var all = _exceptions.exceptions || [];
    var items = all.slice();
    if (_excFilter === "HUMAN_REVIEW") items = items.filter(function (e) { return e.status === "HUMAN_REVIEW"; });
    if (_excFilter === "UNRESOLVED") items = items.filter(function (e) { return e.status === "UNRESOLVED" || e.status === "UNRESOLVED_FOR_TIER_1"; });
    if (_excFilter === "AI_RETRY") items = items.filter(function (e) { return e.status === "AI_RETRY_REQUIRED"; });
    if (_excFilter === "PARTIAL") items = items.filter(function (e) { return e.status === "PARTIAL_PAYMENT" || e.status === "AMBIGUOUS"; });
    if (_excSearch) items = items.filter(function (e) { return exceptionMatches(e, _excSearch); });

    var visible = items.some(function (e) { return e.transaction_id === _selectedExc; });
    var filters = [
      { key: "ALL", label: "All" },
      { key: "HUMAN_REVIEW", label: "Human review" },
      { key: "UNRESOLVED", label: "Unresolved" },
      { key: "AI_RETRY", label: "AI retry" },
      { key: "PARTIAL", label: "Partial / ambiguous" }
    ];

    host.innerHTML =
      '<div class="toolbar">' +
        '<div class="toolbar__search"><label class="sr-only" for="exception-search">Search the exception queue</label>' +
          '<input class="field" id="exception-search" type="search" value="' + esc(_excSearch) + '" placeholder="Transaction, reason, source row…" autocomplete="off"></div>' +
        '<div class="filters" role="group" aria-label="Exception filters">' +
          filters.map(function (f) {
            return '<button class="filter" type="button" data-exc-filter="' + f.key + '" aria-pressed="' + (_excFilter === f.key) + '">' + esc(f.label) + "</button>";
          }).join("") +
        "</div>" +
        '<span class="toolbar__count">' + items.length + " of " + all.length + "</span>" +
      "</div>" +

      '<div class="split-panel">' +
        '<div class="block"><div class="block__head"><h2>Investigation queue</h2><p>Arrow keys move, Enter opens</p></div>' +
          '<div class="block__body block__body--flush"><div class="table-scroll"><table class="grid-table grid-table--queue"><thead><tr>' +
            '<th scope="col">Transaction</th><th scope="col">Status</th><th scope="col" class="num">Amount</th><th scope="col">Reason</th>' +
          "</tr></thead><tbody>" +
          (items.length ? items.map(function (e) {
            var selected = _selectedExc === e.transaction_id;
            return '<tr data-tid="' + esc(e.transaction_id) + '" tabindex="0" class="' + (selected ? "is-selected" : "") + '">' +
              '<td><span class="id">' + esc(e.transaction_id) + '</span><span class="sub">' + softTokens(e.rule || e.tier || "—") + "</span></td>" +
              "<td>" + statusTag(e.status) + "</td>" +
              '<td class="num">' + esc(inr(firstValue(e.gateway_amount, e.expected_net, e.received))) + "</td>" +
              "<td>" + softTokens(e.reason || "—") + "</td></tr>";
          }).join("") : '<tr><td colspan="4"><div class="empty"><strong>No exceptions match</strong>Adjust the filter or the search.</div></td></tr>') +
          "</tbody></table></div></div></div>" +

        '<div class="block" id="exc-detail" aria-live="polite"><div class="block__head"><h2>Investigation</h2><p>Status → reason → evidence → action</p></div>' +
          '<div class="block__body">' +
          (visible && _selectedExc ? skeletonHtml(5)
            : '<div class="empty"><strong>' + (_selectedExc ? "Selection is filtered out" : "Select an exception") + "</strong>" +
              (_selectedExc ? "Choose a visible row to inspect it." : "Evidence, source rows, and the next action appear here.") + "</div>") +
          "</div></div>" +
      "</div>";

    var search = document.getElementById("exception-search");
    if (search) {
      search.addEventListener("input", function () {
        _excSearch = search.value;
        renderExceptions();
        var next = document.getElementById("exception-search");
        if (next) { next.focus(); next.setSelectionRange(next.value.length, next.value.length); }
      });
    }
    host.querySelectorAll("[data-exc-filter]").forEach(function (btn) {
      btn.addEventListener("click", function () { _excFilter = btn.dataset.excFilter; renderExceptions(); });
    });
    bindQueueTable(host, "#exc-detail", function (tid) { _selectedExc = tid; renderExceptions(); }, function (tid) { loadExcDetail(tid); });

    if (_selectedExc && visible) loadExcDetail(_selectedExc);
  }

  /* Keyboard triage: ↑ ↓ move, Enter opens, Esc clears. */
  function bindQueueTable(root, detailSelector, onSelect, onOpen) {
    var rows = Array.prototype.slice.call(root.querySelectorAll("tbody tr[data-tid]"));
    rows.forEach(function (tr) {
      tr.addEventListener("click", function () { onSelect(tr.dataset.tid); });
      tr.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(tr.dataset.tid); }
      });
    });
    root.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      var current = rows.indexOf(document.activeElement);
      if (current === -1) return;
      event.preventDefault();
      var next = current + (event.key === "ArrowDown" ? 1 : -1);
      if (next < 0 || next >= rows.length) return;
      rows[next].focus();
      onSelect(rows[next].dataset.tid);
      if (onOpen) onOpen(rows[next].dataset.tid);
    });
  }

  async function loadExcDetail(tid) {
    var box = document.getElementById("exc-detail");
    if (!box) return;
    var body = box.querySelector(".block__body");
    if (body) body.innerHTML = skeletonHtml(5);
    try {
      var detail = await fetchJson("/api/transaction/" + encodeURIComponent(tid));
      if (body) { body.innerHTML = ""; body.appendChild(detailFragment(detail)); bindDetailActions(body, tid); }
    } catch (err) {
      if (body) { body.innerHTML = ""; body.appendChild(errorState(err.message, "exc-detail", function () { loadExcDetail(tid); })); }
    }
  }

  /* The detail is written into the block body, never over the block: replacing
     the block's own markup would drop its head and its body inset, leaving the
     detail flush against the rule and its top unaligned with the index beside
     it. Same contract as loadExcDetail. */
  async function loadTxnDetail(tid) {
    var box = document.getElementById("txn-detail");
    if (!box) return;
    var body = box.querySelector(".block__body");
    if (body) body.innerHTML = skeletonHtml(5);
    try {
      var detail = await fetchJson("/api/transaction/" + encodeURIComponent(tid));
      if (body) { body.innerHTML = ""; body.appendChild(detailFragment(detail)); bindDetailActions(body, tid); }
    } catch (err) {
      if (body) { body.innerHTML = ""; body.appendChild(errorState(err.message, "txn-detail", function () { loadTxnDetail(tid); })); }
    }
  }

  /* ── Transactions ─────────────────────────────────────────────────── */

  async function loadTransactions() {
    var host = document.getElementById("transactions-content");
    if (host) host.innerHTML = skeletonHtml(6);
    try {
      _transactions = await fetchJson("/api/transactions");
      _txSort = { field: "transaction_id", dir: "asc" };
      _txFilter = "ALL";
      var wanted = new URLSearchParams(window.location.search).get("txn");
      var rows = _transactions.transactions || [];
      var settlementCase = rows.filter(function (r) { return r.tier === "STAGE_3" && r.settlement && Object.keys(r.settlement).length; })[0];
      _selectedTxn = (wanted && rows.some(function (r) { return r.transaction_id === wanted.toUpperCase(); }))
        ? wanted.toUpperCase()
        : (settlementCase ? settlementCase.transaction_id : (rows[0] && rows[0].transaction_id));
      if (wanted) _txSearch = "";
      renderTransactionsPanel();
    } catch (err) {
      if (host) { host.innerHTML = ""; host.appendChild(errorState(err.message, "transactions", loadTransactions)); }
    }
  }

  function transactionSearchText(r) {
    return [r.transaction_id, r.status, r.tier, r.rule, r.reason, r.amount, r.gateway_row, r.ledger_row]
      .concat(r.bank_row_ids || []).join(" ").toLowerCase();
  }

  function settlementState(row) {
    if (!row || row.tier !== "STAGE_3") return "—";
    if (isMatched(row.status)) return "Settled";
    if (row.status === "PARTIAL_PAYMENT") return "Partial";
    return String(row.status || "—").replace(/_/g, " ");
  }

  function renderTransactionsPanel() {
    var host = document.getElementById("transactions-content");
    if (!host || !_transactions) return;
    var rows = (_transactions.transactions || []).slice();
    if (_txFilter === "MATCHED") rows = rows.filter(function (r) { return isMatched(r.status); });
    if (_txFilter === "EXCEPTIONS") rows = rows.filter(function (r) { return !isMatched(r.status); });
    if (_txFilter === "SETTLEMENTS") rows = rows.filter(function (r) { return r.tier === "STAGE_3"; });
    if (_txSearch) {
      var q = _txSearch.toLowerCase();
      rows = rows.filter(function (r) { return transactionSearchText(r).indexOf(q) !== -1; });
    }
    rows.sort(function (a, b) {
      var av = _txSort.field === "amount" ? a.amount : a[_txSort.field];
      var bv = _txSort.field === "amount" ? b.amount : b[_txSort.field];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return _txSort.dir === "asc" ? av - bv : bv - av;
      av = String(av); bv = String(bv);
      return _txSort.dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    });

    var filters = [
      { key: "ALL", label: "All " + count(_transactions.count) },
      { key: "MATCHED", label: "Matched" },
      { key: "EXCEPTIONS", label: "Exceptions" },
      { key: "SETTLEMENTS", label: "Settlements" }
    ];

    function sortHeader(field, label) {
      var active = _txSort.field === field;
      var mark = active ? (_txSort.dir === "asc" ? "↑" : "↓") : "";
      return '<th scope="col" aria-sort="' + (active ? (_txSort.dir === "asc" ? "ascending" : "descending") : "none") + '">' +
        '<button class="sort" type="button" data-tx-sort="' + field + '">' + esc(label) +
        (mark ? ' <span class="sort__mark" aria-hidden="true">' + mark + "</span>" : "") + "</button></th>";
    }

    /* Five columns, each a distinct dimension: identity, provenance, amount,
       outcome, and the stage that produced it. Settlement state is not a column
       here — it is derivable from outcome plus stage, and its arithmetic lives in
       the detail panel where the received, expected and variance figures are. */

    host.innerHTML =
      '<div class="toolbar">' +
        '<div class="toolbar__search"><label class="sr-only" for="txn-search">Search transactions</label>' +
          '<input class="field" id="txn-search" type="search" value="' + esc(_txSearch) + '" placeholder="ID, source row, rule, status…" autocomplete="off"></div>' +
        '<div class="filters" role="group" aria-label="Transaction filters">' +
          filters.map(function (f) {
            return '<button class="filter" type="button" data-tx-filter="' + f.key + '" aria-pressed="' + (_txFilter === f.key) + '">' + esc(f.label) + "</button>";
          }).join("") + "</div>" +
        '<span class="toolbar__count">' + rows.length + " of " + count(_transactions.count) + "</span>" +
      "</div>" +

      '<div class="split-panel">' +
        '<div class="block"><div class="block__head"><h2>Source index</h2><p>Gateway-anchored, one row per logical transaction</p></div>' +
          '<div class="block__body block__body--flush"><div class="table-scroll"><table class="grid-table grid-table--index"><thead><tr>' +
            sortHeader("transaction_id", "Transaction") +
            '<th scope="col">Source</th>' + sortHeader("amount", "Amount") +
            '<th scope="col">Status</th>' + sortHeader("tier", "Stage") +
          "</tr></thead><tbody>" +
          (rows.length ? rows.map(function (r) {
            var selected = _selectedTxn === r.transaction_id;
            var source = [r.gateway_row].concat(r.bank_row_ids || [], r.ledger_row || []).filter(Boolean).join(" · ");
            return '<tr data-tid="' + esc(r.transaction_id) + '" tabindex="0" class="' + (selected ? "is-selected" : "") + '">' +
              '<td><span class="id">' + esc(r.transaction_id) + '</span><span class="sub">' + softTokens(r.rule || "—") + "</span></td>" +
              '<td class="id" style="font-size:.75rem">' + esc(source || "—") + "</td>" +
              '<td class="num">' + esc(inr(r.amount)) + "</td>" +
              "<td>" + statusTag(r.status) + "</td>" +
              "<td>" + tierTag(r.tier) + "</td></tr>";
          }).join("") : '<tr><td colspan="5"><div class="empty"><strong>No transactions match</strong>Adjust the search or filter.</div></td></tr>') +
          "</tbody></table></div></div></div>" +

        '<div class="block" id="txn-detail" aria-live="polite"><div class="block__head"><h2>Transaction</h2><p>Match, settlement, and evidence</p></div>' +
          '<div class="block__body">' + (_selectedTxn ? skeletonHtml(5) :
            '<div class="empty"><strong>Select a transaction</strong>Its financial context appears here.</div>') + "</div></div>" +
      "</div>";

    var search = document.getElementById("txn-search");
    if (search) {
      search.addEventListener("input", function () {
        _txSearch = search.value;
        renderTransactionsPanel();
        var next = document.getElementById("txn-search");
        if (next) { next.focus(); next.setSelectionRange(next.value.length, next.value.length); }
      });
      search.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") return;
        var exact = (_transactions.transactions || []).filter(function (r) {
          return r.transaction_id.toLowerCase() === search.value.trim().toLowerCase();
        })[0];
        if (exact) { _selectedTxn = exact.transaction_id; renderTransactionsPanel(); }
      });
    }
    host.querySelectorAll("[data-tx-filter]").forEach(function (btn) {
      btn.addEventListener("click", function () { _txFilter = btn.dataset.txFilter; renderTransactionsPanel(); });
    });
    host.querySelectorAll("[data-tx-sort]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var field = btn.dataset.txSort;
        if (_txSort.field === field) _txSort.dir = _txSort.dir === "asc" ? "desc" : "asc";
        else { _txSort.field = field; _txSort.dir = "asc"; }
        renderTransactionsPanel();
      });
    });
    bindQueueTable(host, "#txn-detail", function (tid) { _selectedTxn = tid; renderTransactionsPanel(); }, function (tid) { loadTxnDetail(tid); });

    if (_selectedTxn) loadTxnDetail(_selectedTxn);
  }

  /* ── Transaction detail fragment (shared by both panels) ──────────── */

  /* Machine output is marked before it exists: the action that asks for it, and
     the plate that returns it, are both a distinct kind of thing from the
     deterministic result. Advisory must never read as authoritative. */
  var MACHINE_MARK = '<svg class="machine__mark" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true">' +
    '<circle cx="8" cy="8" r="6" stroke-dasharray="2.5 2.5"/>' +
    '<circle cx="8" cy="8" r="2" fill="currentColor" stroke="none"/></svg>';

  function factRow(label, value, mono) {
    return "<div><dt>" + esc(label) + "</dt><dd" + (mono ? ' class="mono"' : "") + ">" + esc(String(value)) + "</dd></div>";
  }

  function detailFragment(d) {
    var mr = d.matched_records || {};
    var s = d.settlement || {};
    var ev = d.evidence || {};
    var bankIds = d.bank_row_ids || [];
    var isStage3 = d.tier === "STAGE_3" && s && Object.keys(s).length > 0;
    var partial = d.status === "PARTIAL_PAYMENT"
      ? '<div class="callout"><strong>Partially settled</strong><p style="margin-top:.25rem">Received INR ' +
        esc(inr(d.received)) + " · outstanding INR " + esc(inr(d.outstanding)) + "</p></div>"
      : "";

    var actions = "";
    if (d.status === "AI_RETRY_REQUIRED") {
      if (d.tier === "TIER_3") actions += '<button class="btn btn--sm btn--oxide" type="button" data-retry="retry-llm">Retry adjudication</button>';
      else if (d.tier === "STAGE_3") actions += '<button class="btn btn--sm btn--oxide" type="button" data-retry="retry-stage3">Retry split adjudication</button>';
    }
    actions += '<button class="btn btn--sm btn--machine" type="button" data-retry="ai-review">' +
      MACHINE_MARK + "AI review · read-only</button>";

    var facts = [
      factRow("Rule", d.rule || "—"),
      factRow("Reason", d.reason || "—"),
      factRow("Gateway row", mr.gateway || d.gateway_row_id || "—", true),
      factRow("Bank rows", bankIds.length ? bankIds.join(", ") : (mr.bank || "—"), true),
      factRow("Ledger row", mr.ledger || d.ledger_row_id || "—", true),
      factRow("Amount", "INR " + inr(firstValue(d.gateway_amount, s.gross_amount, d.amount, d.received)), true),
      factRow("Expected net", "INR " + inr(firstValue(s.expected_net_amount, s.expected_net, d.expected_net)), true)
    ];
    if (d.llm_consulted !== undefined) facts.push(factRow("AI consulted", d.llm_consulted ? "Yes" : "No"));
    if (d.confidence != null) facts.push(factRow("Advisory confidence", pct(Number(d.confidence) * 100) + "%", true));

    return el("div", { className: "detail" },
      '<div class="detail__id">' + esc(d.transaction_id || "—") + statusTag(d.status) + tierTag(d.tier) + "</div>" +
      '<div class="detail__actions">' + actions + "</div>" +
      '<div class="callout"><strong>Next action</strong><p style="margin-top:.25rem">' + esc(nextActionFor(d.status)) + "</p></div>" +
      partial +
      '<dl class="facts">' + facts.join("") + "</dl>" +
      (isStage3
        ? '<div class="subhead"><span class="label subhead__label">Settlement · Decimal arithmetic</span>' +
          settlementLedger(s) + "</div>"
        : "") +
      '<div class="subhead subhead--authority"><span class="label subhead__label">Matching evidence · deterministic</span>' + evidenceRows(ev) + "</div>" +
      '<div data-review-out></div>'
    );
  }

  function el(tag, attrs, html) {
    var node = document.createElement(tag);
    if (attrs) node.setAttribute("class", attrs.className || "");
    if (attrs && attrs.role) node.setAttribute("role", attrs.role);
    if (html != null) node.innerHTML = html;
    return node;
  }

  function bindDetailActions(scope, tid) {
    scope.querySelectorAll("[data-retry]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var label = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Working…";
        if (btn.dataset.retry === "ai-review") reviewTransaction(tid, btn, label, scope);
        else retryTransaction(tid, btn, label, btn.dataset.retry, scope);
      });
    });
  }

  /* A dedicated output slot: existing content is never wiped. */
  function reviewOut(scope) {
    var host = scope && scope.querySelector ? scope : document;
    var slot = host.querySelector("[data-review-out]");
    if (!slot) {
      slot = document.createElement("div");
      slot.setAttribute("data-review-out", "");
      if (host !== document) host.appendChild(slot);
    }
    return slot;
  }

  async function retryTransaction(tid, button, label, endpoint, scope) {
    var slot = reviewOut(scope || button.parentNode);
    try {
      var res = await fetch(API + "/api/transaction/" + encodeURIComponent(tid) + "/" + endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      var data = await res.json();
      if (res.status === 503) {
        var notice = el("div", { className: "notice notice--oxide" });
        notice.innerHTML = "<span><strong>" + esc(tid) + " is still retryable.</strong> " +
          esc(data.reason || "The provider was unavailable, so the stored result was left unchanged.") + "</span>";
        slot.innerHTML = "";
        slot.appendChild(notice);
        button.disabled = false;
        button.textContent = label;
        return;
      }
      if (!res.ok) throw new Error(data.error || "Retry failed");
      var done = el("div", { className: "notice" });
      done.innerHTML = "<span><strong>" + esc(tid) + " resolved as " + esc(data.status || "MATCH") + ".</strong> " +
        esc(data.rule || "") + (data.reason ? " · " + esc(data.reason) : "") + "</span>";
      slot.innerHTML = "";
      slot.appendChild(done);
      button.textContent = "Resolved";
      await loadExceptions(true);
      await loadTransactions();
      if (_currentPanel === "exceptions") loadExcDetail(tid);
    } catch (err) {
      button.disabled = false;
      button.textContent = label;
      var warn = el("div", { className: "notice notice--oxide" });
      warn.innerHTML = "<span>" + esc(err.message) + "</span>";
      slot.innerHTML = "";
      slot.appendChild(warn);
    }
  }

  async function reviewTransaction(tid, button, label, scope) {
    var slot = reviewOut(scope || button.parentNode);
    try {
      var data = await fetchJson("/api/transaction/" + encodeURIComponent(tid) + "/ai-review", { method: "POST" });
      var review = data.review || {};
      var unavailable = data.source === "DETERMINISTIC_FALLBACK";
      var block = el("div", { className: "machine" + (unavailable ? " machine--unavailable" : "") });
      block.innerHTML = '<div class="machine__head">' + MACHINE_MARK +
        '<span class="machine__title">AI review</span>' +
        '<span class="tag ' + (unavailable ? "tag--quiet" : "tag--ink") + ' machine__state">' +
        (unavailable ? "Gemini unavailable" : "Gemini · read-only") + "</span></div>" +
        '<dl class="facts">' +
        factRow("Decision", review.decision || "—") +
        factRow("Confidence", review.confidence != null ? pct(Number(review.confidence) * 100) + "%" : "Unavailable", true) +
        factRow("Rationale", review.rationale || "—") +
        factRow("Evidence", evidenceText(review.evidence || {}), true) +
        '</dl><p class="machine__note">' + (unavailable
          ? "No provider answered, so this is the stored pipeline result read back — not a model judgement."
          : "A model assessment of stored context. It cannot change status, select rows, or alter the settlement; the stored result is untouched.") + "</p>";
      slot.innerHTML = "";
      slot.appendChild(block);
      button.textContent = "Reviewed";
    } catch (err) {
      button.disabled = false;
      button.textContent = label;
      var warn = el("div", { className: "notice notice--oxide" });
      warn.innerHTML = "<span>" + esc(err.message) + "</span>";
      slot.innerHTML = "";
      slot.appendChild(warn);
    }
  }

  /* ── Settlement Intelligence ──────────────────────────────────────── */

  function initQA() {
    if (_qaInited) return _qaReady;
    _qaInited = true;
    var host = document.getElementById("qa-content");
    if (host) host.innerHTML = skeletonHtml(6);
    _qaReady = Promise.all([fetchJson("/api/overview"), fetchJson("/api/transactions")])
      .then(function (responses) {
        _overview = responses[0];
        _transactions = responses[1];
        setSourceScope();
        renderSettlementWorkspace();
      })
      .catch(function (err) {
        _qaInited = false;
        if (host) { host.innerHTML = ""; host.appendChild(errorState(err.message, "settlement", function () { initQA(); })); }
        throw err;
      });
    return _qaReady;
  }

  function renderSettlementWorkspace() {
    var host = document.getElementById("qa-content");
    if (!host || !_overview || !_transactions) return;
    var d = _overview;
    var t4 = d.stage3_summary || {};
    var rows = (_transactions.transactions || []).filter(function (r) {
      return r.tier === "STAGE_3" && r.settlement && Object.keys(r.settlement).length > 0;
    });
    var focus = rows.find(function (r) {
      return (r.bank_row_ids || []).length > 1 && isMatched(r.status);
    }) || rows[0];

    function sum(key) {
      return rows.reduce(function (total, r) {
        var n = Number((r.settlement || {})[key] || 0);
        return total + (isFinite(n) ? n : 0);
      }, 0);
    }
    var expected = sum("expected_net_amount");
    var actual = sum("actual_bank_amount");
    var variance = sum("variance");
    var evaluated = count(t4.total_evaluated);

    /* The position must survive the reader's own subtraction. A row with no
       computed variance (an unresolved split) contributes its whole shortfall to
       expected-minus-actual while adding nothing to the reported variance, so the
       strip states that split instead of letting the numbers quietly disagree. */
    var difference = expected - actual;
    var unreported = rows.filter(function (r) {
      var s = r.settlement || {};
      return s.variance === null || s.variance === undefined || s.variance === "";
    });
    var unreportedGap = unreported.reduce(function (total, r) {
      var s = r.settlement || {};
      var e = Number(s.expected_net_amount || 0);
      var a = Number(s.actual_bank_amount || 0);
      return total + (isFinite(e - a) ? e - a : 0);
    }, 0);
    var explained = sum("explained_variance");
    var remaining = sum("remaining_variance");

    var metrics = [
      ["Fees + MDR", inr(sum("total_fee_amount") + sum("mdr_amount")), "deductions"],
      ["Taxes", inr(sum("gst_amount") + sum("tds_amount")), "GST and TDS"],
      ["Refunds", inr(sum("refund_amount")), "credited back"]
    ];

    /* The position is an identity, so it prints as one: expected, actual, the
       difference between them, and how much of it the engine actually reported. */
    var positionLedger =
      ledgerLine("expected net · " + rows.length + " settlements", expected) +
      ledgerLine("actual bank", actual) +
      ledgerLine("= difference", difference, "sum") +
      ledgerLine("reported by settlement rows", variance) +
      ledgerLine("  explained", explained) +
      ledgerLine("  remaining", remaining, "total");

    var positionNote = unreported.length
      ? "Difference minus reported variance is INR " + inr(unreportedGap) + ": " + unreported.length + " " +
        (unreported.length === 1 ? "settlement carries" : "settlements carry") +
        " no computed variance (" + unreported.map(function (r) { return r.transaction_id; }).join(", ") + "). " +
        "The engine reports that shortfall; it does not absorb it into a variance it never computed."
      : "Expected net minus actual bank equals the sum of the per-row variances the engine reported.";

    var reasons = rows.filter(function (r) {
      return !isMatched(r.status) || (r.settlement.variance && Math.abs(Number(r.settlement.variance)) > 0.01);
    }).slice(0, 8);
    var evidence = focus ? [focus] : [];
    var evaluated4 = [
      ["Settled", count(t4.match_count)],
      ["Partial", count(t4.partial_count)],
      ["Unresolved", count(t4.unresolved_count) + count(t4.ambiguous_count)]
    ];

    var promptTransaction = focus ? focus.transaction_id : null;
    var hint = promptTransaction
      ? ["What happened to " + promptTransaction + "?", "What is the variance for " + promptTransaction + "?", "Show unresolved transactions."]
      : ["Show unresolved transactions.", "Which transactions need human review?"];

    var evidenceHtml = focus
      ? '<div class="subhead"><span class="label subhead__label">Evidence case</span><dl class="facts">' +
        factRow("Transaction", focus.transaction_id, true) +
        factRow("Status", focus.status) +
        factRow("Bank rows", (focus.bank_row_ids || []).join(", ") || "—", true) +
        factRow("Reason", focus.reason || "—") +
        "</dl></div>"
      : '<div class="empty"><strong>No Stage 3 evidence</strong>This run returned no split-settlement detail.</div>';

    host.innerHTML =
      '<div class="block"><div class="block__head"><h2>Settlement position</h2><p>Stage 3 results only · INR</p></div>' +
        '<div class="block__body">' + '<div class="ledger">' + positionLedger + "</div>" +
          '<div class="metrics" style="margin-top:.9rem">' + metrics.map(function (m) {
            return '<div class="metric"><span class="label metric__k">' + esc(m[0]) + '</span><span class="metric__v">' + esc(m[1]) +
              '</span><span class="metric__note">' + esc(m[2]) + "</span></div>";
          }).join("") + "</div>" +
        "</div>" +
        '<div class="block__foot' + (unreported.length ? " callout--oxide" : "") + '">' + esc(positionNote) + "</div></div>" +

      '<div class="split-panel">' +
        '<div class="stack">' +
        '<div class="block"><div class="block__head"><h2>Stage 3 outcomes</h2><p>' + evaluated + " evaluated</p></div>" +
          '<div class="block__body block__body--flush"><div class="table-scroll" style="border:0;max-height:none"><table class="grid-table"><thead><tr>' +
            '<th scope="col">Outcome</th><th scope="col" class="num">Count</th><th scope="col" class="num">Share</th></tr></thead><tbody>' +
            evaluated4.map(function (r) {
              return "<tr><td>" + esc(r[0]) + '</td><td class="num">' + r[1] + '</td><td class="num">' + pct(evaluated ? r[1] / evaluated * 100 : 0) + "%</td></tr>";
            }).join("") + "</tbody></table></div></div></div>" +

      '<div class="block"><div class="block__head"><h2>Grounded question</h2><p>Deterministic answer first · citations retained · AI optional</p></div>' +
        '<div class="block__body">' +
          '<div class="log" id="qa-log"><div class="empty"><strong>No question asked yet</strong>Use a prompt below, or the command line at the top of the console.</div></div>' +
          '<div class="command__hints" style="border:0;padding-inline:0">' + hint.map(function (q) {
            return '<button class="hint" type="button" data-ask="' + esc(q) + '">' + esc(q) + "</button>";
          }).join("") + "</div>" +
        "</div></div>" +
        "</div>" +

        '<div class="stack">' +
        '<div class="block"><div class="block__head"><h2>Variance to read</h2><p>Settlements that are not clean</p></div>' +
          '<div class="block__body block__body--flush"><div class="table-scroll" style="border:0;max-height:none"><table class="grid-table"><thead><tr>' +
            '<th scope="col">Transaction</th><th scope="col">Reason</th><th scope="col" class="num">Variance</th></tr></thead><tbody>' +
            (reasons.length ? reasons.map(function (r) {
              return '<tr><td><span class="id">' + esc(r.transaction_id) + '</span><span class="sub">' + esc(r.status || "") + "</span></td>" +
                '<td style="max-width:24ch">' + softTokens(r.reason || "—") + '</td><td class="num">' + esc(inr(r.settlement.variance)) + "</td></tr>";
            }).join("") : '<tr><td colspan="3"><div class="empty"><strong>No settlement mismatch</strong>Every evaluated settlement closes within tolerance.</div></td></tr>') +
            "</tbody></table></div></div></div>" +

      '<div class="block"><div class="block__head"><h2>Evidence case</h2><p>One live Stage 3 result, with the rows that carried it</p></div>' +
        '<div class="block__body">' + evidenceHtml + "</div></div>" +
        "</div>" +
      "</div>";

    host.querySelectorAll("[data-ask]").forEach(function (btn) {
      btn.addEventListener("click", function () { askQuestion(btn.dataset.ask, "#qa-log"); });
    });
  }

  function initConsoleAsk() {
    var form = document.getElementById("console-ask");
    var input = document.getElementById("console-ask-input");
    if (!form || !input) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var question = input.value.trim();
      if (!question) return;
      input.value = "";
      switchPanel("qa");
      var ready = initQA();
      if (!ready) return;
      ready.then(function () { askQuestion(question, "#qa-log"); }).catch(function () { /* surfaced in the panel */ });
    });
  }

  function initConsole() {
    initConsoleAsk();
    /* The shell's run state must be true on every panel, not just Overview. */
    fetchJson("/api/overview").then(function (d) {
      _overview = d;
      setRunStatus("Run ready", "ready");
      updateBadges(d);
    }).catch(function () {
      setRunStatus("Data unavailable", "error");
    });
    var nav = document.getElementById("nav");
    if (nav) {
      nav.addEventListener("click", function (event) {
        var item = event.target.closest(".rail__item");
        if (!item) return;
        switchPanel(item.dataset.panel);
      });
    }
    document.addEventListener("click", function (event) {
      var jump = event.target.closest("[data-jump-panel]");
      if (jump) { event.preventDefault(); switchPanel(jump.dataset.jumpPanel); }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && _currentPanel === "exceptions" && _excSearch) {
        _excSearch = "";
        renderExceptions();
      }
      if (event.key === "/" && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
        var field = document.querySelector(".panel.is-active input[type=search]");
        if (field) { event.preventDefault(); field.focus(); }
      }
    });
    window.addEventListener("hashchange", function () {
      var panel = window.location.hash.replace(/^#/, "");
      if (PANEL_META[panel] && panel !== _currentPanel) switchPanel(panel);
    });

    var initial = window.location.hash.replace(/^#/, "");
    switchPanel(PANEL_META[initial] ? initial : "overview");
  }

  /* ── Boot ─────────────────────────────────────────────────────────── */

  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("theme-toggle");
    if (toggle) toggle.addEventListener("click", toggleTheme);
    initTheme();
    if (surface === "console") initConsole();
    else initPitch();
  });

})();
