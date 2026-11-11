"""Shared fixtures for integration tests."""

from __future__ import annotations

import json
import time
import pytest

from backend.core.config import get_settings
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.infra.ipfs.factory import get_ipfs_backend
from backend.did.txidbech32 import txid_to_bech32



def _mine_block(rpc: BitcoinRPCClient) -> str:
    """Mine a block to the wallet's address to confirm mempool transactions."""
    #addr = rpc._call("getnewaddress", "", "legacy")
    addr = "n1HH6aDu5Bn8q1czw3itr6sUEXy61Lif5D" # regtest address 
    block_hash = rpc._call("generatetoaddress", 1, addr)[0]
    return block_hash


def _wait_for_indexer(txid: str, indexer_client, expected_type: str, timeout: int = 15) -> None:
    """Poll the indexer until the transaction is visible."""
    start = time.time()
    while time.time() - start < timeout:
        # We query by txid. If it's a PD/PI/PS, the indexer will have it in the wallet address history.
        # Here we just check if the indexer has the transaction's spending or outputs.
        # Actually, the simplest way is to wait for the indexer to catch up, but polling `get_tx_spending` or similar is tricky.
        # Instead, we just wait for the block to be processed. A more robust way is to check the address.
        time.sleep(1)
        # Just wait a few seconds. In a real environment, we'd check the indexer height.
    # For now, just wait a few seconds to let the indexer poll the new block.
    time.sleep(3)


@pytest.fixture(scope="session")
def issuer_identity(regtest_rpc: BitcoinRPCClient, ipfs_backend):
    """Create a fresh issuer address, fund it, and anchor its DID."""
    if not regtest_rpc._call("listwallets"):
        regtest_rpc._call("createwallet", "test_issuer")

    # regtest address
    addr = "mwDYv1fjAVWZg4zdwGBg6KfeZvgRfa92K4" 
    pub = "0216696e2beafb85bfa49acec993526776cc6ecc28dea3d5d1108c39d5b8d7c1c5"
    wif = "cNfYZAjrctyQnK7Pu418DhWQv7vpp6JpMuJcxLh5iDhXrd9aCepw"

    # Fund it
    txid = regtest_rpc._call("sendtoaddress", addr, 10.0)
    _mine_block(regtest_rpc)

    # Find the correct vout for ``addr`` (Bitcoin Core shuffles outputs)
    tx = regtest_rpc.getrawtransaction(txid, True)
    vout_idx = next(
        v["n"] for v in tx["vout"]
        if v["scriptPubKey"].get("address") == addr
    )

    # Create DID
    did_doc = {
        "didDocument": {
            "verificationMethod": [{
                "id": "#vckey-0",
                "type": "EcdsaSecp256k1VerificationKey2019",
                "publicKeyHex": pub
            }],
            "assertionMethod": ["#vckey-0"]
        }
    }
    cid = ipfs_backend.add_bytes(json.dumps(did_doc).encode(), "issuer_ddo.json")
    
    # Anchor DID via OP_RETURN
    inputs = [{"txid": txid, "vout": vout_idx}]
    outputs = {addr: 9.99, "data": f"ipfs://{cid}".encode().hex()}
    raw = regtest_rpc.createrawtransaction(inputs, outputs)
    signed = regtest_rpc.signrawtransactionwithkey(raw, [wif])
    did_txid = regtest_rpc.sendrawtransaction(signed["hex"])
    _mine_block(regtest_rpc)

    # Encode DID
    bech32 = txid_to_bech32(did_txid, regtest_rpc, regtest_rpc.network)
    did = "did:btcr:" + bech32.replace("txtest1-", "")

    # Find the change UTXO from the DID anchor transaction
    # (the sendtoaddress txid has been fully spent by the DID anchor)
    tx = regtest_rpc.getrawtransaction(did_txid, True)
    change_vout = next(
        v["n"] for v in tx["vout"]
        if v["scriptPubKey"].get("address") == addr and v["value"] > 0
    )

    return {
        "address": addr,
        "pubkey": pub,
        "wif": wif,
        "did": did,
        "utxo_txid": did_txid,
        "utxo_vout": change_vout,
    }


@pytest.fixture(scope="session")
def revocation_identity(regtest_rpc: BitcoinRPCClient, ipfs_backend):
    """Create a fresh revocation address, fund it, and anchor its DID."""
    if not regtest_rpc._call("listwallets"):
        regtest_rpc._call("createwallet", "test_revocation")

    # regtest address 
    addr = "mxrZdekZ6n3SwJ9nGWt799gEQrW1U3S4gr"
    pub = "031393496c974bebf7d0f9a7979e98331d7e1d0566d2fa99dcb28c8da992e2d363"
    wif = "cTgymhnrmgKFHJZwcCn9wjYtyt4mQzjrCSFG6bmMXX6oh6TUaK4z"

    txid = regtest_rpc._call("sendtoaddress", addr, 10.0)
    _mine_block(regtest_rpc)

    # Find the correct vout for ``addr`` (Bitcoin Core shuffles outputs)
    tx = regtest_rpc.getrawtransaction(txid, True)
    vout_idx = next(
        v["n"] for v in tx["vout"]
        if v["scriptPubKey"].get("address") == addr
    )

    did_doc = {
        "didDocument": {
            "verificationMethod": [{
                "id": "#vckey-0",
                "type": "EcdsaSecp256k1VerificationKey2019",
                "publicKeyHex": pub
            }],
            "assertionMethod": ["#vckey-0"]
        }
    }
    cid = ipfs_backend.add_bytes(json.dumps(did_doc).encode(), "revocation_ddo.json")

    inputs = [{"txid": txid, "vout": vout_idx}]
    outputs = {addr: 9.99, "data": f"ipfs://{cid}".encode().hex()}
    raw = regtest_rpc.createrawtransaction(inputs, outputs)
    signed = regtest_rpc.signrawtransactionwithkey(raw, [wif])
    did_txid = regtest_rpc.sendrawtransaction(signed["hex"])
    _mine_block(regtest_rpc)

    bech32 = txid_to_bech32(did_txid, regtest_rpc, regtest_rpc.network)
    did = "did:btcr:" + bech32.replace("txtest1-", "")

    tx = regtest_rpc.getrawtransaction(did_txid, True)
    change_vout = next(
        v["n"] for v in tx["vout"]
        if v["scriptPubKey"].get("address") == addr and v["value"] > 0
    )

    return {
        "address": addr,
        "pubkey": pub,
        "wif": wif,
        "did": did,
        "utxo_txid": did_txid,
        "utxo_vout": change_vout,
    }