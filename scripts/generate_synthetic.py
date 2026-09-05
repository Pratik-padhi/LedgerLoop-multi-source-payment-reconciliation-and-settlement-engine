"""
LedgerLoop — Phase 1: Synthetic Dataset Generator
===================================================

Generates three independent, imperfect source files (gateway, bank, ledger)
representing the same underlying settlement batch, plus a ground_truth.csv
that documents the expected reconciliation outcome for every logical
transaction, and a KNOWN_DISCREPANCIES.md describing every deliberately
injected discrepancy.

Deterministic: fixed SEED = 42. Re-running this script produces byte-for-byte
identical output (aside from any wall-clock timestamps, which are not used).

This script ONLY generates data. It contains no matching/reconciliation
logic of any kind.
"""

import csv
import random
import os

SEED = 42
random.seed(SEED)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Source row ID counters (for traceability — every row gets a stable ID)
# ---------------------------------------------------------------------------
_g_counter = 0
_b_counter = 0
_l_counter = 0


def next_g_id():
    global _g_counter
    _g_counter += 1
    return f"G{_g_counter:03d}"


def next_b_id():
    global _b_counter
    _b_counter += 1
    return f"B{_b_counter:03d}"


def next_l_id():
    global _l_counter
    _l_counter += 1
    return f"L{_l_counter:03d}"


# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------
gateway_rows = []   # dicts
bank_rows = []
ledger_rows = []
ground_truth_rows = []
discrepancy_docs = []  # list of dicts describing each documented case

# Settlement batch: all payments happen on 2026-08-20, settle 20-22 Aug.
BATCH_DATE = "2026-08-20"

TAX_RATE_TDS = 0.01  # 1% illustrative TDS rate used only for the TDS cases


def money(x):
    """Fixed 2-decimal precision, INR."""
    return f"{round(x + 1e-9, 2):.2f}"


# ---------------------------------------------------------------------------
# Helper to fabricate a normal exact-match transaction
# ---------------------------------------------------------------------------
def make_normal_match(pay_num, amount, txn_date=BATCH_DATE):
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    inv_id = f"INV{pay_num:03d}"
    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()

    gateway_rows.append({
        "source_row_id": g_id,
        "payment_id": pay_id,
        "payment_date": txn_date,
        "amount": money(amount),
        "status": "CAPTURED",
        "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": txn_date,
    })
    bank_rows.append({
        "source_row_id": b_id,
        "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": txn_date,
        "value_date": txn_date,
        "credit_amount": money(amount),
        "utr": utr,
        "bank_reference": gw_id,
        "description": f"Settlement {pay_id}",
    })
    ledger_rows.append({
        "source_row_id": l_id,
        "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": txn_date,
        "payment_reference": pay_id,
        "invoice_reference": inv_id,
        "recorded_amount": money(amount),
        "tax_amount": "0.00",
        "tds_amount": "0.00",
        "gst_amount": "0.00",
        "mdr_amount": "0.00",
        "mdr_gst": "0.00",
        "fee_amount": "0.00",
        "entry_type": "SALE",
    })

    ground_truth_rows.append({
        "transaction_id": pay_id,
        "expected_status": "MATCHED",
        "expected_category": "NORMAL_EXACT",
        "expected_matching_tier": "TIER_1",
        "expected_gateway_presence": "YES",
        "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "0.00",
        "expected_date_difference": "0",
        "discrepancy_id": "",
    })
    return pay_id, g_id, b_id, l_id


# ===========================================================================
# A. NORMAL EXACT MATCHES  (target ~70 of ~108 total => majority)
# ===========================================================================
NORMAL_COUNT = 70
normal_amounts = [round(random.uniform(150, 15000), 2) for _ in range(NORMAL_COUNT)]

pay_counter = 1
for amt in normal_amounts:
    make_normal_match(pay_counter, amt)
    pay_counter += 1

NORMAL_END = pay_counter - 1  # last PAY number used by normal matches (1..70)

# ===========================================================================
# B. ROUNDING / SMALL AMOUNT DIFFERENCE (Tier 2 tolerance) — 7 cases
# ===========================================================================
rounding_cases = [
    (pay_counter + i, round(random.uniform(200, 5000), 2), round(random.uniform(0.01, 0.05), 2))
    for i in range(7)
]
for pay_num, base_amt, diff in rounding_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    inv_id = f"INV{pay_num:03d}"
    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()
    bank_amt = base_amt - diff  # bank slightly short due to rounding at bank's end

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(base_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(bank_amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id}",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(base_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })

    disc_id = f"DISC-{pay_id}-ROUNDING"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "ROUNDING", "expected_matching_tier": "TIER_2",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(diff), "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Rounding / Small Amount Difference",
        "gateway": f"₹{money(base_amt)} on {BATCH_DATE} ({g_id})",
        "bank": f"₹{money(bank_amt)} on {BATCH_DATE} ({b_id})",
        "ledger": f"₹{money(base_amt)} on {BATCH_DATE} ({l_id})",
        "expected": "MATCHED via TIER_2 (tolerance match)",
        "reason": f"Bank settled ₹{money(diff)} less than gateway/ledger recorded. "
                  f"This is within tolerance and represents the same underlying payment, "
                  f"not a genuine mismatch.",
        "tier": "TIER_2", "exception": "No",
        "amount_diff": money(diff), "date_diff": "0 days",
    })

pay_counter += len(rounding_cases)

# ===========================================================================
# C. SETTLEMENT TIMING DRIFT (Tier 2 date-window matching) — 8 cases
# ===========================================================================
timing_cases = [
    (pay_counter + i, round(random.uniform(200, 8000), 2), random.choice([1, 2]))
    for i in range(8)
]
DATE_PLUS_1 = "2026-08-21"
DATE_PLUS_2 = "2026-08-22"
for pay_num, amt, lag_days in timing_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    inv_id = f"INV{pay_num:03d}"
    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()
    bank_date = DATE_PLUS_1 if lag_days == 1 else DATE_PLUS_2

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": bank_date,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": bank_date, "value_date": bank_date,
        "credit_amount": money(amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id}",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })

    disc_id = f"DISC-{pay_id}-TIMING"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "SETTLEMENT_DELAY", "expected_matching_tier": "TIER_2",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "0.00", "expected_date_difference": str(lag_days),
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Settlement Timing Drift",
        "gateway": f"₹{money(amt)} on {BATCH_DATE} ({g_id})",
        "bank": f"₹{money(amt)} on {bank_date} ({b_id})",
        "ledger": f"₹{money(amt)} on {BATCH_DATE} ({l_id})",
        "expected": "MATCHED via TIER_2 (date-window match)",
        "reason": f"Bank settlement occurred {lag_days} day(s) after the payment/ledger date. "
                  f"This is legitimate settlement lag, not an error.",
        "tier": "TIER_2", "exception": "No",
        "amount_diff": "0.00", "date_diff": f"{lag_days} day(s)",
    })

pay_counter += len(timing_cases)

# ===========================================================================
# D. REFERENCE TRUNCATION / FORMATTING DIFFERENCES — 5 cases
# ===========================================================================
truncation_cases = [
    (pay_counter + i, round(random.uniform(200, 6000), 2))
    for i in range(5)
]
truncation_styles = ["truncate6", "truncate_full_id", "dash_prefix", "no_prefix", "lowercase"]
for (pay_num, amt), style in zip(truncation_cases, truncation_styles):
    pay_id = f"PAY{pay_num:03d}"
    gw_id_full = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()
    utr = f"UTR{100000 + pay_num}"

    if style == "truncate6":
        bank_ref = f"PAY{pay_num:03d}"[:6]          # gateway ref used differently below
        bank_ref_display = pay_id[:6]
    elif style == "truncate_full_id":
        bank_ref_display = gw_id_full[:5]
    elif style == "dash_prefix":
        bank_ref_display = f"PAY-{pay_num:03d}"
    elif style == "no_prefix":
        bank_ref_display = f"{pay_num:03d}"
    else:  # lowercase
        bank_ref_display = gw_id_full.lower()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(amt), "status": "CAPTURED", "gateway_reference": gw_id_full,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(amt), "utr": utr, "bank_reference": bank_ref_display,
        "description": f"Settlement {pay_id}",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })

    disc_id = f"DISC-{pay_id}-REFFMT"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "REFERENCE_FORMATTING", "expected_matching_tier": "TIER_2",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "0.00", "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Reference Truncation / Formatting Difference",
        "gateway": f"gateway_reference = {gw_id_full} ({g_id})",
        "bank": f"bank_reference = {bank_ref_display} ({b_id})",
        "ledger": f"payment_reference = {pay_id} ({l_id})",
        "expected": "MATCHED via TIER_2 (partial/fuzzy reference match)",
        "reason": f"Bank reference is a reformatted/truncated variant of the gateway reference "
                  f"('{style}' style). The underlying payment is the same.",
        "tier": "TIER_2", "exception": "No",
        "amount_diff": "0.00", "date_diff": "0 days",
    })

pay_counter += len(truncation_cases)

# ===========================================================================
# E. DUPLICATE TRANSACTION — 3 cases (duplicate appears in ledger)
# ===========================================================================
duplicate_cases = [
    (pay_counter + i, round(random.uniform(500, 4000), 2))
    for i in range(3)
]
for pay_num, amt in duplicate_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    g_id, b_id, l_id1 = next_g_id(), next_b_id(), next_l_id()
    l_id2 = next_l_id()  # duplicate ledger row

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id}",
    })
    for l_id in (l_id1, l_id2):
        ledger_rows.append({
            "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}_{l_id}",
            "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
            "recorded_amount": money(amt), "tax_amount": "0.00", "tds_amount": "0.00",
            "entry_type": "SALE",
        })

    disc_id = f"DISC-{pay_id}-DUPLICATE"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "DUPLICATE_LEDGER_ENTRY", "expected_matching_tier": "TIER_2",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "DUPLICATE(2)",
        "expected_amount_difference": "0.00", "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Duplicate Ledger Entry",
        "gateway": f"₹{money(amt)}, single row ({g_id})",
        "bank": f"₹{money(amt)}, single settlement ({b_id})",
        "ledger": f"₹{money(amt)} recorded TWICE ({l_id1}, {l_id2}) referencing the same {pay_id}",
        "expected": "EXCEPTION — DUPLICATE_LEDGER_ENTRY (only one settlement exists; "
                    "the second ledger row must not be counted as a separate settled transaction)",
        "reason": "The merchant ledger accidentally recorded the same sale twice. There is only "
                  "one gateway payment and one bank settlement, so the second ledger row is a "
                  "duplicate that must be flagged, not treated as an unmatched extra transaction.",
        "tier": "TIER_2", "exception": "Yes",
        "amount_diff": "0.00", "date_diff": "0 days",
    })

pay_counter += len(duplicate_cases)

# ===========================================================================
# F. PARTIAL REFUND — 4 cases
# ===========================================================================
refund_cases = [
    (pay_counter + i, round(random.uniform(2000, 8000), 2))
    for i in range(4)
]
for pay_num, gross_amt in refund_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    refund_amt = round(gross_amt * random.uniform(0.1, 0.3), 2)
    net_amt = round(gross_amt - refund_amt, 2)

    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()
    g_refund_id = next_g_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gross_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    gateway_rows.append({
        "source_row_id": g_refund_id, "payment_id": f"{pay_id}-REFUND",
        "payment_date": BATCH_DATE, "amount": money(-refund_amt), "status": "REFUNDED",
        "gateway_reference": f"{gw_id}-R", "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(net_amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (net of refund)",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gross_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })
    l_refund_id = next_l_id()
    ledger_rows.append({
        "source_row_id": l_refund_id, "ledger_entry_id": f"LED{pay_num:03d}R",
        "entry_date": BATCH_DATE, "payment_reference": f"{pay_id}-REFUND",
        "invoice_reference": inv_id, "recorded_amount": money(-refund_amt),
        "tax_amount": "0.00", "tds_amount": "0.00", "entry_type": "REFUND",
    })

    disc_id = f"DISC-{pay_id}-REFUND"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "PARTIAL_REFUND", "expected_matching_tier": "TIER_2",
        "expected_gateway_presence": "YES(+REFUND ROW)", "expected_bank_presence": "YES(NET)",
        "expected_ledger_presence": "YES(+REFUND ROW)",
        "expected_amount_difference": money(refund_amt), "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Partial Refund",
        "gateway": f"Original ₹{money(gross_amt)} ({g_id}) + Refund -₹{money(refund_amt)} "
                   f"as {pay_id}-REFUND ({g_refund_id})",
        "bank": f"Net settlement ₹{money(net_amt)} ({b_id})",
        "ledger": f"Original ₹{money(gross_amt)} ({l_id}) + Refund -₹{money(refund_amt)} "
                  f"as {pay_id}-REFUND ({l_refund_id})",
        "expected": "MATCHED via TIER_2 — classified as PARTIAL_REFUND, "
                    "net amount reconciles exactly (gross - refund = bank settlement)",
        "reason": f"₹{money(refund_amt)} was refunded, so bank settled the net ₹{money(net_amt)}. "
                  f"Both gateway and ledger carry an explicit linked refund row, distinguishing "
                  f"this from an unexplained amount mismatch.",
        "tier": "TIER_2", "exception": "No",
        "amount_diff": money(refund_amt), "date_diff": "0 days",
    })

pay_counter += len(refund_cases)

# ===========================================================================
# G. GST/TDS DEDUCTION — 5 cases
# ===========================================================================
tax_cases = [
    (pay_counter + i, round(random.uniform(3000, 12000), 2))
    for i in range(5)
]
for pay_num, gross_amt in tax_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    tds_amt = round(gross_amt * TAX_RATE_TDS, 2)
    net_amt = round(gross_amt - tds_amt, 2)

    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gross_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(net_amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (net of TDS)",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gross_amt), "tax_amount": "0.00", "tds_amount": money(tds_amt),
        "entry_type": "SALE",
    })

    disc_id = f"DISC-{pay_id}-TDS"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "TAX_LINE_MISMATCH", "expected_matching_tier": "TIER_2",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(tds_amt), "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — GST/TDS Deduction",
        "gateway": f"₹{money(gross_amt)} gross ({g_id})",
        "bank": f"₹{money(net_amt)} net of TDS ({b_id})",
        "ledger": f"₹{money(gross_amt)} gross, tds_amount = ₹{money(tds_amt)} ({l_id})",
        "expected": "MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH "
                    "(gross - tds_amount = bank settlement, exactly)",
        "reason": f"Bank settled ₹{money(tds_amt)} less than the gross amount due to TDS "
                  f"deduction (rate {TAX_RATE_TDS*100:.0f}%), which the ledger explicitly "
                  f"records in tds_amount. This must not be classified as a generic amount "
                  f"mismatch.",
        "tier": "TIER_2", "exception": "No",
        "amount_diff": money(tds_amt), "date_diff": "0 days",
    })

pay_counter += len(tax_cases)

# ===========================================================================
# H. MISSING BANK COUNTERPART — 2 cases
# ===========================================================================
missing_bank_cases = [
    (pay_counter + i, round(random.uniform(500, 4000), 2))
    for i in range(2)
]
for pay_num, amt in missing_bank_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    g_id, l_id = next_g_id(), next_l_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })
    # Deliberately NO bank row created.

    disc_id = f"DISC-{pay_id}-NOBANK"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "NO_BANK_COUNTERPART", "expected_matching_tier": "N/A",
        "expected_gateway_presence": "YES", "expected_bank_presence": "NO",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "N/A", "expected_date_difference": "N/A",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Missing Bank Counterpart",
        "gateway": f"₹{money(amt)} on {BATCH_DATE} ({g_id})",
        "bank": "No corresponding row exists in bank.csv",
        "ledger": f"₹{money(amt)} on {BATCH_DATE} ({l_id})",
        "expected": "EXCEPTION — NO_BANK_COUNTERPART (unresolved, goes to exception queue)",
        "reason": "The payment exists in both the gateway export and the merchant ledger, but "
                  "no matching settlement was ever found in the bank statement. The system must "
                  "NOT invent or assume a settlement; this must surface as an unresolved item.",
        "tier": "N/A (unresolved)", "exception": "Yes",
        "amount_diff": "N/A", "date_diff": "N/A",
    })

pay_counter += len(missing_bank_cases)

# ===========================================================================
# I. TRUE ORPHAN — 2 cases (one gateway-only, one bank-only, for good measure)
# ===========================================================================
orphan_cases = [
    (pay_counter, round(random.uniform(500, 4000), 2), "GATEWAY_ONLY"),
    (pay_counter + 1, round(random.uniform(500, 4000), 2), "BANK_ONLY"),
]
for pay_num, amt, kind in orphan_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"

    if kind == "GATEWAY_ONLY":
        g_id = next_g_id()
        gateway_rows.append({
            "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
            "amount": money(amt), "status": "CAPTURED", "gateway_reference": gw_id,
            "customer_reference": f"ORD{pay_num:03d}",
            "settlement_expected_date": BATCH_DATE,
        })
        gateway_ref, bank_ref, ledger_ref = f"YES ({g_id})", "No counterpart", "No counterpart"
        category = "UNMATCHED_GATEWAY_TRANSACTION"
        gt = {"g": "YES", "b": "NO", "l": "NO"}
    else:
        b_id = next_b_id()
        bank_rows.append({
            "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
            "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
            "credit_amount": money(amt), "utr": f"UTR{100000 + pay_num}",
            "bank_reference": "UNKNOWN", "description": "Unidentified inward credit",
        })
        gateway_ref, bank_ref, ledger_ref = "No counterpart", f"YES ({b_id})", "No counterpart"
        category = "UNMATCHED_BANK_TRANSACTION"
        gt = {"g": "NO", "b": "YES", "l": "NO"}

    disc_id = f"DISC-{pay_id}-ORPHAN"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": category, "expected_matching_tier": "N/A",
        "expected_gateway_presence": gt["g"], "expected_bank_presence": gt["b"],
        "expected_ledger_presence": gt["l"],
        "expected_amount_difference": "N/A", "expected_date_difference": "N/A",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — True Orphan ({category})",
        "gateway": gateway_ref, "bank": bank_ref, "ledger": ledger_ref,
        "expected": f"EXCEPTION — {category} (unresolved, goes to exception queue)",
        "reason": f"This transaction exists in exactly one source ({kind.replace('_', ' ').title()}) "
                  f"with no counterpart in either of the other two sources. It must be kept "
                  f"distinct from NO_BANK_COUNTERPART, which requires presence in two sources.",
        "tier": "N/A (unresolved)", "exception": "Yes",
        "amount_diff": "N/A", "date_diff": "N/A",
    })

pay_counter += len(orphan_cases)

TOTAL_TRANSACTIONS = pay_counter - 1

# ---------------------------------------------------------------------------
# Shuffle row order within each source file (but NOT ground truth) to avoid
# an artificially tidy "all rows in PAY-number order" appearance, while
# keeping source_row_id sequential/stable for traceability.
# ---------------------------------------------------------------------------
random.shuffle(gateway_rows)
random.shuffle(bank_rows)
random.shuffle(ledger_rows)


# ---------------------------------------------------------------------------
# Write CSVs
# ---------------------------------------------------------------------------
def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


GATEWAY_FIELDS = ["source_row_id", "payment_id", "payment_date", "amount", "status",
                   "gateway_reference", "customer_reference", "settlement_expected_date"]
BANK_FIELDS = ["source_row_id", "bank_transaction_id", "transaction_date", "value_date",
               "credit_amount", "utr", "bank_reference", "description"]
LEDGER_FIELDS = ["source_row_id", "ledger_entry_id", "entry_date", "payment_reference",
                  "invoice_reference", "recorded_amount", "tax_amount", "tds_amount", "gst_amount", "mdr_amount", "mdr_gst", "fee_amount",
                  "entry_type"]
GT_FIELDS = ["transaction_id", "expected_status", "expected_category", "expected_matching_tier",
             "expected_gateway_presence", "expected_bank_presence", "expected_ledger_presence",
             "expected_amount_difference", "expected_date_difference", "discrepancy_id"]

write_csv(os.path.join(OUT_DIR, "gateway.csv"), gateway_rows, GATEWAY_FIELDS)
write_csv(os.path.join(OUT_DIR, "bank.csv"), bank_rows, BANK_FIELDS)
write_csv(os.path.join(OUT_DIR, "ledger.csv"), ledger_rows, LEDGER_FIELDS)
write_csv(os.path.join(OUT_DIR, "ground_truth.csv"), ground_truth_rows, GT_FIELDS)

# ---------------------------------------------------------------------------
# Write KNOWN_DISCREPANCIES.md
# ---------------------------------------------------------------------------
md_lines = [
    "# KNOWN_DISCREPANCIES.md",
    "",
    "This file documents every deliberately injected discrepancy in the LedgerLoop",
    "Phase 1 synthetic dataset. Each entry is traceable to specific source rows via",
    "their `source_row_id` (e.g. G001, B002, L003).",
    "",
    f"Total logical transactions: {TOTAL_TRANSACTIONS}",
    f"Random seed: {SEED}",
    "",
    "---",
    "",
]
for d in discrepancy_docs:
    md_lines += [
        f"## {d['title']}",
        "",
        f"**Discrepancy ID:** `{d['id']}`",
        "",
        f"**Gateway:** {d['gateway']}",
        "",
        f"**Bank:** {d['bank']}",
        "",
        f"**Ledger:** {d['ledger']}",
        "",
        f"**Expected outcome:** {d['expected']}",
        "",
        f"**Why this is correct:** {d['reason']}",
        "",
        f"**Matching tier:** {d['tier']}",
        "",
        f"**Remains an exception:** {d['exception']}",
        "",
        f"**Amount difference:** {d['amount_diff']} | **Date difference:** {d['date_diff']}",
        "",
        "---",
        "",
    ]

with open(os.path.join(OUT_DIR, "KNOWN_DISCREPANCIES.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md_lines))

# ---------------------------------------------------------------------------
# Console summary (useful when regenerating)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Generated {TOTAL_TRANSACTIONS} logical transactions.")
    print(f"  gateway.csv : {len(gateway_rows)} rows")
    print(f"  bank.csv    : {len(bank_rows)} rows")
    print(f"  ledger.csv  : {len(ledger_rows)} rows")
    print(f"  ground_truth.csv : {len(ground_truth_rows)} rows")
    print(f"  KNOWN_DISCREPANCIES.md : {len(discrepancy_docs)} documented cases")
