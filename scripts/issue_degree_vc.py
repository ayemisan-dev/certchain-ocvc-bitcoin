"""Issue a batch of degree credentials (CLI).

Usage:
    python -m scripts.issue_degree_vc --config pd_bsc
    python -m scripts.issue_degree_vc --config ps_create
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.logging import configure_logging, get_logger
from backend.encoding.cbor_multibase import cbor_zlib_encode, vc_fp_encode
from backend.encoding.jsonld import decompose_vc
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.models.configs import (
    PDDegreeConfig,
    PIConfig,
    PSConfig,
)
from backend.services.issuance import (
    build_vc_fingerprints,
    issue_transaction,
    merkle_root_and_proofs,
)

logger = get_logger(__name__)

_CONFIG_DIR = Path("backend/configs/degree")


def _load_config(name: str) -> PSConfig | PIConfig | PDDegreeConfig:
    """Load a degree config file by name (without .json extension)."""
    path = _CONFIG_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"config not found: {path}. "
            f"Copy {path.with_suffix('.json.example')} to {path} and fill in values."
        )

    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    tx_type = raw.get("tx_type")
    if tx_type in ("PS", "PI"):
        return PSConfig.model_validate(raw) if tx_type == "PS" else PIConfig.model_validate(raw)
    if tx_type == "PD":
        return PDDegreeConfig.model_validate(raw)
    raise ValueError(f"unsupported tx_type: {tx_type}")


def _issue_pd_degree(config: PDDegreeConfig, rpc: BitcoinRPCClient) -> str:
    """Issue a PD transaction for a batch of degree credentials."""
    # 1. Load full VC list
    full_vc_list = _load_json(config.full_vc_list_path)
    if not isinstance(full_vc_list, list) or not full_vc_list:
        raise ValueError(f"empty or invalid VC list: {config.full_vc_list_path}")

    # 2. Load VC specification (template at index 1)
    vc_spec = _load_json(config.vc_temp_path)
    if not isinstance(vc_spec, list) or len(vc_spec) < 2:
        raise ValueError(f"invalid VC spec (expected list): {config.vc_temp_path}")
    vc_template = vc_spec[1]

    # 3. Decompose each full VC to a vd value array
    vd_list = [decompose_vc(vc, vc_template, "object") for vc in full_vc_list]
    logger.info("decomposed %d credentials into vd arrays", len(vd_list))

    # 4. Compute Merkle root (only Hash_Value mode is supported for batch issuance)
    if config.data_type != "Hash_Value":
        raise ValueError(
            f"degree batch issuance requires data_type='Hash_Value', got {config.data_type!r}"
        )
    merkle_root, proofs = merkle_root_and_proofs(vd_list)
    logger.info("merkle root: %s", merkle_root)

    # 5. Issue the PD transaction with the computed Merkle root
    pd_txid = issue_transaction(config, rpc, pd_data_hex=merkle_root)
    logger.info("PD transaction broadcast: %s", pd_txid)

    # 6. Generate vc_fp files (one per student)
    fp_template = _load_json(config.vc_fp_tem_path)
    header = fp_template["header"]
    bcn = fp_template["proof"].get("bcn", "btc:regtest")

    vc_fp_list, encoded_list = build_vc_fingerprints(
        vd_list, proofs, pd_txid, header, bcn=bcn, payload_from_vd=True
    )

    _write_fingerprints(config, vc_fp_list, encoded_list)
    return pd_txid


def _write_fingerprints(
    config: PDDegreeConfig,
    vc_fp_list: list[dict],
    encoded_list: list[str],
) -> None:
    """Write one JSON file per fingerprint, plus a QR image for each."""
    output_dir = Path(config.vc_fp_path) / config.file_name
    output_dir.mkdir(parents=True, exist_ok=True)

    qrcode_dir = Path(config.qrcode_path) / config.file_name
    qrcode_dir.mkdir(parents=True, exist_ok=True)

    qr_ok = 0
    for index, (vc_fp, encoded) in enumerate(zip(vc_fp_list, encoded_list), start=1):
        payload = {"vc_fp": vc_fp, "encoded_vc_fp": encoded}
        file_path = output_dir / f"vc_fp_{index}.json"
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        if _render_qrcode(encoded, qrcode_dir / f"qrcode_{index}.png", index):
            qr_ok += 1

    logger.info("wrote %d fingerprints to %s", len(vc_fp_list), output_dir)
    logger.info("wrote %d QR codes to %s", qr_ok, qrcode_dir)


def _render_qrcode(data: str, output_path: Path, index: int) -> bool:
    """Render one QR code PNG. Returns True on success, False on overflow.

    A typical encoded fingerprint is ~800 bytes. QR version 40 with L-level
    error correction holds up to 2953 bytes in byte mode, so we have plenty
    of margin. If the data ever exceeds that, the JSON file still holds the
    fingerprint, so we just log a warning instead of crashing the batch.
    """
    import qrcode
    from qrcode import constants
    from qrcode.exceptions import DataOverflowError

    qr = qrcode.QRCode(
        version=None,
        error_correction=constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    try:
        qr.make(fit=True)
    except DataOverflowError:
        logger.warning(
            "fingerprint #%d (%d bytes) exceeds QR capacity; "
            "skipping QR generation (JSON file still written)",
            index,
            len(data),
        )
        return False

    img = qr.make_image(fill_color="black", back_color="white")
    with open(output_path, "wb") as f:
        img.save(f)
    return True


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a degree credential transaction")
    parser.add_argument(
        "--config",
        required=True,
        help="Config name without .json (e.g. ps_create, pd_bsc)",
    )
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    rpc = BitcoinRPCClient(settings.bitcoin)

    config = _load_config(args.config)

    if isinstance(config, PDDegreeConfig):
        txid = _issue_pd_degree(config, rpc)
    else:
        txid = issue_transaction(config, rpc)

    print(f"txid: {txid}")


if __name__ == "__main__":
    main()