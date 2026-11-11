"""Entry point for the standalone bc_index service.

Modes (via ``INDEXER_MODE`` env var):
- ``both``    (default): indexer thread + Flask web server in one process
- ``web``:    Flask web server only
- ``indexer``: indexing loop only
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from flask import Flask, jsonify
import argparse
from typing import Optional
from indexer.indexer import Indexer
from indexer.rpc import IndexerRPC
from indexer.storage import IndexStorage

def create_app(storage: IndexStorage) -> Flask:
    """Build a read-only Flask app over the index storage."""
    app = Flask(__name__)

    # Lazy RPC holder: only created on the first ``/get_tx_detail`` call.
    _rpc_holder: dict[str, IndexerRPC | None] = {"client": None}

    def _get_rpc() -> IndexerRPC:
        if _rpc_holder["client"] is None:
            _rpc_holder["client"] = IndexerRPC()
        return _rpc_holder["client"]

    @app.get("/get_addr_in_txs/<address>")
    def get_addr_in_txs(address: str):
        txs = storage.get_addr_in_txs(address)
        if txs:
            return jsonify({"transactions": txs}), 200
        return jsonify({"message": "No transactions found"}), 200

    @app.get("/get_addr_out_txs/<address>")
    def get_addr_out_txs(address: str):
        txs = storage.get_addr_out_txs(address)
        if txs:
            return jsonify({"transactions": txs}), 200
        return jsonify({"message": "No transactions found"}), 200

    @app.get("/get_tx_spending/<txid>/<int:vout>")
    def get_tx_spending(txid: str, vout: int):
        spending_txid = storage.get_spending_txid(txid, vout)
        if spending_txid:
            return jsonify({"spending_txid": spending_txid}), 200
        return jsonify({"message": "Output is unspent"}), 200

    @app.get("/get_address_utxos/<address>")
    def get_address_utxos(address: str):
        utxos = storage.get_utxos(address)
        if utxos:
            return jsonify({"UTXOs": utxos}), 200
        return jsonify({"message": "No UTXOs found"}), 200

    @app.get("/get_tx_detail/<txid>")
    def get_tx_detail(txid: str):
        try:
            tx = _get_rpc().getrawtransaction(txid, verbose=True)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        return jsonify({"tx data": tx}), 200

    return app

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the certificate indexer"
    )

    parser.add_argument(
        "--mode",
        choices=["indexer", "web", "both"],
        default=os.getenv("INDEXER_MODE", "both").lower(),
        help="Execution mode",
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=os.getenv("INDEXER_DATA_DIR", "indexer/var"),
        help="Directory used to store indexer data",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=os.getenv("INDEXER_PORT", "5000"),
        help="Web server port",
    )

    args = parser.parse_args()

    # Validate configuration
    if args.mode not in ["indexer", "web", "both"]:
        parser.error("Invalid execution mode")

    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    # Initialize storage
    base_dir = args.data_dir
    progress_file = base_dir / "last_processed_block.txt"
    storage = IndexStorage(base_dir)

    indexer: Indexer | None = None
    indexer_thread: threading.Thread | None = None

    try:
        # Mode 1: Indexer only
        if args.mode == "indexer":
            rpc = IndexerRPC()
            indexer = Indexer(rpc, storage, progress_file)
            indexer.run()
            return

        # Initialize Web application
        app = create_app(storage)

        # Mode 2: Web only
        if args.mode == "web":
            app.run(
                host="127.0.0.1",
                port=args.port,
                debug=False,
                use_reloader=False,
            )
            return

        # Mode 3: Indexer + Web
        if args.mode == "both":
            rpc = IndexerRPC()
            indexer = Indexer(rpc, storage, progress_file)

            indexer_thread = threading.Thread(
                target=indexer.run,
                name="indexer-thread",
                daemon=True,
            )
            indexer_thread.start()

            app.run(
                host="127.0.0.1",
                port=args.port,
                debug=False,
                use_reloader=False,
            )

    finally:
        if indexer is not None:
            if indexer_thread is not None and indexer_thread.is_alive():
                indexer.stop()
                indexer_thread.join(timeout=5)

                if indexer_thread.is_alive():
                    raise RuntimeError(
                        "Indexer thread failed to stop within 5 seconds"
                    )

        storage.close()

    
if __name__ == "__main__":
    main()