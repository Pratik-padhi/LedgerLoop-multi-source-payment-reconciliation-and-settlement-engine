# LedgerLoop — Phase 3: Tier 1 Exact Matching

`core/match_exact.py` consumes the canonical records produced by Phase 2
(`core/normalize.py`) and produces deterministic, explainable exact matches
across Gateway, Bank, and Ledger, plus an explicit residue for everything it
could not confidently resolve.

## Guiding principle

**"Match only when the deterministic evidence is unambiguous."** Tier 1 never
guesses. Anything that isn't a clean, unique, exact match falls through to
the residue for Tier 2 (fuzzy/tolerance matching) to attempt.

## Architectural boundary

**Tier 1 DOES:** exact amount comparison (no tolerance), exact
normalized-reference comparison (no fuzzy/substring/edit-distance), one-to-one
match protection, explicit ambiguity detection, preserve which sources were
actually found, and produce a structured, auditable result per logical
transaction.

**Tier 1 DOES NOT:** apply any tolerance to amount or date, apply any
fuzzy/similarity logic, call an LLM, resolve ambiguity by guessing, create
final exception records, modify Phase 1/Phase 2 data, or consult
`ground_truth.csv` to make any matching decision. Ground truth is used only
by the separate `evaluate_against_ground_truth()` function, called strictly
*after* matching is complete, purely for reporting.

## Eligible reference pairs

Inspecting the actual Phase 1/Phase 2 data (not assumed) established exactly
two eligible cross-source reference comparisons:

| Eligible pair | Why |
|---|---|
| `gateway.transaction_reference` (`payment_id`) ↔ `ledger.transaction_reference` (`payment_reference`) | Same identifier space — 116/116 real ledger rows with a `payment_reference` match some gateway `payment_id` exactly. |
| `gateway.secondary_references["gateway_reference"]` ↔ `bank.secondary_references["bank_reference"]` | The bank's copy of the gateway's own reference — e.g. `bank_reference="GW093"` pairs with `gateway_reference="GW093"`, not with the gateway's `payment_id="PAY093"`. |

**Never compared as equivalent:** `bank_transaction_id` vs anything
gateway/ledger; `utr` vs anything gateway/ledger; any comparison that would
require truncation-awareness, fuzzy matching, or free-text interpretation
(e.g. the bank `description` field). Those are Tier 2/3 concerns.

The logical transaction anchor is always the **gateway `payment_id`** — every
`Tier1Result` is keyed by it. A bank or ledger record with no eligible
reference match to any gateway `payment_id` never becomes part of a
`Tier1Result`'s `matched_records`; see `get_unclaimed_source_records()` for
that gateway-invisible residue (e.g. Phase 1's true bank-only orphan).

## Status taxonomy

| Status | Meaning |
|---|---|
| `MATCHED` | Gateway + Bank + Ledger all found via exact reference + exact amount. |
| `PARTIAL_MATCH` | Exactly 2 of the 3 sources found, unambiguously, via exact reference + exact amount. Real, useful evidence — never silently treated as a complete 3-source match. |
| `UNRESOLVED_FOR_TIER_1` | Ambiguous (multiple exact candidates) or no eligible candidate at all. |

`get_residue()` returns everything that is *not* `MATCHED` — both
`PARTIAL_MATCH` and `UNRESOLVED_FOR_TIER_1` — since Tier 1's job is confident
3-source resolution; anything short of that is handed to Tier 2. This is
residue, **not** a final exception queue (Section 16) — "Tier 1 could not
resolve this" is not the same claim as "this transaction is broken."

## Rules

| Rule | Fires when |
|---|---|
| `EXACT_REFERENCE_AND_AMOUNT` | A unique exact-reference, exact-amount ledger match was found (gateway+ledger, optionally +bank). |
| `EXACT_GATEWAY_REFERENCE_AND_AMOUNT` | A unique exact-reference, exact-amount bank match was found, but no ledger match (gateway+bank only). |

## Reasons (populated when `status != MATCHED`)

| Reason | Meaning |
|---|---|
| `MULTIPLE_EXACT_CANDIDATES` | More than one bank and/or ledger row exactly matches this gateway record's reference+amount (e.g. Phase 1's deliberate `DUPLICATE_LEDGER_ENTRY` cases). Never resolved by picking one. |
| `NO_EXACT_CANDIDATE` | A gateway reference exists, but no bank/ledger row exactly matches it. |
| `GATEWAY_ONLY` | The gateway record itself has no usable reference to look anything up with. |
| `CONTENDED_BY_ANOTHER_GATEWAY_RECORD` | See "Order-independence of ambiguity detection" below — a candidate exists, but a *different* gateway record's reference maps to the exact same candidate, so neither may claim it via Tier 1. |

## Order-independence of ambiguity detection

A subtler one-to-one hazard than "one bank row, two ledger rows" (Section
10/11) is two *different* gateway records competing for the *same* bank or
ledger candidate (e.g. a gateway-side data-quality issue producing a
duplicate `gateway_reference`). If ambiguity were checked only against the
currently-available candidate pool at the moment each gateway record is
processed, the first-processed record would silently "win" the shared
candidate and look like a confident, unambiguous match — while the
second-processed one would incorrectly report "no candidate at all" instead
of "a candidate existed but was already claimed by an equally valid
competitor." That would be exactly the "confidently wrong" failure mode
Section 20 warns against, and it would make Tier 1's *correctness* silently
depend on incidental CSV row order (even though its mechanical output would
still be deterministic).

To prevent this, `ExactMatcher` computes contention as a **global,
order-independent property at construction time**: for each bank/ledger
reference key, if more than one gateway record's own reference maps to it,
every one of those gateway records is routed to `UNRESOLVED_FOR_TIER_1` /
`CONTENDED_BY_ANOTHER_GATEWAY_RECORD` up front — none of them silently
consumes the shared candidate, regardless of processing order. (This
scenario does not occur in the real Phase 1 dataset — every `gateway_reference`
is unique — but the protection exists because the spec requires it and
because relying on "it doesn't happen in this dataset" would be fragile.)

## Settlement date (Section 14)

Tier 1 does **not** require the gateway `payment_date` and bank date to be
identical for a match to fire. If reference + amount are exact, a date
difference does not block the match — it is preserved as evidence
(`evidence["date_difference_days"]`) for the audit trail, but never gates the
decision. This means Phase 1's `SETTLEMENT_DELAY` cases (which Phase 1's own
ground truth expects to resolve via `TIER_2`) actually resolve at Tier 1 in
practice, since their reference and amount are both exact — see "Measured
Tier 1 performance" below. This is documented, spec-compliant behavior per
Section 14 ("do not require... if that would incorrectly prevent legitimate
matching"), not a bug.

## Amount and reference comparison

- **Amount:** exact equality only (`a.amount.normalized == b.amount.normalized`).
  No tolerance, no re-rounding beyond what Phase 2 already standardized.
  `500.00 == 500.00` but `500.00 != 499.99` and `500.00 != 500.01`.
- **Reference:** exact equality of Phase 2's *normalized* reference only. No
  substring matching, no edit distance, no fuzzy similarity. If Phase 2
  conservatively normalized `PAY-123456` → `PAY123456`, those normalized
  forms may be compared — but `PAY123456` and `PAY123457` never match.

## Measured Tier 1 performance (real Phase 1/1.1 dataset, 115 gateway records / 111 ground-truth logical transactions)

| Metric | Value |
|---|---|
| Total logical transactions processed | 115 |
| MATCHED (all 3 sources, exact) | 81 |
| PARTIAL_MATCH (2 of 3, exact) | 29 |
| UNRESOLVED_FOR_TIER_1 | 5 |
| Tier 1 match percentage | 70.43% |
| Residue size (→ Tier 2) | 34 |
| Ground truth: expected TIER_1 matches | 70 |
| Ground truth: correctly matched at Tier 1 | 70 (100%) |
| Missed Tier 1 opportunities | 0 |
| "False matches" (Tier 1 matched, ground truth expected TIER_2/3) | 11 — see below, all documented/expected |
| Correctly deferred to later tiers | 30 |

### The 11 "false matches" are expected, documented outcomes, not bugs

| Cases | Ground truth category | Why Tier 1 legitimately matches them anyway |
|---|---|---|
| PAY078–PAY085 (8 cases) | `SETTLEMENT_DELAY` | Reference and amount are exact; only the *date* differs. Per Section 14, Tier 1 must not gate on date, so these correctly resolve here rather than waiting for Tier 2. |
| PAY087, PAY090 (2 cases) | `REFERENCE_FORMATTING` | Phase 1 intended these as truncation/formatting cases, but the actual generated values for these two happen to already be identical strings in both sources (a Phase 1 dataset labeling nuance, documented in `KNOWN_DISCREPANCIES.md`) — so they are genuinely exact matches, not fuzzy ones. |
| PAY107 (1 case) | `LLM_AMBIGUOUS_MATCH` (Tier 3) | Designed as an ambiguous-reference case against decoy `PAY107B`, but `GW107` and `GW107B` are distinct normalized strings — there is no exact-match ambiguity, only a *conceptual* one a fuzzy/LLM tier would need to reason about. Verified: PAY107's bank/ledger candidates are unique and unambiguous at the exact-match level. |

None of these represent Tier 1 forcing an incorrect match, applying a
tolerance, or resolving genuine ambiguity — in each case the deterministic
evidence really was unambiguous; the *ground truth's* Tier assignment
reflected Phase 1's design intent for the discrepancy type, not a claim that
exact-match evidence was insufficient for that specific generated row.

## Files

| File | Purpose |
|---|---|
| `core/match_exact.py` | Tier 1 matching module. |
| `tests/test_match_exact.py` | 34 tests: 12 required cases (Section 19) + adversarial safety (Section 20, including an order-independence regression test) + integration tests against real Phase 1/1.1 data. |
| `scripts/run_tier1_demo.py` | Report/inspection script — prints a human-readable summary and writes `data/tier1/*.json`. |
| `data/tier1/*.json` | Generated output of the above script. |

## How to run

```bash
# Run the test suite
python3 -m unittest tests.test_match_exact -v

# Generate the human-readable report + inspectable JSON output
python3 scripts/run_tier1_demo.py
```
