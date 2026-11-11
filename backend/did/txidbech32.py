"""TxRef (Bech32-encoded transaction reference) for did:btcr identifiers.

Reference: https://github.com/WebOfTrustInfo/txref-conversion-python
"""

from __future__ import annotations

from backend.core.config import BitcoinNetwork
from backend.did import segwit_addr

MAGIC_BTC_MAINNET = 0x03
MAGIC_BTC_TESTNET = 0x06

HRP_MAINNET = "tx"
HRP_TESTNET = "txtest"


def _chain_params(network: BitcoinNetwork) -> tuple[int, str, bool]:
    """Return (magic, hrp, non_standard) for the given network."""
    if network is BitcoinNetwork.MAINNET:
        return MAGIC_BTC_MAINNET, HRP_MAINNET, False
    # regtest and testnet share the same txref encoding.
    return MAGIC_BTC_TESTNET, HRP_TESTNET, True


def txref_encode(network: BitcoinNetwork, block_height: int, tx_pos: int) -> str | None:
    """Encode a (block_height, tx_pos) pair as a Bech32 txref string."""
    magic, prefix, non_standard = _chain_params(network)

    short_id = [0x00] * (10 if non_standard else 8)

    if non_standard:
        if block_height <= 0x1FFFFF and tx_pos <= 0x1FFF and magic <= 0x1F:
            short_form = True
        elif block_height <= 0x3FFFFFF and tx_pos <= 0x3FFFF and magic <= 0x1F:
            short_form = False
        else:
            return None
    else:
        if block_height > 0x1FFFFF or tx_pos > 0x1FFF or magic > 0x1F:
            return None
        short_form = True

    short_id[0] = magic
    short_id[1] &= ~(1 << 0)
    short_id[1] |= (block_height & 0xF) << 1
    short_id[2] |= (block_height & 0x1F0) >> 4
    short_id[3] |= (block_height & 0x3E00) >> 9
    short_id[4] |= (block_height & 0x7C000) >> 14

    if non_standard and not short_form:
        short_id[5] |= (block_height & 0xF80000) >> 19
        short_id[6] |= (block_height & 0x3000000) >> 24
        short_id[6] |= (tx_pos & 0x7) << 2
        short_id[7] |= (tx_pos & 0xF8) >> 3
        short_id[8] |= (tx_pos & 0x1F00) >> 8
        short_id[9] |= (tx_pos & 0x3E000) >> 13
    else:
        short_id[5] |= (block_height & 0x180000) >> 19
        short_id[5] |= (tx_pos & 0x7) << 2
        short_id[6] |= (tx_pos & 0xF8) >> 3
        short_id[7] |= (tx_pos & 0x1F00) >> 8

    result = segwit_addr.bech32_encode(prefix, short_id)
    break_index = len(prefix) + 1
    return (
        result[:break_index]
        + "-"
        + result[break_index : break_index + 4]
        + "-"
        + result[break_index + 4 : break_index + 8]
        + "-"
        + result[break_index + 8 : break_index + 12]
        + "-"
        + result[break_index + 12 :]
    )


def txref_decode(bech32_tx: str) -> tuple[int, int, str]:
    """Decode a txref string into ``(block_height, tx_pos, chain)``.

    Regtest/testnet txrefs may use either short form (8 bytes) or extended
    form (10 bytes). We try both interpretations and pick the plausible one.
    """
    stripped = bech32_tx.replace("-", "")
    hrp, data = segwit_addr.bech32_decode(stripped)
    if data is None or len(data) < 8:
        raise ValueError(f"invalid txref: {bech32_tx}")

    magic = data[0]
    chain = "mainnet" if magic == MAGIC_BTC_MAINNET else "testnet"
    non_standard = chain != "mainnet"

    b_start = (data[1] >> 1) | (data[2] << 4) | (data[3] << 9) | (data[4] << 14)

    # Short form: 21-bit height, 13-bit position
    short_height = b_start | ((data[5] & 0x03) << 19)
    short_pos = ((data[5] & 0x1C) >> 2) | (data[6] << 3) | (data[7] << 8)

    if not non_standard:
        # Mainnet only supports short form.
        return short_height, short_pos, chain

    # Regtest/testnet: extended form needs >= 10 data words.
    if len(data) < 10:
        return short_height, short_pos, chain

    ext_height = b_start | (data[5] << 19) | ((data[6] & 0x03) << 24)
    ext_pos = (
        ((data[6] & 0x1C) >> 2)
        | (data[7] << 3)
        | (data[8] << 8)
        | (data[9] << 13)
    )

    # Heuristic:
    # - Extended form encodes heights > 0x1FFFFF. If the extended height
    #   exceeds 0x1FFFFF *and* the short form is a valid alternative, the
    #   encoder likely used short form (typical for small regtest chains).
    # - Otherwise use the extended interpretation.
    if ext_height > 0x1FFFFF and short_height <= 0x1FFFFF:
        return short_height, short_pos, chain
    return ext_height, ext_pos, chain


def txid_to_bech32(txid: str, rpc_client, network: BitcoinNetwork) -> str:
    """Look up the block height / position of ``txid`` and encode as txref.

    Raises:
        TransactionNotConfirmedError: if the transaction has no ``blockhash``
            (i.e., it is still in the mempool).
    """
    from backend.core.errors import TransactionNotConfirmedError

    if network is BitcoinNetwork.REGTEST:
        tx = rpc_client.gettransaction(txid)
    else:
        tx = rpc_client.getrawtransaction(txid, True)

    block_hash = tx.get("blockhash")
    if not block_hash:
        raise TransactionNotConfirmedError(
            f"transaction {txid} is not yet mined; wait for 1 confirmation"
        )

    block = rpc_client.getblock(block_hash)
    block_height = block["height"]
    tx_pos = block["tx"].index(txid)

    encoded = txref_encode(network, block_height, tx_pos)
    if encoded is None:
        raise ValueError(f"txref encoding failed for txid={txid}")
    return encoded


def bech32_to_txid(bech32_tx: str, rpc_client) -> str:
    """Decode a txref and look up the corresponding txid."""
    block_height, tx_pos, _chain = txref_decode(bech32_tx)
    block_hash = rpc_client.getblockhash(block_height)
    block = rpc_client.getblock(block_hash)
    return block["tx"][tx_pos]