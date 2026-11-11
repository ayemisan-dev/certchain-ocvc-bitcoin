"""Unit tests for encoding/bitstr.py (Golomb-encoded revocation lists)."""

from __future__ import annotations

import pytest

from backend.encoding.bitstr import (
    decoded_bitstr_reason,
    encoded_bitstr_m,
    encoded_bitstr_reason,
    is_revoke,
)


@pytest.mark.parametrize(
    "bits_len, revoked_list, m",
    [
        (1000, [4, 23], 32),
        (1000, [1], 32),
        (1000, [1000], 32),           # last index
        (1000, [1, 1000], 32),        # both ends
        (100, [50], 16),
        (100, [10, 20, 30], 16),
    ],
)
def test_encode_decode_revoked_set(bits_len, revoked_list, m):
    """The encoded stream must decode to exactly the original revoked set."""
    revoke_int, encoded_len = encoded_bitstr_m(bits_len, revoked_list, m)

    # Check every revoked position returns True.
    for pos in revoked_list:
        _, revoked = is_revoke(pos, m, revoke_int, encoded_len)
        assert revoked, f"position {pos} should be revoked"

    # Check a few non-revoked positions return False.
    for pos in range(1, bits_len + 1):
        if pos in revoked_list:
            continue
        _, revoked = is_revoke(pos, m, revoke_int, encoded_len)
        if revoked:
            # is_revoke returns the full list first; make sure pos is not in it.
            raise AssertionError(f"position {pos} should NOT be revoked but is")


def test_trailing_zeros_are_encoded():
    """The original implementation had a bug where trailing zeros were dropped.

    This test verifies the fix: a credential at the very end of the bitstring
    must still be decodable.
    """
    bits_len = 1000
    revoked_list = [1000]  # last position
    m = 32
    revoke_int, encoded_len = encoded_bitstr_m(bits_len, revoked_list, m)

    _, revoked = is_revoke(1000, m, revoke_int, encoded_len)
    assert revoked, "trailing position must be revoked"


def test_reason_encoding():
    # reasons: [1, 2] with 2 bits per credential -> binary 01 10 = 6
    reason_int = encoded_bitstr_reason([1, 2], 2)
    assert reason_int == 6

    # reasons: [1] with 2 bits per credential -> binary 01 = 1
    assert encoded_bitstr_reason([1], 2) == 1

    # reasons: [3] with 2 bits per credential -> binary 11 = 3
    assert encoded_bitstr_reason([3], 2) == 3


def test_reason_decoding():
    reason_desc = ["academic_misconduct", "administrative_error", "fraud", "Others"]
    revoke_list = [4, 23]
    bit_per_cred = 2

    # reasons: [1, 2] -> encoded as 6 (binary 01 10)
    reason_int = encoded_bitstr_reason([1, 2], bit_per_cred)

    assert decoded_bitstr_reason(4, revoke_list, reason_int, bit_per_cred, reason_desc) == "academic_misconduct"
    assert decoded_bitstr_reason(23, revoke_list, reason_int, bit_per_cred, reason_desc) == "administrative_error"


def test_reason_decoding_position_not_in_list():
    """If the position isn't in the revoked list, return None."""
    reason_desc = ["a", "b", "c", "d"]
    result = decoded_bitstr_reason(
        99, [4, 23], 1, 2, reason_desc
    )
    assert result is None


def test_empty_revoked_list():
    """An empty revocation list must not crash (produces a valid encoded stream)."""
    revoke_int, encoded_len = encoded_bitstr_m(100, [], 16)
    # Nothing should be revoked.
    _, revoked = is_revoke(1, 16, revoke_int, encoded_len)
    assert not revoked


def test_all_revoked():
    """All positions revoked: the encoded stream should decode every position as revoked."""
    bits_len = 10
    revoked_list = list(range(1, bits_len + 1))
    revoke_int, encoded_len = encoded_bitstr_m(bits_len, revoked_list, 4)

    for pos in revoked_list:
        _, revoked = is_revoke(pos, 4, revoke_int, encoded_len)
        assert revoked