"""Structured view of the fixed parts of a W3C Verifiable Credential.

The full credential is a JSON-LD document whose shape depends on the VC
template, so it is kept as ``dict``. Only the fixed ``credentialStatus``
structure is modelled with pydantic for early validation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RevocationListAddress(BaseModel):
    """Bitcoin address holding the revocation list."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., description="e.g. 'btc:testnet:legacy'")
    val: str = Field(..., description="Bitcoin address of the revocation list")


class CredentialStatus(BaseModel):
    """The ``credentialStatus`` block of a Verifiable Credential."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    type: list[str]
    issuer: str = Field(..., description="DID of the revocation list issuer")
    revocation_list_address: RevocationListAddress = Field(
        ..., alias="revocationListAddress"
    )
    revocation_list_index: list[int] = Field(
        ...,
        alias="revocationListIndex",
        description="[individual_index, group_index]",
    )

    @property
    def individual_index(self) -> int:
        return self.revocation_list_index[0]

    @property
    def group_index(self) -> int:
        return self.revocation_list_index[1]

    @property
    def revocation_mode(self) -> str:
        """Return the second element of ``type`` (FullSnapshot / SingleSnapshot)."""
        return self.type[1] if len(self.type) > 1 else ""


def extract_credential_status(full_vc: dict) -> CredentialStatus:
    """Parse and validate the ``credentialStatus`` block of a rendered VC.

    Raises:
        pydantic.ValidationError: if the block is missing or malformed.
    """
    raw = full_vc.get("credentialStatus")
    if not isinstance(raw, dict):
        raise ValueError("credentialStatus block is missing or not an object")
    return CredentialStatus.model_validate(raw)