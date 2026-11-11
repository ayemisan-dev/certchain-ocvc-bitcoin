"""JSON-LD helpers: context loading, VC decomposition, rendering, and framing."""

from __future__ import annotations

import json
from pathlib import Path

import jcs
from pyld import jsonld
from typing import Any

_CONTEXT_DIR = Path(__file__).resolve().parent.parent / "data" / "context"

# Cache contexts so we don't read the same file on every call.
_CONTEXT_CACHE: dict[str, dict] = {}

_CONTEXT_FILES = {
    "https://www.w3.org/2018/credentials/v1": "credentials_v1.json",
    "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.2.json": "imsglobal.json",
    "https://w3id.org/vc-revocation-list-2020/v1": "revocation_list_v1.json",
}


def _load_context(url: str) -> dict:
    if url not in _CONTEXT_CACHE:
        filename = _CONTEXT_FILES.get(url)
        if filename is None:
            raise ValueError(f"unknown JSON-LD context URL: {url}")
        path = _CONTEXT_DIR / filename
        if not path.exists():
            raise FileNotFoundError(
                f"JSON-LD context file not found: {path}. "
                f"Please copy the context files into {_CONTEXT_DIR}."
            )
        with path.open("r", encoding="utf-8") as fh:
            _CONTEXT_CACHE[url] = json.load(fh)
    return _CONTEXT_CACHE[url]

_default_loader = jsonld.get_document_loader()

def _custom_loader(url: str, options=None) -> dict:
    """Serve local contexts without network access."""
    if url in _CONTEXT_FILES:
        return {
            "contextUrl": None,
            "document": _load_context(url),
            "documentUrl": url,
        }

    return _default_loader(url, options)

# Register the loader at import time.
jsonld.set_document_loader(_custom_loader)


# ---------------------------------------------------------------------------
# Decomposition
# ---------------------------------------------------------------------------

def decompose_vc(full_vc: dict, vc_template: dict, vtype: str):
    """Decompose ``full_vc`` according to ``vc_template``.

    ``vtype`` is ``"array"`` for common values (vi) or ``"object"`` for
    credential-specific values (vd).
    """

    def _walk(full_node, template_node):
        # Guard: template_node must be a dict. An empty-array placeholder
        # ([]) that doesn't match vtype is not expanded element-wise.
        if not isinstance(template_node, dict):
            return []

        result: list = []
        for key, temp_val in template_node.items():
            full_val = full_node.get(key)

            temp_type = None
            temp_len = 0
            if isinstance(temp_val, (list, dict)):
                temp_type = "array" if isinstance(temp_val, list) else "object"
                temp_len = len(temp_val)

            # Skip simple values and non-empty arrays.
            if temp_type != "object" and not (temp_type == "array" and temp_len == 0):
                continue

            # Leaf placeholder: empty [] or {} of the requested type.
            if temp_len == 0 and temp_type == vtype:
                result.append(full_val)
                continue

            # Non-empty object: recurse.
            if isinstance(full_val, dict):
                sub = _walk(full_val, temp_val)
                if sub:
                    result.append([sub])
            elif isinstance(full_val, list):
                # Only recurse element-wise when the template node is a dict
                # (i.e., a non-empty object). An empty-array placeholder that
                # did NOT match vtype has nothing to extract.
                if not isinstance(temp_val, dict):
                    continue
                for i, item in enumerate(full_val):
                    sub = _walk(item, temp_val)
                    if sub:
                        if i >= 1 and result:
                            result[-1] = result[-1] + [sub]
                        else:
                            result.append([sub])

        return result

    return _walk(full_vc, vc_template)


# ---------------------------------------------------------------------------
# Rendering (Algorithm 2 from the thesis)
# ---------------------------------------------------------------------------

def render_obj(obj: dict, values: list, vtype: str):
    """Render ``obj`` in-place using ``values``. Returns ``(obj, index)``."""
    i = -1
    for key in list(obj.keys()):
        val = obj[key]

        if isinstance(val, (list, dict)):
            val_type = "array" if isinstance(val, list) else "object"
            val_len = len(val)
        else:
            val_type = type(val).__name__
            val_len = len(str(val))

        if val_type != "object" and not (val_type == "array" and val_len == 0):
            continue

        if val_len == 0 and val_type == vtype:
            i += 1
            if i < len(values):
                obj[key] = values[i]
        elif len(values) > i + 1:
            if isinstance(values[i + 1], list) and isinstance(values[i + 1][0], list):
                i += 1
                items = []
                for item_values in values[i]:
                    obj_copy = json.loads(json.dumps(val))
                    rendered, child_index = render_obj(obj_copy, item_values, vtype)
                    if child_index == -1:
                        i -= 1
                        break
                    items.append(rendered)
                if len(items) == 1:
                    obj[key] = items[0]
                elif len(items) > 1:
                    obj[key] = items
    return obj, i


def render_common_vc(vc_spec: list, vd: list, vi: list | None = None) -> dict:
    """Render a full VC from ``vc_spec[1]`` (template), ``vd``, and ``vi``."""
    template = json.loads(json.dumps(vc_spec[1]))  # deep copy
    if vi is not None:
        render_obj(template, vi, "array")
    render_obj(template, vd, "object")
    return template


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------

def jsonld_frame(
    rendered_vc: dict[str, Any],
    external_obj: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply JSON-LD framing so that linked data is embedded inline."""

    context = rendered_vc["@context"]

    frame = {
        "@context": context,
        "@embed": "@always",
        "@id": rendered_vc["id"],
    }

    result = jsonld.frame(
        [rendered_vc, *external_obj],
        frame,
        options={"base": " "},
    )

    if not isinstance(result, dict):
        raise TypeError(
            f"Expected JSON-LD framing result to be a dict, "
            f"got {type(result).__name__}"
        )

    return result


# ---------------------------------------------------------------------------
# Normalisation (kept for completeness; not used by the verification flow)
# ---------------------------------------------------------------------------

def jcs_normalize(data: dict) -> dict:
    """JCS-canonicalise a JSON object."""
    canonical = jcs.canonicalize(data)
    if isinstance(canonical, bytes):
        canonical = canonical.decode("utf-8")
    return json.loads(canonical)

