"""Integration test for the degree issuance flow (PS -> PI -> PD)."""

from __future__ import annotations

import json

import pytest

from backend.models.configs import PDDegreeConfig, PIConfig, PSConfig
from backend.services.issuance import issue_transaction
from tests.integration.conftest import _mine_block

pytestmark = pytest.mark.integration


@pytest.fixture
def degree_templates(tmp_path):
    """Write temporary VC specs and VI/VD arrays to disk."""
    vc_spec = [
        {"name": "Test Protocol", "version": "1.0"},
        {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": {}, "issuer": [], "dateIssued": {},
            "credentialSubject": {"id": {}, "name": {}}
        },
        {}
    ]
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(vc_spec))

    vi = [[["did:btcr:test_issuer"]], "Test University", "Some Major"]
    vi_path = tmp_path / "vi.json"
    vi_path.write_text(json.dumps(vi))

    return spec_path, vi_path


def test_full_issuance_flow(regtest_rpc, issuer_identity, degree_templates):
    """Test PS -> PI -> PD (create + spend + PD)."""
    spec_path, vi_path = degree_templates
    issuer = issuer_identity

    # --- 1. PS Create ---
    ps_create = PSConfig(
        tx_type="PS", data_type="Tx_Data_ScriptHash", segwit_status="create",
        data_path=str(spec_path), prev_txid=issuer["utxo_txid"], vout=issuer["utxo_vout"],
        send_value=9.98, priv_key=issuer["wif"], pub_key=issuer["pubkey"]
    )
    ps_create_txid = issue_transaction(ps_create, regtest_rpc)
    _mine_block(regtest_rpc)
    
    # Find the P2WSH output
    tx = regtest_rpc.getrawtransaction(ps_create_txid, True)
    p2wsh_vout = next(v for v in tx["vout"] if v["scriptPubKey"]["type"] == "witness_v0_scripthash")

    # --- 2. PS Spend ---
    ps_spend = PSConfig(
        tx_type="PS", data_type="Tx_Data_ScriptHash", segwit_status="spend",
        data_path=str(spec_path), prev_txid=ps_create_txid, vout=p2wsh_vout["n"],
        amount=9.98, send_value=9.97, receive_addr=issuer["address"],
        wif_privkey=issuer["wif"], pub_key=issuer["pubkey"]
    )
    ps_spend_txid = issue_transaction(ps_spend, regtest_rpc)
    _mine_block(regtest_rpc)

    # --- 3. PI Create ---
    pi_create = PIConfig(
        tx_type="PI", data_type="Tx_Data_ScriptHash", segwit_status="create",
        data_path=str(vi_path), prev_txid=ps_spend_txid, vout=0,
        send_value=9.96, priv_key=issuer["wif"], pub_key=issuer["pubkey"]
    )
    pi_create_txid = issue_transaction(pi_create, regtest_rpc)
    _mine_block(regtest_rpc)

    tx = regtest_rpc.getrawtransaction(pi_create_txid, True)
    p2wsh_vout = next(v for v in tx["vout"] if v["scriptPubKey"]["type"] == "witness_v0_scripthash")

    # --- 4. PI Spend ---
    pi_spend = PIConfig(
        tx_type="PI", data_type="Text", encoding_method="No_Encoding",
        extra_data_type="Tx_Data_ScriptHash", extra_encoding_method="CBOR_ZLIB",
        segwit_status="spend", data_path=str(vi_path), ps_txid=ps_spend_txid,
        prev_txid=pi_create_txid, vout=p2wsh_vout["n"],
        amount=9.96, send_value=9.95, receive_addr=issuer["address"],
        wif_privkey=issuer["wif"], pub_key=issuer["pubkey"]
    )
    pi_spend_txid = issue_transaction(pi_spend, regtest_rpc)
    _mine_block(regtest_rpc)

    # --- 5. PD (Batch of 2) ---
    pd_config = PDDegreeConfig(
        tx_type="PD", data_type="Hash_Value", encoding_method="SHA256",
        extra_data_type="Text", extra_encoding_method="No_Encoding",
        sequence=1, prev_txid=pi_spend_txid, vout=0,
        send_value=9.94, priv_key=issuer["wif"], receive_addr=issuer["address"],
        file_name="test_batch", full_vc_list_path="", vc_temp_path="",
        vc_fp_tem_path="", vc_fp_path="", qrcode_path="", vc_type="BSc"
    )
    
    # Mock merkle root for 2 leaves
    import hashlib
    h1 = hashlib.sha256(b'{"id":"1"}').hexdigest()
    h2 = hashlib.sha256(b'{"id":"2"}').hexdigest()
    root = hashlib.sha256(bytes.fromhex(h1) + bytes.fromhex(h2)).hexdigest()

    pd_txid = issue_transaction(pd_config, regtest_rpc, pd_data_hex=root)
    _mine_block(regtest_rpc)

    # --- Assertions ---
    pd_tx = regtest_rpc.getrawtransaction(pd_txid, True)
    assert "OP_RETURN" in pd_tx["vout"][1]["scriptPubKey"]["asm"]
    assert pd_tx["vout"][1]["scriptPubKey"]["type"] == "nulldata"