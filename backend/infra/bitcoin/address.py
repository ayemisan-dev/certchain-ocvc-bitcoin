"""Bitcoin address helpers derived from a public or private key."""

from __future__ import annotations

import base58


def generate_legacy_address(public_key_hex: str, network: str = "testnet") -> str:
    """Generate a P2PKH (legacy) address from a compressed secp256k1 public key."""
    import hashlib

    public_key_bytes = bytes.fromhex(public_key_hex)
    sha256_hash = hashlib.sha256(public_key_bytes).digest()
    ripemd160 = hashlib.new("ripemd160", sha256_hash).digest()

    prefix = b"\x6f" if network in ("testnet", "regtest") else b"\x00"
    payload = prefix + ripemd160
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return base58.b58encode(payload + checksum).decode()

def p2wsh_address_from_script(witness_script_hex: str, network: str = "regtest") -> str:
    """Compute the P2WSH bech32 address for a witness script.

    P2WSH (BIP141): ``OP_0 <sha256(witness_script)>``.
    Address HRP depends on the network: bc (mainnet), tb (testnet), bcrt (regtest).
    """
    import hashlib

    from backend.did import segwit_addr

    try:
        witness_bytes = bytes.fromhex(witness_script_hex)
    except ValueError as exc:
        raise ValueError(f"invalid witness script hex: {exc}") from exc

    if not witness_bytes:
        raise ValueError("witness script is empty")

    sha256_hash = hashlib.sha256(witness_bytes).digest()
    if len(sha256_hash) != 32:
        raise ValueError("P2WSH requires a 32-byte SHA256 hash")

    hrp = {"mainnet": "bc", "testnet": "tb", "regtest": "bcrt"}.get(network)
    if hrp is None:
        raise ValueError(f"unknown network: {network!r}")

    return segwit_addr.encode(hrp, 0, sha256_hash)

def wif_to_private_key(wif_key: str) -> bytes:
    """Extract the 32-byte private key from a Wallet Import Format string."""
    decoded = base58.b58decode_check(wif_key)
    if len(decoded) == 34:  # compressed key
        return decoded[1:-1]
    if len(decoded) == 33:  # uncompressed key
        return decoded[1:]
    raise ValueError("invalid WIF key")