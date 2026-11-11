"""LevelDB-backed index storage."""

from __future__ import annotations

import json
from pathlib import Path

import plyvel_next as plyvel


class IndexStorage:
    """Four LevelDB databases used by the indexer.

    - ``addrindex_in``:  address -> list of txids whose inputs spend from it
    - ``addrindex_out``: address -> list of txids whose outputs pay to it
    - ``txindex``:       "<txid>:<vout>" -> spending txid
    - ``utxoindex``:     address -> list of unspent "<txid>:<vout>"
    """

    def __init__(self, base_dir: str | Path) -> None:
        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)

        self.addrindex_in = plyvel.DB(str(base / "addrindex_in"), create_if_missing=True)
        self.addrindex_out = plyvel.DB(str(base / "addrindex_out"), create_if_missing=True)
        self.txindex = plyvel.DB(str(base / "txindex"), create_if_missing=True)
        self.utxoindex = plyvel.DB(str(base / "utxoindex"), create_if_missing=True)

    def close(self) -> None:
        for db in (self.addrindex_in, self.addrindex_out, self.txindex, self.utxoindex):
            db.close()

    # -- addrindex_in ----------------------------------------------------

    def get_addr_in_txs(self, address: str) -> list[str] | None:
        return self._get_list(self.addrindex_in, address)

    def add_addr_in_tx(self, address: str, txid: str) -> None:
        self._append_to_list(self.addrindex_in, address, txid)

    # -- addrindex_out ---------------------------------------------------

    def get_addr_out_txs(self, address: str) -> list[str] | None:
        return self._get_list(self.addrindex_out, address)

    def add_addr_out_tx(self, address: str, txid: str) -> None:
        self._append_to_list(self.addrindex_out, address, txid)

    # -- txindex ---------------------------------------------------------

    def get_spending_txid(self, txid: str, vout: int) -> str | None:
        key = f"{txid}:{vout}".encode()
        value = self.txindex.get(key)
        return value.decode() if value else None

    def set_spending_txid(self, txid: str, vout: int, spending_txid: str) -> None:
        key = f"{txid}:{vout}".encode()
        self.txindex.put(key, spending_txid.encode())

    # -- utxoindex -------------------------------------------------------

    def get_utxos(self, address: str) -> list[str] | None:
        return self._get_list(self.utxoindex, address)

    def add_utxo(self, address: str, utxo_key: str) -> None:
        self._append_to_list(self.utxoindex, address, utxo_key)

    def remove_utxo(self, address: str, utxo_key: str) -> None:
        existing = self.get_utxos(address) or []
        if utxo_key in existing:
            existing.remove(utxo_key)
            self.utxoindex.put(address.encode(), json.dumps(existing).encode())

    # -- progress file ---------------------------------------------------

    @staticmethod
    def read_progress(progress_file: str | Path) -> tuple[int, int]:
        """Return ``(last_height, tx_count)``, or ``(0, 0)`` if not found."""
        path = Path(progress_file)
        if not path.exists():
            return 0, 0
        try:
            content = path.read_text().strip()
            height_str, count_str = content.split(",")
            return int(height_str), int(count_str)
        except (ValueError, OSError):
            return 0, 0

    @staticmethod
    def write_progress(progress_file: str | Path, height: int, tx_count: int) -> None:
        Path(progress_file).write_text(f"{height},{tx_count}")

    # -- internal helpers ------------------------------------------------

    @staticmethod
    def _get_list(db: plyvel.DB, key: str) -> list[str] | None:
        raw = db.get(key.encode())
        if raw is None:
            return None
        try:
            return json.loads(raw.decode())
        except (ValueError, UnicodeDecodeError):
            return None

    @staticmethod
    def _append_to_list(db: plyvel.DB, key: str, value: str) -> None:
        existing = IndexStorage._get_list(db, key) or []
        if value not in existing:
            existing.append(value)
            db.put(key.encode(), json.dumps(existing).encode())