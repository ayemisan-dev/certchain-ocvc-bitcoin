"""Golomb-encoded bitstring for revocation lists."""

from __future__ import annotations

import math

from bitarray import bitarray
from bitarray.util import ba2int, int2ba


def encoded_bitstr_m(bits_len: int, revoked_list: list[int], m: int) -> tuple[int, int]:
    """Encode a revocation list as a Golomb-compressed bitstring.

    ``revoked_list`` uses **1-based** indices (credential #1 is index 0).
    Returns ``(encoded_int, encoded_bit_length)``.
    """
    bits = bitarray("0") * bits_len
    for index in revoked_list:
        bits[index - 1] = 1
    encoded_bits = _golomb_encode_bitarray(bits, m)
    return ba2int(encoded_bits), len(encoded_bits)


def encoded_bitstr_reason(reason_list: list[int], bit_per_cred: int) -> int:
    """Encode revocation reasons as a fixed-width integer bitstring."""
    binary_str = "".join(format(n, f"0{bit_per_cred}b") for n in reason_list)
    return int(binary_str, 2) if binary_str else 0


def is_revoke(
    pos: int, m: int, revoke_int: int, encoded_bits_len: int
) -> tuple[list[int], bool]:
    """Check whether position ``pos`` (1-based) is revoked.

    Returns ``(revocation_list, revoked)`` where ``revocation_list`` is the
    full decoded list of revoked positions (useful for reason lookup).
    """
    ba = int2ba(revoke_int, length=encoded_bits_len)
    return _bit_at_index(ba, m, pos)


def decoded_bitstr_reason(
    revoke_index: int,
    revoke_list: list[int],
    reason_int: int,
    bit_per_cred: int,
    reason_desc: list[str],
) -> str | None:
    """Return the reason string for a revoked credential, or ``None``."""
    if revoke_index not in revoke_list:
        return None
    index = revoke_list.index(revoke_index)
    bitstr = format(reason_int, "b")
    # Pad to a multiple of ``bit_per_cred``.
    if len(bitstr) % bit_per_cred != 0:
        bitstr = "0" * (bit_per_cred - len(bitstr) % bit_per_cred) + bitstr
    start = index * bit_per_cred
    end = start + bit_per_cred
    try:
        reason_bits = bitstr[start:end]
        reason_index = int(reason_bits, 2)
        return reason_desc[reason_index - 1]
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Golomb internals
# ---------------------------------------------------------------------------

def _unary_encode(q: int) -> bitarray:
    return bitarray("0" * q + "1")


def _truncated_binary_encode(r: int, m: int) -> bitarray:
    b = math.ceil(math.log2(m))
    cutoff = (1 << b) - m
    if r < cutoff:
        return bitarray(f"{r:0{b - 1}b}")
    r += cutoff
    return bitarray(f"{r:0{b}b}")


def _golomb_encode_number(n: int, m: int) -> bitarray:
    q, r = divmod(n, m)
    return _unary_encode(q) + _truncated_binary_encode(r, m)


def _golomb_encode_bitarray(bits: bitarray, m: int) -> bitarray:
    result = bitarray()
    zero_run = 0
    for bit in bits:
        if bit == 0:
            zero_run += 1
        else:
            result.extend(_golomb_encode_number(zero_run, m))
            zero_run = 0
    # IMPORTANT: encode trailing zeros so that ``is_revoke`` can decode
    # positions after the last revoked index. The original code commented
    # this out, which was a bug.
    if zero_run > 0:
        result.extend(_golomb_encode_number(zero_run, m))
    return result


def _golomb_read(bitstream: bitarray, m: int, pos: int) -> tuple[int, int]:
    """Decode one Golomb code starting at ``pos``. Returns ``(value, next_pos)``."""
    q = 0
    while pos < len(bitstream) and bitstream[pos] == 0:
        q += 1
        pos += 1
    pos += 1  # skip the terminating 1

    b = m.bit_length() - 1
    cutoff = (1 << (b + 1)) - m
    rbits = bitstream[pos : pos + b].to01()
    r = int(rbits, 2) if rbits else 0
    pos += b
    if r >= cutoff:
        r = (r << 1) | (bitstream[pos] if pos < len(bitstream) else 0)
        r -= cutoff
        pos += 1

    return q * m + r, pos


def _bit_at_index(e: bitarray, m: int, n: int) -> tuple[list[int], bool]:
    """Decode the full revocation list and check whether ``n`` is revoked."""
    pos = 0
    bit_index = 1
    revocation_list: list[int] = []
    revoked = False

    while pos < len(e):
        run, pos = _golomb_read(e, m, pos)
        revocation_list.append(bit_index + run)
        if n < bit_index + run:
            return revocation_list, revoked
        if n == bit_index + run:
            revoked = True
            return revocation_list, revoked
        bit_index += run + 1

    return revocation_list, revoked