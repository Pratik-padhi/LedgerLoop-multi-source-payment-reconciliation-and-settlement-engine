"""
LedgerLoop — Accounting-Aware Settlement Calculation Layer
=============================================================

A reusable, deterministic settlement/accounting representation. Its purpose is
to separate *accounting arithmetic* from *matching*. Python computes the
money here; Gemini never does. Every accounting claim the engine makes carries
traceable evidence and is independently re-derived from the raw/gross amount.

STRICT ARCHITECTURAL BOUNDARY
-----------------------------
This module:
    - represents GST decomposition, TDS, MDR/payment fees, and refunds
    - computes expected net settlement from a gross amount
    - classifies remaining variance as explained vs unexplained
    - attaches evidence (source row ids + field names + relationship)
    - validates every amount (numeric, finite, signed, no double-counting)

This module DOES NOT:
    - match records across sources (that is Tier 1/2/3)
    - decide whether a payment is duplicated/fuzzy/ambiguous
    - consult ground_truth.csv
    - call an LLM or trust an LLM recommendation
    - mutate any CanonicalRecord

It is deliberately dumb-and-safe: it answers the question "given a gross
amount and these known adjustments, what should the bank receive, and does
the actual bank amount match?" It is reusable by the reconciliation tiers, the
API, the Q&A layer, and the frontend.

GST MODEL (IMPORTANT — DOUBLE-COUNTING)
---------------------------------------
GST is *decomposition*, not a settlement deduction. Following the project's
actual financial representation (see `core/match_llm.py` GST rule: gateway
taxable amount + GST == bank settlement amount), the gateway `gross` is the
**pre-GST taxable base** and the bank receives the GST-inclusive amount.
Therefore GST is *added* to reach expected settlement, never subtracted.

This is exactly the "do not blindly subtract GST from gross if GST is already
included" principle: here GST is NOT already included in the gateway gross,
so it is applied additively. If a caller supplies a GST-inclusive gross, they
should pass `gst = 0` (the pre-GST base), and no double-count occurs.

SETTLEMENT IDENTITY
-------------------
    expected_net = gross + gst - tds - mdr - mdr_gst - fee - refund

where every right-hand term is a *positive magnitude* documented below.
GST decomposition is additionally cross-checked (taxable + gst == gross)
as corroborating evidence, never as a second amount adjustment.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Optional

# ---------------------------------------------------------------------------
# Account (no hardcoded transaction values — everything is data-driven)
# ---------------------------------------------------------------------------

# Small, documented epsilon for linked-arithmetic checks. Phase 2 rounds every
# amount to 2 decimals; this absorbs Decimal/float boundary noise, never a real
# discrepancy. It matches `_EXACT_EPSILON` used across the Tier 3 matcher.
EPSILON = Decimal("0.01")

# Statuses — how the accounting layer classifies a settlement.
STATUS_EXACT = "EXACT"                    # no adjustments needed; fully reconciles
STATUS_EXPLAINED = "EXPLAINED"            # accounting adjustments fully explain variance
STATUS_UNEXPLAINED = "UNEXPLAINED"        # genuine unexplained variance remains

# GST decomposition consistency outcomes.
GST_CONSISTENT = "CONSISTENT"
GST_INCONSISTENT = "INCONSISTENT"
GST_NO_EVIDENCE = "NO_EVIDENCE"

# Reasons (structured; keep them descriptive and stable).
REASON_FULLY_EXPLAINED = "FULLY_EXPLAINED"
REASON_UNEXPLAINED_VARIANCE = "UNEXPLAINED_VARIANCE"
REASON_NO_ACCOUNTING_EVIDENCE = "NO_ACCOUNTING_EVIDENCE"
REASON_CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
REASON_REFUND_EXCEEDS_GROSS = "REFUND_EXCEEDS_GROSS"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AccountingError(Exception):
    """Base error for the settlement-accounting layer."""


class AccountingValidationError(AccountingError):
    """An amount was non-numeric, non-finite, or otherwise unsafe to add."""


# ---------------------------------------------------------------------------
# Low-level amount validation (Python stays authoritative)
# ---------------------------------------------------------------------------

def _as_decimal(value, field_name: str) -> Decimal:
    """Coerce a value to a finite Decimal, raising on anything unsafe.

    Accepts int/float/str/Decimal. Rejects None (unless `allow_none`), NaN,
    and infinities. This is the single choke-point for numeric safety so the
    arithmetic below never has to re-check.
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(str(value))
    elif isinstance(value, float):
        # Route through str to keep Decimal from its float-float artifacts.
        d = Decimal(str(value))
    elif isinstance(value, str):
        d = Decimal(value.strip())
    else:
        raise AccountingValidationError(
            f"{field_name}: unsupported numeric type {type(value).__name__}"
        )
    if not d.is_finite():
        raise AccountingValidationError(f"{field_name}: non-finite amount {d}")
    return d


def validate_adjustment(value, field_name: str, permit_negative: bool) -> Decimal:
    """Validate one adjustment magnitude.

    Adjustment magnitudes are normally non-negative (TDS/MDR/fees/refund/GST
    are deductions or additive components). `permit_negative` is only used
    where the project's representation legitimately carries a sign (refunds
    net a negative ledger amount to a positive magnitude).
    """
    d = _as_decimal(value, field_name)
    if not permit_negative and d < 0:
        raise AccountingValidationError(
            f"{field_name}: unexpected negative adjustment {d} "
            "(negative is only permitted for signed refund inputs)"
        )
    return d


# ---------------------------------------------------------------------------
# Primitive calculations (composable, testable in isolation)
# ---------------------------------------------------------------------------

def gst_decomposition(taxable, gst, gross):
    """Check whether `taxable + gst == gross` (within EPSILON).

    Returns (consistency: str, evidence: dict). This is corroborating
    evidence for GST — it never changes expected-*settlement* arithmetic.
    """
    taxable_d = _as_decimal(taxable, "gst.taxable")
    gst_d = _as_decimal(gst, "gst.amount")
    gross_d = _as_decimal(gross, "gst.gross")
    if gst_d == 0:
        return GST_NO_EVIDENCE, {
            "gst_evidence": GST_NO_EVIDENCE,
            "relationship": "no gst_amount provided",
        }
    implied = taxable_d + gst_d
    consistent = abs(implied - gross_d) <= EPSILON
    return (GST_CONSISTENT if consistent else GST_INCONSISTENT), {
        "gst_evidence": GST_CONSISTENT if consistent else GST_INCONSISTENT,
        "taxable_amount": round(float(taxable_d), 2),
        "gst_amount": round(float(gst_d), 2),
        "implied_gross": round(float(implied), 2),
        "reported_gross": round(float(gross_d), 2),
        "relationship": "taxable + gst = gross",
    }


def compute_expected_net(gross, gst=0, tds=0, mdr=0, mdr_gst=0, fee=0, refund=0):
    """The one deterministic settlement path.

    expected_net = gross + gst - tds - mdr - mdr_gst - fee - refund

    GST is additive here (see module docstring: gross is the pre-GST taxable
    base in this dataset and the bank receives gross + GST). Passing a
    GST-inclusive gross with gst=0 avoids double-counting.
    """
    gross_d = validate_adjustment(gross, "gross", permit_negative=False)
    gst_d = validate_adjustment(gst, "gst", permit_negative=False)
    tds_d = validate_adjustment(tds, "tds", permit_negative=False)
    mdr_d = validate_adjustment(mdr, "mdr", permit_negative=False)
    mdr_gst_d = validate_adjustment(mdr_gst, "mdr_gst", permit_negative=False)
    fee_d = validate_adjustment(fee, "fee", permit_negative=False)
    refund_d = validate_adjustment(refund, "refund", permit_negative=False)

    expected = gross_d + gst_d - tds_d - mdr_d - mdr_gst_d - fee_d - refund_d
    return Decimal(expected)


# ---------------------------------------------------------------------------
# Structured settlement breakdown
# ---------------------------------------------------------------------------

@dataclass
class SettlementBreakdown:
    """One structured, evidence-backed accounting result.

    All amounts are stored as 2-decimal floats in `to_dict()` for JSON /
    frontend compatibility (matching NormalizedAmount.normalized). Internally
    computed in Decimal.
    """
    gross_amount: Optional[float]
    gst_amount: float                 # additive GST component (decomposition)
    tds_amount: float
    mdr_amount: float
    mdr_gst_amount: float
    fee_amount: float
    fee_tax_amount: float             # alias for GST-on-MDR
    total_fee_amount: float           # mdr + mdr_gst + fee
    refund_amount: float
    explained_variance: float          # magnitude of gross -> bank movement explained by adjustments
    expected_net_amount: Optional[float]
    actual_bank_amount: Optional[float]
    variance: Optional[float]          # remaining unexplained variance (expected_net - actual)
    remaining_variance: Optional[float]
    status: str
    reason: Optional[str]
    gst_consistency: str
    evidence: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _make_evidence(adjustment_type: str, field_name: str, source_row_id: Optional[str],
                   amount, relationship: str) -> dict:
    return {
        "adjustment": adjustment_type,
        "source_row_id": source_row_id,
        "field": field_name,
        "amount": round(float(Decimal(str(amount))), 2),
        "relationship": relationship,
    }


def compute_settlement(gross, *, gst=0, tds=0, mdr=0, mdr_gst=0, fee=0,
                       refund=0, taxable=None, actual_bank=None,
                       source_rows=None):
    """Compute and classify a full accounting-aware settlement.

    `refund` is a positive magnitude (a negative signed ledger refund is
    reduced to its magnitude by the caller). `taxable` (optional) is used to
    cross-check GST decomposition evidence. `source_rows` (optional) is a dict
    e.g. {"gateway": "G001", "ledger": "L001", "bank": "B001"} used to attach
    traceable identity to each adjustment.
    """
    gross_d = validate_adjustment(gross, "gross", permit_negative=False)
    gst_d = validate_adjustment(gst, "gst", permit_negative=False)
    tds_d = validate_adjustment(tds, "tds", permit_negative=False)
    mdr_d = validate_adjustment(mdr, "mdr", permit_negative=False)
    mdr_gst_d = validate_adjustment(mdr_gst, "mdr_gst", permit_negative=False)
    fee_d = validate_adjustment(fee, "fee", permit_negative=False)
    refund_d = validate_adjustment(refund, "refund", permit_negative=False)
    actual_d = None if actual_bank is None else _as_decimal(actual_bank, "actual_bank")

    # --- Evidence ---------------------------------------------------------
    rows = source_rows or {}
    gateway_id = rows.get("gateway")
    ledger_id = rows.get("ledger")
    bank_id = rows.get("bank")

    evidence: list[dict] = []
    evidence.append(_make_evidence(
        "GROSS", "gross_amount", gateway_id, gross_d,
        "starting gross (pre-adjustment basis)"))
    if gst_d > 0:
        evidence.append(_make_evidence(
            "GST", "gst_amount", ledger_id, gst_d,
            "additive GST component (taxable + gst = gross)"))
    if tds_d > 0:
        evidence.append(_make_evidence(
            "TDS", "tds_amount", ledger_id, tds_d,
            "gross - tds = expected bank"))
    if mdr_d > 0:
        evidence.append(_make_evidence(
            "MDR", "mdr_amount", ledger_id, mdr_d,
            "payment fee deducted from expected settlement"))
    if mdr_gst_d > 0:
        evidence.append(_make_evidence(
            "MDR_GST", "mdr_gst", ledger_id, mdr_gst_d,
            "GST on MDR deducted from expected settlement"))
    if fee_d > 0:
        evidence.append(_make_evidence(
            "FEE", "fee_amount", ledger_id, fee_d,
            "payment fee deducted from expected settlement"))
    if refund_d > 0:
        evidence.append(_make_evidence(
            "REFUND", "refund_amount", ledger_id, refund_d,
            "settlement reduced by refund magnitude"))

    # --- GST decomposition (corroborating, never a second adjustment) ----
    # Only run this when the GST-inclusive receipt (actual bank) is known;
    # without it there is nothing external to cross-check "taxable + gst"
    # against, so the honest answer is NO_EVIDENCE, not a guess.
    gst_consistency = GST_NO_EVIDENCE
    if gst_d > 0 and taxable is not None and actual_d is not None:
        gst_consistency, gst_ev = gst_decomposition(taxable, gst_d, actual_d)
        evidence.append({"gst_decomposition": gst_ev})

    # --- Expected settlement ---------------------------------------------
    expected = compute_expected_net(
        gross_d, gst=gst_d, tds=tds_d, mdr=mdr_d, mdr_gst=mdr_gst_d,
        fee=fee_d, refund=refund_d,
    )

    total_fee = mdr_d + mdr_gst_d + fee_d
    # Magnitude of the gross -> expected movement explained by adjustments.
    explained = gst_d + tds_d + mdr_d + mdr_gst_d + fee_d + refund_d

    any_adjustment = explained != 0
    refund_exceeds = refund_d > gross_d

    # --- Variance classification ------------------------------------------
    # A settlement is EXPLAINED only when deterministic accounting evidence
    # brings expected_net within EPSILON of the actual bank amount. Anything
    # that still differs is genuine unexplained variance, with a precise
    # reason naming the weak link: no evidence at all, or claimed-but-
    # contradictory GST evidence.
    if actual_d is None:
        status = STATUS_EXPLAINED if any_adjustment else STATUS_EXACT
        reason = None
        variance = None
    else:
        variance = Decimal(expected) - actual_d
        if abs(variance) <= EPSILON:
            status = STATUS_EXPLAINED if any_adjustment else STATUS_EXACT
            reason = REASON_FULLY_EXPLAINED if any_adjustment else None
        elif not any_adjustment:
            # A difference exists but there are no accounting signals to
            # explain it — never invent one.
            status = STATUS_UNEXPLAINED
            reason = REASON_NO_ACCOUNTING_EVIDENCE
        elif gst_consistency == GST_INCONSISTENT:
            # GST was claimed as an explanation but does not reconcile.
            status = STATUS_UNEXPLAINED
            reason = REASON_CONTRADICTORY_EVIDENCE
        elif refund_exceeds:
            # Refund magnitude exceeds gross yet a difference still remains.
            status = STATUS_UNEXPLAINED
            reason = REASON_REFUND_EXCEEDS_GROSS
        else:
            status = STATUS_UNEXPLAINED
            reason = REASON_UNEXPLAINED_VARIANCE

    return SettlementBreakdown(
        gross_amount=round(float(gross_d), 2),
        gst_amount=round(float(gst_d), 2),
        tds_amount=round(float(tds_d), 2),
        mdr_amount=round(float(mdr_d), 2),
        mdr_gst_amount=round(float(mdr_gst_d), 2),
        fee_amount=round(float(fee_d), 2),
        fee_tax_amount=round(float(mdr_gst_d), 2),
        total_fee_amount=round(float(total_fee), 2),
        refund_amount=round(float(refund_d), 2),
        explained_variance=round(float(explained), 2),
        expected_net_amount=round(float(expected), 2),
        actual_bank_amount=round(float(actual_d), 2) if actual_d is not None else None,
        variance=round(float(variance), 2) if variance is not None else None,
        remaining_variance=round(float(variance), 2) if variance is not None else None,
        status=status,
        reason=reason,
        gst_consistency=gst_consistency,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Convenience: build a settlement from a ledger CanonicalRecord's tax_fields.
# Reusable by matchers, API, Q&A, and tests. Doesn't depend on tier internals.
# ---------------------------------------------------------------------------

def build_settlement_from_ledger(gross, ledger_record, actual_bank=None,
                                 source_rows=None) -> SettlementBreakdown:
    """Build a SettlementBreakdown from a ledger record's tax_fields.

    Reads gst_amount / tds_amount / mdr_amount / mdr_gst / fee_amount from
    `ledger_record.tax_fields` and `refund` from the ledger's signed amount
    when it is a refund entry (negative recorded_amount). Missing fields
    default to zero using .get(), so this is safe against any normalize.py
    variant (pre- or post-optional-fields).
    """
    tf = getattr(ledger_record, "tax_fields", {}) or {}
    gst = tf.get("gst_amount")
    tds = tf.get("tds_amount")
    mdr = tf.get("mdr_amount")
    mdr_gst = tf.get("mdr_gst")
    fee = tf.get("fee_amount")

    def _val(amount_obj):
        if amount_obj is None:
            return 0
        return getattr(amount_obj, "normalized", amount_obj) or 0

    refund_magnitude = 0
    ledger_amount = getattr(ledger_record.amount, "normalized", None)
    if ledger_amount is not None and ledger_amount < 0:
        refund_magnitude = abs(Decimal(str(ledger_amount)))

    return compute_settlement(
        gross,
        gst=_val(gst),
        tds=_val(tds),
        mdr=_val(mdr),
        mdr_gst=_val(mdr_gst),
        fee=_val(fee),
        refund=refund_magnitude,
        taxable=gross,
        actual_bank=actual_bank,
        source_rows=source_rows,
    )