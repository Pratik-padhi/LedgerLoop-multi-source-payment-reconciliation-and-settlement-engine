# LedgerLoop — Phase 4: Tier 2 Deterministic Fuzzy / Tolerance Matching

## 1. Why Tier 2 exists

Tier 1 (`core/match_exact.py`) only resolves transactions where the
reference and amount are **byte-for-byte exact** across sources. That is
deliberately strict — Tier 1's whole job is "match only when the
deterministic evidence is unambiguous." Anything short of exact identity is
handed forward as **residue**, not treated as a failure.

But some of that residue is still safely resolvable without guessing. Two
real, common situations show up in the Phase 1 dataset:

- The bank settled a few paise less than the gateway/ledger recorded
  (`ROUNDING`).
- The bank's copy of the gateway reference was reformatted or truncated
  (`REFERENCE_FORMATTING`).

Both are legitimate, explainable variations of the *same* payment — not
genuine mismatches. Tier 2's job is to recognize these **specific,
pre-approved patterns**, using small, explicit tolerances, and nothing else.

Tier 2 never introduces a similarity score, never uses an LLM, and never
consults `ground_truth.csv` to decide anything. It either finds a single,
well-evidenced candidate, or it leaves the transaction alone.

## 2. What Tier 1 could not solve (and what Tier 2 does about it)

Tier 1 produced 34 residue transactions out of 115. Of those:

| Category | Count | Tier 2 outcome |
|---|---|---|
| `ROUNDING` | 7 | **Matched** — amount tolerance |
| `REFERENCE_FORMATTING` (remaining) | 3 | **Matched** — reference transform + amount tolerance |
| `DUPLICATE_LEDGER_ENTRY` | 3 | Left unresolved — ambiguity is preserved by design |
| `PARTIAL_REFUND` | 4 originals + 4 `-REFUND` rows | Left unresolved — out of approved Phase 4 scope |
| `TAX_LINE_MISMATCH` | 5 | Left unresolved — out of approved Phase 4 scope |
| `NO_BANK_COUNTERPART` | 2 | Left unresolved — no bank row exists at all |
| True orphan (`PAY105`) | 1 | Left unresolved — no counterpart exists |
| Decoy (`PAY107B`) | 1 | Left unresolved — its only candidate was already consumed by Tier 1 |
| Tier-3-designed (`PAY108`–`PAY111`) | 4 | Left unresolved — ambiguous bank credits, split settlement, contradictory amount, or missing structured reference |

Result on the real dataset: **10 matched, 0 ambiguous, 24 unresolved**,
passed forward to Tier 3.

Two categories that a naive reading of `ground_truth.csv` might expect Tier 2
to resolve — `PARTIAL_REFUND` and `TAX_LINE_MISMATCH` — were **deliberately
scoped out** of this phase (see Section 9). Their amount gaps are real,
structural (a refund row or a TDS deduction), not rounding noise, and
resolving them safely needs a different kind of rule (linked-row arithmetic,
not tolerance). That rule was not authorized for Phase 4, so both categories
are passed forward untouched.

## 3. Actual Tier 2 rules

Tier 2 implements exactly **one** composite rule:

```
PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE
```

It fires only when **all** of the following hold for a residue transaction:

1. The transaction already has a Tier-1-established **ledger** match (i.e.
   Tier 1 found gateway+ledger exactly, and only the bank side is missing).
2. Exactly one bank row (not consumed by Tier 1 or already consumed by Tier 2
   this run) has a `bank_reference` that satisfies one of the **explicit**
   reference transforms below.
3. That same bank row's amount is within `AMOUNT_TOLERANCE` of the gateway
   amount.
4. No second candidate satisfies both (2) and (3).

Settlement date is recorded as evidence but never gates the decision (see
Section 4).

## 4. How amount tolerance works

```
AMOUNT_TOLERANCE = INR 0.05  (Decimal, exact)
```

Justification — the actual `ROUNDING` cases in `data/gateway.csv` /
`data/bank.csv`:

| Transaction | Gateway | Bank | Diff |
|---|---|---|---|
| PAY071 | 1212.72 | 1212.67 | 0.05 |
| PAY072 | 4406.56 | 4406.54 | 0.02 |
| PAY073 | 3346.11 | 3346.08 | 0.03 |
| PAY074 | 4589.83 | 4589.80 | 0.03 |
| PAY075 | 1471.42 | 1471.40 | 0.02 |
| PAY076 | 2894.57 | 2894.55 | 0.02 |
| PAY077 | 3006.01 | 3005.96 | 0.05 |

The largest genuine rounding gap observed is **₹0.05** — the tolerance is
set to exactly that, the smallest value that covers every real case. It is
nowhere close to the real `PARTIAL_REFUND` gaps (₹700–₹1700) or
`TAX_LINE_MISMATCH` gaps (₹46–₹112, ~1% of gross), so neither of those is
ever accidentally absorbed.

All amount comparison uses Python's `Decimal(str(...))` on Phase 2's already
2-decimal-normalized floats, never raw binary-float subtraction, to avoid
floating-point artifacts at the boundary.

## 5. How the date window works

```
DATE_WINDOW_DAYS = 2
```

Justified by the real `SETTLEMENT_DELAY` cases (`PAY078`–`PAY085`, 1–2 day
lag) — though in this dataset every one of those cases already resolves at
**Tier 1** (Tier 1 does not gate on date at all, per its own Section 14
rule), so no residue case in this dataset is actually resolved *because of*
the date window.

The date window is retained anyway, as **corroborating evidence only**:

- `evidence["date_difference_days"]` and `evidence["within_date_window"]`
  are recorded on every match.
- A date difference *outside* the window is never, by itself, a reason to
  reject a match that reference + amount tolerance already justify (a test
  covers a 5-day gap that still correctly matches).
- A date difference *inside* the window is never, by itself, a reason to
  accept a match — reference transform + amount tolerance are still both
  required.

## 6. How reference transforms work

Reference transforms are a **closed, explicit set** — not generic
substring/`contains` matching. Each one is named, and each one is only
attempted after Phase 2's `normalize_reference()` has already run (so
whitespace, case, and dash-prefix collapsing have already happened).

| Transform | Example (real dataset) | Meaning |
|---|---|---|
| `IDENTITY` | `GW071` == `GW071` | Reference is already exact; only amount is fuzzy — the `ROUNDING`-case shape |
| `PREFIX_SWAP` | `GW086` gateway ↔ `PAY086` bank | Bank recorded the payment-id-style prefix instead of the gateway-reference-style prefix, same digits |
| (dash-prefix) | `PAY-088` → normalized to `PAY088` by Phase 2 | Collapses into `PREFIX_SWAP` by the time Tier 2 sees it |
| `BARE_NUMERIC` | `GW089` gateway ↔ `089` bank | Bank dropped the prefix entirely, kept only the zero-padded digit suffix |

A reference like `GW094-R` (a refund's `gateway_reference`) is **never**
treated as having a numeric suffix — `_digit_suffix()` requires the
remainder after the prefix to be purely digits, and `"094-R"` is not, so no
transform is even attempted. This is what keeps refunds structurally
protected (see Section 10).

**No transform alone is ever sufficient.** Every transform must additionally
pass amount tolerance and candidate uniqueness before anything is matched
(see the adversarial example in Section 12).

## 7. How ambiguity is handled

If **more than one** available bank candidate satisfies both the reference
transform and the amount tolerance for the same transaction, Tier 2 returns
`AMBIGUOUS` and does **not** pick one — regardless of which candidate is
"closer" in amount or which was listed first.

```json
{
  "status": "AMBIGUOUS",
  "reason": "MULTIPLE_FUZZY_CANDIDATES",
  "matched_records": {"gateway": "...", "bank": null, "ledger": "..."},
  "candidate_records": [ /* every candidate considered, with its own evidence */ ]
}
```

Every candidate that was considered — matched or not — is preserved in
`candidate_records` for audit, never discarded.

On the real dataset, **zero** residue transactions hit this branch, but it
is exercised directly by `tests/test_match_fuzzy.py`
(`TestMultipleCandidatesAmbiguous`) and by an order-independence regression
test, since correctness here must never depend on row processing order.

## 8. One-to-one protection

Tier 2 layers its **own** consumption tracking on top of Tier 1's:

- A bank row Tier 1 already consumed (`ExactMatcher._consumed_bank_row_ids`)
  is never even offered to Tier 2 as a candidate.
- A bank row Tier 2 itself consumes for one transaction is immediately
  removed from the pool for every subsequent transaction in the same run.

This matters concretely for cases like `PAY091`/`PAY092`/`PAY093`: Tier 1
left their bank rows (`B091`, `B092`, `B093`) **unconsumed**, because Tier 1
bailed out due to duplicate-ledger ambiguity before ever reaching
consumption. Tier 2 must be able to see that these bank rows are genuinely
still available in principle — but it never gets the chance to use them,
because those three transactions are ruled ineligible for Tier 2 in the
first place (Section 9).

## 9. Duplicate / refund / TDS protection

**Duplicate ledger (`PAY091`/`092`/`093`):** These are `UNRESOLVED_FOR_TIER_1`
with `reason = MULTIPLE_EXACT_CANDIDATES`. Tier 2's eligibility check
(`_is_eligible_for_tier2`) requires a Tier-1-established ledger match to
already exist — these three have none (Tier 1 refused to pick one of the two
duplicate ledger rows), so they are immediately routed to
`NOT_ELIGIBLE_FOR_TIER_2` and never touched by tolerance/reference logic at
all. The ambiguity Tier 1 correctly preserved is never re-attempted with
looser Tier 2 rules.

**Refunds:** Every `-REFUND` gateway record's `gateway_reference` ends in a
non-numeric suffix (e.g. `GW094-R`), which structurally fails every
reference transform (`IDENTITY` requires exact equality with a real bank
reference; `PREFIX_SWAP`/`BARE_NUMERIC` require a purely-numeric remainder
after `GW`). No refund row can ever satisfy any Tier 2 rule, by
construction — not by a special-cased exclusion, but because the data shape
itself never matches.

**TDS / tax (`TAX_LINE_MISMATCH`):** These have real reference identity
(`GW098` ↔ `PAY098`-style, or already exact) but amount gaps of ₹46–₹112 —
20–2000× the ₹0.05 tolerance. Every one of these five cases correctly falls
into `REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE`: the reference transform
finds the candidate, but the amount gate rejects it. **No TDS-aware rule was
implemented in this phase** (Option B, approved sign-off) — resolving these
safely would require reading `ledger.tax_fields["tds_amount"]` and doing
linked arithmetic, which is a different kind of rule than tolerance
matching, deliberately deferred.

**Partial refunds (`PAY094`–`097`):** Same shape as TDS — real reference
identity, but a genuine ₹700–₹1700 gap (the refunded amount). Same
`REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE` outcome, same deliberate
deferral.

## 10. Why Tier 2 never guesses

Every rejection path in `FuzzyMatcher.resolve()` returns a specific,
named `reason`:

| Reason | Meaning |
|---|---|
| `NOT_ELIGIBLE_FOR_TIER_2` | This residue shape isn't one Tier 2 in this phase attempts at all (no ledger match yet, bank already present, etc.) |
| `NO_REFERENCE_TRANSFORM_MATCH` | No available bank row's reference satisfies any explicit transform |
| `REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE` | A reference-compatible candidate exists, but its amount is outside tolerance |
| `MULTIPLE_FUZZY_CANDIDATES` | More than one candidate satisfies both reference and amount — ambiguous, not resolved |

There is no fallback "pick the closest one" path anywhere in the code.

## 11. What happens to remaining residue

`get_tier2_residue(results)` returns everything with `status != MATCHED` —
`AMBIGUOUS`, and every unresolved/ineligible case. This is not modified,
re-interpreted, or scored further by this module. It is simply passed
forward, exactly as Tier 1's `get_residue()` passed its own residue forward
to Tier 2.

On the real dataset, this is 24 transactions: the 3 duplicate-ledger cases,
8 partial-refund rows (4 originals + 4 `-REFUND` rows), 5 TDS cases, 2
`NO_BANK_COUNTERPART` cases, the true orphan `PAY105`, the decoy `PAY107B`,
and the four Tier-3-designed cases `PAY108`–`PAY111`.

## 12. Why Tier 3 comes next

The remaining 24 residue transactions need something Tier 2 explicitly does
not have: either free-text/contextual reasoning (`PAY108`–`111`, which need
combining a bank description, split-settlement sums, or presence/absence of
other rows), or a distinct linked-field arithmetic rule
(`PARTIAL_REFUND`/`TAX_LINE_MISMATCH`) that was intentionally not authorized
for this phase, or genuine absence of a counterpart that no amount of
matching logic can conjure up (`NO_BANK_COUNTERPART`, `PAY105`, `PAY107B`).

A concrete adversarial example that shows *why* the amount gate matters even
when a reference transform succeeds: bank row `B108` has
`bank_reference = "109"`, which bare-numeric-transforms against gateway
reference `GW109` (belonging to `PAY109`, the split-settlement case). If
amount tolerance were not required *together with* the reference transform,
this could look like a valid match. But `B108`'s amount is ₹2395.50 against
`PAY109`'s ₹6400.00 — nowhere near ₹0.05 — so the amount gate correctly
rejects it, and `PAY109` is passed to Tier 3 for its split-settlement
evidence. This exact scenario is covered by
`TestAdversarialNumericSuffixCollision` in `tests/test_match_fuzzy.py`.

## 13. Final verified state (Phase 4 completion)

```
109 tests passed, 0 failed  (65 original + 44 new)

Tier 2 on real residue:
  Evaluated:  34
  Matched:    10   (all via PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE)
  Ambiguous:   0
  Unresolved: 24   (passed forward to Tier 3)
```

**Note:** This reflects the test baseline at Phase 4 completion. The full project now includes Phase 5 (Tier 3), Phase 5b (Gemini), Phase 6 (Q&A Agent), and Phase 6b (Controller UI), bringing the total to **271 tests, 30 subtests passed, 0 failures**.

Evaluation against ground_truth.csv (post-hoc only):
  False matches:            0
  Missed opportunities:     9 (all PARTIAL_REFUND / TAX_LINE_MISMATCH —
                                explicitly out of approved Phase 4 scope)
  Unexpected missed cases:  0
```

No LLM used. No ground truth used during matching. No Tier 1 result
overwritten. No ambiguous match forced. No source row double-consumed.
Results are deterministic (verified by repeated-run and reversed-order
regression tests).
