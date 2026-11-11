"""Credential verification and revocation checking.

This is the only public entry point for verifying an OCVC credential. It
orchestrates: fingerprint decoding, on-chain data reading, VC rendering,
issuer key verification, and revocation checking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.core.errors import (
    CertificateInvalidError,
    IndexerUnavailableError,
    MerkleProofError,
)
from backend.core.logging import get_logger
from backend.core.utils import iso_to_timestamp
from backend.did.document import check_key_exists
from backend.did.resolver import resolve_did_url
from backend.encoding.bitstr import decoded_bitstr_reason, is_revoke
from backend.encoding.cbor_multibase import vc_fp_decode
from backend.encoding.jsonld import jsonld_frame, render_common_vc
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.infra.indexer.client import IndexerClient
from backend.infra.ipfs.base import IPFSBackend
from backend.models.credential import CredentialStatus, extract_credential_status
from backend.models.result import VerificationResult
from backend.services import onchain_reader
from backend.models.fingerprint import (
    FingerprintHeader,
    FingerprintProof,
    VCFingerprint,
    fingerprint_type_is_ocvc,
)


logger = get_logger(__name__)


def verify_credential(
    encoded_fp: str,
    rpc_client: BitcoinRPCClient,
    indexer_client: IndexerClient,
    ipfs_backend: IPFSBackend,
) -> VerificationResult:
    """Verify a credential fingerprint end-to-end.

    Returns a ``VerificationResult`` with ``status`` in {valid, revoked, invalid}.
    """
    # --- Step 1: decode fingerprint ---
    try:
        header, payload, proof = vc_fp_decode(encoded_fp)
    except Exception as exc:
        return VerificationResult.invalid(f"malformed fingerprint: {exc}")

    try:
        fingerprint = VCFingerprint(
            header=FingerprintHeader.model_validate(header),
            payload=payload,
            proof=FingerprintProof.model_validate(proof),
        )
    except Exception as exc:
        return VerificationResult.invalid(f"invalid fingerprint structure: {exc}")

    if not fingerprint_type_is_ocvc(fingerprint):
        return VerificationResult.invalid(
            f"unsupported fingerprint type: {fingerprint.header.typ}"
        )

    # --- Step 2: read PD transaction and verify Merkle root ---
    try:
        is_valid, prev_txid, t_tx, issuer_pubkey, vd, sequence = onchain_reader.bc_get_pd(
            rpc_client, payload, fingerprint.proof.tid, fingerprint.proof.pth
        )
    except MerkleProofError as exc:
        return VerificationResult.invalid(str(exc))
    except Exception as exc:
        return VerificationResult.invalid(f"failed to read PD transaction: {exc}")

    if not is_valid or vd is None:
        return VerificationResult.invalid("PD transaction invalid (Merkle root mismatch)")
    if issuer_pubkey is None:
        return VerificationResult.invalid("issuer public key missing from PD input")
    if prev_txid is None:
        return VerificationResult.invalid("PD transaction has no previous txid")

    # --- Step 3: walk back to PI ---
    try:
        pi_txid = onchain_reader.backward_traversal_pi_index(rpc_client, sequence, prev_txid)
    except Exception as exc:
        return VerificationResult.invalid(f"failed to traverse to PI: {exc}")
    if pi_txid is None:
        return VerificationResult.invalid("PI transaction not found")

    # --- Step 4: read PI (vi + PS txid) ---
    try:
        pi_valid, ps_txid, vi = onchain_reader.bc_get_pi(rpc_client, pi_txid)
    except Exception as exc:
        return VerificationResult.invalid(f"failed to read PI transaction: {exc}")
    if not pi_valid or ps_txid is None or vi is None:
        return VerificationResult.invalid("PI transaction invalid")

    # --- Step 5: read PS (VC template) ---
    try:
        ps_valid, vc_template = onchain_reader.bc_get_ps(rpc_client, ps_txid)
    except Exception as exc:
        return VerificationResult.invalid(f"failed to read PS transaction: {exc}")
    if not ps_valid or vc_template is None:
        return VerificationResult.invalid("PS transaction invalid")

    # --- Step 6: render VC ---
    try:
        rendered = render_common_vc(vc_template, vd, vi)
    except Exception as exc:
        return VerificationResult.invalid(f"failed to render VC: {exc}")

    if not isinstance(rendered, dict):
        return VerificationResult.invalid("rendered VC is not a dict")

    # --- Step 7: verify issuer key at issuance time ---
    try:
        issuer_block = rendered.get("issuer")
        issuer_id = (
            issuer_block.get("id") if isinstance(issuer_block, dict) else issuer_block
        )
        if not issuer_id:
            return VerificationResult.invalid("VC has no issuer id")

        did_doc = resolve_did_url(
            rpc_client, indexer_client, ipfs_backend, f"{issuer_id}?versionTime={t_tx}"
        )
        if did_doc is None:
            return VerificationResult.invalid("issuer DID document not found")

        key_exists, _ = check_key_exists(did_doc, issuer_pubkey)
        if not key_exists:
            return VerificationResult.invalid(
                "issuer public key is not valid at issuance time"
            )
    except IndexerUnavailableError as exc:
        return VerificationResult.invalid(f"cannot resolve DID (indexer unavailable): {exc}")
    except Exception as exc:
        return VerificationResult.invalid(f"failed to verify issuer key: {exc}")

        # --- Step 8: check revocation ---
    try:
        revoked, reason = check_revocation(
            rendered, rpc_client, indexer_client, ipfs_backend, t_tx
        )
    except IndexerUnavailableError as exc:
        return VerificationResult.invalid(
            f"revocation status unknown (indexer unavailable): {exc}"
        )
    except Exception as exc:
        return VerificationResult.invalid(f"failed to check revocation: {exc}")

    # --- Step 9: JSON-LD framing (applies to both valid and revoked) ---
    try:
        rendered = jsonld_frame(rendered, [rendered.get("Course", [])])
    except Exception as exc:
        logger.warning("JSON-LD framing failed (returning unframed VC): %s", exc)

    if revoked:
        return VerificationResult.revoked(rendered, reason)

    return VerificationResult.valid(rendered)


# ---------------------------------------------------------------------------
# Revocation checking (independent, testable)
# ---------------------------------------------------------------------------

def check_revocation(
    credential: dict,
    rpc_client: BitcoinRPCClient,
    indexer_client: IndexerClient,
    ipfs_backend: IPFSBackend,
    t_issued: int,
) -> tuple[bool, str | None]:
    """Check whether ``credential`` is revoked.

    Returns ``(revoked, reason)``. Raises ``IndexerUnavailableError`` when
    the indexer is unreachable — callers MUST treat this as "unknown".
    """
    try:
        status = extract_credential_status(credential)
    except Exception as exc:
        raise CertificateInvalidError(f"invalid credentialStatus: {exc}") from exc

    out_txids = indexer_client.get_addr_out_txs(status.revocation_list_address.val)
    if not out_txids:
        return False, None

    # Filter to PD transactions only.
    pd_txids: list[str] = []
    for txid in out_txids:
        try:
            _, _, tx_type, _ = onchain_reader.bc_read(rpc_client, txid)
        except Exception:
            continue
        if tx_type == "PD":
            pd_txids.append(txid)

    if not pd_txids:
        return False, None

    vd_list, pi_txid, error = _find_latest_revocation_chain(
        rpc_client, indexer_client, ipfs_backend, status, pd_txids, t_issued
    )
    if error is not None:
        raise CertificateInvalidError(
            f"revocation PD invalid for address {status.revocation_list_address.val}: {error}"
        )
    if not vd_list or pi_txid is None:
        raise CertificateInvalidError(
            "revocation PD found but could not reconstruct the revocation list"
        )

    pi_valid, ps_txid, vi = onchain_reader.bc_get_pi(rpc_client, pi_txid)
    if not pi_valid or ps_txid is None or vi is None:
        raise CertificateInvalidError("revocation PI invalid")

    ps_valid, cs = onchain_reader.bc_get_ps(rpc_client, ps_txid)
    if not ps_valid or cs is None:
        raise CertificateInvalidError("revocation PS invalid")

    for vd in vd_list:
        try:
            rev_vc = render_common_vc(cs, vd, vi)
        except Exception:
            continue
        if not isinstance(rev_vc, dict):
            continue
        issuer_block = rev_vc.get("issuer")
        issuer_id = (
            issuer_block.get("id") if isinstance(issuer_block, dict) else issuer_block
        )
        if issuer_id != status.issuer:
            continue
        cred_subject = rev_vc.get("credentialSubject", {})
        if not isinstance(cred_subject, dict):
            continue
        revoked, reason = _is_revoked(
            cred_subject, status.individual_index, status.group_index
        )
        if revoked:
            return True, reason

    return False, None


def _find_latest_revocation_chain(
    rpc_client: BitcoinRPCClient,
    indexer_client: IndexerClient,
    ipfs_backend: IPFSBackend,
    status: CredentialStatus,
    pd_txids: list[str],
    t_issued: int,
) -> tuple[list, str | None, str | None]:
    """Locate the latest valid revocation PD and its vd list.

    Returns ``(vd_list, pi_txid, error)``:
    - ``([], None, None)``: no usable PD
    - ``(vd_list, pi_txid, None)``: valid PD(s) found
    - ``([], None, "reason")``: PD exists but is invalid
    """
    vd_list: list = []
    sequence = 0
    prev_txid: str | None = None
    last_error: str | None = None

    for txid in reversed(pd_txids):
        try:
            is_valid, prev, t_tx, k_pub, vd, seq = onchain_reader.bc_get_pd(
                rpc_client, [], txid, None
            )
        except Exception as exc:
            last_error = f"failed to read PD {txid}: {exc}"
            logger.warning(last_error)
            continue

        if not is_valid or vd is None or prev is None:
            last_error = f"PD {txid} failed validation (data_type/encoding mismatch)"
            logger.warning(last_error)
            continue

        now = int(datetime.now(timezone.utc).timestamp())
        key_ok, updated_at, _ = _check_signing_key(
            rpc_client, indexer_client, ipfs_backend, status.issuer, k_pub, now
        )
        if not key_ok:
            last_error = f"PD {txid}: signing key {k_pub} not in revocation DID"
            logger.warning(last_error)
            continue

        if updated_at is None or updated_at <= t_tx:
            vd_list.append(vd)
            sequence = seq
            prev_txid = prev
            break
        last_error = f"PD {txid}: issued after signing key update"

    if not vd_list:
        return [], None, last_error

    if status.revocation_mode == "SingleSnapshot" and sequence > 1 and prev_txid:
        vd_list, sequence, prev_txid = _collect_all_pd(
            rpc_client, prev_txid, sequence, vd_list, t_issued
        )

    if sequence == 1:
        pi_txid = prev_txid
    else:
        pi_txid = (
            onchain_reader.backward_traversal_pi_index(rpc_client, sequence, prev_txid)
            if prev_txid
            else None
        )

    return vd_list, pi_txid, None


def _check_signing_key(
    rpc_client: BitcoinRPCClient,
    indexer_client: IndexerClient,
    ipfs_backend: IPFSBackend,
    did: str,
    public_key: str | None,
    now: int,
) -> tuple[bool, int | None, str | None]:
    """Return ``(key_exists, updated_at, public_key)`` for the DID's latest version."""
    if public_key is None:
        return False, None, None
    try:
        did_doc = resolve_did_url(
            rpc_client, indexer_client, ipfs_backend, f"{did}?versionTime={now}"
        )
    except Exception:
        return False, None, None
    if not did_doc:
        return False, None, None

    key_exists, _ = check_key_exists(did_doc, public_key)
    if not key_exists:
        return False, None, None

    updated = did_doc.get("didDocumentMetadata", {}).get("updated")
    updated_at = iso_to_timestamp(updated) if updated else None
    return True, updated_at, public_key


def _collect_all_pd(
    rpc_client: BitcoinRPCClient,
    prev_txid: str,
    sequence: int,
    vd_list: list,
    t_exp: int | None,
) -> tuple[list, int, str | None]:
    """Traverse back through the PD chain, collecting vd values."""
    while sequence > 1:
        try:
            is_valid, prev, t_tx, _, vd, seq = onchain_reader.bc_get_pd(
                rpc_client, [], prev_txid, None
            )
        except Exception:
            break
        if not is_valid or vd is None or prev is None:
            break
        vd_list.append(vd)
        prev_txid = prev
        sequence = seq
        if t_exp is not None and t_tx > t_exp:
            break
    return vd_list, sequence, prev_txid


def _is_revoked(
    cred_subject: dict, individual_index: int, group_index: int
) -> tuple[bool, str | None]:
    """Check the rendered revocation VC's credentialSubject for a match."""
    encoding_method = (cred_subject.get("type") or [""])[0]
    revocation_list = cred_subject.get("revocationList")
    prev_list = cred_subject.get("previousList")
    rev_reason = cred_subject.get("reason") or 0
    prev_reason = cred_subject.get("previousListReason") or 0
    reason_desc = cred_subject.get("reasonDescription") or []
    rev_param = cred_subject.get("revocationListParam") or [0, 1]
    bit_per_cred = rev_param[1] if len(rev_param) > 1 else 1

    if encoding_method == "OCVCRevListBts": # bitstring 
        m = rev_param[0] if rev_param else 32
        bit_len = cred_subject.get("bitLength") or 0
        if revocation_list:
            revoke_list, revoked = is_revoke(individual_index, m, revocation_list, bit_len)
            if not revoked:
                revoke_list, revoked = is_revoke(group_index, m, revocation_list, bit_len)
            if revoked:
                return True, decoded_bitstr_reason(
                    individual_index, revoke_list, rev_reason, bit_per_cred, reason_desc
                )
        elif prev_list:
            revoke_list, revoked = is_revoke(individual_index, m, prev_list, bit_len)
            if not revoked:
                revoke_list, revoked = is_revoke(group_index, m, prev_list, bit_len)
            if revoked:
                return True, decoded_bitstr_reason(
                    individual_index, revoke_list, prev_reason, bit_per_cred, reason_desc
                )
    else:  # indexList
        if revocation_list and (
            individual_index in revocation_list or group_index in revocation_list
        ):
            return True, decoded_bitstr_reason(
                individual_index, revocation_list, rev_reason, bit_per_cred, reason_desc
            )
        if prev_list and (individual_index in prev_list or group_index in prev_list):
            return True, decoded_bitstr_reason(
                individual_index, prev_list, prev_reason, bit_per_cred, reason_desc
            )

    return False, None