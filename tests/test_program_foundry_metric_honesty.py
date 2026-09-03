# summary: "Tests AK-5362/5366 metric honesty: concept_coverage GEPA binding, the optimizer-manifest metric_honesty block, consume-time wrapper verification, exact-metric refusal, and non-blocking differs signals."
# read_when:
#   - "Changing program_foundry_gepa_proposal._metric_plan, program_refinement_gepa concept-coverage wrapping, the metric_honesty block, or refinement comparison signals."

from __future__ import annotations

import glob
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from dspx.services.program_foundry_gepa_proposal import (
    ProgramFoundryGepaProposalError,
    _metric_plan,
)
from dspx.services.program_foundry_gepa_execution_contract import (
    _SUPPORTED_METRICS as EXECUTOR_METRICS,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_refinement import (
    _bounded_refinement,
    _failure_signals_from_behavior,
    _target_surface_for_status,
    comparison_signal_kind,
    metric_is_exact,
)
from dspx.services.program_refinement_gepa import (
    CONCEPT_COVERAGE_PROGRAM_NAME,
    build_program_refinement_gepa_result,
    write_program_refinement_gepa_result,
)
from dspx.services.program_refinement_gepa_candidate import (
    materialize_gepa_refinement_candidate,
)
from dspx.services.program_refinement_gepa_candidate_contracts import (
    ProgramRefinementGepaCandidateError,
    _identity_from_manifest,
    validate_program_refinement_gepa_candidate_result_contract,
    validate_program_refinement_gepa_result_contract,
)
from dspx.services.program_refinement_gepa_metric_honesty import (
    METRIC_HONESTY_KEYS,
    criteria_sha256,
    render_concept_coverage_program,
    wrapper_binding_line,
)
from dspx.services.program_service import materialize_program_from_intent
from test_program_refinement_gepa import _fake_gepa, _setup_env

DOCS_PROJECT = Path(__file__).resolve().parents[1] / "docs" / "project"

_CRITERIA = [
    {
        "id": "recipe_fidelity",
        "output_field": "answer",
        "evaluator": "concept_coverage",
        "required_concept_groups": [["espresso"], ["170 c", "170 °c"]],
        "forbidden_concepts": [],
        "min_score": 1.0,
    }
]


def _candidate(metric: str | None, criteria: list[dict[str, Any]] | None) -> dict:
    intent: dict[str, Any] = {"metric": metric}
    if criteria is not None:
        intent["quality_criteria"] = criteria
    return {"manifest": {"intent": intent}}


# --- proposal metric plan -------------------------------------------------------


def test_metric_plan_binds_concept_coverage_to_intent_criteria() -> None:
    plan = _metric_plan(_candidate("concept_coverage", _CRITERIA), metric_override=None)
    assert plan["optimizer_metric"] == "concept_coverage"
    assert plan["operator_metric_required"] is False
    assert plan["blockers"] == []
    binding = plan["concept_coverage_binding"]
    assert binding["criterion_ids"] == ["recipe_fidelity"]
    assert len(binding["criteria_sha256"]) == 64
    assert binding["optimizer_backend_metric"] == "exact"

    explicit = _metric_plan(
        _candidate("concept_coverage", _CRITERIA), metric_override="concept_coverage"
    )
    assert explicit["operator_metric_override"] == "concept_coverage"
    assert explicit["optimizer_metric"] == "concept_coverage"
    assert explicit["concept_coverage_binding"] == binding
    assert "concept_coverage" in EXECUTOR_METRICS


@pytest.mark.parametrize("override", ["exact", "exact_match"])
def test_metric_plan_refuses_exact_over_concept_coverage_intent(override: str) -> None:
    with pytest.raises(ProgramFoundryGepaProposalError, match="dishonest"):
        _metric_plan(
            _candidate("concept_coverage", _CRITERIA), metric_override=override
        )


def test_metric_plan_refuses_concept_coverage_without_matching_intent() -> None:
    with pytest.raises(ProgramFoundryGepaProposalError, match="requires an intent"):
        _metric_plan(
            _candidate("exact_match", None), metric_override="concept_coverage"
        )
    with pytest.raises(ProgramFoundryGepaProposalError, match="quality_criteria"):
        _metric_plan(_candidate("concept_coverage", []), metric_override=None)
    with pytest.raises(ProgramFoundryGepaProposalError, match="must be"):
        _metric_plan(_candidate("concept_coverage", _CRITERIA), metric_override="bogus")
    exact = _metric_plan(_candidate("exact_match", None), metric_override="exact")
    assert exact["optimizer_metric"] == "exact"
    assert "concept_coverage_binding" not in exact


# --- refinement comparison signals ----------------------------------------------


def _behavior() -> dict[str, Any]:
    return {
        "examples": [
            {
                "status": "failed",
                "expected_outputs": {"answer": "Espresso brownies bake at 170 °C."},
                "observed_outputs": {"answer": "Bake the espresso brownies at 170 C."},
                "notes": ["output mismatch for answer"],
            }
        ]
    }


def test_non_exact_metric_downgrades_mismatch_to_non_blocking_differs() -> None:
    assert metric_is_exact(None) and metric_is_exact("exact") and metric_is_exact("")
    assert not metric_is_exact("concept_coverage") and not metric_is_exact("f1")
    assert comparison_signal_kind("exact_match") == "mismatch"
    assert comparison_signal_kind("concept_coverage") == "differs"

    exact = _failure_signals_from_behavior(_behavior(), output_fields=["answer"])
    assert exact == ["mismatch:answer"]
    relaxed = _failure_signals_from_behavior(
        _behavior(), output_fields=["answer"], exact_metric=False
    )
    assert relaxed == ["differs:answer"]
    assert not any(signal.startswith("mismatch:") for signal in relaxed)

    surface, reason = _target_surface_for_status("failed", relaxed)
    assert surface == "module"
    assert "non-blocking" in reason and "mismatch" not in reason.split(";")[0]
    exact_surface, exact_reason = _target_surface_for_status("failed", exact)
    assert exact_surface == "module" and "output mismatch for answer" in exact_reason

    bounded = _bounded_refinement(
        behavior_status="failed", proposal_status="proposed", signals=relaxed
    )
    change = bounded["proposed_changes"][0]
    assert change["change_type"] == "improve_declared_quality_coverage"
    assert "not exact" in change["rationale"]
    assert "exact_match" not in change["rationale"]
    strict = _bounded_refinement(
        behavior_status="failed", proposal_status="proposed", signals=exact
    )
    assert strict["proposed_changes"][0]["change_type"] == "tighten_output_mapping"


# --- GEPA concept-coverage wrapper ----------------------------------------------


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("dspx_test_cc_wrapper", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    modules_before = dict(sys.modules)
    path_before = list(sys.path)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.clear()
        sys.modules.update(modules_before)
        sys.path[:] = path_before
    # The wrapper must not leak the candidate's modules into the process.
    assert "program" not in sys.modules or sys.modules["program"] is modules_before.get(
        "program"
    )
    assert "module" not in sys.modules or sys.modules["module"] is modules_before.get(
        "module"
    )
    return module


def test_gepa_concept_coverage_binds_wrapper_program_and_exact_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "DSPX_REPLAY_FIXTURE_JSON",
        json.dumps({"reasoning": "bounded", "answer": "Espresso brownies at 170 C."}),
    )
    calls = _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="RecipeFidelityProgram",
            objective="Assess a recipe evidence package.",
            inputs=["evidence"],
            outputs=["answer"],
            metric="concept_coverage",
            quality_criteria=_CRITERIA,
            examples=[
                {
                    "inputs": {"evidence": "espresso brownies bake at 170 C"},
                    "outputs": {"answer": "Espresso brownies bake at 170 °C."},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    outdir = tmp_path / "program-gepa"

    result = build_program_refinement_gepa_result(
        manifest_path=program_root / "manifest.json",
        outdir=outdir,
        metric="concept_coverage",
        max_metric_calls=2,
    )

    assert len(calls) == 1
    wrapper = outdir / "_gepa_inputs" / CONCEPT_COVERAGE_PROGRAM_NAME
    assert Path(calls[0]["program_path"]) == wrapper
    assert calls[0]["metric"] == "exact"
    gepa = result["gepa"]
    assert gepa["metric"] == "concept_coverage"
    assert gepa["optimizer_metric"] == "concept_coverage"
    assert gepa["metric_honesty"] == {
        "intent_metric": "concept_coverage",
        "optimizer_metric": "concept_coverage",
        "aligned": True,
    }
    binding = gepa["concept_coverage_binding"]
    assert binding["criterion_ids"] == ["recipe_fidelity"]
    assert binding["optimizer_backend_metric"] == "exact"
    assert Path(binding["candidate_program_path"]) == program_root / "program.py"
    assert Path(binding["wrapper_program_path"]) == wrapper
    assert len(binding["wrapper_program_sha256"]) == 64
    assert "dspx_version" not in wrapper.read_text(encoding="utf-8")
    assert not (program_root / CONCEPT_COVERAGE_PROGRAM_NAME).exists()

    module = _load_module(wrapper)
    assert module.io_spec()["outputs"] == ["answer"]
    passed = module.normalize_output(
        "answer", "irrelevant gold", "Espresso brownies, bake at 170 °C for 35 min."
    )
    assert passed[0] == passed[1] == "concept_coverage[recipe_fidelity]:passed"
    failed = module.normalize_output("answer", "irrelevant gold", "Bake at 350 F.")
    assert failed[0] == "concept_coverage[recipe_fidelity]:passed"
    assert failed[1].startswith("concept_coverage[recipe_fidelity]:failed (")
    assert "matched 0/2 groups" in failed[1]
    assert "missing group indexes [0, 1]" in failed[1]
    # Keys without criteria fall back to the candidate's own normalizer.
    assert module.normalize_output("other", '{"a":1}', '{ "a" : 1 }') == (
        '{"a":1}',
        '{"a":1}',
    )
    assert callable(module.build_student)


def test_gepa_result_records_metric_misalignment_for_exact_over_concept_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    calls = _fake_gepa(monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="RecipeFidelityProgram",
            objective="Assess a recipe evidence package.",
            inputs=["evidence"],
            outputs=["answer"],
            metric="concept_coverage",
            quality_criteria=_CRITERIA,
            examples=[
                {
                    "inputs": {"evidence": "espresso brownies bake at 170 C"},
                    "outputs": {"answer": "Espresso brownies bake at 170 °C."},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    result = build_program_refinement_gepa_result(
        manifest_path=Path(artifact.root_path) / "manifest.json",
        outdir=tmp_path / "program-gepa",
        metric="exact",
        max_metric_calls=2,
    )
    assert calls[0]["metric"] == "exact"
    assert result["gepa"]["metric_honesty"]["aligned"] is False
    assert "concept_coverage_binding" not in result["gepa"]


# --- metric_honesty block: manifest, receipt mirror, consume verification --------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _concept_coverage_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, metric: str = "concept_coverage"
) -> tuple[Path, Path, Path, dict[str, Any]]:
    """Materialize a source candidate and one fake, hash-bound GEPA run over it."""

    _setup_env(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "DSPX_REPLAY_FIXTURE_JSON",
        json.dumps({"reasoning": "bounded", "answer": "Espresso brownies at 170 C."}),
    )
    _fake_gepa(monkeypatch, hash_program=True)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="RecipeFidelityProgram",
            objective="Assess a recipe evidence package.",
            inputs=["evidence"],
            outputs=["answer"],
            metric=metric,
            quality_criteria=_CRITERIA,
            examples=[
                {
                    "inputs": {"evidence": "espresso brownies bake at 170 C"},
                    "outputs": {"answer": "Espresso brownies bake at 170 °C."},
                }
            ],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    optimizer_root = tmp_path / "program-gepa"
    result_path = tmp_path / "refinement" / "gepa_refinement_result.json"
    result = build_program_refinement_gepa_result(
        manifest_path=program_root / "manifest.json",
        outdir=optimizer_root,
        metric=metric,
        max_metric_calls=2,
        result_out=result_path,
    )
    write_program_refinement_gepa_result(result, result_path)
    return program_root, optimizer_root, result_path, result


def _validate_with_source(program_root: Path, result_path: Path) -> dict[str, Any]:
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    return validate_program_refinement_gepa_result_contract(
        json.loads(result_path.read_text(encoding="utf-8")),
        expected_identities=[_identity_from_manifest(manifest)],
        source_program_hash=_sha256(program_root / "program.py"),
        source_manifest=manifest,
        source_program_path=program_root / "program.py",
    )


def _rewrite_manifest(
    optimizer_root: Path,
    result_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """Mutate the optimizer manifest and rebind the sidecar to the new manifest hash."""

    manifest_path = optimizer_root / "manifest.json"
    pristine = optimizer_root.parent / "manifest.pristine.json"
    if not pristine.exists():
        pristine.write_bytes(manifest_path.read_bytes())
    manifest = json.loads(pristine.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sidecar = json.loads(result_path.read_text(encoding="utf-8"))
    sidecar["gepa_output"]["manifest_sha256"] = _sha256(manifest_path)
    result_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n")


def test_gepa_concept_coverage_stamps_closed_metric_honesty_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, optimizer_root, _, result = _concept_coverage_lineage(
        tmp_path, monkeypatch
    )
    assert result["status"] == "degraded"
    assert result["gepa"]["status"] == "completed"
    manifest = json.loads((optimizer_root / "manifest.json").read_text("utf-8"))
    block = manifest["metric_honesty"]
    binding = result["gepa"]["concept_coverage_binding"]
    source_sha256 = _sha256(program_root / "program.py")
    wrapper = optimizer_root / "_gepa_inputs" / CONCEPT_COVERAGE_PROGRAM_NAME
    intent = json.loads((program_root / "manifest.json").read_text("utf-8"))["intent"]
    assert set(block) == METRIC_HONESTY_KEYS
    assert block == binding["metric_honesty"]
    assert block == {
        "metric": "concept_coverage",
        "wrapper_program_sha256": _sha256(wrapper),
        "source_program_sha256": source_sha256,
        "criteria_sha256": criteria_sha256(intent["quality_criteria"]),
    }
    assert manifest["program"]["sha256"] == block["wrapper_program_sha256"]
    assert block["wrapper_program_sha256"] != source_sha256
    assert binding["criteria_sha256"] == block["criteria_sha256"]
    # The wrapper carries the source hash binding and is byte-reproducible.
    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert wrapper_binding_line(source_sha256) in wrapper_text.splitlines()
    assert wrapper_text == render_concept_coverage_program(
        candidate_program=(program_root / "program.py").resolve(),
        candidate_program_sha256=source_sha256,
        criteria=intent["quality_criteria"],
        output_fields=intent["outputs"],
    )
    assert (optimizer_root / "source" / CONCEPT_COVERAGE_PROGRAM_NAME).read_bytes() == (
        wrapper.read_bytes()
    )
    # Loading the wrapper over a drifted source program refuses.
    module = _load_module(wrapper)
    assert callable(module.build_student)
    (program_root / "program.py").write_text(
        (program_root / "program.py").read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="hash drifted"):
        _load_module(wrapper)


def test_consume_contract_accepts_and_materializes_concept_coverage_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, optimizer_root, result_path, _ = _concept_coverage_lineage(
        tmp_path, monkeypatch
    )
    validation = _validate_with_source(program_root, result_path)
    manifest = json.loads((optimizer_root / "manifest.json").read_text("utf-8"))
    block = manifest["metric_honesty"]
    assert validation["ready_for_future_candidate_materializer"] is True
    assert validation["optimizer_manifest"]["metric_honesty"] == block
    # Hash-only verification (no source context) still binds the source hash.
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    identity = _identity_from_manifest(
        json.loads((program_root / "manifest.json").read_text("utf-8"))
    )
    validate_program_refinement_gepa_result_contract(
        payload,
        expected_identities=[identity],
        source_program_hash=_sha256(program_root / "program.py"),
    )
    with pytest.raises(
        ProgramRefinementGepaCandidateError, match="source_program_sha256"
    ):
        validate_program_refinement_gepa_result_contract(
            payload, expected_identities=[identity], source_program_hash="0" * 64
        )

    outdir = tmp_path / "program-gepa-candidate"
    result_out = tmp_path / "refinement" / "gepa_candidate_result.json"
    result = materialize_gepa_refinement_candidate(
        manifest_path=program_root / "manifest.json",
        gepa_result_path=result_path,
        outdir=outdir,
        result_out=result_out,
    )
    assert result["status"] == "materialized"
    assert result["gepa_output"]["metric_honesty"] == block
    assert (
        result["gepa_output"]["source_program_sha256"]
        == (block["source_program_sha256"])
    )
    assert (
        result["gepa_output"]["optimizer_manifest_program_sha256"]
        == (block["wrapper_program_sha256"])
    )
    # The candidate program is the source program plus the optimizer loader,
    # never the metric wrapper.
    candidate_program = (outdir / "program.py").read_text(encoding="utf-8")
    source_program = (program_root / "program.py").read_text(encoding="utf-8")
    source_lines = [
        line
        for line in source_program.splitlines()
        if line.strip() and not line.startswith("CONSTRAINTS = ")
    ]
    candidate_lines = candidate_program.splitlines()
    assert source_lines and all(line in candidate_lines for line in source_lines)
    assert "GEPA metric wrapper" not in candidate_program
    assert "CANDIDATE_PROGRAM_SHA256" not in candidate_program
    assert _sha256(outdir / "program.py") != block["wrapper_program_sha256"]
    candidate_manifest = json.loads((outdir / "manifest.json").read_text("utf-8"))
    assert candidate_manifest["gepa_refinement"]["metric_honesty"] == block
    lineage = json.loads((outdir / "gepa_candidate_lineage.json").read_text("utf-8"))
    assert lineage["metric_honesty"] == block
    validate_program_refinement_gepa_candidate_result_contract(
        result,
        expected_source_manifest_path=program_root / "manifest.json",
        expected_gepa_result_path=result_path,
    )
    # Lineage that drops or alters the block no longer validates.
    candidate_manifest["gepa_refinement"]["metric_honesty"] = {
        **block,
        "source_program_sha256": "0" * 64,
    }
    (outdir / "manifest.json").write_text(json.dumps(candidate_manifest), "utf-8")
    with pytest.raises(
        ProgramRefinementGepaCandidateError,
        match="lineage metric_honesty does not match",
    ):
        validate_program_refinement_gepa_candidate_result_contract(
            result,
            expected_source_manifest_path=program_root / "manifest.json",
            expected_gepa_result_path=result_path,
        )


def test_consume_contract_rejects_tampered_wrapper_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, optimizer_root, result_path, _ = _concept_coverage_lineage(
        tmp_path, monkeypatch
    )

    def tamper(manifest: dict[str, Any]) -> None:
        manifest["metric_honesty"]["wrapper_program_sha256"] = "1" * 64

    _rewrite_manifest(optimizer_root, result_path, tamper)
    with pytest.raises(
        ProgramRefinementGepaCandidateError,
        match="wrapper_program_sha256 does not match the GEPA optimizer manifest",
    ):
        _validate_with_source(program_root, result_path)

    def tamper_both(manifest: dict[str, Any]) -> None:
        manifest["metric_honesty"]["wrapper_program_sha256"] = "1" * 64
        manifest["program"]["sha256"] = "1" * 64

    _rewrite_manifest(optimizer_root, result_path, tamper_both)
    with pytest.raises(
        ProgramRefinementGepaCandidateError,
        match="does not match the wrapper re-derived",
    ):
        _validate_with_source(program_root, result_path)
    with pytest.raises(ProgramRefinementGepaCandidateError):
        materialize_gepa_refinement_candidate(
            manifest_path=program_root / "manifest.json",
            gepa_result_path=result_path,
            outdir=tmp_path / "program-gepa-candidate",
        )
    assert not (tmp_path / "program-gepa-candidate").exists()


def test_consume_contract_rejects_tampered_source_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, optimizer_root, result_path, _ = _concept_coverage_lineage(
        tmp_path, monkeypatch
    )

    def tamper(manifest: dict[str, Any]) -> None:
        manifest["metric_honesty"]["source_program_sha256"] = "2" * 64

    _rewrite_manifest(optimizer_root, result_path, tamper)
    with pytest.raises(
        ProgramRefinementGepaCandidateError,
        match="source_program_sha256 does not match source candidate",
    ):
        _validate_with_source(program_root, result_path)

    def tamper_criteria(manifest: dict[str, Any]) -> None:
        manifest["metric_honesty"]["criteria_sha256"] = "3" * 64

    _rewrite_manifest(optimizer_root, result_path, tamper_criteria)
    with pytest.raises(
        ProgramRefinementGepaCandidateError, match="criteria_sha256 does not match"
    ):
        _validate_with_source(program_root, result_path)

    def drop_block(manifest: dict[str, Any]) -> None:
        del manifest["metric_honesty"]

    _rewrite_manifest(optimizer_root, result_path, drop_block)
    with pytest.raises(
        ProgramRefinementGepaCandidateError, match="must carry a metric_honesty block"
    ):
        _validate_with_source(program_root, result_path)

    def open_block(manifest: dict[str, Any]) -> None:
        manifest["metric_honesty"]["extra"] = True

    _rewrite_manifest(optimizer_root, result_path, open_block)
    with pytest.raises(ProgramRefinementGepaCandidateError, match="exactly metric"):
        _validate_with_source(program_root, result_path)


def test_consume_contract_rejects_wrapper_not_derived_from_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrapper with consistent hashes but foreign bytes is still rejected."""

    program_root, optimizer_root, result_path, _ = _concept_coverage_lineage(
        tmp_path, monkeypatch
    )
    wrapper = optimizer_root / "source" / CONCEPT_COVERAGE_PROGRAM_NAME
    wrapper.write_text(
        wrapper.read_text(encoding="utf-8").replace(
            "OUTPUT_FIELDS = ", "SCORE_ALWAYS = True\nOUTPUT_FIELDS = "
        ),
        encoding="utf-8",
    )
    wrapper_sha256 = _sha256(wrapper)

    def rebind(manifest: dict[str, Any]) -> None:
        manifest["program"]["sha256"] = wrapper_sha256
        manifest["metric_honesty"]["wrapper_program_sha256"] = wrapper_sha256
        for item in manifest["output_payload"]["files"]:
            if item["path"] == f"source/{CONCEPT_COVERAGE_PROGRAM_NAME}":
                item["sha256"] = wrapper_sha256
                item["size_bytes"] = wrapper.stat().st_size
        files = manifest["output_payload"]["files"]
        tree_text = json.dumps(
            files, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        manifest["output_payload"]["tree_hash"] = hashlib.sha256(
            tree_text.encode("utf-8")
        ).hexdigest()

    _rewrite_manifest(optimizer_root, result_path, rebind)
    with pytest.raises(
        ProgramRefinementGepaCandidateError,
        match="does not match the wrapper re-derived",
    ):
        _validate_with_source(program_root, result_path)


def test_exact_metric_optimizer_manifest_carries_no_metric_honesty_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_root, optimizer_root, result_path, result = _concept_coverage_lineage(
        tmp_path, monkeypatch, metric="exact_match"
    )
    manifest = json.loads((optimizer_root / "manifest.json").read_text("utf-8"))
    assert "metric_honesty" not in manifest
    assert "concept_coverage_binding" not in result["gepa"]
    assert manifest["program"]["sha256"] == _sha256(program_root / "program.py")
    validation = _validate_with_source(program_root, result_path)
    assert validation["ready_for_future_candidate_materializer"] is True
    assert "metric_honesty" not in validation["optimizer_manifest"]

    def tamper(manifest: dict[str, Any]) -> None:
        manifest["program"]["sha256"] = "4" * 64

    _rewrite_manifest(optimizer_root, result_path, tamper)
    with pytest.raises(
        ProgramRefinementGepaCandidateError,
        match="source program hash does not match source candidate",
    ):
        _validate_with_source(program_root, result_path)


def test_retained_execution_receipts_predate_metric_honesty_and_keep_shape() -> None:
    expected_keys = {
        "schema_version",
        "status",
        "proposal_id",
        "proposal_sha256",
        "attempt_sha256",
        "result_path",
        "result_sha256",
        "gepa_status",
        "optimizer_output_readiness",
        "optimizer_manifest_sha256",
        "optimizer_tree_sha256",
        "effect",
        "non_authority",
    }
    receipts = 0
    for path in sorted(glob.glob(str(DOCS_PROJECT / "*-evidence.json"))):
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        artifacts = document.get("artifacts") or {}
        execution_receipt = artifacts.get("execution_receipt")
        if not isinstance(execution_receipt, dict):
            continue
        projection = execution_receipt.get("projection")
        if not isinstance(projection, dict):
            continue
        receipts += 1
        assert "metric_honesty" not in projection, path
        assert set(projection) - {"provider_evidence_kind"} == expected_keys, path
        assert projection["status"] == "ok", path
    assert receipts >= 5, "retained foundry GEPA execution receipts must be present"
