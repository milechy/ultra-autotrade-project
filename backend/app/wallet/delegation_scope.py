"""DelegationScope: Pydantic model for Privy delegated signing scope.

This module is **independent from the actual delegated execution logic**.
It only defines the typed shape of a delegation scope and its serialization
helpers (to/from a JWT claim dict).

The actual Privy SDK call (`request_delegation` / `execute_action` / `revoke`)
lives in :mod:`backend.app.wallet.privy_delegated_client` and is currently a
PoC skeleton (NotImplementedError). See
``docs/internal/privy_delegated_signing_poc_design.md`` for the design.

Why this is split out
---------------------
- ``DelegationScope`` is the canonical type that flows between:
  - the onboarding UI (user 同意画面) → backend → Privy
  - the AI judgment scheduler → backend → ``execute_action`` pre-check
  - audit log writers (``backend.app.wallet.audit``)
- Pulling it out of the skeleton client keeps the type usable & testable
  before the real Privy SDK wiring lands.
"""
from __future__ import annotations

import time
from typing import Any, Literal

try:  # pragma: no cover - import shim
    from pydantic import BaseModel, Field, field_validator
    _PYDANTIC_V2 = True
except ImportError:  # pragma: no cover - older pydantic fallback
    from pydantic import BaseModel, Field  # type: ignore[assignment]
    from pydantic import validator as field_validator  # type: ignore[assignment]
    _PYDANTIC_V2 = False


SupportedAction = Literal["aave:supply", "aave:withdraw", "aave:repay"]

SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    {"aave:supply", "aave:withdraw", "aave:repay"}
)


class DelegationScope(BaseModel):
    """Scope of a Privy delegation token.

    Fields
    ------
    actions:
        Allowed action keys. Must be a non-empty subset of
        :data:`SUPPORTED_ACTIONS`.
    max_amount_per_tx_usdc:
        Maximum USDC (integer; whole-dollar units in PoC) that a single
        ``execute_action`` call may move. Must be > 0.
    max_amount_per_day_usdc:
        Maximum USDC over a rolling 24h window. Must be > 0 and
        >= ``max_amount_per_tx_usdc``.
    expires_at_unix:
        Unix epoch seconds when the delegation expires. Must be in the
        future at construction time.
    revoke_token:
        Opaque server-side handle used by the operator-side revoke path.
        Stored as an opaque string; **never** logged verbatim.
    """

    actions: list[SupportedAction] = Field(..., min_length=1)
    max_amount_per_tx_usdc: int = Field(..., gt=0)
    max_amount_per_day_usdc: int = Field(..., gt=0)
    expires_at_unix: int = Field(..., gt=0)
    revoke_token: str = Field(..., min_length=1)

    if _PYDANTIC_V2:

        @field_validator("actions")
        @classmethod
        def _validate_actions(cls, v: list[str]) -> list[str]:
            if not v:
                raise ValueError("actions must be non-empty")
            unknown = [a for a in v if a not in SUPPORTED_ACTIONS]
            if unknown:
                raise ValueError(
                    f"unsupported actions: {unknown}; "
                    f"allowed={sorted(SUPPORTED_ACTIONS)}"
                )
            return v

        @field_validator("expires_at_unix")
        @classmethod
        def _validate_expiry(cls, v: int) -> int:
            now = int(time.time())
            if v <= now:
                raise ValueError(
                    f"expires_at_unix must be in the future "
                    f"(got {v}, now {now})"
                )
            return v
    else:  # pragma: no cover - pydantic v1 fallback

        @field_validator("actions", allow_reuse=True)  # type: ignore[misc]
        def _validate_actions(cls, v: list[str]) -> list[str]:  # noqa: N805
            if not v:
                raise ValueError("actions must be non-empty")
            unknown = [a for a in v if a not in SUPPORTED_ACTIONS]
            if unknown:
                raise ValueError(
                    f"unsupported actions: {unknown}; "
                    f"allowed={sorted(SUPPORTED_ACTIONS)}"
                )
            return v

        @field_validator("expires_at_unix", allow_reuse=True)  # type: ignore[misc]
        def _validate_expiry(cls, v: int) -> int:  # noqa: N805
            now = int(time.time())
            if v <= now:
                raise ValueError(
                    f"expires_at_unix must be in the future "
                    f"(got {v}, now {now})"
                )
            return v

    def assert_consistent(self) -> None:
        """Cross-field validation that pydantic field_validator can't do.

        Raises ``ValueError`` if per-day < per-tx (a per-tx cap larger than
        the per-day cap would be self-contradictory).
        """
        if self.max_amount_per_day_usdc < self.max_amount_per_tx_usdc:
            raise ValueError(
                f"max_amount_per_day_usdc ({self.max_amount_per_day_usdc}) "
                f"must be >= max_amount_per_tx_usdc "
                f"({self.max_amount_per_tx_usdc})"
            )

    # ------------------------------------------------------------------
    # JWT claim (de)serialization
    # ------------------------------------------------------------------

    def to_jwt_claim(self) -> dict[str, Any]:
        """Serialize to a JWT-claim-compatible dict.

        The shape mirrors the documented scope JSON schema in the design
        doc (§3.5). Keys are stable; do not rename without bumping a
        version on the delegation token.
        """
        return {
            "actions": list(self.actions),
            "max_amount_per_tx_usdc": int(self.max_amount_per_tx_usdc),
            "max_amount_per_day_usdc": int(self.max_amount_per_day_usdc),
            "expires_at_unix": int(self.expires_at_unix),
            "revoke_token": self.revoke_token,
        }

    @classmethod
    def from_jwt_claim(cls, d: dict[str, Any]) -> "DelegationScope":
        """Reconstruct from a dict produced by :meth:`to_jwt_claim`.

        Unknown keys are ignored (forward-compatible). Missing keys raise
        a pydantic ``ValidationError`` (or ``ValueError`` depending on
        the pydantic version installed).
        """
        return cls(
            actions=list(d["actions"]),
            max_amount_per_tx_usdc=int(d["max_amount_per_tx_usdc"]),
            max_amount_per_day_usdc=int(d["max_amount_per_day_usdc"]),
            expires_at_unix=int(d["expires_at_unix"]),
            revoke_token=str(d["revoke_token"]),
        )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def is_expired(self, now_unix: int | None = None) -> bool:
        """Return True if the delegation has expired as of *now_unix*."""
        ts = int(time.time()) if now_unix is None else int(now_unix)
        return self.expires_at_unix <= ts

    def allows_action(self, action: str) -> bool:
        """Return True iff *action* is in :attr:`actions`."""
        return action in self.actions

    def allows_amount(self, amount_usdc: int) -> bool:
        """Return True iff *amount_usdc* fits the per-tx cap.

        This is **per-tx only**. The per-day rolling check is the
        responsibility of the audit / accounting layer
        (see :mod:`backend.app.wallet.audit`).
        """
        return 0 < int(amount_usdc) <= self.max_amount_per_tx_usdc
