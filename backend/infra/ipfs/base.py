"""Abstract IPFS backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IPFSBackend(ABC):
    """Interface for adding and reading files on IPFS."""

    @abstractmethod
    def add_file(self, file_path: str) -> str:
        """Add a file to IPFS and return its CID."""

    @abstractmethod
    def add_bytes(self, data: bytes, filename: str = "data.bin") -> str:
        """Add raw bytes to IPFS and return its CID."""

    @abstractmethod
    def get_file(self, cid: str) -> dict:
        """Fetch a JSON document from IPFS by CID."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if the backend is reachable."""