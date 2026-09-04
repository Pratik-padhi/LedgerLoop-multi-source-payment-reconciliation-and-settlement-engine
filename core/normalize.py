"""
LedgerLoop — Phase 2: Data Ingestion & Schema Normalization
===============================================================

Converts each Phase 1 source CSV (gateway.csv, bank.csv, ledger.csv) into a
common internal "canonical record" structure, WITHOUT ever discarding the
original source data and WITHOUT making any matching/reconciliation decision.

STRICT ARCHITECTURAL BOUNDARY
------------------------------
This module DOES:
    - parse each source CSV
    - validate required columns, amount format, and date format
    - standardize dates and amounts into a consistent machine-readable form
    - conservatively normalize references (whitespace/case/separator only)
    - expose all of the above in a common CanonicalRecord structure
    - preserve every original value (nothing is ever discarded)

This module DOES NOT:
    - compare records across sources
    - decide whether two records represent the same payment
    - apply fuzzy/tolerance matching of any kind
    - resolve or remove duplicate rows
    - merge payment + refund pairs
    - determine settlement status or exceptions
    - call an LLM
    - answer questions

All of the above belong to later phases (Tier 1/2/3 matching, exception
handling, Q&A, API, dashboard).

CANONICAL SCHEMA
-----------------
Every canonical record is a `CanonicalRecord` (see below) with these fields:

    source                  "gateway" | "bank" | "ledger"
    source_row_id            Stable original row identifier (e.g. "G001").
    transaction_reference     The most useful transaction/payment reference
                              available from that source (see per-source
                              mapping below). Distinct records are NEVER
                              collapsed onto the same transaction_reference
                              by this layer — e.g. a payment and its
                              "-REFUND" counterpart keep their own distinct
                              reference strings.
    date                     Primary business date for that source, as a
                              NormalizedDate (see below).
    amount                   The monetary amount that source represents, as
                              a NormalizedAmount (see below).
    status                   Source-reported status string, if the source
                              has one (gateway: CAPTURED/REFUNDED; ledger:
                              entry_type SALE/REFUND used as a stand-in;
                              bank: None, banks in this dataset carry no
                              status concept).
    secondary_references     Dict of other potentially useful identifiers,
                              each stored as a Reference (original +
                              normalized), with unavailable ones set to None
                              rather than omitted, so callers can always
                              check `secondary_references.get("utr")` safely.
    extra_dates              Dict of any additional source-specific dates
                              beyond the single primary `date` (currently
                              only used by bank: transaction_date +
                              value_date, both preserved as NormalizedDate).
    tax_fields               Dict of tax-related numeric fields that must
                              stay separate from `amount` (currently only
                              used by ledger: tax_amount, tds_amount).
    raw_record                The complete original row, as a dict, verbatim
                              (values as strings, exactly as read from CSV).

Per-source mapping of `transaction_reference` and `date`:

    gateway:  transaction_reference = payment_id
              date                  = payment_date
    bank:     transaction_reference = bank_transaction_id
              date                  = transaction_date (value_date kept in
                                       extra_dates)
    ledger:   transaction_reference = payment_reference
              date                  = entry_date

Note the deliberate asymmetry: the bank's `transaction_reference` is its OWN
transaction id (`bank_transaction_id`), not the gateway's payment_id or the
UTR — the bank does not natively know the gateway's identifier scheme. The
UTR and bank_reference (bank's copy of the gateway reference, possibly
truncated/reformatted) live in `secondary_references`, exactly as the Phase 1
README documents. This is intentional and matches Section 3/6/7 of the Phase
2 spec ("Do NOT treat gateway_reference as automatically equivalent to a bank
UTR", "Do NOT assume that a bank UTR is identical to the gateway payment_id").
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional


# ===========================================================================
# Exceptions
# ===========================================================================

class NormalizationError(Exception):
    """
    Raised for genuinely invalid input that cannot be safely normalized.

    Carries structured context so callers (and validation reports) can show:
    source, source_row_id (if known), field, problem, suggested correction.
    """

    def __init__(self, source: str, field_name: str, problem: str,
                 source_row_id: Optional[str] = None,
                 suggested_correction: Optional[str] = None,
                 raw_value: Optional[str] = None):
        self.source = source
        self.source_row_id = source_row_id
        self.field = field_name
        self.problem = problem
        self.suggested_correction = suggested_correction
        self.raw_value = raw_value
        msg = (f"[{source}"
               f"{'/' + source_row_id if source_row_id else ''}] "
               f"field '{field_name}': {problem}")
        if raw_value is not None:
            msg += f" (raw value: {raw_value!r})"
        if suggested_correction:
            msg += f" — suggested: {suggested_correction}"
        super().__init__(msg)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "source_row_id": self.source_row_id,
            "field": self.field,
            "problem": self.problem,
            "suggested_correction": self.suggested_correction,
            "raw_value": self.raw_value,
        }


@dataclass
class ValidationWarning:
    """
    A recoverable issue: normalization proceeded, but something about the
    record is worth flagging (e.g. a secondary reference is blank/missing).
    This is NOT a matching decision — it is purely about data completeness.
    """
    source: str
    source_row_id: Optional[str]
    field: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# Canonical value types
# ===========================================================================

@dataclass
class NormalizedDate:
    """
    A date preserved in both its original and normalized form.
    normalized is None if the original value could not be parsed — in that
    case a NormalizationError is raised by the caller, but for extra_dates
    (secondary dates) an unparsable value is downgraded to a warning and
    normalized stays None, since a broken secondary date shouldn't block
    normalization of an otherwise-valid record.
    """
    original: str
    normalized: Optional[str]  # YYYY-MM-DD, or None if unparsable

    def to_dict(self) -> dict:
        return {"original": self.original, "normalized": self.normalized}


@dataclass
class NormalizedAmount:
    """
    A monetary amount preserved in both its original string form and a
    normalized numeric (float, 2-decimal-precision) form. Normalization
    only standardizes representation (e.g. "500", "500.0", "500.00" all
    become 500.00) — it never rounds away a genuine difference such as
    500.00 vs 499.99, and it never decides whether two amounts "match".
    """
    original: str
    normalized: Optional[float]  # rounded to 2 decimals, or None if invalid

    def to_dict(self) -> dict:
        return {"original": self.original, "normalized": self.normalized}


@dataclass
class Reference:
    """
    A reference/identifier preserved in both original and conservatively
    normalized form. See `normalize_reference()` for exactly what
    normalization is and is not allowed to do. `original` is None (not "")
    when the source field itself was blank/absent, so callers can
    distinguish "field exists and is blank" from "field omitted" — in this
    dataset both surface as blank CSV cells, so we treat blank-string and
    absent identically as "not provided" (original=None, normalized=None).
    """
    original: Optional[str]
    normalized: Optional[str]

    def to_dict(self) -> dict:
        return {"original": self.original, "normalized": self.normalized}


# ===========================================================================
# Canonical record
# ===========================================================================

@dataclass
class CanonicalRecord:
    source: str                                  # "gateway" | "bank" | "ledger"
    source_row_id: str
    transaction_reference: Reference
    date: NormalizedDate
    amount: NormalizedAmount
    status: Optional[str]
    secondary_references: dict[str, Reference]
    extra_dates: dict[str, NormalizedDate] = field(default_factory=dict)
    tax_fields: dict[str, NormalizedAmount] = field(default_factory=dict)
    raw_record: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "source_row_id": self.source_row_id,
            "transaction_reference": self.transaction_reference.to_dict(),
            "date": self.date.to_dict(),
            "amount": self.amount.to_dict(),
            "status": self.status,
            "secondary_references": {
                k: v.to_dict() for k, v in self.secondary_references.items()
            },
            "extra_dates": {k: v.to_dict() for k, v in self.extra_dates.items()},
            "tax_fields": {k: v.to_dict() for k, v in self.tax_fields.items()},
            "raw_record": self.raw_record,
        }


# ===========================================================================
# Low-level normalization primitives
# ===========================================================================

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AMOUNT_RE = re.compile(r"^-?\d+(\.\d+)?$")


def normalize_date(raw: str) -> NormalizedDate:
    """
    Standardize a date string into YYYY-MM-DD.

    Phase 1 dates are already YYYY-MM-DD, but this function is written to
    tolerate that representation robustly (and to fail clearly, not
    silently, on anything it cannot parse) rather than assuming the input
    is always pre-formatted.

    Raises NormalizationError if `raw` is empty or not a real calendar date.
    """
    if raw is None or raw.strip() == "":
        raise NormalizationError(
            source="", field_name="date", problem="date value is missing/blank",
            raw_value=raw,
        )
    raw_stripped = raw.strip()
    try:
        parsed = datetime.strptime(raw_stripped, "%Y-%m-%d")
    except ValueError:
        raise NormalizationError(
            source="", field_name="date",
            problem="value is not a valid YYYY-MM-DD calendar date",
            raw_value=raw,
            suggested_correction="provide date as YYYY-MM-DD",
        )
    return NormalizedDate(original=raw, normalized=parsed.strftime("%Y-%m-%d"))


def normalize_secondary_date(raw: str) -> NormalizedDate:
    """
    Like normalize_date, but for secondary/extra dates (e.g. bank
    value_date): an unparsable value here should not block normalization of
    the whole record. Returns NormalizedDate(original=raw, normalized=None)
    on parse failure instead of raising; the caller is responsible for
    surfacing a ValidationWarning.
    """
    if raw is None or raw.strip() == "":
        return NormalizedDate(original=raw or "", normalized=None)
    raw_stripped = raw.strip()
    try:
        parsed = datetime.strptime(raw_stripped, "%Y-%m-%d")
    except ValueError:
        return NormalizedDate(original=raw, normalized=None)
    return NormalizedDate(original=raw, normalized=parsed.strftime("%Y-%m-%d"))


def normalize_amount(raw: str) -> NormalizedAmount:
    """
    Standardize a monetary string into a 2-decimal-precision float.

    "500", "500.0", "500.00" all normalize to 500.00 — pure representation
    standardization. Genuinely different amounts (500.00 vs 499.99) remain
    genuinely different; this function never applies a tolerance threshold.

    Raises NormalizationError if `raw` is empty or not a valid number.
    """
    if raw is None or raw.strip() == "":
        raise NormalizationError(
            source="", field_name="amount", problem="amount value is missing/blank",
            raw_value=raw,
        )
    raw_stripped = raw.strip()
    if not _AMOUNT_RE.match(raw_stripped):
        raise NormalizationError(
            source="", field_name="amount",
            problem="value is not a valid numeric amount",
            raw_value=raw,
            suggested_correction="provide amount as a plain decimal number, e.g. 500.00",
        )
    return NormalizedAmount(original=raw, normalized=round(float(raw_stripped), 2))


def normalize_reference(raw: Optional[str]) -> Reference:
    """
    CONSERVATIVE reference normalization only. This function is explicitly
    NOT allowed to perform fuzzy matching, truncation-awareness, or any
    judgment about whether two references "mean the same thing" — that is
    Tier 2's job, not normalization's.

    What this function DOES do (all documented, all reversible-in-spirit —
    the original is always kept alongside):
        1. Treat blank/whitespace-only/absent values as "not provided"
           (original=None, normalized=None) rather than inventing a
           placeholder.
        2. Trim leading/trailing whitespace.
        3. Uppercase the value (references in this dataset are
           case-insensitively meaningful — e.g. "gw090" and "GW090" are the
           same literal string typed differently, not two different
           identifiers).
        4. Strip a single internal hyphen when it appears immediately after
           a leading alphabetic prefix and before a numeric suffix — i.e.
           "PAY-123456" -> "PAY123456", "GW-001" -> "GW001". This is a pure
           formatting normalization of separator characters, not a
           semantic judgment: it does not touch hyphens elsewhere (so
           "PAY097-REFUND" and "GW094-R" are left untouched, since their
           hyphen is a meaningful suffix separator, not a prefix/number
           separator).

    What this function does NOT do:
        - It does NOT strip characters to make "PAY123456" match
          "PAY123" (truncation is a Tier 2 concern).
        - It does NOT infer a missing prefix (e.g. it will NOT turn the raw
          bank_reference "089" into "PAY089" or "GW089" — that inference
          belongs to fuzzy/Tier 2 matching, and inventing it here would
          violate the "do not decide whether two references are the same"
          boundary).
        - It does NOT resolve "UNKNOWN" into anything meaningful — it is
          normalized like any other string (trimmed + uppercased) and
          remains exactly "UNKNOWN".
    """
    if raw is None or raw.strip() == "":
        return Reference(original=None, normalized=None)

    original = raw
    value = raw.strip().upper()

    # Strip a hyphen only when it sits between a leading alphabetic prefix
    # and a following digit — i.e. it is acting as a prefix/number
    # separator, not a meaningful suffix marker.
    match = re.match(r"^([A-Z]+)-(\d.*)$", value)
    if match:
        value = match.group(1) + match.group(2)

    return Reference(original=original, normalized=value)


# ===========================================================================
# CSV loading helper
# ===========================================================================

def _load_csv_rows(path: str) -> list[dict[str, str]]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        raise NormalizationError(
            source="", field_name="<file>", problem=f"file not found: {path}",
        )
    except OSError as e:
        raise NormalizationError(
            source="", field_name="<file>", problem=f"unable to read file {path}: {e}",
        )
    return rows


def _require_columns(rows: list[dict[str, str]], required: list[str],
                      source: str, path: str) -> None:
    if not rows:
        return  # an empty file has no rows to validate column presence on;
        # downstream callers will simply produce zero records.
    actual = set(rows[0].keys())
    missing = [c for c in required if c not in actual]
    if missing:
        raise NormalizationError(
            source=source, field_name=", ".join(missing),
            problem=f"required column(s) missing from {path}: {missing}",
            suggested_correction=f"ensure {path} has header columns: {required}",
        )


def _check_duplicate_source_row_ids(rows: list[dict[str, str]], source: str) -> None:
    seen = {}
    for r in rows:
        rid = r.get("source_row_id")
        if rid in seen:
            raise NormalizationError(
                source=source, source_row_id=rid, field_name="source_row_id",
                problem=f"duplicate source_row_id '{rid}' found in {source} CSV "
                        f"(source_row_id must be unique per source row)",
                suggested_correction="ensure every row has a unique source_row_id",
            )
        seen[rid] = True


# ===========================================================================
# Per-source normalization
# ===========================================================================

GATEWAY_REQUIRED_COLUMNS = ["source_row_id", "payment_id", "payment_date", "amount",
                             "status", "gateway_reference", "customer_reference",
                             "settlement_expected_date"]
BANK_REQUIRED_COLUMNS = ["source_row_id", "bank_transaction_id", "transaction_date",
                          "value_date", "credit_amount", "utr", "bank_reference",
                          "description"]
LEDGER_REQUIRED_COLUMNS = ["source_row_id", "ledger_entry_id", "entry_date",
                            "payment_reference", "invoice_reference", "recorded_amount",
                            "tax_amount", "tds_amount", "entry_type"]


def normalize_gateway_row(row: dict[str, str],
                           warnings: list[ValidationWarning]) -> CanonicalRecord:
    """
    Normalize a single gateway.csv row into a CanonicalRecord.

    Mapping (see module docstring for full rationale):
        transaction_reference = payment_id      (the gateway's own primary id;
                                                   distinct for -REFUND rows —
                                                   never merged with the
                                                   original payment here)
        date                   = payment_date
        amount                 = amount          (negative for refund rows —
                                                   preserved as-is, sign intact)
        status                 = status          (CAPTURED / REFUNDED)
        secondary_references   = gateway_reference, customer_reference,
                                  settlement_expected_date (as a reference,
                                  since it's an expectation, not the primary
                                  business date of this record)
    """
    source_row_id = row.get("source_row_id")

    tx_ref = normalize_reference(row.get("payment_id"))
    if tx_ref.original is None:
        raise NormalizationError(
            source="gateway", source_row_id=source_row_id,
            field_name="payment_id", problem="payment_id is missing/blank — "
            "this is the gateway's primary transaction reference and cannot be absent",
        )

    date = normalize_date(row.get("payment_date", ""))
    # attach source context to any date/amount parse error raised above
    # (they're raised with source="" internally; re-raise with full context)
    amount = normalize_amount(row.get("amount", ""))

    status = (row.get("status") or "").strip() or None

    gateway_ref = normalize_reference(row.get("gateway_reference"))
    customer_ref = normalize_reference(row.get("customer_reference"))
    settlement_expected = normalize_secondary_date(row.get("settlement_expected_date", ""))
    if row.get("settlement_expected_date") and settlement_expected.normalized is None:
        warnings.append(ValidationWarning(
            source="gateway", source_row_id=source_row_id,
            field="settlement_expected_date",
            message=f"could not parse settlement_expected_date "
                    f"({row.get('settlement_expected_date')!r}); kept as unparsed original",
        ))

    if gateway_ref.original is None:
        warnings.append(ValidationWarning(
            source="gateway", source_row_id=source_row_id, field="gateway_reference",
            message="gateway_reference is missing/blank",
        ))

    return CanonicalRecord(
        source="gateway",
        source_row_id=source_row_id,
        transaction_reference=tx_ref,
        date=date,
        amount=amount,
        status=status,
        secondary_references={
            "gateway_reference": gateway_ref,
            "customer_reference": customer_ref,
        },
        extra_dates={
            "settlement_expected_date": settlement_expected,
        },
        tax_fields={},
        raw_record=dict(row),
    )


def normalize_bank_row(row: dict[str, str],
                        warnings: list[ValidationWarning]) -> CanonicalRecord:
    """
    Normalize a single bank.csv row into a CanonicalRecord.

    Mapping:
        transaction_reference = bank_transaction_id (the BANK's own id — this
                                  is deliberately NOT the gateway payment_id
                                  and NOT the UTR; the bank does not natively
                                  know the gateway's identifier scheme)
        date                   = transaction_date (primary canonical date;
                                  value_date is preserved separately in
                                  extra_dates, never discarded)
        amount                 = credit_amount
        status                 = None (this dataset's bank rows carry no
                                  status field/concept)
        secondary_references   = utr, bank_reference, description (description
                                  is free text, not a structured identifier,
                                  but is preserved verbatim as a Reference so
                                  later Tier 3 text-matching can use it — see
                                  KNOWN_DISCREPANCIES.md PAY111/PAY109 cases)
    """
    source_row_id = row.get("source_row_id")

    tx_ref = normalize_reference(row.get("bank_transaction_id"))
    if tx_ref.original is None:
        raise NormalizationError(
            source="bank", source_row_id=source_row_id,
            field_name="bank_transaction_id",
            problem="bank_transaction_id is missing/blank — this is the bank's "
                    "own primary transaction reference and cannot be absent",
        )

    date = normalize_date(row.get("transaction_date", ""))
    value_date = normalize_secondary_date(row.get("value_date", ""))
    if row.get("value_date") and value_date.normalized is None:
        warnings.append(ValidationWarning(
            source="bank", source_row_id=source_row_id, field="value_date",
            message=f"could not parse value_date ({row.get('value_date')!r}); "
                    f"kept as unparsed original",
        ))

    amount = normalize_amount(row.get("credit_amount", ""))

    utr = normalize_reference(row.get("utr"))
    bank_ref = normalize_reference(row.get("bank_reference"))
    # description is free text, not a structured identifier: normalize_reference's
    # uppercasing/hyphen-stripping is NOT appropriate for prose. Store it as a
    # Reference with only whitespace-trimming (no case change, no hyphen logic)
    # so its original phrasing is preserved for later free-text evidence use.
    raw_description = row.get("description")
    description = Reference(
        original=raw_description if raw_description and raw_description.strip() else None,
        normalized=raw_description.strip() if raw_description and raw_description.strip() else None,
    )

    if bank_ref.original is None:
        warnings.append(ValidationWarning(
            source="bank", source_row_id=source_row_id, field="bank_reference",
            message="bank_reference is missing/blank (this occurs for some genuine "
                    "orphan/unidentified-credit cases in the Phase 1 dataset)",
        ))

    return CanonicalRecord(
        source="bank",
        source_row_id=source_row_id,
        transaction_reference=tx_ref,
        date=date,
        amount=amount,
        status=None,
        secondary_references={
            "utr": utr,
            "bank_reference": bank_ref,
            "description": description,
        },
        extra_dates={
            "value_date": value_date,
        },
        tax_fields={},
        raw_record=dict(row),
    )


def normalize_ledger_row(row: dict[str, str],
                          warnings: list[ValidationWarning]) -> CanonicalRecord:
    """
    Normalize a single ledger.csv row into a CanonicalRecord.

    Mapping:
        transaction_reference = payment_reference (merchant's reference back
                                  to the gateway payment_id; -REFUND rows keep
                                  their own distinct reference string, never
                                  merged with the original payment; duplicate
                                  ledger rows for the same payment_reference —
                                  the deliberate DUPLICATE_LEDGER_ENTRY cases —
                                  each produce their own separate
                                  CanonicalRecord, keyed by their own distinct
                                  source_row_id)
        date                   = entry_date
        amount                 = recorded_amount (gross amount; negative for
                                  refund entries, preserved as-is)
        status                 = entry_type (SALE / REFUND — used as the
                                  closest ledger equivalent of "status")
        secondary_references   = invoice_reference
        tax_fields              = tax_amount, tds_amount — kept STRICTLY
                                  separate from `amount`/recorded_amount, per
                                  spec Section 8/15. Never combined, never
                                  used to adjust `amount`.
    """
    source_row_id = row.get("source_row_id")

    tx_ref = normalize_reference(row.get("payment_reference"))
    if tx_ref.original is None:
        # A ledger row without any payment_reference is realistic (spec
        # Section 7: "Some payment references may be missing or truncated"),
        # so this is a warning, not a hard failure — unlike gateway/bank
        # primary ids, which this dataset never actually omits.
        warnings.append(ValidationWarning(
            source="ledger", source_row_id=source_row_id, field="payment_reference",
            message="payment_reference is missing/blank",
        ))

    date = normalize_date(row.get("entry_date", ""))
    amount = normalize_amount(row.get("recorded_amount", ""))
    tax_amount = normalize_amount(row.get("tax_amount", "0.00"))
    tds_amount = normalize_amount(row.get("tds_amount", "0.00"))

    status = (row.get("entry_type") or "").strip() or None

    invoice_ref = normalize_reference(row.get("invoice_reference"))
    if invoice_ref.original is None:
        warnings.append(ValidationWarning(
            source="ledger", source_row_id=source_row_id, field="invoice_reference",
            message="invoice_reference is missing/blank",
        ))

    return CanonicalRecord(
        source="ledger",
        source_row_id=source_row_id,
        transaction_reference=tx_ref,
        date=date,
        amount=amount,
        status=status,
        secondary_references={
            "invoice_reference": invoice_ref,
        },
        extra_dates={},
        tax_fields={
            "tax_amount": tax_amount,
            "tds_amount": tds_amount,
        },
        raw_record=dict(row),
    )


# ===========================================================================
# Public API: normalize_gateway / normalize_bank / normalize_ledger
# ===========================================================================

@dataclass
class NormalizationResult:
    """
    Result of normalizing an entire source file: the successfully normalized
    records, any recoverable warnings, and any hard errors for rows that
    could NOT be normalized (those rows are excluded from `records` but their
    row identity + reason are preserved in `errors` for reporting).
    """
    source: str
    records: list[CanonicalRecord]
    warnings: list[ValidationWarning]
    errors: list[NormalizationError]

    def summary(self) -> dict:
        return {
            "source": self.source,
            "records_normalized": len(self.records),
            "warnings": len(self.warnings),
            "errors": len(self.errors),
        }


def _row_context(err: NormalizationError, source: str, source_row_id: Optional[str]
                  ) -> NormalizationError:
    """Re-raise a low-level (source="") error with full source/row context."""
    err.source = source
    if err.source_row_id is None:
        err.source_row_id = source_row_id
    return err


def normalize_gateway(path: str = "data/gateway.csv",
                       strict: bool = False) -> NormalizationResult:
    """
    Normalize the entire gateway.csv into canonical records.

    strict=True: raise on the first NormalizationError encountered.
    strict=False (default): skip the offending row, collect the error, and
        continue normalizing the rest of the file — this matches Section 17
        ("For recoverable issues, provide a clear warning... For invalid
        records, provide source/source_row_id/field/problem"), i.e. one bad
        row should not prevent inspection of the other 100+ good rows.
    """
    return _normalize_source(
        path=path, source="gateway", required_columns=GATEWAY_REQUIRED_COLUMNS,
        row_fn=normalize_gateway_row, strict=strict,
    )


def normalize_bank(path: str = "data/bank.csv",
                    strict: bool = False) -> NormalizationResult:
    """Normalize the entire bank.csv into canonical records. See normalize_gateway()."""
    return _normalize_source(
        path=path, source="bank", required_columns=BANK_REQUIRED_COLUMNS,
        row_fn=normalize_bank_row, strict=strict,
    )


def normalize_ledger(path: str = "data/ledger.csv",
                      strict: bool = False) -> NormalizationResult:
    """Normalize the entire ledger.csv into canonical records. See normalize_gateway()."""
    return _normalize_source(
        path=path, source="ledger", required_columns=LEDGER_REQUIRED_COLUMNS,
        row_fn=normalize_ledger_row, strict=strict,
    )


def _normalize_source(path: str, source: str, required_columns: list[str],
                       row_fn, strict: bool) -> NormalizationResult:
    rows = _load_csv_rows(path)
    _require_columns(rows, required_columns, source, path)
    _check_duplicate_source_row_ids(rows, source)

    records: list[CanonicalRecord] = []
    warnings: list[ValidationWarning] = []
    errors: list[NormalizationError] = []

    for row in rows:
        source_row_id = row.get("source_row_id")
        try:
            record = row_fn(row, warnings)
            records.append(record)
        except NormalizationError as e:
            e = _row_context(e, source, source_row_id)
            if strict:
                raise e
            errors.append(e)

    return NormalizationResult(source=source, records=records, warnings=warnings, errors=errors)


# ===========================================================================
# Convenience: normalize all three sources at once
# ===========================================================================

@dataclass
class AllSourcesNormalizationResult:
    gateway: NormalizationResult
    bank: NormalizationResult
    ledger: NormalizationResult

    def summary(self) -> dict:
        return {
            "gateway": self.gateway.summary(),
            "bank": self.bank.summary(),
            "ledger": self.ledger.summary(),
            "total_records_normalized": (
                len(self.gateway.records) + len(self.bank.records) + len(self.ledger.records)
            ),
            "total_warnings": (
                len(self.gateway.warnings) + len(self.bank.warnings) + len(self.ledger.warnings)
            ),
            "total_errors": (
                len(self.gateway.errors) + len(self.bank.errors) + len(self.ledger.errors)
            ),
        }


def normalize_all(data_dir: str = "data", strict: bool = False) -> AllSourcesNormalizationResult:
    """
    Convenience entry point: normalize gateway.csv, bank.csv, and ledger.csv
    from `data_dir` in one call. Does NOT compare or match records across
    sources — it simply runs the three per-source normalizers and returns
    their independent results.
    """
    return AllSourcesNormalizationResult(
        gateway=normalize_gateway(f"{data_dir}/gateway.csv", strict=strict),
        bank=normalize_bank(f"{data_dir}/bank.csv", strict=strict),
        ledger=normalize_ledger(f"{data_dir}/ledger.csv", strict=strict),
    )
