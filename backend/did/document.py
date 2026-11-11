"""DID document helpers."""

from __future__ import annotations


def check_key_exists(did_doc: dict, public_key_hex: str) -> tuple[bool, str | None]:
    """Check whether ``public_key_hex`` is an authorised assertion method.

    Returns ``(key_exists, verification_method_id)``.
    """
    did_document = did_doc.get("didDocument", {})
    assertion_methods = did_document.get("assertionMethod", [])
    verification_methods = did_document.get("verificationMethod", [])

    for item in assertion_methods:
        if isinstance(item, str):
            # The assertion method is a reference like "#vckey-0".
            for method in verification_methods:
                if method.get("id", "").endswith(item):
                    if method.get("publicKeyHex") == public_key_hex:
                        return True, method.get("id")
        elif isinstance(item, dict):
            if item.get("publicKeyHex") == public_key_hex:
                return True, item.get("id")

    return False, None