# summary: "Executes receipt-bound generated-program runtime replay in an isolated temporary sandbox."
# read_when:
#   - "Changing replay subprocess isolation, reproduction checks, or unexpected-effect detection."

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, cast

from dspx.provider_runtime import sanitize_text
from dspx.run_receipts import (
    EXECUTION_REPLAY_POLICY_VERSION,
    PROGRAM_RUNTIME_REPLAY_CONTRACT_MODES,
    canonical_replay_identity_hash,
    current_execution_replay_runtime_identity,
    load_run_receipt,
    valid_program_runtime_expected_episode,
)
from dspx.services.program_execution_replay import (
    PROGRAM_RUNTIME_REPLAY_STRATEGY,
    _ALLOWED_ENVIRONMENT_KEYS,
    _EFFECTS,
    _MAX_DIAGNOSTIC_CHARS,
    _add_error,
    _build_replay_evidence,
    _canonical_hash,
    _exclusive_publish,
    _hash_tree,
    _load_json_object,
    _observed_outputs,
    _prepare_replay_target,
    _replay_failure_code,
    _resolved_bound_path,
    _safe_mapping,
    _sha256_file,
)
from dspx.services.program_runtime_episode import (
    load_validated_program_runtime_episode_bundle,
)
from dspx.services.run_replay_service import check_run_receipt
from dspx.services.replay_claims import build_replay_claim_matrix


def _legacy_behavior_without_provider(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(value))
    normalized.pop("provider", None)
    return normalized


def _legacy_traces_without_behavior_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(value))
    sources = normalized.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if (
                isinstance(source, dict)
                and source.get("path") == "behavior_results.json"
            ):
                source["content_hash"] = "<provider-normalized-behavior-hash>"
    return normalized


def _legacy_oracle_without_provider_dependent_hashes(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = deepcopy(dict(value))
    behavior = normalized.get("behavior")
    if isinstance(behavior, dict) and "result_hash" in behavior:
        behavior["result_hash"] = "<provider-normalized-behavior-hash>"
    sources = normalized.get("source_artifacts")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            if source.get("path") == "behavior_results.json":
                source["content_hash"] = "<provider-normalized-behavior-hash>"
            elif source.get("path") == "program_runtime_traces.json":
                source["content_hash"] = "<provider-normalized-traces-hash>"
    return normalized


def execute_program_runtime_receipt_impl(
    meta_path: Path, replay_output: Path, report: dict[str, Any]
) -> dict[str, Any]:
    """Reproduce one supported stub-backed runtime episode and publish evidence."""

    report["replay_mode"] = "execute"
    report["replay_claims"] = build_replay_claim_matrix(
        mode="runtime_execution_reproduction",
        receipt_integrity_status=(
            "passed" if report.get("status") == "ok" else "not_established"
        ),
        execution_status="not_established",
    )
    report["execution"] = {
        "attempted": False,
        "strategy": PROGRAM_RUNTIME_REPLAY_STRATEGY,
        "effects": dict(_EFFECTS),
    }
    execution = cast(dict[str, Any], report["execution"])
    if report.get("status") != "ok":
        execution["blocked_reason"] = "receipt_or_artifact_drift"
        return report
    source_receipt_hash = _sha256_file(meta_path)
    receipt = load_run_receipt(meta_path)
    if receipt is None:
        return _add_error(
            report,
            code="execution_replay_policy_missing",
            message="runtime receipt is unavailable",
            status="invalid",
        )
    rebound_check = check_run_receipt(meta_path)
    if (
        rebound_check.get("status") != "ok"
        or _sha256_file(meta_path) != source_receipt_hash
    ):
        return _add_error(
            report,
            code="execution_replay_identity_drift",
            message="runtime receipt changed during replay validation",
        )
    if (
        receipt.get("run_kind") != "program-runtime"
        or receipt.get("provider") != "stub"
    ):
        return _add_error(
            report,
            code="execution_replay_unsupported_kind",
            message="only stub-backed program-runtime receipts are supported",
            status="invalid",
        )
    policy = _safe_mapping(receipt.get("execution_replay"))
    effects = _safe_mapping(policy.get("effects"))
    if (
        policy.get("schema_version") != EXECUTION_REPLAY_POLICY_VERSION
        or policy.get("supported") is not True
        or policy.get("strategy") != PROGRAM_RUNTIME_REPLAY_STRATEGY
        or policy.get("local_only") is not True
        or effects != _EFFECTS
    ):
        return _add_error(
            report,
            code="execution_replay_unsupported_effects",
            message="runtime receipt replay policy/effects are unsupported",
            status="invalid",
        )
    replay_inputs = _safe_mapping(receipt.get("replay_inputs"))
    provider_identity = _safe_mapping(policy.get("provider_identity"))
    runtime_identity = _safe_mapping(policy.get("runtime_identity"))
    output_identity = _safe_mapping(policy.get("output_identity"))
    provider_details = receipt.get("provider_details")
    expected_provider_identity = {
        "provider": receipt.get("provider"),
        "provider_details": dict(provider_details)
        if isinstance(provider_details, Mapping)
        else None,
    }
    current_runtime = current_execution_replay_runtime_identity()
    if (
        policy.get("input_hash") != canonical_replay_identity_hash(replay_inputs)
        or provider_identity.get("provider") != receipt.get("provider")
        or provider_identity.get("provider_details")
        != expected_provider_identity["provider_details"]
        or provider_identity.get("hash")
        != canonical_replay_identity_hash(expected_provider_identity)
        or runtime_identity.get("hash")
        != canonical_replay_identity_hash(current_runtime)
        or {key: value for key, value in runtime_identity.items() if key != "hash"}
        != current_runtime
        or output_identity != {"algorithm": "sha256", "hash": receipt.get("hash")}
    ):
        return _add_error(
            report,
            code="execution_replay_identity_drift",
            message="runtime receipt input/runtime identity drift",
        )
    contract_mode = replay_inputs.get("contract_mode")
    if (
        contract_mode not in PROGRAM_RUNTIME_REPLAY_CONTRACT_MODES
        or not valid_program_runtime_expected_episode(
            replay_inputs.get("expected_episode"), contract_mode=contract_mode
        )
        or replay_inputs.get("skip_oracle_index") is not True
        or replay_inputs.get("publication_preflight_requested") is not False
        or not isinstance(replay_inputs.get("replay_fixture_path"), str)
        or not isinstance(replay_inputs.get("replay_fixture_sha256"), str)
    ):
        return _add_error(
            report,
            code="execution_replay_unsupported_inputs",
            message="runtime replay inputs request unsupported behavior",
            status="invalid",
        )

    try:
        candidate_manifest = _resolved_bound_path(
            replay_inputs.get("candidate_manifest_path"),
            expected_hash=replay_inputs.get("candidate_manifest_sha256"),
            label="candidate manifest",
        )
        candidate_receipt = _resolved_bound_path(
            replay_inputs.get("candidate_receipt_path"),
            expected_hash=replay_inputs.get("candidate_receipt_sha256"),
            label="candidate receipt",
        )
        if candidate_receipt != candidate_manifest.with_name(
            f"{candidate_manifest.name}.meta.json"
        ):
            raise ValueError("candidate receipt path does not match candidate manifest")
        candidate_check = check_run_receipt(candidate_receipt)
        if candidate_check.get("status") != "ok":
            raise ValueError(
                "candidate generation receipt no longer passes integrity checks"
            )
        candidate_receipt_payload = load_run_receipt(candidate_receipt)
        if candidate_receipt_payload is None:
            raise ValueError("candidate generation receipt is unavailable")
        candidate_receipt_output = (
            Path(str(candidate_receipt_payload.get("output_path") or ""))
            .expanduser()
            .resolve()
        )
        if (
            candidate_receipt_payload.get("run_kind") != "program-gen"
            or candidate_receipt_output != candidate_manifest
            or candidate_receipt_payload.get("hash")
            != replay_inputs.get("candidate_manifest_sha256")
        ):
            raise ValueError(
                "candidate receipt does not identify the bound program manifest"
            )
        manifest_payload = _load_json_object(
            candidate_manifest, label="candidate manifest"
        )
        manifest_hash = _sha256_file(candidate_manifest)
        replay_fixture_path = _resolved_bound_path(
            replay_inputs.get("replay_fixture_path"),
            expected_hash=replay_inputs.get("replay_fixture_sha256"),
            label="runtime replay fixture",
        )
        if (
            replay_fixture_path.parent != meta_path.expanduser().resolve().parent
            or replay_fixture_path.name != "runtime_replay_fixture.json"
        ):
            raise ValueError("runtime replay fixture must be receipt-local")
        fixture_descriptor = os.open(
            replay_fixture_path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            fixture_stat = os.fstat(fixture_descriptor)
            if (
                not stat.S_ISREG(fixture_stat.st_mode)
                or stat.S_IMODE(fixture_stat.st_mode) != 0o600
            ):
                raise ValueError("runtime replay fixture mode must be 0600")
        finally:
            os.close(fixture_descriptor)
        replay_fixture = _load_json_object(
            replay_fixture_path, label="runtime replay fixture"
        )
        if (
            replay_fixture.get("schema_version") != "program-runtime-replay-fixture-v1"
            or replay_fixture.get("redaction_status") != "checked"
            or replay_fixture.get("retention_class") != "explicit_local_replay_fixture"
            or not isinstance(replay_fixture.get("runtime_inputs"), Mapping)
            or not isinstance(replay_fixture.get("stub_response"), Mapping)
        ):
            raise ValueError("runtime replay fixture contract is invalid")
        runtime_inputs = _safe_mapping(replay_fixture.get("runtime_inputs"))
        stub_response = _safe_mapping(replay_fixture.get("stub_response"))
        expected_inputs_text = (
            json.dumps(
                {"inputs": runtime_inputs},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        if hashlib.sha256(
            expected_inputs_text.encode("utf-8")
        ).hexdigest() != replay_inputs.get("runtime_inputs_sha256"):
            raise ValueError("runtime replay fixture inputs do not match receipt")
        source_episode_path = meta_path.with_name(
            meta_path.name.removesuffix(".meta.json")
        )
        runtime_root = source_episode_path.parent.resolve()
        candidate_root = candidate_manifest.parent.resolve()
        if (
            runtime_root == candidate_root
            or runtime_root in candidate_root.parents
            or candidate_root in runtime_root.parents
        ):
            raise ValueError(
                "runtime episode root must be disjoint from the source candidate"
            )
        source_bundle = load_validated_program_runtime_episode_bundle(
            runtime_episode_path=source_episode_path,
            expected_manifest_path=candidate_manifest,
            expected_manifest=manifest_payload,
            expected_manifest_sha256=manifest_hash,
            label="source runtime episode",
        )
        expected = _safe_mapping(replay_inputs.get("expected_episode"))
        legacy_provider_evidence = (
            "provider" not in source_bundle.runtime_episode
            and source_bundle.behavior_results.get("provider")
            == {"status": "configured", "provider": "stub/echo"}
        )
        source_legacy_traces = (
            _load_json_object(
                source_episode_path.parent / "program_runtime_traces.json",
                label="source legacy runtime traces",
            )
            if legacy_provider_evidence
            else {}
        )
        source_legacy_oracle = (
            _load_json_object(
                source_episode_path.parent / "oracle_evidence.json",
                label="source legacy Oracle evidence",
            )
            if legacy_provider_evidence
            else {}
        )
        source_observed = _observed_outputs(source_bundle.behavior_results)
        source_quality = _safe_mapping(
            source_bundle.behavior_results.get("quality_evaluation")
        )
        source_checks = {
            "runtime_episode_id": source_bundle.runtime_episode.get(
                "runtime_episode_id"
            )
            == expected.get("runtime_episode_id"),
            "contract_mode": source_bundle.runtime_episode.get("contract_mode")
            == contract_mode
            == expected.get("contract_mode"),
            "execution_status": source_bundle.runtime_episode.get("execution_status")
            == source_bundle.behavior_results.get("execution_status")
            == expected.get("execution_status"),
            "status": source_bundle.runtime_episode.get("status")
            == expected.get("status"),
            "quality_status": source_quality.get("status")
            == expected.get("quality_status"),
            "quality_evaluation": _canonical_hash(source_quality)
            == expected.get("quality_evaluation_sha256"),
            "observed_outputs": _canonical_hash(source_observed)
            == expected.get("observed_outputs_sha256"),
            "behavior_results": source_bundle.behavior_results_sha256
            == expected.get("behavior_results_sha256"),
            "runtime_episode": source_bundle.runtime_episode_sha256
            == expected.get("runtime_episode_sha256"),
        }
        if not all(source_checks.values()):
            raise ValueError(
                "source runtime episode no longer matches receipt evidence"
            )
        target = _prepare_replay_target(meta_path, replay_output)
    except FileExistsError as exc:
        return _add_error(
            report, code="execution_replay_output_exists", message=str(exc)
        )
    except Exception as exc:
        return _add_error(
            report,
            code="execution_replay_identity_drift",
            message=str(exc),
            status="invalid",
        )

    source_runtime_tree_before = _hash_tree(source_episode_path.parent)
    source_candidate_tree_before = _hash_tree(candidate_manifest.parent)
    with tempfile.TemporaryDirectory(prefix="dspx-program-replay-") as temporary_dir:
        sandbox = Path(temporary_dir)
        inputs_file = sandbox / "inputs.json"
        inputs_file.write_text(expected_inputs_text, encoding="utf-8")
        snapshot_candidate = sandbox / "candidate"
        shutil.copytree(candidate_manifest.parent, snapshot_candidate)
        snapshot_manifest = snapshot_candidate / candidate_manifest.name
        snapshot_receipt = snapshot_candidate / candidate_receipt.name
        snapshot_receipt_payload = _load_json_object(
            snapshot_receipt, label="snapshot candidate receipt"
        )
        snapshot_cache_file = (
            snapshot_candidate
            / ".cache"
            / "program"
            / f"{snapshot_receipt_payload['cache_key']}.json"
        )
        snapshot_receipt_payload["output_path"] = str(snapshot_manifest)
        snapshot_receipt_payload["cache_file"] = str(snapshot_cache_file)
        snapshot_receipt_payload["cache_enabled"] = False
        snapshot_receipt.write_text(
            json.dumps(
                snapshot_receipt_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if check_run_receipt(snapshot_receipt).get("status") != "ok":
            return _add_error(
                report,
                code="execution_replay_identity_drift",
                message="sandbox candidate snapshot failed integrity validation",
            )
        snapshot_manifest_payload = _load_json_object(
            snapshot_manifest, label="snapshot candidate manifest"
        )
        if _sha256_file(snapshot_manifest) != manifest_hash:
            return _add_error(
                report,
                code="execution_replay_identity_drift",
                message="sandbox candidate snapshot manifest drifted",
            )
        fresh_root = sandbox / "fresh"
        argv = [
            sys.executable,
            "-I",
            "-m",
            "dspx.cli.dspx",
            "program-run",
            "--manifest",
            str(snapshot_manifest),
            "--inputs",
            str(inputs_file),
            "--outdir",
            str(fresh_root),
            "--contract-mode",
            str(contract_mode),
            "--skip-oracle-index",
            "--json",
        ]
        scrubbed_env = {
            key: value
            for key, value in os.environ.items()
            if key in _ALLOWED_ENVIRONMENT_KEYS
        }
        scrubbed_env.update(
            {
                "HOME": str(sandbox),
                "DSPX_PROVIDER": "stub",
                "DSPX_REPLAY_FIXTURE_JSON": json.dumps(
                    stub_response, ensure_ascii=False, sort_keys=True
                ),
                "DSPX_CACHE_ENABLE": "0",
                "DSPX_CACHE_DIR": str(snapshot_candidate / ".cache"),
                "MLFLOW_ENABLE": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        execution["attempted"] = True
        try:
            completed = subprocess.run(
                argv,
                cwd=sandbox,
                env=scrubbed_env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return _add_error(
                report,
                code="execution_replay_process_failed",
                message=f"runtime replay process failed: {type(exc).__name__}",
            )
        if completed.returncode != 0:
            diagnostic = sanitize_text(
                (completed.stderr or completed.stdout)[-_MAX_DIAGNOSTIC_CHARS:],
                limit=500,
            )
            return _add_error(
                report,
                code="execution_replay_process_failed",
                message=(
                    f"runtime replay exited nonzero: {completed.returncode}; "
                    f"diagnostic: {diagnostic}"
                ),
            )
        try:
            fresh_receipt = fresh_root / "runtime_episode.json.meta.json"
            fresh_check = check_run_receipt(fresh_receipt)
            if fresh_check.get("status") != "ok":
                raise ValueError("fresh runtime receipt failed integrity checks")
            fresh_bundle = load_validated_program_runtime_episode_bundle(
                runtime_episode_path=fresh_root / "runtime_episode.json",
                expected_manifest_path=snapshot_manifest,
                expected_manifest=snapshot_manifest_payload,
                expected_manifest_sha256=manifest_hash,
                label="fresh runtime episode",
            )
            fresh_observed = _observed_outputs(fresh_bundle.behavior_results)
            fresh_episode = fresh_bundle.runtime_episode
            fresh_quality = _safe_mapping(
                fresh_bundle.behavior_results.get("quality_evaluation")
            )
            fresh_hashes = _safe_mapping(fresh_episode.get("artifact_hashes"))
            raw_output_files = fresh_episode.get("output_files")
            declared_output_files = {
                str(path)
                for path in (
                    raw_output_files if isinstance(raw_output_files, list) else []
                )
                if isinstance(path, str) and path
            }
            allowed_fresh_files = {
                "runtime_inputs.json",
                "behavior_results.json",
                "program_runtime_traces.json",
                "manifest.json",
                "oracle_evidence.json",
                "runtime_episode.json",
                "runtime_episode.json.meta.json",
                *declared_output_files,
            }
            observed_fresh_files = {
                path.relative_to(fresh_root).as_posix()
                for path in fresh_root.rglob("*")
                if path.is_file()
            }
            if any(path.is_symlink() for path in fresh_root.rglob("*")):
                raise ValueError("fresh runtime execution produced a symlink")
            unexpected_fresh_files = sorted(observed_fresh_files - allowed_fresh_files)
            if unexpected_fresh_files:
                raise ValueError(
                    "fresh runtime execution produced undeclared files: "
                    + ", ".join(unexpected_fresh_files)
                )
            reproduction_checks = {
                "runtime_episode_id_match": fresh_episode.get("runtime_episode_id")
                == expected.get("runtime_episode_id"),
                "contract_mode_match": fresh_episode.get("contract_mode")
                == contract_mode
                == expected.get("contract_mode"),
                "execution_status_match": fresh_episode.get("execution_status")
                == fresh_bundle.behavior_results.get("execution_status")
                == expected.get("execution_status"),
                "runtime_status_match": fresh_episode.get("status")
                == expected.get("status"),
                "quality_status_match": fresh_quality.get("status")
                == expected.get("quality_status"),
                "quality_evaluation_match": _canonical_hash(fresh_quality)
                == expected.get("quality_evaluation_sha256"),
                "observed_outputs_match": _canonical_hash(fresh_observed)
                == expected.get("observed_outputs_sha256"),
            }
            if legacy_provider_evidence:
                fresh_traces = _load_json_object(
                    fresh_root / "program_runtime_traces.json",
                    label="fresh legacy-compatible runtime traces",
                )
                fresh_oracle = _load_json_object(
                    fresh_root / "oracle_evidence.json",
                    label="fresh legacy-compatible Oracle evidence",
                )
                reproduction_checks.update(
                    {
                        "legacy_behavior_normalized_match": (
                            _legacy_behavior_without_provider(
                                source_bundle.behavior_results
                            )
                            == _legacy_behavior_without_provider(
                                fresh_bundle.behavior_results
                            )
                        ),
                        "legacy_runtime_traces_normalized_match": (
                            _legacy_traces_without_behavior_hash(source_legacy_traces)
                            == _legacy_traces_without_behavior_hash(fresh_traces)
                        ),
                        "legacy_oracle_evidence_normalized_match": (
                            _legacy_oracle_without_provider_dependent_hashes(
                                source_legacy_oracle
                            )
                            == _legacy_oracle_without_provider_dependent_hashes(
                                fresh_oracle
                            )
                        ),
                    }
                )
            else:
                reproduction_checks.update(
                    {
                        "behavior_results_hash_match": fresh_bundle.behavior_results_sha256
                        == expected.get("behavior_results_sha256"),
                        "runtime_traces_hash_match": fresh_hashes.get(
                            "program_runtime_traces_sha256"
                        )
                        == expected.get("program_runtime_traces_sha256"),
                        "oracle_evidence_hash_match": fresh_hashes.get(
                            "oracle_evidence_sha256"
                        )
                        == expected.get("oracle_evidence_sha256"),
                    }
                )
            report.setdefault("checks", {}).update(reproduction_checks)
            if not all(reproduction_checks.values()):
                raise ValueError(
                    "fresh runtime execution did not reproduce receipt-bound evidence"
                )
            source_runtime_tree_after = _hash_tree(source_episode_path.parent)
            source_candidate_tree_after = _hash_tree(candidate_manifest.parent)
            if (
                source_runtime_tree_after != source_runtime_tree_before
                or source_candidate_tree_after != source_candidate_tree_before
            ):
                raise ValueError(
                    "source candidate or runtime episode changed during replay"
                )
            evidence = _build_replay_evidence(
                stdout=completed.stdout,
                stderr=completed.stderr,
                source_receipt_hash=source_receipt_hash,
                manifest_hash=manifest_hash,
                candidate_receipt_hash=_sha256_file(candidate_receipt),
                expected=expected,
                reproduction_checks=reproduction_checks,
                behavior_results_hash=fresh_bundle.behavior_results_sha256,
                runtime_traces_hash=fresh_hashes.get("program_runtime_traces_sha256"),
                oracle_evidence_hash=fresh_hashes.get("oracle_evidence_sha256"),
                observed_outputs_hash=_canonical_hash(fresh_observed),
            )
            bytes_written = _exclusive_publish(
                receipt_root=meta_path.expanduser().resolve().parent,
                target=target,
                payload=evidence,
            )
        except Exception as exc:
            return _add_error(report, code=_replay_failure_code(exc), message=str(exc))

    report["status"] = "executed"
    report["replay_claims"] = evidence["replay_claims"]
    report["execution"] = {
        "attempted": True,
        "strategy": PROGRAM_RUNTIME_REPLAY_STRATEGY,
        "run_kind": "program-runtime",
        "provider": "stub",
        "source_receipt": str(meta_path),
        "source_output": str(source_episode_path),
        "replay_output": str(target),
        "bytes_written": bytes_written,
        "effects": dict(_EFFECTS),
        "evidence": evidence,
    }
    return report
