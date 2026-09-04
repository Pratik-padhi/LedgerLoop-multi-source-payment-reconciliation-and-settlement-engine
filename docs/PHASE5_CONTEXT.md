# LedgerLoop — Phase 5 Context Handoff

**Purpose of this file:** concise handoff for transferring this project to another
Claude/ChatGPT session without losing state. Read this first, then the source files
if deeper detail is needed.

---

## 1. What LedgerLoop is

A multi-source payment reconciliation engine built for the Razorpay AI Buildathon
(Track 04 — AI Finance Controller), targeting a 6–12 month internship. It
reconciles three independent, imperfect data sources — **gateway**, **bank**,
**ledger** — using a tiered matching pipeline, ending in a bounded natural-language
Q&A agent (not yet built). Built by Pratik, who holds SAP S/4HANA Business
Process Integration + ABAP Cloud certifications, used authentically in the schema
design (tax/TDS fields, settlement semantics), not as decoration.

Submission deadline: **September 5**.

## 2. Architecture / phases

```
CSV (gateway.csv, bank.csv, ledger.csv)
  → Phase 2: Normalize        (core/normalize.py)
  → Phase 3: Tier 1 — exact match       (core/match_exact.py)
  → Phase 4: Tier 2 — deterministic fuzzy/tolerance   (core/match_fuzzy.py)
  → Phase 5: Tier 3 — deterministic-first + LLM-assisted   (core/match_llm.py)
  → Phase 6: Controller UI + Settlement Q&A (app.py — Flask; core/qa_agent.py)
```

Every tier: takes only the **prior tier's residue**, never reprocesses a prior
tier's MATCHED result, never consults `ground_truth.csv` for decisions (ground
truth is evaluation-only, applied strictly after matching), enforces one-to-one
source-row consumption, and produces `Status → Reason → Evidence → Action` —
never a bare score.

Guiding principle throughout: **"An unresolved transaction is better than an
incorrect financial match."**

## 3. Current baseline

**271 tests pass, 30 subtests pass, 0 fail**. Run: `python3 -m pytest -v` from the project root (needs
`core/__init__.py`, `tests/__init__.py`, and `data/*.csv` present — see §8).

Phase-by-phase test counts: Phase 2 (normalize) = 31 tests, Phase 3 (Tier 1) = 34 tests, Phase 4 (Tier 2) = 44 tests, Phase 5 (Tier 3) = 34 tests, Phase 5b (Gemini client) = 4 tests, Phase 6 (Q&A Agent) = 77 tests, Phase 6b (Controller UI) = 39 tests. Total = 271.

## 4. Phase 5 / Tier 3 behavior

**Deterministic rules (tried first, zero LLM calls, resolve most real residue):**
- `REFUND_LINKED_NET_AMOUNT` — gateway + linked `-REFUND` row nets to bank settlement exactly.
- `TDS_LINKED_NET_AMOUNT` — gateway amount minus ledger's `tds_amount` equals bank settlement exactly.
- `DESCRIPTION_LINKED_REFERENCE` — bank free-text description contains ledger `invoice_reference` or gateway `customer_reference`, amount matches exactly, candidate unique.

**LLM-assisted rule (only path that ever calls an LLM):**
- `SPLIT_SETTLEMENT_SUM` — two+ bank credits whose sum is *close but not exact* to the gateway amount (real case: `PAY109`, ₹6400.00 vs ₹6395.50 across two credits). A deterministic pre-check first verifies at least one 2-subset sum falls within `SPLIT_SETTLEMENT_TOLERANCE` (₹5.00) before any LLM call is even attempted — no call is spent chasing evidence that can't exist.

**Dispositions:** `MATCH` / `HUMAN_REVIEW` / `UNRESOLVED`. On the real dataset:
10 matched without LLM, 11 matched with a valid split-settlement LLM
recommendation, 5–6 routed to human review, 8 genuinely unresolved (true
orphans, decoys, no-bank-counterpart).

## 5. LLM safety boundaries (unchanged, load-bearing)

The LLM is **only ever a recommender**. `LLMAdjudicator._validate_split_recommendation()`
independently re-derives the arithmetic from raw records before accepting anything.
The LLM can NEVER:
- override Tier 1/2 results
- invent a `source_row_id` (every proposed ID must be in the pre-vetted candidate set)
- force a match on ambiguous/symmetric evidence
- match on similarity alone (no embeddings, no fuzzy scoring)
- bypass arithmetic validation (sum is recomputed in Python from raw amounts, tolerance checked in `Decimal`)
- violate one-to-one consumption (validator checks candidate availability before accepting)

Invalid/unparseable/fabricated/out-of-tolerance LLM output → `HUMAN_REVIEW`
with `REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR`. No API key or API
outage → `HUMAN_REVIEW` with `REASON_LLM_UNAVAILABLE` (safe fallback, never
a crash, never a silent guess).

## 6. Gemini integration

`match_llm.py` contains only `GeminiLLMClient` as a production provider,
implementing the `LLMClient` Protocol. `run_tier3` selects it when
`LLM_PROVIDER=gemini` or when `GEMINI_API_KEY` is configured; other provider
values use deterministic-only mode. An explicit test or application client
may still be injected.

**Implementation:** `GeminiLLMClient` (in `core/match_llm.py`) calls Gemini's
REST `generateContent` endpoint directly via `urllib` (no new SDK dependency).
Default model: `gemini-3.6-flash`. Requests `application/json`
response mime type from Gemini directly (reduces parsing fragility vs. the
Anthropic client's markdown-fence-stripping fallback, though `LLMAdjudicator`
still has that fallback for safety).

**Security:**
- Key read only via `os.environ.get("GEMINI_API_KEY")` — never hardcoded, never
  a default parameter value.
- Sent only as the `x-goog-api-key` HTTP header — never in the URL, body, or
  query string.
- Never printed/logged anywhere in the client.
- Not present in any committed file (verify with `git diff` before committing
  any `.env` file — none was created by this session).
- Missing key → `LLMUnavailableError` raised before any network call is
  attempted (verified by `test_missing_api_key_raises_llm_unavailable_without_network_call`).

## 7. Files changed this session

| File | Change |
|---|---|
| `core/match_llm.py` | Removed non-Gemini providers and restricted automatic selection to Gemini. |
| `tests/test_gemini.py` | Gemini client configuration, safe missing-key behavior, and mocked response parsing. |
| `docs/PHASE5_CONTEXT.md` | This file (new). |

Tier 1, Tier 2, and all reconciliation rules: **untouched**.

## 8. How to configure and run

```bash
# Set the key (never commit this)
export GEMINI_API_KEY="your-key-from-ai-studio"

# From project root (needs core/, tests/, data/{gateway,bank,ledger,ground_truth}.csv)
python3 -m pytest -v

# Smoke test the Gemini client's config path directly (no API call, safe without a key)
python3 -c "
from core.match_llm import GeminiLLMClient, LLMUnavailableError
c = GeminiLLMClient()
try:
    c.complete('test', 'test')
except LLMUnavailableError as e:
    print('Expected without key:', e)
"

# To actually exercise Tier 3 end-to-end with live Gemini calls:
python3 -c "
from core.match_exact import run_tier1, get_residue
from core.match_fuzzy import run_tier2
from core.match_llm import run_tier3, GeminiLLMClient
r1, _, matcher = run_tier1(data_dir='data', return_matcher=True)
r2, _ = run_tier2(get_residue(r1), matcher)
r3, summary = run_tier3(r2, matcher, llm_client=GeminiLLMClient())
print(summary)
"
```

Expected test output: `271 passed, 30 subtests passed`.

## 9. Known limitations / free-tier considerations

- Google AI Studio free tier has request-per-minute and daily quotas; `GeminiLLMClient`
  does not implement retry/backoff — a `429` will surface as a `urllib.error.URLError`
  → `LLMUnavailableError` → safe `HUMAN_REVIEW`/`REASON_LLM_UNAVAILABLE` fallback
  (never a crash), but it also means transient rate-limiting looks identical to a
  genuine outage from the caller's perspective. Acceptable for now; a future
  session could add limited retry with backoff if quota errors prove common in
  testing.
- Real dataset only produces **one** LLM-eligible case (`PAY109`), so live-Gemini
  behavior on this exact dataset can only be smoke-tested against that single
  transaction — broader validation would need synthetic split-settlement cases.
- `gemini-3.6-flash` is used as the default model; not
  independently benchmarked against other variants for
  this specific JSON-recommendation task.
- No `.env` / secrets-loading convention has been set up yet (e.g. `python-dotenv`).
  Currently assumes the key is present in the process environment however the
  deployment target sets it.

## 10. Exact recommended next step

Per the user's explicit instruction, this session **stops after Gemini
integration and documentation**. The next session should:

1. Confirm `python3 -m pytest -v` still shows 271 passed in the new environment.
2. (Optional, if a live key is available) Run the live-Gemini smoke-test snippet
   in §8 against `PAY109` and confirm `status == MATCH`, `rule == SPLIT_SETTLEMENT_SUM`,
   `llm_consulted == True`.
3. Phase 6 (Settlement Q&A Agent + Controller UI) is now **built and tested** — `core/qa_agent.py`, `app.py`, `ui/index.html`, `tests/test_qa_agent.py`, `tests/test_ui_server.py`. No further Phase 6 work is needed.
4. Do NOT modify Tier 1/2/3 logic without explicit sign-off, per the project's
   established gate-based-progression working style.
