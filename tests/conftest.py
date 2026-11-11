"""Shared pytest fixtures.

Unit tests use only the pure-data fixtures below.
Integration tests additionally require ``--regtest`` (see pytest_addoption).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.core.config import (
    BitcoinNetwork,
    BitcoinSettings,
    IPFSSettings,
    IndexerSettings,
    Settings,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Pure-data fixtures (no external dependencies)
# ---------------------------------------------------------------------------

def _load_fixture(name: str):
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"missing fixture: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def full_bsc_vc() -> dict:
    """A complete degree VC used as the source for decomposition tests."""
    return _load_fixture("full_bsc_vc.json")


@pytest.fixture(scope="session")
def bsc_vc_spec() -> list:
    """The OCVC protocol specification (``[desc, template, external]``)."""
    return _load_fixture("bsc_vc_spec.json")


@pytest.fixture(scope="session")
def bsc_vd() -> list:
    """The expected ``vd`` (credential-specific) value array."""
    return _load_fixture("bsc_vd.json")


@pytest.fixture(scope="session")
def bsc_vi() -> list:
    """The expected ``vi`` (common) value array."""
    return _load_fixture("bsc_vi.json")


@pytest.fixture(scope="session")
def example_fp_text() -> str:
    """An encoded fingerprint (Base64URL.ZLIB.CBOR) as a plain string."""
    path = FIXTURES_DIR / "encoded_vc_fp.txt"
    if not path.exists():
        pytest.skip(f"missing fixture: {path}")
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Settings fixture (never reads the real .env)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_settings() -> Settings:
    """A deterministic Settings object for unit tests."""
    return Settings(
        flask_env="test",
        flask_debug=False,
        flask_host="127.0.0.1",
        flask_port=8000,
        cors_origins=[],
        log_level="DEBUG",
        bitcoin=BitcoinSettings(
            network=BitcoinNetwork.REGTEST,
            rpc_host="127.0.0.1",
            rpc_port=8332,
            rpc_user="test",
            rpc_password="test",
            rpc_timeout=5,
        ),
        indexer=IndexerSettings(
            enabled=False,
            base_url="http://127.0.0.1:5000",
            timeout=5,
        ),
        ipfs=IPFSSettings(
            backend="local",
            filebase_rpc_url="",
            filebase_rpc_token="",
            local_api_url="/ip4/127.0.0.1/tcp/5001",
        ),
    )


# ---------------------------------------------------------------------------
# Integration-only fixtures (skipped unless regtest is running)
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--regtest",
        action="store_true",
        default=False,
        help="Run integration tests that require a live regtest node",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires regtest + bc_index + IPFS",
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip ``@pytest.mark.integration`` tests when --regtest is absent."""
    if config.getoption("--regtest"):
        return
    skip = pytest.mark.skip(reason="use --regtest to run integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def regtest_rpc():
    """A live BitcoinRPCClient. Skips the test if the node is unreachable."""
    if not os.environ.get("BITCOIN_RPC_USER"):
        pytest.skip("BITCOIN_RPC_USER not set; regtest unavailable")

    from backend.core.config import get_settings
    from backend.infra.bitcoin.rpc import BitcoinRPCClient

    try:
        settings = get_settings()
        client = BitcoinRPCClient(settings.bitcoin)
        client.getblockcount()
    except Exception as exc:
        pytest.skip(f"regtest node unavailable: {exc}")

    return client


@pytest.fixture(scope="session")
def indexer_client():
    """A live IndexerClient. Skips the test if the indexer is unreachable."""
    from backend.core.config import get_settings
    from backend.infra.indexer.client import IndexerClient

    try:
        settings = get_settings()
        client = IndexerClient(settings.indexer)
        client.get_tx_spending("0" * 64, 0)  # any call to test reachability
    except Exception as exc:
        pytest.skip(f"indexer unavailable: {exc}")

    return client


@pytest.fixture(scope="session")
def ipfs_backend():
    """A live IPFS backend. Skips the test if IPFS is unreachable."""
    from backend.core.config import get_settings
    from backend.infra.ipfs.factory import get_ipfs_backend

    settings = get_settings()
    backend = get_ipfs_backend(settings.ipfs)
    if not backend.is_available():
        pytest.skip(f"IPFS backend '{settings.ipfs.backend}' unavailable")
    return backend