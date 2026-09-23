"""Application service for running the LedgerLoop reconciliation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config import Settings, load_settings
from core.match_exact import get_residue, run_tier1
from core.match_fuzzy import run_tier2
from core.match_llm import GeminiFallbackClient, run_tier3
from core.match_split import SplitStatus, run_stage3
from core.persistence import ReconciliationStore


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
    run_id: int | None = None


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


def authoritative_results(run: ReconciliationRun) -> list[dict[str, Any]]:
    """Serialize final per-transaction decisions without changing them."""
    index: dict[str, dict[str, Any]] = {}
    for tier, results in (("TIER_1", run.r1), ("TIER_2", run.r2), ("TIER_3", run.r3), ("STAGE_3", run.r4)):
        for result in results:
            if tier == "TIER_2" and getattr(result, "status", None) != "MATCHED":
                continue
            index[result.transaction_id] = {"transaction_id": result.transaction_id, "tier": tier, "data": result.to_dict()}
    return [index[key] for key in sorted(index)]


def persist_run(run: ReconciliationRun) -> int:
    """Persist the completed run; this has no effect on matching decisions."""
    summary = {"tier1": run.summary1.to_dict(), "tier2": run.summary2.to_dict(),
               "tier3": run.summary3.to_dict(), "stage3": run.summary4.to_dict()}
    run_id = ReconciliationStore(run.settings.database_path).save_run(
        run.settings.dataset_name,
        summary,
        authoritative_results(run),
        status="COMPLETED",
        source_files=[str(run.settings.data_dir)],
        notes=f"dataset={run.settings.dataset_name}",
    )
    return run_id


def run_reconciliation(settings: Settings | None = None) -> ReconciliationRun:
    """Run all reconciliation stages for the configured dataset."""
    settings = settings or load_settings()
    r1, summary1, matcher = run_tier1(
        data_dir=str(settings.data_dir),
        return_matcher=True,
    )
    r2, summary2 = run_tier2(get_residue(r1), matcher)
    tier3_llm = GeminiFallbackClient() if settings.ai_enabled else None
    r3, summary3 = run_tier3(r2, matcher, llm_client=tier3_llm)

    consumed = consumed_bank_ids(r1, r2, r3)
    stage3_llm = GeminiFallbackClient() if settings.ai_enabled else None
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
    run = ReconciliationRun(
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
    run_id = persist_run(run)
    run = ReconciliationRun(
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
        run_id=run_id,
    )
    return run
