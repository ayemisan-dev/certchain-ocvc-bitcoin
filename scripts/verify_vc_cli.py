"""Verify a credential fingerprint from the command line.

Usage:
    python -m scripts.verify_vc_cli --file vc_fp_1.json
    python -m scripts.verify_vc_cli --fp "eJx..."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.core.config import get_settings
from backend.core.logging import configure_logging
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.infra.indexer.client import IndexerClient
from backend.infra.ipfs.factory import get_ipfs_backend
from backend.services.verification import verify_credential

def _decode_qr_image(image_path: str) -> str:
    """Decode the first QR code from a PNG/JPG image (zxing-cpp, no system lib)."""
    from PIL import Image

    try:
        import zxingcpp
    except ImportError as exc:
        raise ImportError(
            "zxing-cpp is required for --image mode: pip install zxing-cpp"
        ) from exc

    img = Image.open(image_path)
    results = zxingcpp.read_barcodes(img)
    if not results:
        raise ValueError(f"no QR code found in {image_path}")
    return results[0].text


def _load_fingerprint(
    fingerprint_arg: str | None,
    file_arg: str | None,
    image_arg: str | None,
) -> str:
    if fingerprint_arg:
        return fingerprint_arg

    if image_arg:
        return _decode_qr_image(image_arg)

    if file_arg:
        raw = Path(file_arg).read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip()
        if isinstance(parsed, dict) and "encoded_vc_fp" in parsed:
            return parsed["encoded_vc_fp"]
        return raw.strip()

    raise ValueError("provide one of --fp, --file, or --image")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a credential fingerprint")
    parser.add_argument("--fp", help="Encoded fingerprint string")
    parser.add_argument("--file", help="Path to vc_fp_*.json or a raw encoded string file")
    parser.add_argument("--image", help="Path to a QR code image (PNG/JPG)")
    parser.add_argument("--json", action="store_true", help="Print full JSON result")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    rpc = BitcoinRPCClient(settings.bitcoin)
    indexer = IndexerClient(settings.indexer)
    ipfs = get_ipfs_backend(settings.ipfs)

    try:
        encoded_fp = _load_fingerprint(args.fp, args.file, args.image)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    result = verify_credential(encoded_fp, rpc, indexer, ipfs)

    if args.json:
        print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    else:
        print(f"status: {result.status.value}")
        if result.reason:
            print(f"reason: {result.reason}")

    sys.exit({"valid": 0, "revoked": 1, "invalid": 2}[result.status.value])

if __name__ == "__main__":
    main()