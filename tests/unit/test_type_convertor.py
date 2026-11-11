"""Unit tests for encoding/type_convertor.py."""

from __future__ import annotations

import pytest

from backend.encoding.type_convertor import (
    binary_to_hex,
    hex_to_binary,
    int_to_hex,
    type_bin_to_str,
    type_hex_to_str,
    type_str_to_binary,
    type_str_to_hex,
)


@pytest.mark.parametrize(
    "type_str, expected_bin",
    [
        ("PS", "000"),
        ("PI", "001"),
        ("PD", "010"),
        ("PT", "011"),
        ("Text", "00000"),
        ("Hash_Value", "00011"),
        ("CBOR_ZLIB", "00000011"),
    ],
)
def test_type_str_to_binary(type_str: str, expected_bin: str):
    assert type_str_to_binary(type_str) == expected_bin


def test_type_str_to_binary_unknown():
    assert type_str_to_binary("UNKNOWN_TYPE") is None


@pytest.mark.parametrize(
    "type_str, expected_hex",
    [
        ("PD", "02"),           # 010 = 0x02
        ("PI", "01"),           # 001 = 0x01
        ("PS", "00"),
        ("CBOR_ZLIB", "03"),
    ],
)
def test_type_str_to_hex(type_str: str, expected_hex: str):
    assert type_str_to_hex(type_str) == expected_hex


def test_type_roundtrip():
    # Only 8-bit encoding methods round-trip correctly through hex.
    for type_str in ["No_Encoding", "SHA256", "CBOR", "CBOR_ZLIB"]:
        binary = type_str_to_binary(type_str)
        assert binary is not None
        assert type_bin_to_str(binary) == type_str

        hex_str = type_str_to_hex(type_str)
        assert hex_str is not None
        assert type_hex_to_str(hex_str) == type_str


def test_type_3bit_roundtrip_binary_only():
    # 3-bit tx_type can round-trip via binary, but not via hex
    # (0x00 collides with "No_Encoding").
    for type_str in ["PS", "PI", "PD", "PT"]:
        binary = type_str_to_binary(type_str)
        assert binary is not None
        assert type_bin_to_str(binary) == type_str


def test_binary_to_hex():
    assert binary_to_hex("01000110") == "46"
    assert binary_to_hex("1") == "01"


def test_hex_to_binary():
    assert hex_to_binary("46") == "01000110"
    assert hex_to_binary("1") == "00000001"
    assert hex_to_binary("zz") is None


def test_int_to_hex():
    assert int_to_hex(0) == "00"
    assert int_to_hex(1) == "01"
    assert int_to_hex(15) == "0f"
    assert int_to_hex(16) == "10"