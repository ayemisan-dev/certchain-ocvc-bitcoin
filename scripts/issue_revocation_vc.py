"""Issue a revocation-list transaction (CLI).

Usage:
    python -m scripts.issue_revocation_vc --config bitstring/pd_config_bstr
    python -m scripts.issue_revocation_vc --config indexlist/pd_config_index
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.logging import configure_logging, get_logger
from backend.encoding.bitstr import encoded_bitstr_m, encoded_bitstr_reason
from backend.encoding.cbor_multibase import cbor_encode
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.models.configs import PDRevocationConfig, PIConfig, PSConfig
from backend.services.issuance import issue_transaction

logger = get_logger(__name__)

_CONFIG_DIR = Path("backend/configs/revocation")


def _load_config(name: str) -> PSConfig | PIConfig | PDRevocationConfig:
    """Load a revocation config file by name (relative to revocation/)."""
    path = _CONFIG_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"config not found: {path}. "
            f"Copy {path.with_suffix('.json.example')} and fill in values."
        )

    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    tx_type = raw.get("tx_type")
    if tx_type == "PS":
        return PSConfig.model_validate(raw)
    if tx_type == "PI":
        return PIConfig.model_validate(raw)
    if tx_type == "PD":
        return PDRevocationConfig.model_validate(raw)
    raise ValueError(f"unsupported tx_type: {tx_type}")


def _encode_bitstring_vd(config: PDRevocationConfig) -> str:
    """Encode the revocation data as ``[id, dateIssued, [[revocationEntry]]]``
    with a Golomb-compressed bitstring.
    """
    assert config.bits_len is not None and config.m is not None
    revoke_int, encoded_len = encoded_bitstr_m(
        config.bits_len, config.revoked_list, config.m
    )
    reason_int = encoded_bitstr_reason(config.reason_list, config.bitPerCred)

    vd_data = [
        "#1",
        date.today().isoformat(),
        [["1#list", encoded_len, revoke_int, reason_int]],
    ]
    return cbor_encode(vd_data).hex()


def _encode_indexlist_vd(config: PDRevocationConfig) -> str:
    """Encode the revocation data as ``[id, dateIssued, [[revocationEntry]]]``
    with a plain index list.
    """
    reason_int = encoded_bitstr_reason(config.reason_list, config.bitPerCred)

    vd_data = [
        "#1",
        date.today().isoformat(),
        [["1#list", None, config.revoked_list, reason_int]],
    ]
    return cbor_encode(vd_data).hex()


def _issue_pd_revocation(config: PDRevocationConfig, rpc: BitcoinRPCClient) -> str:
    """Issue a PD transaction for the revocation list."""
    config.validate_for_rev_type()

    if config.rev_type == "bitstring":
        encoded_vd = _encode_bitstring_vd(config)
    elif config.rev_type == "indexList":
        encoded_vd = _encode_indexlist_vd(config)
    else:
        raise ValueError(f"unsupported rev_type: {config.rev_type}")

    logger.info(
        "revocation type=%s, %d revoked, encoded vd size=%d bytes",
        config.rev_type,
        len(config.revoked_list),
        len(encoded_vd) // 2,
    )
    return issue_transaction(config, rpc, pd_data_hex=encoded_vd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a revocation-list transaction")
    parser.add_argument(
        "--config",
        required=True,
        help="Config name relative to backend/configs/revocation/ (e.g. bitstring/pd_config_bstr)",
    )
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    rpc = BitcoinRPCClient(settings.bitcoin)

    config = _load_config(args.config)

    if isinstance(config, PDRevocationConfig):
        txid = _issue_pd_revocation(config, rpc)
    else:
        txid = issue_transaction(config, rpc)

    print(f"txid: {txid}")


if __name__ == "__main__":
    main()