"""Flask blueprint for the verification API."""

from __future__ import annotations

import io
import json

from flask import Blueprint, current_app, jsonify, request
from PIL import Image

from backend.core.errors import (
    CertiChainError,
    IndexerUnavailableError,
    IPFSError,
    IPFSBackendUnavailableError,
)
from backend.core.logging import get_logger
from backend.models.result import VerificationStatus
from backend.services.verification import verify_credential

logger = get_logger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

def _decode_qr_from_image(file_storage) -> str | None:
    """Decode the first QR code found in an uploaded image."""
    try:
        from PIL import Image
        import zxingcpp

        image = Image.open(io.BytesIO(file_storage.read()))
        results = zxingcpp.read_barcodes(image)
        if not results:
            return None
        return results[0].text
    except Exception as exc:
        logger.warning("failed to decode QR from uploaded image: %s", exc)
        return None


def _extract_fingerprint() -> str | None:
    """Extract the fingerprint string from either a file upload or JSON body."""
    # Mode 1: multipart/form-data with a 'file' field
    if "file" in request.files:
        fingerprint = _decode_qr_from_image(request.files["file"])
        if fingerprint:
            return _maybe_extract_encoded_fp(fingerprint)

    # Mode 2: JSON body
    body = request.get_json(silent=True)
    if isinstance(body, dict) and "fingerprint" in body:
        raw = body["fingerprint"]
        if isinstance(raw, str) and raw.strip():
            return _maybe_extract_encoded_fp(raw)

    return None


def _maybe_extract_encoded_fp(raw: str) -> str:
    """If ``raw`` is a JSON file (vc_fp_*.json), extract the encoded string."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if isinstance(parsed, dict) and "encoded_vc_fp" in parsed:
        return parsed["encoded_vc_fp"]
    return raw


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def _to_response(result) -> dict:
    """Convert a ``VerificationResult`` to the API response payload."""
    return {
        "verification_status": result.status.value,
        "verified": result.status is VerificationStatus.VALID,
        "reason": result.reason,
        "vc": result.credential,
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@bp.post("/verify")
def verify_endpoint():
    """Verify a credential fingerprint.

    Accepts either:
    - ``multipart/form-data`` with ``file`` = QR image
    - ``application/json`` with ``{"fingerprint": "..."}``

    Returns a JSON object with ``verification_status``, ``verified``,
    ``reason``, and ``vc``.
    """
    fingerprint = _extract_fingerprint()
    if not fingerprint:
        return jsonify({
            "verification_status": "invalid",
            "verified": False,
            "reason": "no fingerprint provided (file or JSON body expected)",
            "vc": None,
        }), 400

    runtime = current_app.config["RUNTIME"]

    try:
        result = verify_credential(
            fingerprint,
            rpc_client=runtime.rpc_client,
            indexer_client=runtime.indexer_client,
            ipfs_backend=runtime.ipfs_backend,
        )
    except IndexerUnavailableError as exc:
        logger.warning("indexer unavailable during verification: %s", exc)
        return jsonify({
            "verification_status": "invalid",
            "verified": False,
            "reason": f"indexer unavailable: {exc}",
            "vc": None,
        }), 503
    except (IPFSError, IPFSBackendUnavailableError) as exc:
        logger.warning("IPFS unavailable during verification: %s", exc)
        return jsonify({
            "verification_status": "invalid",
            "verified": False,
            "reason": f"IPFS unavailable: {exc}",
            "vc": None,
        }), 503
    except CertiChainError as exc:
        logger.warning("domain error during verification: %s", exc)
        return jsonify({
            "verification_status": "invalid",
            "verified": False,
            "reason": str(exc),
            "vc": None,
        }), 400
    except Exception as exc:
        logger.exception("unexpected error during verification")
        return jsonify({
            "verification_status": "invalid",
            "verified": False,
            "reason": "internal error while verifying credential",
            "vc": None,
        }), 500

    return jsonify(_to_response(result)), 200