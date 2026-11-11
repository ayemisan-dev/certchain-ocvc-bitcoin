"""Domain exceptions for CertiChain.

All business errors must derive from ``CertiChainError`` so that
``backend.api.routes`` can translate them to HTTP responses in one place.
"""


class CertiChainError(Exception):
    """Base class for all CertiChain domain errors."""


class ConfigurationError(CertiChainError):
    """Raised when a required configuration value is missing or invalid."""


class BitcoinRPCError(CertiChainError):
    """Raised when Bitcoin Core RPC returns an error or cannot be reached."""


class TransactionBroadcastError(BitcoinRPCError):
    """Raised when ``sendrawtransaction`` fails (rejected, insufficient fee, etc.)."""


class TransactionNotConfirmedError(BitcoinRPCError):
    """Raised when a transaction is broadcast but not yet mined."""


class IPFSError(CertiChainError):
    """Raised when the configured IPFS backend fails."""


class IPFSBackendUnavailableError(IPFSError):
    """Raised when the IPFS backend is not reachable."""


class IndexerUnavailableError(CertiChainError):
    """Raised when ``bc_index`` is unreachable.

    Callers in ``services/verification`` MUST catch this and degrade the
    verification result to ``verification_status="invalid"`` instead of
    crashing.
    """


class CertificateInvalidError(CertiChainError):
    """Raised when a credential fingerprint is structurally invalid."""


class MerkleProofError(CertiChainError):
    """Raised when a Merkle proof does not reconstruct the on-chain root."""


class IssuerKeyError(CertiChainError):
    """Raised when the issuer public key is not valid at issuance time."""


class CredentialRevokedError(CertiChainError):
    """Raised when a credential is found in the revocation list."""

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason
        super().__init__(f"credential revoked: {reason}" if reason else "credential revoked")