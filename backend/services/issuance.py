"""Credential and revocation-list issuance.

Implements the OCVC PS / PI / PD transaction flow. 
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.core.errors import BitcoinRPCError
from backend.core.logging import get_logger
from backend.encoding.cbor_multibase import cbor_encode, cbor_zlib_encode, vc_fp_encode
from backend.encoding.jsonld import decompose_vc
from backend.encoding.pushdata import encode_push_data
from backend.encoding.type_convertor import (
    binary_to_hex,
    int_to_hex,
    type_str_to_binary,
    type_str_to_hex,
)
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.infra.bitcoin.segwit import create_p2wsh, create_witness_script_if, spend_p2wsh
from backend.models.configs import (
    PIConfig,
    PDDegreeConfig,
    PDRevocationConfig,
    PSConfig,
)

logger = get_logger(__name__)

PROTOCOL_ID_HEX = "4f435643"  # "OCVC"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def issue_transaction(
    config: PSConfig | PIConfig | PDDegreeConfig | PDRevocationConfig,
    rpc_client: BitcoinRPCClient,
    pd_data_hex: str | None = None,
) -> str:
    """Dispatch to the correct issue function based on config type.

    For PD transactions, ``pd_data_hex`` MUST be provided (Merkle root hex,
    or encoded-vd hex, depending on ``config.data_type``).
    """
    if isinstance(config, (PSConfig, PIConfig)):
        return _issue_ps_or_pi(config, rpc_client)

    if isinstance(config, (PDDegreeConfig, PDRevocationConfig)):
        if pd_data_hex is None:
            raise ValueError(
                "PD transaction requires pd_data_hex (Merkle root or encoded vd)"
            )
        return _issue_pd(config, pd_data_hex, rpc_client)

    raise TypeError(f"unsupported config type: {type(config).__name__}")


# ---------------------------------------------------------------------------
# PS / PI: P2WSH create + spend
# ---------------------------------------------------------------------------

def _issue_ps_or_pi(config: PSConfig | PIConfig, rpc_client: BitcoinRPCClient) -> str:
    """Issue a PS or PI transaction (two-stage: P2WSH create + spend)."""
    if config.segwit_status == "create":
        if not config.priv_key:
            raise ValueError(f"{config.tx_type} create requires 'priv_key'")
        encoded_data = _load_data_for_p2wsh(config)
        witness_script = create_witness_script_if(encoded_data, config.pub_key)
        signed = create_p2wsh(
            rpc_client,
            config.prev_txid,
            config.vout,
            config.send_value,
            config.priv_key,
            witness_script,
        )
        return rpc_client.sendrawtransaction(signed)

    if config.segwit_status == "spend":
        if not config.wif_privkey:
            raise ValueError(f"{config.tx_type} spend requires 'wif_privkey'")
        if not config.receive_addr:
            raise ValueError(f"{config.tx_type} spend requires 'receive_addr'")
        if config.amount is None or config.amount <= 0:
            raise ValueError(
                f"{config.tx_type} spend requires 'amount' "
                f"(must equal the send_value of the corresponding create transaction)"
            )

        if config.tx_type == "PS":
            metadata = _build_ps_metadata(config)
        else:
            metadata = _build_pi_metadata(config)

        if metadata is None:
            raise ValueError(f"{config.tx_type} metadata exceeds 80 bytes")

        data_for_witness = _load_data_for_p2wsh(config)
        witness_script = create_witness_script_if(data_for_witness, config.pub_key)

        # Cross-check: config.amount must equal the on-chain UTXO amount.
        # A mismatch would make BIP143 sighash wrong, causing NULLFAIL.
        input_amount_sat = _utxo_amount_sat(rpc_client, config.prev_txid, config.vout)
        config_amount_sat = round(config.amount * 1e8)
        if input_amount_sat != config_amount_sat:
            raise ValueError(
                f"{config.tx_type} spend: 'amount' in config is "
                f"{config.amount} BTC ({config_amount_sat} sat), but the UTXO "
                f"{config.prev_txid}:{config.vout} holds "
                f"{input_amount_sat} sat ({input_amount_sat / 1e8:.8f} BTC). "
                f"Set 'amount' to {input_amount_sat / 1e8:.8f} in the config."
            )

        signed = spend_p2wsh(
            rpc_client,
            prev_txid=config.prev_txid,
            vout=config.vout,
            input_amount_sat=input_amount_sat,
            send_value_sat=round(config.send_value * 1e8),
            receive_addr=config.receive_addr,
            witness_script_hex=witness_script,
            wif_private_key=config.wif_privkey,
            op_return_hex=metadata,
        )
        return rpc_client.sendrawtransaction(signed)

    raise ValueError(f"unknown segwit_status: {config.segwit_status}")


def _utxo_amount_sat(rpc_client: BitcoinRPCClient, txid: str, vout: int) -> int:
    from decimal import Decimal

    if rpc_client.network.value == "regtest":
        tx = rpc_client.gettransaction(txid)
        tx_data = rpc_client.decoderawtransaction(tx["hex"])
    else:
        tx_data = rpc_client.getrawtransaction(txid, True)

    raw_value = tx_data["vout"][vout]["value"]
    if isinstance(raw_value, Decimal):
        return int(raw_value * Decimal("100000000"))
    return round(float(raw_value) * 1e8)


# ---------------------------------------------------------------------------
# PD: P2PKH
# ---------------------------------------------------------------------------

def _issue_pd(
    config: PDDegreeConfig | PDRevocationConfig,
    data_hex: str,
    rpc_client: BitcoinRPCClient,
) -> str:
    """Issue a PD transaction (single P2PKH tx)."""
    metadata = _build_pd_metadata(config, data_hex)
    if metadata is None:
        raise ValueError("PD metadata exceeds 80 bytes")

    inputs = [{"txid": config.prev_txid, "vout": config.vout}]
    outputs: dict[str, Any] = {config.receive_addr: config.send_value, "data": metadata}

    unsigned_hex = rpc_client.createrawtransaction(inputs, outputs)
    signed = rpc_client.signrawtransactionwithkey(unsigned_hex, [config.priv_key])
    if not signed.get("complete"):
        raise BitcoinRPCError(f"signrawtransactionwithkey failed: {signed}")
    return rpc_client.sendrawtransaction(signed["hex"])


# ---------------------------------------------------------------------------
# OP_RETURN metadata builders (wire format preserved from original code)
# ---------------------------------------------------------------------------

def _build_ps_metadata(config: PSConfig) -> str | None:
    """PS OP_RETURN: OCVC + [TYPE=0x05||encoding||hash]."""
    tx_bin = type_str_to_binary(config.tx_type)
    data_bin = type_str_to_binary(config.data_type)
    if tx_bin is None or data_bin is None:
        return None
    tx_data_type = binary_to_hex(tx_bin + data_bin)

    encoding_method = type_str_to_hex(config.encoding_method or "CBOR_ZLIB")
    if encoding_method is None:
        return None

    vc_temp_hash = _sha256_canonical_json(config.data_path)
    data = encoding_method + vc_temp_hash
    payload = encode_push_data(bytes.fromhex(tx_data_type + data))
    metadata = "04" + PROTOCOL_ID_HEX + payload.hex()
    return metadata if len(metadata) <= 160 else None


def _build_pi_metadata(config: PIConfig) -> str | None:
    """PI OP_RETURN: OCVC + [PS txid] + [vi hash]."""
    tx_bin = type_str_to_binary(config.tx_type)
    data_bin = type_str_to_binary(config.data_type)
    if tx_bin is None or data_bin is None:
        return None
    tx_data_type = binary_to_hex(tx_bin + data_bin)

    ps_txid = config.ps_txid or ""
    data_encoding = type_str_to_hex(config.encoding_method or "No_Encoding")
    if data_encoding is None:
        return None
    data = tx_data_type + data_encoding + ps_txid
    push_data = encode_push_data(bytes.fromhex(data))

    extra_type = config.extra_data_type or "Tx_Data_ScriptHash"
    extra_tx_data_type = type_str_to_hex(extra_type)
    extra_encoding = config.extra_encoding_method or "CBOR_ZLIB"
    extra_encoding_method = type_str_to_hex(extra_encoding)
    if extra_tx_data_type is None or extra_encoding_method is None:
        return None

    if extra_type == "Tx_Data_ScriptHash":
        extra_data = _sha256_canonical_json(config.data_path)
    elif extra_type in ("Text", "Encoded_Data"):
        vi_data = _load_json(config.data_path)
        extra_data = _encoded_vc_data(extra_encoding, vi_data)
    else:
        return None

    full_extra = extra_tx_data_type + extra_encoding_method + extra_data
    push_extra = encode_push_data(bytes.fromhex(full_extra))
    metadata = "04" + PROTOCOL_ID_HEX + push_data.hex() + push_extra.hex()
    return metadata if len(metadata) <= 160 else None


def _build_pd_metadata(
    config: PDDegreeConfig | PDRevocationConfig,
    data_hex: str,
) -> str | None:
    """PD OP_RETURN: OCVC + [merkleRoot || encoded_vd] + [sequence].

    ``data_hex`` is the pre-computed payload (Merkle root for Hash_Value mode,
    or CBOR-encoded vd for Encoded_Data mode).
    """
    tx_bin = type_str_to_binary(config.tx_type)
    data_bin = type_str_to_binary(config.data_type)
    if tx_bin is None or data_bin is None:
        return None
    tx_data_type = binary_to_hex(tx_bin + data_bin)

    encoding_method = type_str_to_hex(config.encoding_method)
    if encoding_method is None:
        return None
    vd_data = encoding_method + data_hex
    push_data = encode_push_data(bytes.fromhex(tx_data_type + vd_data))

    extra_tx_data_type = type_str_to_hex(config.extra_data_type)
    extra_encoding_method = type_str_to_hex(config.extra_encoding_method)
    if extra_tx_data_type is None or extra_encoding_method is None:
        return None
    extra = extra_tx_data_type + extra_encoding_method + int_to_hex(config.sequence)
    push_extra = encode_push_data(bytes.fromhex(extra))

    metadata = "04" + PROTOCOL_ID_HEX + push_data.hex() + push_extra.hex()
    return metadata if len(metadata) <= 160 else None


# ---------------------------------------------------------------------------
# Merkle tree (self-implemented, replaces merkletools)
# ---------------------------------------------------------------------------

def _single_sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def merkle_root_and_proofs(leaves: list) -> tuple[str, list[list[dict]]]:
    """Compute the Merkle root and per-leaf proof paths.

    Matches ``MerkleTools(hash_type="SHA256")`` behaviour:
    - leaf hash: single SHA256 of ``json.dumps(leaf)``
    - internal: single SHA256 of ``left + right``
    - odd leaves at a level are duplicated (last one repeated)
    """
    if not leaves:
        raise ValueError("cannot compute Merkle root of empty list")

    leaf_hashes = [_single_sha256(json.dumps(leaf).encode("utf-8")) for leaf in leaves]
    n = len(leaf_hashes)

    next_pow2 = 1 << (n - 1).bit_length()
    padded = leaf_hashes + [leaf_hashes[-1]] * (next_pow2 - n)

    levels = [padded]
    while len(levels[-1]) > 1:
        current = levels[-1]
        next_level = [
            _single_sha256(current[i] + current[i + 1])
            for i in range(0, len(current), 2)
        ]
        levels.append(next_level)

    root = levels[-1][0].hex()

    proofs: list[list[dict]] = []
    for i in range(n):
        proof: list[dict] = []
        idx = i
        for level_idx in range(len(levels) - 1):
            sibling_idx = idx ^ 1
            sibling = levels[level_idx][sibling_idx]
            direction = "right" if idx % 2 == 0 else "left"
            proof.append({direction: sibling.hex()})
            idx //= 2
        proofs.append(proof)

    return root, proofs


# ---------------------------------------------------------------------------
# vc_fp generation
# ---------------------------------------------------------------------------

def build_vc_fingerprints(
    vd_list: list,
    proofs: list[list[dict]],
    pd_txid: str,
    header: dict,
    bcn: str,
    payload_from_vd: bool = True,
) -> tuple[list[dict], list[str]]:
    """Return ``(vc_fp_list, encoded_vc_fp_list)``.

    ``bcn`` is the blockchain identifier, e.g. ``"btc:regtest"`` or ``"btc:testnet"``.
    """
    vc_fp_list: list[dict] = []
    encoded_list: list[str] = []

    for vd, proof in zip(vd_list, proofs):
        payload = vd if payload_from_vd else []
        fp = {
            "header": header,
            "payload": payload,
            "proof": {"bcn": bcn, "tid": pd_txid, "pth": proof},
        }
        vc_fp_list.append(fp)
        encoded_list.append(vc_fp_encode(header, payload, fp["proof"]))

    return vc_fp_list, encoded_list


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_canonical_json(path: str) -> str:
    """SHA256 of ``json.dumps(obj, sort_keys=True, separators=(',', ':'))``."""
    data = _load_json(path)
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_data_for_p2wsh(config: PSConfig | PIConfig) -> bytes:
    """Load the JSON file at ``config.data_path`` and CBOR+ZLIB encode it."""
    data = _load_json(config.data_path)
    serialized = json.dumps(data, separators=(",", ":"))
    return cbor_zlib_encode(serialized)


def _encoded_vc_data(encoding_method: str, data: Any) -> str:
    if encoding_method == "No_Encoding":
        return str(data)
    if encoding_method == "CBOR":
        return cbor_encode(data).hex()
    if encoding_method == "CBOR_ZLIB":
        return cbor_zlib_encode(data).hex()
    raise ValueError(f"unknown encoding method: {encoding_method}")