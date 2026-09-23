import csv

import pytest

from core.adapters import SchemaMappingError, SourceSchema


def test_adapter_maps_explicit_headers(tmp_path):
    source = tmp_path / "provider.csv"
    source.write_text("row,reference,value\n1,PAY1,10.00\n", encoding="utf-8")
    output = tmp_path / "gateway.csv"
    adapter = SourceSchema("gateway", {"source_row_id": "row", "payment_id": "reference", "amount": "value"})

    assert adapter.adapt(source, output) == 1
    assert list(csv.DictReader(output.open(encoding="utf-8"))) == [{"source_row_id": "1", "payment_id": "PAY1", "amount": "10.00"}]


def test_adapter_rejects_missing_configured_header(tmp_path):
    source = tmp_path / "provider.csv"
    source.write_text("row\n1\n", encoding="utf-8")
    with pytest.raises(SchemaMappingError, match="missing"):
        SourceSchema("gateway", {"payment_id": "missing"}).adapt(source, tmp_path / "out.csv")
