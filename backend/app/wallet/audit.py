"""Audit event recording for delegated signing (PoC support layer).

This module provides the **audit-side** plumbing for Phase 3 delegated
signing. It is intentionally independent from the actual delegated
execution code (which is still a skeleton in
:mod:`backend.app.wallet.privy_delegated_client`).

Design intent
-------------
- All ``execute_action`` invocations (and ``request_delegation`` /
  ``revoke`` lifecycle events) should be recorded as :class:`AuditEvent`s.
- Events are persisted to the ``user_actions`` table introduced by
  P0-6. If that table does not yet exist in the connected database,
  :func:`record_audit` **must not** raise — it falls back to an INFO log
  so the caller path is never broken just because the table is missing
  in a test / preview / early-staging environment.

Schema-relaxed by design
------------------------
The exact ORM model for ``user_actions`` is owned by P0-6. To avoid a
hard import-time coupling (and to let this PoC PR land cleanly without
Tier-S churn), the recorder uses a duck-typed write path:

1. Try to import a ``UserAction`` model from a small list of
   candidate modules.
2. If found and the session has ``add()`` / ``commit()``, persist.
3. Otherwise, emit a structured INFO log and return.

The real delegated-execution PR will tighten this once the canonical
``user_actions`` model location is settled.
"""
from __future__ import annotations

import importlib
import json
import logging
from typing import Any, Literal, Optional

try:  # pragma: no cover
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pydantic is required for backend.app.wallet.audit"
    ) from exc

from .delegation_scope import DelegationScope

logger = logging.getLogger(__name__)


AuditEventType = Literal[
    "delegation.granted",
    "delegation.revoked",
    "delegation.renewed",
    "execute_action.attempt",
    "execute_action.success",
    "execute_action.failure",
    "policy_violation",
]


class AuditEvent(BaseModel):
    """A single audit record for delegated-signing-related activity.

    Fields
    ------
    event_type:
        One of :data:`AuditEventType`. Use the most specific value
        possible (e.g. ``execute_action.failure`` rather than a generic
        catch-all).
    user_id:
        Internal user id (string form — accepts UUID / int-as-str).
    scope:
        The delegation scope that authorized (or *would have* authorized)
        the action. Optional for lifecycle-only events like
        ``delegation.revoked`` after the scope has been purged.
    action:
        The action key (e.g. ``aave:supply``). Optional for events that
        are not action-specific.
    amount:
        Amount in USDC (integer; whole-dollar units in PoC). Optional.
    tx_hash:
        On-chain tx hash if the event corresponds to a settled
        transaction. Optional.
    timestamp:
        Unix epoch seconds. Caller-supplied so retries reuse the original
        timestamp.
    reason:
        Human-readable reason, used heavily for ``policy_violation`` and
        ``*.failure`` events.
    idempotency_key:
        Mirrors the same field on the execute path; lets the audit row
        be joined back to the execution attempt.
    ai_decision_id:
        Optional FK to ``ai_decisions.id`` — used to reconstruct
        "which AI judgment caused this action".
    """

    event_type: AuditEventType
    user_id: str = Field(..., min_length=1)
    scope: Optional[DelegationScope] = None
    action: Optional[str] = None
    amount: Optional[int] = Field(default=None, ge=0)
    tx_hash: Optional[str] = None
    timestamp: int = Field(..., gt=0)
    reason: Optional[str] = None
    idempotency_key: Optional[str] = None
    ai_decision_id: Optional[str] = None

    def to_row(self) -> dict[str, Any]:
        """Flatten to a dict suitable for a SQL INSERT.

        ``scope`` is serialized via
        :meth:`DelegationScope.to_jwt_claim` so the audit row carries
        the exact policy that was in effect at decision time.
        """
        return {
            "event_type": self.event_type,
            "user_id": self.user_id,
            "scope_json": (
                json.dumps(self.scope.to_jwt_claim(), sort_keys=True)
                if self.scope is not None
                else None
            ),
            "action": self.action,
            "amount_usdc": self.amount,
            "tx_hash": self.tx_hash,
            "timestamp_unix": self.timestamp,
            "reason": self.reason,
            "idempotency_key": self.idempotency_key,
            "ai_decision_id": self.ai_decision_id,
        }


# Candidate import paths for the user_actions ORM model.
# Ordered most-likely first. The first one that imports cleanly wins.
_USER_ACTION_MODEL_CANDIDATES: tuple[str, ...] = (
    "backend.app.users.models:UserAction",
    "backend.app.users.user_action:UserAction",
    "backend.app.automation.models:UserAction",
    "backend.app.database:UserAction",
)


def _try_resolve_user_action_model() -> Any | None:
    """Best-effort lookup of the P0-6 ``UserAction`` ORM model.

    Returns the class, or ``None`` if no candidate import succeeded.
    Never raises.
    """
    for spec in _USER_ACTION_MODEL_CANDIDATES:
        module_name, _, attr = spec.partition(":")
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 — best-effort
            continue
        cls = getattr(module, attr, None)
        if cls is not None:
            return cls
    return None


def record_audit(session: Any, event: AuditEvent) -> None:
    """Record an :class:`AuditEvent`.

    Parameters
    ----------
    session:
        A DB session-like object (typically a SQLAlchemy ``Session``).
        We duck-type for ``.add(obj)`` + ``.commit()``. ``None`` is
        accepted and triggers the log-only fallback.
    event:
        The event to persist.

    Behavior
    --------
    - If the ``user_actions`` ORM model is importable and ``session``
      can ``add`` / ``commit``, persist a row.
    - On **any** failure (model not found, session lacks add/commit,
      DB error), log a structured INFO line and return — this function
      never propagates an exception, so audit pressure never breaks the
      caller path. Hard-failing audit would be worse than a missing row
      in the PoC phase; the **separate** execute path will retain its
      own error handling.

    The real delegated-execution PR is expected to tighten this to a
    strict mode (raise on persistence failure) once ``user_actions`` is
    canonical everywhere.
    """
    row = event.to_row()

    model = _try_resolve_user_action_model()
    if model is None:
        logger.info(
            "audit.fallback no UserAction model resolved event=%s row=%s",
            event.event_type,
            json.dumps(row, sort_keys=True, default=str),
        )
        return

    if session is None or not (
        hasattr(session, "add") and hasattr(session, "commit")
    ):
        logger.info(
            "audit.fallback session unusable event=%s row=%s",
            event.event_type,
            json.dumps(row, sort_keys=True, default=str),
        )
        return

    try:
        obj = model(**row)
    except TypeError:
        # Model schema doesn't match our row shape (P0-6 likely uses a
        # different column set in early states). Fall back to log.
        logger.info(
            "audit.fallback UserAction(**row) TypeError event=%s row=%s",
            event.event_type,
            json.dumps(row, sort_keys=True, default=str),
        )
        return

    try:
        session.add(obj)
        session.commit()
    except Exception as exc:  # noqa: BLE001 — must not propagate
        # Best-effort rollback (ignore failures within the fallback path).
        rollback = getattr(session, "rollback", None)
        if callable(rollback):
            try:
                rollback()
            except Exception:  # noqa: BLE001
                pass
        logger.info(
            "audit.fallback persist failed event=%s err=%s row=%s",
            event.event_type,
            exc,
            json.dumps(row, sort_keys=True, default=str),
        )
        return

    logger.debug(
        "audit.persisted event=%s user=%s action=%s amount=%s",
        event.event_type,
        event.user_id,
        event.action,
        event.amount,
    )
