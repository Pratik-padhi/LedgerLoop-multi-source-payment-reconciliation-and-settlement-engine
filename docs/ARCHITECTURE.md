# LedgerLoop Architecture

LedgerLoop is organized around a deterministic reconciliation core, a thin web controller, and explicit dataset/tooling boundaries.

## Repository layout

```text
.
├── app.py                 # Flask entrypoint kept at root for Gunicorn/Render
├── core/                  # Domain logic and application services
│   ├── accounting.py      # Decimal settlement, tax, refund, and fee arithmetic
│   ├── config.py          # Environment-backed runtime settings
│   ├── match_exact.py     # Tier 1 deterministic matching
│   ├── match_fuzzy.py     # Tier 2 bounded tolerance/reference matching
│   ├── match_llm.py       # Tier 3 guarded adjudication and validation
│   ├── match_split.py     # Split, multi-payment, and partial settlement matching
│   ├── normalize.py       # Source CSV to canonical records
│   ├── qa_agent.py        # Read-only evidence-grounded Q&A
│   └── service.py         # Full pipeline orchestration
├── data/                  # Compact canonical demo profile
│   ├── baseline/          # Pre-Phase-1.1 historical fixture
│   └── *.csv              # Current inputs and evaluation-only ground truth
├── data_large/            # Expanded benchmark/deployment profile
├── docs/                  # Architecture, schema, phase notes, and reports
│   ├── archive/           # Historical session/project artifacts
│   └── reports/           # Generated inspection reports
├── scripts/               # Dataset generation, validation, and inspection tools
├── tests/                 # Unit, integration, and Flask contract tests
├── ui/                    # Static controller UI served by app.py
├── .python-version        # Supported local Python version
├── render.yaml            # Render deployment definition
└── requirements.txt       # Runtime and test dependencies
```

## Runtime flow

```text
source CSVs
    │
    ▼
core.normalize
    │ canonical records
    ▼
Tier 1 exact → Tier 2 bounded → Tier 3 guarded → Stage 3 split
    │
    ▼
core.service.ReconciliationRun
    │
    ├── app.py Flask JSON API
    ├── ui/ controller interface
    └── core.qa_agent read-only explanations
```

The matching stages own financial decisions. `app.py` serializes results and
routes requests; it should not contain matching rules. `core.service` is the
callable boundary for running the complete pipeline without depending on Flask.

## Dataset policy

- `data/` is the fast local default and the compact validation profile.
- `data_large/` is the expanded scenario and deployment profile.
- `ground_truth.csv` is evaluation-only and must never be read by matching code.
- Generated inspection output belongs in ignored subdirectories such as
  `data/normalized/`, `data/tier1/`, or `docs/reports/`.

## Change boundaries

When adding reconciliation behavior, prefer this ownership:

- New parsing or source fields: `core/normalize.py` and `docs/SCHEMA.md`.
- New arithmetic: `core/accounting.py` with Decimal-based tests.
- New deterministic evidence rule: the owning matcher and its focused tests.
- New pipeline stage: `core/service.py` plus a result contract test.
- New API/UI behavior: `app.py`, `ui/`, and `tests/test_ui_server.py`.
- New dataset scenario: the appropriate generator, dataset documentation, and
  validator coverage.
