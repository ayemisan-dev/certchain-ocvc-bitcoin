"""BTCR DID resolution (version history via transaction chain)."""

from __future__ import annotations

from backend.core.utils import iso_to_timestamp
from backend.did.txidbech32 import bech32_to_txid
from backend.infra.ipfs.base import IPFSBackend
from backend.infra.indexer.client import IndexerClient


def _is_did_anchor(tx_data: dict) -> tuple[bool, str | None]:
    """Check whether a transaction is a DID anchor (OP_RETURN = ipfs://CID).

    Returns ``(is_anchor, cid)``.
    """
    for vout in tx_data.get("vout", []):
        spk = vout.get("scriptPubKey", {})
        if spk.get("type") != "nulldata":
            continue
        asm = spk.get("asm", "")
        data_hex = asm.split("OP_RETURN")[-1].strip()
        if not data_hex:
            continue
        try:
            data_str = bytes.fromhex(data_hex).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if data_str.startswith("ipfs://"):
            return True, data_str[len("ipfs://"):]
    return False, None


def _get_did_document_list(
    rpc_client,
    indexer_client: IndexerClient,
    ipfs: IPFSBackend,
    did: str,
    txid: str,
    public_key_list: list | None = None,
    count: int = 0,
) -> list[dict]:
    """Recursively follow the transaction chain to collect all DID document versions."""
    if public_key_list is None:
        public_key_list = []

    # Fetch the transaction
    if rpc_client.network.value == "regtest":
        tx = rpc_client.gettransaction(txid)
        tx_data = rpc_client.decoderawtransaction(tx["hex"])
    else:
        tx_data = rpc_client.getrawtransaction(txid, True)

    # Verify this transaction is a DID anchor.
    # If not (e.g., a PS/PI/PD transaction that spent the DID UTXO), stop
    # traversal instead of crashing.
    is_anchor, cid = _is_did_anchor(tx_data)
    if not is_anchor or cid is None:
        return []

    # Fetch DID document from IPFS
    did_doc = ipfs.get_file(cid)
    did_document = did_doc["didDocument"]
    did_document.setdefault("id", did)

    # Extract pubkey from input
    tx_in = tx_data["vin"][0]
    if "txinwitness" in tx_in and len(tx_in["txinwitness"]) > 1:
        pub_key = tx_in["txinwitness"][1]
    else:
        pub_key = tx_in["scriptSig"]["asm"].split("[ALL]")[-1].lstrip()

    pub_key_obj = {
        "id": f"{did}#key-{count}",
        "type": "EcdsaSecp256k1VerificationKey2019",
        "controller": did,
        "publicKeyHex": pub_key,
    }
    public_key_list.append(pub_key_obj)

    satoshi_obj = dict(pub_key_obj)
    satoshi_obj["id"] = f"{did}#satoshi"

    existing_vm = did_document.get("verificationMethod", [])
    for method in existing_vm:
        if not method["id"].startswith(did):
            method["id"] = did + method["id"]
        method.setdefault("controller", did)

    did_document["verificationMethod"] = [pub_key_obj, satoshi_obj] + existing_vm
    did_doc["didDocument"] = did_document
    did_document_list = [did_doc]

    # Recurse only if the spending transaction is also a DID anchor.
    spending = indexer_client.get_tx_spending(txid, 0)
    if spending is not None:
        next_versions = _get_did_document_list(
            rpc_client,
            indexer_client,
            ipfs,
            did,
            spending,
            public_key_list,
            count + 1,
        )
        did_document_list.extend(next_versions)

    return did_document_list


def resolve_did_url(
    rpc_client,
    indexer_client: IndexerClient,
    ipfs: IPFSBackend,
    did_url: str,
) -> dict | None:
    """Resolve a did:btcr URL to a DID document.

    Supported query parameters:
    - ``?versionTime=<unix timestamp>``: latest version before that time.
    - ``?versionId=<int>``: exact version.
    """
    did, key, value = did_url, None, None
    if "?" in did_url:
        did, query = did_url.split("?", 1)
        if "=" in query:
            key, value = query.split("=", 1)

    if not did.startswith("did:btcr:"):
        raise ValueError(f"unsupported DID method: {did}")

    bech32 = did.replace("did:btcr:", "txtest1-")
    txid = bech32_to_txid(bech32, rpc_client)

    versions = _get_did_document_list(rpc_client, indexer_client, ipfs, did, txid)
    if not versions:
        return None

    for doc in reversed(versions):
        metadata = doc["didDocumentMetadata"]

        if key == "versionTime" and value is not None:
            updated_ts = iso_to_timestamp(metadata["updated"])
            try:
                requested = int(value)
            except ValueError as exc:
                raise ValueError(f"invalid versionTime value: {value!r}") from exc
            if requested >= updated_ts:
                return doc

        elif key == "versionId" and value is not None:
            if str(value) == str(metadata["versionId"]):
                return doc

        else:
            return versions[-1]

    return versions[-1]