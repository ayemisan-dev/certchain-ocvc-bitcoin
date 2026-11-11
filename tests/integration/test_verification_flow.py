"""Integration test for the verification flow."""

from __future__ import annotations

import pytest

from backend.services.verification import verify_credential

pytestmark = pytest.mark.integration

def test_verify_valid_credential(
    example_fp_text, regtest_rpc, indexer_client, ipfs_backend
):
    result = verify_credential(
        example_fp_text, regtest_rpc, indexer_client, ipfs_backend
    )
    if result.status.value == "invalid":
        pytest.fail(f"Expected valid/revoked, got invalid: {result.reason}")
    assert result.status.value in ("valid", "revoked")


def test_verify_tampered_credential(
    example_fp_text, regtest_rpc, indexer_client, ipfs_backend
):
    # Flip a character in the payload
    tampered = example_fp_text[:-10] + "aaaaaaaaaa"
    result = verify_credential(tampered, regtest_rpc, indexer_client, ipfs_backend)
    assert result.status.value == "invalid"


def test_verify_malformed_credential(regtest_rpc, indexer_client, ipfs_backend):
    result = verify_credential("not-a-valid-base64-string", regtest_rpc, indexer_client, ipfs_backend)
    assert result.status.value == "invalid"
    assert result.reason is not None
    assert "malformed fingerprint" in result.reason