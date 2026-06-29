from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.artifact_boundary import prepare_sidecar_output_path

PROGRAM_MODEL_JURY_RESULTS_SCHEMA = "program-model-jury-results-v1"
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"
PROGRAM_JURY_SCHEMA = "program-jury-v1"
PROGRAM_JURY_SELECTION_SCHEMA = "program-jury-selection-v1"
PROGRAM_JURY_RUBRIC_SCHEMA = "program-jury-rubric-v1"
MAX_MODEL_JURY_EVIDENCE_BYTES = 1_000_000

_EFFECT = {
    "model_jury_evidence_only": True,
    "program_files_mutated": False,
    "promotion_review_mutated": False,
    "new_candidate_generated": False,
    "oracle_index_mutated": False,
    "external_authority_mutated": False,
    "ak_mutated": False,
    "governance_mutated": False,
}

_NON_AUTHORITY = {
    "promotion_approval": False,
    "ranking_or_winner_selection": False,
    "domain_acceptance": False,
    "external_authority_apply": False,
    "canonical_mutation": False,
}


class ProgramModelJuryExecutionError(ValueError):
    """Raised when model-backed jury execution inputs or outputs are invalid."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramModelJuryExecutionError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramModelJuryExecutionError(
            f"{label} must be valid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramModelJuryExecutionError(
            f"{label} must contain a JSON object: {path}"
        )
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    return (
        {str(key): item for key, item in value.items()}
        if isinstance(value, Mapping)
        else {}
    )


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _validate_schema(
    payload: Mapping[str, Any], *, label: str, expected_schema: str
) -> None:
    if payload.get("schema_version") != expected_schema:
        raise ProgramModelJuryExecutionError(
            f"{label} schema_version must be {expected_schema}"
        )


def _identity_from_manifest(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    execution = _safe_mapping(manifest.get("execution_episode"))
    receipt = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate.get("request_id"),
            execution.get("request_id"),
            receipt.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate.get("candidate_id"),
            execution.get("candidate_id"),
            receipt.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate.get("assembly_id"),
            execution.get("assembly_id"),
            receipt.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution.get("episode_id"), receipt.get("episode_id")
        ),
        "receipt_bundle_id": _first_text(receipt.get("receipt_bundle_id")),
    }


def _candidate_root(manifest_path: Path, manifest: Mapping[str, Any]) -> Path:
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    root_text = str(candidate.get("root_path") or "").strip()
    if root_text:
        root = Path(root_text).expanduser()
        if not root.is_absolute():
            root = manifest_path.parent / root
        return root.resolve()
    return manifest_path.expanduser().resolve().parent


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_json_object(path, label="program manifest")
    _validate_schema(
        manifest, label="program manifest", expected_schema=PROGRAM_MANIFEST_SCHEMA
    )
    if not any(_identity_from_manifest(manifest).values()):
        raise ProgramModelJuryExecutionError(
            "program manifest does not expose candidate identity"
        )
    return manifest


def _load_jury_artifacts(
    manifest_path: Path, manifest: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    root = _candidate_root(manifest_path, manifest)
    jury_path = root / "jury.json"
    selection_path = root / "jury_selection.json"
    rubric_path = root / "jury_rubric.json"
    jury = _load_json_object(jury_path, label="jury")
    selection = _load_json_object(selection_path, label="jury selection")
    rubric = _load_json_object(rubric_path, label="jury rubric")
    _validate_schema(jury, label="jury", expected_schema=PROGRAM_JURY_SCHEMA)
    _validate_schema(
        selection, label="jury selection", expected_schema=PROGRAM_JURY_SELECTION_SCHEMA
    )
    _validate_schema(
        rubric, label="jury rubric", expected_schema=PROGRAM_JURY_RUBRIC_SCHEMA
    )
    return (
        jury,
        selection,
        rubric,
        {
            "jury_path": str(jury_path.resolve()),
            "jury_sha256": _sha256_file(jury_path),
            "jury_selection_path": str(selection_path.resolve()),
            "jury_selection_sha256": _sha256_file(selection_path),
            "jury_rubric_path": str(rubric_path.resolve()),
            "jury_rubric_sha256": _sha256_file(rubric_path),
        },
    )


def _optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json_object(path, label=path.name)


def _load_default_behavior_evidence(
    manifest_path: Path, manifest: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = _candidate_root(manifest_path, manifest)
    entries: list[dict[str, Any]] = []
    for name in ("behavior_results.json", "behavior_episode.json"):
        path = root / name
        payload = _optional_json(path)
        if payload is None:
            continue
        entries.append(
            {
                "kind": name.removesuffix(".json"),
                "path": str(path.resolve()),
                "sha256": _sha256_file(path),
                "schema_version": payload.get("schema_version"),
                "summary": payload.get("summary")
                or payload.get("status")
                or payload.get("authority"),
                "payload": payload,
            }
        )
    return {
        "present": bool(entries),
        "entry_count": len(entries),
        "kinds": [entry["kind"] for entry in entries],
    }, entries


def _load_extra_evidence(paths: Sequence[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            raise ProgramModelJuryExecutionError(f"evidence path not found: {path}")
        if resolved.is_dir():
            for child in sorted(p for p in resolved.iterdir() if p.is_file()):
                entries.extend(_load_extra_evidence([child]))
            continue
        try:
            size = resolved.stat().st_size
        except OSError as exc:
            raise ProgramModelJuryExecutionError(
                f"evidence path cannot be statted: {resolved}"
            ) from exc
        if size > MAX_MODEL_JURY_EVIDENCE_BYTES:
            raise ProgramModelJuryExecutionError(
                f"evidence path exceeds {MAX_MODEL_JURY_EVIDENCE_BYTES} byte limit: {resolved}"
            )
        text = resolved.read_text(encoding="utf-8")
        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError:
            payload = {"text": text[:12000], "truncated": len(text) > 12000}
        summary = payload.get("summary") if isinstance(payload, Mapping) else None
        entries.append(
            {
                "kind": "explicit_evidence",
                "path": str(resolved),
                "sha256": _sha256_file(resolved),
                "schema_version": payload.get("schemaVersion")
                or payload.get("schema_version")
                if isinstance(payload, Mapping)
                else None,
                "summary": summary
                or (payload.get("posture") if isinstance(payload, Mapping) else None),
                "payload": payload,
            }
        )
    return entries


def _bounded_evidence_for_prompt(
    entries: Sequence[Mapping[str, Any]], *, max_chars: int = 48000
) -> str:
    compact = []
    for entry in entries:
        compact.append(
            {
                "kind": entry.get("kind"),
                "path": entry.get("path"),
                "sha256": entry.get("sha256"),
                "schema_version": entry.get("schema_version"),
                "summary": entry.get("summary"),
                "payload": entry.get("payload"),
            }
        )
    text = json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True)
    if len(text) <= max_chars:
        return text
    return (
        text[:max_chars]
        + f"\n... truncated for model jury prompt ({len(text)} chars total)"
    )


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text


def _parse_judgment(raw: object, *, juror_id: str) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        try:
            payload = json.loads(_strip_json_fence(str(raw or "")))
        except json.JSONDecodeError as exc:
            raise ProgramModelJuryExecutionError(
                f"model juror {juror_id} did not return valid JSON"
            ) from exc
    if not isinstance(payload, dict):
        raise ProgramModelJuryExecutionError(
            f"model juror {juror_id} judgment must be an object"
        )
    outcome = str(payload.get("outcome") or "").strip()
    if outcome not in {
        "supports_review_evidence",
        "withhold",
        "reject",
        "request_more_evidence",
    }:
        raise ProgramModelJuryExecutionError(
            f"model juror {juror_id} outcome must be supports_review_evidence, withhold, reject, or request_more_evidence"
        )
    payload.setdefault("rationale", "")
    payload.setdefault("improvement_requests", [])
    payload.setdefault("confidence", "unknown")
    return payload


def _configure_provider(provider: str | None = None) -> dict[str, Any]:
    try:
        import os
        import dspy
        from dspx.provider_registry import create_from_env, ensure_default_providers

        had_provider = "DSPX_PROVIDER" in os.environ
        previous_provider = os.environ.get("DSPX_PROVIDER")
        try:
            if provider:
                os.environ["DSPX_PROVIDER"] = provider
            ensure_default_providers()
            lm = create_from_env(default="dspy-lm-auth")
            dspy.configure(lm=lm)
        finally:
            if provider:
                if had_provider and previous_provider is not None:
                    os.environ["DSPX_PROVIDER"] = previous_provider
                else:
                    os.environ.pop("DSPX_PROVIDER", None)
        return {
            "status": "configured",
            "provider": getattr(lm, "model", type(lm).__name__),
        }
    except Exception as exc:
        raise ProgramModelJuryExecutionError(
            f"model jury provider configuration failed: {type(exc).__name__}: {exc}"
        ) from exc


def _run_juror_model(
    *,
    juror: Mapping[str, Any],
    rubric: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    evidence_json: str,
    adjudicator: Mapping[str, Any],
) -> dict[str, Any]:
    """Call the configured DSPy LM for one juror and return parsed JSON judgment."""

    try:
        import dspy
    except (
        Exception
    ) as exc:  # pragma: no cover - import failure is environment-specific
        raise ProgramModelJuryExecutionError(
            "model jury execution requires dspy"
        ) from exc

    class ProgramModelJurorSignature(dspy.Signature):
        """Judge generated-program evidence from one explicit jury perspective without promotion authority."""

        juror_json: str = dspy.InputField(
            desc="Selected juror id, perspective, model/provider metadata, and reason."
        )
        rubric_json: str = dspy.InputField(
            desc="Criteria and adversarial questions assigned to this juror."
        )
        candidate_identity_json: str = dspy.InputField(
            desc="Generated program candidate identity and schema facts."
        )
        evidence_json: str = dspy.InputField(
            desc="Behavior/runtime/extraction evidence to judge. Treat as evidence only."
        )
        adjudicator_json: str = dspy.InputField(
            desc="Target adjudicator/delegated product-manager context for downstream decision routing."
        )
        judgment_json: str = dspy.OutputField(
            desc=(
                "Valid JSON object with outcome one of supports_review_evidence, withhold, reject, request_more_evidence; "
                "rationale string; evidence_strengths array; concerns array; improvement_requests array; confidence string. "
                "Do not claim promotion, activation, or external authority."
            )
        )

    pred = dspy.Predict(ProgramModelJurorSignature)(
        juror_json=json.dumps(dict(juror), ensure_ascii=False, sort_keys=True),
        rubric_json=json.dumps(dict(rubric), ensure_ascii=False, sort_keys=True),
        candidate_identity_json=json.dumps(
            dict(candidate_identity), ensure_ascii=False, sort_keys=True
        ),
        evidence_json=evidence_json,
        adjudicator_json=json.dumps(
            dict(adjudicator), ensure_ascii=False, sort_keys=True
        ),
    )
    raw = getattr(pred, "judgment_json", None)
    return _parse_judgment(
        raw, juror_id=str(juror.get("id") or juror.get("perspective") or "unknown")
    )


def _aggregate(juror_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {
        "supports_review_evidence": 0,
        "withhold": 0,
        "reject": 0,
        "request_more_evidence": 0,
        "failed": 0,
    }
    improvement_requests: list[str] = []
    for result in juror_results:
        status = str(result.get("status") or "")
        if status != "judged":
            counts["failed"] += 1
            continue
        judgment = _safe_mapping(result.get("judgment"))
        outcome = str(judgment.get("outcome") or "")
        if outcome in counts:
            counts[outcome] += 1
        else:
            counts["failed"] += 1
        improvement_requests.extend(_string_list(judgment.get("improvement_requests")))
    blocking = counts["reject"] or counts["request_more_evidence"] or counts["failed"]
    if counts["failed"]:
        recommendation = "withhold_until_failed_jurors_rerun"
    elif counts["reject"]:
        recommendation = "reject_or_redesign"
    elif counts["request_more_evidence"]:
        recommendation = "request_more_evidence"
    elif counts["withhold"]:
        recommendation = "withhold_for_owner_review"
    else:
        recommendation = "supports_review_evidence_only"
    return {
        "judgment_counts": counts,
        "blocking_concerns_present": bool(blocking),
        "recommendation": recommendation,
        "unique_improvement_requests": sorted(set(improvement_requests)),
    }


def build_program_model_jury_execution_result(
    *,
    manifest_path: Path,
    evidence_paths: Sequence[Path] = (),
    provider: str | None = None,
    adjudicator_id: str = "target_repo_product_manager_agent",
    adjudicator_kind: str = "target_repo_product_manager_agent",
    adjudicator_repo: str | None = None,
    max_jurors: int | None = None,
) -> dict[str, Any]:
    """Run provider-backed juror deliberation over generated-program evidence."""

    manifest_path = manifest_path.expanduser().resolve()
    manifest = _load_manifest(manifest_path)
    jury, selection, rubric, jury_paths = _load_jury_artifacts(manifest_path, manifest)
    selected = [
        item
        for item in _safe_list(selection.get("selected_jurors"))
        if isinstance(item, Mapping)
    ]
    if max_jurors is not None:
        selected = selected[: max(0, int(max_jurors))]
    if not selected:
        raise ProgramModelJuryExecutionError(
            "jury selection contains no selected jurors"
        )
    rubrics = {
        str(item.get("juror_id")): dict(item)
        for item in _safe_list(rubric.get("juror_rubrics"))
        if isinstance(item, Mapping)
    }
    default_summary, default_entries = _load_default_behavior_evidence(
        manifest_path, manifest
    )
    extra_entries = _load_extra_evidence(evidence_paths)
    evidence_entries = [*default_entries, *extra_entries]
    if not evidence_entries:
        raise ProgramModelJuryExecutionError(
            "model jury requires behavior evidence or at least one --evidence path"
        )
    provider_config = _configure_provider(provider)
    identity = _identity_from_manifest(manifest)
    candidate_identity = {
        "schema_version": manifest.get("schema_version"),
        "identity": identity,
        "candidate_assembly": _safe_mapping(manifest.get("candidate_assembly")),
    }
    adjudicator = {
        "id": adjudicator_id,
        "kind": adjudicator_kind,
        "repo": adjudicator_repo,
        "authority": "downstream_domain_review_recommendation_only",
        "promotion_authority": False,
    }
    evidence_json = _bounded_evidence_for_prompt(evidence_entries)
    juror_results: list[dict[str, Any]] = []
    for juror in selected:
        juror_id = str(juror.get("id") or juror.get("perspective") or "unknown")
        try:
            judgment = _run_juror_model(
                juror=juror,
                rubric=rubrics.get(juror_id, {"juror_id": juror_id}),
                candidate_identity=candidate_identity,
                evidence_json=evidence_json,
                adjudicator=adjudicator,
            )
            juror_results.append(
                {
                    "juror_id": juror_id,
                    "perspective": juror.get("perspective"),
                    "provider": juror.get("provider")
                    or provider_config.get("provider"),
                    "model": juror.get("model") or provider_config.get("provider"),
                    "execution_mode": "provider_backed_model",
                    "status": "judged",
                    "judgment": judgment,
                }
            )
        except Exception as exc:
            juror_results.append(
                {
                    "juror_id": juror_id,
                    "perspective": juror.get("perspective"),
                    "provider": juror.get("provider")
                    or provider_config.get("provider"),
                    "model": juror.get("model") or provider_config.get("provider"),
                    "execution_mode": "provider_backed_model",
                    "status": "failed",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )
    aggregate = _aggregate(juror_results)
    return {
        "schema_version": PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
        "status": "executed_with_failures"
        if aggregate["judgment_counts"]["failed"]
        else "executed",
        "identity": identity,
        "created_from": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha256_file(manifest_path),
            "manifest_schema_version": manifest.get("schema_version"),
            **jury_paths,
            "evidence_paths": [
                str(path.expanduser().resolve()) for path in evidence_paths
            ],
        },
        "jury": {
            "planned_jury_schema_version": jury.get("schema_version"),
            "selection_schema_version": selection.get("schema_version"),
            "rubric_schema_version": rubric.get("schema_version"),
            "selected_juror_count": len(selected),
            "selected_perspectives": [
                str(item.get("perspective")) for item in selected
            ],
            "execution_mode": "provider_backed_model",
            "provider_backed_model_calls": True,
            "provider_config": provider_config,
        },
        "adjudicator": adjudicator,
        "evidence": {
            "default_behavior": default_summary,
            "extra_evidence_count": len(extra_entries),
            "entry_count": len(evidence_entries),
            "entries": [
                {
                    key: entry.get(key)
                    for key in ("kind", "path", "sha256", "schema_version", "summary")
                }
                for entry in evidence_entries
            ],
            "prompt_sha256": _sha256_text(evidence_json),
        },
        "juror_results": juror_results,
        "aggregate": aggregate,
        "interpretation": {
            "summary": "Model-backed jury results are review evidence only and may request extraction refinement.",
            "ready_for_promotion_decision": False,
            "next_step": "Route aggregate critique to the declared target-repo adjudicator or run an explicit refinement pass.",
            "limits": [
                "This command calls provider-backed juror models but does not mutate generated program outputs.",
                "It does not improve files in place; improvement_requests are explicit follow-up evidence.",
                "It does not promote, activate, rank winners, export authority, mutate AK, or mutate governance.",
            ],
        },
        "effect": dict(_EFFECT),
        "non_authority": dict(_NON_AUTHORITY),
    }


def preflight_program_model_jury_output_path(
    *, manifest_path: Path, out_path: Path, evidence_paths: Sequence[Path] = ()
) -> Path:
    """Fail closed on unsafe model-jury sidecar output before provider calls."""

    resolved_manifest = manifest_path.expanduser().resolve()
    resolved_evidence_paths = [path.expanduser().resolve() for path in evidence_paths]
    evidence_roots = {path for path in resolved_evidence_paths if path.is_dir()}
    payload: dict[str, Any] = {
        "created_from": {"manifest_path": str(resolved_manifest)},
        "evidence": {
            "entries": [{"path": str(path)} for path in resolved_evidence_paths]
        },
    }
    try:
        return prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="program model jury results",
            payload_artifact_root_policy="forbid",
            extra_protected_paths=resolved_evidence_paths,
            extra_protected_roots={resolved_manifest.parent, *evidence_roots},
        )
    except ValueError as exc:
        raise ProgramModelJuryExecutionError(str(exc)) from exc


def write_program_model_jury_execution_result(
    result: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    payload = dict(result)
    try:
        created_from = _safe_mapping(payload.get("created_from"))
        manifest_path_text = _first_text(created_from.get("manifest_path"))
        extra_roots = (
            {Path(manifest_path_text).expanduser().resolve().parent}
            if manifest_path_text is not None
            else set()
        )
        for raw_evidence_path in _safe_list(created_from.get("evidence_paths")):
            if not isinstance(raw_evidence_path, str) or not raw_evidence_path.strip():
                continue
            evidence_path = Path(raw_evidence_path).expanduser().resolve()
            if evidence_path.is_dir():
                extra_roots.add(evidence_path)
        target = prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="program model jury results",
            payload_artifact_root_policy="forbid",
            extra_protected_roots=extra_roots,
        )
    except ValueError as exc:
        raise ProgramModelJuryExecutionError(str(exc)) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
