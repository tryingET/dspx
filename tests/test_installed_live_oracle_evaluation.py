# summary: "Tests the no-live installed corpus and Oracle evaluation contract."

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "scripts/ci/validate_installed_live_oracle_evaluation.py"
CONTRACT_PATH = (
    REPO_ROOT / "benchmarks/semantic/installed-live-oracle-evaluation-v1.json"
)
CORPUS_PATH = REPO_ROOT / "benchmarks/semantic/program-corpus-v2.json"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_installed_live_oracle_evaluation", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload() -> dict[str, Any]:
    payload = json.loads(CONTRACT_PATH.read_text())
    assert isinstance(payload, dict)
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _validate(
    module: ModuleType, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    return module.validate_contract(
        contract_path=contract_path,
        corpus_path=CORPUS_PATH,
        repo_root=REPO_ROOT,
    )


def test_checked_in_legacy_contract_fails_closed_after_typed_cutover() -> None:
    module = _load_validator()

    with pytest.raises(module.ContractValidationError, match="model roles source hash"):
        _validate(module)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(
            {"claims": {"release_readiness": True, "production_activation": True}}
        ),
        lambda payload: payload["source_corpus"].update(
            {"coverage_claim": "representative"}
        ),
        lambda payload: payload["source_corpus"]["thresholds"].update(
            {"min_overall_score": True}
        ),
        lambda payload: payload["attempt_budget"].update(
            {"provider_transport_call_count": 3}
        ),
        lambda payload: payload["attempt_budget"].update(
            {"selective_quality_rerun_allowed": True}
        ),
        lambda payload: payload.pop("live_behavior_acceptance"),
        lambda payload: payload["privacy_and_retention"].update(
            {"inspect_or_copy_credentials": True}
        ),
        lambda payload: payload["oracle_evaluation"]["semantic_analysis_lm"].update(
            {"acceptance": []}
        ),
        lambda payload: payload["oracle_evaluation"]["embedding_model"].update(
            {"production_semantic_claim_allowed": True}
        ),
        lambda payload: payload["oracle_evaluation"]["embedding_model"][
            "held_out_queries"
        ][0].update({"query": ""}),
        lambda payload: payload["oracle_evaluation"]["coordinate_store"].update(
            {"shared_store_connection_allowed_in_this_contract_check": True}
        ),
        lambda payload: payload["oracle_evaluation"].update({"sequence": []}),
        lambda payload: payload["contract_check_effects"].update(
            {"provider_calls": False}
        ),
        lambda payload: payload["nonclaims"].update({"release_readiness": 0}),
    ],
    ids=[
        "unknown-positive-claims",
        "representative-claim",
        "boolean-threshold",
        "provider-call-inference",
        "selective-rerun",
        "missing-live-acceptance",
        "credential-inspection",
        "missing-semantic-acceptance",
        "production-semantic-claim",
        "empty-held-out-query",
        "shared-store-connection",
        "missing-sequence",
        "boolean-zero-effect",
        "numeric-false-nonclaim",
    ],
)
def test_any_contract_byte_drift_fails_closed(tmp_path: Path, mutate: Any) -> None:
    module = _load_validator()
    payload = _payload()
    mutate(payload)
    contract = tmp_path / "contract.json"
    _write(contract, payload)

    with pytest.raises(module.ContractValidationError, match="contract file hash"):
        module._read_contract(contract)


def test_corpus_case_drift_fails_fixed_hash_binding() -> None:
    module = _load_validator()
    contract = _payload()
    corpus = json.loads(CORPUS_PATH.read_text())
    drifted = copy.deepcopy(corpus)
    drifted["cases"][0]["intent"]["objective"] = "Drifted objective"
    raw = (json.dumps(drifted, indent=2, sort_keys=True) + "\n").encode()

    with pytest.raises(module.ContractValidationError, match="corpus file hash"):
        module._validate_corpus(contract, drifted, raw)


def test_foreign_identical_corpus_path_is_rejected(tmp_path: Path) -> None:
    module = _load_validator()
    foreign = tmp_path / "program-corpus-v2.json"
    foreign.write_bytes(CORPUS_PATH.read_bytes())

    with pytest.raises(module.ContractValidationError, match="canonical path"):
        module.validate_contract(
            contract_path=CONTRACT_PATH,
            corpus_path=foreign,
            repo_root=REPO_ROOT,
        )


def test_foreign_identical_contract_path_is_rejected(tmp_path: Path) -> None:
    module = _load_validator()
    foreign = tmp_path / "installed-live-oracle-evaluation-v1.json"
    foreign.write_bytes(CONTRACT_PATH.read_bytes())

    with pytest.raises(module.ContractValidationError, match="canonical path"):
        module.validate_contract(
            contract_path=foreign,
            corpus_path=CORPUS_PATH,
            repo_root=REPO_ROOT,
        )


def test_model_role_source_shadowing_fails_fixed_hash_binding(tmp_path: Path) -> None:
    module = _load_validator()
    source = REPO_ROOT / "packages/dspx-core/src/dspx/model_roles.py"
    shadow = """
ORACLE_SEMANTIC_ROLE = ModelRole(
    name="oracle_semantic",
    model="codex/shadow-route",
    reasoning_effort="none",
    purpose="runtime shadow",
)

"""
    altered = source.read_text().replace(
        "_ROLE_DEFAULTS = {", shadow + "_ROLE_DEFAULTS = {", 1
    )
    altered_path = tmp_path / "model_roles.py"
    altered_path.write_text(altered)

    with pytest.raises(module.ContractValidationError, match="model roles source hash"):
        module._model_role_source_identity(altered_path)


def test_validator_has_only_standard_library_imports() -> None:
    tree = ast.parse(VALIDATOR_PATH.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert imported <= {
        "__future__",
        "ast",
        "hashlib",
        "json",
        "os",
        "stat",
        "sys",
        "collections.abc",
        "pathlib",
        "typing",
    }


def test_validator_subprocess_does_not_create_home_or_cache_state(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    cache = tmp_path / "cache"
    home.mkdir()
    cache.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CACHE_HOME": str(cache),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "model roles source hash" in result.stderr
    assert list(home.iterdir()) == []
    assert list(cache.iterdir()) == []
