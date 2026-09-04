"""
LedgerLoop — Phase 1.1: Tier 3 (LLM Adjudication) Ambiguous Cases — ADDITIVE PATCH
=====================================================================================

This script does NOT regenerate the Phase 1 dataset. It APPENDS a small,
deliberately curated set of Tier 3 cases to the existing gateway.csv, bank.csv,
ledger.csv, and ground_truth.csv, and appends matching documentation to
KNOWN_DISCREPANCIES.md.

Existing rows and existing PAY001–PAY106 transactions are NEVER modified,
reordered, or deleted. This script only appends new rows with new,
non-colliding IDs (PAY107–PAY111, source_row_id continuing from where
Phase 1 left off).

Deterministic: fixed SEED = 42 (kept consistent with Phase 1, though these
cases are hand-designed rather than randomly parameterized, so determinism
here mainly governs the couple of amount values that are randomized).

Run once. Running it again is a no-op guarded by a marker check (see
`already_patched()`), so it is safe to re-run without duplicating rows.
"""

import csv
import os
import random

SEED = 42
random.seed(SEED)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

GATEWAY_PATH = os.path.join(OUT_DIR, "gateway.csv")
BANK_PATH = os.path.join(OUT_DIR, "bank.csv")
LEDGER_PATH = os.path.join(OUT_DIR, "ledger.csv")
GT_PATH = os.path.join(OUT_DIR, "ground_truth.csv")
MD_PATH = os.path.join(OUT_DIR, "KNOWN_DISCREPANCIES.md")

GATEWAY_FIELDS = ["source_row_id", "payment_id", "payment_date", "amount", "status",
                   "gateway_reference", "customer_reference", "settlement_expected_date"]
BANK_FIELDS = ["source_row_id", "bank_transaction_id", "transaction_date", "value_date",
               "credit_amount", "utr", "bank_reference", "description"]
LEDGER_FIELDS = ["source_row_id", "ledger_entry_id", "entry_date", "payment_reference",
                  "invoice_reference", "recorded_amount", "tax_amount", "tds_amount", "entry_type"]
GT_FIELDS = ["transaction_id", "expected_status", "expected_category", "expected_matching_tier",
             "expected_gateway_presence", "expected_bank_presence", "expected_ledger_presence",
             "expected_amount_difference", "expected_date_difference", "discrepancy_id"]

MARKER = "PAY107"  # if this already exists in gateway.csv, the patch has already been applied


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def already_patched():
    rows = read_csv(GATEWAY_PATH)
    return any(r["payment_id"] == MARKER for r in rows)


def append_rows(path, fieldnames, new_rows):
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for r in new_rows:
            writer.writerow(r)


def next_ids():
    g_max = max(int(r["source_row_id"][1:]) for r in read_csv(GATEWAY_PATH))
    b_max = max(int(r["source_row_id"][1:]) for r in read_csv(BANK_PATH))
    l_max = max(int(r["source_row_id"][1:]) for r in read_csv(LEDGER_PATH))
    return g_max, b_max, l_max


def main():
    if already_patched():
        print("Phase 1.1 patch already applied (PAY107 found in gateway.csv). No changes made.")
        return

    g_max, b_max, l_max = next_ids()
    g_ctr, b_ctr, l_ctr = g_max, b_max, l_max

    def gid():
        nonlocal g_ctr
        g_ctr += 1
        return f"G{g_ctr:03d}"

    def bid():
        nonlocal b_ctr
        b_ctr += 1
        return f"B{b_ctr:03d}"

    def lid():
        nonlocal l_ctr
        l_ctr += 1
        return f"L{l_ctr:03d}"

    new_gateway, new_bank, new_ledger, new_gt = [], [], [], []
    discrepancy_docs = []

    BATCH_DATE = "2026-08-20"
    DATE_PLUS_1 = "2026-08-21"

    # =====================================================================
    # PAY107 — Multi-evidence resolvable: reference fragment shared by two
    # candidates, but amount + date + partial reference together point to
    # one specific match.
    # =====================================================================
    # Two gateway payments in the same batch happen to share a common
    # reference substring ("ORD210") because of an unrelated upstream
    # numbering coincidence (realistic: order ref reused across a
    # sub-order/parent-order pair). Only one bank credit references it.
    g107 = gid()
    g_decoy = gid()  # a same-day, same-reference-fragment decoy payment already "explained"
    b107 = bid()
    l107 = lid()

    amt_107 = 3120.50
    amt_decoy = 3120.50  # identical amount — genuinely ambiguous on amount alone

    new_gateway.append({
        "source_row_id": g107, "payment_id": "PAY107", "payment_date": BATCH_DATE,
        "amount": f"{amt_107:.2f}", "status": "CAPTURED", "gateway_reference": "GW107",
        "customer_reference": "ORD210-A", "settlement_expected_date": BATCH_DATE,
    })
    new_gateway.append({
        "source_row_id": g_decoy, "payment_id": "PAY107B", "payment_date": BATCH_DATE,
        "amount": f"{amt_decoy:.2f}", "status": "CAPTURED", "gateway_reference": "GW107B",
        "customer_reference": "ORD210-B", "settlement_expected_date": BATCH_DATE,
    })
    # Bank shows ONE credit for this amount, with a reference that partially
    # matches BOTH gateway_reference values (truncated to "GW107"), but the
    # description field carries the fuller "ORD210-A" fragment — the
    # deciding piece of evidence when combined with the amount.
    new_bank.append({
        "source_row_id": b107, "bank_transaction_id": "BANK107", "transaction_date": BATCH_DATE,
        "value_date": BATCH_DATE, "credit_amount": f"{amt_107:.2f}", "utr": "UTR100107",
        "bank_reference": "GW107", "description": "Settlement ORD210-A batch credit",
    })
    # Only PAY107 (not PAY107B) has a corresponding ledger entry in this
    # batch — PAY107B's ledger entry belongs to a different, unrelated
    # settlement cycle and is intentionally NOT included here (out of scope
    # for this batch), which is itself part of the evidence.
    new_ledger.append({
        "source_row_id": l107, "ledger_entry_id": "LED107", "entry_date": BATCH_DATE,
        "payment_reference": "PAY107", "invoice_reference": "ORD210-A",
        "recorded_amount": f"{amt_107:.2f}", "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })

    disc_107 = "DISC-PAY107-LLM-MULTIEVIDENCE"
    new_gt.append({
        "transaction_id": "PAY107", "expected_status": "MATCHED",
        "expected_category": "LLM_AMBIGUOUS_MATCH", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "0.00", "expected_date_difference": "0",
        "discrepancy_id": disc_107,
    })
    discrepancy_docs.append({
        "id": disc_107, "title": "PAY107 — Ambiguous Reference Shared by Two Candidates "
                                  "(Resolvable via Multiple Evidence)",
        "gateway": f"PAY107: ₹{amt_107:.2f}, gateway_reference=GW107, customer_reference=ORD210-A ({g107})  \n"
                   f"PAY107B: ₹{amt_decoy:.2f}, gateway_reference=GW107B, customer_reference=ORD210-B ({g_decoy})",
        "bank": f"₹{amt_107:.2f} credit, bank_reference=GW107 (truncated — matches both gateway "
                f"references equally), description mentions 'ORD210-A' ({b107})",
        "ledger": f"PAY107: ₹{amt_107:.2f}, payment_reference=PAY107, invoice_reference=ORD210-A ({l107}). "
                  f"No ledger entry exists for PAY107B in this batch.",
        "expected": "MATCHED to PAY107 via TIER_3 LLM adjudication — LLM_AMBIGUOUS_MATCH",
        "reason": "Amount and truncated bank_reference alone cannot distinguish PAY107 from "
                  "PAY107B (both same amount, both same-day, both plausible owners of 'GW107'). "
                  "Exact matching fails (reference is ambiguous) and tolerance/fuzzy rules fail "
                  "(two equally-scoring candidates by reference alone). Resolution requires "
                  "combining THREE signals together: (1) the bank description's fuller "
                  "'ORD210-A' fragment, (2) the fact that only PAY107 has a ledger counterpart "
                  "in this batch, and (3) the exact amount match. No single deterministic rule "
                  "covers this; it is a legitimate Tier 3 case.",
        "tier": "TIER_3 (LLM adjudication)", "exception": "No (resolved)",
        "amount_diff": "0.00", "date_diff": "0 days",
    })

    # =====================================================================
    # PAY108 — Genuinely unresolved: two equally plausible bank credits,
    # same amount, same day, no distinguishing reference on either side.
    # =====================================================================
    g108 = gid()
    l108 = lid()
    b108a = bid()
    b108b = bid()

    amt_108 = 1875.00

    new_gateway.append({
        "source_row_id": g108, "payment_id": "PAY108", "payment_date": BATCH_DATE,
        "amount": f"{amt_108:.2f}", "status": "CAPTURED", "gateway_reference": "GW108",
        "customer_reference": "ORD225", "settlement_expected_date": BATCH_DATE,
    })
    # Both bank credits are genuinely unlabeled / generic — neither carries
    # any reference that ties back to GW108 or ORD225.
    new_bank.append({
        "source_row_id": b108a, "bank_transaction_id": "BANK108A", "transaction_date": BATCH_DATE,
        "value_date": BATCH_DATE, "credit_amount": f"{amt_108:.2f}", "utr": "UTR100108A",
        "bank_reference": "", "description": "NEFT credit",
    })
    new_bank.append({
        "source_row_id": b108b, "bank_transaction_id": "BANK108B", "transaction_date": BATCH_DATE,
        "value_date": BATCH_DATE, "credit_amount": f"{amt_108:.2f}", "utr": "UTR100108B",
        "bank_reference": "", "description": "NEFT credit",
    })
    new_ledger.append({
        "source_row_id": l108, "ledger_entry_id": "LED108", "entry_date": BATCH_DATE,
        "payment_reference": "PAY108", "invoice_reference": "INV108",
        "recorded_amount": f"{amt_108:.2f}", "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })

    disc_108 = "DISC-PAY108-LLM-NEEDSHUMAN"
    new_gt.append({
        "transaction_id": "PAY108", "expected_status": "EXCEPTION",
        "expected_category": "LLM_NEEDS_HUMAN", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES(2 CANDIDATES)",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "0.00", "expected_date_difference": "0",
        "discrepancy_id": disc_108,
    })
    discrepancy_docs.append({
        "id": disc_108, "title": "PAY108 — Two Equally Plausible Bank Credits "
                                  "(Genuinely Unresolved)",
        "gateway": f"₹{amt_108:.2f}, gateway_reference=GW108, customer_reference=ORD225 ({g108})",
        "bank": f"TWO unlabeled NEFT credits of ₹{amt_108:.2f} each, same date, neither carrying "
                f"any reference back to GW108 or ORD225 ({b108a}, {b108b})",
        "ledger": f"₹{amt_108:.2f}, payment_reference=PAY108 ({l108})",
        "expected": "NOT auto-matched — TIER_3 LLM adjudication should return LLM_NEEDS_HUMAN",
        "reason": "There is no evidence anywhere (reference, description, timing, sequencing) "
                  "that distinguishes which of the two identical-amount bank credits belongs to "
                  "PAY108. Picking either one would be a coin flip presented as a confident "
                  "match. This is a deliberate case where the correct behavior is for the LLM "
                  "to decline to guess and route to a human reviewer, rather than being forced "
                  "to pick one.",
        "tier": "TIER_3 (LLM adjudication)", "exception": "Yes (NEEDS_HUMAN)",
        "amount_diff": "0.00", "date_diff": "0 days",
    })

    # =====================================================================
    # PAY109 — Multi-evidence resolvable: split settlement across two bank
    # credits whose sum is close (not exact) to the gateway amount, with a
    # weak but present reference hint tying them together.
    # =====================================================================
    g109 = gid()
    l109 = lid()
    b109a = bid()
    b109b = bid()

    gross_109 = 6400.00
    split_a = 4000.00
    split_b = 2395.50  # sum = 6395.50, ₹4.50 short — plausibly a bank processing fee, undocumented

    new_gateway.append({
        "source_row_id": g109, "payment_id": "PAY109", "payment_date": BATCH_DATE,
        "amount": f"{gross_109:.2f}", "status": "CAPTURED", "gateway_reference": "GW109",
        "customer_reference": "ORD240", "settlement_expected_date": BATCH_DATE,
    })
    new_bank.append({
        "source_row_id": b109a, "bank_transaction_id": "BANK109A", "transaction_date": BATCH_DATE,
        "value_date": BATCH_DATE, "credit_amount": f"{split_a:.2f}", "utr": "UTR100109A",
        "bank_reference": "GW109", "description": "Partial settlement 1 of 2 ORD240",
    })
    new_bank.append({
        "source_row_id": b109b, "bank_transaction_id": "BANK109B", "transaction_date": DATE_PLUS_1,
        "value_date": DATE_PLUS_1, "credit_amount": f"{split_b:.2f}", "utr": "UTR100109B",
        "bank_reference": "109", "description": "Balance credit",
    })
    new_ledger.append({
        "source_row_id": l109, "ledger_entry_id": "LED109", "entry_date": BATCH_DATE,
        "payment_reference": "PAY109", "invoice_reference": "ORD240",
        "recorded_amount": f"{gross_109:.2f}", "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })

    split_sum = round(split_a + split_b, 2)
    diff_109 = round(gross_109 - split_sum, 2)

    disc_109 = "DISC-PAY109-LLM-SPLITSETTLEMENT"
    new_gt.append({
        "transaction_id": "PAY109", "expected_status": "MATCHED",
        "expected_category": "LLM_AMBIGUOUS_MATCH", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES(SPLIT,2 ROWS)",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": f"{diff_109:.2f}", "expected_date_difference": "0-1",
        "discrepancy_id": disc_109,
    })
    discrepancy_docs.append({
        "id": disc_109, "title": "PAY109 — Split Settlement Across Two Bank Credits "
                                  "(Resolvable via Multiple Evidence)",
        "gateway": f"₹{gross_109:.2f} single payment, gateway_reference=GW109, "
                   f"customer_reference=ORD240 ({g109})",
        "bank": f"TWO credits: ₹{split_a:.2f} on {BATCH_DATE} referencing 'GW109' and explicitly "
                f"labeled 'Partial settlement 1 of 2 ORD240' ({b109a}); ₹{split_b:.2f} on "
                f"{DATE_PLUS_1} referencing only '109' with generic description ({b109b}). "
                f"Combined sum ₹{split_sum:.2f} is ₹{diff_109:.2f} short of the gateway amount.",
        "ledger": f"₹{gross_109:.2f}, payment_reference=PAY109 ({l109})",
        "expected": "MATCHED (as a split settlement) via TIER_3 LLM adjudication — "
                    "LLM_AMBIGUOUS_MATCH",
        "reason": "No single bank row matches the gateway amount, so exact matching fails "
                  "outright. Tolerance rules fail too: neither individual bank amount is within "
                  "a normal rounding tolerance of ₹6400.00, and the combined sum still leaves an "
                  "unexplained ₹4.50 gap (larger than the dataset's typical rounding tolerance, "
                  "so Tier 2 should not silently absorb it). Resolving this requires combining "
                  "THREE weak signals: the explicit '1 of 2 ORD240' description on the first "
                  "credit, the numeric fragment '109' on the second, and the near-equality of "
                  "their sum to the gateway amount across two consecutive dates. This is a "
                  "legitimate Tier 3 case — a human or LLM adjudicator would reasonably conclude "
                  "this is a split settlement with a small unexplained residual, not two separate "
                  "unrelated transactions.",
        "tier": "TIER_3 (LLM adjudication)", "exception": "No (resolved, with residual flagged)",
        "amount_diff": f"{diff_109:.2f}", "date_diff": "0-1 day(s) across the two credits",
    })

    # =====================================================================
    # PAY110 — Contradictory signals: reference matches exactly, amount is
    # off by a real, non-trivial, undocumented amount. Should NOT be forced
    # to match; correct behavior is NEEDS_HUMAN.
    # =====================================================================
    g110 = gid()
    b110 = bid()
    l110 = lid()

    amt_gateway_110 = 5000.00
    amt_ledger_110 = 4550.00  # ₹450 short, no tax/refund fields populated to explain it

    new_gateway.append({
        "source_row_id": g110, "payment_id": "PAY110", "payment_date": BATCH_DATE,
        "amount": f"{amt_gateway_110:.2f}", "status": "CAPTURED", "gateway_reference": "GW110",
        "customer_reference": "ORD255", "settlement_expected_date": BATCH_DATE,
    })
    new_bank.append({
        "source_row_id": b110, "bank_transaction_id": "BANK110", "transaction_date": BATCH_DATE,
        "value_date": BATCH_DATE, "credit_amount": f"{amt_gateway_110:.2f}", "utr": "UTR100110",
        "bank_reference": "GW110", "description": "Settlement PAY110",
    })
    # Ledger reference matches perfectly, but the recorded amount is
    # meaningfully different with NO tax/tds/refund fields populated to
    # explain the gap — a real conflict, not a documented discrepancy type.
    new_ledger.append({
        "source_row_id": l110, "ledger_entry_id": "LED110", "entry_date": BATCH_DATE,
        "payment_reference": "PAY110", "invoice_reference": "INV110",
        "recorded_amount": f"{amt_ledger_110:.2f}", "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })

    diff_110 = round(amt_gateway_110 - amt_ledger_110, 2)
    disc_110 = "DISC-PAY110-LLM-NEEDSHUMAN"
    new_gt.append({
        "transaction_id": "PAY110", "expected_status": "EXCEPTION",
        "expected_category": "LLM_NEEDS_HUMAN", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": f"{diff_110:.2f}", "expected_date_difference": "0",
        "discrepancy_id": disc_110,
    })
    discrepancy_docs.append({
        "id": disc_110, "title": "PAY110 — Perfect Reference Match, Unexplained Amount "
                                  "Conflict (Genuinely Unresolved)",
        "gateway": f"₹{amt_gateway_110:.2f}, gateway_reference=GW110 ({g110})",
        "bank": f"₹{amt_gateway_110:.2f}, bank_reference=GW110 — agrees exactly with gateway ({b110})",
        "ledger": f"₹{amt_ledger_110:.2f}, payment_reference=PAY110 (exact reference match) but "
                  f"₹{diff_110:.2f} short of gateway/bank, with tax_amount and tds_amount both "
                  f"0.00 — nothing in the ledger explains the gap ({l110})",
        "expected": "NOT auto-matched — TIER_3 LLM adjudication should return LLM_NEEDS_HUMAN",
        "reason": "The reference linkage is unambiguous (gateway, bank, and ledger all cite the "
                  "same payment), so this is not a reference-ambiguity case. But the amount gap "
                  "(₹450.00) is too large for Tier 2 rounding tolerance, and no refund, tax, or "
                  "TDS field explains it — unlike the documented PARTIAL_REFUND and "
                  "TAX_LINE_MISMATCH cases, which carry explicit supporting fields. This is a "
                  "genuine conflict between strong identity evidence and irreconcilable amount "
                  "evidence. Forcing a match would hide a possible ledger data-entry error or "
                  "an undisclosed deduction; the correct behavior is to flag it for a human to "
                  "investigate rather than have the LLM guess whether it's benign.",
        "tier": "TIER_3 (LLM adjudication)", "exception": "Yes (NEEDS_HUMAN)",
        "amount_diff": f"{diff_110:.2f}", "date_diff": "0 days",
    })

    # =====================================================================
    # PAY111 — Resolvable via soft/textual evidence: gateway_reference is
    # missing from the bank row entirely, but the bank description contains
    # a free-text order reference that matches the ledger's invoice
    # reference, allowing the link to be inferred.
    # =====================================================================
    g111 = gid()
    b111 = bid()
    l111 = lid()

    amt_111 = 2260.75

    new_gateway.append({
        "source_row_id": g111, "payment_id": "PAY111", "payment_date": BATCH_DATE,
        "amount": f"{amt_111:.2f}", "status": "CAPTURED", "gateway_reference": "GW111",
        "customer_reference": "ORD270", "settlement_expected_date": BATCH_DATE,
    })
    # Bank reference field is blank (a real-world occurrence for some
    # payment corridors), but the free-text description happens to carry
    # the customer/order reference instead of the gateway reference.
    new_bank.append({
        "source_row_id": b111, "bank_transaction_id": "BANK111", "transaction_date": BATCH_DATE,
        "value_date": BATCH_DATE, "credit_amount": f"{amt_111:.2f}", "utr": "UTR100111",
        "bank_reference": "", "description": "Payment received for ORD270",
    })
    new_ledger.append({
        "source_row_id": l111, "ledger_entry_id": "LED111", "entry_date": BATCH_DATE,
        "payment_reference": "PAY111", "invoice_reference": "ORD270",
        "recorded_amount": f"{amt_111:.2f}", "tax_amount": "0.00", "tds_amount": "0.00",
        "entry_type": "SALE",
    })

    disc_111 = "DISC-PAY111-LLM-TEXTUALEVIDENCE"
    new_gt.append({
        "transaction_id": "PAY111", "expected_status": "MATCHED",
        "expected_category": "LLM_AMBIGUOUS_MATCH", "expected_matching_tier": "TIER_3",
        "expected_gateway_presence": "YES", "expected_bank_presence": "YES",
        "expected_ledger_presence": "YES",
        "expected_amount_difference": "0.00", "expected_date_difference": "0",
        "discrepancy_id": disc_111,
    })
    discrepancy_docs.append({
        "id": disc_111, "title": "PAY111 — Missing Bank Reference, Identifiable via "
                                  "Free-Text Description",
        "gateway": f"₹{amt_111:.2f}, gateway_reference=GW111, customer_reference=ORD270 ({g111})",
        "bank": f"₹{amt_111:.2f}, bank_reference is BLANK, but description reads "
                f"'Payment received for ORD270' ({b111})",
        "ledger": f"₹{amt_111:.2f}, payment_reference=PAY111, invoice_reference=ORD270 ({l111})",
        "expected": "MATCHED via TIER_3 LLM adjudication — LLM_AMBIGUOUS_MATCH",
        "reason": "The structured bank_reference field — which every deterministic Tier 1/Tier 2 "
                  "rule relies on — is empty, so exact and fuzzy reference matching have no field "
                  "to operate on. The only link between the bank row and the payment is unstructured "
                  "free text ('ORD270') that happens to match the ledger's invoice_reference and "
                  "the gateway's customer_reference. Interpreting free-text descriptions is a "
                  "natural-language task outside deterministic rule matching, making this a "
                  "legitimate Tier 3 case that a rule-based Tier 2 pass would likely leave "
                  "unmatched even though sufficient evidence exists to resolve it confidently.",
        "tier": "TIER_3 (LLM adjudication)", "exception": "No (resolved)",
        "amount_diff": "0.00", "date_diff": "0 days",
    })

    # =====================================================================
    # Append everything
    # =====================================================================
    append_rows(GATEWAY_PATH, GATEWAY_FIELDS, new_gateway)
    append_rows(BANK_PATH, BANK_FIELDS, new_bank)
    append_rows(LEDGER_PATH, LEDGER_FIELDS, new_ledger)
    append_rows(GT_PATH, GT_FIELDS, new_gt)

    md_lines = [
        "",
        "# Phase 1.1 Addendum — Tier 3 (LLM Adjudication) Ambiguous Cases",
        "",
        "The cases below were added in Phase 1.1 to provide genuine Tier 3 test coverage. "
        "They were appended to the existing dataset without modifying any prior transaction. "
        "Two categories are used:",
        "",
        "- **LLM_AMBIGUOUS_MATCH** — sufficient evidence exists to confidently resolve the "
        "transaction, but only by combining multiple weak/partial signals together; no single "
        "deterministic Tier 1/Tier 2 rule can resolve it alone.",
        "- **LLM_NEEDS_HUMAN** — evidence is genuinely insufficient or contradictory; the "
        "correct behavior is for the LLM to decline to guess and route the case to a human "
        "reviewer rather than being forced into a match.",
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

    with open(MD_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"Phase 1.1 patch applied: added {len(new_gt)} new logical transactions "
          f"(PAY107–PAY111).")
    print(f"  gateway.csv : +{len(new_gateway)} rows")
    print(f"  bank.csv    : +{len(new_bank)} rows")
    print(f"  ledger.csv  : +{len(new_ledger)} rows")
    print(f"  ground_truth.csv : +{len(new_gt)} rows")
    print(f"  KNOWN_DISCREPANCIES.md : +{len(discrepancy_docs)} documented cases")


if __name__ == "__main__":
    main()
