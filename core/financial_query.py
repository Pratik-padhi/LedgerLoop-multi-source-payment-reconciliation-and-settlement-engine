"""Bounded structured financial queries over completed reconciliation results."""
from __future__ import annotations

import re
from typing import Mapping

_TRANSACTION = re.compile(r"\b(?:PAY|TXN)[-_]?\d+[A-Z]?(?:-REFUND)?\b", re.I)
_FIELDS = {
    "settlement": "expected_net_amount",
    "variance": "variance",
    "gst": "gst_amount",
    "tds": "tds_amount",
    "mdr": "mdr_amount",
    "fee": "total_fee_amount",
    "refund": "refund_amount",
}


def answer_financial_question(question: str, index: Mapping[str, Mapping], *, run_id: int | str | None = None) -> dict | None:
    """Return a supported deterministic answer or ``None`` for normal Q&A.

    This deliberately exposes values only when a matcher already produced a
    settlement breakdown; it never calculates, fills gaps, or changes status.
    """
    lowered = question.lower()
    field = next((value for word, value in _FIELDS.items() if word in lowered), None)
    match = _TRANSACTION.search(question)
    if field is None or match is None:
        return None
    transaction_id = match.group(0).replace("-", "").upper()
    entry = index.get(transaction_id)
    if entry is None:
        return {
            "supported": True,
            "found": False,
            "transaction_ids": [transaction_id],
            "explanation": "I don’t have enough uploaded data to answer that.",
            "citations": [],
            "run_id": run_id,
        }
    data = entry["data"]
    settlement = data.get("settlement") or {}
    if field not in settlement:
        return {
            "supported": True,
            "found": False,
            "transaction_ids": [transaction_id],
            "explanation": "I don’t have enough uploaded data to answer that.",
            "citations": _citations(transaction_id, entry),
            "run_id": run_id,
        }
    answer = {
        "supported": True,
        "found": True,
        "transaction_ids": [transaction_id],
        "tier": entry["tier"],
        "field": field,
        "value": settlement[field],
        "status": data.get("status"),
        "citations": _citations(transaction_id, entry),
        "source": "DETERMINISTIC_SETTLEMENT",
        "run_id": run_id,
    }
    return answer


def _citations(transaction_id: str, entry: Mapping) -> list[dict]:
    data = entry["data"]
    rows = data.get("matched_records") or {}
    cited = [{"transaction_id": transaction_id, "tier": entry["tier"], "source": source, "source_row_id": row_id}
             for source, row_id in rows.items() if row_id]
    cited.extend({"transaction_id": transaction_id, "tier": entry["tier"], "source": "bank", "source_row_id": row_id}
                 for row_id in data.get("bank_row_ids", []) if row_id)
    return cited
