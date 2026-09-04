# KNOWN_DISCREPANCIES.md

This file documents every deliberately injected discrepancy in the LedgerLoop
Phase 1 synthetic dataset. Each entry is traceable to specific source rows via
their `source_row_id` (e.g. G001, B002, L003).

Total logical transactions: 106
Random seed: 42

---

## PAY071 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY071-ROUNDING`

**Gateway:** ₹1212.72 on 2026-08-20 (G071)

**Bank:** ₹1212.67 on 2026-08-20 (B071)

**Ledger:** ₹1212.72 on 2026-08-20 (L071)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.05 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment, not a genuine mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.05 | **Date difference:** 0 days

---

## PAY072 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY072-ROUNDING`

**Gateway:** ₹4406.56 on 2026-08-20 (G072)

**Bank:** ₹4406.54 on 2026-08-20 (B072)

**Ledger:** ₹4406.56 on 2026-08-20 (L072)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.02 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment, not a genuine mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.02 | **Date difference:** 0 days

---

## PAY073 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY073-ROUNDING`

**Gateway:** ₹3346.11 on 2026-08-20 (G073)

**Bank:** ₹3346.08 on 2026-08-20 (B073)

**Ledger:** ₹3346.11 on 2026-08-20 (L073)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.03 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment, not a genuine mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.03 | **Date difference:** 0 days

---

## PAY074 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY074-ROUNDING`

**Gateway:** ₹4589.83 on 2026-08-20 (G074)

**Bank:** ₹4589.80 on 2026-08-20 (B074)

**Ledger:** ₹4589.83 on 2026-08-20 (L074)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.03 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment, not a genuine mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.03 | **Date difference:** 0 days

---

## PAY075 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY075-ROUNDING`

**Gateway:** ₹1471.42 on 2026-08-20 (G075)

**Bank:** ₹1471.40 on 2026-08-20 (B075)

**Ledger:** ₹1471.42 on 2026-08-20 (L075)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.02 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment, not a genuine mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.02 | **Date difference:** 0 days

---

## PAY076 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY076-ROUNDING`

**Gateway:** ₹2894.57 on 2026-08-20 (G076)

**Bank:** ₹2894.55 on 2026-08-20 (B076)

**Ledger:** ₹2894.57 on 2026-08-20 (L076)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.02 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment, not a genuine mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.02 | **Date difference:** 0 days

---

## PAY077 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY077-ROUNDING`

**Gateway:** ₹3006.01 on 2026-08-20 (G077)

**Bank:** ₹3005.96 on 2026-08-20 (B077)

**Ledger:** ₹3006.01 on 2026-08-20 (L077)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.05 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment, not a genuine mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.05 | **Date difference:** 0 days

---

## PAY078 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY078-TIMING`

**Gateway:** ₹3315.32 on 2026-08-20 (G078)

**Bank:** ₹3315.32 on 2026-08-21 (B078)

**Ledger:** ₹3315.32 on 2026-08-20 (L078)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY079 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY079-TIMING`

**Gateway:** ₹7979.14 on 2026-08-20 (G079)

**Bank:** ₹7979.14 on 2026-08-21 (B079)

**Ledger:** ₹7979.14 on 2026-08-20 (L079)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY080 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY080-TIMING`

**Gateway:** ₹4174.31 on 2026-08-20 (G080)

**Bank:** ₹4174.31 on 2026-08-21 (B080)

**Ledger:** ₹4174.31 on 2026-08-20 (L080)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY081 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY081-TIMING`

**Gateway:** ₹6095.10 on 2026-08-20 (G081)

**Bank:** ₹6095.10 on 2026-08-21 (B081)

**Ledger:** ₹6095.10 on 2026-08-20 (L081)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY082 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY082-TIMING`

**Gateway:** ₹1392.16 on 2026-08-20 (G082)

**Bank:** ₹1392.16 on 2026-08-21 (B082)

**Ledger:** ₹1392.16 on 2026-08-20 (L082)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY083 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY083-TIMING`

**Gateway:** ₹6378.22 on 2026-08-20 (G083)

**Bank:** ₹6378.22 on 2026-08-22 (B083)

**Ledger:** ₹6378.22 on 2026-08-20 (L083)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 2 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 2 day(s)

---

## PAY084 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY084-TIMING`

**Gateway:** ₹4851.99 on 2026-08-20 (G084)

**Bank:** ₹4851.99 on 2026-08-22 (B084)

**Ledger:** ₹4851.99 on 2026-08-20 (L084)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 2 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 2 day(s)

---

## PAY085 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY085-TIMING`

**Gateway:** ₹3176.63 on 2026-08-20 (G085)

**Bank:** ₹3176.63 on 2026-08-22 (B085)

**Ledger:** ₹3176.63 on 2026-08-20 (L085)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 2 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 2 day(s)

---

## PAY086 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY086-REFFMT`

**Gateway:** gateway_reference = GW086 (G086)

**Bank:** bank_reference = PAY086 (B086)

**Ledger:** payment_reference = PAY086 (L086)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('truncate6' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY087 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY087-REFFMT`

**Gateway:** gateway_reference = GW087 (G087)

**Bank:** bank_reference = GW087 (B087)

**Ledger:** payment_reference = PAY087 (L087)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('truncate_full_id' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY088 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY088-REFFMT`

**Gateway:** gateway_reference = GW088 (G088)

**Bank:** bank_reference = PAY-088 (B088)

**Ledger:** payment_reference = PAY088 (L088)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('dash_prefix' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY089 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY089-REFFMT`

**Gateway:** gateway_reference = GW089 (G089)

**Bank:** bank_reference = 089 (B089)

**Ledger:** payment_reference = PAY089 (L089)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('no_prefix' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY090 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY090-REFFMT`

**Gateway:** gateway_reference = GW090 (G090)

**Bank:** bank_reference = gw090 (B090)

**Ledger:** payment_reference = PAY090 (L090)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('lowercase' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY091 — Duplicate Ledger Entry

**Discrepancy ID:** `DISC-PAY091-DUPLICATE`

**Gateway:** ₹2885.99, single row (G091)

**Bank:** ₹2885.99, single settlement (B091)

**Ledger:** ₹2885.99 recorded TWICE (L091, L092) referencing the same PAY091

**Expected outcome:** EXCEPTION — DUPLICATE_LEDGER_ENTRY (only one settlement exists; the second ledger row must not be counted as a separate settled transaction)

**Why this is correct:** The merchant ledger accidentally recorded the same sale twice. There is only one gateway payment and one bank settlement, so the second ledger row is a duplicate that must be flagged, not treated as an unmatched extra transaction.

**Matching tier:** TIER_2

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY092 — Duplicate Ledger Entry

**Discrepancy ID:** `DISC-PAY092-DUPLICATE`

**Gateway:** ₹2379.40, single row (G092)

**Bank:** ₹2379.40, single settlement (B092)

**Ledger:** ₹2379.40 recorded TWICE (L093, L094) referencing the same PAY092

**Expected outcome:** EXCEPTION — DUPLICATE_LEDGER_ENTRY (only one settlement exists; the second ledger row must not be counted as a separate settled transaction)

**Why this is correct:** The merchant ledger accidentally recorded the same sale twice. There is only one gateway payment and one bank settlement, so the second ledger row is a duplicate that must be flagged, not treated as an unmatched extra transaction.

**Matching tier:** TIER_2

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY093 — Duplicate Ledger Entry

**Discrepancy ID:** `DISC-PAY093-DUPLICATE`

**Gateway:** ₹1433.89, single row (G093)

**Bank:** ₹1433.89, single settlement (B093)

**Ledger:** ₹1433.89 recorded TWICE (L095, L096) referencing the same PAY093

**Expected outcome:** EXCEPTION — DUPLICATE_LEDGER_ENTRY (only one settlement exists; the second ledger row must not be counted as a separate settled transaction)

**Why this is correct:** The merchant ledger accidentally recorded the same sale twice. There is only one gateway payment and one bank settlement, so the second ledger row is a duplicate that must be flagged, not treated as an unmatched extra transaction.

**Matching tier:** TIER_2

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY094 — Partial Refund

**Discrepancy ID:** `DISC-PAY094-REFUND`

**Gateway:** Original ₹5845.77 (G094) + Refund -₹1699.73 as PAY094-REFUND (G095)

**Bank:** Net settlement ₹4146.04 (B094)

**Ledger:** Original ₹5845.77 (L097) + Refund -₹1699.73 as PAY094-REFUND (L098)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹1699.73 was refunded, so bank settled the net ₹4146.04. Both gateway and ledger carry an explicit linked refund row, distinguishing this from an unexplained amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 1699.73 | **Date difference:** 0 days

---

## PAY095 — Partial Refund

**Discrepancy ID:** `DISC-PAY095-REFUND`

**Gateway:** Original ₹2669.31 (G096) + Refund -₹734.52 as PAY095-REFUND (G097)

**Bank:** Net settlement ₹1934.79 (B095)

**Ledger:** Original ₹2669.31 (L099) + Refund -₹734.52 as PAY095-REFUND (L100)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹734.52 was refunded, so bank settled the net ₹1934.79. Both gateway and ledger carry an explicit linked refund row, distinguishing this from an unexplained amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 734.52 | **Date difference:** 0 days

---

## PAY096 — Partial Refund

**Discrepancy ID:** `DISC-PAY096-REFUND`

**Gateway:** Original ₹4608.59 (G098) + Refund -₹703.63 as PAY096-REFUND (G099)

**Bank:** Net settlement ₹3904.96 (B096)

**Ledger:** Original ₹4608.59 (L101) + Refund -₹703.63 as PAY096-REFUND (L102)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹703.63 was refunded, so bank settled the net ₹3904.96. Both gateway and ledger carry an explicit linked refund row, distinguishing this from an unexplained amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 703.63 | **Date difference:** 0 days

---

## PAY097 — Partial Refund

**Discrepancy ID:** `DISC-PAY097-REFUND`

**Gateway:** Original ₹4722.34 (G100) + Refund -₹945.02 as PAY097-REFUND (G101)

**Bank:** Net settlement ₹3777.32 (B097)

**Ledger:** Original ₹4722.34 (L103) + Refund -₹945.02 as PAY097-REFUND (L104)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹945.02 was refunded, so bank settled the net ₹3777.32. Both gateway and ledger carry an explicit linked refund row, distinguishing this from an unexplained amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 945.02 | **Date difference:** 0 days

---

## PAY098 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY098-TDS`

**Gateway:** ₹4607.87 gross (G102)

**Bank:** ₹4561.79 net of TDS (B098)

**Ledger:** ₹4607.87 gross, tds_amount = ₹46.08 (L105)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹46.08 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 46.08 | **Date difference:** 0 days

---

## PAY099 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY099-TDS`

**Gateway:** ₹11213.65 gross (G103)

**Bank:** ₹11101.51 net of TDS (B099)

**Ledger:** ₹11213.65 gross, tds_amount = ₹112.14 (L106)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹112.14 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 112.14 | **Date difference:** 0 days

---

## PAY100 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY100-TDS`

**Gateway:** ₹10834.67 gross (G104)

**Bank:** ₹10726.32 net of TDS (B100)

**Ledger:** ₹10834.67 gross, tds_amount = ₹108.35 (L107)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹108.35 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 108.35 | **Date difference:** 0 days

---

## PAY101 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY101-TDS`

**Gateway:** ₹5686.00 gross (G105)

**Bank:** ₹5629.14 net of TDS (B101)

**Ledger:** ₹5686.00 gross, tds_amount = ₹56.86 (L108)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹56.86 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 56.86 | **Date difference:** 0 days

---

## PAY102 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY102-TDS`

**Gateway:** ₹8750.55 gross (G106)

**Bank:** ₹8663.04 net of TDS (B102)

**Ledger:** ₹8750.55 gross, tds_amount = ₹87.51 (L109)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹87.51 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 87.51 | **Date difference:** 0 days

---

## PAY103 — Missing Bank Counterpart

**Discrepancy ID:** `DISC-PAY103-NOBANK`

**Gateway:** ₹2631.40 on 2026-08-20 (G107)

**Bank:** No corresponding row exists in bank.csv

**Ledger:** ₹2631.40 on 2026-08-20 (L110)

**Expected outcome:** EXCEPTION — NO_BANK_COUNTERPART (unresolved, goes to exception queue)

**Why this is correct:** The payment exists in both the gateway export and the merchant ledger, but no matching settlement was ever found in the bank statement. The system must NOT invent or assume a settlement; this must surface as an unresolved item.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY104 — Missing Bank Counterpart

**Discrepancy ID:** `DISC-PAY104-NOBANK`

**Gateway:** ₹1034.94 on 2026-08-20 (G108)

**Bank:** No corresponding row exists in bank.csv

**Ledger:** ₹1034.94 on 2026-08-20 (L111)

**Expected outcome:** EXCEPTION — NO_BANK_COUNTERPART (unresolved, goes to exception queue)

**Why this is correct:** The payment exists in both the gateway export and the merchant ledger, but no matching settlement was ever found in the bank statement. The system must NOT invent or assume a settlement; this must surface as an unresolved item.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY105 — True Orphan (UNMATCHED_GATEWAY_TRANSACTION)

**Discrepancy ID:** `DISC-PAY105-ORPHAN`

**Gateway:** YES (G109)

**Bank:** No counterpart

**Ledger:** No counterpart

**Expected outcome:** EXCEPTION — UNMATCHED_GATEWAY_TRANSACTION (unresolved, goes to exception queue)

**Why this is correct:** This transaction exists in exactly one source (Gateway Only) with no counterpart in either of the other two sources. It must be kept distinct from NO_BANK_COUNTERPART, which requires presence in two sources.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY106 — True Orphan (UNMATCHED_BANK_TRANSACTION)

**Discrepancy ID:** `DISC-PAY106-ORPHAN`

**Gateway:** No counterpart

**Bank:** YES (B103)

**Ledger:** No counterpart

**Expected outcome:** EXCEPTION — UNMATCHED_BANK_TRANSACTION (unresolved, goes to exception queue)

**Why this is correct:** This transaction exists in exactly one source (Bank Only) with no counterpart in either of the other two sources. It must be kept distinct from NO_BANK_COUNTERPART, which requires presence in two sources.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

# Phase 1.1 Addendum — Tier 3 (LLM Adjudication) Ambiguous Cases

The cases below were added in Phase 1.1 to provide genuine Tier 3 test coverage. They were appended to the existing dataset without modifying any prior transaction. Two categories are used:

- **LLM_AMBIGUOUS_MATCH** — sufficient evidence exists to confidently resolve the transaction, but only by combining multiple weak/partial signals together; no single deterministic Tier 1/Tier 2 rule can resolve it alone.
- **LLM_NEEDS_HUMAN** — evidence is genuinely insufficient or contradictory; the correct behavior is for the LLM to decline to guess and route the case to a human reviewer rather than being forced into a match.

---

## PAY107 — Ambiguous Reference Shared by Two Candidates (Resolvable via Multiple Evidence)

**Discrepancy ID:** `DISC-PAY107-LLM-MULTIEVIDENCE`

**Gateway:** PAY107: ₹3120.50, gateway_reference=GW107, customer_reference=ORD210-A (G110)  
PAY107B: ₹3120.50, gateway_reference=GW107B, customer_reference=ORD210-B (G111)

**Bank:** ₹3120.50 credit, bank_reference=GW107 (truncated — matches both gateway references equally), description mentions 'ORD210-A' (B104)

**Ledger:** PAY107: ₹3120.50, payment_reference=PAY107, invoice_reference=ORD210-A (L112). No ledger entry exists for PAY107B in this batch.

**Expected outcome:** MATCHED to PAY107 via TIER_3 LLM adjudication — LLM_AMBIGUOUS_MATCH

**Why this is correct:** Amount and truncated bank_reference alone cannot distinguish PAY107 from PAY107B (both same amount, both same-day, both plausible owners of 'GW107'). Exact matching fails (reference is ambiguous) and tolerance/fuzzy rules fail (two equally-scoring candidates by reference alone). Resolution requires combining THREE signals together: (1) the bank description's fuller 'ORD210-A' fragment, (2) the fact that only PAY107 has a ledger counterpart in this batch, and (3) the exact amount match. No single deterministic rule covers this; it is a legitimate Tier 3 case.

**Matching tier:** TIER_3 (LLM adjudication)

**Remains an exception:** No (resolved)

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY108 — Two Equally Plausible Bank Credits (Genuinely Unresolved)

**Discrepancy ID:** `DISC-PAY108-LLM-NEEDSHUMAN`

**Gateway:** ₹1875.00, gateway_reference=GW108, customer_reference=ORD225 (G112)

**Bank:** TWO unlabeled NEFT credits of ₹1875.00 each, same date, neither carrying any reference back to GW108 or ORD225 (B105, B106)

**Ledger:** ₹1875.00, payment_reference=PAY108 (L113)

**Expected outcome:** NOT auto-matched — TIER_3 LLM adjudication should return LLM_NEEDS_HUMAN

**Why this is correct:** There is no evidence anywhere (reference, description, timing, sequencing) that distinguishes which of the two identical-amount bank credits belongs to PAY108. Picking either one would be a coin flip presented as a confident match. This is a deliberate case where the correct behavior is for the LLM to decline to guess and route to a human reviewer, rather than being forced to pick one.

**Matching tier:** TIER_3 (LLM adjudication)

**Remains an exception:** Yes (NEEDS_HUMAN)

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY109 — Split Settlement Across Two Bank Credits (Resolvable via Multiple Evidence)

**Discrepancy ID:** `DISC-PAY109-LLM-SPLITSETTLEMENT`

**Gateway:** ₹6400.00 single payment, gateway_reference=GW109, customer_reference=ORD240 (G113)

**Bank:** TWO credits: ₹4000.00 on 2026-08-20 referencing 'GW109' and explicitly labeled 'Partial settlement 1 of 2 ORD240' (B107); ₹2395.50 on 2026-08-21 referencing only '109' with generic description (B108). Combined sum ₹6395.50 is ₹4.50 short of the gateway amount.

**Ledger:** ₹6400.00, payment_reference=PAY109 (L114)

**Expected outcome:** MATCHED (as a split settlement) via TIER_3 LLM adjudication — LLM_AMBIGUOUS_MATCH

**Why this is correct:** No single bank row matches the gateway amount, so exact matching fails outright. Tolerance rules fail too: neither individual bank amount is within a normal rounding tolerance of ₹6400.00, and the combined sum still leaves an unexplained ₹4.50 gap (larger than the dataset's typical rounding tolerance, so Tier 2 should not silently absorb it). Resolving this requires combining THREE weak signals: the explicit '1 of 2 ORD240' description on the first credit, the numeric fragment '109' on the second, and the near-equality of their sum to the gateway amount across two consecutive dates. This is a legitimate Tier 3 case — a human or LLM adjudicator would reasonably conclude this is a split settlement with a small unexplained residual, not two separate unrelated transactions.

**Matching tier:** TIER_3 (LLM adjudication)

**Remains an exception:** No (resolved, with residual flagged)

**Amount difference:** 4.50 | **Date difference:** 0-1 day(s) across the two credits

---

## PAY110 — Perfect Reference Match, Unexplained Amount Conflict (Genuinely Unresolved)

**Discrepancy ID:** `DISC-PAY110-LLM-NEEDSHUMAN`

**Gateway:** ₹5000.00, gateway_reference=GW110 (G114)

**Bank:** ₹5000.00, bank_reference=GW110 — agrees exactly with gateway (B109)

**Ledger:** ₹4550.00, payment_reference=PAY110 (exact reference match) but ₹450.00 short of gateway/bank, with tax_amount and tds_amount both 0.00 — nothing in the ledger explains the gap (L115)

**Expected outcome:** NOT auto-matched — TIER_3 LLM adjudication should return LLM_NEEDS_HUMAN

**Why this is correct:** The reference linkage is unambiguous (gateway, bank, and ledger all cite the same payment), so this is not a reference-ambiguity case. But the amount gap (₹450.00) is too large for Tier 2 rounding tolerance, and no refund, tax, or TDS field explains it — unlike the documented PARTIAL_REFUND and TAX_LINE_MISMATCH cases, which carry explicit supporting fields. This is a genuine conflict between strong identity evidence and irreconcilable amount evidence. Forcing a match would hide a possible ledger data-entry error or an undisclosed deduction; the correct behavior is to flag it for a human to investigate rather than have the LLM guess whether it's benign.

**Matching tier:** TIER_3 (LLM adjudication)

**Remains an exception:** Yes (NEEDS_HUMAN)

**Amount difference:** 450.00 | **Date difference:** 0 days

---

## PAY111 — Missing Bank Reference, Identifiable via Free-Text Description

**Discrepancy ID:** `DISC-PAY111-LLM-TEXTUALEVIDENCE`

**Gateway:** ₹2260.75, gateway_reference=GW111, customer_reference=ORD270 (G115)

**Bank:** ₹2260.75, bank_reference is BLANK, but description reads 'Payment received for ORD270' (B110)

**Ledger:** ₹2260.75, payment_reference=PAY111, invoice_reference=ORD270 (L116)

**Expected outcome:** MATCHED via TIER_3 LLM adjudication — LLM_AMBIGUOUS_MATCH

**Why this is correct:** The structured bank_reference field — which every deterministic Tier 1/Tier 2 rule relies on — is empty, so exact and fuzzy reference matching have no field to operate on. The only link between the bank row and the payment is unstructured free text ('ORD270') that happens to match the ledger's invoice_reference and the gateway's customer_reference. Interpreting free-text descriptions is a natural-language task outside deterministic rule matching, making this a legitimate Tier 3 case that a rule-based Tier 2 pass would likely leave unmatched even though sufficient evidence exists to resolve it confidently.

**Matching tier:** TIER_3 (LLM adjudication)

**Remains an exception:** No (resolved)

**Amount difference:** 0.00 | **Date difference:** 0 days

---
