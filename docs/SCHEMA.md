# LedgerLoop — Phase 2: Canonical Schema & Normalization Layer

Phase 2 converts the three frozen Phase 1 source files into a common internal
representation (`core/normalize.py`) without making any matching/reconciliation
decision. This document describes the resulting canonical schema and how it
maps to each source's actual columns.

## Architectural boundary

**Normalization DOES:** parse, validate, standardize date/amount representation,
conservatively normalize reference formatting, and expose every source's data
in a common structure — without ever discarding the original values.

**Normalization DOES NOT:** compare records across sources, decide whether two
records represent the same payment, apply fuzzy/tolerance thresholds, resolve
duplicates, merge payment/refund pairs, determine settlement status or
exceptions, call an LLM, or answer questions. Those are Phase 3+ concerns.

`core/normalize.py`'s three entry points (`normalize_gateway()`,
`normalize_bank()`, `normalize_ledger()`, plus the convenience wrapper
`normalize_all()`) each operate on exactly one source file and never read or
reference another source's data.

## The canonical record (`CanonicalRecord`)

```python
CanonicalRecord(
    source: str,                              # "gateway" | "bank" | "ledger"
    source_row_id: str,                       # e.g. "G001", "B002", "L003"
    transaction_reference: Reference,          # original + normalized
    date: NormalizedDate,                      # original + normalized (YYYY-MM-DD)
    amount: NormalizedAmount,                  # original + normalized (2-decimal float)
    status: str | None,                        # source-native status, if any
    secondary_references: dict[str, Reference],# other identifiers, always present as keys
    extra_dates: dict[str, NormalizedDate],    # secondary dates (currently bank only)
    tax_fields: dict[str, NormalizedAmount],   # tax-related amounts (currently ledger only)
    raw_record: dict[str, str],                # the complete original row, verbatim
)
```

Three small value types back every field that needs to preserve both an
original and a standardized form:

- **`Reference(original, normalized)`** — an identifier/reference string.
  `original` is `None` (not `""`) when the source field itself was blank.
- **`NormalizedDate(original, normalized)`** — `normalized` is `YYYY-MM-DD`,
  or `None` if the value couldn't be parsed (only possible for secondary
  dates; a bad *primary* date is a hard error, not a soft `None`).
- **`NormalizedAmount(original, normalized)`** — `normalized` is a 2-decimal
  float. `"500"`, `"500.0"`, `"500.00"` all normalize to `500.00`; genuinely
  different amounts (`500.00` vs `499.99`) remain genuinely different — no
  tolerance is applied here.

## Field meanings

| Field | Meaning |
|---|---|
| `source` | Which of the three source systems this record came from. |
| `source_row_id` | Stable identifier of the original source row (from Phase 1's `source_row_id` column) — the traceability anchor. |
| `transaction_reference` | The single most useful transaction/payment reference available *from that source*. Never invented, never merged across sources, never collapsed between a payment and its `-REFUND` counterpart. |
| `date` | The primary business date for that source. |
| `amount` | The monetary amount that source represents (sign preserved — refunds are negative). |
| `status` | The source-native status concept, if one exists (gateway: `CAPTURED`/`REFUNDED`; ledger: `entry_type` used as the closest equivalent, `SALE`/`REFUND`; bank: always `None` — this dataset's bank rows carry no status field). |
| `secondary_references` | Other identifiers that may become matching evidence later (UTR, gateway_reference, customer_reference, invoice_reference, bank_reference, description). Every expected key is always present in the dict, with `Reference(None, None)` when the source field was blank — so callers can safely do `record.secondary_references["utr"]` without a `KeyError`. |
| `extra_dates` | Additional source-specific dates beyond the primary `date`. Currently only bank records populate this (`value_date`), since Section 7 of the Phase 2 spec explicitly requires both `transaction_date` and `value_date` to survive. |
| `tax_fields` | Tax-related numeric fields that must stay separate from `amount`. Currently only ledger records populate this (`tax_amount`, `tds_amount`), per Section 8/15 — normalization never nets these against `amount`. |
| `raw_record` | The complete original CSV row, as a `dict[str, str]`, exactly as read — untouched, unparsed, always available as a fallback. |

## Per-source mapping

### Gateway (`gateway.csv` → `normalize_gateway()`)

| Canonical field | Source column |
|---|---|
| `transaction_reference` | `payment_id` |
| `date` | `payment_date` |
| `amount` | `amount` |
| `status` | `status` |
| `secondary_references.gateway_reference` | `gateway_reference` |
| `secondary_references.customer_reference` | `customer_reference` |
| `extra_dates.settlement_expected_date` | `settlement_expected_date` |

`gateway_reference` is **never** treated as equivalent to a bank UTR, and no
UTR is ever fabricated for a gateway record — the gateway simply has no UTR
concept, so no `utr` key appears in a gateway record's `secondary_references`.

### Bank (`bank.csv` → `normalize_bank()`)

| Canonical field | Source column |
|---|---|
| `transaction_reference` | `bank_transaction_id` |
| `date` | `transaction_date` |
| `extra_dates.value_date` | `value_date` |
| `amount` | `credit_amount` |
| `status` | *(none — always `None`)* |
| `secondary_references.utr` | `utr` |
| `secondary_references.bank_reference` | `bank_reference` |
| `secondary_references.description` | `description` (preserved verbatim, whitespace-trimmed only — **not** uppercased/hyphen-normalized like structured references, since it's free text) |

`transaction_reference` is deliberately the bank's **own** transaction id, not
the gateway's `payment_id` and not the UTR — the bank does not natively know
the gateway's identifier scheme. The UTR and (possibly truncated/reformatted)
gateway reference copy live in `secondary_references`, available for later
matching but never assumed equal to anything.

### Ledger (`ledger.csv` → `normalize_ledger()`)

| Canonical field | Source column |
|---|---|
| `transaction_reference` | `payment_reference` |
| `date` | `entry_date` |
| `amount` | `recorded_amount` (gross; sign preserved for refund entries) |
| `status` | `entry_type` (`SALE` / `REFUND`) |
| `secondary_references.invoice_reference` | `invoice_reference` |
| `tax_fields.tax_amount` | `tax_amount` |
| `tax_fields.tds_amount` | `tds_amount` |

`tax_amount` and `tds_amount` are always kept as independent fields —
normalization never subtracts them from `amount`/`recorded_amount`. Whether a
TDS deduction "explains" a settlement gap is a later reconciliation decision
(see Phase 1's `TAX_LINE_MISMATCH` ground-truth category).

## Reference normalization rules (conservative, documented)

`normalize_reference()` performs only:

1. Blank/whitespace-only → `Reference(None, None)` (never a fabricated placeholder).
2. Trim leading/trailing whitespace.
3. Uppercase (references in this dataset are case-insensitively meaningful:
   `"gw090"` and `"GW090"` are the same string typed differently).
4. Strip a single hyphen **only** when it sits between a leading alphabetic
   prefix and a following digit — i.e. `"PAY-123456"` → `"PAY123456"`. This
   does **not** touch hyphens elsewhere (`"PAY097-REFUND"` stays exactly
   `"PAY097-REFUND"`, since that hyphen is a meaningful suffix separator, not
   a prefix/number separator).

It explicitly does **not**: truncate to force a match (`"PAY123456"` vs
`"PAY123"` remain different strings), infer a missing prefix, or resolve
`"UNKNOWN"` into anything. Those are Tier 2/3 concerns.

## Error handling

- **Hard errors** (`NormalizationError`) — raised for genuinely invalid input:
  missing required column, invalid amount, invalid primary date, unreadable
  CSV, duplicate `source_row_id`, or a missing primary identifier
  (`payment_id` for gateway, `bank_transaction_id` for bank). Every error
  carries `source`, `source_row_id` (if known), `field`, `problem`, and
  `suggested_correction`.
- **Warnings** (`ValidationWarning`) — raised for recoverable issues that
  don't block normalization: a missing secondary reference (e.g. blank
  `bank_reference` or `invoice_reference`), a missing `payment_reference` on
  a ledger row (realistic per Phase 1 Section 7), or an unparsable secondary
  date.
- `normalize_gateway()` / `normalize_bank()` / `normalize_ledger()` all accept
  `strict: bool = False`. In non-strict mode (the default), a bad row is
  skipped, its error recorded in `NormalizationResult.errors`, and the rest
  of the file is still processed — one bad row never blocks visibility into
  the other 100+ good ones. `strict=True` raises immediately on the first
  error.

## What Phase 2 explicitly proves (see `tests/test_normalize.py`)

1. **Original source rows remain traceable** — every `CanonicalRecord` carries
   its exact `source_row_id` and a verbatim copy of `raw_record`.
2. **Duplicate rows remain present** — Phase 1's `DUPLICATE_LEDGER_ENTRY`
   cases (e.g. `PAY091`, two separate ledger rows) each produce their own
   `CanonicalRecord`; nothing is deduplicated.
3. **Refund rows remain present** — `PAY095` and `PAY095-REFUND` normalize to
   two distinct records with distinct `transaction_reference` values and
   distinct (non-netted) amounts.
4. **Tax/TDS information remains present** — `tax_fields.tds_amount` is
   always independently inspectable; `amount` is never pre-reduced by it.
5. **Bank `transaction_date` and `value_date` remain available** — every bank
   record carries both, even when they're equal (settlement-timing-drift
   cases have them differ; normal cases have them match — both are always
   present in `extra_dates`).
6. **Missing identifiers remain missing** — e.g. the Phase 1.1 `PAY108`/`PAY111`
   cases (blank `bank_reference`) normalize to `Reference(None, None)`, never
   a fabricated value.
7. **No matching decision has been made** — canonical records carry no
   `matched_to`, `match_status`, `match_score`, `tier`, or similar field;
   `normalize_all()` never compares one source's records against another's.

## Files

| File | Purpose |
|---|---|
| `core/normalize.py` | The normalization module (this schema's implementation). |
| `tests/test_normalize.py` | 31 tests: 15 required cases (Section 18) + integration tests against the real Phase 1 CSVs + a few extra boundary checks. |
| `scripts/export_normalized.py` | Dev/debug utility — dumps `normalize_all()`'s output to `data/normalized/*.json` for manual inspection. Not a user-facing deliverable. |
| `data/normalized/*.json` | Generated output of the above script (gitignore-able; regenerate anytime with `python3 scripts/export_normalized.py`). |

## How to run

```bash
# Run the test suite
python3 -m unittest tests.test_normalize -v

# Generate inspectable JSON output from the real Phase 1 dataset
python3 scripts/export_normalized.py
```
