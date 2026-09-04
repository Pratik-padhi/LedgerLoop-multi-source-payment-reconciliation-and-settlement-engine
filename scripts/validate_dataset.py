"""
LedgerLoop — Phase 1: Dataset Validation
==========================================

Verifies the synthetic dataset itself (files, schemas, counts, required
failure modes, documentation completeness, and data-quality invariants).

This script does NOT perform any reconciliation/matching logic — it only
validates that the generated data is internally consistent and complete
enough to be used for testing a future reconciliation engine.

Usage:
    python3 validate_dataset.py
Exit code 0 = all checks passed. Exit code 1 = at least one check failed.
"""

import csv
import os
import re
import sys
from datetime import datetime

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

REQUIRED_FILES = ["gateway.csv", "bank.csv", "ledger.csv",
                   "ground_truth.csv", "KNOWN_DISCREPANCIES.md"]

EXPECTED_COLUMNS = {
    "gateway.csv": ["source_row_id", "payment_id", "payment_date", "amount", "status",
                     "gateway_reference", "customer_reference", "settlement_expected_date"],
    "bank.csv": ["source_row_id", "bank_transaction_id", "transaction_date", "value_date",
                  "credit_amount", "utr", "bank_reference", "description"],
    "ledger.csv": ["source_row_id", "ledger_entry_id", "entry_date", "payment_reference",
                    "invoice_reference", "recorded_amount", "tax_amount", "tds_amount", "entry_type"],
    "ground_truth.csv": ["transaction_id", "expected_status", "expected_category",
                          "expected_matching_tier", "expected_gateway_presence",
                          "expected_bank_presence", "expected_ledger_presence",
                          "expected_amount_difference", "expected_date_difference",
                          "discrepancy_id"],
}

REQUIRED_CATEGORIES = {
    "NORMAL_EXACT", "ROUNDING", "SETTLEMENT_DELAY", "REFERENCE_FORMATTING",
    "DUPLICATE_LEDGER_ENTRY", "PARTIAL_REFUND", "TAX_LINE_MISMATCH",
    "NO_BANK_COUNTERPART",
}
# At least one of these two orphan categories must exist (both are generated,
# but validation only strictly requires "a true orphan" to exist per spec).
ORPHAN_CATEGORIES = {"UNMATCHED_GATEWAY_TRANSACTION", "UNMATCHED_BANK_TRANSACTION"}

# Phase 1.1: gateway payment_ids that are intentionally NOT standalone logical
# transactions in ground_truth.csv. These exist purely as supporting evidence
# (a plausible decoy/candidate) inside another transaction's Tier 3 ambiguity
# case, and are documented as such in KNOWN_DISCREPANCIES.md.
KNOWN_EVIDENCE_ONLY_GATEWAY_IDS = {
    "PAY107B",  # decoy candidate for PAY107's LLM_AMBIGUOUS_MATCH case — see DISC-PAY107-LLM-MULTIEVIDENCE
}

# Phase 1.1: Tier 3 (LLM adjudication) categories.
TIER3_CATEGORIES = {"LLM_AMBIGUOUS_MATCH", "LLM_NEEDS_HUMAN"}
MIN_TIER3_CASES = 3
MAX_TIER3_CASES = 5  # per Phase 1.1 spec ("3-5 deliberately ambiguous transactions")

AMOUNT_RE = re.compile(r"^-?\d+\.\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

errors = []
warnings = []


def check(condition, message, is_warning=False):
    if not condition:
        (warnings if is_warning else errors).append(message)
    return condition


def read_csv(name):
    path = os.path.join(OUT_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    # 1. Required files exist
    for fname in REQUIRED_FILES:
        check(os.path.isfile(os.path.join(OUT_DIR, fname)), f"Missing required file: {fname}")
    if errors:
        report()
        return

    gateway = read_csv("gateway.csv")
    bank = read_csv("bank.csv")
    ledger = read_csv("ledger.csv")
    ground_truth = read_csv("ground_truth.csv")

    # 2. Expected columns present
    for fname, rows, key in [("gateway.csv", gateway, None), ("bank.csv", bank, None),
                               ("ledger.csv", ledger, None), ("ground_truth.csv", ground_truth, None)]:
        if rows:
            actual_cols = set(rows[0].keys())
            expected_cols = set(EXPECTED_COLUMNS[fname])
            missing = expected_cols - actual_cols
            check(not missing, f"{fname} missing expected columns: {missing}")

    # 3. At least 100 logical transactions (based on ground_truth, one row per logical txn)
    check(len(ground_truth) >= 100,
          f"Expected at least 100 logical transactions, found {len(ground_truth)}")

    # 4. All required failure modes exist in ground_truth
    categories_present = {r["expected_category"] for r in ground_truth}
    missing_categories = REQUIRED_CATEGORIES - categories_present
    check(not missing_categories, f"Missing required failure-mode categories: {missing_categories}")
    check(bool(categories_present & ORPHAN_CATEGORIES),
          "No true-orphan category (UNMATCHED_GATEWAY_TRANSACTION / UNMATCHED_BANK_TRANSACTION) found")

    # 4b. Phase 1.1 — Tier 3 (LLM adjudication) coverage.
    tier3_rows = [r for r in ground_truth if r["expected_matching_tier"] == "TIER_3"]
    check(MIN_TIER3_CASES <= len(tier3_rows) <= MAX_TIER3_CASES,
          f"Expected {MIN_TIER3_CASES}-{MAX_TIER3_CASES} TIER_3 cases, found {len(tier3_rows)}")

    tier3_categories_present = {r["expected_category"] for r in tier3_rows}
    check(tier3_categories_present.issubset(TIER3_CATEGORIES),
          f"TIER_3 rows use unexpected categories (expected only {TIER3_CATEGORIES}): "
          f"{tier3_categories_present - TIER3_CATEGORIES}")
    check("LLM_AMBIGUOUS_MATCH" in tier3_categories_present,
          "No LLM_AMBIGUOUS_MATCH case found among TIER_3 rows")
    check("LLM_NEEDS_HUMAN" in tier3_categories_present,
          "No LLM_NEEDS_HUMAN case found among TIER_3 rows — at least one genuinely "
          "unresolved case is required")

    # Every category outside TIER_3 must NOT claim TIER_3, and vice versa
    # (tier and category should be consistent).
    mismatched = [r["transaction_id"] for r in ground_truth
                  if (r["expected_category"] in TIER3_CATEGORIES) != (r["expected_matching_tier"] == "TIER_3")]
    check(not mismatched,
          f"Rows where expected_category (LLM_*) and expected_matching_tier (TIER_3) are "
          f"inconsistent: {mismatched}")

    # 4c. Phase 1.1 — Tier 3 cases must not be trivially resolvable by exact
    # matching: for LLM_NEEDS_HUMAN cases specifically, check that either the
    # bank side has >1 same-amount unlabeled candidate, or amount/reference
    # evidence genuinely conflicts (heuristic spot-check, not a matching
    # engine — Phase 1 does not implement matching logic).
    needs_human_ids = {r["transaction_id"] for r in tier3_rows
                        if r["expected_category"] == "LLM_NEEDS_HUMAN"}
    for txn_id in needs_human_ids:
        gw_row = next((r for r in gateway if r["payment_id"] == txn_id), None)
        led_row = next((r for r in ledger if r["payment_reference"] == txn_id), None)
        if gw_row and led_row:
            same_ref_bank = [r for r in bank if r["bank_reference"] == gw_row["gateway_reference"]]
            same_amount_bank = [r for r in bank if r["credit_amount"] == gw_row["amount"]]
            ambiguous_bank = len(same_amount_bank) >= 2 and not same_ref_bank
            amount_conflict = gw_row["amount"] != led_row["recorded_amount"] and \
                abs(float(gw_row["amount"]) - float(led_row["recorded_amount"])) > 1.00
            check(ambiguous_bank or amount_conflict,
                  f"{txn_id} is marked LLM_NEEDS_HUMAN but does not exhibit either multi-candidate "
                  f"bank ambiguity or a real (>₹1.00, undocumented) amount conflict — verify this "
                  f"case is genuinely ambiguous, not trivially resolvable", is_warning=True)

    # 5. Ground truth transaction IDs: gateway-sourced IDs (PAYxxx, excluding refund
    #    sub-rows and the bank-only orphan) should be traceable.
    gt_ids = {r["transaction_id"] for r in ground_truth}
    gateway_payment_ids = {r["payment_id"] for r in gateway if not r["payment_id"].endswith("-REFUND")}
    # Every "normal" gateway payment_id should appear in ground truth (bank-only orphan won't,
    # by design, since it has no gateway row; evidence-only decoy rows are an explicitly
    # documented Phase 1.1 exception — see KNOWN_EVIDENCE_ONLY_GATEWAY_IDS).
    missing_from_gt = gateway_payment_ids - gt_ids - KNOWN_EVIDENCE_ONLY_GATEWAY_IDS
    check(not missing_from_gt,
          f"{len(missing_from_gt)} gateway payment_id(s) missing from ground_truth: "
          f"{sorted(missing_from_gt)[:10]}")
    # Guard against the allowlist silently growing stale: every allowlisted ID must
    # still actually exist in gateway.csv and still be absent from ground_truth.
    stale_allowlist = KNOWN_EVIDENCE_ONLY_GATEWAY_IDS - gateway_payment_ids
    check(not stale_allowlist,
          f"KNOWN_EVIDENCE_ONLY_GATEWAY_IDS references payment_id(s) no longer in gateway.csv: "
          f"{stale_allowlist}", is_warning=True)
    unexpectedly_in_gt = KNOWN_EVIDENCE_ONLY_GATEWAY_IDS & gt_ids
    check(not unexpectedly_in_gt,
          f"Evidence-only gateway id(s) unexpectedly found in ground_truth.csv "
          f"(allowlist may be stale): {unexpectedly_in_gt}", is_warning=True)

    # 6. Every injected discrepancy documented: cross-check discrepancy_id references
    #    in ground_truth against KNOWN_DISCREPANCIES.md content.
    with open(os.path.join(OUT_DIR, "KNOWN_DISCREPANCIES.md"), encoding="utf-8") as f:
        md_content = f.read()
    disc_ids = [r["discrepancy_id"] for r in ground_truth if r["discrepancy_id"]]
    undocumented = [d for d in disc_ids if d not in md_content]
    check(not undocumented, f"Discrepancy IDs referenced in ground_truth but not documented "
                             f"in KNOWN_DISCREPANCIES.md: {undocumented}")

    # 7. No accidental duplicate primary IDs (source_row_id must be unique per file;
    #    payment_id in gateway may only repeat for deliberate -REFUND pairs, which have
    #    distinct payment_id strings already, so gateway payment_id should be fully unique;
    #    ledger payment_reference MAY repeat only for documented DUPLICATE_LEDGER_ENTRY cases).
    def check_unique(rows, field, fname):
        values = [r[field] for r in rows]
        dupes = {v for v in values if values.count(v) > 1}
        check(not dupes, f"{fname}: unexpected duplicate {field} values: {dupes}")

    check_unique(gateway, "source_row_id", "gateway.csv")
    check_unique(bank, "source_row_id", "bank.csv")
    check_unique(ledger, "source_row_id", "ledger.csv")
    check_unique(gateway, "payment_id", "gateway.csv")

    duplicate_flagged_ids = {r["transaction_id"] for r in ground_truth
                              if r["expected_category"] == "DUPLICATE_LEDGER_ENTRY"}
    ledger_refs = [r["payment_reference"] for r in ledger]
    ledger_ref_dupes = {v for v in ledger_refs if ledger_refs.count(v) > 1}
    undocumented_ledger_dupes = ledger_ref_dupes - duplicate_flagged_ids
    check(not undocumented_ledger_dupes,
          f"ledger.csv has duplicate payment_reference values not documented as "
          f"DUPLICATE_LEDGER_ENTRY: {undocumented_ledger_dupes}")

    # 8. All amounts valid INR values with two decimal places
    for fname, rows, field in [("gateway.csv", gateway, "amount"),
                                 ("bank.csv", bank, "credit_amount"),
                                 ("ledger.csv", ledger, "recorded_amount")]:
        bad = [r[field] for r in rows if not AMOUNT_RE.match(r[field])]
        check(not bad, f"{fname}: invalid amount format in '{field}': {bad[:5]}")
    for r in ledger:
        for field in ("tax_amount", "tds_amount"):
            check(AMOUNT_RE.match(r[field]) is not None,
                  f"ledger.csv: invalid {field} format for {r['ledger_entry_id']}: {r[field]}")

    # 9. Dates valid
    def valid_date(s):
        return bool(DATE_RE.match(s)) and _parses(s)

    def _parses(s):
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    for fname, rows, fields in [("gateway.csv", gateway, ["payment_date", "settlement_expected_date"]),
                                  ("bank.csv", bank, ["transaction_date", "value_date"]),
                                  ("ledger.csv", ledger, ["entry_date"])]:
        for r in rows:
            for field in fields:
                check(valid_date(r[field]), f"{fname}: invalid date '{r[field]}' in {field} "
                                             f"(row {r.get('source_row_id')})")

    # 10. Deterministic regeneration check.
    # The full pipeline is now two steps: (1) generate_synthetic.py builds the
    # base Phase 1 dataset (PAY001-PAY106), then (2) patch_phase1_1_tier3.py
    # additively appends the Phase 1.1 Tier 3 cases (PAY107-PAY111). Both
    # steps must be deterministic together: regenerating from scratch and
    # re-applying the patch must reproduce the current files exactly.
    import hashlib

    def hash_files():
        h = {}
        for fname in ["gateway.csv", "bank.csv", "ledger.csv", "ground_truth.csv",
                      "KNOWN_DISCREPANCIES.md"]:
            with open(os.path.join(OUT_DIR, fname), "rb") as f:
                h[fname] = hashlib.md5(f.read()).hexdigest()
        return h

    before = hash_files()
    gen_path = os.path.join(OUT_DIR, "generate_synthetic.py")
    patch_path = os.path.join(OUT_DIR, "patch_phase1_1_tier3.py")
    if os.path.isfile(gen_path) and os.path.isfile(patch_path):
        os.system(f"cd {OUT_DIR} && python3 generate_synthetic.py > /dev/null 2>&1")
        os.system(f"cd {OUT_DIR} && python3 patch_phase1_1_tier3.py > /dev/null 2>&1")
        after = hash_files()
        check(before == after, "Regenerating base dataset + re-applying the Phase 1.1 Tier 3 "
                                "patch did NOT reproduce identical files (pipeline is not "
                                "deterministic)")
    elif not os.path.isfile(gen_path):
        warnings.append("generate_synthetic.py not found — could not verify determinism")
    else:
        warnings.append("patch_phase1_1_tier3.py not found — could not verify full-pipeline "
                         "determinism")

    report()


def report():
    print(f"Checks run. Errors: {len(errors)}, Warnings: {len(warnings)}\n")
    if errors:
        print("FAILURES:")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  ! {w}")
    if not errors:
        print("✓ All validation checks passed.")
    print()
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
