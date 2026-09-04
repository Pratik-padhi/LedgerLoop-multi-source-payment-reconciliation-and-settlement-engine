# LedgerLoop v2.1 — Project-State Checkpoint

## 1. PROJECT STATUS

- **Project**: LedgerLoop v2.1 — multi-source payment reconciliation engine (Razorpay AI Buildathon, submission deadline 2026-09-05).
- **Pipeline**: Phases 2–6 complete.
  - Phase 2: Normalization (`core/normalize.py`)
  - Phase 3: Tier 1 exact matching (`core/match_exact.py`)
  - Phase 4: Tier 2 tolerance matching (`core/match_fuzzy.py`)
  - Phase 5: Tier 3 deterministic-first + LLM-assisted (`core/match_llm.py`)
  - Phase 6: Controller UI + Settlement Q&A Agent (`app.py`, `core/qa_agent.py`)
- **Test baseline**: **279 passed, 30 subtests passed** (0 failures).

## 2. LLM PROVIDER

- **Gemini is the sole supported provider** through `GeminiLLMClient`.
- `run_tier3` selects Gemini for `LLM_PROVIDER=gemini`, or automatically when
  `GEMINI_API_KEY` is present. Other provider values fall back to deterministic-only.
- An explicit `llm_client` argument still takes precedence over env-based selection.
- **Gemini contract fix (2026-09-04)**: `GeminiLLMClient.complete` now sends an
  explicit `responseSchema` in `generationConfig`, making the structured output
  contract enforceable at the API level. The system prompt reinforces the schema
  and prohibits markdown-fenced or prose-wrapped responses. The existing robust
  JSON parser (`_parse_llm_json`) remains as a fallback for edge cases. This
  addresses the live PAY109 failure where Gemini's response was unparseable.

## 3. ENVIRONMENT

- `LLM_PROVIDER=gemini` (optional when `GEMINI_API_KEY` is set)
- `GEMINI_MODEL=gemini-3.6-flash` (optional; default)
- `GEMINI_API_KEY` is supplied through the environment and is never logged or committed.

## 4. TEST STATUS

- **279 passed**, **30 subtests passed**, **0 failures**.
- Gemini provider tests pass (`tests/test_gemini.py`), including request-schema validation.
- Settlement Q&A agent tests pass (`tests/test_qa_agent.py`).
- Controller UI server tests pass (`tests/test_ui_server.py`).
- **Caveat**: Unit tests mock the LLM client. They do **not** constitute proof of live Gemini integration success.

## 5. SAFETY / ARCHITECTURE CONSTRAINTS

- Do not weaken Python-side recommendation validation.
- Do not accept arbitrary LLM prose as a valid recommendation.
- Do not bypass Tier-3 validation.
- Do not expose API keys.
- Do not run broad / full-dataset LLM calls.
- Preserve deterministic Tier 1 / Tier 2 behavior.
- Prefer minimal, provider-agnostic changes.

## 6. FILES CURRENTLY RELEVANT

- `core/match_llm.py`
- `core/qa_agent.py` — Settlement Q&A Agent
- `app.py` — Controller UI server (Flask)
- `tests/test_match_llm.py`
- `tests/test_gemini.py`
- `tests/test_qa_agent.py`
- `tests/test_ui_server.py`
- `CLAUDE.md`
- `docs/PROGRESS.md`
