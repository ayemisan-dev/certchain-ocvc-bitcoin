"""Unit tests for the self-implemented Merkle tree.

Verifies that:
1. ``merkle_root_and_proofs`` produces valid Merkle proofs.
2. ``cal_merkle_root`` correctly reconstructs the root from a leaf + proof.
3. Both are consistent with each other (the root computed by the issuer
   matches the root computed by the verifier).
"""

from __future__ import annotations

import hashlib
import json

import pytest

from backend.services.issuance import merkle_root_and_proofs
from backend.services.onchain_reader import cal_merkle_root
from backend.encoding.cbor_multibase import decode_proof_bytes, encode_proof_bytes


def _leaf_hash(data) -> str:
    return hashlib.sha256(json.dumps(data).encode("utf-8")).hexdigest()


def _proof_to_wire_format(proof: list[dict]) -> list:
    """Convert ``[{"right": hex}]`` (issuer format) to ``[1, hex]`` (verifier format).

    Single-leaf trees produce an empty proof, which has no wire representation.
    """
    if not proof:
        return []
    encoded = encode_proof_bytes({"tid": "00" * 32, "pth": proof})
    decoded = decode_proof_bytes(encoded)
    return decoded.get("pth", [])


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 8, 100])
def test_merkle_proof_reconstructs_root(n: int):
    leaves = [{"cred_id": f"cred/{i}", "grade": "A"} for i in range(1, n + 1)]
    root, proofs = merkle_root_and_proofs(leaves)

    assert len(proofs) == n
    for leaf, proof in zip(leaves, proofs):
        leaf_hash = _leaf_hash(leaf)
        wire_proof = _proof_to_wire_format(proof)
        reconstructed = cal_merkle_root(leaf_hash, wire_proof)
        assert reconstructed == root, f"Merkle proof mismatch for leaf {leaf}"


def test_merkle_single_leaf():
    leaves = [{"data": "only-one"}]
    root, proofs = merkle_root_and_proofs(leaves)
    # With one leaf, proof is empty and root == leaf hash
    assert proofs[0] == []
    assert root == _leaf_hash(leaves[0])


def test_merkle_proofs_are_deterministic():
    leaves = [{"id": i} for i in range(5)]
    root1, proofs1 = merkle_root_and_proofs(leaves)
    root2, proofs2 = merkle_root_and_proofs(leaves)
    assert root1 == root2
    assert proofs1 == proofs2


def test_merkle_wrong_proof_fails():
    leaves = [{"id": i} for i in range(4)]
    root, proofs = merkle_root_and_proofs(leaves)

    # Tamper with the proof of leaf 2
    tampered = list(proofs[2])
    first_entry = dict(tampered[0])
    direction = "right" if "right" in first_entry else "left"
    first_entry[direction] = "00" * 32
    tampered[0] = first_entry

    leaf_hash = _leaf_hash(leaves[2])
    bad_root = cal_merkle_root(leaf_hash, _proof_to_wire_format(tampered))
    assert bad_root != root


def test_merkle_empty_raises():
    with pytest.raises(ValueError):
        merkle_root_and_proofs([])


def test_merkle_odd_number_duplicates_last():
    """Odd leaves: last one is duplicated at each level (standard convention)."""
    leaves = [{"id": 1}, {"id": 2}, {"id": 3}]
    root, proofs = merkle_root_and_proofs(leaves)

    # Manual computation: hash(1), hash(2), hash(3), hash(3) -> pairs
    h1, h2, h3 = (_leaf_hash(l) for l in leaves)
    pair12 = hashlib.sha256(bytes.fromhex(h1) + bytes.fromhex(h2)).hexdigest()
    pair33 = hashlib.sha256(bytes.fromhex(h3) + bytes.fromhex(h3)).hexdigest()
    expected_root = hashlib.sha256(
        bytes.fromhex(pair12) + bytes.fromhex(pair33)
    ).hexdigest()

    assert root == expected_root