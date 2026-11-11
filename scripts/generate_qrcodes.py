"""Generate QR codes from existing vc_fp JSON files.

Use this when a PD transaction has already been broadcast and the vc_fp
JSON files exist, but the QR images are missing.

Usage:
    python -m scripts.generate_qrcodes --config pd_bsc
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.core.logging import configure_logging, get_logger
from scripts.issue_degree_vc import _load_config  # reuse config loader
from backend.models.configs import PDDegreeConfig

logger = get_logger(__name__)


def _load_qr_renderer():
    """Import the QR helper lazily to keep this script lightweight."""
    from scripts.issue_degree_vc import _render_qrcode

    return _render_qrcode


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate QR codes from existing vc_fp files")
    parser.add_argument("--config", required=True, help="Config name (e.g. pd_bsc)")
    args = parser.parse_args()

    configure_logging()

    config = _load_config(args.config)
    if not isinstance(config, PDDegreeConfig):
        print(f"error: --config must point to a PD config, got {type(config).__name__}", file=sys.stderr)
        sys.exit(1)

    fp_dir = Path(config.vc_fp_path) / config.file_name
    qr_dir = Path(config.qrcode_path) / config.file_name

    if not fp_dir.exists():
        print(f"error: fingerprint directory not found: {fp_dir}", file=sys.stderr)
        sys.exit(1)

    qr_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(fp_dir.glob("vc_fp_*.json"))
    if not files:
        print(f"error: no vc_fp_*.json files in {fp_dir}", file=sys.stderr)
        sys.exit(1)

    render_qr = _load_qr_renderer()
    ok = 0
    for fp_file in files:
        try:
            data = json.loads(fp_file.read_text(encoding="utf-8"))
            encoded = data.get("encoded_vc_fp")
            if not isinstance(encoded, str) or not encoded:
                logger.warning("%s has no 'encoded_vc_fp' field, skipping", fp_file.name)
                continue
            index = int(fp_file.stem.replace("vc_fp_", ""))
            out_path = qr_dir / f"qrcode_{index}.png"
            if render_qr(encoded, out_path, index):
                ok += 1
                logger.info("wrote %s", out_path)
        except Exception as exc:
            logger.error("failed to process %s: %s", fp_file, exc)

    print(f"generated {ok}/{len(files)} QR codes in {qr_dir}")


if __name__ == "__main__":
    main()