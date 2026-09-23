from core.persistence import ReconciliationStore


def test_persists_snapshot_and_append_only_audit(tmp_path):
    store = ReconciliationStore(tmp_path / "runs.sqlite3")
    run_id = store.save_run("data", {"matched": 1}, [{
        "transaction_id": "PAY1", "tier": "TIER_1", "data": {"status": "MATCHED", "evidence": {"gateway": "G1"}},
    }])
    store.audit(actor="reviewer@example.test", action="RETRY", transaction_id="PAY1", outcome="REJECTED")

    latest = store.latest_run()
    assert latest["run_id"] == run_id
    assert latest["results"][0]["data"]["evidence"]["gateway"] == "G1"
