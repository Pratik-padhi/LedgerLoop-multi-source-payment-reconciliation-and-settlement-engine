# KNOWN_DISCREPANCIES.md (data_large — expanded 250+ transaction dataset)

This file documents every deliberately injected discrepancy in the LedgerLoop
expanded Phase 1 dataset (250+ logical transactions). Each entry is traceable
to specific source rows via their `source_row_id` (e.g. G001, B002, L003).

Total logical transactions: 250
Random seed: 42
Dataset directory: data_large/ (data/ is the canonical 111-txn set for deployment)

---

## PAY131 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY131-ROUNDING`

**Gateway:** ₹1676.07 on 2026-08-20 (G131)

**Bank:** ₹1676.06 on 2026-08-20 (B131)

**Ledger:** ₹1676.07 on 2026-08-20 (L131)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.01 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.01 | **Date difference:** 0 days

---

## PAY132 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY132-ROUNDING`

**Gateway:** ₹4414.45 on 2026-08-20 (G132)

**Bank:** ₹4414.40 on 2026-08-20 (B132)

**Ledger:** ₹4414.45 on 2026-08-20 (L132)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.05 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.05 | **Date difference:** 0 days

---

## PAY133 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY133-ROUNDING`

**Gateway:** ₹611.14 on 2026-08-20 (G133)

**Bank:** ₹611.11 on 2026-08-20 (B133)

**Ledger:** ₹611.14 on 2026-08-20 (L133)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.03 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.03 | **Date difference:** 0 days

---

## PAY134 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY134-ROUNDING`

**Gateway:** ₹532.22 on 2026-08-20 (G134)

**Bank:** ₹532.18 on 2026-08-20 (B134)

**Ledger:** ₹532.22 on 2026-08-20 (L134)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.04 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.04 | **Date difference:** 0 days

---

## PAY135 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY135-ROUNDING`

**Gateway:** ₹3876.01 on 2026-08-20 (G135)

**Bank:** ₹3875.99 on 2026-08-20 (B135)

**Ledger:** ₹3876.01 on 2026-08-20 (L135)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.02 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.02 | **Date difference:** 0 days

---

## PAY136 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY136-ROUNDING`

**Gateway:** ₹2481.36 on 2026-08-20 (G136)

**Bank:** ₹2481.33 on 2026-08-20 (B136)

**Ledger:** ₹2481.36 on 2026-08-20 (L136)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.03 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.03 | **Date difference:** 0 days

---

## PAY137 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY137-ROUNDING`

**Gateway:** ₹1472.27 on 2026-08-20 (G137)

**Bank:** ₹1472.23 on 2026-08-20 (B137)

**Ledger:** ₹1472.27 on 2026-08-20 (L137)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.04 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.04 | **Date difference:** 0 days

---

## PAY138 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY138-ROUNDING`

**Gateway:** ₹2231.06 on 2026-08-20 (G138)

**Bank:** ₹2231.04 on 2026-08-20 (B138)

**Ledger:** ₹2231.06 on 2026-08-20 (L138)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.02 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.02 | **Date difference:** 0 days

---

## PAY139 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY139-ROUNDING`

**Gateway:** ₹2788.62 on 2026-08-20 (G139)

**Bank:** ₹2788.58 on 2026-08-20 (B139)

**Ledger:** ₹2788.62 on 2026-08-20 (L139)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.04 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.04 | **Date difference:** 0 days

---

## PAY140 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY140-ROUNDING`

**Gateway:** ₹1165.53 on 2026-08-20 (G140)

**Bank:** ₹1165.51 on 2026-08-20 (B140)

**Ledger:** ₹1165.53 on 2026-08-20 (L140)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.02 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.02 | **Date difference:** 0 days

---

## PAY141 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY141-ROUNDING`

**Gateway:** ₹4976.72 on 2026-08-20 (G141)

**Bank:** ₹4976.68 on 2026-08-20 (B141)

**Ledger:** ₹4976.72 on 2026-08-20 (L141)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.04 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.04 | **Date difference:** 0 days

---

## PAY142 — Rounding / Small Amount Difference

**Discrepancy ID:** `DISC-PAY142-ROUNDING`

**Gateway:** ₹2302.88 on 2026-08-20 (G142)

**Bank:** ₹2302.85 on 2026-08-20 (B142)

**Ledger:** ₹2302.88 on 2026-08-20 (L142)

**Expected outcome:** MATCHED via TIER_2 (tolerance match)

**Why this is correct:** Bank settled ₹0.03 less than gateway/ledger recorded. This is within tolerance and represents the same underlying payment.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.03 | **Date difference:** 0 days

---

## PAY143 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY143-TIMING`

**Gateway:** ₹1143.83 on 2026-08-20 (G143)

**Bank:** ₹1143.83 on 2026-08-21 (B143)

**Ledger:** ₹1143.83 on 2026-08-20 (L143)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY144 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY144-TIMING`

**Gateway:** ₹699.40 on 2026-08-20 (G144)

**Bank:** ₹699.40 on 2026-08-21 (B144)

**Ledger:** ₹699.40 on 2026-08-20 (L144)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY145 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY145-TIMING`

**Gateway:** ₹4788.81 on 2026-08-20 (G145)

**Bank:** ₹4788.81 on 2026-08-21 (B145)

**Ledger:** ₹4788.81 on 2026-08-20 (L145)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY146 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY146-TIMING`

**Gateway:** ₹4789.83 on 2026-08-20 (G146)

**Bank:** ₹4789.83 on 2026-08-21 (B146)

**Ledger:** ₹4789.83 on 2026-08-20 (L146)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY147 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY147-TIMING`

**Gateway:** ₹753.75 on 2026-08-20 (G147)

**Bank:** ₹753.75 on 2026-08-21 (B147)

**Ledger:** ₹753.75 on 2026-08-20 (L147)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY148 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY148-TIMING`

**Gateway:** ₹1985.75 on 2026-08-20 (G148)

**Bank:** ₹1985.75 on 2026-08-21 (B148)

**Ledger:** ₹1985.75 on 2026-08-20 (L148)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY149 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY149-TIMING`

**Gateway:** ₹6905.16 on 2026-08-20 (G149)

**Bank:** ₹6905.16 on 2026-08-21 (B149)

**Ledger:** ₹6905.16 on 2026-08-20 (L149)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY150 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY150-TIMING`

**Gateway:** ₹4210.42 on 2026-08-20 (G150)

**Bank:** ₹4210.42 on 2026-08-22 (B150)

**Ledger:** ₹4210.42 on 2026-08-20 (L150)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 2 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 2 day(s)

---

## PAY151 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY151-TIMING`

**Gateway:** ₹5418.03 on 2026-08-20 (G151)

**Bank:** ₹5418.03 on 2026-08-21 (B151)

**Ledger:** ₹5418.03 on 2026-08-20 (L151)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 1 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 1 day(s)

---

## PAY152 — Settlement Timing Drift

**Discrepancy ID:** `DISC-PAY152-TIMING`

**Gateway:** ₹4406.02 on 2026-08-20 (G152)

**Bank:** ₹4406.02 on 2026-08-22 (B152)

**Ledger:** ₹4406.02 on 2026-08-20 (L152)

**Expected outcome:** MATCHED via TIER_2 (date-window match)

**Why this is correct:** Bank settlement occurred 2 day(s) after the payment/ledger date. This is legitimate settlement lag, not an error.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 2 day(s)

---

## PAY153 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY153-REFFMT`

**Gateway:** gateway_reference = GW153 (G153)

**Bank:** bank_reference = PAY153 (B153)

**Ledger:** payment_reference = PAY153 (L153)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('truncate6' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY154 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY154-REFFMT`

**Gateway:** gateway_reference = GW154 (G154)

**Bank:** bank_reference = GW154 (B154)

**Ledger:** payment_reference = PAY154 (L154)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('truncate_full_id' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY155 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY155-REFFMT`

**Gateway:** gateway_reference = GW155 (G155)

**Bank:** bank_reference = PAY-155 (B155)

**Ledger:** payment_reference = PAY155 (L155)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('dash_prefix' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY156 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY156-REFFMT`

**Gateway:** gateway_reference = GW156 (G156)

**Bank:** bank_reference = 156 (B156)

**Ledger:** payment_reference = PAY156 (L156)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('no_prefix' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY157 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY157-REFFMT`

**Gateway:** gateway_reference = GW157 (G157)

**Bank:** bank_reference = gw157 (B157)

**Ledger:** payment_reference = PAY157 (L157)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('lowercase' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY158 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY158-REFFMT`

**Gateway:** gateway_reference = GW158 (G158)

**Bank:** bank_reference = PAY158 (B158)

**Ledger:** payment_reference = PAY158 (L158)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('truncate6' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY159 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY159-REFFMT`

**Gateway:** gateway_reference = GW159 (G159)

**Bank:** bank_reference = PAY-159 (B159)

**Ledger:** payment_reference = PAY159 (L159)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('dash_prefix' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY160 — Reference Truncation / Formatting Difference

**Discrepancy ID:** `DISC-PAY160-REFFMT`

**Gateway:** gateway_reference = GW160 (G160)

**Bank:** bank_reference = 160 (B160)

**Ledger:** payment_reference = PAY160 (L160)

**Expected outcome:** MATCHED via TIER_2 (partial/fuzzy reference match)

**Why this is correct:** Bank reference is a reformatted/truncated variant of the gateway reference ('no_prefix' style). The underlying payment is the same.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY161 — Duplicate Ledger Entry

**Discrepancy ID:** `DISC-PAY161-DUPLICATE`

**Gateway:** ₹689.60, single row (G161)

**Bank:** ₹689.60, single settlement (B161)

**Ledger:** ₹689.60 recorded TWICE (L161, L162) referencing the same PAY161

**Expected outcome:** EXCEPTION — DUPLICATE_LEDGER_ENTRY (only one settlement exists; the second ledger row must not be counted as a separate settled transaction)

**Why this is correct:** The merchant ledger accidentally recorded the same sale twice. There is only one gateway payment and one bank settlement, so the second ledger row is a duplicate that must be flagged, not treated as an unmatched extra transaction.

**Matching tier:** TIER_2

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY162 — Duplicate Ledger Entry

**Discrepancy ID:** `DISC-PAY162-DUPLICATE`

**Gateway:** ₹2787.09, single row (G162)

**Bank:** ₹2787.09, single settlement (B162)

**Ledger:** ₹2787.09 recorded TWICE (L163, L164) referencing the same PAY162

**Expected outcome:** EXCEPTION — DUPLICATE_LEDGER_ENTRY (only one settlement exists; the second ledger row must not be counted as a separate settled transaction)

**Why this is correct:** The merchant ledger accidentally recorded the same sale twice. There is only one gateway payment and one bank settlement, so the second ledger row is a duplicate that must be flagged, not treated as an unmatched extra transaction.

**Matching tier:** TIER_2

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY163 — Duplicate Ledger Entry

**Discrepancy ID:** `DISC-PAY163-DUPLICATE`

**Gateway:** ₹2761.63, single row (G163)

**Bank:** ₹2761.63, single settlement (B163)

**Ledger:** ₹2761.63 recorded TWICE (L165, L166) referencing the same PAY163

**Expected outcome:** EXCEPTION — DUPLICATE_LEDGER_ENTRY (only one settlement exists; the second ledger row must not be counted as a separate settled transaction)

**Why this is correct:** The merchant ledger accidentally recorded the same sale twice. There is only one gateway payment and one bank settlement, so the second ledger row is a duplicate that must be flagged, not treated as an unmatched extra transaction.

**Matching tier:** TIER_2

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY164 — Duplicate Ledger Entry

**Discrepancy ID:** `DISC-PAY164-DUPLICATE`

**Gateway:** ₹712.14, single row (G164)

**Bank:** ₹712.14, single settlement (B164)

**Ledger:** ₹712.14 recorded TWICE (L167, L168) referencing the same PAY164

**Expected outcome:** EXCEPTION — DUPLICATE_LEDGER_ENTRY (only one settlement exists; the second ledger row must not be counted as a separate settled transaction)

**Why this is correct:** The merchant ledger accidentally recorded the same sale twice. There is only one gateway payment and one bank settlement, so the second ledger row is a duplicate that must be flagged, not treated as an unmatched extra transaction.

**Matching tier:** TIER_2

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY165 — Partial Refund

**Discrepancy ID:** `DISC-PAY165-REFUND`

**Gateway:** Original ₹6369.28 (G165) + Refund -₹870.67 as PAY165-REFUND (G166)

**Bank:** Net settlement ₹5498.61 (B165)

**Ledger:** Original ₹6369.28 (L169) + Refund -₹870.67 as PAY165-REFUND (L170)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹870.67 was refunded, so bank settled the net. Both gateway and ledger carry an explicit linked refund row.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 870.67 | **Date difference:** 0 days

---

## PAY166 — Partial Refund

**Discrepancy ID:** `DISC-PAY166-REFUND`

**Gateway:** Original ₹6803.56 (G167) + Refund -₹1309.86 as PAY166-REFUND (G168)

**Bank:** Net settlement ₹5493.70 (B166)

**Ledger:** Original ₹6803.56 (L171) + Refund -₹1309.86 as PAY166-REFUND (L172)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹1309.86 was refunded, so bank settled the net. Both gateway and ledger carry an explicit linked refund row.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 1309.86 | **Date difference:** 0 days

---

## PAY167 — Partial Refund

**Discrepancy ID:** `DISC-PAY167-REFUND`

**Gateway:** Original ₹2655.61 (G169) + Refund -₹730.02 as PAY167-REFUND (G170)

**Bank:** Net settlement ₹1925.59 (B167)

**Ledger:** Original ₹2655.61 (L173) + Refund -₹730.02 as PAY167-REFUND (L174)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹730.02 was refunded, so bank settled the net. Both gateway and ledger carry an explicit linked refund row.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 730.02 | **Date difference:** 0 days

---

## PAY168 — Partial Refund

**Discrepancy ID:** `DISC-PAY168-REFUND`

**Gateway:** Original ₹3149.54 (G171) + Refund -₹362.44 as PAY168-REFUND (G172)

**Bank:** Net settlement ₹2787.10 (B168)

**Ledger:** Original ₹3149.54 (L175) + Refund -₹362.44 as PAY168-REFUND (L176)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹362.44 was refunded, so bank settled the net. Both gateway and ledger carry an explicit linked refund row.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 362.44 | **Date difference:** 0 days

---

## PAY169 — Partial Refund

**Discrepancy ID:** `DISC-PAY169-REFUND`

**Gateway:** Original ₹5217.71 (G173) + Refund -₹1364.98 as PAY169-REFUND (G174)

**Bank:** Net settlement ₹3852.73 (B169)

**Ledger:** Original ₹5217.71 (L177) + Refund -₹1364.98 as PAY169-REFUND (L178)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹1364.98 was refunded, so bank settled the net. Both gateway and ledger carry an explicit linked refund row.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 1364.98 | **Date difference:** 0 days

---

## PAY170 — Partial Refund

**Discrepancy ID:** `DISC-PAY170-REFUND`

**Gateway:** Original ₹2841.09 (G175) + Refund -₹770.48 as PAY170-REFUND (G176)

**Bank:** Net settlement ₹2070.61 (B170)

**Ledger:** Original ₹2841.09 (L179) + Refund -₹770.48 as PAY170-REFUND (L180)

**Expected outcome:** MATCHED via TIER_2 — classified as PARTIAL_REFUND, net amount reconciles exactly (gross - refund = bank settlement)

**Why this is correct:** ₹770.48 was refunded, so bank settled the net. Both gateway and ledger carry an explicit linked refund row.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 770.48 | **Date difference:** 0 days

---

## PAY171 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY171-TDS`

**Gateway:** ₹3881.18 gross (G177)

**Bank:** ₹3842.37 net of TDS (B171)

**Ledger:** ₹3881.18 gross, tds_amount = ₹38.81 (L181)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹38.81 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 38.81 | **Date difference:** 0 days

---

## PAY172 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY172-TDS`

**Gateway:** ₹8869.30 gross (G178)

**Bank:** ₹8780.61 net of TDS (B172)

**Ledger:** ₹8869.30 gross, tds_amount = ₹88.69 (L182)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹88.69 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 88.69 | **Date difference:** 0 days

---

## PAY173 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY173-TDS`

**Gateway:** ₹7865.29 gross (G179)

**Bank:** ₹7786.64 net of TDS (B173)

**Ledger:** ₹7865.29 gross, tds_amount = ₹78.65 (L183)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹78.65 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 78.65 | **Date difference:** 0 days

---

## PAY174 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY174-TDS`

**Gateway:** ₹3132.82 gross (G180)

**Bank:** ₹3101.49 net of TDS (B174)

**Ledger:** ₹3132.82 gross, tds_amount = ₹31.33 (L184)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹31.33 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 31.33 | **Date difference:** 0 days

---

## PAY175 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY175-TDS`

**Gateway:** ₹3839.36 gross (G181)

**Bank:** ₹3800.97 net of TDS (B175)

**Ledger:** ₹3839.36 gross, tds_amount = ₹38.39 (L185)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹38.39 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 38.39 | **Date difference:** 0 days

---

## PAY176 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY176-TDS`

**Gateway:** ₹9782.09 gross (G182)

**Bank:** ₹9684.27 net of TDS (B176)

**Ledger:** ₹9782.09 gross, tds_amount = ₹97.82 (L186)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹97.82 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 97.82 | **Date difference:** 0 days

---

## PAY177 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY177-TDS`

**Gateway:** ₹5127.42 gross (G183)

**Bank:** ₹5076.15 net of TDS (B177)

**Ledger:** ₹5127.42 gross, tds_amount = ₹51.27 (L187)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹51.27 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 51.27 | **Date difference:** 0 days

---

## PAY178 — GST/TDS Deduction

**Discrepancy ID:** `DISC-PAY178-TDS`

**Gateway:** ₹6657.73 gross (G184)

**Bank:** ₹6591.15 net of TDS (B178)

**Ledger:** ₹6657.73 gross, tds_amount = ₹66.58 (L188)

**Expected outcome:** MATCHED via TIER_2 — classified as TAX_LINE_MISMATCH (gross - tds_amount = bank settlement, exactly)

**Why this is correct:** Bank settled ₹66.58 less than the gross amount due to TDS deduction (rate 1%), which the ledger explicitly records in tds_amount. This must not be classified as a generic amount mismatch.

**Matching tier:** TIER_2

**Remains an exception:** No

**Amount difference:** 66.58 | **Date difference:** 0 days

---

## PAY179 — Missing Bank Counterpart

**Discrepancy ID:** `DISC-PAY179-NOBANK`

**Gateway:** ₹2184.75 on 2026-08-20 (G185)

**Bank:** No corresponding row exists in bank.csv

**Ledger:** ₹2184.75 on 2026-08-20 (L189)

**Expected outcome:** EXCEPTION — NO_BANK_COUNTERPART (unresolved, goes to exception queue)

**Why this is correct:** The payment exists in both the gateway export and the merchant ledger, but no matching settlement was ever found in the bank statement. The system must NOT invent or assume a settlement; this must surface as an unresolved item.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY180 — Missing Bank Counterpart

**Discrepancy ID:** `DISC-PAY180-NOBANK`

**Gateway:** ₹3526.28 on 2026-08-20 (G186)

**Bank:** No corresponding row exists in bank.csv

**Ledger:** ₹3526.28 on 2026-08-20 (L190)

**Expected outcome:** EXCEPTION — NO_BANK_COUNTERPART (unresolved, goes to exception queue)

**Why this is correct:** The payment exists in both the gateway export and the merchant ledger, but no matching settlement was ever found in the bank statement. The system must NOT invent or assume a settlement; this must surface as an unresolved item.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY181 — Missing Bank Counterpart

**Discrepancy ID:** `DISC-PAY181-NOBANK`

**Gateway:** ₹3658.55 on 2026-08-20 (G187)

**Bank:** No corresponding row exists in bank.csv

**Ledger:** ₹3658.55 on 2026-08-20 (L191)

**Expected outcome:** EXCEPTION — NO_BANK_COUNTERPART (unresolved, goes to exception queue)

**Why this is correct:** The payment exists in both the gateway export and the merchant ledger, but no matching settlement was ever found in the bank statement. The system must NOT invent or assume a settlement; this must surface as an unresolved item.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY182 — Missing Bank Counterpart

**Discrepancy ID:** `DISC-PAY182-NOBANK`

**Gateway:** ₹1076.23 on 2026-08-20 (G188)

**Bank:** No corresponding row exists in bank.csv

**Ledger:** ₹1076.23 on 2026-08-20 (L192)

**Expected outcome:** EXCEPTION — NO_BANK_COUNTERPART (unresolved, goes to exception queue)

**Why this is correct:** The payment exists in both the gateway export and the merchant ledger, but no matching settlement was ever found in the bank statement. The system must NOT invent or assume a settlement; this must surface as an unresolved item.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY183 — True Orphan (UNMATCHED_GATEWAY_TRANSACTION)

**Discrepancy ID:** `DISC-PAY183-ORPHAN`

**Gateway:** YES (G189)

**Bank:** No counterpart

**Ledger:** No counterpart

**Expected outcome:** EXCEPTION — UNMATCHED_GATEWAY_TRANSACTION (unresolved, goes to exception queue)

**Why this is correct:** This transaction exists in exactly one source (Gateway Only) with no counterpart in either of the other two sources. It must be kept distinct from NO_BANK_COUNTERPART, which requires presence in two sources.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY184 — True Orphan (UNMATCHED_BANK_TRANSACTION)

**Discrepancy ID:** `DISC-PAY184-ORPHAN`

**Gateway:** No counterpart

**Bank:** YES (B179)

**Ledger:** No counterpart

**Expected outcome:** EXCEPTION — UNMATCHED_BANK_TRANSACTION (unresolved, goes to exception queue)

**Why this is correct:** This transaction exists in exactly one source (Bank Only) with no counterpart in either of the other two sources. It must be kept distinct from NO_BANK_COUNTERPART, which requires presence in two sources.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY185 — True Orphan (UNMATCHED_GATEWAY_TRANSACTION)

**Discrepancy ID:** `DISC-PAY185-ORPHAN`

**Gateway:** YES (G190)

**Bank:** No counterpart

**Ledger:** No counterpart

**Expected outcome:** EXCEPTION — UNMATCHED_GATEWAY_TRANSACTION (unresolved, goes to exception queue)

**Why this is correct:** This transaction exists in exactly one source (Gateway Only) with no counterpart in either of the other two sources. It must be kept distinct from NO_BANK_COUNTERPART, which requires presence in two sources.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY186 — True Orphan (UNMATCHED_BANK_TRANSACTION)

**Discrepancy ID:** `DISC-PAY186-ORPHAN`

**Gateway:** No counterpart

**Bank:** YES (B180)

**Ledger:** No counterpart

**Expected outcome:** EXCEPTION — UNMATCHED_BANK_TRANSACTION (unresolved, goes to exception queue)

**Why this is correct:** This transaction exists in exactly one source (Bank Only) with no counterpart in either of the other two sources. It must be kept distinct from NO_BANK_COUNTERPART, which requires presence in two sources.

**Matching tier:** N/A (unresolved)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY187 — GST Decomposition (Tier 3)

**Discrepancy ID:** `DISC-PAY187-GST-DECOMP`

**Gateway:** ₹4852.49 gateway amount (G191), ref GW187

**Bank:** ₹5095.11 credit = gateway 4852.49 + GST 242.62 (B181), bank_reference=GW187

**Ledger:** ₹4852.49 recorded, gst_amount = ₹242.62 (L193)

**Expected outcome:** MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)

**Why this is correct:** Bank settled ₹242.62 more than the raw gateway amount. The ledger's gst_amount field precisely explains the variance: 4852.49 + 242.62 = 5095.11 (bank). This is a legitimate tax decomposition, not an amount mismatch.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 242.62 | **Date difference:** 0 days

---

## PAY188 — GST Decomposition (Tier 3)

**Discrepancy ID:** `DISC-PAY188-GST-DECOMP`

**Gateway:** ₹8965.92 gateway amount (G192), ref GW188

**Bank:** ₹10579.79 credit = gateway 8965.92 + GST 1613.87 (B182), bank_reference=GW188

**Ledger:** ₹8965.92 recorded, gst_amount = ₹1613.87 (L194)

**Expected outcome:** MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)

**Why this is correct:** Bank settled ₹1613.87 more than the raw gateway amount. The ledger's gst_amount field precisely explains the variance: 8965.92 + 1613.87 = 10579.79 (bank). This is a legitimate tax decomposition, not an amount mismatch.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 1613.87 | **Date difference:** 0 days

---

## PAY189 — GST Decomposition (Tier 3)

**Discrepancy ID:** `DISC-PAY189-GST-DECOMP`

**Gateway:** ₹9305.05 gateway amount (G193), ref GW189

**Bank:** ₹10979.96 credit = gateway 9305.05 + GST 1674.91 (B183), bank_reference=GW189

**Ledger:** ₹9305.05 recorded, gst_amount = ₹1674.91 (L195)

**Expected outcome:** MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)

**Why this is correct:** Bank settled ₹1674.91 more than the raw gateway amount. The ledger's gst_amount field precisely explains the variance: 9305.05 + 1674.91 = 10979.96 (bank). This is a legitimate tax decomposition, not an amount mismatch.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 1674.91 | **Date difference:** 0 days

---

## PAY190 — GST Decomposition (Tier 3)

**Discrepancy ID:** `DISC-PAY190-GST-DECOMP`

**Gateway:** ₹9833.62 gateway amount (G194), ref GW190

**Bank:** ₹11603.67 credit = gateway 9833.62 + GST 1770.05 (B184), bank_reference=GW190

**Ledger:** ₹9833.62 recorded, gst_amount = ₹1770.05 (L196)

**Expected outcome:** MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)

**Why this is correct:** Bank settled ₹1770.05 more than the raw gateway amount. The ledger's gst_amount field precisely explains the variance: 9833.62 + 1770.05 = 11603.67 (bank). This is a legitimate tax decomposition, not an amount mismatch.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 1770.05 | **Date difference:** 0 days

---

## PAY191 — GST Decomposition (Tier 3)

**Discrepancy ID:** `DISC-PAY191-GST-DECOMP`

**Gateway:** ₹8618.71 gateway amount (G195), ref GW191

**Bank:** ₹9049.65 credit = gateway 8618.71 + GST 430.94 (B185), bank_reference=GW191

**Ledger:** ₹8618.71 recorded, gst_amount = ₹430.94 (L197)

**Expected outcome:** MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)

**Why this is correct:** Bank settled ₹430.94 more than the raw gateway amount. The ledger's gst_amount field precisely explains the variance: 8618.71 + 430.94 = 9049.65 (bank). This is a legitimate tax decomposition, not an amount mismatch.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 430.94 | **Date difference:** 0 days

---

## PAY192 — GST Decomposition (Tier 3)

**Discrepancy ID:** `DISC-PAY192-GST-DECOMP`

**Gateway:** ₹6866.71 gateway amount (G196), ref GW192

**Bank:** ₹8102.72 credit = gateway 6866.71 + GST 1236.01 (B186), bank_reference=GW192

**Ledger:** ₹6866.71 recorded, gst_amount = ₹1236.01 (L198)

**Expected outcome:** MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)

**Why this is correct:** Bank settled ₹1236.01 more than the raw gateway amount. The ledger's gst_amount field precisely explains the variance: 6866.71 + 1236.01 = 8102.72 (bank). This is a legitimate tax decomposition, not an amount mismatch.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 1236.01 | **Date difference:** 0 days

---

## PAY193 — GST Decomposition (Tier 3)

**Discrepancy ID:** `DISC-PAY193-GST-DECOMP`

**Gateway:** ₹3898.98 gateway amount (G197), ref GW193

**Bank:** ₹4366.86 credit = gateway 3898.98 + GST 467.88 (B187), bank_reference=GW193

**Ledger:** ₹3898.98 recorded, gst_amount = ₹467.88 (L199)

**Expected outcome:** MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)

**Why this is correct:** Bank settled ₹467.88 more than the raw gateway amount. The ledger's gst_amount field precisely explains the variance: 3898.98 + 467.88 = 4366.86 (bank). This is a legitimate tax decomposition, not an amount mismatch.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 467.88 | **Date difference:** 0 days

---

## PAY194 — GST Decomposition (Tier 3)

**Discrepancy ID:** `DISC-PAY194-GST-DECOMP`

**Gateway:** ₹4177.01 gateway amount (G198), ref GW194

**Bank:** ₹4385.86 credit = gateway 4177.01 + GST 208.85 (B188), bank_reference=GW194

**Ledger:** ₹4177.01 recorded, gst_amount = ₹208.85 (L200)

**Expected outcome:** MATCHED via TIER_3 (GST_DECOMPOSITION: gateway + gst_amount = bank, exactly)

**Why this is correct:** Bank settled ₹208.85 more than the raw gateway amount. The ledger's gst_amount field precisely explains the variance: 4177.01 + 208.85 = 4385.86 (bank). This is a legitimate tax decomposition, not an amount mismatch.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 208.85 | **Date difference:** 0 days

---

## PAY195 — MDR / Fee Deduction (Tier 3)

**Discrepancy ID:** `DISC-PAY195-MDR-FEE`

**Gateway:** ₹3601.71 gateway amount (G199), ref GW195

**Bank:** ₹3546.47 = gateway 3601.71 - MDR 36.02 - MDR GST 6.48 - fee 12.74 (B189), bank_reference=GW195

**Ledger:** ₹3601.71 recorded, mdr=36.02, mdr_gst=6.48, fee=12.74 (L201)

**Expected outcome:** MATCHED via TIER_3 (MDR_FEE_DEDUCTION: gateway - mdr - mdr_gst - fee = bank, exactly)

**Why this is correct:** Bank settled less than the gateway by the sum of MDR and fees. The ledger's mdr_amount, mdr_gst, and fee_amount precisely explain: 3601.71 - 36.02 - 6.48 - 12.74 = 3546.47.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 55.24 | **Date difference:** 0 days

---

## PAY196 — MDR / Fee Deduction (Tier 3)

**Discrepancy ID:** `DISC-PAY196-MDR-FEE`

**Gateway:** ₹8721.46 gateway amount (G200), ref GW196

**Bank:** ₹8581.54 = gateway 8721.46 - MDR 87.21 - MDR GST 15.70 - fee 37.01 (B190), bank_reference=GW196

**Ledger:** ₹8721.46 recorded, mdr=87.21, mdr_gst=15.70, fee=37.01 (L202)

**Expected outcome:** MATCHED via TIER_3 (MDR_FEE_DEDUCTION: gateway - mdr - mdr_gst - fee = bank, exactly)

**Why this is correct:** Bank settled less than the gateway by the sum of MDR and fees. The ledger's mdr_amount, mdr_gst, and fee_amount precisely explain: 8721.46 - 87.21 - 15.70 - 37.01 = 8581.54.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 139.92 | **Date difference:** 0 days

---

## PAY197 — MDR / Fee Deduction (Tier 3)

**Discrepancy ID:** `DISC-PAY197-MDR-FEE`

**Gateway:** ₹14032.65 gateway amount (G201), ref GW197

**Bank:** ₹13840.91 = gateway 14032.65 - MDR 140.33 - MDR GST 25.26 - fee 26.15 (B191), bank_reference=GW197

**Ledger:** ₹14032.65 recorded, mdr=140.33, mdr_gst=25.26, fee=26.15 (L203)

**Expected outcome:** MATCHED via TIER_3 (MDR_FEE_DEDUCTION: gateway - mdr - mdr_gst - fee = bank, exactly)

**Why this is correct:** Bank settled less than the gateway by the sum of MDR and fees. The ledger's mdr_amount, mdr_gst, and fee_amount precisely explain: 14032.65 - 140.33 - 25.26 - 26.15 = 13840.91.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 191.74 | **Date difference:** 0 days

---

## PAY198 — MDR / Fee Deduction (Tier 3)

**Discrepancy ID:** `DISC-PAY198-MDR-FEE`

**Gateway:** ₹9373.51 gateway amount (G202), ref GW198

**Bank:** ₹9132.45 = gateway 9373.51 - MDR 187.47 - MDR GST 33.74 - fee 19.85 (B192), bank_reference=GW198

**Ledger:** ₹9373.51 recorded, mdr=187.47, mdr_gst=33.74, fee=19.85 (L204)

**Expected outcome:** MATCHED via TIER_3 (MDR_FEE_DEDUCTION: gateway - mdr - mdr_gst - fee = bank, exactly)

**Why this is correct:** Bank settled less than the gateway by the sum of MDR and fees. The ledger's mdr_amount, mdr_gst, and fee_amount precisely explain: 9373.51 - 187.47 - 33.74 - 19.85 = 9132.45.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 241.06 | **Date difference:** 0 days

---

## PAY199 — MDR / Fee Deduction (Tier 3)

**Discrepancy ID:** `DISC-PAY199-MDR-FEE`

**Gateway:** ₹3682.55 gateway amount (G203), ref GW199

**Bank:** ₹3584.05 = gateway 3682.55 - MDR 73.65 - MDR GST 13.26 - fee 11.59 (B193), bank_reference=GW199

**Ledger:** ₹3682.55 recorded, mdr=73.65, mdr_gst=13.26, fee=11.59 (L205)

**Expected outcome:** MATCHED via TIER_3 (MDR_FEE_DEDUCTION: gateway - mdr - mdr_gst - fee = bank, exactly)

**Why this is correct:** Bank settled less than the gateway by the sum of MDR and fees. The ledger's mdr_amount, mdr_gst, and fee_amount precisely explain: 3682.55 - 73.65 - 13.26 - 11.59 = 3584.05.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 98.50 | **Date difference:** 0 days

---

## PAY200 — MDR / Fee Deduction (Tier 3)

**Discrepancy ID:** `DISC-PAY200-MDR-FEE`

**Gateway:** ₹9093.94 gateway amount (G204), ref GW200

**Bank:** ₹8959.86 = gateway 9093.94 - MDR 90.94 - MDR GST 16.37 - fee 26.77 (B194), bank_reference=GW200

**Ledger:** ₹9093.94 recorded, mdr=90.94, mdr_gst=16.37, fee=26.77 (L206)

**Expected outcome:** MATCHED via TIER_3 (MDR_FEE_DEDUCTION: gateway - mdr - mdr_gst - fee = bank, exactly)

**Why this is correct:** Bank settled less than the gateway by the sum of MDR and fees. The ledger's mdr_amount, mdr_gst, and fee_amount precisely explain: 9093.94 - 90.94 - 16.37 - 26.77 = 8959.86.

**Matching tier:** TIER_3

**Remains an exception:** No

**Amount difference:** 134.08 | **Date difference:** 0 days

---

## PAY201 — Split Settlement (2 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY201-SPLIT-2ROW`

**Gateway:** ₹10004.07 single gateway payment (G205), ref GW201

**Bank:** Two credits ₹5049.59 (B195) + ₹4958.39 (B196) = ₹10007.98 (gap 3.91, ref GW201)

**Ledger:** ₹10004.07 recorded (L207)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 2 credits sum within ₹5.00 of gateway)

**Why this is correct:** One gateway payment was settled as 2 separate bank credits. The two credits sum to within SPLIT_SETTLEMENT_TOLERANCE (₹5.00) of the gateway amount. An LLM recommender identifies the pair; arithmetic is independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 3.91 | **Date difference:** 0 days

---

## PAY202 — Split Settlement (2 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY202-SPLIT-2ROW`

**Gateway:** ₹5451.11 single gateway payment (G206), ref GW202

**Bank:** Two credits ₹2959.98 (B197) + ₹2488.78 (B198) = ₹5448.76 (gap 2.35, ref GW202)

**Ledger:** ₹5451.11 recorded (L208)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 2 credits sum within ₹5.00 of gateway)

**Why this is correct:** One gateway payment was settled as 2 separate bank credits. The two credits sum to within SPLIT_SETTLEMENT_TOLERANCE (₹5.00) of the gateway amount. An LLM recommender identifies the pair; arithmetic is independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 2.35 | **Date difference:** 0 days

---

## PAY203 — Split Settlement (2 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY203-SPLIT-2ROW`

**Gateway:** ₹7749.43 single gateway payment (G207), ref GW203

**Bank:** Two credits ₹4139.85 (B199) + ₹3607.78 (B200) = ₹7747.63 (gap 1.80, ref GW203)

**Ledger:** ₹7749.43 recorded (L209)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 2 credits sum within ₹5.00 of gateway)

**Why this is correct:** One gateway payment was settled as 2 separate bank credits. The two credits sum to within SPLIT_SETTLEMENT_TOLERANCE (₹5.00) of the gateway amount. An LLM recommender identifies the pair; arithmetic is independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 1.80 | **Date difference:** 0 days

---

## PAY204 — Split Settlement (2 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY204-SPLIT-2ROW`

**Gateway:** ₹6794.13 single gateway payment (G208), ref GW204

**Bank:** Two credits ₹3737.19 (B201) + ₹3053.09 (B202) = ₹6790.28 (gap 3.85, ref GW204)

**Ledger:** ₹6794.13 recorded (L210)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 2 credits sum within ₹5.00 of gateway)

**Why this is correct:** One gateway payment was settled as 2 separate bank credits. The two credits sum to within SPLIT_SETTLEMENT_TOLERANCE (₹5.00) of the gateway amount. An LLM recommender identifies the pair; arithmetic is independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 3.85 | **Date difference:** 0 days

---

## PAY205 — Split Settlement (2 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY205-SPLIT-2ROW`

**Gateway:** ₹8499.43 single gateway payment (G209), ref GW205

**Bank:** Two credits ₹5099.71 (B203) + ₹3404.18 (B204) = ₹8503.89 (gap 4.46, ref GW205)

**Ledger:** ₹8499.43 recorded (L211)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 2 credits sum within ₹5.00 of gateway)

**Why this is correct:** One gateway payment was settled as 2 separate bank credits. The two credits sum to within SPLIT_SETTLEMENT_TOLERANCE (₹5.00) of the gateway amount. An LLM recommender identifies the pair; arithmetic is independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 4.46 | **Date difference:** 0 days

---

## PAY206 — Split Settlement (2 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY206-SPLIT-2ROW`

**Gateway:** ₹3879.13 single gateway payment (G210), ref GW206

**Bank:** Two credits ₹1716.09 (B205) + ₹2160.93 (B206) = ₹3877.02 (gap 2.11, ref GW206)

**Ledger:** ₹3879.13 recorded (L212)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 2 credits sum within ₹5.00 of gateway)

**Why this is correct:** One gateway payment was settled as 2 separate bank credits. The two credits sum to within SPLIT_SETTLEMENT_TOLERANCE (₹5.00) of the gateway amount. An LLM recommender identifies the pair; arithmetic is independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 2.11 | **Date difference:** 0 days

---

## PAY207 — Split Settlement (3 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY207-SPLIT-3ROW`

**Gateway:** ₹18998.89 single gateway payment (G211), ref GW207

**Bank:** Three credits ₹6421.40 + ₹5452.77 + ₹7128.15 = ₹19002.32 (gap 3.43, ref GW207)

**Ledger:** ₹18998.89 recorded (L213)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 3 credits sum within ₹5.00)

**Why this is correct:** One gateway payment was settled as 3 separate bank credits. The three credits together sum within SPLIT_SETTLEMENT_TOLERANCE. LLM recommender is required (2+ combos may be plausible); arithmetic independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 3.43 | **Date difference:** 0 days

---

## PAY208 — Split Settlement (3 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY208-SPLIT-3ROW`

**Gateway:** ₹7366.20 single gateway payment (G212), ref GW208

**Bank:** Three credits ₹2360.75 + ₹2293.06 + ₹2715.39 = ₹7369.20 (gap 3.00, ref GW208)

**Ledger:** ₹7366.20 recorded (L214)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 3 credits sum within ₹5.00)

**Why this is correct:** One gateway payment was settled as 3 separate bank credits. The three credits together sum within SPLIT_SETTLEMENT_TOLERANCE. LLM recommender is required (2+ combos may be plausible); arithmetic independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 3.00 | **Date difference:** 0 days

---

## PAY209 — Split Settlement (3 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY209-SPLIT-3ROW`

**Gateway:** ₹19808.50 single gateway payment (G213), ref GW209

**Bank:** Three credits ₹4967.97 + ₹6571.15 + ₹8270.77 = ₹19809.89 (gap 1.39, ref GW209)

**Ledger:** ₹19808.50 recorded (L215)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 3 credits sum within ₹5.00)

**Why this is correct:** One gateway payment was settled as 3 separate bank credits. The three credits together sum within SPLIT_SETTLEMENT_TOLERANCE. LLM recommender is required (2+ combos may be plausible); arithmetic independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 1.39 | **Date difference:** 0 days

---

## PAY210 — Split Settlement (3 bank rows, Tier 3 LLM-assisted)

**Discrepancy ID:** `DISC-PAY210-SPLIT-3ROW`

**Gateway:** ₹9490.68 single gateway payment (G214), ref GW210

**Bank:** Three credits ₹3264.28 + ₹2500.51 + ₹3727.36 = ₹9492.15 (gap 1.47, ref GW210)

**Ledger:** ₹9490.68 recorded (L216)

**Expected outcome:** MATCHED via TIER_3 SPLIT_SETTLEMENT_SUM (LLM-assisted; 3 credits sum within ₹5.00)

**Why this is correct:** One gateway payment was settled as 3 separate bank credits. The three credits together sum within SPLIT_SETTLEMENT_TOLERANCE. LLM recommender is required (2+ combos may be plausible); arithmetic independently validated.

**Matching tier:** TIER_3 (LLM-assisted)

**Remains an exception:** No

**Amount difference:** 1.47 | **Date difference:** 0 days

---

## PAY211 — Delayed Refund (net settlement on later date)

**Discrepancy ID:** `DISC-PAY211-DELAYED-REFUND`

**Gateway:** Original ₹2923.43 (G215) + Refund -₹386.22 (G216)

**Bank:** Net settlement ₹2537.21 on 2026-08-22 (B219) — refund-linked net, delayed by 2 days

**Ledger:** Original ₹2923.43 (L217) + Refund -₹386.22 (L218) on 2026-08-22

**Expected outcome:** MATCHED via TIER_3 REFUND_LINKED_NET_AMOUNT (net amount reconciles; date delay is corroborating only)

**Why this is correct:** ₹386.22 was refunded, so bank settled the net ₹2537.21. The settlement date is 2 days after the original because the refund decision delayed the net. Gateway and ledger carry linked refund rows.

**Matching tier:** TIER_3 (RefundLinked)

**Remains an exception:** No

**Amount difference:** 386.22 | **Date difference:** 2 days

---

## PAY212 — Delayed Refund (net settlement on later date)

**Discrepancy ID:** `DISC-PAY212-DELAYED-REFUND`

**Gateway:** Original ₹6425.79 (G217) + Refund -₹1167.59 (G218)

**Bank:** Net settlement ₹5258.20 on 2026-08-22 (B220) — refund-linked net, delayed by 2 days

**Ledger:** Original ₹6425.79 (L219) + Refund -₹1167.59 (L220) on 2026-08-22

**Expected outcome:** MATCHED via TIER_3 REFUND_LINKED_NET_AMOUNT (net amount reconciles; date delay is corroborating only)

**Why this is correct:** ₹1167.59 was refunded, so bank settled the net ₹5258.20. The settlement date is 2 days after the original because the refund decision delayed the net. Gateway and ledger carry linked refund rows.

**Matching tier:** TIER_3 (RefundLinked)

**Remains an exception:** No

**Amount difference:** 1167.59 | **Date difference:** 2 days

---

## PAY213 — Delayed Refund (net settlement on later date)

**Discrepancy ID:** `DISC-PAY213-DELAYED-REFUND`

**Gateway:** Original ₹6838.64 (G219) + Refund -₹2156.11 (G220)

**Bank:** Net settlement ₹4682.53 on 2026-08-22 (B221) — refund-linked net, delayed by 2 days

**Ledger:** Original ₹6838.64 (L221) + Refund -₹2156.11 (L222) on 2026-08-22

**Expected outcome:** MATCHED via TIER_3 REFUND_LINKED_NET_AMOUNT (net amount reconciles; date delay is corroborating only)

**Why this is correct:** ₹2156.11 was refunded, so bank settled the net ₹4682.53. The settlement date is 2 days after the original because the refund decision delayed the net. Gateway and ledger carry linked refund rows.

**Matching tier:** TIER_3 (RefundLinked)

**Remains an exception:** No

**Amount difference:** 2156.11 | **Date difference:** 2 days

---

## PAY214 — Delayed Refund (net settlement on later date)

**Discrepancy ID:** `DISC-PAY214-DELAYED-REFUND`

**Gateway:** Original ₹3628.78 (G221) + Refund -₹1053.33 (G222)

**Bank:** Net settlement ₹2575.45 on 2026-08-22 (B222) — refund-linked net, delayed by 2 days

**Ledger:** Original ₹3628.78 (L223) + Refund -₹1053.33 (L224) on 2026-08-22

**Expected outcome:** MATCHED via TIER_3 REFUND_LINKED_NET_AMOUNT (net amount reconciles; date delay is corroborating only)

**Why this is correct:** ₹1053.33 was refunded, so bank settled the net ₹2575.45. The settlement date is 2 days after the original because the refund decision delayed the net. Gateway and ledger carry linked refund rows.

**Matching tier:** TIER_3 (RefundLinked)

**Remains an exception:** No

**Amount difference:** 1053.33 | **Date difference:** 2 days

---

## PAY215 — Full Refund (no bank settlement expected)

**Discrepancy ID:** `DISC-PAY215-FULLREFUND`

**Gateway:** Original ₹2847.89 (G223) + Full Refund -₹2847.89 (G224)

**Bank:** No corresponding settlement (net zero — fully refunded before settlement window)

**Ledger:** Original ₹2847.89 (L225) + Full Refund -₹2847.89 (L226)

**Expected outcome:** EXCEPTION — FULL_REFUND (net zero; no bank settlement expected; not an amount mismatch)

**Why this is correct:** The payment of ₹2847.89 was fully refunded before any bank settlement. There is no bank counterpart to match — this is correct, not an error. It surfaces as an exception for audit, not a Tier 3 human review.

**Matching tier:** N/A (exception)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY216 — Full Refund (no bank settlement expected)

**Discrepancy ID:** `DISC-PAY216-FULLREFUND`

**Gateway:** Original ₹4419.72 (G225) + Full Refund -₹4419.72 (G226)

**Bank:** No corresponding settlement (net zero — fully refunded before settlement window)

**Ledger:** Original ₹4419.72 (L227) + Full Refund -₹4419.72 (L228)

**Expected outcome:** EXCEPTION — FULL_REFUND (net zero; no bank settlement expected; not an amount mismatch)

**Why this is correct:** The payment of ₹4419.72 was fully refunded before any bank settlement. There is no bank counterpart to match — this is correct, not an error. It surfaces as an exception for audit, not a Tier 3 human review.

**Matching tier:** N/A (exception)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY217 — Full Refund (no bank settlement expected)

**Discrepancy ID:** `DISC-PAY217-FULLREFUND`

**Gateway:** Original ₹7337.36 (G227) + Full Refund -₹7337.36 (G228)

**Bank:** No corresponding settlement (net zero — fully refunded before settlement window)

**Ledger:** Original ₹7337.36 (L229) + Full Refund -₹7337.36 (L230)

**Expected outcome:** EXCEPTION — FULL_REFUND (net zero; no bank settlement expected; not an amount mismatch)

**Why this is correct:** The payment of ₹7337.36 was fully refunded before any bank settlement. There is no bank counterpart to match — this is correct, not an error. It surfaces as an exception for audit, not a Tier 3 human review.

**Matching tier:** N/A (exception)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY218 — Full Refund (no bank settlement expected)

**Discrepancy ID:** `DISC-PAY218-FULLREFUND`

**Gateway:** Original ₹6922.73 (G229) + Full Refund -₹6922.73 (G230)

**Bank:** No corresponding settlement (net zero — fully refunded before settlement window)

**Ledger:** Original ₹6922.73 (L231) + Full Refund -₹6922.73 (L232)

**Expected outcome:** EXCEPTION — FULL_REFUND (net zero; no bank settlement expected; not an amount mismatch)

**Why this is correct:** The payment of ₹6922.73 was fully refunded before any bank settlement. There is no bank counterpart to match — this is correct, not an error. It surfaces as an exception for audit, not a Tier 3 human review.

**Matching tier:** N/A (exception)

**Remains an exception:** Yes

**Amount difference:** N/A | **Date difference:** N/A

---

## PAY219 — Partial Payment (gateway/bank agree, ledger invoice higher)

**Discrepancy ID:** `DISC-PAY219-PARTIAL-PAYMENT`

**Gateway:** ₹3144.95 paid (G231), ref GW219; UTR UTR100219

**Bank:** ₹3144.95 settled (B223), ref GW219 — matches gateway exactly

**Ledger:** ₹5015.28 invoiced/recorded (L233) — customer paid only ₹3144.95, shortfall ₹1870.33

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION — two sources agree at ₹3144.95, ledger says ₹5015.28)

**Why this is correct:** Customer paid ₹3144.95 of an invoice recorded as ₹5015.28 (shortfall ₹1870.33). Gateway and bank agree, ledger disagrees. No tax/fee field explains the gap — a human must decide: partial settlement vs. ledger error.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 1870.33 | **Date difference:** 0 days

---

## PAY220 — Partial Payment (gateway/bank agree, ledger invoice higher)

**Discrepancy ID:** `DISC-PAY220-PARTIAL-PAYMENT`

**Gateway:** ₹3529.23 paid (G232), ref GW220; UTR UTR100220

**Bank:** ₹3529.23 settled (B224), ref GW220 — matches gateway exactly

**Ledger:** ₹7043.48 invoiced/recorded (L234) — customer paid only ₹3529.23, shortfall ₹3514.25

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION — two sources agree at ₹3529.23, ledger says ₹7043.48)

**Why this is correct:** Customer paid ₹3529.23 of an invoice recorded as ₹7043.48 (shortfall ₹3514.25). Gateway and bank agree, ledger disagrees. No tax/fee field explains the gap — a human must decide: partial settlement vs. ledger error.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 3514.25 | **Date difference:** 0 days

---

## PAY221 — Partial Payment (gateway/bank agree, ledger invoice higher)

**Discrepancy ID:** `DISC-PAY221-PARTIAL-PAYMENT`

**Gateway:** ₹8626.95 paid (G233), ref GW221; UTR UTR100221

**Bank:** ₹8626.95 settled (B225), ref GW221 — matches gateway exactly

**Ledger:** ₹12482.31 invoiced/recorded (L235) — customer paid only ₹8626.95, shortfall ₹3855.36

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION — two sources agree at ₹8626.95, ledger says ₹12482.31)

**Why this is correct:** Customer paid ₹8626.95 of an invoice recorded as ₹12482.31 (shortfall ₹3855.36). Gateway and bank agree, ledger disagrees. No tax/fee field explains the gap — a human must decide: partial settlement vs. ledger error.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 3855.36 | **Date difference:** 0 days

---

## PAY222 — Partial Payment (gateway/bank agree, ledger invoice higher)

**Discrepancy ID:** `DISC-PAY222-PARTIAL-PAYMENT`

**Gateway:** ₹4970.99 paid (G234), ref GW222; UTR UTR100222

**Bank:** ₹4970.99 settled (B226), ref GW222 — matches gateway exactly

**Ledger:** ₹6881.51 invoiced/recorded (L236) — customer paid only ₹4970.99, shortfall ₹1910.52

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION — two sources agree at ₹4970.99, ledger says ₹6881.51)

**Why this is correct:** Customer paid ₹4970.99 of an invoice recorded as ₹6881.51 (shortfall ₹1910.52). Gateway and bank agree, ledger disagrees. No tax/fee field explains the gap — a human must decide: partial settlement vs. ledger error.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 1910.52 | **Date difference:** 0 days

---

## PAY223 — Multiple Payments (installment 1/2 for INV223)

**Discrepancy ID:** `DISC-PAY223-MULTIPAY`

**Gateway:** ₹4085.04 installment (G235), ref GW223, customer ORD223

**Bank:** ₹4085.04 settlement (B227), ref GW223

**Ledger:** ₹4085.04 recorded (L237), invoice INV223 (paired total ₹8413.44)

**Expected outcome:** MATCHED via TIER_1 — installment of a multi-payment invoice

**Why this is correct:** Invoice INV223 (total ₹8413.44) was paid in 2 installments. This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.

**Matching tier:** TIER_1

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY224 — Multiple Payments (installment 2/2 for INV223)

**Discrepancy ID:** `DISC-PAY224-MULTIPAY`

**Gateway:** ₹4328.40 installment (G236), ref GW224, customer ORD223

**Bank:** ₹4328.40 settlement (B228), ref GW224

**Ledger:** ₹4328.40 recorded (L238), invoice INV223 (paired total ₹8413.44)

**Expected outcome:** MATCHED via TIER_1 — installment of a multi-payment invoice

**Why this is correct:** Invoice INV223 (total ₹8413.44) was paid in 2 installments. This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.

**Matching tier:** TIER_1

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY225 — Multiple Payments (installment 1/2 for INV225)

**Discrepancy ID:** `DISC-PAY225-MULTIPAY`

**Gateway:** ₹1692.30 installment (G237), ref GW225, customer ORD225

**Bank:** ₹1692.30 settlement (B229), ref GW225

**Ledger:** ₹1692.30 recorded (L239), invoice INV225 (paired total ₹4077.36)

**Expected outcome:** MATCHED via TIER_1 — installment of a multi-payment invoice

**Why this is correct:** Invoice INV225 (total ₹4077.36) was paid in 2 installments. This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.

**Matching tier:** TIER_1

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY226 — Multiple Payments (installment 2/2 for INV225)

**Discrepancy ID:** `DISC-PAY226-MULTIPAY`

**Gateway:** ₹2385.06 installment (G238), ref GW226, customer ORD225

**Bank:** ₹2385.06 settlement (B230), ref GW226

**Ledger:** ₹2385.06 recorded (L240), invoice INV225 (paired total ₹4077.36)

**Expected outcome:** MATCHED via TIER_1 — installment of a multi-payment invoice

**Why this is correct:** Invoice INV225 (total ₹4077.36) was paid in 2 installments. This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.

**Matching tier:** TIER_1

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY227 — Multiple Payments (installment 1/2 for INV227)

**Discrepancy ID:** `DISC-PAY227-MULTIPAY`

**Gateway:** ₹6426.31 installment (G239), ref GW227, customer ORD227

**Bank:** ₹6426.31 settlement (B231), ref GW227

**Ledger:** ₹6426.31 recorded (L241), invoice INV227 (paired total ₹11064.85)

**Expected outcome:** MATCHED via TIER_1 — installment of a multi-payment invoice

**Why this is correct:** Invoice INV227 (total ₹11064.85) was paid in 2 installments. This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.

**Matching tier:** TIER_1

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY228 — Multiple Payments (installment 2/2 for INV227)

**Discrepancy ID:** `DISC-PAY228-MULTIPAY`

**Gateway:** ₹4638.54 installment (G240), ref GW228, customer ORD227

**Bank:** ₹4638.54 settlement (B232), ref GW228

**Ledger:** ₹4638.54 recorded (L242), invoice INV227 (paired total ₹11064.85)

**Expected outcome:** MATCHED via TIER_1 — installment of a multi-payment invoice

**Why this is correct:** Invoice INV227 (total ₹11064.85) was paid in 2 installments. This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.

**Matching tier:** TIER_1

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY229 — Multiple Payments (installment 1/2 for INV229)

**Discrepancy ID:** `DISC-PAY229-MULTIPAY`

**Gateway:** ₹4742.12 installment (G241), ref GW229, customer ORD229

**Bank:** ₹4742.12 settlement (B233), ref GW229

**Ledger:** ₹4742.12 recorded (L243), invoice INV229 (paired total ₹8364.72)

**Expected outcome:** MATCHED via TIER_1 — installment of a multi-payment invoice

**Why this is correct:** Invoice INV229 (total ₹8364.72) was paid in 2 installments. This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.

**Matching tier:** TIER_1

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY230 — Multiple Payments (installment 2/2 for INV229)

**Discrepancy ID:** `DISC-PAY230-MULTIPAY`

**Gateway:** ₹3622.60 installment (G242), ref GW230, customer ORD229

**Bank:** ₹3622.60 settlement (B234), ref GW230

**Ledger:** ₹3622.60 recorded (L244), invoice INV229 (paired total ₹8364.72)

**Expected outcome:** MATCHED via TIER_1 — installment of a multi-payment invoice

**Why this is correct:** Invoice INV229 (total ₹8364.72) was paid in 2 installments. This row is one installment; each installment matches exactly at Tier 1 as an independent transaction.

**Matching tier:** TIER_1

**Remains an exception:** No

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY231 — Ambiguous Candidates (symmetric evidence, 2 identical-amount banks)

**Discrepancy ID:** `DISC-PAY231-AMBIGUOUS`

**Gateway:** ₹4703.80 (G243), ref GW231

**Bank:** Two credits at exactly ₹4703.80: B235 (ref REF-231) and B236 (ref XREF231) — neither ref matches GW231

**Ledger:** ₹4703.80 recorded (L245)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD) — 2 equally plausible banks

**Why this is correct:** Two bank credits both exactly match the gateway/ledger amount, and neither carries a reference or description that distinguishes which belongs to PAY231. System must NOT guess; a human must disambiguate.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY232 — Ambiguous Candidates (symmetric evidence, 2 identical-amount banks)

**Discrepancy ID:** `DISC-PAY232-AMBIGUOUS`

**Gateway:** ₹2314.52 (G244), ref GW232

**Bank:** Two credits at exactly ₹2314.52: B237 (ref REF-232) and B238 (ref XREF232) — neither ref matches GW232

**Ledger:** ₹2314.52 recorded (L246)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD) — 2 equally plausible banks

**Why this is correct:** Two bank credits both exactly match the gateway/ledger amount, and neither carries a reference or description that distinguishes which belongs to PAY232. System must NOT guess; a human must disambiguate.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY233 — Ambiguous Candidates (symmetric evidence, 2 identical-amount banks)

**Discrepancy ID:** `DISC-PAY233-AMBIGUOUS`

**Gateway:** ₹2200.95 (G245), ref GW233

**Bank:** Two credits at exactly ₹2200.95: B239 (ref REF-233) and B240 (ref XREF233) — neither ref matches GW233

**Ledger:** ₹2200.95 recorded (L247)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD) — 2 equally plausible banks

**Why this is correct:** Two bank credits both exactly match the gateway/ledger amount, and neither carries a reference or description that distinguishes which belongs to PAY233. System must NOT guess; a human must disambiguate.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY234 — Ambiguous Candidates (symmetric evidence, 2 identical-amount banks)

**Discrepancy ID:** `DISC-PAY234-AMBIGUOUS`

**Gateway:** ₹3195.42 (G246), ref GW234

**Bank:** Two credits at exactly ₹3195.42: B241 (ref REF-234) and B242 (ref XREF234) — neither ref matches GW234

**Ledger:** ₹3195.42 recorded (L248)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD) — 2 equally plausible banks

**Why this is correct:** Two bank credits both exactly match the gateway/ledger amount, and neither carries a reference or description that distinguishes which belongs to PAY234. System must NOT guess; a human must disambiguate.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY235 — Conflicting Evidence (gateway/bank agree, ledger disagrees)

**Discrepancy ID:** `DISC-PAY235-CONFLICTING`

**Gateway:** ₹7393.89 (G247), ref GW235

**Bank:** ₹7393.89 settlement (B243), ref GW235 — agrees with gateway

**Ledger:** ₹8502.97 recorded (L249) — differs from gateway/bank (gap ₹1109.08)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION)

**Why this is correct:** Gateway and bank agree at ₹7393.89, but the ledger records ₹8502.97 with no tax/fee field explaining the gap. There is no determistic rule to safely reconcile: a human must determine whether the ledger or gateway is correct.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 1109.08 | **Date difference:** 0 days

---

## PAY236 — Conflicting Evidence (gateway/bank agree, ledger disagrees)

**Discrepancy ID:** `DISC-PAY236-CONFLICTING`

**Gateway:** ₹7393.55 (G248), ref GW236

**Bank:** ₹7393.55 settlement (B244), ref GW236 — agrees with gateway

**Ledger:** ₹9241.94 recorded (L250) — differs from gateway/bank (gap ₹1848.39)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION)

**Why this is correct:** Gateway and bank agree at ₹7393.55, but the ledger records ₹9241.94 with no tax/fee field explaining the gap. There is no determistic rule to safely reconcile: a human must determine whether the ledger or gateway is correct.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 1848.39 | **Date difference:** 0 days

---

## PAY237 — Conflicting Evidence (gateway/bank agree, ledger disagrees)

**Discrepancy ID:** `DISC-PAY237-CONFLICTING`

**Gateway:** ₹6092.40 (G249), ref GW237

**Bank:** ₹6092.40 settlement (B245), ref GW237 — agrees with gateway

**Ledger:** ₹7006.26 recorded (L251) — differs from gateway/bank (gap ₹913.86)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION)

**Why this is correct:** Gateway and bank agree at ₹6092.40, but the ledger records ₹7006.26 with no tax/fee field explaining the gap. There is no determistic rule to safely reconcile: a human must determine whether the ledger or gateway is correct.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 913.86 | **Date difference:** 0 days

---

## PAY238 — Conflicting Evidence (gateway/bank agree, ledger disagrees)

**Discrepancy ID:** `DISC-PAY238-CONFLICTING`

**Gateway:** ₹4122.07 (G250), ref GW238

**Bank:** ₹4122.07 settlement (B246), ref GW238 — agrees with gateway

**Ledger:** ₹4451.84 recorded (L252) — differs from gateway/bank (gap ₹329.77)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (CONTRADICTORY_EVIDENCE_NO_EXPLANATION)

**Why this is correct:** Gateway and bank agree at ₹4122.07, but the ledger records ₹4451.84 with no tax/fee field explaining the gap. There is no determistic rule to safely reconcile: a human must determine whether the ledger or gateway is correct.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 329.77 | **Date difference:** 0 days

---

## PAY239 — Adversarial Decoy (plausible bank row is not same payment)

**Discrepancy ID:** `DISC-PAY239-ADVERSARIAL`

**Gateway:** ₹8803.78 (G251), ref GW239

**Bank:** ₹8803.78 decoy (B247), ref 'UNKNOWN', desc 'Unidentified inward credit' — same amount but no reference connection to GW239

**Ledger:** ₹8803.78 recorded (L253)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (WEAK_EVIDENCE_INSUFFICIENT — lone amount match, no reference corroboration)

**Why this is correct:** A bank credit at exactly ₹8803.78 exists, matching the amount, but its reference ('UNKNOWN') bears no transformable relationship to GW239 and its description does not contain the invoice/customer reference. Matching on amount alone, without any corroborating reference, is unsafe — must be reviewed.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY240 — Adversarial Decoy (plausible bank row is not same payment)

**Discrepancy ID:** `DISC-PAY240-ADVERSARIAL`

**Gateway:** ₹7121.08 (G252), ref GW240

**Bank:** ₹7121.08 decoy (B248), ref 'NEFT-10240', desc 'NEFT inward - UNIDENTIFIED' — same amount but no reference connection to GW240

**Ledger:** ₹7121.08 recorded (L254)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (WEAK_EVIDENCE_INSUFFICIENT — lone amount match, no reference corroboration)

**Why this is correct:** A bank credit at exactly ₹7121.08 exists, matching the amount, but its reference ('NEFT-10240') bears no transformable relationship to GW240 and its description does not contain the invoice/customer reference. Matching on amount alone, without any corroborating reference, is unsafe — must be reviewed.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY241 — Adversarial Decoy (plausible bank row is not same payment)

**Discrepancy ID:** `DISC-PAY241-ADVERSARIAL`

**Gateway:** ₹8443.23 (G253), ref GW241

**Bank:** ₹8443.23 decoy (B249), ref 'UNKNOWN', desc 'Unidentified inward credit' — same amount but no reference connection to GW241

**Ledger:** ₹8443.23 recorded (L255)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (WEAK_EVIDENCE_INSUFFICIENT — lone amount match, no reference corroboration)

**Why this is correct:** A bank credit at exactly ₹8443.23 exists, matching the amount, but its reference ('UNKNOWN') bears no transformable relationship to GW241 and its description does not contain the invoice/customer reference. Matching on amount alone, without any corroborating reference, is unsafe — must be reviewed.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY242 — Adversarial Decoy (plausible bank row is not same payment)

**Discrepancy ID:** `DISC-PAY242-ADVERSARIAL`

**Gateway:** ₹3275.53 (G254), ref GW242

**Bank:** ₹3275.53 decoy (B250), ref 'NEFT-10242', desc 'NEFT inward - UNIDENTIFIED' — same amount but no reference connection to GW242

**Ledger:** ₹3275.53 recorded (L256)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (WEAK_EVIDENCE_INSUFFICIENT — lone amount match, no reference corroboration)

**Why this is correct:** A bank credit at exactly ₹3275.53 exists, matching the amount, but its reference ('NEFT-10242') bears no transformable relationship to GW242 and its description does not contain the invoice/customer reference. Matching on amount alone, without any corroborating reference, is unsafe — must be reviewed.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 0.00 | **Date difference:** 0 days

---

## PAY243 — GST Incorrect (claimed GST does not explain variance)

**Discrepancy ID:** `DISC-PAY243-GST-INCORRECT`

**Gateway:** ₹4462.52 (G255), ref GW243

**Bank:** ₹4233.08 actual settlement (B251), ref GW243 — gap ₹229.44

**Ledger:** ₹4462.52 recorded, gst_amount claimed ₹223.13 (L257); gw+claimed_gst=4685.65 ≠ bank 4233.08

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (GST rule fails; no other deterministic rule resolves)

**Why this is correct:** Ledger claims gst_amount = ₹223.13, but 4462.52 + 223.13 = 4685.65 ≠ bank 4233.08 (error -452.57). A human must check: wrong GST rate, mis-booked ledger, or bank-side adjustment.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 229.44 | **Date difference:** 0 days

---

## PAY244 — GST Incorrect (claimed GST does not explain variance)

**Discrepancy ID:** `DISC-PAY244-GST-INCORRECT`

**Gateway:** ₹4614.25 (G256), ref GW244

**Bank:** ₹5580.91 actual settlement (B252), ref GW244 — gap ₹966.66

**Ledger:** ₹4614.25 recorded, gst_amount claimed ₹553.71 (L258); gw+claimed_gst=5167.96 ≠ bank 5580.91

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (GST rule fails; no other deterministic rule resolves)

**Why this is correct:** Ledger claims gst_amount = ₹553.71, but 4614.25 + 553.71 = 5167.96 ≠ bank 5580.91 (error 412.95). A human must check: wrong GST rate, mis-booked ledger, or bank-side adjustment.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 966.66 | **Date difference:** 0 days

---

## PAY245 — GST Incorrect (claimed GST does not explain variance)

**Discrepancy ID:** `DISC-PAY245-GST-INCORRECT`

**Gateway:** ₹10220.12 (G257), ref GW245

**Bank:** ₹12484.04 actual settlement (B253), ref GW245 — gap ₹2263.92

**Ledger:** ₹10220.12 recorded, gst_amount claimed ₹1839.62 (L259); gw+claimed_gst=12059.74 ≠ bank 12484.04

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (GST rule fails; no other deterministic rule resolves)

**Why this is correct:** Ledger claims gst_amount = ₹1839.62, but 10220.12 + 1839.62 = 12059.74 ≠ bank 12484.04 (error 424.30). A human must check: wrong GST rate, mis-booked ledger, or bank-side adjustment.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 2263.92 | **Date difference:** 0 days

---

## PAY246 — GST Incorrect (claimed GST does not explain variance)

**Discrepancy ID:** `DISC-PAY246-GST-INCORRECT`

**Gateway:** ₹4432.78 (G258), ref GW246

**Bank:** ₹5087.44 actual settlement (B254), ref GW246 — gap ₹654.66

**Ledger:** ₹4432.78 recorded, gst_amount claimed ₹797.90 (L260); gw+claimed_gst=5230.68 ≠ bank 5087.44

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (GST rule fails; no other deterministic rule resolves)

**Why this is correct:** Ledger claims gst_amount = ₹797.90, but 4432.78 + 797.90 = 5230.68 ≠ bank 5087.44 (error -143.24). A human must check: wrong GST rate, mis-booked ledger, or bank-side adjustment.

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 654.66 | **Date difference:** 0 days

---

## PAY247 — LLM Recommendation Rejected (ambiguous split; validation safety)

**Discrepancy ID:** `DISC-PAY247-LLM-REJECTED`

**Gateway:** ₹13727.34 (G259), ref GW247

**Bank:** Three bank credits at same ref GW247: ₹7548.82 (B255) + ₹6176.30 (B256) = ₹13725.12 (gap 2.22 — plausible split); decoy ₹1724.88 (B257) also at GW247

**Ledger:** ₹13727.34 recorded (L261)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (offline: LLM_UNAVAILABLE; with LLM: recommendation validated only if arithmetic + candidate checks pass)

**Why this is correct:** One 2-row combination sums within ₹5.00 of the gateway, but a third bank row at the same reference creates ambiguity (LLM may recommend the wrong pair). The system independently re-derives the sum — a wrong recommendation is rejected. Offline without an LLM, this is HUMAN_REVIEW (LLM unavailable for split adjudication).

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 2.22 | **Date difference:** 0 days

---

## PAY248 — LLM Recommendation Rejected (ambiguous split; validation safety)

**Discrepancy ID:** `DISC-PAY248-LLM-REJECTED`

**Gateway:** ₹10142.73 (G260), ref GW248

**Bank:** Three bank credits at same ref GW248: ₹5577.64 (B258) + ₹4563.53 (B259) = ₹10141.17 (gap 1.56 — plausible split); decoy ₹1693.02 (B260) also at GW248

**Ledger:** ₹10142.73 recorded (L262)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (offline: LLM_UNAVAILABLE; with LLM: recommendation validated only if arithmetic + candidate checks pass)

**Why this is correct:** One 2-row combination sums within ₹5.00 of the gateway, but a third bank row at the same reference creates ambiguity (LLM may recommend the wrong pair). The system independently re-derives the sum — a wrong recommendation is rejected. Offline without an LLM, this is HUMAN_REVIEW (LLM unavailable for split adjudication).

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 1.56 | **Date difference:** 0 days

---

## PAY249 — LLM Recommendation Rejected (ambiguous split; validation safety)

**Discrepancy ID:** `DISC-PAY249-LLM-REJECTED`

**Gateway:** ₹8048.36 (G261), ref GW249

**Bank:** Three bank credits at same ref GW249: ₹4424.50 (B261) + ₹3620.05 (B262) = ₹8044.55 (gap 3.81 — plausible split); decoy ₹789.69 (B263) also at GW249

**Ledger:** ₹8048.36 recorded (L263)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (offline: LLM_UNAVAILABLE; with LLM: recommendation validated only if arithmetic + candidate checks pass)

**Why this is correct:** One 2-row combination sums within ₹5.00 of the gateway, but a third bank row at the same reference creates ambiguity (LLM may recommend the wrong pair). The system independently re-derives the sum — a wrong recommendation is rejected. Offline without an LLM, this is HUMAN_REVIEW (LLM unavailable for split adjudication).

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 3.81 | **Date difference:** 0 days

---

## PAY250 — LLM Recommendation Rejected (ambiguous split; validation safety)

**Discrepancy ID:** `DISC-PAY250-LLM-REJECTED`

**Gateway:** ₹8954.36 (G262), ref GW250

**Bank:** Three bank credits at same ref GW250: ₹4926.50 (B264) + ₹4030.77 (B265) = ₹8957.27 (gap 2.91 — plausible split); decoy ₹1950.33 (B266) also at GW250

**Ledger:** ₹8954.36 recorded (L264)

**Expected outcome:** EXCEPTION via TIER_3 HUMAN_REVIEW (offline: LLM_UNAVAILABLE; with LLM: recommendation validated only if arithmetic + candidate checks pass)

**Why this is correct:** One 2-row combination sums within ₹5.00 of the gateway, but a third bank row at the same reference creates ambiguity (LLM may recommend the wrong pair). The system independently re-derives the sum — a wrong recommendation is rejected. Offline without an LLM, this is HUMAN_REVIEW (LLM unavailable for split adjudication).

**Matching tier:** TIER_3 (human review)

**Remains an exception:** Yes

**Amount difference:** 2.91 | **Date difference:** 0 days

---
