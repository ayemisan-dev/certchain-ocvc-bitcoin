"""P2WSH transaction construction (BIP143).

This module knows how to build a SegWit P2WSH output (``create``) and how to
spend a P2WSH UTXO (``spend``). It does not know what the payload means.
"""

from __future__ import annotations

import hashlib
import struct

import base58
import ecdsa
from ecdsa.util import sigencode_der_canonize

from backend.core.errors import BitcoinRPCError
from backend.encoding.pushdata import encode_push_data


# ---------------------------------------------------------------------------
# P2WSH output creation
# ---------------------------------------------------------------------------

def create_witness_script_if(data_bytes: bytes, public_key_hex: str) -> str:
    """Build ``OP_IF <data...> OP_ELSE <pubKey> OP_CHECKSIG OP_ENDIF``."""
    push_data = _create_data_chunk(data_bytes)
    pubkey_bytes = bytes.fromhex(public_key_hex)
    pubkey_push = f"{len(pubkey_bytes):02x}" + public_key_hex
    return "63" + push_data + "67" + pubkey_push + "ac68"


def _create_data_chunk(data_bytes: bytes) -> str:
    """Split ``data_bytes`` into ≤520-byte chunks, pushdata-encoded."""
    chunks = [data_bytes[i : i + 520] for i in range(0, len(data_bytes), 520)]
    return "".join(encode_push_data(chunk).hex() for chunk in chunks)


def create_p2wsh(
    rpc_client,
    prev_txid: str,
    vout: int,
    send_value: float,
    private_key: str,
    witness_script: str,
) -> str:
    """Create a P2WSH UTXO. Returns the signed transaction hex.

    The address is computed locally (``sha256(witness_script)`` → bech32)
    instead of relying on ``decodescript``, whose response shape varies
    across Bitcoin Core versions.
    """
    if len(witness_script) // 2 > 3600:
        raise BitcoinRPCError("witness_script exceeds the 3600-byte policy limit")

    from backend.infra.bitcoin.address import p2wsh_address_from_script

    p2wsh_address = p2wsh_address_from_script(witness_script, rpc_client.network.value)

    unsigned_hex = rpc_client.createrawtransaction(
        [{"txid": prev_txid, "vout": vout}], {p2wsh_address: send_value}
    )
    signed = rpc_client.signrawtransactionwithkey(unsigned_hex, [private_key])

    if not signed.get("complete"):
        raise BitcoinRPCError(f"signrawtransactionwithkey failed: {signed}")
    return signed["hex"]


# ---------------------------------------------------------------------------
# P2WSH spending
# ---------------------------------------------------------------------------

def spend_p2wsh(
    rpc_client,
    prev_txid: str,
    vout: int,
    input_amount_sat: int,
    send_value_sat: int,
    receive_addr: str,
    witness_script_hex: str,
    wif_private_key: str,
    op_return_hex: str,
) -> str:
    """Spend a P2WSH UTXO and attach an OP_RETURN output.

    Both ``input_amount_sat`` and ``send_value_sat`` are in **satoshis**.
    """
    version = 2
    locktime = 0

    # tx inputs
    inputs = [{"txid": prev_txid, "vout": vout}]

    # tx outputs#1: {to, amount}
    receive_spk = bytes.fromhex(rpc_client.validateaddress(receive_addr)["scriptPubKey"])
    outputs = [{"amount": send_value_sat, "script_pubkey": receive_spk}]

    # tx output#2: op_return data 
    op_return_data = bytes.fromhex(op_return_hex)
    outputs.append(
        {"amount": 0, "script_pubkey": b"\x6a" + encode_push_data(op_return_data)}
    )

    script_code = bytes.fromhex(witness_script_hex)
    sighash = _create_sighash(version, inputs, outputs, locktime, 0, script_code, input_amount_sat)
    signature = _sign_input(sighash, wif_private_key)

    witness = [[signature, b"", script_code]]
    return _build_final_tx(version, inputs, outputs, witness)


# ---------------------------------------------------------------------------
# BIP143 internals  
# ---------------------------------------------------------------------------

def _sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _var_int(n: int) -> bytes:
    if n < 0xFD:
        return struct.pack("B", n)
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def _hash_prevouts(inputs: list[dict]) -> bytes:
    data = b"".join(
        bytes.fromhex(inp["txid"])[::-1] + struct.pack("<I", inp["vout"]) for inp in inputs
    )
    return _sha256d(data)


def _hash_sequence(inputs: list[dict]) -> bytes:
    return _sha256d(b"".join(struct.pack("<I", 0xFFFFFFFF) for _ in inputs))


def _hash_outputs(outputs: list[dict]) -> bytes:
    data = b"".join(
        struct.pack("<Q", int(out["amount"]))
        + _var_int(len(out["script_pubkey"]))
        + out["script_pubkey"]
        for out in outputs
    )
    return _sha256d(data)


def _create_sighash(
    version: int,
    inputs: list[dict],
    outputs: list[dict],
    locktime: int,
    input_index: int,
    script_code: bytes,
    input_amount_sat: int,
) -> bytes:
    preimage = (
        struct.pack("<I", version)
        + _hash_prevouts(inputs)
        + _hash_sequence(inputs)
        + bytes.fromhex(inputs[input_index]["txid"])[::-1]
        + struct.pack("<I", inputs[input_index]["vout"])
        + _var_int(len(script_code))
        + script_code
        + struct.pack("<Q", input_amount_sat)
        + struct.pack("<I", 0xFFFFFFFF)
        + _hash_outputs(outputs)
        + struct.pack("<I", locktime)
        + struct.pack("<I", 1)  # SIGHASH_ALL
    )
    return _sha256d(preimage)


def _sign_input(sighash: bytes, wif_private_key: str) -> bytes:
    decoded = base58.b58decode_check(wif_private_key)
    private_key_bytes = decoded[1:-1] if len(decoded) == 34 else decoded[1:]
    sk = ecdsa.SigningKey.from_string(private_key_bytes, curve=ecdsa.SECP256k1)
    signature = sk.sign_digest(sighash, sigencode=sigencode_der_canonize)
    return signature + b"\x01"  # SIGHASH_ALL


def _build_final_tx(
    version: int, inputs: list[dict], outputs: list[dict], witness: list[list[bytes]]
) -> str:
    tx = struct.pack("<I", version) + b"\x00\x01"  # SegWit marker + flag
    tx += _var_int(len(inputs))
    for inp in inputs:
        tx += bytes.fromhex(inp["txid"])[::-1]
        tx += struct.pack("<I", inp["vout"])
        tx += _var_int(0)
        tx += struct.pack("<I", 0xFFFFFFFF)
    tx += _var_int(len(outputs))
    for out in outputs:
        tx += struct.pack("<Q", int(out["amount"]))
        tx += _var_int(len(out["script_pubkey"])) + out["script_pubkey"]
    for stack in witness:
        tx += _var_int(len(stack))
        for item in stack:
            tx += _var_int(len(item)) + item
    tx += struct.pack("<I", 0)  # locktime
    return tx.hex()