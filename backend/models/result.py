"""Verification result contract shared by services, API, and CLI."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field


class VerificationStatus(str, Enum):
    """Three-state verification status (replaces ambiguous ``verified: bool``)."""

    VALID = "valid"
    REVOKED = "revoked"
    INVALID = "invalid"


class VerificationResult(BaseModel):
    """The single source of truth for verification outcomes.

    - ``status == "valid"``:    signature, Merkle root, and revocation all passed.
    - ``status == "revoked"``:  credential found in the revocation list.
    - ``status == "invalid"``:  any structural, cryptographic, or infrastructure error.
    """

    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    reason: str | None = Field(
        default=None,
        description="Human-readable reason when status is revoked/invalid.",
    )
    credential: dict | None = Field(
        default=None,
        description="Rendered Verifiable Credential (only present when parsing succeeded).",
    )

    @computed_field  # type: ignore[misc]
    @property
    def verified(self) -> bool:
        """Convenience boolean for legacy callers (``status == VALID``)."""
        return self.status is VerificationStatus.VALID

    # -- factory helpers --------------------------------------------------

    @classmethod
    def valid(cls, credential: dict) -> VerificationResult:
        return cls(status=VerificationStatus.VALID, credential=credential)

    @classmethod
    def revoked(cls, credential: dict, reason: str | None) -> VerificationResult:
        return cls(
            status=VerificationStatus.REVOKED,
            reason=reason or "credential has been revoked",
            credential=credential,
        )

    @classmethod
    def invalid(cls, reason: str, credential: dict | None = None) -> VerificationResult:
        return cls(status=VerificationStatus.INVALID, reason=reason, credential=credential)