"""Bitcoin RPC client for the standalone indexer.

Intentionally duplicates the minimal RPC surface needed by the indexer
(instead of importing from ``backend``) so that ``indexer`` stays a
self-contained service.
"""

from __future__ import annotations

import os
import time
from typing import Any

from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from dotenv import load_dotenv

load_dotenv()  # Load .env from project root so the indexer sees BITCOIN_RPC_* vars.

class IndexerRPCError(Exception):
    """Raised when the indexer cannot reach Bitcoin Core."""


class IndexerRPC:
    """Minimal Bitcoin RPC client used only by the indexer."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: int = 120,
    ) -> None:
        host = host or os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
        port = port or int(os.getenv("BITCOIN_RPC_PORT", "8332"))
        user = user or os.getenv("BITCOIN_RPC_USER", "")
        password = password or os.getenv("BITCOIN_RPC_PASSWORD", "")
        if not user or not password:
            raise IndexerRPCError(
                "BITCOIN_RPC_USER and BITCOIN_RPC_PASSWORD must be set"
            )
        self._url = f"http://{user}:{password}@{host}:{port}"
        self._timeout = timeout
        self._proxy = AuthServiceProxy(self._url, timeout=timeout)

    def call(self, method: str, *params: Any) -> Any:
        """Call an RPC method. Raises ``IndexerRPCError`` on failure."""
        attempt = 0
        last_error: Exception | None = None
        while attempt < 3:
            try:
                return getattr(self._proxy, method)(*params)
            except JSONRPCException as exc:
                raise IndexerRPCError(f"RPC {method} failed: {exc}") from exc
            except Exception as exc:
                last_error = exc
                attempt += 1
                if attempt >= 3:
                    break
                time.sleep(2 ** attempt)
                self._proxy = AuthServiceProxy(self._url, timeout=self._timeout)
        raise IndexerRPCError(f"RPC {method} failed after 3 attempts: {last_error}")

    # -- convenience wrappers --------------------------------------------

    def getblockcount(self) -> int:
        return self.call("getblockcount")

    def getblockhash(self, height: int) -> str:
        return self.call("getblockhash", height)

    def getblock(self, block_hash: str, verbosity: int = 2) -> dict:
        return self.call("getblock", block_hash, verbosity)

    def getrawtransaction(self, txid: str, verbose: bool = True) -> dict:
        return self.call("getrawtransaction", txid, verbose)