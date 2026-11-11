"""Round-trip tests for VC fingerprints across a range of payload sizes."""

from __future__ import annotations

import pytest

from backend.encoding.cbor_multibase import vc_fp_decode, vc_fp_encode


@pytest.mark.parametrize(
    "payload_size",
    [0, 1, 10, 100],
)
def test_roundtrip_various_payloads(payload_size: int):
    header = {"alg": "ES256", "typ": "ovc+ld+jwt"}
    payload = [f"item-{i}" for i in range(payload_size)]
    proof = {
        "bcn": "btc:regtest",
        "tid": "ff" * 32,
        "pth": [1, "aa" * 32, 0, "bb" * 32],
    }

    encoded = vc_fp_encode(header, payload, proof)
    d_header, d_payload, d_proof = vc_fp_decode(encoded)

    assert d_header == header
    assert d_payload == payload
    assert d_proof["tid"] == proof["tid"]
    # pth is converted to wire format [1, "aa".., 0, "bb"..]
    assert d_proof["pth"] == [1, "aa" * 32, 0, "bb" * 32]


def test_encoded_size_is_compact():
    """The encoded fingerprint should be significantly smaller than raw JSON."""
    import json

    header = {"alg": "ES256", "typ": "ovc+ld+jwt"}
    payload = [["did:example:123", "Alice"], [["course1", "A"], ["course2", "B"]]]
    proof = {"bcn": "btc:regtest", "tid": "ff" * 32, "pth": [1, "aa" * 32]}

    encoded = vc_fp_encode(header, payload, proof)
    raw_json = json.dumps({"header": header, "payload": payload, "proof": proof})
    assert len(encoded) < len(raw_json)