"""Create a did:btcr identifier by anchoring a DID document on Bitcoin.

Usage:
    python -m scripts.create_did \
        --did-doc backend/data/did/issuer_ddo.json \
        --prev-txid <64-hex> \
        --vout 0 \
        --priv-key <WIF> \
        --receive-addr <legacy-address> \
        --send-value 9.99
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.core.config import get_settings
from backend.core.logging import configure_logging, get_logger
from backend.did.txidbech32 import txid_to_bech32
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.infra.ipfs.factory import get_ipfs_backend

logger = get_logger(__name__)


def _build_op_return(cid: str) -> str:
    """Build the OP_RETURN payload ``ipfs://<CID>`` (hex)."""
    payload = f"ipfs://{cid}".encode("utf-8")
    return payload.hex()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a did:btcr identifier")
    parser.add_argument("--did-doc", required=True, help="Path to DID document JSON")
    parser.add_argument("--prev-txid", help="Funding transaction ID (64 hex) — not needed if --txid is provided")
    parser.add_argument("--vout", type=int, default=0, help="Funding output index")
    parser.add_argument("--priv-key", help="WIF private key")
    parser.add_argument("--receive-addr", help="Legacy address to receive change")
    parser.add_argument("--send-value", type=float, help="BTC amount to send back")
    parser.add_argument("--txid", help="Already-confirmed anchor transaction ID (skips broadcasting)")
    parser.add_argument("--wait-timeout", type=int, default=60, help="Seconds to wait for confirmation")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    rpc = BitcoinRPCClient(settings.bitcoin)

    # --- Mode 1: use an already-confirmed anchor transaction ---
    if args.txid:
        anchor_txid = args.txid
        logger.info("using existing anchor transaction: %s", anchor_txid)
    else:
        # --- Mode 2: broadcast a new anchor transaction ---
        if not all([args.prev_txid, args.priv_key, args.receive_addr, args.send_value]):
            print(
                "error: --prev-txid, --priv-key, --receive-addr, --send-value are required "
                "when --txid is not provided",
                file=sys.stderr,
            )
            sys.exit(1)

        ipfs = get_ipfs_backend(settings.ipfs)
        did_doc_path = Path(args.did_doc)
        if not did_doc_path.exists():
            print(f"error: DID document not found: {did_doc_path}", file=sys.stderr)
            sys.exit(1)

        cid = ipfs.add_file(str(did_doc_path))
        logger.info("DID document uploaded to IPFS: %s", cid)

        op_return_hex = _build_op_return(cid)
        if len(op_return_hex) > 160:
            print(
                f"error: OP_RETURN exceeds 80 bytes ({len(op_return_hex) // 2} bytes)",
                file=sys.stderr,
            )
            sys.exit(1)

        inputs = [{"txid": args.prev_txid, "vout": args.vout}]
        outputs = {args.receive_addr: args.send_value, "data": op_return_hex}
        unsigned_hex = rpc.createrawtransaction(inputs, outputs)
        signed = rpc.signrawtransactionwithkey(unsigned_hex, [args.priv_key])
        if not signed.get("complete"):
            print(f"error: signing failed: {signed}", file=sys.stderr)
            sys.exit(1)
        anchor_txid = rpc.sendrawtransaction(signed["hex"])
        logger.info("DID anchor transaction broadcast: %s", anchor_txid)

    # --- Wait for confirmation (TxRef requires a block) ---
    logger.info("waiting for 1 confirmation (timeout %ds)...", args.wait_timeout)
    confirmed = _wait_for_confirmation(rpc, anchor_txid, args.wait_timeout)
    if not confirmed:
        print(
            f"error: transaction {anchor_txid} not confirmed within {args.wait_timeout}s.\n"
            f"After mining a block, re-run:\n"
            f"  python -m scripts.create_did --did-doc {args.did_doc} --txid {anchor_txid}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Encode as did:btcr ---
    bech32 = txid_to_bech32(anchor_txid, rpc, settings.bitcoin.network)
    prefix = "tx1-" if settings.bitcoin.network.value == "mainnet" else "txtest1-"
    did = "did:btcr:" + bech32.replace(prefix, "")

    print(f"txid: {anchor_txid}")
    print(f"did:  {did}")


def _wait_for_confirmation(
    rpc: BitcoinRPCClient, txid: str, timeout_seconds: int
) -> bool:
    """Poll until the transaction has >= 1 confirmation, or timeout."""
    import time

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if rpc.network.value == "regtest":
                tx = rpc.gettransaction(txid)
            else:
                tx = rpc.getrawtransaction(txid, True)
            if tx.get("confirmations", 0) >= 1:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


if __name__ == "__main__":
    main()