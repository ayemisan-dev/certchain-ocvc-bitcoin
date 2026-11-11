"""Unit tests for VC fingerprint wire-format compatibility."""

from __future__ import annotations

from backend.encoding.cbor_multibase import vc_fp_decode, vc_fp_encode


def test_example_fp_decodes(example_fp_text):
    """The legacy fingerprint from the original project must still decode."""
    header, payload, proof = vc_fp_decode(example_fp_text)

    assert header["alg"] == "ES256"
    assert header["typ"] == "ovc+ld+jwt"

    assert isinstance(payload, list)
    assert "bcn" in proof
    assert "tid" in proof
    assert len(proof["tid"]) == 64  # 32-byte txid, hex
    assert proof["tid"] == proof["tid"].lower()


def test_example_fp_roundtrip(example_fp_text):
    """Re-encoding a decoded fingerprint must produce the same string."""
    header, payload, proof = vc_fp_decode(example_fp_text)
    re_encoded = vc_fp_encode(header, payload, proof)

    # ZLIB / CBOR are deterministic -> re-encoding is byte-identical.
    assert re_encoded == example_fp_text


def test_fingerprint_empty_payload_fp_mode():
    """FO mode: empty payload, no Merkle proof."""
    header = {"alg": "ES256", "typ": "ovc+ld+jwt"}
    payload = []
    proof = {"bcn": "btc:regtest", "tid": "00" * 32, "pth": None}

    encoded = vc_fp_encode(header, payload, proof)
    parts = encoded.split(".")
    assert len(parts) == 3
    assert parts[1] == ""  # empty payload segment

    _, decoded_payload, decoded_proof = vc_fp_decode(encoded)
    assert decoded_payload == []
    assert "pth" not in decoded_proof