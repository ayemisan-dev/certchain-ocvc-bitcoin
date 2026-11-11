"""Unit tests for encoding/pushdata.py."""

from __future__ import annotations

import pytest

from backend.encoding.pushdata import (
    decode_push_data,
    encode_push_data,
    extract_all_pushdatas_from_script,
)


@pytest.mark.parametrize(
    "data_len, expected_prefix",
    [
        (0, b"\x00"),
        (1, b"\x01"),
        (75, b"\x4b"),                 # 0x4b = 75 < 0x4c
        (76, b"\x4c\x4c"),             # OP_PUSHDATA1 + length
        (255, b"\x4c\xff"),
        (256, b"\x4d\x00\x01"),        # OP_PUSHDATA2 little-endian
        (65535, b"\x4d\xff\xff"),
        (65536, b"\x4e\x00\x00\x01\x00"),  # OP_PUSHDATA4
    ],
)
def test_encode_push_data_prefix(data_len: int, expected_prefix: bytes):
    encoded = encode_push_data(b"\x00" * data_len)
    assert encoded.startswith(expected_prefix)


def test_encode_decode_roundtrip_simple():
    data = b"hello"
    encoded = encode_push_data(data)
    assert decode_push_data(encoded) == [data]


def test_encode_decode_roundtrip_multi():
    chunks = [b"a", b"b" * 100, b"c" * 300]
    concatenated = b"".join(encode_push_data(c) for c in chunks)
    assert decode_push_data(concatenated) == chunks


def test_decode_empty():
    assert decode_push_data(b"") == []


def test_decode_truncated_pushdata1():
    with pytest.raises(ValueError, match="truncated"):
        decode_push_data(b"\x4c")


def test_decode_pushdata_length_overflow():
    # Says length is 10, but only 3 bytes follow
    with pytest.raises(ValueError, match="exceeds remaining"):
        decode_push_data(b"\x0a\x01\x02\x03")


def test_extract_all_pushdatas_from_script():
    # "04deadbeef" -> 1-byte length (4), then 4 bytes of data
    script_hex = "00" + "04deadbeef" + "00"
    raw = extract_all_pushdatas_from_script(script_hex, 2, 12)
    assert raw == b"\x04\xde\xad\xbe\xef"