# Test Suite
## Running tests
### Unit tests (no external dependencies)

```bash
pytest tests/unit -v
```

Runs in seconds, no Bitcoin / IPFS needed.

---
### Integration tests (requires regtest + bc_index + IPFS)

```bash
# Terminal 1
bitcoind -datadir=$HOME/bitcoin-data -daemon

# Terminal 2
python -m indexer.main --mode both

# Terminal 3
ipfs daemon --offline

# Terminal 4
pytest tests/integration --regtest -v
```

Integration tests will `skip` if any dependency is unreachable.

---
### Full suite

```bash 
pytest
```

Unit tests always run; integration tests are skipped unless `--regtest`.

---
## Coverage

```bash 
pytest --cov=backend --cov=indexer --cov-report=term-missing
```

---
