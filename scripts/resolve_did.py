"""Resolve a did:btcr identifier to its DID document.

Usage:
    python -m scripts.resolve_did did:btcr:xvhp-qqyq-qqm3-svag
    python -m scripts.resolve_did did:btcr:xvhp-qqyq-qqm3-svag?versionId=1
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.core.config import get_settings
from backend.core.logging import configure_logging
from backend.did.resolver import resolve_did_url
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.infra.indexer.client import IndexerClient
from backend.infra.ipfs.factory import get_ipfs_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve a did:btcr identifier")
    parser.add_argument("did_url", help="Full DID URL, optionally with ?versionTime= or ?versionId=")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    rpc = BitcoinRPCClient(settings.bitcoin)
    indexer = IndexerClient(settings.indexer)
    ipfs = get_ipfs_backend(settings.ipfs)

    try:
        document = resolve_did_url(rpc, indexer, ipfs, args.did_url)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if document is None:
        print("DID document not found", file=sys.stderr)
        sys.exit(2)

    print(json.dumps(document, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()