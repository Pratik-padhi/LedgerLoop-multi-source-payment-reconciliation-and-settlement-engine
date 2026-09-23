"""Authorization and audit helpers for state-changing reconciliation actions."""
from __future__ import annotations

import hmac
from typing import Mapping

from core.persistence import ReconciliationStore


class ActionAuthorizationError(PermissionError):
    pass


def authorize_and_audit(headers: Mapping[str, str], store: ReconciliationStore, *, action: str,
                        transaction_id: str, outcome: str, details: Mapping | None = None,
                        required_token: str | None = None, run_id: int | None = None) -> None:
    """Require a named actor and, when configured, a constant-time action token."""
    actor = headers.get("X-LedgerLoop-Actor", "").strip()
    if not actor:
        raise ActionAuthorizationError("X-LedgerLoop-Actor is required")
    supplied = headers.get("X-LedgerLoop-Action-Token", "")
    if required_token and not hmac.compare_digest(supplied, required_token):
        raise ActionAuthorizationError("invalid action token")
    store.audit(actor=actor, action=action, transaction_id=transaction_id, outcome=outcome, details=details, run_id=run_id)
