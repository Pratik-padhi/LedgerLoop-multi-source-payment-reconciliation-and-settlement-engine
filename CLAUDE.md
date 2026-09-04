# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LedgerLoop is a multi-source payment reconciliation engine built for the Razorpay AI Buildathon. It reconciles three independent data sources — **gateway**, **bank**, and **ledger** — using a tiered matching pipeline that progresses from deterministic exact matching to tolerance-based fuzzy matching to LLM-assisted adjudication.

**Core principle**: "An unresolved transaction is better than an incorrect financial match."

**Submission deadline**: September 5, 2026

## Architecture: Tiered Pipeline

The reconciliation follows a strict progression where each tier operates ONLY on the previous tier's residue:

```
CSV Sources (gateway.csv, bank.csv, ledger.csv)
  ↓
Phase 2: Normalization (core/normalize.py)
  ↓
Phase 3: Tier 1 — Exact Match (core/match_exact.py)
  ↓
Phase 4: Tier 2 — Deterministic Fuzzy/Tolerance (core/match_fuzzy.py)
  ↓
Phase 5: Tier 3 — Deterministic-first + LLM-assisted (core/match_llm.py)
  ↓
Phase 6: Controller UI + Settlement Q&A (app.py — Flask; core/qa_agent.py)
```

### Key Architectural Invariants

1. **One-way flow**: No tier ever reprocesses or overrides a previous tier's MATCHED results
2. **Ground truth isolation**: `ground_truth.csv` is NEVER consulted during matching — it's evaluation-only, applied strictly after matching completes
3. **One-to-one consumption**: Each source row can be consumed at most once across all tiers
4. **Structured output**: Every result has `Status → Reason → Evidence → Action`, never a bare score

## Common Development Commands

### Run All Tests
```bash
python -m pytest -v
```
**Expected (offline, provider env vars cleared)**: 279 tests passed, 30 subtests passed.

### Run a Single Test
```bash
# By test class and method name
python -m pytest tests/test_match_llm.py::TestTier3LLM::test_split_settlement -v

# By keyword (matches any part of test name)
python -m pytest -k "split_settlement" -v

# Single unittest-style test
python -m unittest tests.test_normalize.TestNormalize.test_gateway_normalization -v
```

### Run Tests for Specific Phase
```bash
# Phase 2: Normalization (31 tests)
python -m unittest tests.test_normalize -v

# Phase 3: Tier 1 Exact Matching (34 tests)
python -m unittest tests.test_match_exact -v

# Phase 4: Tier 2 Fuzzy Matching (44 tests)
python -m unittest tests.test_match_fuzzy -v

# Phase 5: Tier 3 LLM-Assisted (34 tests)
python -m pytest tests/test_match_llm.py -v

# Phase 6: Settlement Q&A agent & Controller UI (77 + 39 tests)
python -m unittest tests.test_qa_agent -v     # SettlementQAAgent intents, read-only safety
python -m unittest tests.test_ui_server -v    # app.py Flask endpoints (/api/overview, /api/qa, ...)

# Gemini client configuration and parsing (unit-tested, mocked network)
python -m unittest tests.test_gemini -v
```

### Dependencies
No `requirements.txt` exists. The codebase uses only Python standard library modules plus:
- `decimal` (stdlib) — all monetary arithmetic
- `csv` (stdlib) — CSV parsing
- `urllib` (stdlib) — HTTP calls to Gemini API (no third-party HTTP lib)
- `pytest` — test runner (install: `pip install pytest`)
- `flask` — Controller UI server only (`app.py`; not needed by the engine itself)

### Run the Controller UI
```bash
# Starts the pipeline once, then serves the single-page UI + JSON API on :5000
python app.py
# Then open http://localhost:5000 (see ui/index.html, docs/qa_report.html)
```
`app.py` runs the full pipeline at startup and exposes read-only endpoints:
`/` (UI), `/api/overview`, `/api/exceptions`, `/api/transaction/<id>`, `POST /api/qa`.
It never re-runs matching per request and never consults `ground_truth.csv`.

### Generate Human-Readable Reports
```bash
# Export normalized canonical records to JSON
python scripts/export_normalized.py
# Output: data/normalized/*.json

# Generate Tier 1 matching report
python scripts/run_tier1_demo.py
# Output: outputs/tier1_*.json
```

### Dataset Validation
```bash
# Validate dataset structure and completeness
python scripts/validate_dataset.py

# Regenerate synthetic dataset (Phase 1 base + Phase 1.1 Tier 3 cases)
python scripts/generate_synthetic.py
python scripts/patch_phase1_1_tier3.py
```

## Tier-Specific Behaviors

### Tier 1: Exact Matching (`core/match_exact.py`)
- **What it does**: Matches on exact reference AND exact amount only
- **What it doesn't do**: No tolerance, no fuzzy logic, no date requirement
- **Output statuses**: `MATCHED` (all 3 sources) | `PARTIAL_MATCH` (2 of 3) | `UNRESOLVED_FOR_TIER_1`
- **Measured performance**: 81 full matches, 29 partial matches, 34 residue (70.43% match rate)

**Critical boundary**: Settlement date differences do NOT block matches if reference + amount are exact. This means `SETTLEMENT_DELAY` cases resolve at Tier 1, not Tier 2.

### Tier 2: Tolerance Matching (`core/match_fuzzy.py`)
- **Amount tolerance**: Exactly ₹0.05 (Decimal-based)
- **Date window**: 2 days (corroborating evidence only, never sufficient alone)
- **Reference transforms** (explicit closed set):
  - `IDENTITY` — already exact, only amount is fuzzy
  - `PREFIX_SWAP` — `GW086` ↔ `PAY086`
  - `BARE_NUMERIC` — `GW089` ↔ `089`
- **Output**: 10 matched, 0 ambiguous, 24 residue
- **Protected categories**: Refunds (structural suffix blocks transforms), TDS mismatches (outside tolerance), duplicates (ineligible)

### Tier 3: LLM-Assisted (`core/match_llm.py`)
**Deterministic rules tried FIRST** (zero LLM calls):
- `REFUND_LINKED_NET_AMOUNT` — gateway + linked `-REFUND` row nets to bank exactly
- `TDS_LINKED_NET_AMOUNT` — gateway minus `tds_amount` equals bank exactly
- `DESCRIPTION_LINKED_REFERENCE` — bank description contains ledger/gateway reference + exact amount + unique candidate

**LLM-assisted rule** (only path that calls LLM):
- `SPLIT_SETTLEMENT_SUM` — multiple bank credits whose sum is close (within ₹5.00) to gateway amount
- **Safety boundary**: LLM is ONLY a recommender; all arithmetic/availability is independently validated in Python before accepting

**Output dispositions**: `MATCH` | `HUMAN_REVIEW` | `UNRESOLVED`

**LLM provider**: `run_tier3` supports only `GeminiLLMClient`, selected by `LLM_PROVIDER=gemini` or automatically when `GEMINI_API_KEY` is present. Any other provider value is ignored. An explicit `llm_client` argument always overrides env selection.

### Phase 6: Controller UI + Settlement Q&A Agent
Two read-only consumer layers over the completed pipeline results — neither re-runs nor mutates reconciliation logic:

- **`core/qa_agent.py`** — `SettlementQAAgent` answers a **closed set** of intents (`LOOKUP`, `STATUS`, `WHY`, `EVIDENCE`, `FILTER_STATUS`, `FILTER_RULE`, `UNSUPPORTED`) via deterministic structured lookups against a `ReconciliationIndex` built from the pipeline output. Gemini is used only to compose prose explanations (bounded to already-retrieved data), never to make decisions. Unknown transaction → "not found", out-of-scope question → explicit refusal — no hallucination path. Build with `build_qa_agent(r1, r2, r3)`; index priority is Tier 3 > Tier 2 (matched) > Tier 1.
- **`app.py`** — Flask server that runs the pipeline once at startup and serves `ui/index.html` plus JSON endpoints (`/api/overview`, `/api/exceptions`, `/api/transaction/<id>`, `POST /api/qa`). By default the Q&A agent runs with `use_llm_for_explanations=False` (deterministic answers only, no Gemini call).

## LLM Configuration

### Gemini API Setup
```bash
# Set API key (NEVER commit this)
export GEMINI_API_KEY="your-key-from-ai-studio"
export GEMINI_MODEL="gemini-3.6-flash"  # optional; this is the default

# Smoke test without network call (safe without key)
python -c "
from core.match_llm import GeminiLLMClient, LLMUnavailableError
c = GeminiLLMClient()
try:
    c.complete('test', 'test')
except LLMUnavailableError as e:
    print('Expected without key:', e)
"
```

**Security invariants**:
- Key read ONLY via `os.environ.get("GEMINI_API_KEY")`
- Sent ONLY in HTTP `x-goog-api-key` header, never in URL/body
- Missing key → `LLMUnavailableError` → safe `HUMAN_REVIEW` fallback (never crashes)

## Dataset Structure

**Size**: 111 logical transactions across 116 gateway rows, 111 bank rows, 117 ledger rows

**Failure mode distribution**:
- 70 normal exact matches (63.1%)
- 8 settlement delays (7.2%)
- 7 rounding cases (6.3%)
- 5 reference formatting (4.5%)
- 5 TDS/tax mismatches (4.5%)
- 4 partial refunds (3.6%)
- 3 LLM-ambiguous matches (2.7%, Tier 3)
- 3 duplicate ledger entries (2.7%)
- 2 LLM needs human (1.8%, Tier 3)
- Remaining: orphans, no-counterpart cases

**Phase 1.1 Tier 3 cases** (PAY107–PAY111): Specifically designed to require LLM adjudication — split settlements, symmetric evidence, contradictory amounts, or missing structured references.

## Critical Files

### Core Modules
- `core/normalize.py` — Phase 2 canonical schema + normalization
- `core/match_exact.py` — Phase 3 Tier 1 exact matching
- `core/match_fuzzy.py` — Phase 4 Tier 2 tolerance matching
- `core/match_llm.py` — Phase 5 Tier 3 deterministic-first + LLM-assisted
- `core/qa_agent.py` — Phase 6 bounded, read-only Settlement Q&A agent
- `app.py` — Flask Controller UI server (runs pipeline once, serves JSON API + `ui/index.html`)

### Data Files
- `data/gateway.csv`, `data/bank.csv`, `data/ledger.csv` — source data
- `data/ground_truth.csv` — evaluation-only answer key
- `data/KNOWN_DISCREPANCIES.md` — human-readable discrepancy documentation

### Documentation
- `docs/README.md` — Phase 1 synthetic dataset overview
- `docs/SCHEMA.md` — Phase 2 canonical schema specification
- `docs/TIER1.md` — Phase 3 Tier 1 exact matching specification
- `docs/TIER2.md` — Phase 4 Tier 2 tolerance matching specification
- `docs/PHASE5_CONTEXT.md` — Phase 5 handoff document (Gemini integration)
- `docs/qa_report.html` — generated report illustrating the Q&A agent's answer format
- `docs/PROGRESS.md` — **authoritative project-state checkpoint**: current status, safety constraints, and what to work on next

## Working Conventions

1. **Gate-based progression**: Do NOT modify Tier 1/2/3 logic without explicit sign-off
2. **Test-first validation**: Every phase has comprehensive test coverage — run tests after any change
3. **Preserve traceability**: Every `CanonicalRecord` carries `source_row_id` and `raw_record`
4. **SAP authenticity**: Tax/TDS fields, settlement semantics reflect genuine SAP S/4HANA Business Process Integration patterns

## Known Limitations

1. **Gemini free tier**: No retry/backoff on rate limiting (429 → safe `HUMAN_REVIEW` fallback)
2. **Single LLM test case**: Real dataset has only one split-settlement case (PAY109) for live LLM testing
3. **Environment-sensitive tests**: `test_split_settlement_without_llm_client_defers_safely` and `test_counts_without_llm` in `tests/test_match_llm.py` call the pipeline with `llm_client=None` and expect zero LLM calls, but `run_tier3` reads `LLM_PROVIDER` from the environment. If `LLM_PROVIDER` + a provider API key are set in the shell, these two tests fire a **live network call** and fail (`llm_calls_made` becomes 1). Run the suite with provider env vars cleared (or unset them) for a deterministic, offline result.

## Next Development Steps

Per Phase 5/6 handoff (deadline 2026-09-05):
1. Confirm 279 tests still pass offline (provider env vars cleared)
2. (Optional) Live-test PAY109 (the single split-settlement case) with a Gemini API key — see Known Limitations #2
3. Do NOT modify core reconciliation logic (normalize / Tier 1 / Tier 2 / Tier 3) without explicit gate-based sign-off; the UI and Q&A agent are read-only consumers and must stay that way
