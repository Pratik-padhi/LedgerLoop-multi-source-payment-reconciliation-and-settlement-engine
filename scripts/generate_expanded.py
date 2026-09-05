"""
LedgerLoop — Phase 1 Expanded: Enhanced Dataset Generator (250-500 logical transactions)
=====================================================================================

Deterministic expanded dataset with new categories exercising all Tier 3 rules,
including GST, MDR/Fee deduction, split settlements, delayed refunds, and
adversarial patterns.

SEED=42 (same as canonical generator) — reproducible.
Writes to data_large/ so canonical data/ stays byte-identical for deployment.

Categories:
  A. NORMAL_EXACT
  B. ROUNDING
  C. SETTLEMENT_DELAY
  D. REFERENCE_FORMATTING
  E. DUPLICATE_LEDGER_ENTRY
  F. PARTIAL_REFUND
  G. TAX_LINE_MISMATCH (TDS)
  H. NO_BANK_COUNTERPART
  I. TRUE_ORPHAN
  J. GST_DECOMPOSITION (Tier 3)
  K. MDR_FEE_DEDUCTION (Tier 3)
  L. SPLIT_SETTLEMENT_2_ROW (Tier 3)
  M. SPLIT_SETTLEMENT_3_ROW (Tier 3)
  N. DELAYED_REFUND
  O. FULL_REFUND
  P. PARTIAL_PAYMENT
  Q. MULTIPLE_PAYMENTS
  R. AMBIGUOUS_CANDIDATES
  S. CONFLICTING_EVIDENCE
  T. ADVERSARIAL_DECOY
  U. GST_INCORRECT
  V. LLM_RECOMMENDATION_REJECTED

This script ONLY generates data — no matching logic.
"""

import csv
import random
import os

SEED = 42
random.seed(SEED)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "..", "data_large")

os.makedirs(OUT_DIR, exist_ok=True)

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

gateway_rows = []
bank_rows = []
ledger_rows = []
ground_truth_rows = []
discrepancy_docs = []

BATCH_DATE = "2026-08-20"
DATE_PLUS_1 = "2026-08-21"
DATE_PLUS_2 = "2026-08-22"
DATE_PLUS_3 = "2026-08-25"
TAX_RATE_TDS = 0.01

def money(x):
    return f"{round(x + 1e-9, 2):.2f}"

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
# A. NORMAL EXACT MATCHES — 130 cases
# ===========================================================================
NORMAL_COUNT = 130
normal_amounts = [round(random.uniform(150, 15000), 2) for _ in range(NORMAL_COUNT)]

pay_counter = 1
for amt in normal_amounts:
    make_normal_match(pay_counter, amt)
    pay_counter += 1

NORMAL_END = pay_counter - 1

# ===========================================================================
# B. ROUNDING / SMALL AMOUNT DIFFERENCE — 12 cases
# ===========================================================================
rounding_cases = [
    (pay_counter + i, round(random.uniform(200, 5000), 2), round(random.uniform(0.01, 0.05), 2))
    for i in range(12)
]
for pay_num, base_amt, diff in rounding_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    inv_id = f"INV{pay_num:03d}"
    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()
    bank_amt = base_amt - diff

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
                  f"This is within tolerance and represents the same underlying payment.",
        "tier": "TIER_2", "exception": "No",
        "amount_diff": money(diff), "date_diff": "0 days",
    })

pay_counter += len(rounding_cases)

# ===========================================================================
# C. SETTLEMENT TIMING DRIFT — 10 cases
# ===========================================================================
timing_cases = [
    (pay_counter + i, round(random.uniform(200, 8000), 2), random.choice([1, 2]))
    for i in range(10)
]
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
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
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
# D. REFERENCE TRUNCATION / FORMATTING DIFFERENCES — 8 cases
# ===========================================================================
truncation_cases = [
    (pay_counter + i, round(random.uniform(200, 6000), 2))
    for i in range(8)
]
truncation_styles = ["truncate6", "truncate_full_id", "dash_prefix", "no_prefix",
                     "lowercase", "truncate6", "dash_prefix", "no_prefix"]
for (pay_num, amt), style in zip(truncation_cases, truncation_styles):
    pay_id = f"PAY{pay_num:03d}"
    gw_id_full = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()
    utr = f"UTR{100000 + pay_num}"

    if style == "truncate6":
        bank_ref_display = pay_id[:6]
    elif style == "truncate_full_id":
        bank_ref_display = gw_id_full[:5]
    elif style == "dash_prefix":
        bank_ref_display = f"PAY-{pay_num:03d}"
    elif style == "no_prefix":
        bank_ref_display = f"{pay_num:03d}"
    else:
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
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
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
# E. DUPLICATE TRANSACTION — 4 cases
# ===========================================================================
duplicate_cases = [
    (pay_counter + i, round(random.uniform(500, 4000), 2))
    for i in range(4)
]
for pay_num, amt in duplicate_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    g_id, b_id, l_id1 = next_g_id(), next_b_id(), next_l_id()
    l_id2 = next_l_id()

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
            "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
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
# F. PARTIAL REFUND — 6 cases
# ===========================================================================
refund_cases = [
    (pay_counter + i, round(random.uniform(2000, 8000), 2))
    for i in range(6)
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
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    l_refund_id = next_l_id()
    ledger_rows.append({
        "source_row_id": l_refund_id, "ledger_entry_id": f"LED{pay_num:03d}R",
        "entry_date": BATCH_DATE, "payment_reference": f"{pay_id}-REFUND",
        "invoice_reference": inv_id, "recorded_amount": money(-refund_amt),
        "tax_amount": "0.00", "tds_amount": "0.00", "gst_amount": "0.00",
        "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "REFUND",
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
        "reason": f"₹{money(refund_amt)} was refunded, so bank settled the net. "
                  f"Both gateway and ledger carry an explicit linked refund row.",
        "tier": "TIER_2", "exception": "No",
        "amount_diff": money(refund_amt), "date_diff": "0 days",
    })

pay_counter += len(refund_cases)

# ===========================================================================
# G. GST/TDS DEDUCTION — 8 cases
# ===========================================================================
tax_cases = [
    (pay_counter + i, round(random.uniform(3000, 12000), 2))
    for i in range(8)
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
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
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
# H. MISSING BANK COUNTERPART — 4 cases
# ===========================================================================
missing_bank_cases = [
    (pay_counter + i, round(random.uniform(500, 4000), 2))
    for i in range(4)
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
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
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
# I. TRUE ORPHAN — 4 cases (2 gateway-only, 2 bank-only)
# ===========================================================================
orphan_cases = [
    (pay_counter, round(random.uniform(500, 4000), 2), "GATEWAY_ONLY"),
    (pay_counter + 1, round(random.uniform(500, 4000), 2), "BANK_ONLY"),
    (pay_counter + 2, round(random.uniform(500, 4000), 2), "GATEWAY_ONLY"),
    (pay_counter + 3, round(random.uniform(500, 4000), 2), "BANK_ONLY"),
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

# ===========================================================================
# === NEW EXPANDED CATEGORIES: J - V ===
# ===========================================================================

# ===========================================================================
# J. GST DECOMPOSITION — 8 cases (Tier 3 MATCH via GST rule)
# Shape: gateway amount A, ledger gst_amount = G (> 0.05), bank = A + G (ref matches)
# ===========================================================================
j_cases = [
    (pay_counter + i, round(random.uniform(2000, 12000), 2))
    for i in range(8)
]
for pay_num, gw_amt in j_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    # GST rate varies 5-18% of gw amount
    gst_rate = random.choice([0.05, 0.12, 0.18])
    gst_amt = round(gw_amt * gst_rate, 2)
    bank_amt = round(gw_amt + gst_amt, 2)
    # Ensure the gap is NOT within Tier 2 tolerance (0.05) — use at least 1.00
    if gst_amt < 1.00:
        gst_amt = random.uniform(100, 500)
        bank_amt = round(gw_amt + gst_amt, 2)
        gst_amt = round(gst_amt, 2)

    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gw_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(bank_amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (incl. GST)",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gw_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": money(gst_amt), "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-GST-DECOMP"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "GST_DECOMPOSITION", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(gst_amt), "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — GST Decomposition (Tier 3)",
        "gateway": f"₹{money(gw_amt)} gateway amount ({g_id}), ref {gw_id}",
        "bank": f"₹{money(bank_amt)} credit = gateway {money(gw_amt)} + GST {money(gst_amt)} ({b_id}), bank_reference={gw_id}",
        "ledger": f"₹{money(gw_amt)} recorded, gst_amount = ₹{money(gst_amt)} ({l_id})",
        "expected": "MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)",
        "reason": f"Bank settled ₹{money(gst_amt)} more than the raw gateway amount. "
                  f"The ledger's gst_amount field precisely explains the variance: "
                  f"{money(gw_amt)} + {money(gst_amt)} = {money(bank_amt)} (bank). "
                  f"This is a legitimate tax decomposition, not an amount mismatch.",
        "tier": "TIER_3", "exception": "No",
        "amount_diff": money(gst_amt), "date_diff": "0 days",
    })

pay_counter += len(j_cases)

# ===========================================================================
# K. MDR / FEE DEDUCTION — 6 cases (Tier 3 MATCH via MDR rule)
# Shape: gateway A, ledger mdr/mdr_gst/fee, bank = A - mdr - mdr_gst - fee
# ===========================================================================
k_cases = [
    (pay_counter + i, round(random.uniform(3000, 15000), 2))
    for i in range(6)
]
for pay_num, gw_amt in k_cases:
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    # Realistic: MDR 1-2% of gw, GST on MDR 18%, fixed fee 10-50
    mdr_rate = random.choice([0.01, 0.015, 0.02])
    mdr_amt = round(gw_amt * mdr_rate, 2)
    mdr_gst_val = round(mdr_amt * 0.18, 2)
    fee_val = round(random.uniform(10, 50), 2)
    bank_amt = round(gw_amt - mdr_amt - mdr_gst_val - fee_val, 2)

    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gw_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(bank_amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (MDR + fee deducted)",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gw_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": money(mdr_amt), "mdr_gst": money(mdr_gst_val),
        "fee_amount": money(fee_val), "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-MDR-FEE"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "MDR_FEE_DEDUCTION", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(mdr_amt + mdr_gst_val + fee_val),
        "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — MDR / Fee Deduction (Tier 3)",
        "gateway": f"₹{money(gw_amt)} gateway amount ({g_id}), ref {gw_id}",
        "bank": f"₹{money(bank_amt)} = gateway {money(gw_amt)} - MDR {money(mdr_amt)} "
                f"- MDR GST {money(mdr_gst_val)} - fee {money(fee_val)} ({b_id}), bank_reference={gw_id}",
        "ledger": f"₹{money(gw_amt)} recorded, mdr={money(mdr_amt)}, mdr_gst={money(mdr_gst_val)}, fee={money(fee_val)} ({l_id})",
        "expected": "MATCHED via TIER_3 (MDR_FEE_DEDUCTION: gateway - mdr - mdr_gst - fee = bank, exactly)",
        "reason": f"Bank settled less than the gateway by the sum of MDR and fees. "
                  f"The ledger's mdr_amount, mdr_gst, and fee_amount precisely explain: "
                  f"{money(gw_amt)} - {money(mdr_amt)} - {money(mdr_gst_val)} - {money(fee_val)} = {money(bank_amt)}.",
        "tier": "TIER_3", "exception": "No",
        "amount_diff": money(mdr_amt + mdr_gst_val + fee_val), "date_diff": "0 days",
    })

pay_counter += len(k_cases)

# ===========================================================================
# L. SPLIT SETTLEMENT — 2-ROW SPLIT — 6 cases (Tier 3 LLM-assisted)
# Shape: gateway A, 2 bank credits (same ref) summing to A ± small (< 5.00)
# ===========================================================================
for idx in range(6):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    gw_amt = round(random.uniform(3000, 15000), 2)
    # Split: two halves with a small allowable gap (0 - 4.50)
    split_ratio = random.uniform(0.4, 0.6)
    # Total split should sum to gw_amt +/- small gap
    small_gap = round(random.uniform(-4.50, 4.50), 2)
    total_split = round(gw_amt + small_gap, 2)
    b1_amt = round(total_split * split_ratio, 2)
    b2_amt = round(total_split - b1_amt, 2)
    # Ensure each individual row is well OUTSIDE the Tier 2 0.05 tolerance from gw
    # (so Tier 1 and Tier 2 don't match them as individual reconciliations)
    # Each is roughly half of gw, so clearly outside 0.05

    g_id, l_id = next_g_id(), next_l_id()
    b_id1, b_id2 = next_b_id(), next_b_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gw_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id1, "bank_transaction_id": f"BANK{pay_num:03d}-A",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(b1_amt), "utr": f"UTR{100000 + pay_num}-1",
        "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (instr 1/2)",
    })
    bank_rows.append({
        "source_row_id": b_id2, "bank_transaction_id": f"BANK{pay_num:03d}-B",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(b2_amt), "utr": f"UTR{100000 + pay_num}-2",
        "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (instr 2/2)",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gw_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-SPLIT-2ROW"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "SPLIT_SETTLEMENT_2_ROW", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": f"ESPLIT2({b_id1},{b_id2})",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(abs(gw_amt - (b1_amt + b2_amt))),
        "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Split Settlement (2 bank rows, Tier 3 LLM-assisted)",
        "gateway": f"₹{money(gw_amt)} single gateway payment ({g_id}), ref {gw_id}",
        "bank": f"Two credits ₹{money(b1_amt)} ({b_id1}) + ₹{money(b2_amt)} ({b_id2}) = "
                f"₹{money(b1_amt + b2_amt)} (gap {money(abs(gw_amt - (b1_amt + b2_amt)))}, ref {gw_id})",
        "ledger": f"₹{money(gw_amt)} recorded ({l_id})",
        "expected": "MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 2 credits sum within ₹5.00 of gateway)",
        "reason": f"One gateway payment was settled as 2 separate bank credits. "
                  f"The two credits sum to within SPLIT_SETTLEMENT_TOLERANCE (₹5.00) of the gateway amount. "
                  f"An LLM recommender identifies the pair; arithmetic is independently validated.",
        "tier": "TIER_3 (LLM-assisted)", "exception": "No",
        "amount_diff": money(abs(gw_amt - (b1_amt + b2_amt))), "date_diff": "0 days",
    })

pay_counter += 6

# ===========================================================================
# M. SPLIT SETTLEMENT — 3-ROW SPLIT — 4 cases (Tier 3 LLM-assisted)
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    gw_amt = round(random.uniform(5000, 20000), 2)
    small_gap = round(random.uniform(-4.50, 4.50), 2)
    total_split = round(gw_amt + small_gap, 2)
    # Split into 3 parts
    r1, r2 = random.uniform(0.25, 0.35), random.uniform(0.25, 0.35)
    b1_amt = round(total_split * r1, 2)
    b2_amt = round(total_split * r2, 2)
    b3_amt = round(total_split - b1_amt - b2_amt, 2)

    g_id, l_id = next_g_id(), next_l_id()
    b_id1, b_id2, b_id3 = next_b_id(), next_b_id(), next_b_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gw_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    for b_id, b_amt in [(b_id1, b1_amt), (b_id2, b2_amt), (b_id3, b3_amt)]:
        bank_rows.append({
            "source_row_id": b_id, "bank_transaction_id": b_id.replace("B", "BANK"),
            "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
            "credit_amount": money(b_amt), "utr": f"UTR{100000 + pay_num}-{b_id[-1]}",
            "bank_reference": gw_id,
            "description": f"Settlement {pay_id} (instr)",
        })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gw_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-SPLIT-3ROW"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "SPLIT_SETTLEMENT_3_ROW", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES",
        "expected_bank_presence": f"ESPLIT3({b_id1},{b_id2},{b_id3})",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(abs(gw_amt - (b1_amt + b2_amt + b3_amt))),
        "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Split Settlement (3 bank rows, Tier 3 LLM-assisted)",
        "gateway": f"₹{money(gw_amt)} single gateway payment ({g_id}), ref {gw_id}",
        "bank": f"Three credits ₹{money(b1_amt)} + ₹{money(b2_amt)} + ₹{money(b3_amt)} = "
                f"₹{money(b1_amt + b2_amt + b3_amt)} (gap {money(abs(gw_amt - (b1_amt + b2_amt + b3_amt)))}, ref {gw_id})",
        "ledger": f"₹{money(gw_amt)} recorded ({l_id})",
        "expected": "MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 3 credits sum within ₹5.00)",
        "reason": f"One gateway payment was settled as 3 separate bank credits. "
                  f"The three credits together sum within SPLIT_SETTLEMENT_TOLERANCE. "
                  f"LLM recommender is required (2+ combos may be plausible); arithmetic independently validated.",
        "tier": "TIER_3 (LLM-assisted)", "exception": "No",
        "amount_diff": money(abs(gw_amt - (b1_amt + b2_amt + b3_amt))), "date_diff": "0 days",
    })

pay_counter += 4

# ===========================================================================
# N. DELAYED REFUND — 4 cases
# Shape: original gateway+refund, bank net of refund but delayed by days
# The net-settlement pattern (Tier 2 REFUND_LINKED) but with bank on later date
# For delayed refund, bank date is +2 or +3 days; amount matches refund-link logic
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    utr = f"UTR{100000 + pay_num}"
    gross_amt = round(random.uniform(2000, 10000), 2)
    refund_amt = round(gross_amt * random.uniform(0.1, 0.4), 2)
    net_amt = round(gross_amt - refund_amt, 2)
    # Refund issued on BATCH_DATE, settlement delayed by 2-3 days
    refund_date = DATE_PLUS_2

    g_id = next_g_id()
    g_refund_id = next_g_id()
    b_id = next_b_id()
    l_id = next_l_id()
    l_refund_id = next_l_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gross_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": refund_date,
    })
    gateway_rows.append({
        "source_row_id": g_refund_id, "payment_id": f"{pay_id}-REFUND",
        "payment_date": BATCH_DATE, "amount": money(-refund_amt), "status": "REFUNDED",
        "gateway_reference": f"{gw_id}-R", "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": refund_date,
    })
    # Bank settled the NET (gross - refund) but on the REFUND's later date (delayed)
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": refund_date, "value_date": refund_date,
        "credit_amount": money(net_amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (net of refund, delayed)",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gross_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    ledger_rows.append({
        "source_row_id": l_refund_id, "ledger_entry_id": f"LED{pay_num:03d}R",
        "entry_date": refund_date, "payment_reference": f"{pay_id}-REFUND",
        "invoice_reference": inv_id, "recorded_amount": money(-refund_amt),
        "tax_amount": "0.00", "tds_amount": "0.00", "gst_amount": "0.00",
        "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "REFUND",
    })
    disc_id = f"DISC-{pay_id}-DELAYED-REFUND"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "MATCHED",
        "expected_category": "DELAYED_REFUND", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES(+REFUND ROW)", "expected_bank_presence": "YES(NET,DELAYED)",
        "expected_ledger_presence": "YES(+REFUND ROW)",
        "expected_amount_difference": money(refund_amt), "expected_date_difference": "2",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Delayed Refund (net settlement on later date)",
        "gateway": f"Original ₹{money(gross_amt)} ({g_id}) + Refund -₹{money(refund_amt)} ({g_refund_id})",
        "bank": f"Net settlement ₹{money(net_amt)} on {refund_date} ({b_id}) — refund-linked net, delayed by 2 days",
        "ledger": f"Original ₹{money(gross_amt)} ({l_id}) + Refund -₹{money(refund_amt)} ({l_refund_id}) on {refund_date}",
        "expected": "MATCHED via TIER_3 REFUND_LINKED_NET_AMOUNT (net amount reconciles; date delay is corroborating only)",
        "reason": f"₹{money(refund_amt)} was refunded, so bank settled the net ₹{money(net_amt)}. "
                  f"The settlement date is 2 days after the original because the refund decision "
                  f"delayed the net. Gateway and ledger carry linked refund rows.",
        "tier": "TIER_3 (RefundLinked)", "exception": "No",
        "amount_diff": money(refund_amt), "date_diff": "2 days",
    })

pay_counter += 4

# ===========================================================================
# O. FULL REFUND — 4 cases
# Shape: original fully refunded (gross == refund), bank settled net 0 (or refund only)
# Gateway+ledger have full refund; bank has a tiny settlement (if any) or no row
# The refund row has no bank counterpart — goes HUMAN_REVIEW (linked original)
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    gross_amt = round(random.uniform(1000, 8000), 2)
    # Full refund: refund amount equals gross
    refund_amt = gross_amt
    net_amt = 0.00  # nothing to settle

    g_id = next_g_id()
    g_refund_id = next_g_id()
    l_id = next_l_id()
    l_refund_id = next_l_id()

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
    # Bank: NO row for this transaction (net 0, nothing to settle)
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gross_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    ledger_rows.append({
        "source_row_id": l_refund_id, "ledger_entry_id": f"LED{pay_num:03d}R",
        "entry_date": BATCH_DATE, "payment_reference": f"{pay_id}-REFUND",
        "invoice_reference": inv_id, "recorded_amount": money(-refund_amt),
        "tax_amount": "0.00", "tds_amount": "0.00", "gst_amount": "0.00",
        "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "REFUND",
    })
    disc_id = f"DISC-{pay_id}-FULLREFUND"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "FULL_REFUND", "expected_matching_tier": "N/A",
        "expected_gateway_presence": "YES(+REFUND ROW)", "expected_bank_presence": "NO(NET_ZERO)",
        "expected_ledger_presence": "YES(+REFUND ROW)",
        "expected_amount_difference": money(refund_amt), "expected_date_difference": "N/A",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Full Refund (no bank settlement expected)",
        "gateway": f"Original ₹{money(gross_amt)} ({g_id}) + Full Refund -₹{money(refund_amt)} ({g_refund_id})",
        "bank": "No corresponding settlement (net zero — fully refunded before settlement window)",
        "ledger": f"Original ₹{money(gross_amt)} ({l_id}) + Full Refund -₹{money(refund_amt)} ({l_refund_id})",
        "expected": "EXCEPTION — FULL_REFUND (net zero; no bank settlement expected; not an amount mismatch)",
        "reason": f"The payment of ₹{money(gross_amt)} was fully refunded before any bank settlement. "
                  f"There is no bank counterpart to match — this is correct, not an error. "
                  f"It surfaces as an exception for audit, not a Tier 3 human review.",
        "tier": "N/A (exception)", "exception": "Yes",
        "amount_diff": "N/A", "date_diff": "N/A",
    })

pay_counter += 4

# ===========================================================================
# P. PARTIAL PAYMENT — 4 cases
# Shape: gateway paid less than ledger invoice (customer paid part), bank settled that part
# Gateway+bank agree (exact ref+amount), ledger recorded full invoice — goes HUMAN_REVIEW (contradictory)
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    invoice_amt = round(random.uniform(4000, 15000), 2)
    # Customer paid 50-80% of invoice
    paid_amt = round(invoice_amt * random.uniform(0.5, 0.8), 2)
    utr = f"UTR{100000 + pay_num}"

    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(paid_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(paid_amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id}",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(invoice_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-PARTIAL-PAYMENT"
    # Tier 1: gateway+bank exact? gateway ref GW### matches bank GW###, amount paid == paid → exact! So Tier1 PARTIAL (bank matched, ledger not)
    # Tier 2: not eligible (needs gateway+ledger partial). Tier 3: _resolve_bank_present_ledger_missing → TDS check fails, HUMAN_REVIEW
    # But actually Tier1: ledger candidate PAY### with amount invoice != paid → not exact → no ledger match. So Tier1 = PARTIAL gateway+bank. Good.
    # The amount_diff from gateway perspective = invoice - paid (what's unpaid)
    diff_amt = round(invoice_amt - paid_amt, 2)
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "PARTIAL_PAYMENT", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(diff_amt), "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Partial Payment (gateway/bank agree, ledger invoice higher)",
        "gateway": f"₹{money(paid_amt)} paid ({g_id}), ref {gw_id}; UTR {utr}",
        "bank": f"₹{money(paid_amt)} settled ({b_id}), ref {gw_id} — matches gateway exactly",
        "ledger": f"₹{money(invoice_amt)} invoiced/recorded ({l_id}) — customer paid only ₹{money(paid_amt)}, shortfall ₹{money(diff_amt)}",
        "expected": "EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION — two sources agree at ₹{0}, ledger says ₹{1})".format(money(paid_amt), money(invoice_amt)),
        "reason": f"Customer paid ₹{money(paid_amt)} of an invoice recorded as ₹{money(invoice_amt)} "
                  f"(shortfall ₹{money(diff_amt)}). Gateway and bank agree, ledger disagrees. "
                  f"No tax/fee field explains the gap — a human must decide: partial settlement vs. ledger error.",
        "tier": "TIER_3 (human review)", "exception": "Yes",
        "amount_diff": money(diff_amt), "date_diff": "0 days",
    })

pay_counter += 4

# ===========================================================================
# Q. MULTIPLE PAYMENTS — 4 logical transactions, each split into 2 installments
# Shape: one invoice paid in 2 installments. 2 gateway rows (A+B), 2 bank rows, 2 ledger entries
# Each installment matches exactly at Tier 1 → both MATCHED
# ===========================================================================
for grp in range(4):
    inv_id = f"INV{pay_counter:03d}"
    total_invoice = round(random.uniform(4000, 12000), 2)
    # Split into 2 installments: 40-60% each
    inst1 = round(total_invoice * random.uniform(0.4, 0.6), 2)
    inst2 = round(total_invoice - inst1, 2)
    amounts = [inst1, inst2]
    pay_nums = [pay_counter, pay_counter + 1]

    for pay_num, amt in zip(pay_nums, amounts):
        pay_id = f"PAY{pay_num:03d}"
        gw_id = f"GW{pay_num:03d}"
        utr = f"UTR{100000 + pay_num}"
        g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()

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
            "description": f"Settlement {pay_id} (installment for {inv_id})",
        })
        ledger_rows.append({
            "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
            "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
            "recorded_amount": money(amt), "tax_amount": "0.00", "tds_amount": "0.00",
            "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
            "entry_type": "SALE",
        })
        disc_id = f"DISC-{pay_id}-MULTIPAY"
        ground_truth_rows.append({
            "transaction_id": pay_id, "expected_status": "MATCHED",
            "expected_category": "MULTIPLE_PAYMENTS", "expected_matching_tier": "TIER_1",
            "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
            "expected_ledger_presence": "YES",
            "expected_amount_difference": "0.00", "expected_date_difference": "0",
            "discrepancy_id": disc_id,
        })
        discrepancy_docs.append({
            "id": disc_id, "title": f"{pay_id} — Multiple Payments (installment {1 if pay_num == pay_nums[0] else 2}/2 for {inv_id})",
            "gateway": f"₹{money(amt)} installment ({g_id}), ref {gw_id}, customer {inv_id.replace('INV','ORD')}",
            "bank": f"₹{money(amt)} settlement ({b_id}), ref {gw_id}",
            "ledger": f"₹{money(amt)} recorded ({l_id}), invoice {inv_id} (paired total ₹{money(total_invoice)})",
            "expected": f"MATCHED via TIER_1 — installment of a multi-payment invoice",
            "reason": f"Invoice {inv_id} (total ₹{money(total_invoice)}) was paid in 2 installments. "
                      f"This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.",
            "tier": "TIER_1", "exception": "No",
            "amount_diff": "0.00", "date_diff": "0 days",
        })

    pay_counter += 2

# ===========================================================================
# R. AMBIGUOUS CANDIDATES — 4 cases (Tier 3 HUMAN_REVIEW, symmetric evidence)
# Shape: gateway+ledger agree (ref+amount), but 2 bank rows have SAME exact amount
#         and NO distinguishing description → symmetric, must be HUMAN_REVIEW
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    amt = round(random.uniform(1500, 7000), 2)
    gw_amt = amt
    # Create 2 bank rows with exact same amount but different, non-transforming references
    # Neither reference transform-matches GW### → Tier 2 NO_REFERENCE_TRANSFORM_MATCH
    # But at Tier 3, amount-only candidates both exist → symmetric → HUMAN_REVIEW

    g_id, l_id = next_g_id(), next_l_id()
    b_id1, b_id2 = next_b_id(), next_b_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gw_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    # Two bank rows with same amount, neither ref transform-matches
    for b_id, bank_ref in [(b_id1, f"REF-{pay_num:03d}"), (b_id2, f"XREF{pay_num:03d}")]:
        bank_rows.append({
            "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}{b_id[-1]}",
            "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
            "credit_amount": money(gw_amt), "utr": f"UTR{100000 + pay_num}",
            "bank_reference": bank_ref,
            "description": f"Inward credit {b_id}",
        })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gw_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-AMBIGUOUS"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "AMBIGUOUS_CANDIDATES", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": f"AMBIGUOUS2({b_id1},{b_id2})",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "0.00", "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Ambiguous Candidates (symmetric evidence, 2 identical-amount banks)",
        "gateway": f"₹{money(gw_amt)} ({g_id}), ref {gw_id}",
        "bank": f"Two credits at exactly ₹{money(gw_amt)}: {b_id1} (ref REF-{pay_num:03d}) and {b_id2} (ref XREF{pay_num:03d}) — neither ref matches {gw_id}",
        "ledger": f"₹{money(gw_amt)} recorded ({l_id})",
        "expected": "EXCEPTION via TIER_3 HUMAN_REVIEW (SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD) — 2 equally plausible banks",
        "reason": f"Two bank credits both exactly match the gateway/ledger amount, and neither "
                  f"carries a reference or description that distinguishes which belongs to {pay_id}. "
                  f"System must NOT guess; a human must disambiguate.",
        "tier": "TIER_3 (human review)", "exception": "Yes",
        "amount_diff": "0.00", "date_diff": "0 days",
    })

pay_counter += 4

# ===========================================================================
# S. CONFLICTING EVIDENCE — 4 cases (Tier 3 HUMAN_REVIEW, contradictory)
# Shape: gateway GW### bank GW### ref matches, amount exact → Tier1 PARTIAL bank matched
#        But ledger recorded full invoice amount I != paid, so ledger can't match
#        Goes NOT_ELIGIBLE (bank present, ledger missing) → Tier3 _resolve_bank_present...
#        which finds ledger row with conflicting amount, TDS doesn't explain → HUMAN_REVIEW
# For S, we use: gateway paid = A, bank settled = A (agree), ledger recorded = B ≠ A, no tds
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    paid_amt = round(random.uniform(2000, 8000), 2)
    # Ledger recorded a different amount (could be invoice total, related fees, etc.)
    # Make it noticeably different (outside tolerance, not explainable by tds/tax)
    ledger_amt = round(paid_amt * random.choice([1.15, 1.25, 0.85, 1.08]), 2)
    if abs(ledger_amt - paid_amt) < 1.00:
        ledger_amt = round(paid_amt + random.uniform(200, 800), 2)
    utr = f"UTR{100000 + pay_num}"

    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(paid_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(paid_amt), "utr": utr, "bank_reference": gw_id,
        "description": f"Settlement {pay_id}",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(ledger_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-CONFLICTING"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "CONFLICTING_EVIDENCE", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(abs(paid_amt - ledger_amt)),
        "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Conflicting Evidence (gateway/bank agree, ledger disagrees)",
        "gateway": f"₹{money(paid_amt)} ({g_id}), ref {gw_id}",
        "bank": f"₹{money(paid_amt)} settlement ({b_id}), ref {gw_id} — agrees with gateway",
        "ledger": f"₹{money(ledger_amt)} recorded ({l_id}) — differs from gateway/bank (gap ₹{money(abs(paid_amt - ledger_amt))})",
        "expected": "EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION)",
        "reason": f"Gateway and bank agree at ₹{money(paid_amt)}, but the ledger records ₹{money(ledger_amt)} "
                  f"with no tax/fee field explaining the gap. There is no determistic rule to safely reconcile: "
                  f"a human must determine whether the ledger or gateway is correct.",
        "tier": "TIER_3 (human review)", "exception": "Yes",
        "amount_diff": money(abs(paid_amt - ledger_amt)), "date_diff": "0 days",
    })

pay_counter += 4

# ===========================================================================
# T. ADVERSARIAL DECOY — 4 cases (Tier 3 HUMAN_REVIEW, decoy bank row looks plausible)
# Shape: gateway+ledger agree, real bank missing, decoy bank has same amount but
#        wrong/unidentified reference (UNKNOWN or generated). Only one candidate,
#        no corroborating reference → WEAK evidence → HUMAN_REVIEW
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    amt = round(random.uniform(1500, 9000), 2)

    g_id, l_id, b_id = next_g_id(), next_l_id(), next_b_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    # Decoy: same amount, but bank_reference doesn't transform-match (either UNKNOWN or random)
    # Description must NOT contain invoice_reference or customer_reference
    decoy_ref = "UNKNOWN" if idx % 2 == 0 else f"NEFT-{(10000 + pay_num)}"
    decoy_desc = "Unidentified inward credit" if decoy_ref == "UNKNOWN" else "NEFT inward - UNIDENTIFIED"
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(amt), "utr": f"UTR{100000 + pay_num}",
        "bank_reference": decoy_ref,
        "description": decoy_desc,
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-ADVERSARIAL"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "ADVERSARIAL_DECOY", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": f"DECOY({b_id})",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "0.00", "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — Adversarial Decoy (plausible bank row is not same payment)",
        "gateway": f"₹{money(amt)} ({g_id}), ref {gw_id}",
        "bank": f"₹{money(amt)} decoy ({b_id}), ref {decoy_ref!r}, desc '{decoy_desc}' — same amount but no reference connection to {gw_id}",
        "ledger": f"₹{money(amt)} recorded ({l_id})",
        "expected": "EXCEPTION via TIER_3 HUMAN_REVIEW (WEAK_EVIDENCE_INSUFFICIENT — lone amount match, no reference corroboration)",
        "reason": f"A bank credit at exactly ₹{money(amt)} exists, matching the amount, but its reference "
                  f"({decoy_ref!r}) bears no transformable relationship to {gw_id} and its description "
                  f"does not contain the invoice/customer reference. Matching on amount alone, without "
                  f"any corroborating reference, is unsafe — must be reviewed.",
        "tier": "TIER_3 (human review)", "exception": "Yes",
        "amount_diff": "0.00", "date_diff": "0 days",
    })

pay_counter += 4

# ===========================================================================
# U. GST INCORRECT — 4 cases (Tier 3 HUMAN_REVIEW, claimed gst doesn't explain)
# Shape: gateway A, ledger gst_amount = G_claimed, bank = A + G_claimed + error
#         The gst_claimed doesn't make gateway+gst==bank → GST rule fails
#         Also no split plausible, description no match → HUMAN_REVIEW (WEAK evidence)
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    gw_amt = round(random.uniform(3000, 12000), 2)
    # Ledger claims some GST
    claimed_gst = round(gw_amt * random.choice([0.05, 0.12, 0.18]), 2)
    # But the actual bank credit differs by gst + a significant error (e.g. rate mismatch)
    # The clerk booked gst at wrong rate, so bank (actual) differs significantly
    error = round(random.uniform(100, 500), 2) * random.choice([-1, 1])
    # Bank is gw + claimed_gst + error (so gw+claimed_gst ≠ bank)
    bank_amt = round(gw_amt + claimed_gst + error, 2)
    # Make sure bank != gw+claimed_gst by more than 0.01 and also outside split tolerance if considered
    if abs(bank_amt - (gw_amt + claimed_gst)) < 10.0:
        # Ensure meaningful gap
        error = 150.0 if error > 0 else -150.0
        bank_amt = round(gw_amt + claimed_gst + error, 2)

    g_id, b_id, l_id = next_g_id(), next_b_id(), next_l_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gw_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id, "bank_transaction_id": f"BANK{pay_num:03d}",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(bank_amt), "utr": f"UTR{100000 + pay_num}",
        "bank_reference": gw_id,
        "description": f"Settlement {pay_id}",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gw_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": money(claimed_gst), "mdr_amount": "0.00", "mdr_gst": "0.00",
        "fee_amount": "0.00", "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-GST-INCORRECT"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "GST_INCORRECT", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(abs(bank_amt - gw_amt)),
        "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — GST Incorrect (claimed GST does not explain variance)",
        "gateway": f"₹{money(gw_amt)} ({g_id}), ref {gw_id}",
        "bank": f"₹{money(bank_amt)} actual settlement ({b_id}), ref {gw_id} — gap ₹{money(abs(bank_amt - gw_amt))}",
        "ledger": f"₹{money(gw_amt)} recorded, gst_amount claimed ₹{money(claimed_gst)} ({l_id}); "
                  f"gw+claimed_gst={money(gw_amt + claimed_gst)} ≠ bank {money(bank_amt)}",
        "expected": "EXCEPTION via TIER_3 HUMAN_REVIEW (GST rule fails; no other deterministic rule resolves)",
        "reason": f"Ledger claims gst_amount = ₹{money(claimed_gst)}, but {money(gw_amt)} + {money(claimed_gst)} "
                  f"= {money(gw_amt + claimed_gst)} ≠ bank {money(bank_amt)} (error {money(error)}). "
                  f"A human must check: wrong GST rate, mis-booked ledger, or bank-side adjustment.",
        "tier": "TIER_3 (human review)", "exception": "Yes",
        "amount_diff": money(abs(bank_amt - gw_amt)), "date_diff": "0 days",
    })

pay_counter += 4

# ===========================================================================
# V. LLM RECOMMENDATION REJECTED — 4 cases
# Shape: a gateway whose amount COULD look like a split (multiple bank credits at
# same ref), but the "correct" settlement is ambiguous — LLM may recommend a
# combination that fails independent validation. Offline (no LLM) → HUMAN_REVIEW
# via LLM_UNAVAILABLE. With a rejecting LLM → LLM_RECOMMENDATION_REJECTED.
# We use 2 bank credits at same ref summing within tolerance (so plausible),
# but include a 3rd credit also at same ref to create multiple plausible combos
# (2-row vs 2-row pair). Either could sum near gateway → ambiguous.
# ===========================================================================
for idx in range(4):
    pay_num = pay_counter + idx
    pay_id = f"PAY{pay_num:03d}"
    gw_id = f"GW{pay_num:03d}"
    inv_id = f"INV{pay_num:03d}"
    gw_amt = round(random.uniform(6000, 15000), 2)
    # Create 3 bank credits at same ref, where:
    #   A) Any single one is far outside Tier2 tolerance (so not individually matchable)
    #   B) Exactly one 2-row combo sums within ₹5 (the "real" split)
    #   C) A second 2-row combo also plausibly within ₹5 (decoy) — but in our generator,
    #      we will make only the FIRST combo truly within tolerance; the 3rd is noise
    # Simpler: 2 credits sum within tolerance, 3rd is distant noise at same ref
    small_gap = round(random.uniform(-4.00, 4.00), 2)
    total_split = round(gw_amt + small_gap, 2)
    b1_amt = round(total_split * 0.55, 2)
    b2_amt = round(total_split - b1_amt, 2)
    # 3rd credit: random amount also at same GW ref — acts as decoy, but doesn't form a
    # clean split with the others (is smaller, or sum with either b1/b2 ≠ gw)
    b3_amt = round(random.uniform(500, 2000), 2)

    g_id, l_id = next_g_id(), next_l_id()
    b_id1, b_id2, b_id3 = next_b_id(), next_b_id(), next_b_id()

    gateway_rows.append({
        "source_row_id": g_id, "payment_id": pay_id, "payment_date": BATCH_DATE,
        "amount": money(gw_amt), "status": "CAPTURED", "gateway_reference": gw_id,
        "customer_reference": inv_id.replace("INV", "ORD"),
        "settlement_expected_date": BATCH_DATE,
    })
    bank_rows.append({
        "source_row_id": b_id1, "bank_transaction_id": f"BANK{pay_num:03d}-A",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(b1_amt), "utr": f"UTR{100000 + pay_num}-1",
        "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (instr 1/2)",
    })
    bank_rows.append({
        "source_row_id": b_id2, "bank_transaction_id": f"BANK{pay_num:03d}-B",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(b2_amt), "utr": f"UTR{100000 + pay_num}-2",
        "bank_reference": gw_id,
        "description": f"Settlement {pay_id} (instr 2/2)",
    })
    bank_rows.append({
        "source_row_id": b_id3, "bank_transaction_id": f"BANK{pay_num:03d}-C",
        "transaction_date": BATCH_DATE, "value_date": BATCH_DATE,
        "credit_amount": money(b3_amt), "utr": f"UTR{100000 + pay_num}-3",
        "bank_reference": gw_id,
        "description": f"Unrelated credit {pay_id}-C",
    })
    ledger_rows.append({
        "source_row_id": l_id, "ledger_entry_id": f"LED{pay_num:03d}",
        "entry_date": BATCH_DATE, "payment_reference": pay_id, "invoice_reference": inv_id,
        "recorded_amount": money(gw_amt), "tax_amount": "0.00", "tds_amount": "0.00",
        "gst_amount": "0.00", "mdr_amount": "0.00", "mdr_gst": "0.00", "fee_amount": "0.00",
        "entry_type": "SALE",
    })
    disc_id = f"DISC-{pay_id}-LLM-REJECTED"
    ground_truth_rows.append({
        "transaction_id": pay_id, "expected_status": "EXCEPTION",
        "expected_category": "LLM_RECOMMENDATION_REJECTED", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": f"ESPLIT-AMBIG({b_id1},{b_id2},{b_id3})",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": money(abs(gw_amt - (b1_amt + b2_amt))),
        "expected_date_difference": "0",
        "discrepancy_id": disc_id,
    })
    discrepancy_docs.append({
        "id": disc_id, "title": f"{pay_id} — LLM Recommendation Rejected (ambiguous split; validation safety)",
        "gateway": f"₹{money(gw_amt)} ({g_id}), ref {gw_id}",
        "bank": f"Three bank credits at same ref {gw_id}: ₹{money(b1_amt)} ({b_id1}) + ₹{money(b2_amt)} ({b_id2}) = ₹{money(b1_amt+b2_amt)} "
                f"(gap {money(abs(gw_amt-(b1_amt+b2_amt)))} — plausible split); decoy ₹{money(b3_amt)} ({b_id3}) also at {gw_id}",
        "ledger": f"₹{money(gw_amt)} recorded ({l_id})",
        "expected": "EXCEPTION via TIER_3 HUMAN_REVIEW (offline: LLM_UNAVAILABLE; with LLM: recommendation validated only if arithmetic + candidate checks pass)",
        "reason": f"One 2-row combination sums within ₹5.00 of the gateway, but a third bank row at the same reference "
                  f"creates ambiguity (LLM may recommend the wrong pair). The system independently re-derives the sum — "
                  f"a wrong recommendation is rejected. Offline without an LLM, this is HUMAN_REVIEW (LLM unavailable for split adjudication).",
        "tier": "TIER_3 (human review)", "exception": "Yes",
        "amount_diff": money(abs(gw_amt - (b1_amt + b2_amt))), "date_diff": "0 days",
    })

pay_counter += 4

TOTAL_TRANSACTIONS = pay_counter - 1

# ---------------------------------------------------------------------------
# Shuffle row order within each source file (but NOT ground truth)
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
                  "invoice_reference", "recorded_amount", "tax_amount", "tds_amount",
                  "gst_amount", "mdr_amount", "mdr_gst", "fee_amount", "entry_type"]
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
    "# KNOWN_DISCREPANCIES.md (data_large — expanded 250+ transaction dataset)",
    "",
    "This file documents every deliberately injected discrepancy in the LedgerLoop",
    "expanded Phase 1 dataset (250+ logical transactions). Each entry is traceable",
    "to specific source rows via their `source_row_id` (e.g. G001, B002, L003).",
    "",
    f"Total logical transactions: {TOTAL_TRANSACTIONS}",
    f"Random seed: {SEED}",
    f"Dataset directory: data_large/ (data/ is the canonical 111-txn set for deployment)",
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
# Console summary
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Generated {TOTAL_TRANSACTIONS} logical transactions.")
    print(f"  gateway.csv : {len(gateway_rows)} rows")
    print(f"  bank.csv    : {len(bank_rows)} rows")
    print(f"  ledger.csv  : {len(ledger_rows)} rows")
    print(f"  ground_truth.csv : {len(ground_truth_rows)} rows")
    print(f"  KNOWN_DISCREPANCIES.md : {len(discrepancy_docs)} documented cases")
    print(f"  Output directory: {OUT_DIR}")
