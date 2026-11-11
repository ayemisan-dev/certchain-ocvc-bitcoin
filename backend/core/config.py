"""Application configuration loaded from environment variables.

Usage:
    from backend.core.config import get_settings
    settings = get_settings()
    settings.bitcoin.network   # BitcoinNetwork.REGTEST
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()  # load .env 


class BitcoinNetwork(str, Enum):
    REGTEST = "regtest"
    TESTNET = "testnet"
    MAINNET = "mainnet"


@dataclass(frozen=True)
class BitcoinSettings:
    network: BitcoinNetwork
    rpc_host: str
    rpc_port: int
    rpc_user: str
    rpc_password: str
    rpc_timeout: int

    @property
    def rpc_url(self) -> str:
        return f"http://{self.rpc_user}:{self.rpc_password}@{self.rpc_host}:{self.rpc_port}"

    @property
    def is_regtest(self) -> bool:
        return self.network is BitcoinNetwork.REGTEST


@dataclass(frozen=True)
class IndexerSettings:
    enabled: bool
    base_url: str
    timeout: int


@dataclass(frozen=True)
class IPFSSettings:
    backend: str  # "filebase" | "local"
    filebase_rpc_url: str
    filebase_rpc_token: str
    local_api_url: str


@dataclass(frozen=True)
class Settings:
    flask_env: str
    flask_debug: bool
    flask_host: str
    flask_port: int
    cors_origins: list[str]
    log_level: str
    bitcoin: BitcoinSettings
    indexer: IndexerSettings
    ipfs: IPFSSettings


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build and cache the Settings object. Raises on invalid config."""
    network = BitcoinNetwork(os.getenv("BITCOIN_NETWORK", "regtest").lower())

    return Settings(
        flask_env=os.getenv("FLASK_ENV", "production"),
        flask_debug=_get_bool("FLASK_DEBUG", False),
        flask_host=os.getenv("FLASK_HOST", "127.0.0.1"),
        flask_port=_get_int("FLASK_PORT", 8000),
        cors_origins=[
            o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
        ],
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        bitcoin=BitcoinSettings(
            network=network,
            rpc_host=os.getenv("BITCOIN_RPC_HOST", "127.0.0.1"),
            rpc_port=_get_int("BITCOIN_RPC_PORT", 8332),
            rpc_user=_require("BITCOIN_RPC_USER"),
            rpc_password=_require("BITCOIN_RPC_PASSWORD"),
            rpc_timeout=_get_int("BITCOIN_RPC_TIMEOUT", 120),
        ),
        indexer=IndexerSettings(
            enabled=_get_bool("INDEXER_ENABLED", True),
            base_url=os.getenv("INDEXER_BASE_URL", "http://127.0.0.1:5000"),
            timeout=_get_int("INDEXER_TIMEOUT", 10),
        ),
        ipfs=IPFSSettings(
            backend=os.getenv("IPFS_BACKEND", "filebase").lower(),
            filebase_rpc_url=os.getenv("FILEBASE_IPFS_RPC_URL", ""),
            filebase_rpc_token=os.getenv("FILEBASE_IPFS_RPC_TOKEN", ""),
            local_api_url=os.getenv("IPFS_LOCAL_API_URL", "/ip4/127.0.0.1/tcp/5001"),
        ),
    )