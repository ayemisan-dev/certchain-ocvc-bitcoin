"""VC fingerprint structure (header.payload.proof).
This model only adds type validation on top of the existing dict representation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FingerprintHeader(BaseModel):
    """JOSE-style header of a VC fingerprint."""

    model_config = ConfigDict(extra="forbid")

    alg: str = Field("ES256", description="Signature algorithm identifier")
    typ: str = Field(
        "ovc+ld+jwt",
        description=(
            "Fingerprint type. "
            "'ovc+ld+jwt' = OCVC, "
            "'fbc+ld+jwt' = full blockcerts, "
            "'pbc+ld+jwt' = partial blockcerts."
        ),
    )


class FingerprintProof(BaseModel):
    """Proof block: blockchain anchor + Merkle path."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    bcn: str = Field(..., description="Blockchain identifier, e.g. 'btc:testnet'")
    tid: str = Field(..., description="PD transaction ID (hex)")
    pth: list | None = Field(
        default=None,
        description="Merkle proof path: [direction, sibling_hex, ...]",
    )
    ipfs: str | None = Field(default=None, description="IPFS CID for partial blockcerts")


class VCFingerprint(BaseModel):
    """Full VC fingerprint: header + payload + proof."""

    model_config = ConfigDict(extra="forbid")

    header: FingerprintHeader
    payload: list[Any] = Field(
        default_factory=list,
        description=(
            "Empty list for fully on-chain credentials (FO mode); "
            "credential-specific value array (vd) for partial on-chain mode (PO mode)."
        ),
    )
    proof: FingerprintProof

    @property
    def is_fully_onchain(self) -> bool:
        """True if the payload is empty (data lives entirely on-chain)."""
        return len(self.payload) == 0

    @property
    def is_partial_onchain(self) -> bool:
        """True if the payload carries ``vd`` (Merkle proof required)."""
        return not self.is_fully_onchain


def fingerprint_type_is_ocvc(fp: VCFingerprint) -> bool:
    """Return True if this fingerprint uses the OCVC protocol."""
    return fp.header.typ == "ovc+ld+jwt"


def fingerprint_type_is_blockcerts(fp: VCFingerprint) -> Literal["fbc", "pbc"] | None:
    """Return ``'fbc'`` / ``'pbc'`` for blockcerts fingerprints, else None."""
    if fp.header.typ == "fbc+ld+jwt":
        return "fbc"
    if fp.header.typ == "pbc+ld+jwt":
        return "pbc"
    return None