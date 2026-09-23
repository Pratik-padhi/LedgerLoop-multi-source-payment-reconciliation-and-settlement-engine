import pytest
from core.actions import ActionAuthorizationError, authorize_and_audit
from core.persistence import ReconciliationStore

def test_action_requires_actor_and_optional_token(tmp_path):
    store = ReconciliationStore(tmp_path / "audit.sqlite3")
    with pytest.raises(ActionAuthorizationError, match="Actor"):
        authorize_and_audit({}, store, action="RETRY", transaction_id="PAY1", outcome="DENIED")
    with pytest.raises(ActionAuthorizationError, match="token"):
        authorize_and_audit({"X-LedgerLoop-Actor": "a", "X-LedgerLoop-Action-Token": "wrong"}, store, action="RETRY", transaction_id="PAY1", outcome="DENIED", required_token="secret")
    authorize_and_audit({"X-LedgerLoop-Actor": "a", "X-LedgerLoop-Action-Token": "secret"}, store, action="RETRY", transaction_id="PAY1", outcome="ALLOWED", required_token="secret")
