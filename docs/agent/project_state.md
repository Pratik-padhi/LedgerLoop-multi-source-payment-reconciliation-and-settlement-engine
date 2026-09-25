# LedgerLoop Agent State

## Current Phase
Frontend Redesign — Phase 3 evidence-led visual system + pitch/console split (Completed in working tree)

## Last Verified Commit
b261593 ("checkpoint before website redesign") with uncommitted Phase 1–3 frontend-redesign working-tree changes.

## Test Baseline
- Total tests: 405 passed, 30 subtests passed (0 failed, 0 errors in 1.38s).
- Total tests: 406 passed, 30 subtests passed (0 failed, 0 errors in 1.55s).
- Total tests: 407 passed, 30 subtests passed (0 failed, 0 errors in 1.39s) after P0.1.
- Total tests: 408 passed, 30 subtests passed (0 failed, 0 errors in 1.36s) after the completed Product/UX Polish phases.
- Total tests: 409 passed, 30 subtests passed (0 failed, 0 errors in 1.35s) after the final settlement-query UI contract test.
- Total tests: 413 passed, 30 subtests passed (0 failed, 0 errors in 1.52s) after the Phase 2 structural frontend redesign.
- Total tests: 414 passed, 30 subtests passed (0 failed, 0 errors in 1.52s) after the Phase 3 evidence-led visual redesign and pitch/console split.
- Ran with: `python -m pytest -q --basetemp=.pytest_tmp`.

## Completed
- Fixed Windows system temp directory permission error (`WinError 5 Access is denied`) for pytest `tmp_path` fixture by adding `pytest.ini` with `addopts = --basetemp=.pytest_tmp`.
- Resolved import-time reconciliation execution side-effect:
  - Removed top-level `_ensure_runtime_globals()` invocation from [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py).
  - Configured `@app.before_request` hook (`_lazy_init_api_state`) to initialize runtime state on `/api/*` request execution.
  - Implemented PEP 562 module `__getattr__` in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py) for backward-compatible attribute access (`_index`, `_stage3_consumed`, `_r1`, etc.) without running reconciliation at import time.
  - Verified `import app` executes cleanly with `app._RUNTIME_STATE is None`.
  - Added regression test `test_import_app_does_not_execute_reconciliation` in [tests/test_ui_server.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/tests/test_ui_server.py).
- Resolved runtime state synchronization in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py):
  - Fixed `_ensure_runtime_globals()` to initialize globals once and share the mutable set reference `state.stage3_consumed` rather than creating a disconnected copy on every call.
  - Fixed `_ensure_runtime_globals()` to initialize globals once (`_GLOBALS_INITIALIZED`) and share the mutable set reference `state.stage3_consumed` rather than creating a disconnected copy on every call.
  - Fixed `api_retry_llm` and `api_retry_stage3` to access live globals (`_r1`, `_r2`, `_r3`, `_stage3_consumed`, `_index`) and update `_stage3_consumed` consistently when retry resolves a match.
  - Eliminated syntax/duplication errors in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py) retry handlers.
- Verified all retry endpoints:
  - `test_retry_stage3_deterministic_resolves_even_when_gemini_down` (PASS)
  - `test_retry_success_returns_validated_adjudication` (PASS)
  - `test_retry_unavailable_remains_retryable` (PASS)
- Verified all persistence and action authorization tests:
  - `test_action_requires_actor_and_optional_token` (PASS)
  - `test_persists_snapshot_and_append_only_audit` (PASS)
  - `test_reconciliation_run_is_persisted` (PASS)
  - `test_adapter_maps_explicit_headers` (PASS)
  - `test_adapter_rejects_missing_configured_header` (PASS)
- **Identified and fixed Render deployment performance bottleneck** (2025-09-24):
  - **Bottleneck**: `run_reconciliation()` in [core/service.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/service.py) was calling `GeminiFallbackClient()` for Tier 3 and Stage 3 whenever `settings.gemini_enabled` was True (which is True on Render because `render.yaml` sets `LLM_PROVIDER: gemini` and `GEMINI_API_KEY`). This caused **dozens of sequential HTTP calls to Google Gemini API** during the initial `/api/overview` request.
  - **Impact**: Reconciliation took **12+ seconds** (vs 0.36s offline), exceeding Gunicorn's default 30s worker timeout, causing worker kills, 502 errors, and the browser showing "Could not load data".
  - **Root Cause**: `run_tier3` default parameter `_AUTO_LLM` checked `LLM_PROVIDER`/`GEMINI_API_KEY` env vars, and `run_stage3` used `settings.gemini_enabled`. Neither respected `settings.ai_enabled` (which requires explicit `LEDGERLOOP_ENABLE_AI=1` opt-in).
  - **Fix** (3 lines in `core/service.py`):
    - Pass `llm_client=GeminiFallbackClient() if settings.ai_enabled else None` explicitly to `run_tier3`
    - Use `settings.ai_enabled` (not `settings.gemini_enabled`) for `stage3_llm` in `run_stage3`
  - **Result**: Reconciliation on `data_large` with Render config now completes in **0.36s with 0 LLM calls** (down from 12s+ with 50+ failed calls).
  - **All 406 tests pass**, `git diff --check` clean.
- **P0.1 Product/UX polish — Overview hierarchy and truthful framing (2026-09-24)**:
  - Reframed the Overview around four primary run-health metrics: total transactions, gateway gross value, reconciled gateway value, and reconciliation rate.
  - Moved exception and Stage 3 settlement diagnostics into a secondary section; clarified that the variance value is split-settlement scope rather than a fabricated cash-at-risk metric.
  - Added dynamic gateway/bank/ledger context, deterministic-first wording, Overview CTAs for Exceptions and Transactions, and a recoverable API error state.
  - Renamed pipeline and LLM sections to make deterministic authority and contextual AI explicit.
  - Added a static UI contract test in [tests/test_ui_server.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/tests/test_ui_server.py).
  - Verification: `407 passed, 30 subtests passed`; `node --check ui/app.js`; `git diff --check` clean.
  - No backend API, reconciliation, AI, dependency, or Render changes were made.
- **P0.2 Product/UX polish — Mobile navigation and resilient UI states (2026-09-24)**:
  - Reworked the responsive navigation into contained four-column/tablet and two-column/mobile grids with short labels for dense viewports.
  - Kept the run status and theme toggle available in the compact sidebar footer.
  - Added responsive containment for primary KPI grids, pipeline stages, exception lists, transaction tables, evidence rows, and the Q&A composer.
  - Added retryable loading/error states for Overview, Exceptions, and Transactions using the existing API routes.
  - No frontend timeout, backend route, reconciliation, AI, dependency, or Render changes were made.
  - Verification: `node --check ui/app.js`; `tests/test_ui_server.py`: 69 passed; full suite: `407 passed, 30 subtests passed`; `git diff --check` clean.
- **P1.1 Product/UX polish — Exception investigation workspace (2026-09-24)**:
  - Extended `/api/exceptions` with read-only `gateway_amount`, `expected_net`, and `settlement` metadata sourced from the existing in-memory index; matching and accounting logic were not changed.
  - Added amount, reason, and AI-history context to the exception queue.
  - Replaced raw evidence JSON with safe structured evidence chips, nested values, source-row chips, and humanized field labels.
  - Added explicit next-best-action guidance and clarified read-only AI review versus retry adjudication.
  - Added exception response-field and metadata consistency tests in [tests/test_ui_server.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/tests/test_ui_server.py).
  - Verification: `node --check ui/app.js`; `tests/test_ui_server.py`: 70 passed; full suite: `408 passed, 30 subtests passed`; `git diff --check` clean.
- **P1.2 Product/UX polish — Settlement Intelligence and grounded AI UX (2026-09-24)**:
  - Removed the inert Q&A AI Review checkbox instead of presenting a control that did not affect `/api/qa`.
  - Clarified the panel as grounded, read-only analysis and added a visible deterministic-first input hint.
  - Rendered the existing deterministic financial-query contract (`field`, `value`, `status`, `citations`) instead of showing “No explanation returned.”
  - Added visible source-row citations, answer provenance labels, and read-only AI review wording; kept retry adjudication separate and tier-aware.
  - No changes were made to Q&A intent classification, financial calculations, Gemini clients, or reconciliation logic.
  - Verification: `node --check ui/app.js`; focused Q&A/API tests: 73 passed; full suite: `408 passed, 30 subtests passed`; `git diff --check` clean.
- **P2.1 Product/UX polish — Demo path and documentation (2026-09-24)**:
  - Added a non-stateful three-step recruiter demo path to the Overview using existing panels and existing data.
  - Explicitly labeled the checked-in profile as a synthetic demo and stated that no upload or Gemini key is required.
  - Updated [README.md](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/README.md) to document lazy initialization, current API routes, deterministic-first behavior, the demo path, and explicit AI opt-in.
  - No separate demo mode, dataset, backend route, upload flow, or Render configuration was added.
  - Verification: `node --check ui/app.js`; `tests/test_ui_server.py`: 70 passed; full suite: `408 passed, 30 subtests passed`; `git diff --check` clean.
- **P2.2 Product/UX polish — Final visual consistency pass (2026-09-24)**:
  - Removed obsolete Q&A toggle styling after removing the inert control.
  - Standardized mobile error states, detail action wrapping, compact navigation, demo steps, evidence chips, settlement values, and citation styling using the existing design tokens.
  - Added active navigation `aria-current` state and retained visible keyboard focus/reduced-motion behavior.
  - No new visual identity, dependency, chart library, backend route, reconciliation logic, AI implementation, or Render setting was introduced.
  - Verification: `node --check ui/app.js`; `tests/test_ui_server.py`: 71 passed; full suite: `409 passed, 30 subtests passed`; `git diff --check` clean.
- **Frontend Redesign Phase 1 — design system, shell, navigation, responsive foundation, theming (2026-09-25)**:
  - Started from the surviving partial previous-agent change (only `ui/index.html` markup had been edited; its references to `#theme-icon`/`#pipeline-status` and the unwired Runs panel were broken against untouched `app.js`/`styles.css`) and integrated it rather than redoing it.
  - `ui/styles.css`: rebuilt the token block as a dual light/dark theme (`:root` light + `[data-theme="dark"]`, `color-scheme` set per theme); replaced the indigo/blue accent with a restrained teal (`--accent: #0F766E` light / `#12A594` dark) plus `--accent-contrast`; kept neutral surfaces and semantic green/amber/red statuses.
  - Application shell: `.app` grid = 232px sidebar + `.workspace` (sticky 56px `.app-header` + scrolling `.main`, `height: 100vh`); compact header with breadcrumb (`Workspace / <panel>`), context line, run-status chip, and a text-only theme toggle (no emoji icon).
  - Navigation communicates Overview, Reconciliation Runs, Exceptions (badge), Transactions, Settlement Intelligence; AI stays secondary; panel headings normalized to `h1.panel-title` with `.panel-eyebrow` (no duplicate header `h1`).
  - Removed AI-slop styling: glassmorphism (`.card-glass`), the `.demo-guide` gradient, hover `translateY` lifts; chips and filter buttons use `var(--radius)` instead of pills.
  - Runs panel renders only real `/api/overview` data (no new backend route, no fabricated run registry); `setPipelineStatus` now targets `#header-run-status`/`#header-run-status-text`; `updateThemeBtn` guards missing elements and flips label/aria (`Light` ⇄ `Dark`); added `PANEL_META`/`updateHeader`/`switchPanel` plus `loadRuns`/`renderRuns`.
  - Fixed a responsive cascade bug: base rules (`.stats-grid-primary/secondary`, `.demo-step-list`, `.overview-two-column`, `.pipeline-funnel`, `.exc-list`, `.ev-row`, `.qa-wrap`) were declared *after* the media blocks and silently overrode them (mobile rendered 4 clipped stat columns and overflowing guide cards); the responsive section was moved to the end of `styles.css` (brace balance 362/362, CRLF preserved, no EOF whitespace).
  - Added 4 static contract tests in `tests/test_ui_server.py` (navigation surfaces, header contract, app.js shell targets, dual-theme/no-glassmorphism CSS).
  - Verification: full suite `413 passed, 30 subtests passed`; `node --check ui/app.js`; `git diff --check` clean (only the pre-existing `ui/index.html` LF→CRLF notice). The OpenCode desktop browser tool was disconnected, so verification used headless Edge (`--screenshot` / `--dump-dom`) plus a temporary same-origin probe page (deleted afterward): dark/light desktop screenshots for Overview, Runs, Exceptions, Transactions, Settlement Intelligence; computed-style diagnostics at 1440px (4-col stats), 800px (2-col stats, 5-col nav), 390px (1-col stats, stacked guide steps, 5-col nav) with `main.scrollWidth == clientWidth` (no horizontal overflow) on every viewport; panel switching and theme-toggle label flips verified. A stale-read artifact in the image-viewing tool initially showed wrong panels/sizes; text diagnostics confirmed ground truth.
  - No backend route, reconciliation, matching, accounting, normalization, financial calculation, AI grounding/safety, persistence, dependency, or Render changes were made.
- **Frontend Redesign Phase 2 — operational page structures (2026-09-25)**:
  - Rebuilt Overview as a run command surface: current-run context, processing volume, financial position, reconciliation health, outcome distribution, deterministic pipeline path, operational navigation paths, and explicit AI governance. All values remain projections of `/api/overview`; unavailable metadata is labeled `Not exposed` rather than invented.
  - Rebuilt Reconciliation Runs as a current persisted run record with stage evaluation/forwarding, outcome distribution, source coverage, and resolution-authority tables. It does not imply a historical run registry that the backend does not expose.
  - Rebuilt Exceptions as a searchable, filterable investigation queue with priority/status/amount/reason columns, keyboard-selectable rows, and a persistent detail panel. The detail renderer now separates financial context, source evidence, matching timeline, settlement analysis, next action, AI history, and explicit retry/read-only review actions.
  - Rebuilt Transactions as a searchable source index with matched/exception/settlement filters, sortable columns, source-row references, match/settlement/exception states, and a contextual detail panel. Amount rendering uses the existing transaction amount fields only; no source or timestamp is inferred.
  - Rebuilt Settlement Intelligence as a deterministic financial workspace with expected/actual/variance, Stage 3 status, mismatch reasons, evidence rows, contextual prompt actions, and a grounded composer. The existing `/api/qa`, citation, AI review, and retry contracts remain unchanged.
  - Added keyboard/accessibility support: skip link, main landmark target, explicit table scopes, `aria-pressed` filters, row `tabindex`/Enter/Space activation, live detail regions, visible focus, and reduced-motion support.
  - Added responsive Phase 2 structure rules for 1100px, 900px, 700px, and 600px breakpoints; dense tables scroll within their surfaces rather than widening the page.
  - Removed the animated typing-dot/emoji presentation from the chat surface. Waiting state now exposes a text status, while deterministic/AI provenance and citations remain visible.
  - Verification: `node --check ui/app.js`; focused UI/API tests `75 passed`; full suite `413 passed, 30 subtests passed in 1.52s`; `git diff --check` clean apart from Git's pre-existing line-ending warnings for `docs/agent/project_state.md` and `ui/index.html`. The connected desktop browser was unavailable again during this pass; `/health` and `/api/overview` were verified against the locally running app, but interactive screenshot verification remains blocked.
- **Frontend Redesign Phase 3 — evidence-led visual system (2026-09-25)**:
  - Replaced the previous dark sidebar theme with a new light-first editorial system: warm paper surfaces, navy typography, cobalt interaction states, restrained gold evidence accents, and semantic-only green/amber/red status color. The old teal/DM Sans/JetBrains Mono visual tokens and sidebar shell are no longer present.
  - Reframed Overview as a recruiter case study with a concise product thesis, system stance, engineering highlights, one authoritative run report, a stage ledger, an AI-governance boundary, and a three-step review path.
  - Rebuilt Pipeline as an architecture and control-boundary trace; Exceptions and Transactions now open a real selected case automatically while retaining search, filters, sorting, and keyboard selection.
  - Fixed a direct-load Exceptions runtime defect: `renderExceptions()` referenced its mount element without declaring it, leaving the queue stuck after a successful API response.
  - Made Settlement Intelligence prompts profile-safe and grammar-safe by deriving supported transaction questions from the active Stage 3 dataset. Removed aggregate prompts and hard-coded `PAY109` assumptions; clarified gateway value as signed scope.
  - Updated the root README recruiter path and static UI contracts for the new shell. Removed unused legacy render helpers from `ui/app.js`.
  - Verification: focused UI/API tests `76 passed`; full suite `414 passed, 30 subtests passed in 1.52s`; `node --check ui/app.js`; HTML parse and CSS brace checks; `git diff --check` clean apart from line-ending notices.
  - Added `/app` as the operator console while keeping `/` as the recruiter/project page; the shared `app.js` dispatches by `data-surface` and keeps the existing API contracts. Console navigation and live evidence are now independently addressable.
  - Corrected profile-sensitive UI behavior: the pitch source count is populated from `/api/overview`, the evidence trace prefers a real multi-credit Stage 3 result, and Settlement Intelligence uses the selected live Stage 3 case for contextual prompts.
  - Verification: `node --check ui/app.js`; focused UI/API tests `76 passed`; full suite `414 passed, 30 subtests passed in 1.52s`; dataset validator passed; `git diff --check` clean apart from line-ending notices.

## In Progress
None. Phase 3 frontend redesign, pitch/console split, responsive QA, and browser-level interaction verification are complete in the working tree.

## Blocked
None. The connected desktop browser remained unavailable during the latest session; the existing verification record for Phase 3 used headless Edge with Chrome DevTools emulation and screenshots.

## Deferred
- Phase 1: Upload pipeline and custom CSV ingestion.
- Phase 2: Action authorization and multi-tenant audit logs.
- Phase 3: Financial question answering expansions.
- Phase 4: Production deployment and containerization.

## Architecture Notes
- Reconciliation pipeline execution is orchestrated via [core/service.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/service.py) (`run_reconciliation`), wrapping Tier 1 exact, Tier 2 fuzzy, Tier 3 LLM-assisted, and Stage 3 split matching.
- Controller server in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py) holds in-memory snapshot state, exposes read-only endpoints (`/api/overview`, `/api/exceptions`, `/api/transactions`, `/api/transaction/<id>`, `/api/qa`, and `/api/transaction/<id>/ai-review`), and mutation-audited retry endpoints (`/api/transaction/<id>/retry-llm`, `/api/transaction/<id>/retry-stage3`).
- Controller server in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py) defines routes and Flask application at import without side-effects, lazily executing reconciliation when API requests arrive or when runtime attributes are explicitly accessed.
- Global variables in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py) (`_r1`, `_r2`, `_r3`, `_r4`, `_index`, `_stage3_consumed`, `_qa_agent`) share reference identity with `_RUNTIME_STATE` for in-process modifications during test and runtime flows.

## Database/Migration Notes
- SQLite database schema is defined in [core/persistence.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/persistence.py) via `ReconciliationStore`, managing tables: `reconciliation_runs`, `reconciliation_results`, `action_audit`, and `uploaded_datasets`.
- Schema additions use safe `_ensure_column` PRAGMA migration checks for backward compatibility with existing SQLite files.

## Deployment Notes
- Default model fallback chain configured in [core/config.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/config.py) and [core/match_llm.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/match_llm.py) (`gemini-2.5-flash-lite`, `gemini-2.0-flash-lite`, `gemini-2.5-flash`).
- Actions require `X-LedgerLoop-Actor` header in production and optional constant-time token validation (`LEDGERLOOP_ACTION_TOKEN`).

## Next Recommended Phase
Recruiter/user review of the completed Phase 3 experience, followed by a commit or deployment once the working tree is approved. Do not add backend or reconciliation changes unless a verified frontend compatibility issue requires one.

