from core.config import load_settings
from core.service import run_reconciliation
from core.persistence import ReconciliationStore


def test_reconciliation_run_is_persisted(tmp_path):
    settings = load_settings()
    settings = settings.__class__(**{**settings.__dict__, "database_path": tmp_path / "run.sqlite3"})
    run = run_reconciliation(settings)
    latest = ReconciliationStore(settings.database_path).latest_run()
    assert latest["dataset"] == "data"
    assert len(latest["results"]) == len({r.transaction_id for r in run.r1})
