"""OCVC TYPE field conversion: string <-> binary <-> hex."""

from __future__ import annotations

# Mapping from string to binary (3 bits for tx_type, 5 bits for data_type,
# 8 bits for encoding_method).
_STR_TO_BIN: dict[str, str] = {
    # transaction types (3 bits)
    "PS": "000",
    "PI": "001",
    "PD": "010",
    "PT": "011",
    # data types (5 bits)
    "Text": "00000",
    "Hash_Link_URL": "00001",
    "IPFS_CID": "00010",
    "Hash_Value": "00011",
    "Tx_Data_Witness": "00100",
    "Tx_Data_ScriptHash": "00101",
    "Encoded_Data": "00110",
    # encoding methods (8 bits)
    "No_Encoding": "00000000",
    "SHA256": "00000001",
    "CBOR": "00000010",
    "CBOR_ZLIB": "00000011",
}

_BIN_TO_STR: dict[str, str] = {v: k for k, v in _STR_TO_BIN.items()}


def type_str_to_binary(type_str: str) -> str | None:
    """Return the binary string for a type name, or None if unknown."""
    return _STR_TO_BIN.get(type_str)


def type_bin_to_str(type_bin: str) -> str | None:
    """Return the type name for a binary string, or None if unknown."""
    return _BIN_TO_STR.get(type_bin)


def type_str_to_hex(type_str: str) -> str | None:
    """Convenience: string -> binary -> hex."""
    binary = type_str_to_binary(type_str)
    if binary is None:
        return None
    return binary_to_hex(binary)


def type_hex_to_str(type_hex: str) -> str | None:
    """Convenience: hex -> binary -> string."""
    binary = hex_to_binary(type_hex)
    if binary is None:
        return None
    return type_bin_to_str(binary)


def binary_to_hex(binary_string: str) -> str:
    """Convert a binary string (e.g. '101') to a 2-char hex string."""
    decimal = int(binary_string, 2)
    return int_to_hex(decimal)


def hex_to_binary(hex_string: str) -> str | None:
    """Convert a hex string to an 8-bit binary string, or None on error."""
    try:
        integer = int(hex_string, 16)
    except ValueError:
        return None
    return format(integer, "08b")


def int_to_hex(number: int) -> str:
    """Convert an integer to a 2-character (or longer) hex string."""
    hex_num = format(number, "x")
    if len(hex_num) % 2 != 0:
        hex_num = "0" + hex_num
    return hex_num