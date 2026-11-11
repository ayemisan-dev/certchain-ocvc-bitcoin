"""HTTP client for the standalone ``bc_index`` service.

All connectivity failures raise ``IndexerUnavailableError`` so callers can
degrade gracefully.
"""

from __future__ import annotations

from typing import Any

import requests

from backend.core.config import IndexerSettings
from backend.core.errors import IndexerUnavailableError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class IndexerClient:
    """Thin HTTP client for ``bc_index``."""

    def __init__(self, settings: IndexerSettings) -> None:
        self._base_url = settings.base_url.rstrip("/")
        self._timeout = settings.timeout
        self._enabled = settings.enabled

    def _get(self, endpoint: str, *args: Any) -> dict | None:
        if not self._enabled:
            raise IndexerUnavailableError("INDEXER_ENABLED=false")

        url = f"{self._base_url}/{endpoint}/" + "/".join(str(a) for a in args)
        try:
            response = requests.get(url, timeout=self._timeout)
        except requests.RequestException as exc:
            raise IndexerUnavailableError(f"indexer unreachable: {exc}") from exc

        if response.status_code != 200:
            raise IndexerUnavailableError(
                f"indexer returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise IndexerUnavailableError(f"indexer returned invalid JSON: {exc}") from exc

    # -- public API -------------------------------------------------------

    def get_addr_in_txs(self, address: str) -> list[str] | None:
        data = self._get("get_addr_in_txs", address)
        if not data or "transactions" not in data:
            return None
        return data["transactions"]

    def get_addr_out_txs(self, address: str) -> list[str] | None:
        data = self._get("get_addr_out_txs", address)
        if not data or "transactions" not in data:
            return None
        return data["transactions"]

    def get_tx_spending(self, txid: str, vout: int) -> str | None:
        data = self._get("get_tx_spending", txid, vout)
        if not data:
            return None
        return data.get("spending_txid")

    def get_address_utxos(self, address: str) -> list[str] | None:
        data = self._get("get_address_utxos", address)
        if not data or "UTXOs" not in data:
            return None
        return data["UTXOs"]

    def get_tx_detail(self, txid: str) -> dict | None:
        data = self._get("get_tx_detail", txid)
        if not data:
            return None
        return data.get("tx data")

    def get_tx(self, txid: str) -> dict | None:
        data = self._get("get_tx", txid)
        if not data:
            return None
        return data.get("tx data")