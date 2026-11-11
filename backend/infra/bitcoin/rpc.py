"""Bitcoin Core JSON-RPC client (transport layer only).

This module only knows how to *talk* to Bitcoin Core. It does not know
anything about the OCVC protocol; that logic lives in ``services/onchain_reader.py``.
"""

from __future__ import annotations

import time
from typing import Any

from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

from backend.core.config import BitcoinNetwork, BitcoinSettings
from backend.core.errors import BitcoinRPCError
from backend.core.logging import get_logger

logger = get_logger(__name__)

# Methods that can be safely retried on transient network errors.
# Write methods (sendrawtransaction) must NOT be blindly retried.
_RETRYABLE_METHODS = frozenset(
    {
        "getrawtransaction",
        "gettransaction",
        "getblock",
        "getblockhash",
        "getblockcount",
        "decoderawtransaction",
        "decodescript",
        "validateaddress",
    }
)


class BitcoinRPCClient:
    """Synchronous Bitcoin Core JSON-RPC client with bounded retries."""

    def __init__(self, settings: BitcoinSettings) -> None:
        self._settings = settings
        self._proxy = AuthServiceProxy(settings.rpc_url, timeout=settings.rpc_timeout)

    @property
    def network(self) -> BitcoinNetwork:
        return self._settings.network

    # -- internal ---------------------------------------------------------

    def _call(self, method: str, *params: Any, retries: int = 3) -> Any:
        attempt = 0
        last_error: Exception | None = None
        while attempt < retries:
            try:
                return getattr(self._proxy, method)(*params)
            except JSONRPCException as exc:
                # Business error from Bitcoin Core — not retryable.
                raise BitcoinRPCError(f"RPC {method} failed: {exc}") from exc
            except Exception as exc:  # network / connection error
                last_error = exc
                attempt += 1
                if attempt >= retries or method not in _RETRYABLE_METHODS:
                    break
                delay = 2 ** attempt
                logger.warning(
                    "RPC %s failed (attempt %d/%d): %s. Retrying in %ds",
                    method,
                    attempt,
                    retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
                self._proxy = AuthServiceProxy(
                    self._settings.rpc_url, timeout=self._settings.rpc_timeout
                )
        raise BitcoinRPCError(f"RPC {method} failed after {attempt} attempts: {last_error}")

    # -- read methods -----------------------------------------------------

    def getrawtransaction(self, txid: str, verbose: bool = False) -> Any:
        return self._call("getrawtransaction", txid, verbose)

    def gettransaction(self, txid: str) -> Any:
        return self._call("gettransaction", txid)

    def decoderawtransaction(self, raw_hex: str) -> Any:
        return self._call("decoderawtransaction", raw_hex)

    def getblock(self, block_hash: str, verbosity: int = 1) -> Any:
        return self._call("getblock", block_hash, verbosity)

    def getblockhash(self, height: int) -> str:
        return self._call("getblockhash", height)

    def getblockcount(self) -> int:
        return self._call("getblockcount")

    def decodescript(self, script_hex: str) -> Any:
        return self._call("decodescript", script_hex)

    def validateaddress(self, address: str) -> Any:
        return self._call("validateaddress", address)

    # -- write methods ----------------------------------------------------

    def createrawtransaction(self, inputs: list[dict], outputs: dict | list) -> str:
        return self._call("createrawtransaction", inputs, outputs)

    def signrawtransactionwithkey(self, unsigned_hex: str, private_keys: list[str]) -> Any:
        return self._call("signrawtransactionwithkey", unsigned_hex, private_keys)

    def sendrawtransaction(self, signed_hex: str) -> str:
        return self._call("sendrawtransaction", signed_hex)

    def generatetoaddress(self, n_blocks: int, address: str) -> list[str]:
        """Mine ``n_blocks`` to ``address`` (regtest only)."""
        return self._call("generatetoaddress", n_blocks, address)