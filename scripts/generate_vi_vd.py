"""Generate vi (common value array) from a full VC by VC decomposition.

Usage:
    python -m scripts.generate_vi_vd \
        --full-vc backend/data/vc/degree/base_full_vc.json \
        --vc-spec backend/data/vc/degree/bsc_vc_spec.json \
        --out-vi backend/data/vc/degree/bsc_vi.json \
        --out-vd backend/data/vc/degree/bsc_vd.json \
        --out-rendered example_vc/rendered_vc/bsc_vc.json
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from backend.encoding.jsonld import decompose_vc, jsonld_frame, render_common_vc


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate vi from a full VC")
    parser.add_argument("--full-vc", required=True, help="Path to full VC JSON")
    parser.add_argument("--vc-spec", required=True, help="Path to VC spec (list)")
    parser.add_argument("--out-vi", required=True, help="Output path for vi")
    parser.add_argument("--out-vd", required=True, help="Output path for vd")
    parser.add_argument("--out-rendered", help="Optional output path for rendered VC (for sanity check)")
    args = parser.parse_args()

    full_vc = _load_json(args.full_vc)
    vc_spec = _load_json(args.vc_spec)
    if not isinstance(vc_spec, list) or len(vc_spec) < 2:
        raise ValueError(f"invalid VC spec (expected [desc, template, external]): {args.vc_spec}")

    vc_template = copy.deepcopy(vc_spec[1])

    # 1. Decompose full VC -> vi (common) and vd (specific)
    vi = decompose_vc(full_vc, vc_template, vtype="array")
    vd = decompose_vc(full_vc, vc_template, vtype="object")

    vi_path = Path(args.out_vi)
    vi_path.parent.mkdir(parents=True, exist_ok=True)
    vi_path.write_text(json.dumps(vi, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"wrote vi to {vi_path}")

    vd_path = Path(args.out_vd)
    vd_path.parent.mkdir(parents=True, exist_ok=True)
    vd_path.write_text(json.dumps(vd, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"wrote vd to {vd_path}")

    # 2. Sanity check: render the full VC from vi + vd, verify it looks correct
    if args.out_rendered:
        rendered = render_common_vc(vc_spec, vd, vi)
        rendered = jsonld_frame(rendered, [rendered.get("Course", [])])
        out_path = Path(args.out_rendered)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rendered, indent=4, ensure_ascii=False), encoding="utf-8")
        print(f"wrote rendered VC to {out_path} (for sanity check)")


if __name__ == "__main__":
    main()