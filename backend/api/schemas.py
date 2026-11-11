"""Request and response schemas for the public API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VerifyRequest(BaseModel):
    """Request body for ``POST /api/verify`` (JSON mode)."""

    model_config = ConfigDict(extra="forbid")

    fingerprint: str = Field(
        ...,
        min_length=1,
        description="Base64URL-encoded VC fingerprint string.",
    )


class VerifyResponse(BaseModel):
    """Response body for ``POST /api/verify``.

    Field names mirror the ``VerificationResult`` model so the API layer
    stays a thin wrapper.
    """

    model_config = ConfigDict(extra="forbid")

    verification_status: str = Field(
        ...,
        description="'valid' | 'revoked' | 'invalid'",
    )
    verified: bool = Field(
        ...,
        description="Convenience boolean: True iff verification_status == 'valid'.",
    )
    reason: str | None = Field(
        default=None,
        description="Human-readable reason for revoked/invalid outcomes.",
    )
    vc: dict | None = Field(
        default=None,
        description="Rendered Verifiable Credential (only if parsing succeeded).",
    )