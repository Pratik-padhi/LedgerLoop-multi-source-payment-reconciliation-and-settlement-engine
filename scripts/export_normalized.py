"""
LedgerLoop — Phase 2: Normalized Output Export (for debugging/inspection)
============================================================================

Runs normalize_all() against the real Phase 1 dataset and writes each
source's canonical records to data/normalized/*.json. This is a
development/debugging aid only — it is NOT a user-facing deliverable and
Phase 3 is not required to consume these files (it can call normalize_all()
directly in-process).

Usage:
    python3 scripts/export_normalized.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.normalize import normalize_all

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(DATA_DIR, "normalized")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    result = normalize_all(data_dir=DATA_DIR, strict=False)

    for source_name, source_result in [
        ("gateway", result.gateway),
        ("bank", result.bank),
        ("ledger", result.ledger),
    ]:
        out_path = os.path.join(OUT_DIR, f"{source_name}_normalized.json")
        payload = {
            "source": source_name,
            "record_count": len(source_result.records),
            "warning_count": len(source_result.warnings),
            "error_count": len(source_result.errors),
            "records": [r.to_dict() for r in source_result.records],
            "warnings": [w.to_dict() for w in source_result.warnings],
            "errors": [e.to_dict() for e in source_result.errors],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"Wrote {out_path} "
              f"({len(source_result.records)} records, "
              f"{len(source_result.warnings)} warnings, "
              f"{len(source_result.errors)} errors)")

    summary = result.summary()
    summary_path = os.path.join(OUT_DIR, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {summary_path}")
    print()
    print("Summary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
