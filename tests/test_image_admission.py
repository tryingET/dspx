# summary: "Canonical admission bytes are immutable identity, not caller-selected digests."
import pytest

from dspx.image_admission import ImageAdmission, ImageContractError, canonical, digest


def test_admission_record_is_a_detached_view():
    raw = canonical({"limits": {"max_source_images": 1}})
    admission = ImageAdmission(
        raw, digest("admission-v2", {"limits": {"max_source_images": 1}})
    )
    admission.record["limits"]["max_source_images"] = 6
    assert admission.record["limits"]["max_source_images"] == 1


@pytest.mark.parametrize("raw", [b'{"x":1}', b'{ "x":1}', b'{"x":1,"x":2}', b"{}"])
def test_admission_rejects_forged_or_noncanonical_identity(raw):
    with pytest.raises(ImageContractError):
        ImageAdmission(raw, "0" * 64)


def test_admission_rejects_noncanonical_bytes_with_matching_semantic_digest():
    with pytest.raises(ImageContractError):
        ImageAdmission(b'{ "x":1}', digest("admission-v2", {"x": 1}))
