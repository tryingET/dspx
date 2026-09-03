# summary: "Tests the read-only Misegraph evidence package loader, the deterministic intent/inputs/binding importer (package-derived expected projection), its CLI, and an offline stub program-gen/program-run smoke."
# read_when:
#   - "You are changing program_foundry_misegraph_evidence*.py or the checked-in misegraph-evidence-package-v1 fixture."

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.program_foundry_misegraph_evidence import (
    ANSWERS_ORIGIN_OPERATOR,
    ANSWERS_ORIGIN_PACKAGE_DERIVED,
    BINDING_FILE,
    BINDING_SCHEMA_VERSION,
    DEFAULT_EXAMPLE_CASES,
    EXPECTED_PROJECTION_SCHEMA_VERSION,
    INPUTS_FILE,
    INTENT_FILE,
    PROVENANCE_FILE,
    REFERENCE_INTENT_TEMPLATE,
    MisegraphEvidenceImportError,
    build_misegraph_inputs,
    build_misegraph_intent,
    build_misegraph_source_projection,
    derive_misegraph_expected,
    load_misegraph_answers,
    write_import_bundle,
)
from dspx.services.program_quality_evaluation import (
    evaluate_declared_quality,
    normalize_quality_criteria,
)
from dspx.services.program_foundry_misegraph_evidence_package import (
    MisegraphEvidencePackageError,
    canonical_json,
    load_misegraph_evidence_package,
)
from dspx.services.program_intent import load_program_intent

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "misegraph-evidence-package-v1"
PACKAGE = FIXTURE_ROOT / "espresso-brownies"
ANSWERS = FIXTURE_ROOT / "espresso-brownies-answers.json"

# Pins from the real `misegraph evidence export examples/espresso-brownies.mise`.
PACKAGE_SHA256 = "0be06d8d561751e9be26f43ada7e0c20ee4fbc7982194c7396986add07114905"
MANIFEST_SHA256 = "5c1fd0f581e738efeaaa87a0a3007768b1f30dd0e45e5ed35a4dd6ecd6c5c5e4"
# sha256 of compact sorted JSON of the AK-5346 reference intent minus `examples`.
REFERENCE_INTENT_WITHOUT_EXAMPLES_SHA256 = (
    "58429c800e01392d29182f3acda7ff533b55189827905e5de15d2d457e81c5e6"
)

runner = CliRunner()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_package(tmp_path: Path, name: str = "pkg") -> Path:
    target = tmp_path / name
    shutil.copytree(PACKAGE, target)
    return target


def _manifest(package_dir: Path) -> dict:
    return json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(package_dir: Path, manifest: dict, *, rebind: bool = True) -> None:
    if rebind:
        unbound = {k: v for k, v in manifest.items() if k != "package_sha256"}
        manifest["package_sha256"] = _sha(canonical_json(unbound).encode("utf-8"))
    (package_dir / "manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8"
    )


def _replace_artifact(package_dir: Path, name: str, data: bytes) -> None:
    (package_dir / name).write_bytes(data)
    manifest = _manifest(package_dir)
    manifest["artifacts"][name]["sha256"] = _sha(data)
    manifest["artifacts"][name]["bytes"] = len(data)
    _write_manifest(package_dir, manifest)


def _snapshot(directory: Path) -> dict[str, tuple]:
    out = {}
    for entry in sorted(os.scandir(directory), key=lambda item: item.name):
        info = entry.stat(follow_symlinks=False)
        out[entry.name] = (info.st_size, info.st_mtime_ns, info.st_ino, info.st_mode)
    return out


def _import(tmp_path: Path, *, outdir_name: str = "out", cases=None, package=PACKAGE):
    return write_import_bundle(
        package_dir=package,
        answers_path=ANSWERS,
        outdir=tmp_path / outdir_name,
        cases=cases,
    )


# --- package loader -----------------------------------------------------------


def test_fixture_package_loads_with_pinned_hashes() -> None:
    package = load_misegraph_evidence_package(PACKAGE)
    assert package.package_sha256 == PACKAGE_SHA256
    assert package.manifest_sha256 == MANIFEST_SHA256
    assert package.dir == PACKAGE.resolve()
    assert package.manifest["recipe"] == {
        "id": "espresso_brownies",
        "title": "Espresso Brownies",
    }
    assert package.manifest["producer"]["name"] == "misegraph"
    assert [case.id for case in package.behavior_cases] == [
        "check-json",
        "convert-json",
        "render-text",
        "render-svg",
    ]
    assert package.canonical_ir_validator == "jsonschema"
    assert set(package.files) == set(package.manifest["artifacts"])
    assert package.json("check.json") == {"diagnostics": []}


def test_tampered_artifact_byte_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    target = package_dir / "render.text.txt"
    data = bytearray(target.read_bytes())
    data[0] ^= 0x01
    target.write_bytes(bytes(data))
    with pytest.raises(MisegraphEvidencePackageError, match="render.text.txt"):
        load_misegraph_evidence_package(package_dir)


def test_tampered_artifact_length_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    target = package_dir / "source.mise"
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(MisegraphEvidencePackageError, match="does not match"):
        load_misegraph_evidence_package(package_dir)


def test_missing_artifact_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    (package_dir / "check.json").unlink()
    with pytest.raises(
        MisegraphEvidencePackageError, match="missing artifact `check.json`"
    ):
        load_misegraph_evidence_package(package_dir)


@pytest.mark.parametrize("stray", ["notes.txt", ".hidden", "manifest.json.bak"])
def test_stray_file_rejected(tmp_path: Path, stray: str) -> None:
    package_dir = _copy_package(tmp_path)
    (package_dir / stray).write_text("x", encoding="utf-8")
    with pytest.raises(MisegraphEvidencePackageError, match="unexpected file"):
        load_misegraph_evidence_package(package_dir)


def test_unknown_manifest_key_rejected_even_when_rebound(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    manifest = _manifest(package_dir)
    manifest["extra"] = {"note": "not part of v1"}
    _write_manifest(package_dir, manifest)
    with pytest.raises(MisegraphEvidencePackageError, match="unknown keys: extra"):
        load_misegraph_evidence_package(package_dir)


def test_unknown_nested_key_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    manifest = _manifest(package_dir)
    manifest["artifacts"]["source.mise"]["mtime"] = 0
    _write_manifest(package_dir, manifest)
    with pytest.raises(MisegraphEvidencePackageError, match="unknown keys: mtime"):
        load_misegraph_evidence_package(package_dir)


def test_wrong_schema_version_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    manifest = _manifest(package_dir)
    manifest["schema_version"] = "misegraph-evidence-package-v2"
    _write_manifest(package_dir, manifest)
    with pytest.raises(MisegraphEvidencePackageError, match="schema_version"):
        load_misegraph_evidence_package(package_dir)


def test_wrong_package_sha256_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    manifest = _manifest(package_dir)
    manifest["package_sha256"] = "0" * 64
    _write_manifest(package_dir, manifest, rebind=False)
    with pytest.raises(MisegraphEvidencePackageError, match="package_sha256"):
        load_misegraph_evidence_package(package_dir)


def test_non_canonical_manifest_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    manifest = _manifest(package_dir)
    (package_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=4, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(MisegraphEvidencePackageError, match="canonical form"):
        load_misegraph_evidence_package(package_dir)


def test_authority_flags_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    manifest = _manifest(package_dir)
    manifest["non_authority"]["acceptance_authority"] = True
    _write_manifest(package_dir, manifest)
    with pytest.raises(MisegraphEvidencePackageError, match="acceptance_authority"):
        load_misegraph_evidence_package(package_dir)


def test_symlinked_artifact_rejected_even_with_matching_bytes(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    outside = tmp_path / "outside.mise"
    outside.write_bytes((package_dir / "source.mise").read_bytes())
    (package_dir / "source.mise").unlink()
    os.symlink(outside, package_dir / "source.mise")
    with pytest.raises(MisegraphEvidencePackageError, match="source.mise"):
        load_misegraph_evidence_package(package_dir)


def test_symlinked_package_dir_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    link = tmp_path / "pkg-link"
    os.symlink(package_dir, link, target_is_directory=True)
    with pytest.raises(MisegraphEvidencePackageError, match="symlink"):
        load_misegraph_evidence_package(link)


def test_artifact_name_escaping_package_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    manifest = _manifest(package_dir)
    entry = manifest["artifacts"].pop("episode.json")
    manifest["artifacts"]["../episode.json"] = entry
    _write_manifest(package_dir, manifest)
    with pytest.raises(MisegraphEvidencePackageError, match="plain file name"):
        load_misegraph_evidence_package(package_dir)


def test_canonical_ir_schema_violation_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    canonical = json.loads((package_dir / "canonical.json").read_text(encoding="utf-8"))
    canonical["unexpected_field"] = True
    _replace_artifact(
        package_dir,
        "canonical.json",
        (json.dumps(canonical, indent=2) + "\n").encode("utf-8"),
    )
    with pytest.raises(MisegraphEvidencePackageError, match="does not validate"):
        load_misegraph_evidence_package(package_dir)


def test_behavior_case_hash_mismatch_rejected(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    behavior = json.loads((package_dir / "behavior.json").read_text(encoding="utf-8"))
    behavior["cases"][0]["output_sha256"] = "1" * 64
    _replace_artifact(package_dir, "behavior.json", canonical_json(behavior).encode())
    with pytest.raises(MisegraphEvidencePackageError, match="output_sha256"):
        load_misegraph_evidence_package(package_dir)


def test_loader_and_importer_never_write_into_package(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    before = _snapshot(package_dir)
    load_misegraph_evidence_package(package_dir)
    _import(tmp_path, package=package_dir)
    assert _snapshot(package_dir) == before
    if os.geteuid() != 0:
        os.chmod(package_dir, 0o555)
        for child in package_dir.iterdir():
            os.chmod(child, 0o444)
        try:
            result = _import(tmp_path, outdir_name="out-ro", package=package_dir)
            assert result["status"] == "ok"
        finally:
            os.chmod(package_dir, 0o755)
            for child in package_dir.iterdir():
                os.chmod(child, 0o644)


# --- importer -----------------------------------------------------------------


def test_import_bundle_writes_four_files_and_is_deterministic(tmp_path: Path) -> None:
    first = _import(tmp_path)
    outdir = Path(first["outdir"])
    names = sorted(entry.name for entry in outdir.iterdir())
    assert names == sorted([INTENT_FILE, INPUTS_FILE, BINDING_FILE, PROVENANCE_FILE])
    first_bytes = {name: (outdir / name).read_bytes() for name in names}
    shutil.rmtree(outdir)
    second = _import(tmp_path)
    assert second == first
    for name in names:
        assert (outdir / name).read_bytes() == first_bytes[name]
    other = _import(tmp_path, outdir_name="elsewhere")
    assert (Path(other["outdir"]) / INTENT_FILE).read_bytes() == first_bytes[
        INTENT_FILE
    ]
    assert (Path(other["outdir"]) / INPUTS_FILE).read_bytes() == first_bytes[
        INPUTS_FILE
    ]


def test_import_bundle_refuses_to_clobber(tmp_path: Path) -> None:
    first = _import(tmp_path)
    outdir = Path(first["outdir"])
    before = _snapshot(outdir)
    with pytest.raises(MisegraphEvidenceImportError, match="refusing to overwrite"):
        _import(tmp_path)
    assert _snapshot(outdir) == before


def test_emitted_intent_loads_through_program_gen_loader(tmp_path: Path) -> None:
    result = _import(tmp_path)
    intent_path = Path(result["intent_path"])
    intent = load_program_intent(intent_path)
    assert intent.name == "AssessAMisegraphRecipeFromSupplied"
    assert intent.inputs == ["evidence"] and intent.outputs == ["answer"]
    assert intent.metric == "concept_coverage"
    assert intent.options["quality_proposal"]["accepted"] is True
    assert intent.quality_criteria[0]["id"] == "misegraph_recipe_fidelity"

    payload = json.loads(intent_path.read_text(encoding="utf-8"))
    examples = payload.pop("examples")
    derived_groups = payload["quality_criteria"][0]["required_concept_groups"]
    expected = derive_misegraph_expected(
        load_misegraph_evidence_package(PACKAGE), "render-text"
    )
    assert derived_groups == expected["required_concept_groups"]
    assert (
        derived_groups
        != REFERENCE_INTENT_TEMPLATE["quality_criteria"][0]["required_concept_groups"]
    )
    # Every non-example field except the package-derived concept groups is the
    # pinned AK-5346 reference intent.
    payload["quality_criteria"][0]["required_concept_groups"] = json.loads(
        json.dumps(
            REFERENCE_INTENT_TEMPLATE["quality_criteria"][0]["required_concept_groups"]
        )
    )
    compact = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert _sha(compact.encode("utf-8")) == REFERENCE_INTENT_WITHOUT_EXAMPLES_SHA256
    assert payload == json.loads(json.dumps(REFERENCE_INTENT_TEMPLATE))

    answers = json.loads(ANSWERS.read_text(encoding="utf-8"))["answers"]
    assert len(examples) == len(DEFAULT_EXAMPLE_CASES)
    for case_id, example in zip(DEFAULT_EXAMPLE_CASES, examples):
        assert set(example) == {"inputs", "outputs"}
        assert example["outputs"] == {"answer": answers[case_id]}
        evidence = json.loads(example["inputs"]["evidence"])
        assert set(evidence) == {
            "recipe",
            "package_sha256",
            "source",
            "canonical",
            "render",
            "check",
            "case",
        }
        assert evidence["package_sha256"] == PACKAGE_SHA256
        assert set(evidence["source"]) == {"sha256", "text"}
        assert set(evidence["canonical"]) == {"sha256", "json"}
        assert set(evidence["render"]) == {"sha256", "text"}
        assert set(evidence["check"]) == {"sha256", "diagnostics"}
        assert set(evidence["case"]) == {"id", "argv", "exit_code"}
        assert evidence["case"]["id"] == case_id
        assert evidence["canonical"]["json"]["id"] == "espresso_brownies"
        assert example["inputs"]["evidence"] == json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    inputs = json.loads(Path(result["inputs_path"]).read_text(encoding="utf-8"))
    assert inputs == {"inputs": examples[0]["inputs"]}


def test_binding_matches_misegraph_verifier_shape(tmp_path: Path) -> None:
    result = _import(tmp_path)
    binding_path = Path(result["binding_path"])
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    assert binding == result["binding"]
    assert set(binding) == {
        "schema_version",
        "package",
        "validation",
        "emitted",
        "example_cases",
        "non_authority",
    }
    assert binding["schema_version"] == BINDING_SCHEMA_VERSION
    assert set(binding["package"]) == {
        "dir",
        "manifest_sha256",
        "package_sha256",
        "producer",
    }
    assert set(binding["package"]["producer"]) == {
        "name",
        "version",
        "ir_schema_version",
    }
    assert binding["package"]["dir"] == str(PACKAGE.resolve())
    assert binding["package"]["manifest_sha256"] == MANIFEST_SHA256
    assert binding["package"]["package_sha256"] == PACKAGE_SHA256
    assert binding["validation"] == {
        "artifact_hashes_ok": True,
        "canonical_ir_schema_valid": True,
        "unknown_manifest_keys": [],
        "freshness": {
            "mode": "hash_bound",
            "check": "manifest_sha256_matches_at_import",
        },
    }
    assert set(binding["emitted"]) == {
        "intent_path",
        "intent_sha256",
        "inputs_path",
        "inputs_sha256",
    }
    emitted = binding["emitted"]
    assert Path(emitted["intent_path"]).is_absolute()
    assert _sha(Path(emitted["intent_path"]).read_bytes()) == emitted["intent_sha256"]
    assert _sha(Path(emitted["inputs_path"]).read_bytes()) == emitted["inputs_sha256"]
    assert binding["example_cases"] == list(DEFAULT_EXAMPLE_CASES)
    assert binding["non_authority"] == {
        "misegraph_mutated": False,
        "acceptance_authority": False,
    }


def test_answers_file_hashed_into_provenance_and_bound_via_intent(
    tmp_path: Path,
) -> None:
    result = _import(tmp_path)
    provenance = json.loads(Path(result["provenance_path"]).read_text(encoding="utf-8"))
    assert provenance["answers"]["origin"] == ANSWERS_ORIGIN_OPERATOR
    assert provenance["answers"]["sha256"] == _sha(ANSWERS.read_bytes())
    assert provenance["answers"]["path"] == str(ANSWERS.resolve())
    assert provenance["expected_projection"]["used_as_example_answer"] is False
    assert provenance["package_sha256"] == PACKAGE_SHA256
    assert provenance["binding"]["sha256"] == _sha(
        Path(result["binding_path"]).read_bytes()
    )
    assert provenance["non_authority"]["answers_authored_by_importer"] is False

    altered = tmp_path / "answers-altered.json"
    payload = json.loads(ANSWERS.read_text(encoding="utf-8"))
    payload["answers"]["render-text"] += " Altered."
    altered.write_text(json.dumps(payload), encoding="utf-8")
    other = write_import_bundle(
        package_dir=PACKAGE, answers_path=altered, outdir=tmp_path / "altered"
    )
    assert (
        other["binding"]["emitted"]["intent_sha256"]
        != result["binding"]["emitted"]["intent_sha256"]
    )
    assert other["provenance"]["answers"]["sha256"] == _sha(altered.read_bytes())


def test_importer_never_invents_operator_answers(tmp_path: Path) -> None:
    package = load_misegraph_evidence_package(PACKAGE)
    answers = load_misegraph_answers(ANSWERS)
    with pytest.raises(
        MisegraphEvidenceImportError, match="no entry for selected case"
    ):
        build_misegraph_intent(package, answers, ["convert-json"])
    with pytest.raises(MisegraphEvidenceImportError, match="not a behavior case"):
        build_misegraph_intent(package, answers, ["render-pdf"])
    with pytest.raises(MisegraphEvidenceImportError, match="repeats"):
        build_misegraph_intent(package, answers, ["check-json", "check-json"])
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {"schema_version": "dspx-misegraph-example-answers-v1", "answers": {}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(MisegraphEvidenceImportError, match="non-empty"):
        load_misegraph_answers(bad)
    bad.write_text(
        json.dumps(
            {
                "schema_version": "dspx-misegraph-example-answers-v1",
                "answers": {"check-json": "ok"},
                "objective": "x",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(MisegraphEvidenceImportError, match="exactly schema_version"):
        load_misegraph_answers(bad)
    bad.write_text(
        json.dumps({"schema_version": "v0", "answers": {"check-json": "ok"}}),
        encoding="utf-8",
    )
    with pytest.raises(MisegraphEvidenceImportError, match="schema_version"):
        load_misegraph_answers(bad)


def test_case_selection_orders_examples(tmp_path: Path) -> None:
    result = _import(tmp_path, cases=["check-json"])
    intent = json.loads(Path(result["intent_path"]).read_text(encoding="utf-8"))
    assert len(intent["examples"]) == 1
    evidence = json.loads(intent["examples"][0]["inputs"]["evidence"])
    assert evidence["case"]["id"] == "check-json"
    assert evidence["case"]["argv"] == [
        "check",
        "source.mise",
        "--json",
        "--deny-warnings",
    ]
    assert result["binding"]["example_cases"] == ["check-json"]
    inputs = build_misegraph_inputs(intent)
    assert inputs == {"inputs": intent["examples"][0]["inputs"]}


def test_no_absolute_path_leaks_beyond_declared_locations(tmp_path: Path) -> None:
    result = _import(tmp_path)
    outdir = Path(result["outdir"])
    allowed = (str(outdir), str(PACKAGE.resolve()), str(ANSWERS.resolve()))
    absolute = re.compile(r"/(?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]+")
    for name in (INTENT_FILE, INPUTS_FILE):
        text = (outdir / name).read_text(encoding="utf-8")
        assert "/home/" not in text and str(tmp_path) not in text
        assert "misegraph/" not in text.replace("misegraph-evidence", "")
    for name in (BINDING_FILE, PROVENANCE_FILE):
        text = (outdir / name).read_text(encoding="utf-8")
        for match in absolute.findall(text):
            assert match.startswith(allowed), match


def test_outdir_guards(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path / "root", name="pkg")
    with pytest.raises(MisegraphEvidenceImportError, match="outside the package dir"):
        write_import_bundle(
            package_dir=package_dir, answers_path=ANSWERS, outdir=package_dir / "out"
        )
    with pytest.raises(
        MisegraphEvidenceImportError, match="must not contain the package"
    ):
        write_import_bundle(
            package_dir=package_dir, answers_path=ANSWERS, outdir=tmp_path / "root"
        )
    fake_repo = tmp_path / "misegraph-repo"
    fake_repo.mkdir()
    (fake_repo / "Cargo.toml").write_text(
        '[package]\nname = "misegraph"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    with pytest.raises(MisegraphEvidenceImportError, match="Misegraph repository root"):
        write_import_bundle(
            package_dir=package_dir,
            answers_path=ANSWERS,
            outdir=fake_repo / "docs" / "project" / "evidence",
        )
    assert not (fake_repo / "docs").exists()
    outdir = tmp_path / "with-answers"
    outdir.mkdir()
    inside = outdir / "answers.json"
    inside.write_bytes(ANSWERS.read_bytes())
    with pytest.raises(
        MisegraphEvidenceImportError, match="answers file must be outside"
    ):
        write_import_bundle(package_dir=package_dir, answers_path=inside, outdir=outdir)
    link = tmp_path / "out-link"
    os.symlink(tmp_path / "real-out", link)
    with pytest.raises(MisegraphEvidenceImportError, match="real directory"):
        write_import_bundle(package_dir=package_dir, answers_path=ANSWERS, outdir=link)


def test_tampered_package_rejected_through_importer(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    (package_dir / "stray.txt").write_text("x", encoding="utf-8")
    with pytest.raises(MisegraphEvidenceImportError, match="package rejected"):
        _import(tmp_path, package=package_dir)
    assert not (tmp_path / "out").exists()


def test_misegraph_source_projection(tmp_path: Path) -> None:
    result = _import(tmp_path)
    projection = build_misegraph_source_projection(result["binding"])
    assert set(projection) == {"source", "canonical", "render", "package"}
    assert projection["source"] == {
        "path": str(PACKAGE.resolve() / "source.mise"),
        "sha256": "b3d210c1e1acc1778f67a2c42f3a76b66f19a4ac864bdbb0331bc23d2b6b6cef",
    }
    assert projection["canonical"]["sha256"] == (
        "068e4890ab5b278cecc3e27998ddf508c12b5b1b4c801ff704879c4915b75210"
    )
    assert projection["render"]["sha256"] == (
        "e0b343d04b2d5d3988a72574ca2532dcd2905016762da896c36e95cbbdb5de9b"
    )
    assert projection["package"]["package_sha256"] == PACKAGE_SHA256
    assert projection["package"]["example_cases"] == list(DEFAULT_EXAMPLE_CASES)
    stale = json.loads(json.dumps(result["binding"]))
    stale["package"]["manifest_sha256"] = "0" * 64
    with pytest.raises(MisegraphEvidenceImportError, match="manifest_sha256"):
        build_misegraph_source_projection(stale)
    with pytest.raises(MisegraphEvidenceImportError, match="schema_version"):
        build_misegraph_source_projection({"schema_version": "other"})


# --- package-derived expected projection --------------------------------------


def _criterion_passes(groups: list[list[str]], answer: str) -> bool:
    criteria = normalize_quality_criteria(
        [
            {
                "id": "misegraph_recipe_fidelity",
                "output_field": "answer",
                "evaluator": "concept_coverage",
                "required_concept_groups": groups,
                "forbidden_concepts": [],
                "min_score": 1.0,
            }
        ],
        outputs=["answer"],
    )
    return evaluate_declared_quality(criteria, {"answer": answer})["status"] == "passed"


def test_derive_misegraph_expected_comes_only_from_package_facts() -> None:
    package = load_misegraph_evidence_package(PACKAGE)
    expected = derive_misegraph_expected(package, "check-json")
    groups = expected["required_concept_groups"]
    flat = [term for group in groups for term in group]
    assert expected["schema_version"] == EXPECTED_PROJECTION_SCHEMA_VERSION
    assert expected["case_id"] == "check-json"
    assert ["espresso"] in groups and ["brownies"] in groups
    assert ["butter", "unsalted butter"] in groups
    assert ["baking_soda", "baking soda"] in groups
    assert ["pan", "8 × 8 inch baking pan"] in groups
    assert any("170 °C" in group and "170 C" in group for group in groups)
    assert any("30-40 min" in group and "40 min" in group for group in groups)
    assert any("0 errors" in group and "no diagnostics" in group for group in groups)
    assert expected["facts"]["error_count"] == 0
    assert expected["facts"]["recipe_id"] == "espresso_brownies"
    assert [item["id"] for item in expected["facts"]["ingredients"]] == [
        "butter",
        "sugar",
        "vanilla",
        "espresso",
        "eggs",
        "flour",
        "cocoa",
        "baking_soda",
        "salt",
    ]
    assert expected["facts"]["bake_steps"] == [
        {
            "step": "bake_brownies",
            "action": "bake",
            "temperature": "170 C",
            "duration": "30-40 min",
        }
    ]
    assert len(groups) <= 20 and all(1 <= len(group) <= 10 for group in groups)
    assert all(len(term) <= 256 for term in flat)
    assert set(expected["derived_from"]) == {
        "canonical.json",
        "check.json",
        "manifest.json",
        "behavior.json",
    }
    projection = expected["projection"]
    assert expected["projection_sha256"] == _sha(projection.encode("utf-8"))
    assert "case check-json (exit code 0)" in projection
    assert "not a judgment" in projection
    assert _criterion_passes(groups, projection)
    # The projection is not template prose: it fails once a package fact is dropped.
    assert not _criterion_passes(groups, projection.replace("170 C", "hot"))
    # The operator answers written for AK-5346 do not carry these package facts.
    operator = json.loads(ANSWERS.read_text(encoding="utf-8"))["answers"]["check-json"]
    assert not _criterion_passes(groups, operator)
    # Determinism and case independence of the groups.
    again = derive_misegraph_expected(package, "check-json")
    assert again == expected
    other = derive_misegraph_expected(package, "render-text")
    assert other["required_concept_groups"] == groups
    assert other["projection"] != projection
    assert "case render-text (exit code 0)" in other["projection"]


def test_derive_misegraph_expected_tracks_check_errors_and_fails_closed(
    tmp_path: Path,
) -> None:
    package_dir = _copy_package(tmp_path)
    check = {
        "diagnostics": [
            {"level": "error", "message": "missing bake temperature"},
            {"level": "warning", "message": "style"},
        ]
    }
    check_bytes = (json.dumps(check, indent=2) + "\n").encode("utf-8")
    _replace_artifact(package_dir, "check.json", check_bytes)
    behavior = json.loads((package_dir / "behavior.json").read_text(encoding="utf-8"))
    for case in behavior["cases"]:
        if case["output_artifact"] == "check.json":
            case["output_sha256"] = _sha(check_bytes)
    _replace_artifact(package_dir, "behavior.json", canonical_json(behavior).encode())
    package = load_misegraph_evidence_package(package_dir)
    expected = derive_misegraph_expected(package, "check-json")
    assert expected["facts"]["error_count"] == 1
    assert expected["facts"]["diagnostic_count"] == 2
    assert ["1 errors", "1 error", "error_count 1", "error_count: 1"] in expected[
        "required_concept_groups"
    ]
    assert "Check: 1 errors, 2 diagnostics" in expected["projection"]

    with pytest.raises(MisegraphEvidenceImportError, match="not a behavior case"):
        derive_misegraph_expected(package, "render-pdf")


def test_import_without_answers_uses_package_derived_projection(tmp_path: Path) -> None:
    result = write_import_bundle(package_dir=PACKAGE, outdir=tmp_path / "derived")
    intent = json.loads(Path(result["intent_path"]).read_text(encoding="utf-8"))
    package = load_misegraph_evidence_package(PACKAGE)
    groups = intent["quality_criteria"][0]["required_concept_groups"]
    for case_id, example in zip(DEFAULT_EXAMPLE_CASES, intent["examples"]):
        expected = derive_misegraph_expected(package, case_id)
        assert example["outputs"] == {"answer": expected["projection"]}
        assert groups == expected["required_concept_groups"]
        assert _criterion_passes(groups, example["outputs"]["answer"])
    provenance = result["provenance"]
    assert provenance["answers"] == {
        "origin": ANSWERS_ORIGIN_PACKAGE_DERIVED,
        "schema_version": None,
        "path": None,
        "sha256": None,
    }
    projection = provenance["expected_projection"]
    assert projection["schema_version"] == EXPECTED_PROJECTION_SCHEMA_VERSION
    assert projection["quality_criterion_id"] == "misegraph_recipe_fidelity"
    assert projection["required_concept_groups"] == groups
    assert projection["used_as_example_answer"] is True
    assert set(projection["projection_sha256_by_case"]) == set(DEFAULT_EXAMPLE_CASES)
    assert provenance["non_authority"]["answers_authored_by_importer"] is True
    written = json.loads(Path(result["provenance_path"]).read_text(encoding="utf-8"))
    assert written == provenance
    # Binding stays byte-compatible with Misegraph's closed receipt shape.
    binding = json.loads(Path(result["binding_path"]).read_text(encoding="utf-8"))
    assert set(binding) == {
        "schema_version",
        "package",
        "validation",
        "emitted",
        "example_cases",
        "non_authority",
    }
    assert binding["non_authority"] == {
        "misegraph_mutated": False,
        "acceptance_authority": False,
    }
    # Determinism across outdirs.
    second = write_import_bundle(package_dir=PACKAGE, outdir=tmp_path / "derived-2")
    assert (
        Path(second["intent_path"]).read_bytes()
        == Path(result["intent_path"]).read_bytes()
    )
    # Operator answers change the example answers but not the derived groups.
    operator = _import(tmp_path, outdir_name="operator")
    operator_intent = json.loads(
        Path(operator["intent_path"]).read_text(encoding="utf-8")
    )
    assert operator_intent["quality_criteria"] == intent["quality_criteria"]
    assert operator_intent["examples"][0]["outputs"] != intent["examples"][0]["outputs"]
    assert operator["provenance"]["answers"]["origin"] == ANSWERS_ORIGIN_OPERATOR
    assert (
        operator["provenance"]["non_authority"]["answers_authored_by_importer"] is False
    )


def test_cli_import_without_answers(tmp_path: Path) -> None:
    outdir = tmp_path / "cli-derived"
    result = runner.invoke(
        app,
        [
            "foundry",
            "import-misegraph-evidence",
            "--package",
            str(PACKAGE),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["provenance"]["answers"]["origin"] == ANSWERS_ORIGIN_PACKAGE_DERIVED
    intent = json.loads((outdir / INTENT_FILE).read_text(encoding="utf-8"))
    assert "not a judgment" in intent["examples"][0]["outputs"]["answer"]


# --- CLI ----------------------------------------------------------------------


def test_cli_import_misegraph_evidence_json(tmp_path: Path) -> None:
    outdir = tmp_path / "cli-out"
    result = runner.invoke(
        app,
        [
            "foundry",
            "import-misegraph-evidence",
            "--package",
            str(PACKAGE),
            "--answers",
            str(ANSWERS),
            "--outdir",
            str(outdir),
            "--case",
            "render-text",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["binding"]["example_cases"] == ["render-text"]
    assert (outdir / BINDING_FILE).is_file()
    plain = runner.invoke(
        app,
        [
            "foundry",
            "import-misegraph-evidence",
            "--package",
            str(PACKAGE),
            "--answers",
            str(ANSWERS),
            "--outdir",
            str(tmp_path / "cli-plain"),
        ],
    )
    assert plain.exit_code == 0, plain.output
    assert "import_misegraph_evidence_status: ok" in plain.stdout


def test_cli_import_rejects_tampered_package_with_exit_2(tmp_path: Path) -> None:
    package_dir = _copy_package(tmp_path)
    manifest = _manifest(package_dir)
    manifest["schema_version"] = "misegraph-evidence-package-v0"
    _write_manifest(package_dir, manifest)
    result = runner.invoke(
        app,
        [
            "foundry",
            "import-misegraph-evidence",
            "--package",
            str(package_dir),
            "--answers",
            str(ANSWERS),
            "--outdir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 2
    assert "package rejected" in result.output
    assert not (tmp_path / "out").exists()


def test_cli_foundry_group_keeps_root_options_and_lists_import() -> None:
    result = runner.invoke(app, ["foundry", "--help"])
    assert result.exit_code == 0
    assert "import-misegraph-evidence" in result.stdout
    root_options = runner.invoke(
        app,
        [
            "foundry",
            "--intent",
            "/nonexistent/intent.json",
            "--quality-proposal",
            "/nonexistent/qp.json",
            "--inputs",
            "/nonexistent/inputs.json",
            "--outdir",
            "/nonexistent/out",
        ],
    )
    assert root_options.exit_code == 2
    assert "intent file not found" in root_options.output
    bare = runner.invoke(app, ["foundry"])
    assert bare.exit_code == 2
    assert "required when foundry has no subcommand" in bare.output
    missing = runner.invoke(app, ["foundry", "--intent", "/nonexistent/intent.json"])
    assert missing.exit_code == 2


# --- offline stub smoke -------------------------------------------------------


def test_offline_stub_program_gen_and_run_accept_emitted_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _import(tmp_path, outdir_name="import")
    intent = json.loads(Path(result["intent_path"]).read_text(encoding="utf-8"))
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_ORACLE_SEMANTIC_BACKEND", "fixture-replay")
    monkeypatch.setenv(
        "DSPX_REPLAY_FIXTURE_JSON",
        json.dumps(
            {
                "reasoning": intent["objective"],
                "answer": intent["examples"][0]["outputs"]["answer"],
            }
        ),
    )
    candidate = tmp_path / "foundry" / "candidate"
    gen = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            result["intent_path"],
            "--outdir",
            str(candidate),
            "--print-manifest",
        ],
    )
    assert gen.exit_code == 0, gen.output
    manifest = json.loads(gen.stdout)
    assert (candidate / "manifest.json").is_file()
    assert manifest["intent"]["name"] == "AssessAMisegraphRecipeFromSupplied"
    run = runner.invoke(
        app,
        [
            "program-run",
            "--manifest",
            str(candidate / "manifest.json"),
            "--inputs",
            result["inputs_path"],
            "--outdir",
            str(tmp_path / "foundry" / "runtime"),
            "--skip-oracle-index",
            "--json",
        ],
    )
    assert run.exit_code == 0, run.output
    payload = json.loads(run.stdout)
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["runtime_receipt_written"] is True
    assert Path(payload["behavior_results_path"]).is_file()
