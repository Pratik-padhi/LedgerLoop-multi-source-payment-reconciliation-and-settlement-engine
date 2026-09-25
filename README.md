# LedgerLoop

LedgerLoop is a schema-driven, multi-source payment reconciliation and settlement engine. It compares payment gateway records with bank settlements and the internal ledger, then produces traceable outcomes for matched and exceptional transactions.

The current implementation is built around a fixed demo schema and CSV dataset. It can be extended to additional source formats, but it does not currently accept arbitrary CSV schemas without corresponding normalization support.

The repository layout and ownership boundaries are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The root `app.py` is intentionally retained as the Render/Gunicorn entrypoint; reconciliation logic lives under `core/`, datasets under `data/` and `data_large/`, and operational tooling under `scripts/`.

## Reconciliation pipeline

The pipeline processes only the previous tier's residue:

1. **Tier 1: deterministic exact matching** matches exact references and exact amounts.
2. **Tier 2: bounded matching** applies the documented amount tolerance and closed-set reference transformations.
3. **Tier 3: deterministic-first plus Gemini adjudication** handles supported linked refund/TDS/description cases and can consult Gemini for split-settlement recommendations. Python independently validates any LLM recommendation before accepting it.
4. **Human review** is retained for ambiguous, contradictory, unresolved, or unsupported evidence. The system prefers an unresolved transaction to an incorrect financial match.

Every result is structured for auditability as **Status -> Reason -> Evidence -> Action**, with source-row traceability and matching-tier details. The read-only Settlement Q&A layer answers supported questions from completed pipeline results; it does not run a second reconciliation engine or make matching decisions.

## Current demo dataset

The repository includes a synthetic dataset of 111 logical transactions across 115 gateway rows, 110 bank rows, and 116 ledger rows (excluding CSV headers). It includes normal exact matches, settlement delays, rounding differences, reference formatting, TDS mismatches, refunds, duplicate ledger entries, missing counterparts, orphan records, and Tier 3 cases requiring human review or LLM-assisted adjudication. `ground_truth.csv` is evaluation-only and is never consulted during matching.

## Recruiter demo path

The checked-in Render deployment is already a zero-configuration synthetic demo. A reviewer can explore the product without uploading files or configuring Gemini:

1. Start on **Overview** to understand the project stance, live run scope, financial position, and deterministic resolution path.
2. Open **Pipeline** to inspect source normalization, tier handoffs, one-to-one controls, and resolution authority.
3. Open **Exceptions** to start with the highest-priority discrepancy, then inspect its reason, source rows, settlement arithmetic, and next action.
4. Open **Transactions** to search the gateway-anchored index and inspect an active Stage 3 settlement case selected from the current dataset.
5. Open **Settlement Intelligence** to review expected net, actual bank value, variance, citations, and bounded transaction-specific questions.

The Settlement Intelligence prompts adapt to the active dataset instead of assuming a fixed transaction ID. In the compact local profile, `PAY109` is a deterministic split-settlement example; the expanded Render profile uses later Stage 3 cases. The UI selects a real Stage 3 result from whichever profile is running.

This is a guided presentation path, not a second demo mode or a second reconciliation dataset. The deterministic engine remains authoritative; AI is never required to load the dashboard or inspect deterministic results.

## Run locally

Use Python 3.13 or newer, install the dependencies, and start the development server:

```bash
python -m pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. Importing the Flask application does not run reconciliation. The first `/api/*` request lazily builds the in-memory reconciliation snapshot; `/health` remains a lightweight liveness check.

The UI and read-only JSON APIs are:

- `GET /`
- `GET /health`
- `GET /api/overview`
- `GET /api/exceptions`
- `GET /api/transactions`
- `GET /api/transaction/<id>`
- `POST /api/qa` with `{"question": "What happened to PAY109?"}`

## Tests

Run the full test suite with:

```bash
python -m pytest -v
```

Generated inspection reports are kept out of the source tree's main surfaces:
`docs/reports/` contains reports, while normalized and Tier 1 debug exports are
written under ignored subdirectories of `data/`.

For deterministic offline tests, leave `GEMINI_API_KEY` unset. The pipeline safely falls back to human review when Gemini is unavailable.

## Reproducible offline demo

```powershell
$env:LLM_PROVIDER=""
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
python scripts/validate_dataset.py
python -m pytest -q
python app.py
```

Completed runs persist to `instance/ledgerloop.sqlite3` by default (override
with `LEDGERLOOP_DATABASE`). It stores pipeline snapshots and audit records,
not source secrets or ground truth. Financial Q&A returns stored deterministic
settlement values only when available and includes source-row citations.

Schema adapters (`core.adapters.SourceSchema`) require explicit mappings; this
is not universal CSV support. Shared deployments should require a named
`X-LedgerLoop-Actor` and configure an action token before stateful actions.

## Gemini configuration

Gemini is optional and configured only through environment variables:

- `GEMINI_API_KEY` - required for live Gemini requests; never commit or expose this value.
- `LLM_PROVIDER=gemini` - optional; selects the supported Gemini provider.
- `GEMINI_MODEL=gemini-2.5-flash-lite` - optional model override. The same model is used by default in local and deployed configuration unless overridden.
- `GEMINI_MODELS` - optional comma-separated fallback model chain shown in the overview response.

`LEDGERLOOP_ENABLE_AI=1` is required for AI to participate in the reconciliation pipeline. Without it, dashboard loading and deterministic reconciliation remain offline and Gemini is used only by an explicit review/retry action.

## Dataset profiles

Local runs default to the compact `data/` dataset for fast, deterministic startup.
Set `LEDGERLOOP_DATA_DIR=data_large` to run the expanded deployment and benchmark
profile. The reconciliation service receives this selection explicitly, so tests
and other integrations can choose a dataset without changing matching logic.

The deterministic tiers and Settlement Q&A remain usable without an API key. The Q&A endpoint is configured for deterministic explanations by default.

## Deploy on Render

Create a Render Blueprint deployment from `render.yaml`:

- Runtime: Python
- Plan: Free
- Branch: `master`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Required environment variable: `GEMINI_API_KEY` (set as a Render secret if explicit Gemini review/retry actions are desired)
- Optional environment variables: `LLM_PROVIDER`, `GEMINI_MODEL`, `GEMINI_MODELS`, `LEDGERLOOP_ENABLE_AI`, and `LEDGERLOOP_DATA_DIR`

Render supplies `PORT`; Gunicorn imports the single Flask application as `app:app`. The included CSV data is read from the repository at startup, and no database or background worker is required for this demo deployment.

## Scope and safety boundaries

LedgerLoop is a hackathon/demo reconciliation service, not a general-purpose accounting system. Matching is schema-driven, one-to-one, tiered, and read-only from the UI/API layer. Secrets are loaded from the process environment, and missing or unavailable Gemini access never causes the deterministic pipeline to invent a match.
