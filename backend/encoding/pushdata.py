"""Bitcoin script OP_PUSHDATA encoding/decoding."""

from __future__ import annotations

import struct


def encode_push_data(data: bytes) -> bytes:
    """Encode ``data`` as a Bitcoin script pushdata element."""
    length = len(data)
    if length < 0x4C:
        prefix = struct.pack("B", length)
    elif length <= 0xFF:
        prefix = b"\x4c" + struct.pack("B", length)  # OP_PUSHDATA1
    elif length <= 0xFFFF:
        prefix = b"\x4d" + struct.pack("<H", length)  # OP_PUSHDATA2
    else:
        prefix = b"\x4e" + struct.pack("<I", length)  # OP_PUSHDATA4
    return prefix + data


def decode_push_data(pushdatas: bytes) -> list[bytes]:
    """Decode a concatenated sequence of pushdata elements.

    Raises:
        ValueError: if the sequence is truncated or contains an unsupported opcode.
    """
    cursor = 0
    result: list[bytes] = []

    while cursor < len(pushdatas):
        opcode = pushdatas[cursor]
        cursor += 1

        if opcode < 0x4C:
            length = opcode
        elif opcode == 0x4C:
            if cursor >= len(pushdatas):
                raise ValueError("truncated OP_PUSHDATA1 length")
            length = pushdatas[cursor]
            cursor += 1
        elif opcode == 0x4D:
            if cursor + 2 > len(pushdatas):
                raise ValueError("truncated OP_PUSHDATA2 length")
            length = struct.unpack("<H", pushdatas[cursor : cursor + 2])[0]
            cursor += 2
        elif opcode == 0x4E:
            if cursor + 4 > len(pushdatas):
                raise ValueError("truncated OP_PUSHDATA4 length")
            length = struct.unpack("<I", pushdatas[cursor : cursor + 4])[0]
            cursor += 4
        else:
            raise ValueError(f"unsupported opcode {opcode:#x} at byte {cursor - 1}")

        if cursor + length > len(pushdatas):
            raise ValueError(f"pushdata of length {length} exceeds remaining bytes")

        result.append(pushdatas[cursor : cursor + length])
        cursor += length

    return result


def extract_all_pushdatas_from_script(
    script_hex: str, start_index: int, end_index: int
) -> bytes:
    """Extract the raw bytes between two hex-string indices.

    ``start_index`` and ``end_index`` are **character** indices into ``script_hex`` (not byte indices).  
    """
    return bytes.fromhex(script_hex[start_index:end_index])