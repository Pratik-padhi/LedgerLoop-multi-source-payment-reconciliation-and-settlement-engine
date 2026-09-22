"""Application service for running the LedgerLoop reconciliation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config import Settings, load_settings
from core.match_exact import get_residue, run_tier1
from core.match_fuzzy import run_tier2
from core.match_llm import GeminiFallbackClient, run_tier3
from core.match_split import SplitStatus, run_stage3


@dataclass(frozen=True)
class ReconciliationRun:
    """All pipeline outputs needed by reporting and API adapters."""

    r1: list[Any]
    summary1: Any
    r2: list[Any]
    summary2: Any
    r3: list[Any]
    summary3: Any
    r4: list[Any]
    summary4: Any
    matcher: Any
    stage3_consumed: frozenset[str]
    settings: Settings


def consumed_bank_ids(*result_sets: list[Any]) -> set[str]:
    consumed: set[str] = set()
    for results in result_sets:
        for result in results:
            bank_id = getattr(result, "matched_records", {}).get("bank")
            if bank_id:
                consumed.add(bank_id)
    return consumed


def _stage3_pending_txns(results: list[Any]) -> list[dict[str, str | None]]:
    return [
        {
            "transaction_id": result.transaction_id,
            "gateway_row_id": result.matched_records.get("gateway"),
            "ledger_row_id": result.matched_records.get("ledger"),
        }
        for result in results
        if result.status != "MATCH"
    ]


def run_reconciliation(settings: Settings | None = None) -> ReconciliationRun:
    """Run all reconciliation stages for the configured dataset."""
    settings = settings or load_settings()
    r1, summary1, matcher = run_tier1(
        data_dir=str(settings.data_dir),
        return_matcher=True,
    )
    r2, summary2 = run_tier2(get_residue(r1), matcher)
    r3, summary3 = run_tier3(r2, matcher)

    consumed = consumed_bank_ids(r1, r2, r3)
    stage3_llm = GeminiFallbackClient() if settings.gemini_enabled else None
    r4, summary4 = run_stage3(
        matcher.gateway_records,
        matcher.bank_records,
        matcher.ledger_records,
        consumed,
        _stage3_pending_txns(r3),
        llm_client=stage3_llm,
    )
    stage3_consumed = {
        bank_id
        for result in r4
        if result.status == SplitStatus.MATCH
        for bank_id in result.bank_row_ids
    }
    return ReconciliationRun(
        r1=r1,
        summary1=summary1,
        r2=r2,
        summary2=summary2,
        r3=r3,
        summary3=summary3,
        r4=r4,
        summary4=summary4,
        matcher=matcher,
        stage3_consumed=frozenset(stage3_consumed),
        settings=settings,
    )
