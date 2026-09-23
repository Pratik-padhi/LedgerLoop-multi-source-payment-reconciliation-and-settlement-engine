# LedgerLoop Agent State

## Current Phase
Phase 0 — Baseline, Recovery and P0 Triage (Completed)

## Last Verified Commit
c3360fa ("Add Q&A report HTML and configuration tests") with uncommitted working-tree additions.

## Test Baseline
- Total tests: 405 passed, 30 subtests passed (0 failed, 0 errors in 1.38s).
- Total tests: 406 passed, 30 subtests passed (0 failed, 0 errors in 1.55s).
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

## In Progress
None.

## Blocked
None.

## Deferred
- Phase 1: Upload pipeline and custom CSV ingestion.
- Phase 2: Action authorization and multi-tenant audit logs.
- Phase 3: Financial question answering expansions.
- Phase 4: Production deployment and containerization.

## Architecture Notes
- Reconciliation pipeline execution is orchestrated via [core/service.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/service.py) (`run_reconciliation`), wrapping Tier 1 exact, Tier 2 fuzzy, Tier 3 LLM-assisted, and Stage 3 split matching.
- Controller server in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py) holds in-memory snapshot state, exposes read-only endpoints (`/api/overview`, `/api/exceptions`, `/api/transactions`, `/api/transaction/<id>`, `/api/qa`), and mutation-audited retry endpoints (`/api/transaction/<id>/retry-llm`, `/api/transaction/<id>/retry-stage3`).
- Controller server in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py) defines routes and Flask application at import without side-effects, lazily executing reconciliation when API requests arrive or when runtime attributes are explicitly accessed.
- Global variables in [app.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/app.py) (`_r1`, `_r2`, `_r3`, `_r4`, `_index`, `_stage3_consumed`, `_qa_agent`) share reference identity with `_RUNTIME_STATE` for in-process modifications during test and runtime flows.

## Database/Migration Notes
- SQLite database schema is defined in [core/persistence.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/persistence.py) via `ReconciliationStore`, managing tables: `reconciliation_runs`, `reconciliation_results`, `action_audit`, and `uploaded_datasets`.
- Schema additions use safe `_ensure_column` PRAGMA migration checks for backward compatibility with existing SQLite files.

## Deployment Notes
- Default model fallback chain configured in [core/config.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/config.py) and [core/match_llm.py](file:///d:/Projects/Deployed/LedgerLoop-multi-source-payment-reconciliation-and-settlement-engine/core/match_llm.py) (`gemini-2.5-flash-lite`, `gemini-2.0-flash-lite`, `gemini-2.5-flash`).
- Actions require `X-LedgerLoop-Actor` header in production and optional constant-time token validation (`LEDGERLOOP_ACTION_TOKEN`).

## Next Recommended Phase
Phase 1 — Ingestion & Upload Pipeline (or next planned milestone as directed).

