"""Unit tests for encoding/jsonld.py (decompose + render)."""

from __future__ import annotations
from backend.encoding.jsonld import decompose_vc, render_common_vc


def test_decompose_produces_non_empty_vi_vd(full_bsc_vc, bsc_vc_spec):
    template = bsc_vc_spec[1]
    vi = decompose_vc(full_bsc_vc, template, vtype="array")
    vd = decompose_vc(full_bsc_vc, template, vtype="object")

    assert isinstance(vi, list) and len(vi) > 0, "vi should not be empty"
    assert isinstance(vd, list) and len(vd) > 0, "vd should not be empty"


def test_decompose_render_roundtrip(full_bsc_vc, bsc_vc_spec):
    """decompose(full) -> render(vi, vd) must reproduce business fields."""
    template = bsc_vc_spec[1]
    vi = decompose_vc(full_bsc_vc, template, vtype="array")
    vd = decompose_vc(full_bsc_vc, template, vtype="object")

    rendered = render_common_vc(bsc_vc_spec, vd, vi)

    # --- Assertions on business fields that MUST survive the round-trip ---
    assert rendered["id"] == full_bsc_vc["id"]
    assert rendered["dateIssued"] == full_bsc_vc["dateIssued"]
    assert rendered["issuer"]["id"] == full_bsc_vc["issuer"]["id"]
    assert (
        rendered["credentialStatus"]["issuer"]
        == full_bsc_vc["credentialStatus"]["issuer"]
    )
    assert (
        rendered["credentialStatus"]["revocationListIndex"]
        == full_bsc_vc["credentialStatus"]["revocationListIndex"]
    )

    rs = rendered["credentialSubject"]
    fs = full_bsc_vc["credentialSubject"]
    assert rs["givenName"] == fs["givenName"]
    assert rs["familyName"] == fs["familyName"]
    assert rs["studentId"] == fs["studentId"]
    assert rs["achievement"]["GPA"] == fs["achievement"]["GPA"]
    assert (
        rs["achievement"]["dateofAdmission"]
        == fs["achievement"]["dateofAdmission"]
    )


def test_decompose_render_preserves_transcript(full_bsc_vc, bsc_vc_spec):
    """Transcript (list of semesters) must survive intact."""
    template = bsc_vc_spec[1]
    vi = decompose_vc(full_bsc_vc, template, vtype="array")
    vd = decompose_vc(full_bsc_vc, template, vtype="object")
    rendered = render_common_vc(bsc_vc_spec, vd, vi)

    rendered_transcript = rendered["credentialSubject"]["transcriptRecord"]
    original_transcript = full_bsc_vc["credentialSubject"]["transcriptRecord"]

    assert len(rendered_transcript) == len(original_transcript)
    for r_sem, o_sem in zip(rendered_transcript, original_transcript):
        assert r_sem["semester"] == o_sem["semester"]
        assert r_sem["GPA"] == o_sem["GPA"]
        assert r_sem["GPS"] == o_sem["GPS"]
        assert len(r_sem["enrollmentRecord"]) == len(o_sem["enrollmentRecord"])


def test_decompose_vi_vd_are_independent(full_bsc_vc, bsc_vc_spec):
    """vi (common values) and vd (specific values) must not overlap."""
    template = bsc_vc_spec[1]
    vi = decompose_vc(full_bsc_vc, template, vtype="array")
    vd = decompose_vc(full_bsc_vc, template, vtype="object")

    # vi should contain issuer-related values, vd should contain
    # credential-specific values (id, dateIssued, student data).
    vi_str = str(vi)
    vd_str = str(vd)

    # Issuer DID appears in vi, not vd.
    issuer_did = full_bsc_vc["issuer"]["id"]
    assert issuer_did in vi_str
    assert issuer_did not in vd_str

    # Credential ID appears in vd, not vi.
    cred_id = full_bsc_vc["id"]
    assert cred_id in vd_str
    assert cred_id not in vi_str


def test_decompose_render_deterministic(full_bsc_vc, bsc_vc_spec):
    """Same input must produce identical output on every run."""
    template = bsc_vc_spec[1]
    vi1 = decompose_vc(full_bsc_vc, template, vtype="array")
    vd1 = decompose_vc(full_bsc_vc, template, vtype="object")
    vi2 = decompose_vc(full_bsc_vc, template, vtype="array")
    vd2 = decompose_vc(full_bsc_vc, template, vtype="object")

    assert vi1 == vi2
    assert vd1 == vd2