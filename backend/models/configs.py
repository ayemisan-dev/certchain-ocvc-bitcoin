"""Issuance configuration models (PS / PI / PD)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BaseTxConfig(BaseModel):
    """Fields common to every OCVC issuance transaction."""

    model_config = ConfigDict(extra="forbid")

    prev_txid: str = Field(..., min_length=64, max_length=64)
    vout: int = Field(..., ge=0)
    send_value: float = Field(..., gt=0)


# ---------------------------------------------------------------------------
# PS / PI
# ---------------------------------------------------------------------------

class PSConfig(BaseTxConfig):
    """Configuration for a PS (Protocol Specification) transaction."""

    tx_type: Literal["PS"] = "PS"
    data_type: Literal["Tx_Data_ScriptHash", "IPFS_CID"] = "Tx_Data_ScriptHash"
    segwit_status: Literal["create", "spend"]

    # Common to both create and spend
    data_path: str = Field(..., description="Path to the VC specification JSON")
    pub_key: str = Field(..., min_length=66, max_length=66, description="Compressed secp256k1 public key (hex)")

    # create-only
    priv_key: str | None = Field(default=None, description="WIF private key (create only)")

    # spend-only
    wif_privkey: str | None = Field(default=None, description="WIF private key (spend only)")
    receive_addr: str | None = None
    amount: float | None = Field(default=None, gt=0)
    encoding_method: Literal["No_Encoding", "CBOR", "CBOR_ZLIB"] | None = None


class PIConfig(BaseTxConfig):
    """Configuration for a PI (Protocol Instance Initialization) transaction."""

    tx_type: Literal["PI"] = "PI"
    data_type: Literal["Tx_Data_ScriptHash", "Text"] = "Tx_Data_ScriptHash"
    segwit_status: Literal["create", "spend"]

    data_path: str
    pub_key: str = Field(..., min_length=66, max_length=66)

    priv_key: str | None = None

    # spend-only
    wif_privkey: str | None = None
    receive_addr: str | None = None
    amount: float | None = Field(default=None, gt=0)
    ps_txid: str | None = Field(
        default=None, min_length=64, max_length=64, description="Reference to the PS transaction"
    )
    encoding_method: Literal["No_Encoding", "CBOR", "CBOR_ZLIB"] | None = None
    extra_data_type: Literal["Tx_Data_ScriptHash", "Text", "Encoded_Data"] | None = None
    extra_encoding_method: Literal["No_Encoding", "CBOR", "CBOR_ZLIB"] | None = None


# ---------------------------------------------------------------------------
# PD (degree)
# ---------------------------------------------------------------------------

class PDDegreeConfig(BaseTxConfig):
    """Configuration for a degree-batch PD transaction."""

    tx_type: Literal["PD"] = "PD"
    data_type: Literal["Hash_Value", "Encoded_Data"] = "Hash_Value"
    encoding_method: Literal["SHA256", "CBOR", "CBOR_ZLIB"] = "SHA256"
    extra_data_type: Literal["Text", "Encoded_Data"] = "Text"
    extra_encoding_method: Literal["No_Encoding", "CBOR", "CBOR_ZLIB"] = "No_Encoding"

    sequence: int = Field(..., ge=1, description="Chain position (1 = first PD after PI)")
    priv_key: str
    receive_addr: str
    file_name: str = Field(..., description="Prefix for output fingerprint files")

    full_vc_list_path: str
    vc_temp_path: str
    vc_fp_tem_path: str
    vc_fp_path: str
    qrcode_path: str

    vc_type: str = Field(..., description="'BSc' by default; affects VC decomposition")


# ---------------------------------------------------------------------------
# PD (revocation)
# ---------------------------------------------------------------------------

class PDRevocationConfig(BaseTxConfig):
    """Configuration for a revocation-list PD transaction.

    Supports both encoding methods (bitstring and index-list). Fields that
    only apply to one method are optional.
    """

    tx_type: Literal["PD"] = "PD"
    data_type: Literal["Encoded_Data"] = "Encoded_Data"
    encoding_method: Literal["CBOR", "CBOR_ZLIB"] = "CBOR"
    extra_data_type: Literal["Text"] = "Text"
    extra_encoding_method: Literal["No_Encoding"] = "No_Encoding"

    rev_type: Literal["bitstring", "indexList"]
    mode: Literal["accumulate", "single"] = "single"
    sequence: int = Field(..., ge=1)

    revoked_list: list[int] = Field(..., min_length=1)
    reason_list: list[int] = Field(..., min_length=1)
    bitPerCred: int = Field(..., ge=1, le=8)

    # bitstring-only
    bits_len: int | None = Field(default=None, gt=0)
    m: int | None = Field(default=None, gt=0)

    # indexList-only
    vc_size: int | None = Field(default=None, gt=0)

    priv_key: str
    receive_addr: str

    def validate_for_rev_type(self) -> None:
        """Raise ValueError if mandatory fields for ``rev_type`` are missing."""
        if self.rev_type == "bitstring":
            if self.bits_len is None or self.m is None:
                raise ValueError("bitstring mode requires 'bits_len' and 'm'")
        elif self.rev_type == "indexList":
            if self.vc_size is None:
                raise ValueError("indexList mode requires 'vc_size'")
        if len(self.revoked_list) != len(self.reason_list):
            raise ValueError(
                f"'revoked_list' and 'reason_list' must have the same length "
                f"(got {len(self.revoked_list)} vs {len(self.reason_list)})"
            )