"""CBOR, ZLIB, Base64URL, and VC fingerprint encoding."""

from __future__ import annotations

import base64
import json
import zlib

import cbor2


# ---------------------------------------------------------------------------
# CBOR
# ---------------------------------------------------------------------------

def cbor_encode(data) -> bytes:
    """Encode ``data`` as CBOR bytes."""
    return cbor2.dumps(data)


def cbor_decode(encoded_bytes: bytes):
    """Decode CBOR bytes."""
    return cbor2.loads(encoded_bytes)


def cbor_zlib_encode(data) -> bytes:
    """CBOR-encode and ZLIB-compress ``data``."""
    return zlib.compress(cbor2.dumps(data))


def cbor_zlib_decode(zlib_hex: str | bytes):
    """Decompress ZLIB + CBOR-decode.

    Accepts either a hex string (original behaviour) or raw bytes.
    """
    zlib_bytes = (
        bytes.fromhex(zlib_hex) if isinstance(zlib_hex, str) else zlib_hex
    )
    return cbor2.loads(zlib.decompress(zlib_bytes))


# ---------------------------------------------------------------------------
# Base64URL (no padding)
# ---------------------------------------------------------------------------

def base64url_encode_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def base64url_decode_str(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


# ---------------------------------------------------------------------------
# Proof helpers (used by vc_fp_encode / vc_fp_decode)
# ---------------------------------------------------------------------------

def encode_proof_bytes(proof: dict) -> dict:
    """Convert ``tid`` and ``pth`` hex strings to bytes (for CBOR compactness).

    ``pth`` may be missing or ``None`` (FO mode: fully on-chain credentials
    do not need a Merkle proof). In that case it is omitted.
    """
    result: dict = {}
    if "bcn" in proof:
        result["bcn"] = proof["bcn"]
    if "tid" in proof:
        result["tid"] = bytes.fromhex(proof["tid"])
    pth = proof.get("pth")
    if pth:
        result["pth"] = _map_path_bytes(pth)
    if "ipfs" in proof:
        result["ipfs"] = proof["ipfs"]
    return result


def decode_proof_bytes(proof: dict) -> dict:
    """Convert ``tid`` and ``pth`` back to hex strings."""
    if "tid" in proof:
        proof["tid"] = proof["tid"].hex()
    if "pth" in proof and proof["pth"]:
        proof["pth"] = _decode_map_path_bytes(proof["pth"])
    return proof


def _map_path_bytes(path_data: list[dict[str, str]] | list[int | str] | None) -> list[int | bytes]:
    """Flatten a proof path into ``[direction, bytes, ...]``.

    Supports both formats:
    - issuer format: ``[{"right": "hex"}, {"left": "hex"}]``
    - wire format:   ``[1, "hex", 0, "hex"]`` (returned by ``vc_fp_decode``)
    """
    if not path_data:
        return []

    # Wire format: already a flat list of (int, hex) pairs.
    if isinstance(path_data[0], int):
        path_list: list[int | bytes] = []
        for i in range(0, len(path_data), 2):
            direction = path_data[i]
            hex_str = path_data[i + 1]
            if isinstance(direction, int) and isinstance(hex_str, str):
                path_list.append(direction)
                path_list.append(bytes.fromhex(hex_str))
        return path_list

    # Issuer format: list of dicts.
    path_list = []
    for item in path_data:
        if isinstance(item, dict):
            if "right" in item:
                path_list.append(1)
                path_list.append(bytes.fromhex(item["right"]))
            elif "left" in item:
                path_list.append(0)
                path_list.append(bytes.fromhex(item["left"]))
    return path_list


def _decode_map_path_bytes(path_list: list) -> list:
    """Reverse ``_map_path_bytes``."""
    decoded: list = []
    for i in range(0, len(path_list), 2):
        decoded.append(path_list[i])
        decoded.append(path_list[i + 1].hex())
    return decoded


# ---------------------------------------------------------------------------
# VC fingerprint (header.payload.proof) — DO NOT CHANGE THE WIRE FORMAT
# ---------------------------------------------------------------------------

def vc_fp_encode(header: dict, payload, proof: dict) -> str:
    """Encode a VC fingerprint as Base64URL(ZLIB(CBOR(...))) × 3 segments.
    """
    cbor_header = cbor2.dumps(header)
    b64_header = base64url_encode_bytes(zlib.compress(cbor_header))

    cbor_proof = cbor2.dumps(encode_proof_bytes(proof))
    b64_proof = base64url_encode_bytes(zlib.compress(cbor_proof))

    if payload:
        cbor_payload = cbor2.dumps(payload)
        b64_payload = base64url_encode_bytes(zlib.compress(cbor_payload))
    else:
        b64_payload = ""

    return f"{b64_header}.{b64_payload}.{b64_proof}"


def vc_fp_decode(encoded: str) -> tuple[dict, list, dict]:
    """Decode a VC fingerprint back to (header, payload, proof)."""
    b64_header, b64_payload, b64_proof = encoded.split(".")

    header = cbor2.loads(zlib.decompress(base64url_decode_str(b64_header)))

    if b64_payload == "":
        payload = []
    else:
        payload = cbor2.loads(zlib.decompress(base64url_decode_str(b64_payload)))

    encoded_proof = cbor2.loads(zlib.decompress(base64url_decode_str(b64_proof)))
    proof = decode_proof_bytes(encoded_proof)

    return header, payload, proof