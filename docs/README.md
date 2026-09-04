# LedgerLoop — Phase 1: Synthetic Dataset

This directory contains the synthetic input data, ground truth, and documentation
that will be used to test the LedgerLoop reconciliation engine in later phases.
**No reconciliation, matching, or LLM logic is implemented in this phase.**

## Files

| File | Purpose |
|---|---|
| `gateway.csv` | What the payment gateway recorded for each payment |
| `bank.csv` | What actually appeared as a settlement in the bank statement |
| `ledger.csv` | What the merchant recorded internally |
| `ground_truth.csv` | The expected reconciliation outcome for every logical transaction |
| `KNOWN_DISCREPANCIES.md` | Human-readable explanation of every deliberately injected discrepancy, with source-row evidence (includes a Phase 1.1 addendum) |
| `scripts/generate_synthetic.py` | Deterministic generator that produces the base Phase 1 dataset (SEED = 42) |
| `scripts/patch_phase1_1_tier3.py` | Additive, idempotent patch that appends the Phase 1.1 Tier 3 cases |
| `scripts/validate_dataset.py` | Validates the dataset's structure, completeness, and internal consistency (including Tier 3 coverage) |

## Column meanings

**gateway.csv**
- `source_row_id` — stable traceability ID (G001, G002, …)
- `payment_id` — the gateway's own primary identifier (e.g. `PAY001`). Refund rows use `PAYxxx-REFUND`.
- `payment_date` — date the payment was captured
- `amount` — amount captured (negative for refund rows)
- `status` — `CAPTURED` or `REFUNDED`
- `gateway_reference` — a secondary reference the gateway exposes (used by bank.csv's `bank_reference` in a possibly reformatted way)
- `customer_reference` — order-level reference
- `settlement_expected_date` — date the gateway expects the bank to settle

**bank.csv**
- `source_row_id` — stable traceability ID (B001, B002, …)
- `bank_transaction_id` — bank's own transaction ID
- `transaction_date` / `value_date` — dates as they appear on the bank statement
- `credit_amount` — amount actually credited
- `utr` — synthetic UTR-like reference (not a real bank reference format)
- `bank_reference` — the bank's record of the gateway's reference — may be truncated, reformatted, or missing/`UNKNOWN` for orphan cases
- `description` — free-text settlement description

**ledger.csv**
- `source_row_id` — stable traceability ID (L001, L002, …)
- `ledger_entry_id` — merchant's own entry ID
- `entry_date` — date recorded internally
- `payment_reference` — merchant's reference back to the gateway payment_id (may repeat for documented duplicates)
- `invoice_reference` — internal invoice ID
- `recorded_amount` — gross amount recorded (negative for refund entries)
- `tax_amount` — reserved for GST-type line items (unused in this dataset; always 0.00)
- `tds_amount` — TDS deducted, when applicable
- `entry_type` — `SALE` or `REFUND`

**ground_truth.csv**
One row per logical transaction (keyed by the gateway `payment_id`, e.g. `PAY071`), describing:
`expected_status` (`MATCHED` / `EXCEPTION`), `expected_category` (failure-mode taxonomy below),
`expected_matching_tier` (`TIER_1` / `TIER_2` / `N/A`), presence flags for each source,
expected amount/date differences, and a `discrepancy_id` linking to `KNOWN_DISCREPANCIES.md`
(blank for plain `NORMAL_EXACT` matches).

## Dataset size

**111 logical transactions** (106 from Phase 1 + 5 added in Phase 1.1) across 116 gateway
rows, 111 bank rows, and 117 ledger rows (row counts differ from transaction counts because
refund pairs add gateway/ledger rows, duplicates add extra ledger rows, orphans/missing-
counterpart cases omit rows by design, and one Phase 1.1 case includes an intentional
evidence-only decoy gateway row — see "Phase 1.1" below).

## Phase 1.1 — Tier 3 (LLM adjudication) cases

Phase 1 originally had strong Tier 1/Tier 2 coverage but no cases that genuinely require
Tier 3 LLM adjudication. Phase 1.1 is a **purely additive patch** (`patch_phase1_1_tier3.py`)
that appends 5 new logical transactions — `PAY107`–`PAY111` — without modifying, reordering,
or deleting any existing row. All Phase 1 data (`PAY001`–`PAY106`) is byte-identical before
and after the patch.

Two new ground-truth categories were introduced, both using `expected_matching_tier = TIER_3`:

- **LLM_AMBIGUOUS_MATCH** — resolvable, but only by combining multiple weak/partial signals
  together (reference fragments, free-text descriptions, split-settlement sums, presence/absence
  of counterpart rows). No single deterministic Tier 1/Tier 2 rule resolves these alone.
- **LLM_NEEDS_HUMAN** — genuinely unresolved. Evidence is either symmetric between two equally
  plausible candidates, or directly contradictory with no supporting field to explain the
  conflict. The correct behavior is for the LLM to decline to force a match.

| Transaction | Category | Status | Why Tier 3 |
|---|---|---|---|
| PAY107 | LLM_AMBIGUOUS_MATCH | MATCHED | Reference shared by two same-amount candidates; resolved only by combining bank description text + ledger presence/absence + amount |
| PAY108 | LLM_NEEDS_HUMAN | EXCEPTION | Two unlabeled bank credits, identical amount, identical date, no distinguishing evidence — a genuine coin flip |
| PAY109 | LLM_AMBIGUOUS_MATCH | MATCHED | Split settlement across two bank credits whose sum is close (not exact) to the gateway amount; resolved via description text + reference fragment + near-equal sum |
| PAY110 | LLM_NEEDS_HUMAN | EXCEPTION | Reference matches perfectly, but amount conflicts by ₹450 with no tax/refund field to explain it — contradictory evidence |
| PAY111 | LLM_AMBIGUOUS_MATCH | MATCHED | Bank's structured reference field is blank; link only exists via free-text description matching the ledger's invoice reference |

See `KNOWN_DISCREPANCIES.md` (Phase 1.1 addendum, appended at the end) for full source-row
evidence and reasoning behind each case.

**Note:** `gateway.csv` contains one additional row, `PAY107B`, which is a plausible decoy
candidate deliberately created as *evidence* for PAY107's ambiguity — it is not itself a
logical transaction requiring reconciliation and intentionally has no row in `ground_truth.csv`.
This is documented and explicitly checked for in `validate_dataset.py`.

## Failure modes injected

| Category | Count | % (of 111) | Tier |
|---|---|---|---|
| `NORMAL_EXACT` | 70 | 63.1% | TIER_1 |
| `SETTLEMENT_DELAY` | 8 | 7.2% | TIER_2 |
| `ROUNDING` | 7 | 6.3% | TIER_2 |
| `REFERENCE_FORMATTING` | 5 | 4.5% | TIER_2 |
| `TAX_LINE_MISMATCH` | 5 | 4.5% | TIER_2 |
| `LLM_AMBIGUOUS_MATCH` | 3 | 2.7% | TIER_3 |
| `PARTIAL_REFUND` | 4 | 3.6% | TIER_2 |
| `DUPLICATE_LEDGER_ENTRY` | 3 | 2.7% | TIER_2 (exception) |
| `LLM_NEEDS_HUMAN` | 2 | 1.8% | TIER_3 (exception) |
| `NO_BANK_COUNTERPART` | 2 | 1.8% | N/A (exception) |
| `UNMATCHED_GATEWAY_TRANSACTION` | 1 | 0.9% | N/A (exception) |
| `UNMATCHED_BANK_TRANSACTION` | 1 | 0.9% | N/A (exception) |

This matches the requested distribution (majority normal matches, every required
failure mode present at least once, orphan/no-counterpart cases kept rare and distinct).

## Ground truth categories (taxonomy)

- **NORMAL_EXACT** — all three sources agree exactly; Tier 1 deterministic match.
- **ROUNDING** — bank settled a few paise/rupees less than gateway/ledger; legitimate tolerance case, not a real mismatch.
- **SETTLEMENT_DELAY** — bank settlement date is 1–2 days after the payment/ledger date; legitimate lag.
- **REFERENCE_FORMATTING** — bank's reference is a truncated/reformatted variant of the gateway reference (5 different formatting styles used).
- **DUPLICATE_LEDGER_ENTRY** — the merchant ledger recorded the same sale twice; only one real gateway payment and bank settlement exist.
- **PARTIAL_REFUND** — gateway and ledger each carry an explicit linked `-REFUND` row; bank settles the net amount.
- **TAX_LINE_MISMATCH** — bank settles gross amount minus TDS (1% rate used); ledger's `tds_amount` field explains the gap exactly.
- **NO_BANK_COUNTERPART** — payment exists in gateway + ledger, but never appears in the bank statement. Must surface as unresolved, not be silently matched.
- **UNMATCHED_GATEWAY_TRANSACTION** — exists only in gateway.csv, no counterpart anywhere.
- **UNMATCHED_BANK_TRANSACTION** — exists only in bank.csv (an unidentified inward credit), no counterpart anywhere.

`UNMATCHED_GATEWAY_TRANSACTION` / `UNMATCHED_BANK_TRANSACTION` are kept distinct from
`NO_BANK_COUNTERPART`: the latter requires presence in **two** sources (gateway + ledger)
with only the bank missing, while true orphans exist in exactly **one** source.

## How ground truth works

`ground_truth.csv` is the answer key. Every logical transaction (by gateway `payment_id`,
or a synthetic ID for the bank-only orphan) has exactly one row stating what a correct
reconciliation engine should conclude — status, category, tier, per-source presence, and
expected amount/date deltas. `KNOWN_DISCREPANCIES.md` gives the human-readable narrative
and source-row evidence (`source_row_id`s) behind every non-trivial row, so any ground-truth
value can be traced back to the exact injected discrepancy and the exact rows that caused it.
Together these are sufficient to compute match accuracy, false-match rate, precision, recall,
and per-failure-type performance once a matching engine exists.

## How to regenerate

```bash
python3 generate_synthetic.py       # builds base Phase 1 dataset (PAY001-PAY106)
python3 patch_phase1_1_tier3.py     # additively appends Phase 1.1 Tier 3 cases (PAY107-PAY111)
```

Both steps use a fixed `SEED = 42` and are safe to re-run: the generator overwrites the base
files deterministically, and the patch script is idempotent (it checks for `PAY107` and no-ops
if the patch is already applied). Running both in sequence reproduces the current files
byte-for-byte (verified by `validate_dataset.py`).

## How to validate

```bash
python3 validate_dataset.py
```

Checks: required files exist; each CSV has its expected columns; ≥100 logical transactions;
all required failure-mode categories present; every gateway `payment_id` appears in
`ground_truth.csv`; every `discrepancy_id` referenced in ground truth is documented in
`KNOWN_DISCREPANCIES.md`; no accidental duplicate primary IDs outside the deliberate
`DUPLICATE_LEDGER_ENTRY` cases; all amounts are valid 2-decimal INR values; all dates are
valid calendar dates; and regeneration is deterministic.

Current status: **all checks pass, 0 errors, 0 warnings.**
