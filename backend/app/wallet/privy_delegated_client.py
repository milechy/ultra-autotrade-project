"""Privy delegated signing client (PoC skeleton)

Phase 3: per-user delegated signing via Privy. Replaces single-key
AAVE_WALLET_PRIVATE_KEY for user-isolated execution.

NOTE: This is a SKELETON ONLY. No delegated execution code lives here yet.
See docs/internal/privy_delegated_signing_poc_design.md for the design.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


SupportedAction = Literal["aave:supply", "aave:withdraw", "aave:repay"]


@dataclass
class DelegationScope:
    actions: list[SupportedAction]
    max_amount_per_tx_usdc: int
    max_amount_per_day_usdc: int
    expires_at_unix: int


class PrivyDelegatedClient:
    """PoC skeleton — NOT WIRED to production paths yet."""

    def __init__(self, privy_app_id: str, privy_app_secret: str) -> None:
        # TODO: initialize Privy SDK client
        self._app_id = privy_app_id
        self._app_secret = privy_app_secret

    def request_delegation(
        self,
        user_privy_did: str,
        scope: DelegationScope,
    ) -> str:
        """TODO: return a Privy delegation token for the given scope."""
        raise NotImplementedError("PoC skeleton — see design doc")

    def execute_action(
        self,
        delegation_token: str,
        action: SupportedAction,
        amount_usdc: int,
        idempotency_key: str,
    ) -> Optional[str]:
        """TODO: execute a scoped action and return tx hash."""
        raise NotImplementedError("PoC skeleton — see design doc")

    def revoke(self, delegation_token: str) -> bool:
        """TODO: revoke an active delegation."""
        raise NotImplementedError("PoC skeleton — see design doc")
