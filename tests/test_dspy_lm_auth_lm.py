from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
import hashlib
import importlib
import importlib._bootstrap_external as bootstrap_external
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import threading
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

import dspx.services.program_oracle_semantic_owner_bridge_v11 as adapter
from dspx.services.program_oracle_semantic_owner_bridge_v11 import DspyLMAuthLM
from dspx.services.program_oracle_semantic_adapter_v11 import ReceiptSafeDspyLMAuthLM
from dspx.services.program_oracle_semantic_artifacts_v11 import (
    ConsumedAttempt,
    TaskBinding,
    assert_attempt_absent,
    state_root_identity_sha256,
)
from dspx.services.program_oracle_semantic_contract_v11 import SemanticV11Error
from dspx.services.program_oracle_semantic_state_v11 import (
    _consume_fixture_attempt,
)
from dspx.services.program_oracle_semantic_gate4_v11 import (
    candidate_source_manifest,
    verify_loaded_runtime_modules,
)
from dspx.services.program_oracle_semantic_contract_v10 import INHERITED_KEYS
from dspx.services.program_oracle_semantic_contract_v11 import (
    CASE_ORDER,
    CONSUMER_MODULE_HASHES,
    CONTRACT_SHA256,
    PROPOSAL_PATH,
    PROPOSAL_SHA256,
    SEMANTIC_KEYS,
    V10_PATH,
    canonical,
    load_bound_cases,
    load_candidate,
    materialized_request,
    semantic_request_projection,
    semantic_request_sha256,
    sha256,
)
from dspx.services.program_oracle_semantic_evaluation_v11 import (
    normalized_semantic_request,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    EXPECTED_ENDPOINT_ORIGIN_SHA256,
    GATE4_DONE_CONTRACT,
    GATE4_GUARDRAILS,
    GATE5_DONE_CONTRACT,
    GATE5_GUARDRAILS,
    PRELEDGER_FORBIDDEN_PREFIXES,
    REQUIRED_LIVE_COMPLETION_KIND,
)
from dspx.services.program_oracle_semantic_gate5_journal_v11 import (
    inspect_journal as gate5_inspect_journal,
)
from dspx.services.program_oracle_semantic_gate5_semantics_v11 import (
    load_verifier_cases,
    validate_retained_semantic_result as gate5_validate_semantic,
)
from dspx.services.program_oracle_semantic_result_artifact_v11 import (
    inspect_fixture_journal,
    inspect_journal,
)
from dspx.services.program_oracle_semantic_result_v11 import (
    SemanticValidationReport,
    validate_semantic_response,
)
from dspx.services.provider_outcome_receipt_contract import (
    EVENT_FIELDS,
    ReceiptReservation,
)
from dspx.services.provider_outcome_receipt_identity import (
    ACCEPTED_OWNER_SOURCE,
    VerifiedOwnerArtifact,
    _fixture_owner_artifact,
)
from dspx.services.provider_outcome_receipt_journal import ReceiptJournal

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts/ci/run_oracle_semantic_analysis_evaluation_v11.py"


def _private(path: Path) -> Path:
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


@dataclass
class _Response:
    output_text: str = "secret-output"
    model: str = "gpt-5.6-sol"
    usage: dict[str, int] | None = None


class _Inner:
    def __init__(self, result: object) -> None:
        self.result = result
        self.kwargs: dict[str, Any] | None = None
        self._uses_codex_route = True
        self.num_retries = 0

    def forward(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _TaintedResponse:
    usage = {"secret": {"nested": "forbidden"}}
    model = object()

    def __str__(self) -> str:  # pragma: no cover
        raise AssertionError("tainted response stringification forbidden")


def _generic_lm(result: object, *, strict: bool = True) -> tuple[DspyLMAuthLM, _Inner]:
    inner = _Inner(result)
    lm = DspyLMAuthLM(
        model="codex/gpt-5.6-sol",
        auth_provider="codex",
        strict=strict,
        kwargs={"reasoning_effort": "max"},
    )
    lm._inner = inner
    lm._uses_codex_route = True
    lm._stream_metadata_reader = lambda response: {"sensitive": "metadata"}
    return lm, inner


def test_generic_adapter_kwargs_behavior_remains_unchanged(monkeypatch):
    monkeypatch.setattr(adapter, "_check_capability", None)
    lm, inner = _generic_lm(_Response())
    outcome_receipt = object()
    prepared_receipt = object()
    lm.forward(
        prompt="bounded",
        outcome_receipt=outcome_receipt,
        prepared_receipt=prepared_receipt,
    )
    assert inner.kwargs is not None
    assert inner.kwargs["outcome_receipt"] is outcome_receipt
    assert inner.kwargs["prepared_receipt"] is prepared_receipt


def test_receipt_safe_adapter_exposes_no_live_invocation_or_callback_surface(
    monkeypatch,
):
    monkeypatch.setattr(adapter, "_check_capability", None)
    lm = ReceiptSafeDspyLMAuthLM()
    with pytest.raises(Exception, match="direct v11 adapter invocation"):
        lm.forward(prompt="bounded")
    with pytest.raises(Exception, match="direct v11 adapter invocation"):
        lm.generate(cast(Any, object()))
    assert not hasattr(lm, "_invoke_once")
    assert not any(
        "callback" in name or "receipt" in name
        for name in vars(type(lm))
        if name not in {"_receipt_text", "_receipt_model"}
    )


def test_loaded_runtime_origin_hash_binding_rejects_foreign_module(monkeypatch):
    manifest = candidate_source_manifest(REPO)
    fake = ModuleType("dspx.services.program_oracle_semantic_backend")
    fake.__file__ = str(REPO / "tests/test_dspy_lm_auth_lm.py")
    from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
        REVIEWED_RUNTIME_MODULES,
    )

    for name in tuple(sys.modules):
        if (
            name == "dspx" or name.startswith("dspx.")
        ) and name not in REVIEWED_RUNTIME_MODULES:
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    with pytest.raises(SemanticV11Error, match="origin(?:/hash)? drift"):
        verify_loaded_runtime_modules(REPO, manifest, require_all=False)


def _run(args: list[str], *, env: dict[str, str] | None = None, cwd: Path = REPO):
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env or {})},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_bootstrap_rejects_preloaded_dspx_and_contaminated_sitecustomize(tmp_path):
    contam = tmp_path / "contam"
    contam.mkdir()
    (contam / "sitecustomize.py").write_text(
        "import sys, types\nsys.modules['dspx'] = types.ModuleType('dspx')\n"
    )
    completed = _run(
        [str(RUNNER), "--repo", str(REPO)],
        env={"PYTHONPATH": str(contam)},
    )
    assert completed.returncode != 0
    assert "preloaded DSPx modules" in completed.stderr


def test_bootstrap_source_loader_ignores_stale_pythonpath_and_checks_allowlist(
    tmp_path,
):
    forbidden = set(PRELEDGER_FORBIDDEN_PREFIXES)
    assert {
        "dspy",
        "dspy_lm_auth",
        "dspx.services.program_oracle_semantic_owner_bridge_v11",
        "dspx.services.program_oracle_semantic_backend",
        "dspx.services.program_oracle_semantic_evaluation",
        "dspx.services.program_oracle_semantic_adapter",
        "dspx.services.program_oracle_semantic_identity",
        "dspx.services.program_oracle_semantic_result",
    } <= forbidden
    from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
        REVIEWED_RUNTIME_MODULES,
    )

    bootstrap_source = RUNNER.read_text()
    assert all(path in bootstrap_source for path in REVIEWED_RUNTIME_MODULES.values())
    stale = tmp_path / "stale"
    package = stale / "dspx"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise RuntimeError('stale package used')\n")
    state = _private(tmp_path / "state")
    completed = _run(
        [
            str(RUNNER),
            "--repo",
            str(REPO),
            "--task-binding-check",
            "85001",
            "--state-root",
            str(state),
        ],
        env={"PYTHONPATH": str(stale)},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["task_binding"][
        "state_root_identity_sha256"
    ] == state_root_identity_sha256(state)
    assert list(state.iterdir()) == []

    code = f"""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('v11_bootstrap', {str(RUNNER)!r})
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
gate=module._load_target_entry(Path({str(REPO)!r}), 'dspx.services.program_oracle_semantic_gate4_v11')
gate._assert_preledger_import_posture()
import copy
import hashlib
import importlib
import importlib._bootstrap_external as bootstrap_external
import importlib.util
import importlib
import importlib._bootstrap_external as bootstrap_external
import importlib.util
gate._runtime_modules()
manifest=gate.candidate_source_manifest(Path({str(REPO)!r}))
gate.verify_loaded_runtime_modules(Path({str(REPO)!r}), manifest, require_all=True)
print('ok')
"""
    allowlist = _run(["-c", code], env={"PYTHONPATH": str(stale)})
    assert allowlist.returncode == 0, allowlist.stdout + allowlist.stderr
    assert allowlist.stdout.strip() == "ok"

    gate5_code = f"""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('v11_bootstrap', {str(RUNNER)!r})
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
gate5=module._load_target_entry(Path({str(REPO)!r}), 'dspx.services.program_oracle_semantic_gate5_v11')
from dspx.services.program_oracle_semantic_gate5_runtime_v11 import source_manifest, verify_loaded_origins
manifest=source_manifest(Path({str(REPO)!r})); verify_loaded_origins(Path({str(REPO)!r}), manifest)
print('ok')
"""
    gate5_origin = _run(["-c", gate5_code], env={"PYTHONPATH": str(stale)})
    assert gate5_origin.returncode == 0, gate5_origin.stdout + gate5_origin.stderr
    assert gate5_origin.stdout.strip() == "ok"


def test_cli_gate4_and_gate5_operations_are_mutually_exclusive():
    completed = _run(
        [str(RUNNER), "--repo", str(REPO), "--execute-live", "--verify-retained"]
    )
    assert completed.returncode != 0
    assert "not allowed with argument" in completed.stderr


@pytest.mark.parametrize(
    "relative",
    [
        "services/program_oracle_semantic_gate4_v11.py",
        "services/program_oracle_semantic_state_v11.py",
    ],
)
def test_bootstrap_rejects_drifted_entry_or_transitive_helper(tmp_path, relative):
    root = tmp_path / "repo"
    target_script = root / "scripts/ci/run_oracle_semantic_analysis_evaluation_v11.py"
    target_script.parent.mkdir(parents=True)
    shutil.copy2(RUNNER, target_script)
    source = REPO / "packages/dspx-core/src/dspx"
    target = root / "packages/dspx-core/src/dspx"
    shutil.copytree(source, target)
    (target / relative).write_text("DRIFT = True\n")
    completed = _run([str(target_script), "--repo", str(root)], cwd=root)
    assert completed.returncode != 0
    assert "preledger module hash drift" in completed.stderr


def test_source_loader_rechecks_hash_when_source_drifts_after_preparation(tmp_path):
    root = tmp_path / "recheck-repo"
    target_script = root / "scripts/ci/run_oracle_semantic_analysis_evaluation_v11.py"
    target_script.parent.mkdir(parents=True)
    shutil.copy2(RUNNER, target_script)
    target_root = root / "packages/dspx-core/src/dspx"
    shutil.copytree(REPO / "packages/dspx-core/src/dspx", target_root)
    helper = target_root / "services/program_oracle_semantic_state_v11.py"
    code = f"""
import importlib, importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('v11_bootstrap', {str(target_script)!r})
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module._prepare_target_packages(Path({str(root)!r}))
path=Path({str(helper)!r}); path.write_bytes(path.read_bytes()+b'\\nDRIFT=True\\n')
importlib.import_module('dspx.services.program_oracle_semantic_state_v11')
"""
    completed = _run(["-c", code], cwd=root)
    assert completed.returncode != 0
    assert "source hash drift during import" in completed.stderr


def test_bootstrap_ignores_timestamp_valid_malicious_pyc_and_executes_source(
    tmp_path,
):
    root = tmp_path / "source-only-repo"
    target_script = root / "scripts/ci/run_oracle_semantic_analysis_evaluation_v11.py"
    target_script.parent.mkdir(parents=True)
    shutil.copy2(RUNNER, target_script)
    source_root = REPO / "packages/dspx-core/src/dspx"
    target_root = root / "packages/dspx-core/src/dspx"
    shutil.copytree(source_root, target_root)
    target_source = target_root / "services/program_oracle_semantic_gate4_v11.py"
    info = target_source.stat()
    hostile = compile(
        "raise RuntimeError('timestamp-valid malicious pyc executed')\n",
        str(target_source),
        "exec",
    )
    cache_path = Path(importlib.util.cache_from_source(str(target_source)))
    cache_path.parent.mkdir(exist_ok=True)
    pyc = cast(Any, bootstrap_external)._code_to_timestamp_pyc(
        hostile, int(info.st_mtime), info.st_size
    )
    cache_path.write_bytes(pyc)
    try:
        _, flags, timestamp, size = struct.unpack("<4sIII", pyc[:16])
        assert flags == 0
        assert timestamp == int(info.st_mtime) & 0xFFFFFFFF
        assert size == info.st_size & 0xFFFFFFFF
        code = f"""
import importlib.util, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('v11_bootstrap', {str(target_script)!r})
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
gate=module._load_target_entry(Path({str(root)!r}), 'dspx.services.program_oracle_semantic_gate4_v11')
assert sys.dont_write_bytecode is True
assert gate.__cached__ is None
assert type(gate.__loader__).__name__ == '_VerifiedSourceLoader'
print(gate.__file__)
"""
        completed = _run(["-c", code], cwd=root)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert completed.stdout.strip() == str(target_source)
        assert "malicious pyc executed" not in completed.stderr
        assert cache_path.read_bytes() == pyc
    finally:
        # This cache lives under this test's tmp_path; no shared/repository cache
        # is traversed or removed.
        shutil.rmtree(cache_path.parent)


@dataclass(frozen=True, slots=True)
class _ReceiptEvent:
    kind: str
    gate_ordinal: int | None = None
    status_class: int | None = None
    error_class: str | None = None
    protocol_event: str | None = None
    response_id_sha256: str | None = None
    observed_model: str | None = None


assert tuple(_ReceiptEvent.__dataclass_fields__) == EVENT_FIELDS


@dataclass(slots=True)
class _FixtureReceipt:
    logical_request_id: str
    semantic_request_sha256: str
    sink: Any
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _used: bool = False


def _fixture_artifact() -> VerifiedOwnerArtifact:
    expected = ACCEPTED_OWNER_SOURCE
    return _fixture_owner_artifact(
        source_identity={
            "owner": "tryinget-dspy-lm-auth",
            "version": expected.version,
            "commit": expected.commit,
            "tree": expected.tree,
            "lock_sha256": expected.lock_sha256,
            "module_sha256": {
                name: digest for name, (_, digest) in expected.modules.items()
            },
        },
        dependency_identity={
            name: {
                "version": item.version,
                "locked_wheel_sha256": item.wheel_sha256,
                "payload_count": item.payload_count,
                "payload_sha256": item.payload_sha256,
                "record_sha256": item.record_sha256,
            }
            for name, item in expected.dependencies.items()
        },
        event_type=_ReceiptEvent,
        receipt_type=_FixtureReceipt,
    )


def _reservation(task_id: int = 91001) -> ReceiptReservation:
    artifact = _fixture_artifact()
    return ReceiptReservation(
        consumer_task_id=task_id,
        ledger_sha256="1" * 64,
        process_id="2" * 64,
        case_id="authority-boundary",
        logical_request_id="3" * 64,
        transport_gate_id="4" * 64,
        semantic_request_sha256="5" * 64,
        contract_sha256=CONTRACT_SHA256,
        mode="sync",
        requested_route="dspy-lm-auth:codex:gpt-5.6-sol:max",
        resolved_route="openai:gpt-5.6-sol:responses",
        endpoint_origin_sha256=EXPECTED_ENDPOINT_ORIGIN_SHA256,
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )


def _journal(tmp_path: Path):
    artifact = _fixture_artifact()
    reservation = _reservation()
    journal = ReceiptJournal.create(
        _private(tmp_path / "journals") / "case", reservation, artifact
    )
    return (
        journal,
        cast(_FixtureReceipt, journal.provider_receipt()),
        reservation,
        artifact,
    )


def test_candidate_contract_and_accepted_consumer_bytes_remain_exact():
    contract, semantics, digest = load_candidate(REPO)
    v10 = json.loads((REPO / V10_PATH).read_text())
    assert digest == CONTRACT_SHA256
    assert tuple(case["id"] for case in contract["cases"]) == CASE_ORDER
    for key in INHERITED_KEYS:
        assert canonical(contract[key]) == canonical(v10[key])
    assert (
        hashlib.sha256((REPO / PROPOSAL_PATH).read_bytes()).hexdigest()
        == PROPOSAL_SHA256
    )
    service_root = REPO / "packages/dspx-core/src/dspx/services"
    for name, expected in CONSUMER_MODULE_HASHES.items():
        assert (
            hashlib.sha256((service_root / name).read_bytes()).hexdigest() == expected
        )
    assert semantics["schema_version"] == "dspx-oracle-semantic-code-semantics-v1"


def test_requests_are_exact_and_gate5_local_normalization_matches_all_cases():
    gate4_cases = load_bound_cases(REPO)
    gate5_cases = load_verifier_cases(REPO)
    from dspx.services.program_oracle_semantic_gate5_semantics_v11 import (
        semantic_request_sha256 as local_sha,
    )

    for gate4, gate5 in zip(gate4_cases, gate5_cases, strict=True):
        request = normalized_semantic_request(gate4.materialized_request())
        assert set(request) == SEMANTIC_KEYS
        assert semantic_request_sha256(request) == local_sha(gate5)
    baseline = normalized_semantic_request(gate4_cases[0].materialized_request())
    with pytest.raises(SemanticV11Error, match="missing"):
        semantic_request_projection(
            {key: value for key, value in baseline.items() if key != "text"}
        )
    contract, semantics, _ = load_candidate(REPO)
    mutable = copy.deepcopy(contract["cases"][0])
    before = materialized_request(mutable, semantics).request_sha256
    mutable["hidden_labels"]["expected_codes"]["observations"] = ["forged"]
    assert materialized_request(mutable, semantics).request_sha256 == before


def test_reservation_comparison_covers_every_field_and_fixed_endpoint():
    from dspx.services.program_oracle_semantic_identity_v11 import (
        assert_exact_reservation,
    )

    expected = _reservation()
    replacements: dict[str, Any] = {
        "consumer_task_id": expected.consumer_task_id + 1,
        "ledger_sha256": "a" * 64,
        "process_id": "different-process",
        "case_id": "causal-calibration",
        "logical_request_id": "b" * 64,
        "transport_gate_id": "c" * 64,
        "semantic_request_sha256": "d" * 64,
        "contract_sha256": "e" * 64,
        "mode": "async",
        "requested_route": "dspy-lm-auth:other",
        "resolved_route": "openai:other:responses",
        "endpoint_origin_sha256": "f" * 64,
        "source_identity": {**expected.source_identity, "lock_sha256": "0" * 64},
        "dependency_identity": {
            **expected.dependency_identity,
            "dspy": {
                **expected.dependency_identity["dspy"],
                "payload_sha256": "0" * 64,
            },
        },
    }
    for field_name, value in replacements.items():
        with pytest.raises(SemanticV11Error, match="exact-field"):
            assert_exact_reservation(replace(expected, **{field_name: value}), expected)


def test_gate5_rejects_self_consistent_retained_reservation_receipt_tamper(tmp_path):
    journal, _, expected, artifact = _journal(tmp_path)
    wrapper_path = journal._root / "reservation.json"
    wrapper = json.loads(wrapper_path.read_bytes())
    tampered = replace(expected, endpoint_origin_sha256="f" * 64)
    wrapper["reservation"] = tampered.payload()
    wrapper["reservation_id"] = tampered.reservation_id
    wrapper_path.write_bytes(canonical(wrapper))
    inspected = gate5_inspect_journal(
        journal._root,
        expected=expected,
        artifact=artifact,
        semantic_outcome="semantic_error",
    )
    assert inspected["provider_outcome"]["provider_outcome_receipt"] == "rejected"
    assert (
        inspected["provider_outcome"]["reason"] == "retained_reservation_or_event_drift"
    )


@pytest.mark.parametrize(
    "marker",
    [
        {"schema_version": "wrong", "effect_possible": False},
        {
            "schema_version": "dspx-provider-outcome-poison-v1",
            "effect_possible": False,
            "extra": 1,
        },
        {
            "schema_version": "dspx-provider-outcome-inflight-v1",
            "sequence": 99,
            "effect_possible": False,
        },
    ],
)
def test_gate4_and_gate5_marker_checks_reject_malformed_schema_keys_and_sequence(
    tmp_path, marker
):
    journal, _, reservation, artifact = _journal(tmp_path)
    name = "inflight.json" if "sequence" in marker else "poisoned.json"
    path = journal._root / name
    path.write_bytes(canonical(marker))
    path.chmod(0o600)
    gate4 = inspect_journal(
        journal._root,
        expected=reservation,
        artifact=artifact,
        semantic_outcome="semantic_error",
    )
    gate5 = gate5_inspect_journal(
        journal._root,
        expected=reservation,
        artifact=artifact,
        semantic_outcome="semantic_error",
    )
    assert gate4.projection.reason == "journal_marker_invalid"
    assert gate5["provider_outcome"]["reason"] == "journal_marker_invalid"
    assert gate4.projection.external_effect_possible is True
    assert gate5["provider_outcome"]["external_effect_possible"] is True


def test_gate5_local_semantics_survive_gate4_common_defect_monkeypatch(
    monkeypatch, tmp_path
):
    case = load_verifier_cases(REPO)[0]
    gate4_case = load_bound_cases(REPO)[0]
    hidden = gate4_case.case["hidden_labels"]
    analysis = {
        **hidden["expected_codes"],
        "evidence_refs": hidden["expected_evidence_refs"],
        "confidence": 0.8,
    }
    bounded = validate_semantic_response(gate4_case, json.dumps(analysis))
    semantic = bounded.semantic_payload()
    exposed = cast(dict[str, Any], bounded.analysis)
    exposed["observations"].append("unknown-arbitrary-code")
    assert (
        "unknown-arbitrary-code" not in canonical(bounded.semantic_payload()).decode()
    )
    assert gate5_validate_semantic(case, semantic)["outcome"] == "score_pass"
    retained = _private(tmp_path / "prewrite")
    for code_field, arbitrary in (
        ("observations", "unknown-arbitrary-code"),
        ("evidence_refs", "ak:credential:sk-live-secret-shaped"),
    ):
        hostile = copy.deepcopy(analysis)
        hostile[code_field] = [arbitrary]
        report = validate_semantic_response(gate4_case, json.dumps(hostile))
        assert report.outcome == "semantic_error"
        assert arbitrary not in canonical(report.semantic_payload()).decode()
    wrong = copy.deepcopy(analysis)
    wrong["observations"] = ["local_quality_checks_failed"]
    wrong_report = validate_semantic_response(gate4_case, json.dumps(wrong))
    assert wrong_report.outcome == "score_miss"
    assert (
        gate5_validate_semantic(case, wrong_report.semantic_payload())["outcome"]
        == "score_miss"
    )
    assert list(retained.iterdir()) == []
    unknown = copy.deepcopy(semantic)
    unknown["analysis"]["observations"] = ["unknown-code"]
    unknown["analysis_sha256"] = sha256(canonical(unknown["analysis"]))
    with pytest.raises(SemanticV11Error, match="unknown code"):
        gate5_validate_semantic(case, unknown)
    extra = copy.deepcopy(semantic)
    extra["analysis"]["extra"] = []
    with pytest.raises(SemanticV11Error, match="field drift"):
        gate5_validate_semantic(case, extra)
    from dspx.services.program_oracle_semantic_gate5_semantics_v11 import (
        semantic_request_sha256 as local_request_sha,
    )

    before = local_request_sha(case)
    monkeypatch.setattr(
        "dspx.services.program_oracle_semantic_evaluation_v11.normalized_semantic_request",
        lambda *_: {"common-defect": True},
    )
    monkeypatch.setattr(
        "dspx.services.program_oracle_semantic_result_v11.validate_retained_semantic_result",
        lambda *_: {"common-defect": True},
    )
    assert local_request_sha(case) == before
    assert gate5_validate_semantic(case, semantic)["outcome"] == "score_pass"


@pytest.mark.parametrize("duplicate_field", ["observations", "evidence_refs"])
def test_gate4_gate5_duplicate_structured_values_are_semantic_error(
    duplicate_field,
):
    gate4_case = load_bound_cases(REPO)[0]
    gate5_case = load_verifier_cases(REPO)[0]
    hidden = gate4_case.case["hidden_labels"]
    analysis: dict[str, Any] = {
        **hidden["expected_codes"],
        "evidence_refs": hidden["expected_evidence_refs"],
        "confidence": 0.8,
    }
    selected = cast(list[str], analysis[duplicate_field])
    selected.append(selected[0])
    report = validate_semantic_response(gate4_case, json.dumps(analysis))
    assert report.outcome == "semantic_error"
    assert (
        gate5_validate_semantic(gate5_case, report.semantic_payload())["outcome"]
        == "semantic_error"
    )


def test_poison_inflight_precedence_remains_effect_indeterminate(tmp_path):
    journal, receipt, reservation, artifact = _journal(tmp_path)
    receipt.sink(_ReceiptEvent("wrapper_request_accepted"))
    receipt.sink(_ReceiptEvent("transport_effect_pending", gate_ordinal=1))
    marker = {
        "schema_version": "dspx-provider-outcome-inflight-v1",
        "sequence": 2,
        "effect_possible": True,
    }
    path = journal._root / "inflight.json"
    path.write_bytes(canonical(marker))
    path.chmod(0o600)
    inspected = inspect_fixture_journal(
        journal._root, expected=reservation, artifact=artifact
    )
    assert (
        inspected["provider_outcome"]["empirical_disposition"] == "effect_indeterminate"
    )


def test_pure_semantic_reports_are_authority_false_and_no_writer_accepts_them():
    case = load_bound_cases(REPO)[0]
    hidden = case.case["hidden_labels"]
    analysis = {
        **hidden["expected_codes"],
        "evidence_refs": hidden["expected_evidence_refs"],
        "confidence": 0.8,
    }
    report = validate_semantic_response(case, json.dumps(analysis))
    assert report.outcome == "score_pass"
    assert report.payload()["authority_granted"] is False
    result = importlib.import_module(
        "dspx.services.program_oracle_semantic_result_artifact_v11"
    )
    assert not any(name.startswith("write_") for name in vars(result))
    assert not hasattr(
        importlib.import_module(
            "dspx.services.program_oracle_semantic_adapter_v11"
        ).ReceiptSafeDspyLMAuthLM,
        "_invoke_once",
    )


def test_obsolete_live_minter_registry_and_writer_surfaces_are_absent(monkeypatch):
    root = REPO / "packages/dspx-core/src/dspx/services"
    modules = [
        importlib.import_module(f"dspx.services.{path.stem}")
        for path in root.glob("program_oracle_semantic_*_v11.py")
    ]
    forbidden = {
        "canonical_documents",
        "require_canonical_documents",
        "_mint_gate4_live_admission",
        "_mint_live_attempt_custody",
        "_mint_case_invocation_custody",
        "_mint_gate5_write_custody",
        "_write_independent_verification",
        "Gate4LiveAdmission",
        "LiveAttemptCustody",
        "CaseInvocationCustody",
        "Gate5VerificationCustody",
        "AuthorityValidationReport",
        "Gate5ValidationReport",
    }
    assert not {
        name for module in modules for name in forbidden if hasattr(module, name)
    }
    assert not (root / "program_oracle_semantic_custody_v11.py").exists()
    assert not (root / "program_oracle_semantic_runner_v11.py").exists()
    assert not (root / "program_oracle_semantic_terminal_v11.py").exists()
    gate5 = importlib.import_module("dspx.services.program_oracle_semantic_gate5_v11")
    monkeypatch.setattr(
        gate5,
        "_validate_gate5_documents",
        lambda **_kwargs: SimpleNamespace(
            gate5_task_id=1,
            gate5_evidence_id=2,
            task_contract_sha256="1" * 64,
            guardrails_sha256="2" * 64,
            evidence_sha256="3" * 64,
        ),
    )
    pure = gate5.validate_gate5_authority_documents(caller_mapping={})
    assert pure["authority_granted"] is False
    assert pure["live_execution_authorized"] is False
    state = importlib.import_module("dspx.services.program_oracle_semantic_state_v11")
    assert not any(
        callable(value) and "live" in name.lower()
        for name, value in vars(state).items()
    )


def test_public_lifecycle_surface_excludes_fixture_mutation():
    artifacts = importlib.import_module(
        "dspx.services.program_oracle_semantic_artifacts_v11"
    )
    state = importlib.import_module("dspx.services.program_oracle_semantic_state_v11")
    gate4 = importlib.import_module("dspx.services.program_oracle_semantic_gate4_v11")
    gate5 = importlib.import_module("dspx.services.program_oracle_semantic_gate5_v11")
    assert "consume_fixture_attempt" not in artifacts.__all__
    assert "consume_fixture_attempt" not in state.__all__
    assert not hasattr(artifacts, "consume_fixture_attempt")
    assert not hasattr(state, "consume_fixture_attempt")
    for module in (artifacts, state):
        assert not {
            name
            for name, value in vars(module).items()
            if not name.startswith("_")
            and callable(value)
            and name.startswith(("consume", "persist", "write"))
        }
    assert "execute_live_once" in gate4.__all__
    assert "verify_retained_once" in gate5.__all__
    assert "execute_live_once" not in gate5.__all__
    assert "verify_retained_once" not in gate4.__all__


def test_fixture_collision_and_gate_separation_remain_closed(tmp_path):
    state = _private(tmp_path / "fixture")
    binding = TaskBinding.create(93001, REQUIRED_LIVE_COMPLETION_KIND, state)
    assert_attempt_absent(state, binding)
    attempt = _consume_fixture_attempt(state, binding)
    assert attempt.live_authorized is False
    with pytest.raises(SemanticV11Error, match="already exists"):
        assert_attempt_absent(state, binding)
    assert (
        GATE5_DONE_CONTRACT["completion_kind"] != GATE4_DONE_CONTRACT["completion_kind"]
    )
    assert GATE5_GUARDRAILS != GATE4_GUARDRAILS


def test_retained_reader_is_authority_false_and_terminal_helpers_are_blocked(
    tmp_path,
):
    state = _private(tmp_path / "state")
    binding = TaskBinding.create(83001, REQUIRED_LIVE_COMPLETION_KIND, state)
    _consume_fixture_attempt(state, binding)
    with pytest.raises(TypeError):
        cast(Any, ConsumedAttempt)()
    forged = object.__new__(ConsumedAttempt)
    with pytest.raises(SemanticV11Error, match="consumed ledger invalid"):
        forged.require_retained()
    report = SemanticValidationReport(
        "caller-authored", "semantic_error", None, None, None
    )
    assert report.payload()["authority_granted"] is False
    artifacts_module = importlib.import_module(
        "dspx.services.program_oracle_semantic_artifacts_v11"
    )
    state_module = importlib.import_module(
        "dspx.services.program_oracle_semantic_state_v11"
    )
    assert not hasattr(artifacts_module, "write_exclusive")
    assert not hasattr(artifacts_module, "write_fixture_member")
    assert not hasattr(state_module, "write_exclusive")
    assert not hasattr(state_module, "write_fixture_member")
    artifacts_source = (
        REPO
        / "packages/dspx-core/src/dspx/services/program_oracle_semantic_artifacts_v11.py"
    ).read_text()
    state_source = (
        REPO
        / "packages/dspx-core/src/dspx/services/program_oracle_semantic_state_v11.py"
    ).read_text()
    gate5_source = (
        REPO
        / "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_v11.py"
    ).read_text()
    assert "_consume_live_attempt" not in artifacts_source + state_source
    assert "_write_attempt_state" not in state_source
    assert "_mint_gate5_write_custody" not in gate5_source
    assert "def require_live" not in artifacts_source + state_source
