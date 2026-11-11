"""Local IPFS backend using the HTTP API of an ``ipfs daemon``."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import requests

from backend.core.config import IPFSSettings
from backend.core.errors import IPFSBackendUnavailableError, IPFSError
from backend.core.logging import get_logger
from backend.infra.ipfs.base import IPFSBackend

logger = get_logger(__name__)

_TIMEOUT = 30


class LocalIPFSBackend(IPFSBackend):
    """Talks to ``ipfs daemon`` via its HTTP API."""

    def __init__(self, settings: IPFSSettings) -> None:
        self._base_url = _multiaddr_to_http(settings.local_api_url)

    def add_file(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise IPFSError(f"file not found: {file_path}")
        return self.add_bytes(path.read_bytes(), filename=path.name)

    def add_bytes(self, data: bytes, filename: str = "data.bin") -> str:
        try:
            response = requests.post(
                f"{self._base_url}/api/v0/add",
                files={"file": (filename, data)},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise IPFSBackendUnavailableError(f"local IPFS unreachable: {exc}") from exc

        if response.status_code != 200:
            raise IPFSError(f"IPFS add failed: HTTP {response.status_code} - {response.text}")

        # The API returns JSON-lines; the last non-empty line has the final CID.
        last_line = [line for line in response.text.splitlines() if line.strip()][-1]
        payload = json.loads(last_line)
        return payload["Hash"]

    def get_file(self, cid: str) -> dict:
        try:
            response = requests.post(
                f"{self._base_url}/api/v0/cat",
                params={"arg": cid},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise IPFSBackendUnavailableError(f"local IPFS unreachable: {exc}") from exc

        if response.status_code != 200:
            raise IPFSError(f"IPFS cat failed for {cid}: HTTP {response.status_code}")

        return json.loads(response.text)

    def is_available(self) -> bool:
        try:
            response = requests.post(f"{self._base_url}/api/v0/version", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False


def _multiaddr_to_http(multiaddr: str) -> str:
    """Convert ``/ip4/127.0.0.1/tcp/5001`` to ``http://127.0.0.1:5001``."""
    parts = [p for p in multiaddr.split("/") if p]
    try:
        host = parts[parts.index("ip4") + 1]
        port = parts[parts.index("tcp") + 1]
    except (ValueError, IndexError) as exc:
        raise IPFSError(f"invalid multiaddr: {multiaddr}") from exc
    return f"http://{host}:{port}"