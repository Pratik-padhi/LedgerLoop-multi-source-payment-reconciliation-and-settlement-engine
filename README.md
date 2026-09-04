# LedgerLoop

LedgerLoop is a schema-driven, multi-source payment reconciliation and settlement engine. It compares payment gateway records with bank settlements and the internal ledger, then produces traceable outcomes for matched and exceptional transactions.

The current implementation is built around a fixed demo schema and CSV dataset. It can be extended to additional source formats, but it does not currently accept arbitrary CSV schemas without corresponding normalization support.

## Reconciliation pipeline

The pipeline processes only the previous tier's residue:

1. **Tier 1: deterministic exact matching** matches exact references and exact amounts.
2. **Tier 2: bounded matching** applies the documented amount tolerance and closed-set reference transformations.
3. **Tier 3: deterministic-first plus Gemini adjudication** handles supported linked refund/TDS/description cases and can consult Gemini for split-settlement recommendations. Python independently validates any LLM recommendation before accepting it.
4. **Human review** is retained for ambiguous, contradictory, unresolved, or unsupported evidence. The system prefers an unresolved transaction to an incorrect financial match.

Every result is structured for auditability as **Status -> Reason -> Evidence -> Action**, with source-row traceability and matching-tier details. The read-only Settlement Q&A layer answers supported questions from completed pipeline results; it does not run a second reconciliation engine or make matching decisions.

## Current demo dataset

The repository includes a synthetic dataset of 111 logical transactions across 116 gateway rows, 111 bank rows, and 117 ledger rows. It includes normal exact matches, settlement delays, rounding differences, reference formatting, TDS mismatches, refunds, duplicate ledger entries, missing counterparts, orphan records, and Tier 3 cases requiring human review or LLM-assisted adjudication. `ground_truth.csv` is evaluation-only and is never consulted during matching.

## Run locally

Use Python 3.13, install the dependencies, and start the development server:

```bash
python -m pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. The application runs the pipeline once at startup and serves the UI and read-only JSON APIs:

- `GET /`
- `GET /health`
- `GET /api/overview`
- `GET /api/exceptions`
- `GET /api/transaction/<id>`
- `POST /api/qa` with `{"question": "What happened to PAY109?"}`

## Tests

Run the full test suite with:

```bash
python -m pytest -v
```

For deterministic offline tests, leave `GEMINI_API_KEY` unset. The pipeline safely falls back to human review when Gemini is unavailable.

## Gemini configuration

Gemini is optional and configured only through environment variables:

- `GEMINI_API_KEY` - required for live Gemini requests; never commit or expose this value.
- `LLM_PROVIDER=gemini` - optional; selects the supported Gemini provider.
- `GEMINI_MODEL=gemini-3.6-flash` - optional model override.

The deterministic tiers and Settlement Q&A remain usable without an API key. The Q&A endpoint is configured for deterministic explanations by default.

## Deploy on Render

Create a Render Blueprint deployment from `render.yaml`:

- Runtime: Python
- Plan: Free
- Branch: `master`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Required environment variable: `GEMINI_API_KEY` (set as a Render secret if live Tier 3 Gemini calls are desired)
- Optional environment variables: `LLM_PROVIDER` and `GEMINI_MODEL`

Render supplies `PORT`; Gunicorn imports the single Flask application as `app:app`. The included CSV data is read from the repository at startup, and no database or background worker is required for this demo deployment.

## Scope and safety boundaries

LedgerLoop is a hackathon/demo reconciliation service, not a general-purpose accounting system. Matching is schema-driven, one-to-one, tiered, and read-only from the UI/API layer. Secrets are loaded from the process environment, and missing or unavailable Gemini access never causes the deterministic pipeline to invent a match.
