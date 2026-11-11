"""Factory to create the configured IPFS backend."""

from __future__ import annotations

from backend.core.config import IPFSSettings
from backend.core.errors import ConfigurationError
from backend.infra.ipfs.base import IPFSBackend
from backend.infra.ipfs.filebase import FilebaseIPFSBackend
from backend.infra.ipfs.local import LocalIPFSBackend


def get_ipfs_backend(settings: IPFSSettings) -> IPFSBackend:
    """Instantiate the backend configured by ``IPFS_BACKEND``."""
    if settings.backend == "local":
        return LocalIPFSBackend(settings)
    if settings.backend == "filebase":
        return FilebaseIPFSBackend(settings)
    raise ConfigurationError(
        f"unknown IPFS_BACKEND={settings.backend!r}; expected 'local' or 'filebase'"
    )