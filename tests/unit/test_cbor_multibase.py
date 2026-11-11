"""Unit tests for encoding/cbor_multibase.py."""

from __future__ import annotations

import pytest

from backend.encoding.cbor_multibase import (
    cbor_decode,
    cbor_encode,
    cbor_zlib_decode,
    cbor_zlib_encode,
    vc_fp_decode,
    vc_fp_encode,
)


@pytest.mark.parametrize(
    "data",
    [
        "hello",
        42,
        [1, 2, 3],
        {"key": "value", "nested": [1, {"a": 2}]},
        ["cred/1", "2025-09-02", [["did:example:123", "Alice"]]],
    ],
)
def test_cbor_roundtrip(data):
    encoded = cbor_encode(data)
    assert cbor_decode(encoded) == data


def test_cbor_zlib_roundtrip_large():
    # Large payload should be smaller after CBOR+ZLIB than raw JSON
    import json

    data = {"items": [f"item-{i}" for i in range(1000)]}
    raw_json = json.dumps(data).encode()
    compressed = cbor_zlib_encode(data)
    assert len(compressed) < len(raw_json)
    assert cbor_zlib_decode(compressed) == data


def test_cbor_zlib_decode_accepts_hex_and_bytes():
    data = ["a", "b"]
    encoded = cbor_zlib_encode(data)
    assert cbor_zlib_decode(encoded) == data
    assert cbor_zlib_decode(encoded.hex()) == data


@pytest.fixture
def sample_fp():
    header = {"alg": "ES256", "typ": "ovc+ld+jwt"}
    payload = ["cred/1", "2025-09-02", [["did:btcr:test", "Alice"]]]
    proof = {
        "bcn": "btc:regtest",
        "tid": "00" * 32,
        "pth": [{"right": "aa" * 32}, {"left": "bb" * 32}],
    }
    return header, payload, proof


def test_vc_fp_encode_decode_roundtrip(sample_fp):
    header, payload, proof = sample_fp
    encoded = vc_fp_encode(header, payload, proof)

    assert encoded.count(".") == 2

    decoded_header, decoded_payload, decoded_proof = vc_fp_decode(encoded)
    assert decoded_header == header
    assert decoded_payload == payload
    assert decoded_proof["bcn"] == proof["bcn"]
    assert decoded_proof["tid"] == proof["tid"]

    # pth is converted to wire format: [{"right": hex}] -> [1, hex]
    expected_pth = [
        1, "aa" * 32,   # {"right": "aa"*32}
        0, "bb" * 32,   # {"left": "bb"*32}
    ]
    assert decoded_proof["pth"] == expected_pth


def test_vc_fp_encode_empty_payload():
    header = {"alg": "ES256", "typ": "ovc+ld+jwt"}
    payload = []
    proof = {"bcn": "btc:regtest", "tid": "00" * 32, "pth": None}

    encoded = vc_fp_encode(header, payload, proof)
    assert encoded.split(".")[1] == ""  # empty payload

    _, decoded_payload, decoded_proof = vc_fp_decode(encoded)
    assert decoded_payload == []
    # pth omitted when None (FO mode: no Merkle proof)
    assert "pth" not in decoded_proof


def test_vc_fp_decode_invalid_string():
    with pytest.raises(ValueError):
        vc_fp_decode("not-a-valid-fingerprint")