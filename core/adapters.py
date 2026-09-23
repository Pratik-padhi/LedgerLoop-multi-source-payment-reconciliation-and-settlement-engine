"""Explicit source-schema adapters for LedgerLoop's canonical CSV inputs.

Adapters rename configured source columns only.  They intentionally do not
guess headers, coerce financial values, or make reconciliation decisions.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class SchemaMappingError(ValueError):
    """A configured source schema cannot safely produce a canonical input."""


@dataclass(frozen=True)
class SourceSchema:
    source: str
    columns: Mapping[str, str]

    def adapt(self, input_path: str | Path, output_path: str | Path) -> int:
        """Write rows with canonical headers, returning the number of rows.

        ``columns`` maps canonical header -> source header. Required canonical
        headers are validated by ``core.normalize`` after this boundary.
        """
        source_path, target_path = Path(input_path), Path(output_path)
        if source_path.resolve() == target_path.resolve():
            raise SchemaMappingError("adapter input and output must differ")
        with source_path.open(newline="", encoding="utf-8-sig") as source_file:
            reader = csv.DictReader(source_file)
            headers = set(reader.fieldnames or [])
            missing = sorted(set(self.columns.values()) - headers)
            if missing:
                raise SchemaMappingError(
                    f"{self.source}: mapped source columns are missing: {', '.join(missing)}"
                )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("w", newline="", encoding="utf-8") as target_file:
                writer = csv.DictWriter(target_file, fieldnames=list(self.columns))
                writer.writeheader()
                count = 0
                for row in reader:
                    writer.writerow({canonical: row.get(native, "") for canonical, native in self.columns.items()})
                    count += 1
        return count


# These defaults document the repository fixtures.  Deployments may construct
# SourceSchema instances with their own *explicit* mapping configuration.
CANONICAL_SCHEMAS = {
    "gateway": SourceSchema("gateway", {
        "source_row_id": "source_row_id", "payment_id": "payment_id",
        "payment_date": "payment_date", "amount": "amount", "status": "status",
        "gateway_reference": "gateway_reference", "customer_reference": "customer_reference",
        "settlement_expected_date": "settlement_expected_date",
    }),
    "bank": SourceSchema("bank", {
        "source_row_id": "source_row_id", "bank_transaction_id": "bank_transaction_id",
        "transaction_date": "transaction_date", "value_date": "value_date",
        "credit_amount": "credit_amount", "utr": "utr", "bank_reference": "bank_reference",
        "description": "description",
    }),
    "ledger": SourceSchema("ledger", {
        "source_row_id": "source_row_id", "payment_reference": "payment_reference",
        "entry_date": "entry_date", "recorded_amount": "recorded_amount",
        "entry_type": "entry_type", "invoice_reference": "invoice_reference",
        "tax_amount": "tax_amount", "tds_amount": "tds_amount",
    }),
}
