# Test Fixtures

This directory holds static JSON/text fixtures shared by unit tests.

| File                | Source                                        | Purpose                                                  |
| ------------------- | --------------------------------------------- | -------------------------------------------------------- |
| `full_bsc_vc.json`  | `backend/data/vc/degree/base_full_vc.json`    | Complete degree VC for decomposition tests               |
| `bsc_vc_spec.json`  | `backend/data/vc/degree/bsc_vc_spec.json`     | OCVC protocol specification (desc + template + external) |
| `bsc_vd.json`       | `backend/data/vc/degree/bsc_vd.json`          | Expected `vd` array                                      |
| `bsc_vi.json`       | `backend/data/vc/degree/bsc_vi.json`          | Expected `vi` array                                      |
| `encoded_vc_fp.txt` | `backend/data/vc_fp/bsc_batch_1/vc_fp_1.json` | Encoded fingerprint for decode tests                     |

## How to populate

These files are copied from the source paths above. They are **snapshots** that should not change unless the protocol itself changes.

```bash
cp backend/data/vc/degree/base_full_vc.json tests/fixtures/full_bsc_vc.json
cp backend/data/vc/degree/bsc_vc_spec.json tests/fixtures/bsc_vc_spec.json
cp backend/data/vc/degree/bsc_vd.json tests/fixtures/bsc_vd.json
cp backend/data/vc/degree/bsc_vi.json tests/fixtures/bsc_vi.json
python3 -c "import json; print(json.load(open('backend/data/vc_fp/bsc_batch_1/vc_fp_1.json'))['encoded_vc_fp'], end='')" > tests/fixtures/encoded_vc_fp.txt
```

---

