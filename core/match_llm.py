"""
LedgerLoop — Phase 5: Tier 3 LLM-Assisted Adjudication
==========================================================

Consumes ONLY the residue left behind by Tier 2 (`match_fuzzy.get_tier2_residue()`)
and produces a final, human-auditable disposition for each residue transaction:

    MATCH           — safe to treat as reconciled
    HUMAN_REVIEW     — evidence is ambiguous / conflicting / insufficient; a
                        person must decide
    UNRESOLVED       — no usable evidence exists at all (nothing for a human
                        to adjudicate either — e.g. a true orphan)

GUIDING PRINCIPLE (unchanged from Tier 1/2, extended one more time)
------------------------------------------------------------------------
"An unresolved transaction is better than an incorrect financial match."

Tier 1 asked "are these obviously identical?" Tier 2 asked "is there enough
small, explicit tolerance to safely say so?" Tier 3 asks a narrower question
than either: "even though no deterministic rule already resolves this, is
there still enough *directly provable* evidence in the records themselves
(a linked refund row, a TDS field, a free-text description, a split
settlement) to safely conclude a match — and if an LLM is used to help
notice/combine that evidence, does the conclusion still hold up once
verified independently in code?"

STRICT ARCHITECTURAL BOUNDARY
-------------------------------
Tier 3 DOES:
    - operate ONLY on Tier 2's residue (`get_tier2_residue()` output)
    - respect Tier 1's and Tier 2's consumption bookkeeping; a bank row
      already claimed by either tier is permanently unavailable here
    - apply its own additional one-to-one consumption on top of both
    - attempt a small, closed set of DETERMINISTIC, directly-provable
      relationships FIRST, without ever calling an LLM, whenever the
      evidence is exact:
          * REFUND_LINKED_NET_AMOUNT   (gateway + linked -REFUND row net to
                                         the bank settlement, exactly)
          * TDS_LINKED_NET_AMOUNT       (gateway amount minus the ledger's
                                         own tds_amount equals the bank
                                         settlement, exactly)
          * DESCRIPTION_LINKED_REFERENCE (bank free-text description
                                         contains the ledger invoice
                                         reference or gateway customer
                                         reference, AND the amount matches
                                         exactly, AND the candidate is
                                         unique)
    - only consult an LLM for the narrow remainder where the evidence is
      real but requires combining multiple weak signals that no closed
      deterministic rule above already resolves (e.g. a split settlement
      across two bank credits whose sum is merely *close* to the gateway
      amount) — this is "LLM_AMBIGUOUS_MATCH" territory
    - treat every LLM response as a RECOMMENDATION ONLY: before any MATCH
      is finalized, the underlying arithmetic is independently
      recomputed in this module from the raw records (never taken on the
      LLM's word), the referenced bank rows must belong to the small,
      pre-vetted candidate set already gathered deterministically (never
      "any row the LLM liked"), and the rows must still be available
      (not already consumed)
    - route to HUMAN_REVIEW whenever evidence is symmetric, missing a
      distinguishing field, contradictory, or the LLM's recommendation
      fails independent validation
    - route to UNRESOLVED only when there is no candidate evidence at all
      for a human to even look at (true orphans, decoys, genuine
      NO_BANK_COUNTERPART cases, or a -REFUND row whose net settlement was
      already explained by its linked original)
    - send only the minimum relevant fields to the LLM (never a raw CSV
      dump) to keep prompts small

Tier 3 DOES NOT:
    - reprocess or override anything Tier 1 or Tier 2 already MATCHED
    - use ground_truth.csv for any matching decision
    - invent a missing reference, description, or amount
    - force a match when more than one candidate/combination is equally
      plausible
    - trust an LLM's stated arithmetic, candidate identity, or confidence
      score in place of independent verification
    - call an LLM for cases that are already deterministically provable
      (saves tokens/calls and keeps the safe rules auditable without any
      model involved) or for cases that are deterministically *hopeless*
      (no candidate evidence exists at all — nothing to investigate)
    - modify any Phase 1-4 source data, canonical record, or prior-tier
      result
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from itertools import combinations
from typing import Optional, Protocol

from core.match_exact import ExactMatcher, Tier1Result
from core.match_fuzzy import Tier2Result, get_tier2_residue
from core.normalize import CanonicalRecord
from core import accounting as accounting_model


logger = logging.getLogger(__name__)


# ===========================================================================
# Status / rule / reason taxonomy
# ===========================================================================

STATUS_MATCH = "MATCH"
STATUS_HUMAN_REVIEW = "HUMAN_REVIEW"
STATUS_UNRESOLVED = "UNRESOLVED"
STATUS_AI_RETRY_REQUIRED = "AI_RETRY_REQUIRED"

RULE_REFUND_LINKED_NET_AMOUNT = "REFUND_LINKED_NET_AMOUNT"
RULE_TDS_LINKED_NET_AMOUNT = "TDS_LINKED_NET_AMOUNT"
RULE_DESCRIPTION_LINKED_REFERENCE = "DESCRIPTION_LINKED_REFERENCE"
RULE_SPLIT_SETTLEMENT_SUM = "SPLIT_SETTLEMENT_SUM"
RULE_GST_DECOMPOSITION = "GST_DECOMPOSITION"
RULE_MDR_FEE_DEDUCTION = "MDR_FEE_DEDUCTION"

REASON_NO_EVIDENCE_AVAILABLE = "NO_EVIDENCE_AVAILABLE"
REASON_AMBIGUOUS_DUPLICATE_CANDIDATES = "AMBIGUOUS_DUPLICATE_CANDIDATES"
REASON_CONTRADICTORY_EVIDENCE_NO_EXPLANATION = "CONTRADICTORY_EVIDENCE_NO_EXPLANATION"
REASON_NO_SEPARATE_SETTLEMENT_EXPECTED = "NO_SEPARATE_SETTLEMENT_EXPECTED"
REASON_LINKED_ORIGINAL_UNRESOLVED = "LINKED_ORIGINAL_UNRESOLVED"
REASON_SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD = "SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD"
REASON_WEAK_EVIDENCE_INSUFFICIENT = "WEAK_EVIDENCE_INSUFFICIENT"
REASON_MULTIPLE_DESCRIPTION_MATCHES = "MULTIPLE_DESCRIPTION_MATCHES"
REASON_CANDIDATE_NO_LONGER_AVAILABLE = "CANDIDATE_NO_LONGER_AVAILABLE"
REASON_TIER2_AMBIGUITY_PRESERVED = "TIER2_AMBIGUITY_PRESERVED"
REASON_LLM_RECOMMENDATION_VALIDATED = "LLM_RECOMMENDATION_VALIDATED"
REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR = "LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR"
REASON_LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
REASON_AI_RETRY_REQUIRED = "AI_RETRY_REQUIRED"
REASON_MISSING_CONFIDENCE = "MISSING_CONFIDENCE"
REASON_INVALID_CONFIDENCE = "INVALID_CONFIDENCE"
REASON_INVALID_STRUCTURED_FIELD = "INVALID_STRUCTURED_FIELD"
REASON_UNCLASSIFIED_RESIDUE = "UNCLASSIFIED_RESIDUE"
REASON_GST_EXPLAINED_VARIANCE = "GST_EXPLAINED_VARIANCE"
REASON_MDR_FEE_EXPLAINED_VARIANCE = "MDR_FEE_EXPLAINED_VARIANCE"

# Small, documented epsilon for exact linked-arithmetic checks (refund netting,
# TDS netting). Phase 2 already rounds every amount to 2 decimals; this just
# absorbs Decimal/float boundary noise, never a real discrepancy.
_EXACT_EPSILON = Decimal("0.01")

# Tolerance for a *split* settlement's summed candidate amounts vs the
# gateway amount. Justified by the one real split-settlement case in the
# dataset (PAY109: gateway 6400.00 vs candidates summing to 6395.50, a
# ₹4.50 / 0.07% gap) — a materially larger, differently-shaped gap than the
# ₹0.05 Tier 2 rounding tolerance, which is why this rule lives in Tier 3
# and is never applied to a single-candidate comparison.
SPLIT_SETTLEMENT_TOLERANCE = Decimal("5.00")


@dataclass
class Tier3Result:
    """
    One structured, final decision per Tier-2-residue transaction. Shape is
    deliberately similar to Tier1Result/Tier2Result for downstream reporting
    consistency, plus explicit LLM-usage bookkeeping for auditability.
    """
    transaction_id: str
    status: str                                # MATCH | HUMAN_REVIEW | UNRESOLVED
    tier: str
    rule: Optional[str]
    matched_records: dict[str, Optional[str]]
    evidence: dict
    reason: Optional[str] = None
    llm_consulted: bool = False
    llm_recommendation: Optional[dict] = None  # raw recommendation, for audit only
    confidence: Optional[float] = None
    decision_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Tier3Summary:
    total_residue_evaluated: int
    match_count: int
    human_review_count: int
    unresolved_count: int
    llm_calls_made: int
    llm_recommendations_validated: int
    llm_recommendations_rejected: int

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# LLM client interface — Tier 3 never trusts this on its own; every MATCH
# recommendation it returns is independently re-derived and re-checked
# below before being accepted.
# ===========================================================================

class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's raw text response (expected to be JSON)."""
        ...


class LLMUnavailableError(Exception):
    """Raised by a client when it cannot be used (e.g. no API key)."""


_AUTO_LLM = object()


class GeminiLLMClient:
    """
    Production client using Google's hosted Gemini API (Google AI Studio),
    via the REST `generateContent` endpoint. Requires `GEMINI_API_KEY` to be
    set in the environment — never hardcoded, never logged, never embedded.
    If the key is missing or the call fails, `complete()` raises
    LLMUnavailableError, which `run_tier3` treats as "no LLM available for
    this case" — never as permission to guess. Implements the same
    `LLMClient` Protocol used by `LLMAdjudicator`/`run_tier3`.
    """

    def __init__(self, model: Optional[str] = None, max_tokens: int = 500,
                 structured: bool = True):
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.max_tokens = max_tokens
        self.structured = structured

    def complete(self, system: str, user: str) -> str:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("Gemini API unavailable: category=missing_api_key")
            raise LLMUnavailableError("GEMINI_API_KEY is not set")

        import urllib.request
        import urllib.error

        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
            },
        }
        if self.structured:
            payload["generationConfig"].update({
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "decision": {
                            "type": "STRING",
                            "enum": ["MATCH", "HUMAN_REVIEW", "UNRESOLVED"],
                        },
                        "bank_row_ids": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                        },
                        "confidence": {
                            "type": "NUMBER",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "rationale": {"type": "STRING"},
                        "evidence": {"type": "OBJECT"},
                        "adjustment": {"type": "OBJECT"},
                    },
                    "required": [
                        "decision", "bank_row_ids", "confidence", "rationale",
                        "evidence", "adjustment",
                    ],
                },
            })
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.warning(
                "Gemini API unavailable: category=http_error http_status=%s",
                e.code,
            )
            raise LLMUnavailableError(f"Gemini API HTTP {e.code}: {error_body[:500]}") from e
        except urllib.error.URLError as e:
            logger.warning(
                "Gemini API unavailable: category=url_error reason_type=%s",
                type(e.reason).__name__,
            )
            raise LLMUnavailableError(f"Gemini API call failed: {e}") from e
        except (TimeoutError, OSError) as e:
            logger.warning("Gemini API unavailable: category=timeout")
            raise LLMUnavailableError(f"Gemini API call failed: {e}") from e
        except json.JSONDecodeError as e:
            logger.warning("Gemini API unavailable: category=invalid_json")
            raise LLMUnavailableError(f"Gemini API returned invalid JSON: {e}") from e

        try:
            candidates = body.get("candidates", [])
            parts = candidates[0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (IndexError, KeyError, TypeError) as e:
            logger.warning("Gemini API unavailable: category=invalid_response_shape")
            raise LLMUnavailableError(f"Gemini API returned an unexpected shape: {e}") from e


# ===========================================================================
# Small helpers
# ===========================================================================

def _amounts_close(a: Optional[float], b: Optional[float],
                    epsilon: Decimal = _EXACT_EPSILON) -> bool:
    if a is None or b is None:
        return False
    return abs(Decimal(str(a)) - Decimal(str(b))) <= epsilon


def _ref_value(record: CanonicalRecord, key: str) -> Optional[str]:
    ref = record.secondary_references.get(key)
    return ref.normalized if ref and ref.normalized else None


def _minimal_gateway(gw: CanonicalRecord) -> dict:
    return {
        "source_row_id": gw.source_row_id,
        "payment_id": gw.transaction_reference.normalized,
        "amount": gw.amount.normalized,
        "gateway_reference": _ref_value(gw, "gateway_reference"),
        "customer_reference": _ref_value(gw, "customer_reference"),
    }


def _minimal_ledger(ledger: CanonicalRecord) -> dict:
    tds = ledger.tax_fields.get("tds_amount")
    return {
        "source_row_id": ledger.source_row_id,
        "payment_reference": ledger.transaction_reference.normalized,
        "recorded_amount": ledger.amount.normalized,
        "invoice_reference": _ref_value(ledger, "invoice_reference"),
        "tds_amount": tds.normalized if tds else None,
    }


def _minimal_bank(bank: CanonicalRecord) -> dict:
    return {
        "source_row_id": bank.source_row_id,
        "bank_reference": _ref_value(bank, "bank_reference"),
        "amount": bank.amount.normalized,
        "description": _ref_value(bank, "description"),
        "date": bank.date.normalized,
    }


# ===========================================================================
# Core Tier 3 adjudicator
# ===========================================================================

class LLMAdjudicator:
    """
    Stateful adjudicator enforcing:
        - Tier 1 + Tier 2 consumption is respected (never re-offers a bank
          row either tier already claimed)
        - Tier 3's own one-to-one consumption on top of that
        - deterministic, directly-provable rules are always tried BEFORE
          any LLM is consulted, and resolve the large majority of real
          residue without any model call at all
        - every LLM MATCH recommendation is independently re-validated
          against the raw records before being accepted
    """

    def __init__(self, tier1_matcher: ExactMatcher, tier2_results: list[Tier2Result],
                 llm_client: Optional[LLMClient] = None,
                 extra_consumed: Optional[set[str]] = None):
        self.gw_by_row_id = {r.source_row_id: r for r in tier1_matcher.gateway_records}
        self.bank_by_row_id = {r.source_row_id: r for r in tier1_matcher.bank_records}
        self.ledger_by_row_id = {r.source_row_id: r for r in tier1_matcher.ledger_records}
        self.all_bank_records = list(tier1_matcher.bank_records)

        already_consumed = set(tier1_matcher._consumed_bank_row_ids)
        for r in tier2_results:
            if r.status == "MATCHED" and r.matched_records.get("bank"):
                already_consumed.add(r.matched_records["bank"])
        if extra_consumed:
            already_consumed |= set(extra_consumed)
        self._consumed_bank_row_ids: set[str] = already_consumed

        self.llm_client = llm_client
        self.llm_calls_made = 0
        self.llm_validated = 0
        self.llm_rejected = 0

    # -- availability ----------------------------------------------------

    def _is_available(self, bank_row_id: str) -> bool:
        return bank_row_id not in self._consumed_bank_row_ids

    def _consume(self, bank_row_id: str) -> None:
        self._consumed_bank_row_ids.add(bank_row_id)

    # -- rule attempts (all deterministic, no LLM) ------------------------

    def _try_tds_linked(self, gw: CanonicalRecord, ledger: CanonicalRecord,
                         candidate_bank_ids: list[str]) -> Optional[str]:
        tds = ledger.tax_fields.get("tds_amount")
        if not tds or tds.normalized is None or tds.normalized <= 0 or gw.amount.normalized is None:
            return None
        # Reuse the shared settlement layer (gross - tds = expected bank).
        expected = accounting_model.compute_expected_net(
            gw.amount.normalized, tds=tds.normalized)
        for bid in candidate_bank_ids:
            if not self._is_available(bid):
                continue
            bank = self.bank_by_row_id[bid]
            if _amounts_close(float(expected), bank.amount.normalized):
                return bid
        return None

    def _try_refund_linked(self, gw: CanonicalRecord, refund_ledger: Optional[CanonicalRecord],
                            candidate_bank_ids: list[str]) -> Optional[str]:
        if refund_ledger is None or gw.amount.normalized is None:
            return None
        # Ledger refund entries carry a negative amount; reduce it to a
        # positive magnitude for the shared settlement layer
        # (gross - refund_magnitude == gross + signed_refund).
        signed = refund_ledger.amount.normalized
        refund_magnitude = abs(Decimal(str(signed))) if signed is not None and signed < 0 else Decimal("0")
        expected = accounting_model.compute_expected_net(
            gw.amount.normalized, refund=refund_magnitude)
        for bid in candidate_bank_ids:
            if not self._is_available(bid):
                continue
            bank = self.bank_by_row_id[bid]
            if _amounts_close(float(expected), bank.amount.normalized):
                return bid
        return None

    def _description_candidates(self, gw: CanonicalRecord, ledger: CanonicalRecord) -> list[str]:
        invoice_ref = _ref_value(ledger, "invoice_reference")
        customer_ref = _ref_value(gw, "customer_reference")
        needles = [n for n in (invoice_ref, customer_ref) if n]
        if not needles:
            return []
        found = []
        for bank in self.all_bank_records:
            if not self._is_available(bank.source_row_id):
                continue
            desc = _ref_value(bank, "description")
            if not desc:
                continue
            haystack = desc.upper()
            if any(n in haystack for n in needles) and _amounts_close(gw.amount.normalized, bank.amount.normalized):
                found.append(bank.source_row_id)
        return found

    def _try_gst_decomposition(self, gw: CanonicalRecord, ledger: CanonicalRecord,
                                   candidate_bank_ids: list[str]) -> Optional[str]:
        """Check if gateway amount plus GST equals bank amount (via shared layer)."""
        gst = ledger.tax_fields.get("gst_amount")
        if not gst or gst.normalized is None or gst.normalized <= 0 or gw.amount.normalized is None:
            return None
        # gross + gst = expected bank (gateway gross is pre-GST taxable base).
        expected = accounting_model.compute_expected_net(
            gw.amount.normalized, gst=gst.normalized)
        for bid in candidate_bank_ids:
            if not self._is_available(bid):
                continue
            bank = self.bank_by_row_id[bid]
            if _amounts_close(float(expected), bank.amount.normalized):
                return bid
        return None

    def _try_mdr_fee_decomposition(self, gw: CanonicalRecord, ledger: CanonicalRecord,
                                   candidate_bank_ids: list[str]) -> Optional[str]:
        """Check if gateway amount minus MDR/fees equals bank amount (via shared layer)."""
        mdr = ledger.tax_fields.get("mdr_amount")
        mdr_gst = ledger.tax_fields.get("mdr_gst")
        fee = ledger.tax_fields.get("fee_amount")
        if gw.amount.normalized is None:
            return None
        mdr_val = Decimal(str(mdr.normalized)) if mdr and mdr.normalized and mdr.normalized > 0 else Decimal("0")
        mdr_gst_val = Decimal(str(mdr_gst.normalized)) if mdr_gst and mdr_gst.normalized and mdr_gst.normalized > 0 else Decimal("0")
        fee_val = Decimal(str(fee.normalized)) if fee and fee.normalized and fee.normalized > 0 else Decimal("0")
        if mdr_val == 0 and mdr_gst_val == 0 and fee_val == 0:
            return None
        # gross - mdr - mdr_gst - fee = expected bank.
        expected = accounting_model.compute_expected_net(
            gw.amount.normalized, mdr=mdr_val, mdr_gst=mdr_gst_val, fee=fee_val)
        for bid in candidate_bank_ids:
            if not self._is_available(bid):
                continue
            bank = self.bank_by_row_id[bid]
            if _amounts_close(float(expected), bank.amount.normalized):
                return bid
        return None

    def _amount_matching_available_candidates(self, gw: CanonicalRecord) -> list[str]:
        return [
            b.source_row_id for b in self.all_bank_records
            if self._is_available(b.source_row_id)
            and _amounts_close(gw.amount.normalized, b.amount.normalized)
        ]

    # -- LLM-assisted split-settlement investigation ----------------------

    def _investigate_split_settlement(
        self, txn_id: str, gw: CanonicalRecord, ledger: CanonicalRecord,
        candidate_bank_ids: list[str],
    ) -> tuple[Optional[list[str]], Optional[dict], Optional[str]]:
        """
        Returns (validated_matched_bank_ids, raw_llm_recommendation, reason).
        `reason` is populated only on the non-match path, so callers can
        report precisely why (no plausible combination at all vs. LLM
        unavailable vs. LLM recommendation rejected by validation). Only
        ever considers combinations drawn from `candidate_bank_ids` — the
        pre-vetted, reference-transform-matched set Tier 2 already
        gathered — never an arbitrary bank row.
        """
        available = [b for b in candidate_bank_ids if self._is_available(b)]
        if len(available) < 2:
            return None, None, REASON_WEAK_EVIDENCE_INSUFFICIENT

        # Deterministic pre-check: does ANY 2+ subset sum within tolerance?
        # If not, there's nothing for an LLM to validate either — skip the
        # call entirely (never spend a call chasing evidence that can't
        # exist).
        plausible_combos = []
        # Check 2, 3, and 4 row combinations (up to 4 rows)
        max_combo_size = min(4, len(available))
        for size in range(2, max_combo_size + 1):
            for combo in combinations(available, size):
                total = sum(Decimal(str(self.bank_by_row_id[b].amount.normalized)) for b in combo)
                if abs(total - Decimal(str(gw.amount.normalized))) <= SPLIT_SETTLEMENT_TOLERANCE:
                    plausible_combos.append(combo)

        if not plausible_combos:
            return None, None, REASON_WEAK_EVIDENCE_INSUFFICIENT

        if self.llm_client is None:
            return None, None, REASON_LLM_UNAVAILABLE

        prompt_payload = {
            "gateway_payment": _minimal_gateway(gw),
            "ledger_entry": _minimal_ledger(ledger),
            "candidate_bank_credits": [
                _minimal_bank(self.bank_by_row_id[b]) for b in available
            ],
            "question": (
                "Do two or more of these bank credits together represent a "
                "single split settlement of the gateway payment above? If "
                "so, name exactly which source_row_ids belong together."
            ),
        }
        system = (
            "You are assisting a payment-reconciliation system. You only "
            "ever see the minimal record excerpts provided. Respond with "
            "ONLY a JSON object matching this exact schema: "
            '{"decision": "<MATCH|HUMAN_REVIEW|UNRESOLVED>", '
            '"bank_row_ids": ["<source_row_id>", ...], '
            '"confidence": <number from 0.0 to 1.0>, '
            '"rationale": "<explanation>", '
            '"evidence": {}, "adjustment": {}}. '
            "The decision field MUST be one of: MATCH, HUMAN_REVIEW, "
            "UNRESOLVED. The bank_row_ids field MUST be a JSON array of "
            "strings matching source_row_ids from the candidates provided. "
            "Never invent a source_row_id that was not given to you. "
            "Do NOT wrap the JSON in markdown fences or prose. "
            "If evidence is symmetric, missing, or contradictory, respond "
            "HUMAN_REVIEW."
        )

        self.llm_calls_made += 1
        try:
            raw = self.llm_client.complete(system, json.dumps(prompt_payload))
        except LLMUnavailableError:
            return None, None, REASON_LLM_UNAVAILABLE

        recommendation = self._parse_llm_json(raw)
        if recommendation is None:
            self.llm_rejected += 1
            return None, {"decision": "HUMAN_REVIEW", "rationale": "unparseable LLM response"}, \
                REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR

        validated, validation_reason = self._validate_split_recommendation(recommendation, gw, available)
        if validated is not None:
            self.llm_validated += 1
            return validated, recommendation, None
        self.llm_rejected += 1
        # Include the specific validation failure reason
        return None, recommendation, validation_reason or REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR

    @staticmethod
    def _parse_llm_json(raw: str) -> Optional[dict]:
        """Parse an LLM response that is expected to contain a JSON object.

        Handles the common patterns returned by free / chat-tuned models:
          - plain JSON: {"decision": "MATCH", ...}
          - markdown-fenced: ```json\\n{...}\\n```
          - markdown-fenced without language tag: ```\\n{...}\\n```
          - leading/trailing prose around a JSON block (extracts the
            first ``{...}`` substring as a last resort)

        Returns None when the input is empty/None or no valid JSON object
        can be extracted. Never raises.
        """
        if not raw:
            return None

        text = raw.strip()

        # Fast path: plain JSON (no backticks)
        if not text.startswith("```"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        else:
            # Strip markdown code fences — handles both
            # ```json\n{...}\n``` and ```\n{...}\n```, including a closing
            # fence that sits directly after the JSON (no newline before it).
            text = "\n".join(text.split("\n")[1:]).strip()
            if text.endswith("```"):
                text = text[:-3].rstrip()
            text = text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Last resort: extract the first balanced {...} block, which handles
        # prose wrapped around the JSON. Returns None if none can be found.
        if "{" not in text:
            return None
        start = text.index("{")
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def _validate_split_recommendation(self, recommendation: dict, gw: CanonicalRecord,
                                        available_candidate_ids: list[str]) -> tuple[Optional[list[str]], Optional[str]]:
        """
        Independently re-derives the split-settlement arithmetic from the
        RAW records. Never trusts the LLM's stated sum, rationale, or
        confidence — only the set of source_row_ids it proposes, and only
        if every one of those ids:
            (a) was in the pre-vetted candidate set (never an invented row)
            (b) is still available (not consumed by an earlier decision)
            (c) sums, together, within SPLIT_SETTLEMENT_TOLERANCE of the
                gateway amount (recomputed here, not taken from the LLM)

        Returns (validated_ids, rejection_reason). rejection_reason is a
        categorized validation failure reason for diagnostics.
        """
        if recommendation.get("decision") != "MATCH":
            return None, "NON_MATCH_DECISION"
        confidence = recommendation.get("confidence")
        if confidence is None:
            return None, REASON_MISSING_CONFIDENCE
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None, REASON_INVALID_CONFIDENCE
        if not 0.0 <= confidence <= 1.0:
            return None, REASON_INVALID_CONFIDENCE
        for field_name in ("evidence", "adjustment"):
            value = recommendation.get(field_name, {})
            if not isinstance(value, dict):
                return None, REASON_INVALID_STRUCTURED_FIELD
        ids = recommendation.get("bank_row_ids")
        if not isinstance(ids, list) or len(ids) < 2:
            return None, "INSUFFICIENT_BANK_ROWS"
        if any(not isinstance(i, str) for i in ids):
            return None, "INVALID_BANK_ROW_ID"
        if any(i not in available_candidate_ids for i in ids):
            return None, "CANDIDATE_NOT_AVAILABLE"
        if len(set(ids)) != len(ids):
            return None, "DUPLICATE_BANK_ROW_ID"

        # Check all rows are still available
        for i in ids:
            if not self._is_available(i):
                return None, "CANDIDATE_NO_LONGER_AVAILABLE"

        total = sum(Decimal(str(self.bank_by_row_id[i].amount.normalized)) for i in ids)
        if abs(total - Decimal(str(gw.amount.normalized))) > SPLIT_SETTLEMENT_TOLERANCE:
            return None, "SUM_OUTSIDE_TOLERANCE"
        return ids, None

    # -- top-level per-transaction resolution -----------------------------

    def resolve(self, r: Tier2Result,
                tier3_by_txn: dict[str, "Tier3Result"]) -> Tier3Result:
        txn_id = r.transaction_id
        gw_id = r.matched_records.get("gateway")
        ledger_id = r.matched_records.get("ledger")
        bank_id = r.matched_records.get("bank")
        gw = self.gw_by_row_id.get(gw_id) if gw_id else None

        # ---- Case: Tier 2 wrapped an ineligible Tier 1 status verbatim ----
        if r.reason == "NOT_ELIGIBLE_FOR_TIER_2":
            tier1_status = r.evidence.get("tier1_status")
            tier1_reason = r.evidence.get("tier1_reason")

            if tier1_reason == "MULTIPLE_EXACT_CANDIDATES":
                return self._result(
                    txn_id, STATUS_HUMAN_REVIEW, None, r.matched_records,
                    {"tier1_reason": tier1_reason},
                    REASON_AMBIGUOUS_DUPLICATE_CANDIDATES,
                )

            if tier1_status == "PARTIAL_MATCH" and bank_id and not ledger_id:
                return self._resolve_bank_present_ledger_missing(txn_id, gw, bank_id, r)

            # true orphan / decoy / gateway-side contention: nothing at all
            return self._result(
                txn_id, STATUS_UNRESOLVED, None, r.matched_records,
                {"tier1_status": tier1_status, "tier1_reason": tier1_reason},
                REASON_NO_EVIDENCE_AVAILABLE,
            )

        # ---- Case: Tier 2 found ambiguity of its own ----
        if r.status == "AMBIGUOUS":
            return self._result(
                txn_id, STATUS_HUMAN_REVIEW, None, r.matched_records,
                {"tier2_candidate_count": len(r.candidate_records)},
                REASON_TIER2_AMBIGUITY_PRESERVED,
            )

        # ---- Case: reference matched, amount didn't (Tier 2's rejection) ----
        if r.reason == "REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE":
            return self._resolve_reference_matched_amount_out_of_tolerance(
                txn_id, gw, ledger_id, r
            )

        # ---- Case: no reference-transform candidate at all ----
        if r.reason == "NO_REFERENCE_TRANSFORM_MATCH":
            return self._resolve_no_reference_transform_match(
                txn_id, gw, ledger_id, r, tier3_by_txn
            )

        # ---- Fallback: anything not explicitly classified above ----
        return self._result(
            txn_id, STATUS_HUMAN_REVIEW, None, r.matched_records,
            {"tier2_reason": r.reason, "tier2_status": r.status},
            REASON_UNCLASSIFIED_RESIDUE,
        )

    # -- sub-resolvers ------------------------------------------------------

    def _resolve_bank_present_ledger_missing(self, txn_id: str, gw: CanonicalRecord,
                                              bank_id: str, r: Tier2Result) -> Tier3Result:
        """
        Tier 1 already found an exact-reference, exact-amount BANK match,
        but no ledger row satisfied Tier 1's exact rule. Investigate
        whether any ledger row sharing this payment_reference has a
        TDS-explainable gap; otherwise this is contradictory evidence that
        needs a human.
        """
        bank = self.bank_by_row_id[bank_id]
        ledger_candidates = [
            l for l in self.ledger_by_row_id.values()
            if l.transaction_reference.normalized == txn_id
        ]
        if not ledger_candidates:
            return self._result(
                txn_id, STATUS_UNRESOLVED, None, r.matched_records,
                {"gateway_amount": gw.amount.normalized, "bank_amount": bank.amount.normalized},
                REASON_NO_EVIDENCE_AVAILABLE,
            )

        for ledger in ledger_candidates:
            tds = ledger.tax_fields.get("tds_amount")
            # A TDS explanation is only valid if the ledger's own recorded
            # (gross) amount agrees with the gateway's gross amount in the
            # first place -- otherwise the ledger row itself is in
            # conflict with the gateway/bank, and no tds_amount value can
            # explain that away (this is exactly PAY110's shape: tds_amount
            # is 0.00, so a naive "gateway - tds == bank" check would
            # trivially "pass" whenever gateway == bank, even though the
            # LEDGER amount is the thing that doesn't reconcile).
            if not _amounts_close(gw.amount.normalized, ledger.amount.normalized):
                continue
            if tds and tds.normalized is not None and tds.normalized > 0:
                expected = Decimal(str(gw.amount.normalized)) - Decimal(str(tds.normalized))
                if _amounts_close(float(expected), bank.amount.normalized):
                    matched = {"gateway": gw.source_row_id, "bank": bank_id,
                               "ledger": ledger.source_row_id}
                    return self._result(
                        txn_id, STATUS_MATCH, RULE_TDS_LINKED_NET_AMOUNT, matched,
                        {
                            "gateway_amount": gw.amount.normalized,
                            "tds_amount": tds.normalized,
                            "bank_amount": bank.amount.normalized,
                        },
                        None,
                    )

        return self._result(
            txn_id, STATUS_HUMAN_REVIEW, None, r.matched_records,
            {
                "gateway_amount": gw.amount.normalized,
                "bank_amount": bank.amount.normalized,
                "ledger_candidates": [
                    {"source_row_id": l.source_row_id, "recorded_amount": l.amount.normalized,
                     "tds_amount": (l.tax_fields.get("tds_amount").normalized
                                    if l.tax_fields.get("tds_amount") else None)}
                    for l in ledger_candidates
                ],
            },
            REASON_CONTRADICTORY_EVIDENCE_NO_EXPLANATION,
        )

    def _resolve_reference_matched_amount_out_of_tolerance(
        self, txn_id: str, gw: CanonicalRecord, ledger_id: str, r: Tier2Result,
    ) -> Tier3Result:
        ledger = self.ledger_by_row_id[ledger_id]
        candidate_ids = [c["source_row_id"] for c in r.candidate_records]

        # Rule 1: TDS-linked net amount.
        tds_match = self._try_tds_linked(gw, ledger, candidate_ids)
        if tds_match:
            self._consume(tds_match)
            bank_rec = self.bank_by_row_id[tds_match]
            settlement = accounting_model.build_settlement_from_ledger(
                gw.amount.normalized, ledger, actual_bank=bank_rec.amount.normalized,
                source_rows={"gateway": gw.source_row_id, "ledger": ledger.source_row_id, "bank": tds_match})
            return self._result(
                txn_id, STATUS_MATCH, RULE_TDS_LINKED_NET_AMOUNT,
                {"gateway": gw.source_row_id, "bank": tds_match, "ledger": ledger_id},
                {"gateway_amount": gw.amount.normalized,
                 "tds_amount": ledger.tax_fields["tds_amount"].normalized,
                 "bank_amount": bank_rec.amount.normalized,
                 "settlement": settlement.to_dict()},
                None,
            )

        # Rule 2: refund-linked net amount (sibling "<id>-REFUND" gateway
        # record, which must itself already have an established ledger
        # match — we never fabricate a refund amount).
        refund_txn_id = txn_id + "-REFUND"
        refund_gw = next(
            (g for g in self.gw_by_row_id.values()
             if g.transaction_reference.normalized == refund_txn_id), None,
        )
        refund_ledger = None
        if refund_gw is not None:
            refund_ledger = next(
                (l for l in self.ledger_by_row_id.values()
                 if l.transaction_reference.normalized == refund_txn_id), None,
            )
        refund_match = self._try_refund_linked(gw, refund_ledger, candidate_ids)
        if refund_match:
            self._consume(refund_match)
            bank_rec = self.bank_by_row_id[refund_match]
            # Compute refund magnitude from the actual refund ledger row
            # (negative recorded_amount → positive magnitude). We use
            # compute_settlement directly here because build_settlement_from_ledger
            # reads the ledger's own amount for the refund field — which works
            # correctly for the refund ledger row but not the original SALE row.
            _rl_amount = refund_ledger.amount.normalized if refund_ledger else None
            _refund_mag = float(abs(Decimal(str(_rl_amount)))) if _rl_amount is not None and _rl_amount < 0 else 0
            settlement = accounting_model.compute_settlement(
                gw.amount.normalized,
                refund=_refund_mag,
                actual_bank=bank_rec.amount.normalized,
                source_rows={
                    "gateway": gw.source_row_id,
                    "ledger": ledger.source_row_id,
                    "bank": refund_match,
                    "refund_ledger": refund_ledger.source_row_id if refund_ledger else None,
                },
            )
            return self._result(
                txn_id, STATUS_MATCH, RULE_REFUND_LINKED_NET_AMOUNT,
                {"gateway": gw.source_row_id, "bank": refund_match, "ledger": ledger_id},
                {"gateway_amount": gw.amount.normalized,
                 "refund_amount": refund_ledger.amount.normalized,
                 "refund_gateway_row": refund_gw.source_row_id,
                 "refund_ledger_row": refund_ledger.source_row_id,
                 "bank_amount": bank_rec.amount.normalized,
                 "settlement": settlement.to_dict()},
                None,
            )

        # Rule 3: GST decomposition (gateway + GST = bank)
        gst_match = self._try_gst_decomposition(gw, ledger, candidate_ids)
        if gst_match:
            self._consume(gst_match)
            bank_rec = self.bank_by_row_id[gst_match]
            settlement = accounting_model.build_settlement_from_ledger(
                gw.amount.normalized, ledger, actual_bank=bank_rec.amount.normalized,
                source_rows={"gateway": gw.source_row_id, "ledger": ledger.source_row_id, "bank": gst_match})
            return self._result(
                txn_id, STATUS_MATCH, RULE_GST_DECOMPOSITION,
                {"gateway": gw.source_row_id, "bank": gst_match, "ledger": ledger_id},
                {"gateway_amount": gw.amount.normalized,
                 "gst_amount": ledger.tax_fields["gst_amount"].normalized,
                 "bank_amount": bank_rec.amount.normalized,
                 "settlement": settlement.to_dict()},
                None,
            )

        # Rule 4: MDR/fee deduction (gateway - MDR - MDR_GST - fee = bank)
        mdr_match = self._try_mdr_fee_decomposition(gw, ledger, candidate_ids)
        if mdr_match:
            self._consume(mdr_match)
            bank_rec = self.bank_by_row_id[mdr_match]
            settlement = accounting_model.build_settlement_from_ledger(
                gw.amount.normalized, ledger, actual_bank=bank_rec.amount.normalized,
                source_rows={"gateway": gw.source_row_id, "ledger": ledger.source_row_id, "bank": mdr_match})
            return self._result(
                txn_id, STATUS_MATCH, RULE_MDR_FEE_DEDUCTION,
                {"gateway": gw.source_row_id, "bank": mdr_match, "ledger": ledger_id},
                {"gateway_amount": gw.amount.normalized,
                 "mdr_amount": ledger.tax_fields.get("mdr_amount").normalized if ledger.tax_fields.get("mdr_amount") else 0,
                 "mdr_gst": ledger.tax_fields.get("mdr_gst").normalized if ledger.tax_fields.get("mdr_gst") else 0,
                 "fee_amount": ledger.tax_fields.get("fee_amount").normalized if ledger.tax_fields.get("fee_amount") else 0,
                 "bank_amount": bank_rec.amount.normalized,
                 "settlement": settlement.to_dict()},
                None,
            )

        # Rule 5 (LLM-assisted, independently validated): split settlement.
        calls_before = self.llm_calls_made
        matched_ids, llm_rec, split_reason = self._investigate_split_settlement(
            txn_id, gw, ledger, candidate_ids,
        )
        llm_was_called = self.llm_calls_made > calls_before
        if matched_ids:
            for bid in matched_ids:
                self._consume(bid)
            total = sum(self.bank_by_row_id[b].amount.normalized for b in matched_ids)
            return self._result(
                txn_id, STATUS_MATCH, RULE_SPLIT_SETTLEMENT_SUM,
                {"gateway": gw.source_row_id, "bank": ",".join(matched_ids), "ledger": ledger_id},
                {"gateway_amount": gw.amount.normalized, "bank_credit_total": total,
                 "bank_row_ids": matched_ids,
                 "llm_evidence": llm_rec.get("evidence", {}) if llm_rec else {},
                 "adjustment": llm_rec.get("adjustment", {}) if llm_rec else {}},
                REASON_LLM_RECOMMENDATION_VALIDATED,
                llm_consulted=True,
                llm_recommendation=llm_rec,
                confidence=llm_rec.get("confidence") if llm_rec else None,
            )

        result_status = STATUS_AI_RETRY_REQUIRED if split_reason == REASON_LLM_UNAVAILABLE else STATUS_HUMAN_REVIEW
        result_reason = REASON_AI_RETRY_REQUIRED if split_reason == REASON_LLM_UNAVAILABLE else split_reason
        return self._result(
            txn_id, result_status, None, r.matched_records,
            {"gateway_amount": gw.amount.normalized,
             "candidates": r.candidate_records},
            result_reason,
            llm_consulted=llm_was_called,
            llm_recommendation=llm_rec,
        )

    def _resolve_no_reference_transform_match(
        self, txn_id: str, gw: CanonicalRecord, ledger_id: str, r: Tier2Result,
        tier3_by_txn: dict[str, "Tier3Result"],
    ) -> Tier3Result:
        ledger = self.ledger_by_row_id[ledger_id]

        if txn_id.endswith("-REFUND"):
            original_id = txn_id[: -len("-REFUND")]
            original = tier3_by_txn.get(original_id)
            if original is not None and original.status == STATUS_MATCH and \
               original.rule == RULE_REFUND_LINKED_NET_AMOUNT:
                return self._result(
                    txn_id, STATUS_UNRESOLVED, None, r.matched_records,
                    {"linked_original": original_id},
                    REASON_NO_SEPARATE_SETTLEMENT_EXPECTED,
                )
            return self._result(
                txn_id, STATUS_HUMAN_REVIEW, None, r.matched_records,
                {"linked_original": original_id,
                 "linked_original_status": original.status if original else "NOT_YET_RESOLVED"},
                REASON_LINKED_ORIGINAL_UNRESOLVED,
            )

        # Free-text description evidence: bank description contains the
        # ledger invoice_reference or gateway customer_reference, AND the
        # amount matches exactly, AND the candidate is unique.
        desc_candidates = self._description_candidates(gw, ledger)
        if len(desc_candidates) == 1:
            bid = desc_candidates[0]
            self._consume(bid)
            return self._result(
                txn_id, STATUS_MATCH, RULE_DESCRIPTION_LINKED_REFERENCE,
                {"gateway": gw.source_row_id, "bank": bid, "ledger": ledger_id},
                {"bank_description": _ref_value(self.bank_by_row_id[bid], "description"),
                 "matched_on": _ref_value(ledger, "invoice_reference") or _ref_value(gw, "customer_reference")},
                None,
            )
        if len(desc_candidates) > 1:
            return self._result(
                txn_id, STATUS_HUMAN_REVIEW, None, r.matched_records,
                {"description_candidates": desc_candidates},
                REASON_MULTIPLE_DESCRIPTION_MATCHES,
            )

        # No textual evidence at all. If multiple/']one amount-only
        # candidates exist, that's symmetric or weak evidence for a human —
        # never a basis to guess. If none exist, there's nothing to review.
        amount_only = self._amount_matching_available_candidates(gw)
        if len(amount_only) >= 2:
            return self._result(
                txn_id, STATUS_HUMAN_REVIEW, None, r.matched_records,
                {"amount_matching_candidates": amount_only},
                REASON_SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD,
            )
        if len(amount_only) == 1:
            return self._result(
                txn_id, STATUS_HUMAN_REVIEW, None, r.matched_records,
                {"amount_matching_candidate": amount_only[0]},
                REASON_WEAK_EVIDENCE_INSUFFICIENT,
            )
        return self._result(
            txn_id, STATUS_UNRESOLVED, None, r.matched_records,
            {}, REASON_NO_EVIDENCE_AVAILABLE,
        )

    # -- result builder ----------------------------------------------------

    @staticmethod
    def _result(txn_id: str, status: str, rule: Optional[str], matched_records: dict,
                evidence: dict, reason: Optional[str],
                llm_consulted: bool = False, llm_recommendation: Optional[dict] = None,
                confidence: Optional[float] = None) -> Tier3Result:
        return Tier3Result(
            transaction_id=txn_id,
            status=status,
            tier="TIER_3",
            rule=rule,
            matched_records=dict(matched_records),
            evidence=evidence,
            reason=reason,
            llm_consulted=llm_consulted,
            llm_recommendation=llm_recommendation,
            confidence=confidence,
        )


# ===========================================================================
# Public entry point
# ===========================================================================

def run_tier3(tier2_results: list[Tier2Result], tier1_matcher: ExactMatcher,
              llm_client: Optional[LLMClient] | object = _AUTO_LLM) -> tuple[list[Tier3Result], Tier3Summary]:
    """
    Run Tier 3 LLM-assisted adjudication over Tier 2's residue.

    tier2_results: the FULL output of run_tier2() (not just its residue) —
        needed so Tier 3 can see which bank rows Tier 2 itself consumed and
        never re-offer them. Only the residue subset
        (`get_tier2_residue(tier2_results)`) ever receives a Tier 3
        decision; anything Tier 2 already MATCHED is left untouched and
        does not appear in the returned results.
    tier1_matcher: the ExactMatcher from run_tier1(..., return_matcher=True),
        used the same way Tier 2 uses it: to look up full CanonicalRecords
        and to respect Tier 1's own consumption bookkeeping.
    llm_client: optional LLMClient. If omitted, Gemini is selected when
        `LLM_PROVIDER=gemini` or `GEMINI_API_KEY` is configured. Any other
        provider value is ignored. Passing `None` explicitly disables LLM calls.
        If Gemini is unavailable, Tier 3 still resolves every
        deterministically-provable case (refund linkage, TDS linkage,
        description linkage) with zero LLM calls; only the split-settlement
        rule is skipped (falls through to HUMAN_REVIEW) when no client is
        available.

    Deterministic given a deterministic llm_client (or none): resolves
    non-refund residue transactions first, then refund rows (so a refund
    row can see whether its linked original was matched), which removes
    any dependency on incidental input ordering.
    """
    selected_llm_client: Optional[LLMClient] = None
    if llm_client is _AUTO_LLM:
        provider = os.environ.get("LLM_PROVIDER", "").lower()
        if provider == "gemini" or (not provider and os.environ.get("GEMINI_API_KEY")):
            selected_llm_client = GeminiLLMClient()
    else:
        selected_llm_client = llm_client

    residue = get_tier2_residue(tier2_results)
    adjudicator = LLMAdjudicator(tier1_matcher, tier2_results, llm_client=selected_llm_client)

    tier3_by_txn: dict[str, Tier3Result] = {}
    non_refund = [r for r in residue if not r.transaction_id.endswith("-REFUND")]
    refund = [r for r in residue if r.transaction_id.endswith("-REFUND")]

    for r in non_refund:
        result = adjudicator.resolve(r, tier3_by_txn)
        tier3_by_txn[result.transaction_id] = result
    for r in refund:
        result = adjudicator.resolve(r, tier3_by_txn)
        tier3_by_txn[result.transaction_id] = result

    # Preserve original residue order in the returned list for readability,
    # even though refund rows were resolved in a second pass internally.
    results = [tier3_by_txn[r.transaction_id] for r in residue]

    match_count = sum(1 for x in results if x.status == STATUS_MATCH)
    human_review_count = sum(1 for x in results if x.status == STATUS_HUMAN_REVIEW)
    unresolved_count = sum(1 for x in results if x.status == STATUS_UNRESOLVED)

    summary = Tier3Summary(
        total_residue_evaluated=len(results),
        match_count=match_count,
        human_review_count=human_review_count,
        unresolved_count=unresolved_count,
        llm_calls_made=adjudicator.llm_calls_made,
        llm_recommendations_validated=adjudicator.llm_validated,
        llm_recommendations_rejected=adjudicator.llm_rejected,
    )
    return results, summary


def retry_tier3_transaction(transaction_id: str, tier2_results: list[Tier2Result],
                            tier1_matcher: ExactMatcher,
                            llm_client: LLMClient,
                            already_consumed: Optional[set[str]] = None) -> Tier3Result:
    """Retry one existing Tier-3 residue transaction with a supplied client.

    This deliberately does not rerun normalization, Tier 1, Tier 2, or the
    full dataset. Candidate discovery and validation remain identical to the
    normal Tier 3 path.

    ``already_consumed`` carries bank rows claimed by *other* Tier 3 matches
    and by Stage 3 split Matches so a retry can never re-offer a row claimed
    after this transaction's original disposition. Defaults to None (nothing
    extra), which is safe for module tests but unsafe for the running server.
    """
    residue = get_tier2_residue(tier2_results)
    result = next((r for r in residue if r.transaction_id == transaction_id), None)
    if result is None:
        raise KeyError(transaction_id)
    adjudicator = LLMAdjudicator(
        tier1_matcher, tier2_results,
        llm_client=llm_client,
        extra_consumed=already_consumed,
    )
    return adjudicator.resolve(result, {})


def parse_llm_json(raw: str) -> Optional[dict]:
    """Module-level alias for LLMAdjudicator._parse_llm_json.

    Exposed so other modules (e.g. core.match_split) can reuse the same
    robust JSON-extraction logic without importing an internal class method.
    """
    return LLMAdjudicator._parse_llm_json(raw)


def get_final_residue(results: list[Tier3Result]) -> list[Tier3Result]:
    """
    Everything Tier 3 did NOT resolve to MATCH: HUMAN_REVIEW and
    UNRESOLVED. Phase 5 is the final implemented tier in this project
    (no Q&A layer here) — this is the queue a human reconciler would work
    from next.
    """
    return [r for r in results if r.status != STATUS_MATCH]
