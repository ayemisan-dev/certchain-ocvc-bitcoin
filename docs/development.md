# Development Guide (macOS)

This guide walks through setting up CertChain-OCVC from scratch on macOS (Apple Silicon).

## 1. Prerequisites

```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install system dependencies
brew install python@3.12 bitcoin ipfs 
```

## 2. Project Setup

```bash 
git clone https://github.com/ayemisan-dev/certchain-ocvc-bitcoin.git
cd certchain-ocvc-bitcoin

# Create a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install the project in editable mode
pip install --upgrade pip
pip install -e ".[dev]"
```

## 3. Bitcoin Regtest Node

```bash
mkdir -p ~/bitcoin-data

cat > ~/bitcoin-data/bitcoin.conf << 'EOF'
server=1
txindex=1
rpcuser=<your-username> 
rpcpassword=<your-password> 
fallbackfee=0.0002
[regtest]
regtest=1
rpcport=8332
rpcallowip=127.0.0.1
EOF

bitcoind -datadir=$HOME/bitcoin-data -daemon
bitcoin-cli -datadir=$HOME/bitcoin-data createwallet "certwallet"

# Generate 101 blocks to activate the chain and get spendable coins
ADDR=$(bitcoin-cli -datadir=$HOME/bitcoin-data getnewaddress "" legacy)
bitcoin-cli -datadir=$HOME/bitcoin-data generatetoaddress 101 "$ADDR"
```

## 4. IPFS Node (or Filebase)

### Local IPFS

```bash
ipfs init
ipfs daemon --offline
```

### Filebase (alternative)

1. Sign up at [filebase.com](https://console.filebase.com/).
2. Create an IPFS bucket and get the RPC token.
3. In `.env`, set:

```text 
IPFS_BACKEND=filebase
FILEBASE_IPFS_RPC_URL=https://rpc.filebase.io
FILEBASE_IPFS_RPC_TOKEN=<your-token>
```

## 5. Environment Configuration

```bash
cp .env.example .env
# Edit .env to match your local setup (especially BITCOIN_RPC_PASSWORD)
```

## 6. Start Services

```bash
# Terminal 1: Bitcoin indexer (also runs a Flask API on port 5000)
python -m indexer.main --mode both

# Terminal 2: Backend API (port 8000)
python -m backend.main
```

## 7. Verify Installation

```bash
# Health check: backend is up
curl http://127.0.0.1:8000/

# Health check: indexer is up
curl http://127.0.0.1:5000/get_tx_spending/0000000000000000000000000000000000000000000000000000000000000000/0

# Health check: IPFS is up
curl -X POST http://127.0.0.1:5001/api/v0/version
```

## 8. Run the Test Suite

```bash
# Unit tests (fast, no external dependencies)
pytest tests/unit -v

# Integration tests (requires regtest + indexer + IPFS)
pytest tests/integration --regtest -v
```

---