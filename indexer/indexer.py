"""Background indexing loop for the bc_index service.

Indexes four views of the chain:
- addrindex_in  (addresses whose outputs are spent by some tx)
- addrindex_out (addresses that receive outputs)
- txindex       (outpoint -> spending txid)
- utxoindex     (address -> unspent outpoints)
"""

from __future__ import annotations

import signal
import threading
from pathlib import Path

from indexer.rpc import IndexerRPC, IndexerRPCError
from indexer.storage import IndexStorage


class Indexer:
    """Incremental Bitcoin indexer."""

    def __init__(
        self,
        rpc: IndexerRPC,
        storage: IndexStorage,
        progress_file: str | Path,
        poll_interval_seconds: int = 10,
    ) -> None:
        self._rpc = rpc
        self._storage = storage
        self._progress_file = progress_file
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._tx_count = 0
        self._stop_event = threading.Event()

    # -- public API ------------------------------------------------------

    def run(self) -> None:
        """Run the indexing loop. Blocks until ``stop()`` is called."""
        self._running = True

        # signal handlers can only be registered from the main thread
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, self._handle_signal)
                signal.signal(signal.SIGTERM, self._handle_signal)
            except ValueError:
                pass

        while not self._stop_event.is_set():
            try:
                self.update_indexes()
            except IndexerRPCError as exc:
                print(f"[indexer] RPC error: {exc}")
                self._stop_event.wait(self._poll_interval)
            except Exception as exc:
                print(f"[indexer] unexpected error: {exc}")
                self._stop_event.wait(self._poll_interval)

    def stop(self) -> None:
        self._stop_event.set()

    # -- internal --------------------------------------------------------

    def _handle_signal(self, _signum, _frame) -> None:
        print("[indexer] shutdown signal received")
        self.stop()

    def update_indexes(self) -> None:
        """Process all blocks between the last known height and the chain tip."""
        current_height = self._rpc.getblockcount()
        last_height, self._tx_count = self._storage.read_progress(self._progress_file)

        if last_height >= current_height:
            self._stop_event.wait(self._poll_interval)
            return

        for height in range(last_height + 1, current_height + 1):
            if self._stop_event.is_set():
                break
            block_hash = self._rpc.getblockhash(height)
            self._index_block(height, block_hash)
            self._storage.write_progress(self._progress_file, height, self._tx_count)

    def _index_block(self, height: int, block_hash: str) -> None:
        block = self._rpc.getblock(block_hash, verbosity=2)
        transactions = block.get("tx", [])

        # Cache parent transactions so we don't fetch the same one repeatedly.
        parent_cache: dict[str, dict] = {}

        for tx in transactions:
            self._tx_count += 1
            self._index_inputs(tx, parent_cache)
            self._index_outputs(tx)

        print(f"[indexer] processed block {height} ({len(transactions)} txs)")

    def _index_inputs(self, tx: dict, parent_cache: dict[str, dict]) -> None:
        for vin in tx.get("vin", []):
            parent_txid = vin.get("txid")
            parent_vout = vin.get("vout")
            if parent_txid is None or parent_vout is None:
                continue

            self._storage.set_spending_txid(parent_txid, parent_vout, tx["txid"])

            if parent_txid not in parent_cache:
                try:
                    parent_cache[parent_txid] = self._rpc.getrawtransaction(
                        parent_txid, verbose=True
                    )
                except IndexerRPCError:
                    continue
            parent_tx = parent_cache[parent_txid]

            vout = parent_tx["vout"][parent_vout]
            addresses = _extract_addresses(vout["scriptPubKey"])

            utxo_key = f"{parent_txid}:{parent_vout}"
            for address in addresses:
                self._storage.add_addr_in_tx(address, tx["txid"])
                self._storage.remove_utxo(address, utxo_key)

    def _index_outputs(self, tx: dict) -> None:
        for vout_index, vout in enumerate(tx["vout"]):
            if vout["scriptPubKey"].get("type") == "nulldata":
                continue
            addresses = _extract_addresses(vout["scriptPubKey"])
            utxo_key = f"{tx['txid']}:{vout_index}"
            for address in addresses:
                self._storage.add_addr_out_tx(address, tx["txid"])
                self._storage.add_utxo(address, utxo_key)


def _extract_addresses(script_pubkey: dict) -> list[str]:
    """Return addresses from ``scriptPubKey``, supporting both API shapes.

    - Bitcoin Core >= 22: ``{"address": "bcrt1q..."}`` (singular)
    - Bitcoin Core < 22:  ``{"addresses": ["bcrt1q...", ...]}`` (plural)
    """
    single = script_pubkey.get("address")
    if isinstance(single, str) and single:
        return [single]

    multi = script_pubkey.get("addresses")
    if isinstance(multi, list):
        return [a for a in multi if isinstance(a, str)]

    return []