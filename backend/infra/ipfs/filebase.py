"""Filebase IPFS backend (managed pinning service).

Reference: https://filebase.com/docs/ipfs
"""

from __future__ import annotations

import json

import requests

from backend.core.config import IPFSSettings
from backend.core.errors import IPFSBackendUnavailableError, IPFSError
from backend.core.logging import get_logger
from backend.infra.ipfs.base import IPFSBackend

logger = get_logger(__name__)

_TIMEOUT = 60


class FilebaseIPFSBackend(IPFSBackend):
    """Talks to Filebase's IPFS RPC endpoint."""

    def __init__(self, settings: IPFSSettings) -> None:
        if not settings.filebase_rpc_url or not settings.filebase_rpc_token:
            raise IPFSError(
                "FILEBASE_IPFS_RPC_URL and FILEBASE_IPFS_RPC_TOKEN must be set"
            )
        self._base_url = settings.filebase_rpc_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.filebase_rpc_token}"}

    def add_file(self, file_path: str) -> str:
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            raise IPFSError(f"file not found: {file_path}")
        return self.add_bytes(path.read_bytes(), filename=path.name)

    def add_bytes(self, data: bytes, filename: str = "data.bin") -> str:
        try:
            response = requests.post(
                f"{self._base_url}/api/v0/add",
                params={"pin": "true"},
                files={"file": (filename, data)},
                headers=self._headers,
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise IPFSBackendUnavailableError(f"Filebase unreachable: {exc}") from exc

        if response.status_code != 200:
            raise IPFSError(
                f"Filebase add failed: HTTP {response.status_code} - {response.text}"
            )

        last_line = [line for line in response.text.splitlines() if line.strip()][-1]
        return json.loads(last_line)["Hash"]

    def get_file(self, cid: str) -> dict:
        try:
            response = requests.post(
                f"{self._base_url}/api/v0/cat",
                params={"arg": cid},
                headers=self._headers,
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise IPFSBackendUnavailableError(f"Filebase unreachable: {exc}") from exc

        if response.status_code != 200:
            raise IPFSError(f"Filebase cat failed for {cid}: HTTP {response.status_code}")
        return json.loads(response.text)

    def is_available(self) -> bool:
        try:
            response = requests.post(
                f"{self._base_url}/api/v0/version",
                headers=self._headers,
                timeout=10,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False