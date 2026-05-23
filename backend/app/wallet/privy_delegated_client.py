"""Privy delegated signing client (PoC skeleton).

Phase 3: per-user delegated signing via Privy. Replaces the single-key
``AAVE_WALLET_PRIVATE_KEY`` execution path with **per-user, scope-limited**
delegations.

**This module is a SKELETON.** All methods raise :class:`NotImplementedError`.
The real Privy SDK wiring lives in a separate PR (see the rollout plan in
``docs/internal/privy_delegated_signing_poc_design.md`` §7.3).

Related modules
---------------
- :mod:`backend.app.wallet.delegation_scope` — the typed scope flowing
  in and out of this client. **Already implemented**, independent of
  Privy SDK availability.
- :mod:`backend.app.wallet.audit` — audit-event recording for every
  ``execute_action`` attempt / outcome. **Already implemented** with a
  log-only fallback when ``user_actions`` is unavailable.

Design references
-----------------
- ``docs/internal/privy_delegated_signing_poc_design.md`` (full design)
- memory ``privy_key_recovery_policy`` (key handling principles)
"""
from __future__ import annotations

from typing import Literal, Optional

from .delegation_scope import DelegationScope, SupportedAction

__all__ = ["SupportedAction", "DelegationScope", "PrivyDelegatedClient"]


class PrivyDelegatedClient:
    """PoC skeleton — NOT WIRED to production paths yet.

    The constructor stores credentials but does **not** initialize a
    Privy SDK client. All operational methods raise
    :class:`NotImplementedError`.

    The corresponding integration PR will:

    1. Initialize a Privy SDK / HTTP client here.
    2. Implement :meth:`request_delegation` against Privy's delegated
       actions endpoint.
    3. Implement :meth:`execute_action` with idempotent on-chain
       submission and audit recording via
       :func:`backend.app.wallet.audit.record_audit`.
    4. Implement :meth:`revoke` with both the user-initiated and
       operator-initiated paths.
    """

    def __init__(self, privy_app_id: str, privy_app_secret: str) -> None:
        """Store credentials. SDK client is **not** initialized yet.

        Parameters
        ----------
        privy_app_id:
            The Privy application id (public-ish). Read from
            ``PRIVY_APP_ID``.
        privy_app_secret:
            The Privy application secret. Read from
            ``PRIVY_APP_SECRET`` — **must never** be logged or returned.

        Notes
        -----
        - The secret is stored on the instance for the real PR's SDK
          init step. Treat instances as sensitive (never serialize).
        """
        # TODO(PR-after): initialize Privy SDK client (see design §7.3).
        self._app_id = privy_app_id
        self._app_secret = privy_app_secret

    # ------------------------------------------------------------------
    # Delegation lifecycle
    # ------------------------------------------------------------------

    def request_delegation(
        self,
        user_privy_did: str,
        scope: DelegationScope,
    ) -> str:
        """Request a new delegation token for the user.

        Parameters
        ----------
        user_privy_did:
            The user's Privy decentralized identifier (e.g.
            ``"did:privy:..."``).
        scope:
            The :class:`DelegationScope` to encode into the token.
            ``scope.assert_consistent()`` should be called by the caller
            before this method.

        Returns
        -------
        str
            An opaque delegation token. Persist its **hash** (not the
            token itself) on the application side; the raw token belongs
            in the secret store.

        Raises
        ------
        NotImplementedError
            Until the integration PR lands.

        Failure paths (planned)
        -----------------------
        - Privy 5xx → wrap as a domain-level ``PrivyUnavailableError``
          so the AI judgment scheduler can record
          ``privy_unavailable`` (see design §6.1).
        - Scope rejected by Privy (e.g. action key unknown) →
          ``DelegationScopeRejectedError`` with the Privy error code.
        - User has revoked at the Privy UI level →
          ``DelegationDeniedError``.
        """
        raise NotImplementedError(
            "PoC skeleton — see docs/internal/"
            "privy_delegated_signing_poc_design.md §7.3"
        )

    def execute_action(
        self,
        delegation_token: str,
        action: SupportedAction,
        amount_usdc: int,
        idempotency_key: str,
    ) -> Optional[str]:
        """Execute a scoped action on behalf of the user.

        Parameters
        ----------
        delegation_token:
            The token previously returned by :meth:`request_delegation`.
            Must be passed by reference (no logging).
        action:
            One of the :data:`SupportedAction` keys.
        amount_usdc:
            Integer USDC amount (whole-dollar units in PoC). Must be
            ``> 0`` and ``<= scope.max_amount_per_tx_usdc``. The per-day
            rolling cap is enforced by the audit/accounting layer.
        idempotency_key:
            Caller-provided key for safe retries. The same key MUST
            produce the same (or no additional) on-chain effect.

        Returns
        -------
        Optional[str]
            The on-chain tx hash on success. ``None`` is reserved for
            "accepted but pending" semantics if Privy returns
            async-only — the real PR will pin this down.

        Raises
        ------
        NotImplementedError
            Until the integration PR lands.

        Failure paths (planned)
        -----------------------
        - Scope violation (action / per-tx amount / expiry) →
          ``DelegationScopeViolation`` (never reach Privy).
        - Per-day cap exceeded → ``DelegationQuotaExceeded`` (recorded
          as ``policy_violation`` via
          :func:`backend.app.wallet.audit.record_audit`).
        - Privy 5xx → ``PrivyUnavailableError`` (see design §6.1).
        - On-chain revert → ``OnChainExecutionFailed`` with the revert
          reason; audit row gets ``execute_action.failure``.
        """
        raise NotImplementedError(
            "PoC skeleton — see docs/internal/"
            "privy_delegated_signing_poc_design.md §7.3"
        )

    def revoke(self, delegation_token: str) -> bool:
        """Revoke an active delegation.

        Parameters
        ----------
        delegation_token:
            The token (or its server-side handle / revoke_token field
            of the scope) identifying the delegation to revoke.

        Returns
        -------
        bool
            ``True`` if the revoke was accepted by Privy. The actual
            effect may be **eventually consistent** on Privy's side —
            see design §3.4 and §8 (open question on revoke latency).

        Raises
        ------
        NotImplementedError
            Until the integration PR lands.

        Failure paths (planned)
        -----------------------
        - Token unknown / already revoked → return ``True`` (idempotent).
        - Privy 5xx → ``PrivyUnavailableError``; operator runbook
          (design §6.3) calls for retry with backoff and, if persistent,
          fall back to setting ``disable_ai_scheduler`` ON to limit
          blast radius until Privy recovers.
        """
        raise NotImplementedError(
            "PoC skeleton — see docs/internal/"
            "privy_delegated_signing_poc_design.md §7.3"
        )
