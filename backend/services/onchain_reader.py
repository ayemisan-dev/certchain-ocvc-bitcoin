"""Read OCVC protocol data from Bitcoin transactions.

This module understands the on-chain wire format (OP_RETURN layout, P2WSH
witness structure, Merkle root verification). 
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from backend.core.errors import BitcoinRPCError, MerkleProofError
from backend.core.logging import get_logger
from backend.encoding.cbor_multibase import cbor_decode, cbor_zlib_decode
from backend.encoding.pushdata import (
    decode_push_data,
    extract_all_pushdatas_from_script,
)
from backend.encoding.type_convertor import type_bin_to_str, type_hex_to_str

logger = get_logger(__name__)

PROTOCOL_ID_HEX = "4f435643"  # "OCVC"


# ---------------------------------------------------------------------------
# Low-level transaction reading
# ---------------------------------------------------------------------------

def bc_read(
    rpc_client, txid: str
) -> tuple[str | None, dict, str | None, int]:
    """Read OP_RETURN payload, first input, OCVC type, and timestamp (int)."""
    if rpc_client.network.value == "regtest":
        tx = rpc_client.gettransaction(txid)
        tx_data = rpc_client.decoderawtransaction(tx["hex"])
        t_tx = int(tx["time"])
    else:
        tx_data = rpc_client.getrawtransaction(txid, True)
        t_tx = int(tx_data.get("time", 0))

    op_return_asm: str | None = None
    tx_type: str | None = None

    last_out = tx_data["vout"][-1]
    if last_out["scriptPubKey"]["type"] == "nulldata":
        asm = last_out["scriptPubKey"]["asm"]
        payload = asm.split("OP_RETURN")[-1].lstrip()
        op_return_asm = payload
        if len(payload) >= 14:
            tx_type, _ = _get_tx_data_type(payload[12:14])

    return op_return_asm, tx_data["vin"][0], tx_type, t_tx


# ---------------------------------------------------------------------------
# OP_RETURN payload parsing
# ---------------------------------------------------------------------------

def _get_vc_data(op_return_asm: str) -> tuple[
    str | None, str | None, str | None, str | None, str | None
]:
    """Extract ``(tx_type, data_type, encoding_method, data, extra_data)``.

    ``data`` and ``extra_data`` are hex strings; ``None`` if absent.
    """
    if not op_return_asm.startswith("04" + PROTOCOL_ID_HEX):
        return None, None, None, None, None

    start = 10  # skip "04" + 4-byte OCVC
    raw = extract_all_pushdatas_from_script(op_return_asm, start, len(op_return_asm))
    pushes = decode_push_data(raw)

    if len(pushes) < 1:
        return None, None, None, None, None

    payload_hex = pushes[0].hex()
    tx_type, data_type = _get_tx_data_type(payload_hex[:2])
    encoding = type_hex_to_str(payload_hex[2:4])
    data = payload_hex[4:]

    extra_data = pushes[1].hex() if len(pushes) > 1 else None
    return tx_type, data_type, encoding, data, extra_data


def _get_tx_data_type(type_hex: str) -> tuple[str | None, str | None]:
    """Split one byte into (tx_type, data_type)."""
    try:
        value = int(type_hex, 16)
    except ValueError:
        return None, None
    binary = format(value, "08b")
    return type_bin_to_str(binary[:3]), type_bin_to_str(binary[3:])


def _decoded_vc_data(encoding_method: str | None, data_hex: str) -> Any:
    """Decode a hex string according to the declared encoding method.

    Returns ``str`` for No_Encoding, ``dict``/``list`` for CBOR variants,
    or ``None`` if decoding is not possible.
    """
    if encoding_method == "No_Encoding":
        return data_hex
    if encoding_method == "CBOR":
        return cbor_decode(bytes.fromhex(data_hex))
    if encoding_method == "CBOR_ZLIB":
        return json.loads(cbor_zlib_decode(data_hex))
    return None


# ---------------------------------------------------------------------------
# P2WSH witness extraction
# ---------------------------------------------------------------------------

def _get_data_from_script(rpc_client, tx_in: dict) -> tuple[str, str]:
    """Return ``(if_branch_hex, else_branch_hex)`` from a P2WSH witness."""
    try:
        witness_script = tx_in["txinwitness"][2]
    except (KeyError, IndexError) as exc:
        raise BitcoinRPCError("missing P2WSH witness in transaction input") from exc

    decoded = rpc_client.decodescript(witness_script)
    asm = decoded.get("asm", "")
    return _extract_if_else_blocks(asm)


def _extract_if_else_blocks(script_asm: str) -> tuple[str, str]:
    """Extract data pushed in ``OP_IF ... OP_ELSE ... OP_ENDIF``."""
    tokens = script_asm.strip().split()
    if_tokens: list[str] = []
    else_tokens: list[str] = []
    in_if = in_else = False

    for token in tokens:
        if token == "OP_IF":
            in_if, in_else = True, False
            continue
        if token == "OP_ELSE":
            in_if, in_else = False, True
            continue
        if token == "OP_ENDIF":
            break
        if in_if:
            if_tokens.append(token)
        elif in_else:
            else_tokens.append(token)

    return "".join(if_tokens), "".join(else_tokens)


# ---------------------------------------------------------------------------
# Merkle root verification
# ---------------------------------------------------------------------------

def cal_merkle_root(data_hash_hex: str, proof_path: list | None) -> str:
    """Reconstruct the Merkle root from a leaf hash and proof path.

    ``proof_path`` is ``[direction, sibling_hex, direction, sibling_hex, ...]``.
    ``direction == 0`` means the sibling is on the left; ``1`` means right.
    """
    if not proof_path:
        return data_hash_hex

    current = bytes.fromhex(data_hash_hex)
    for i in range(0, len(proof_path), 2):
        direction = proof_path[i]
        sibling = bytes.fromhex(proof_path[i + 1])
        if direction == 0: # left 
            current = hashlib.sha256(sibling + current).digest()
        else: # right 
            current = hashlib.sha256(current + sibling).digest()
    return current.hex()


# ---------------------------------------------------------------------------
# PS / PI / PD readers
# ---------------------------------------------------------------------------

def bc_get_ps(rpc_client, txid: str) -> tuple[bool, list | None]:
    """Read the OCVC protocol specification (``Cs = [protocol_desc, template, external]``)
    from a PS transaction's P2WSH witness."""
    op_return_asm, tx_in, tx_type, _ = bc_read(rpc_client, txid)
    if tx_type != "PS" or op_return_asm is None:
        return False, None

    _, data_type, encoding, _, _ = _get_vc_data(op_return_asm)
    if data_type != "Tx_Data_ScriptHash" or encoding is None:
        return False, None

    if_branch_hex, _ = _get_data_from_script(rpc_client, tx_in)
    cs = _decoded_vc_data(encoding, if_branch_hex)
    if not isinstance(cs, list):
        return False, None
    return True, cs


def bc_get_pi(
    rpc_client, txid: str
) -> tuple[bool, str | None, list | None]:
    """Read ``(is_valid, ps_txid, vi)`` from a PI transaction."""
    op_return_asm, tx_in, tx_type, _ = bc_read(rpc_client, txid)
    if tx_type != "PI" or op_return_asm is None:
        return False, None, None

    _, _, _, ps_txid, extra_hex = _get_vc_data(op_return_asm)
    if ps_txid is None or extra_hex is None:
        return False, None, None

    _, extra_data_type = _get_tx_data_type(extra_hex[:2])
    extra_encoding = type_hex_to_str(extra_hex[2:4])

    vi: Any = None
    if extra_data_type == "Tx_Data_ScriptHash":
        if_branch_hex, _ = _get_data_from_script(rpc_client, tx_in)
        vi = _decoded_vc_data(extra_encoding, if_branch_hex)
    elif extra_data_type in ("Text", "Encoded_Data"):
        vi = _decoded_vc_data(extra_encoding, extra_hex[4:])

    if not isinstance(vi, list):
        return False, None, None
    return True, ps_txid, vi


def bc_get_pd(
    rpc_client,
    payload: list | None,
    txid: str,
    proof_path: list | None = None,
) -> tuple[bool, str | None, int, str | None, list | None, int]:
    """Read ``(is_valid, prev_txid, t_tx, issuer_pubkey, vd, sequence)``."""
    op_return_asm, tx_in, tx_type, t_tx = bc_read(rpc_client, txid)

    if tx_type != "PD":
        return False, None, t_tx, None, None, 0

    prev_txid = tx_in["txid"]
    issuer_pubkey = _extract_pubkey(tx_in)

    if op_return_asm is None:
        return False, prev_txid, t_tx, issuer_pubkey, None, 0

    _, data_type, encoding, data, extra_hex = _get_vc_data(op_return_asm)
    is_valid = False
    vd: list | None = None

    if payload and data_type == "Hash_Value" and encoding == "SHA256" and data:
        leaf_hash = hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()
        try:
            root = cal_merkle_root(leaf_hash, proof_path)
        except Exception as exc:
            raise MerkleProofError(f"Merkle proof invalid: {exc}") from exc
        if root == data:
            is_valid = True
            vd = payload
    elif data_type == "Encoded_Data" and encoding == "CBOR" and data:
        decoded = _decoded_vc_data(encoding, data)
        if isinstance(decoded, list):
            is_valid = True
            vd = decoded

    sequence = 0
    if extra_hex and len(extra_hex) > 4:
        try:
            sequence = int(extra_hex[4:], 16)
        except ValueError:
            sequence = 0

    return is_valid, prev_txid, t_tx, issuer_pubkey, vd, sequence


def backward_traversal_pi_index(
    rpc_client, chain_len: int, prev_txid: str
) -> str | None:
    """Walk back ``chain_len - 1`` P2PKH hops to find the PI transaction id."""
    while chain_len > 1:
        if rpc_client.network.value == "regtest":
            tx = rpc_client.gettransaction(prev_txid)
            raw = bytes.fromhex(tx["hex"])
            offset = 4  # skip version
            n_inputs = raw[offset]
            if n_inputs == 0:
                return None
            offset += 1
            parent_txid_le = raw[offset : offset + 32]
            prev_txid = parent_txid_le[::-1].hex()
        else:
            tx_data = rpc_client.getrawtransaction(prev_txid, True)
            prev_txid = tx_data["vin"][0]["txid"]
        chain_len -= 1
    return prev_txid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_pubkey(tx_in: dict) -> str | None:
    """Extract the issuer public key from the transaction input."""
    if "txinwitness" in tx_in and len(tx_in["txinwitness"]) > 1:
        return tx_in["txinwitness"][1]
    if "scriptSig" in tx_in and "asm" in tx_in["scriptSig"]:
        return tx_in["scriptSig"]["asm"].split("[ALL]")[-1].lstrip()
    return None