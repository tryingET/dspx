from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

from dspx.coordinates.storage import CoordinateIndex, get_default_index_path
from dspx.dtos import ModuleSpec
from dspx.services.run_explain_service import explain_run_receipt


@dataclass(frozen=True)
class ModuleSynthesisEvidenceRequest:
    name: str
    description: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    use_signature: bool
    template_version: str | None

    @classmethod
    def from_spec(
        cls,
        spec: ModuleSpec,
        *,
        use_signature: bool,
    ) -> "ModuleSynthesisEvidenceRequest":
        options = spec.options if isinstance(spec.options, dict) else {}
        template_version = options.get("template_version")
        return cls(
            name=str(spec.name),
            description=str(spec.description or ""),
            inputs=tuple(str(item) for item in (spec.inputs or [])),
            outputs=tuple(str(item) for item in (spec.outputs or [])),
            use_signature=bool(use_signature),
            template_version=(
                str(template_version) if template_version not in {None, ""} else None
            ),
        )

    def to_replay_inputs(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "use_signature": self.use_signature,
            "template_version": self.template_version,
        }

    def oracle_query_text(self) -> str:
        replay_inputs = self.to_replay_inputs()
        return "\n".join(
            [
                f"name: {replay_inputs['name']}",
                f"description: {replay_inputs['description']}",
                f"inputs: {replay_inputs['inputs']}",
                f"outputs: {replay_inputs['outputs']}",
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "use_signature": self.use_signature,
            "template_version": self.template_version,
        }


@dataclass(frozen=True)
class ModuleSynthesisHistoricalDiagnostics:
    evidence_bundle_version: str | None
    historical_convergence_advisory: dict[str, Any] | None
    candidate_winner_priors: dict[str, Any] | None
    candidate_prior_audit: dict[str, Any] | None
    candidate_prior_divergence_explanation: dict[str, Any] | None
    candidate_prior_readiness_advisory: dict[str, Any] | None = None
    candidate_prior_counterfactual_advisory: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_bundle_version": self.evidence_bundle_version,
            "historical_convergence_advisory": self.historical_convergence_advisory,
            "candidate_winner_priors": self.candidate_winner_priors,
            "candidate_prior_audit": self.candidate_prior_audit,
            "candidate_prior_divergence_explanation": self.candidate_prior_divergence_explanation,
            "candidate_prior_readiness_advisory": self.candidate_prior_readiness_advisory,
            "candidate_prior_counterfactual_advisory": self.candidate_prior_counterfactual_advisory,
        }


@dataclass(frozen=True)
class ModuleSynthesisReceiptEvidence:
    receipt_path: str
    created_at: str | None
    run_kind: str
    provider: str
    template_version: str | None
    replay_inputs: dict[str, Any]
    output_path: str
    output_hash: str
    cache_key: str
    selected_candidate_id: str
    selected_candidate_rank: int
    ranked_candidate_ids: tuple[str, ...]
    ranking_policy_id: str
    ranking_policy_version: str | None
    validation_pass_count: int
    validation_total: int
    smoke_pass_count: int
    smoke_total: int
    evaluation_status: str | None
    promotion_status: str | None
    promotion_outcome: str | None
    synthesis: dict[str, Any] | None
    synthesis_request_id: str | None
    synthesis_candidate_ids: tuple[str, ...]
    synthesis_evaluation_ids: tuple[str, ...]
    synthesis_selection_policy: dict[str, Any] | None
    synthesis_ranked_candidates: tuple[dict[str, Any], ...]
    synthesis_promotion_shell: dict[str, Any] | None
    synthesis_promotion_decision: dict[str, Any] | None
    historical_diagnostics: ModuleSynthesisHistoricalDiagnostics | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_path": self.receipt_path,
            "created_at": self.created_at,
            "run_kind": self.run_kind,
            "provider": self.provider,
            "template_version": self.template_version,
            "replay_inputs": dict(self.replay_inputs),
            "output_path": self.output_path,
            "output_hash": self.output_hash,
            "cache_key": self.cache_key,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_candidate_rank": self.selected_candidate_rank,
            "ranked_candidate_ids": list(self.ranked_candidate_ids),
            "ranking_policy_id": self.ranking_policy_id,
            "ranking_policy_version": self.ranking_policy_version,
            "validation_pass_count": self.validation_pass_count,
            "validation_total": self.validation_total,
            "smoke_pass_count": self.smoke_pass_count,
            "smoke_total": self.smoke_total,
            "evaluation_status": self.evaluation_status,
            "promotion_status": self.promotion_status,
            "promotion_outcome": self.promotion_outcome,
            "synthesis": self.synthesis,
            "synthesis_request_id": self.synthesis_request_id,
            "synthesis_candidate_ids": list(self.synthesis_candidate_ids),
            "synthesis_evaluation_ids": list(self.synthesis_evaluation_ids),
            "synthesis_selection_policy": self.synthesis_selection_policy,
            "synthesis_ranked_candidates": list(self.synthesis_ranked_candidates),
            "synthesis_promotion_shell": self.synthesis_promotion_shell,
            "synthesis_promotion_decision": self.synthesis_promotion_decision,
            "synthesis_diagnostics": (
                self.historical_diagnostics.to_dict()
                if self.historical_diagnostics is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ModuleSynthesisReplayEvidence:
    replay_status: str
    replay_checks: dict[str, bool]
    local_facts: dict[str, Any]
    replay_error_codes: tuple[str, ...]
    replay_error_details: tuple[dict[str, str], ...]
    healthy: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_status": self.replay_status,
            "replay_checks": dict(self.replay_checks),
            "local_facts": dict(self.local_facts),
            "replay_error_codes": list(self.replay_error_codes),
            "replay_error_details": list(self.replay_error_details),
            "healthy": self.healthy,
        }


@dataclass(frozen=True)
class ModuleSynthesisEvidenceMatch:
    receipt: ModuleSynthesisReceiptEvidence
    replay: ModuleSynthesisReplayEvidence

    @property
    def positive_evidence(self) -> bool:
        return self.replay.healthy

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "replay": self.replay.to_dict(),
            "positive_evidence": self.positive_evidence,
        }


@dataclass(frozen=True)
class ModuleSynthesisOracleNeighbor:
    run_id: str
    similarity: float
    distance: float
    run_kind: str
    provider: str
    template_version: str | None
    source_path: str | None
    cache_key: str | None
    receipt_identity: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "similarity": self.similarity,
            "distance": self.distance,
            "run_kind": self.run_kind,
            "provider": self.provider,
            "template_version": self.template_version,
            "source_path": self.source_path,
            "cache_key": self.cache_key,
            "receipt_identity": dict(self.receipt_identity),
        }


@dataclass(frozen=True)
class ModuleSynthesisEvidenceBundle:
    request: ModuleSynthesisEvidenceRequest
    retrieval_order: tuple[str, ...]
    exact_match_receipts: tuple[ModuleSynthesisEvidenceMatch, ...]
    oracle_neighbors: tuple[ModuleSynthesisOracleNeighbor, ...]
    receipts_path: str
    oracle_index_path: str
    receipts_scanned: int
    oracle_query_text: str
    receipt_scan_errors: tuple[dict[str, Any], ...]
    exact_match_receipt_scan_errors: tuple[dict[str, Any], ...]
    oracle_lookup_status: str
    oracle_lookup_error: dict[str, str] | None

    @property
    def positive_evidence_count(self) -> int:
        return sum(1 for item in self.exact_match_receipts if item.positive_evidence)

    @property
    def oracle_index_available(self) -> bool:
        return self.oracle_lookup_status == "available"

    @property
    def receipt_scan_error_count(self) -> int:
        return len(self.receipt_scan_errors)

    @property
    def exact_match_receipt_scan_error_count(self) -> int:
        return len(self.exact_match_receipt_scan_errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "retrieval_order": list(self.retrieval_order),
            "exact_match_receipts": [
                item.to_dict() for item in self.exact_match_receipts
            ],
            "oracle_neighbors": [item.to_dict() for item in self.oracle_neighbors],
            "receipts_path": self.receipts_path,
            "oracle_index_path": self.oracle_index_path,
            "receipts_scanned": self.receipts_scanned,
            "oracle_query_text": self.oracle_query_text,
            "receipt_scan_errors": [dict(item) for item in self.receipt_scan_errors],
            "receipt_scan_error_count": self.receipt_scan_error_count,
            "exact_match_receipt_scan_errors": [
                dict(item) for item in self.exact_match_receipt_scan_errors
            ],
            "exact_match_receipt_scan_error_count": self.exact_match_receipt_scan_error_count,
            "oracle_lookup_status": self.oracle_lookup_status,
            "oracle_lookup_error": (
                dict(self.oracle_lookup_error)
                if isinstance(self.oracle_lookup_error, Mapping)
                else self.oracle_lookup_error
            ),
            "oracle_index_available": self.oracle_index_available,
            "positive_evidence_count": self.positive_evidence_count,
        }


def _parse_created_at(raw: object) -> datetime:
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _as_dict(value: object) -> dict[str, Any]:
    return dict(cast(Mapping[str, Any], value)) if isinstance(value, Mapping) else {}


def _as_str_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _as_ranked_candidates(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            out.append(dict(cast(Mapping[str, Any], item)))
    return tuple(out)


def _as_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            return default
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return default


def _optional_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    return text or None


def _exact_match_request(
    receipt: Mapping[str, Any],
    request: ModuleSynthesisEvidenceRequest,
) -> bool:
    if str(receipt.get("run_kind") or "") != "module-gen":
        return False

    replay_inputs = _as_dict(receipt.get("replay_inputs"))
    return _request_tuple_from_replay_inputs(
        replay_inputs
    ) == _request_tuple_from_request(request)


def _exact_match_receipt_issue(
    meta_path: Path,
    receipt: Mapping[str, Any],
) -> dict[str, Any] | None:
    run_summary = _as_dict(receipt.get("run_summary"))
    if str(run_summary.get("backend") or "") != "synthesis_runtime":
        return {
            "receipt_path": str(meta_path),
            "code": "receipt_backend_not_synthesis_runtime",
            "message": "exact-match receipt backend is not synthesis_runtime",
            "stage": "eligibility",
        }

    selected_candidate_id = str(run_summary.get("selected_candidate_id") or "").strip()
    if not selected_candidate_id:
        return {
            "receipt_path": str(meta_path),
            "code": "receipt_missing_selected_candidate_id",
            "message": "exact-match receipt missing selected_candidate_id",
            "stage": "eligibility",
        }

    selected_candidate_rank = _as_int(
        run_summary.get("selected_candidate_rank"), default=0
    )
    if selected_candidate_rank <= 0:
        return {
            "receipt_path": str(meta_path),
            "code": "receipt_invalid_selected_candidate_rank",
            "message": "exact-match receipt has invalid selected_candidate_rank",
            "stage": "eligibility",
        }

    ranked_candidate_ids = _as_str_list(run_summary.get("ranked_candidate_ids"))
    if not ranked_candidate_ids:
        return {
            "receipt_path": str(meta_path),
            "code": "receipt_missing_ranked_candidate_ids",
            "message": "exact-match receipt missing ranked_candidate_ids",
            "stage": "eligibility",
        }
    if selected_candidate_id not in ranked_candidate_ids:
        return {
            "receipt_path": str(meta_path),
            "code": "receipt_selected_candidate_not_ranked",
            "message": "exact-match receipt selected_candidate_id is absent from ranked_candidate_ids",
            "stage": "eligibility",
        }

    ranking_policy_id = str(run_summary.get("ranking_policy_id") or "").strip()
    if not ranking_policy_id:
        return {
            "receipt_path": str(meta_path),
            "code": "receipt_missing_ranking_policy_id",
            "message": "exact-match receipt missing ranking_policy_id",
            "stage": "eligibility",
        }

    return None


def _request_tuple_from_replay_inputs(
    replay_inputs: Mapping[str, Any],
) -> tuple[Any, ...]:
    return (
        str(replay_inputs.get("name") or ""),
        str(replay_inputs.get("description") or ""),
        tuple(
            str(item)
            for item in (replay_inputs.get("inputs") or [])
            if item is not None
        ),
        tuple(
            str(item)
            for item in (replay_inputs.get("outputs") or [])
            if item is not None
        ),
        bool(replay_inputs.get("use_signature")),
        (
            str(replay_inputs.get("template_version"))
            if replay_inputs.get("template_version") not in {None, ""}
            else None
        ),
    )


def _request_tuple_from_request(
    request: ModuleSynthesisEvidenceRequest,
) -> tuple[Any, ...]:
    return (
        request.name,
        request.description,
        tuple(request.inputs),
        tuple(request.outputs),
        bool(request.use_signature),
        request.template_version,
    )


def _receipt_paths(scan_path: Path) -> list[Path]:
    if scan_path.is_file():
        return [scan_path] if scan_path.name.endswith(".meta.json") else []
    if not scan_path.exists():
        return []
    return sorted(scan_path.rglob("*.meta.json"))


def _load_receipt_for_evidence(
    meta_path: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        raw = meta_path.read_text(encoding="utf-8")
    except Exception as exc:
        return None, {
            "receipt_path": str(meta_path),
            "code": "receipt_read_failed",
            "message": str(exc),
            "error_type": exc.__class__.__name__,
            "stage": "read",
        }

    try:
        loaded = json.loads(raw)
    except Exception as exc:
        return None, {
            "receipt_path": str(meta_path),
            "code": "receipt_invalid_json",
            "message": str(exc),
            "error_type": exc.__class__.__name__,
            "stage": "parse",
        }

    if not isinstance(loaded, dict):
        return None, {
            "receipt_path": str(meta_path),
            "code": "receipt_json_not_object",
            "message": "receipt payload is not a JSON object",
            "stage": "parse",
        }

    return loaded, None


def _extract_historical_diagnostics(
    receipt: Mapping[str, Any],
) -> ModuleSynthesisHistoricalDiagnostics | None:
    raw = receipt.get("synthesis_diagnostics")
    if not isinstance(raw, Mapping):
        return None
    diagnostics = _as_dict(raw)
    return ModuleSynthesisHistoricalDiagnostics(
        evidence_bundle_version=_optional_str(
            diagnostics.get("evidence_bundle_version")
        ),
        historical_convergence_advisory=(
            _as_dict(diagnostics.get("historical_convergence_advisory"))
            if isinstance(diagnostics.get("historical_convergence_advisory"), Mapping)
            else None
        ),
        candidate_winner_priors=(
            _as_dict(diagnostics.get("candidate_winner_priors"))
            if isinstance(diagnostics.get("candidate_winner_priors"), Mapping)
            else None
        ),
        candidate_prior_audit=(
            _as_dict(diagnostics.get("candidate_prior_audit"))
            if isinstance(diagnostics.get("candidate_prior_audit"), Mapping)
            else None
        ),
        candidate_prior_divergence_explanation=(
            _as_dict(diagnostics.get("candidate_prior_divergence_explanation"))
            if isinstance(
                diagnostics.get("candidate_prior_divergence_explanation"), Mapping
            )
            else None
        ),
        candidate_prior_readiness_advisory=(
            _as_dict(diagnostics.get("candidate_prior_readiness_advisory"))
            if isinstance(
                diagnostics.get("candidate_prior_readiness_advisory"), Mapping
            )
            else None
        ),
        candidate_prior_counterfactual_advisory=(
            _as_dict(diagnostics.get("candidate_prior_counterfactual_advisory"))
            if isinstance(
                diagnostics.get("candidate_prior_counterfactual_advisory"), Mapping
            )
            else None
        ),
    )


def _build_receipt_evidence(
    meta_path: Path,
    receipt: Mapping[str, Any],
) -> ModuleSynthesisReceiptEvidence:
    replay_inputs = _as_dict(receipt.get("replay_inputs"))
    run_summary = _as_dict(receipt.get("run_summary"))
    historical_diagnostics = _extract_historical_diagnostics(receipt)
    return ModuleSynthesisReceiptEvidence(
        receipt_path=str(meta_path),
        created_at=(
            str(receipt.get("created_at"))
            if receipt.get("created_at") is not None
            else None
        ),
        run_kind=str(receipt.get("run_kind") or ""),
        provider=str(receipt.get("provider") or ""),
        template_version=(
            str(receipt.get("template_version"))
            if receipt.get("template_version") not in {None, ""}
            else None
        ),
        replay_inputs={
            "name": str(replay_inputs.get("name") or ""),
            "description": str(replay_inputs.get("description") or ""),
            "inputs": list(_as_str_list(replay_inputs.get("inputs"))),
            "outputs": list(_as_str_list(replay_inputs.get("outputs"))),
            "use_signature": bool(replay_inputs.get("use_signature")),
            "template_version": (
                str(replay_inputs.get("template_version"))
                if replay_inputs.get("template_version") not in {None, ""}
                else None
            ),
        },
        output_path=str(receipt.get("output_path") or ""),
        output_hash=str(receipt.get("hash") or ""),
        cache_key=str(receipt.get("cache_key") or ""),
        selected_candidate_id=str(run_summary.get("selected_candidate_id") or ""),
        selected_candidate_rank=_as_int(
            run_summary.get("selected_candidate_rank"), default=0
        ),
        ranked_candidate_ids=_as_str_list(run_summary.get("ranked_candidate_ids")),
        ranking_policy_id=str(run_summary.get("ranking_policy_id") or ""),
        ranking_policy_version=(
            str(run_summary.get("ranking_policy_version"))
            if run_summary.get("ranking_policy_version") not in {None, ""}
            else None
        ),
        validation_pass_count=_as_int(run_summary.get("validation_pass_count")),
        validation_total=_as_int(run_summary.get("validation_total")),
        smoke_pass_count=_as_int(run_summary.get("smoke_pass_count")),
        smoke_total=_as_int(run_summary.get("smoke_total")),
        evaluation_status=(
            str(run_summary.get("evaluation_status"))
            if run_summary.get("evaluation_status") not in {None, ""}
            else None
        ),
        promotion_status=(
            str(run_summary.get("promotion_status"))
            if run_summary.get("promotion_status") not in {None, ""}
            else None
        ),
        promotion_outcome=(
            str(run_summary.get("promotion_outcome"))
            if run_summary.get("promotion_outcome") not in {None, ""}
            else None
        ),
        synthesis=(
            _as_dict(receipt.get("synthesis"))
            if isinstance(receipt.get("synthesis"), Mapping)
            else None
        ),
        synthesis_request_id=(
            str(receipt.get("synthesis_request_id"))
            if receipt.get("synthesis_request_id") not in {None, ""}
            else None
        ),
        synthesis_candidate_ids=_as_str_list(receipt.get("synthesis_candidate_ids")),
        synthesis_evaluation_ids=_as_str_list(receipt.get("synthesis_evaluation_ids")),
        synthesis_selection_policy=(
            _as_dict(receipt.get("synthesis_selection_policy"))
            if isinstance(receipt.get("synthesis_selection_policy"), Mapping)
            else None
        ),
        synthesis_ranked_candidates=_as_ranked_candidates(
            receipt.get("synthesis_ranked_candidates")
        ),
        synthesis_promotion_shell=(
            _as_dict(receipt.get("synthesis_promotion_shell"))
            if isinstance(receipt.get("synthesis_promotion_shell"), Mapping)
            else None
        ),
        synthesis_promotion_decision=(
            _as_dict(receipt.get("synthesis_promotion_decision"))
            if isinstance(receipt.get("synthesis_promotion_decision"), Mapping)
            else None
        ),
        historical_diagnostics=historical_diagnostics,
    )


def _build_replay_evidence(meta_path: Path) -> ModuleSynthesisReplayEvidence:
    report = explain_run_receipt(meta_path)
    replay_status = str(report.get("replay_status") or "invalid")
    replay_checks_raw = report.get("replay_checks")
    replay_checks = (
        {str(key): bool(value) for key, value in replay_checks_raw.items()}
        if isinstance(replay_checks_raw, Mapping)
        else {}
    )
    local_facts_raw = report.get("local_facts")
    local_facts = dict(local_facts_raw) if isinstance(local_facts_raw, Mapping) else {}
    failed_checks = local_facts.get("failed_replay_checks")
    failed_check_names = (
        [str(item) for item in failed_checks if str(item).strip()]
        if isinstance(failed_checks, list)
        else []
    )
    healthy = replay_status == "ok" and not failed_check_names
    error_codes = report.get("replay_error_codes")
    error_details = report.get("replay_error_details")
    return ModuleSynthesisReplayEvidence(
        replay_status=replay_status,
        replay_checks=replay_checks,
        local_facts=local_facts,
        replay_error_codes=(
            tuple(str(item) for item in error_codes if str(item).strip())
            if isinstance(error_codes, list)
            else ()
        ),
        replay_error_details=(
            tuple(dict(item) for item in error_details if isinstance(item, Mapping))
            if isinstance(error_details, list)
            else ()
        ),
        healthy=healthy,
    )


def _retrieve_oracle_neighbors(
    request: ModuleSynthesisEvidenceRequest,
    *,
    oracle_index_path: Path,
    oracle_top_k: int,
) -> tuple[str, tuple[ModuleSynthesisOracleNeighbor, ...], dict[str, str] | None]:
    if not oracle_index_path.exists():
        return "missing", (), None

    try:
        index = CoordinateIndex(db_path=oracle_index_path)
        results = index.search_by_text(
            request.oracle_query_text(),
            top_k=oracle_top_k,
            run_kind="module-gen",
        )
    except Exception as exc:
        return (
            "unavailable",
            (),
            {
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        )

    neighbors: list[ModuleSynthesisOracleNeighbor] = []
    for result in results:
        metadata = (
            dict(result.embedding.metadata)
            if isinstance(result.embedding.metadata, Mapping)
            else {}
        )
        receipt_identity = metadata.get("receipt_identity")
        neighbors.append(
            ModuleSynthesisOracleNeighbor(
                run_id=result.run_id,
                similarity=float(result.similarity),
                distance=float(result.distance),
                run_kind=str(result.embedding.run_kind or "unknown"),
                provider=str(result.embedding.provider or "unknown"),
                template_version=(
                    str(result.embedding.template_version)
                    if result.embedding.template_version not in {None, ""}
                    else None
                ),
                source_path=(
                    str(result.embedding.source_path)
                    if result.embedding.source_path not in {None, ""}
                    else None
                ),
                cache_key=(
                    str(metadata.get("cache_key"))
                    if metadata.get("cache_key") not in {None, ""}
                    else None
                ),
                receipt_identity=(
                    dict(receipt_identity)
                    if isinstance(receipt_identity, Mapping)
                    else {}
                ),
            )
        )
    return "available", tuple(neighbors), None


def _advisory_receipt_identity(
    match: ModuleSynthesisEvidenceMatch,
) -> dict[str, Any]:
    return {
        "receipt_path": match.receipt.receipt_path,
        "created_at": match.receipt.created_at,
        "output_hash": match.receipt.output_hash,
        "cache_key": match.receipt.cache_key,
        "selected_candidate_id": match.receipt.selected_candidate_id,
        "positive_evidence": match.positive_evidence,
    }


def build_module_synthesis_history_advisory(
    bundle: ModuleSynthesisEvidenceBundle,
    *,
    selected_candidate_id: str | None,
    output_hash: str | None,
    cache_key: str | None,
) -> dict[str, Any]:
    selected_artifact = {
        "selected_candidate_id": (
            str(selected_candidate_id)
            if selected_candidate_id not in {None, ""}
            else None
        ),
        "output_hash": str(output_hash) if output_hash not in {None, ""} else None,
        "cache_key": str(cache_key) if cache_key not in {None, ""} else None,
    }
    history_summary = {
        "exact_match_receipt_count": len(bundle.exact_match_receipts),
        "positive_evidence_count": bundle.positive_evidence_count,
        "oracle_neighbor_count": len(bundle.oracle_neighbors),
    }
    notes: list[str] = []

    selected_output_hash = selected_artifact["output_hash"]
    if selected_output_hash is None:
        notes.append("selected artifact output_hash unavailable")
        return {
            "advisory_version": "v1",
            "status": "unavailable",
            "selected_artifact": selected_artifact,
            "history_summary": history_summary,
            "matching_positive_receipts": [],
            "divergent_positive_receipts": [],
            "notes": notes,
        }

    positive_matches = [
        match for match in bundle.exact_match_receipts if match.positive_evidence
    ]
    exact_match_scan_errors = bundle.exact_match_receipt_scan_errors
    matching_positive_receipts = [
        _advisory_receipt_identity(match)
        for match in positive_matches
        if match.receipt.output_hash == selected_output_hash
    ]
    divergent_positive_receipts = [
        _advisory_receipt_identity(match)
        for match in positive_matches
        if match.receipt.output_hash != selected_output_hash
    ]

    if not bundle.exact_match_receipts:
        if exact_match_scan_errors:
            status = "degraded_history_only"
            notes.append(
                "exact-match receipt scan errors prevent confidently classifying history as no_history"
            )
        else:
            status = "no_history"
            notes.append("no exact-match receipts retrieved")
    elif not positive_matches:
        status = "degraded_history_only"
        notes.append(
            "exact-match history exists but no replay-healthy receipts qualify as positive evidence"
        )
    elif matching_positive_receipts:
        status = "convergent_with_positive_history"
        notes.append(
            "selected artifact matches replay-healthy exact-match history by output_hash"
        )
    else:
        status = "divergent_from_positive_history"
        notes.append(
            "selected artifact differs from replay-healthy exact-match history by output_hash"
        )

    if bundle.oracle_lookup_status == "unavailable":
        notes.append(
            "oracle lookup unavailable; advisory anchored on exact-match history only"
        )
    elif bundle.oracle_lookup_status == "missing":
        notes.append(
            "oracle index missing; advisory anchored on exact-match history only"
        )

    if exact_match_scan_errors:
        notes.append(
            "ignored "
            f"{bundle.exact_match_receipt_scan_error_count} malformed exact-match receipt(s) during evidence retrieval"
        )
    elif bundle.receipt_scan_errors:
        notes.append(
            "ignored malformed non-attributable receipt scan errors outside exact-match authority"
        )

    return {
        "advisory_version": "v1",
        "status": status,
        "selected_artifact": selected_artifact,
        "history_summary": history_summary,
        "matching_positive_receipts": matching_positive_receipts,
        "divergent_positive_receipts": divergent_positive_receipts,
        "notes": notes,
    }


def extract_module_synthesis_candidate_prior_inputs(
    synthesis: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(synthesis, Mapping):
        return ()
    raw_candidates = synthesis.get("candidates")
    if not isinstance(raw_candidates, list):
        return ()

    candidates: list[dict[str, Any]] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        candidate_id = _optional_str(raw_candidate.get("candidate_id"))
        if candidate_id is None:
            continue
        metadata = _as_dict(raw_candidate.get("metadata"))
        lineage = _as_dict(raw_candidate.get("lineage"))
        candidates.append(
            {
                "candidate_id": candidate_id,
                "variant_id": _optional_str(metadata.get("variant_id")),
                "variant_origin": _optional_str(lineage.get("variant_origin")),
                "ordinal": _as_int(raw_candidate.get("ordinal"), default=0),
            }
        )
    return tuple(candidates)


def _module_synthesis_ranked_candidate_payloads(
    synthesis: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(synthesis, Mapping):
        return ()

    raw_ranked = None
    promotion_decision = _as_dict(synthesis.get("promotion_decision"))
    decision_metadata = _as_dict(promotion_decision.get("metadata"))
    decision_ranked = decision_metadata.get("ranked_candidates")
    if isinstance(decision_ranked, list) and decision_ranked:
        raw_ranked = decision_ranked

    promotion_shell = _as_dict(synthesis.get("promotion_shell"))
    shell_metadata = _as_dict(promotion_shell.get("metadata"))
    shell_ranked = shell_metadata.get("ranked_candidates")
    if raw_ranked is None and isinstance(shell_ranked, list) and shell_ranked:
        raw_ranked = shell_ranked

    def _materialize_ranked_candidates(
        raw_items: Any,
    ) -> tuple[dict[str, Any], ...]:
        ranked_candidates: list[dict[str, Any]] = []
        for raw_candidate in _as_ranked_candidates(raw_items):
            candidate_id = _optional_str(raw_candidate.get("candidate_id"))
            if candidate_id is None:
                continue
            rank = _as_int(raw_candidate.get("rank"), default=0)
            if rank <= 0:
                continue
            ranked_candidates.append(dict(raw_candidate))
        return tuple(ranked_candidates)

    ranked_candidates = _materialize_ranked_candidates(raw_ranked)
    if ranked_candidates:
        return ranked_candidates
    if raw_ranked is not None:
        return _materialize_ranked_candidates(shell_ranked)
    return ()


def extract_module_synthesis_ranked_candidate_inputs(
    synthesis: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], ...]:
    ranked_candidates: list[dict[str, Any]] = []
    for raw_candidate in _module_synthesis_ranked_candidate_payloads(synthesis):
        candidate_id = _optional_str(raw_candidate.get("candidate_id"))
        if candidate_id is None:
            continue
        ranked_candidates.append(
            {
                "candidate_id": candidate_id,
                "rank": _as_int(raw_candidate.get("rank"), default=0),
                "variant_id": _optional_str(raw_candidate.get("variant_id")),
                "ordinal": _as_int(raw_candidate.get("ordinal"), default=0),
            }
        )
    return tuple(ranked_candidates)


def extract_module_synthesis_ranked_candidate_comparison_inputs(
    synthesis: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(synthesis, Mapping):
        return ()

    evaluation_summaries: dict[str, str] = {}
    raw_evaluations = synthesis.get("evaluations")
    if isinstance(raw_evaluations, list):
        for raw_evaluation in raw_evaluations:
            if not isinstance(raw_evaluation, Mapping):
                continue
            candidate_id = _optional_str(raw_evaluation.get("candidate_id"))
            summary = _optional_str(raw_evaluation.get("summary"))
            if candidate_id is None or summary is None:
                continue
            evaluation_summaries[candidate_id] = summary

    current_candidates = {
        candidate_id: candidate
        for candidate in extract_module_synthesis_candidate_prior_inputs(synthesis)
        if (candidate_id := _optional_str(candidate.get("candidate_id"))) is not None
    }

    comparison_inputs: list[dict[str, Any]] = []
    for raw_candidate in _module_synthesis_ranked_candidate_payloads(synthesis):
        candidate_id = _optional_str(raw_candidate.get("candidate_id"))
        if candidate_id is None:
            continue
        current_candidate = current_candidates.get(candidate_id, {})
        passed_raw = raw_candidate.get("passed")
        comparison_inputs.append(
            {
                "candidate_id": candidate_id,
                "rank": _as_int(raw_candidate.get("rank"), default=0),
                "variant_id": _optional_str(raw_candidate.get("variant_id"))
                or _optional_str(current_candidate.get("variant_id")),
                "variant_origin": _optional_str(raw_candidate.get("variant_origin"))
                or _optional_str(current_candidate.get("variant_origin")),
                "ordinal": _as_int(raw_candidate.get("ordinal"), default=0),
                "evaluation_status": _optional_str(raw_candidate.get("status")),
                "passed": passed_raw if isinstance(passed_raw, bool) else None,
                "ranking_score": _optional_float(raw_candidate.get("score")),
                "evaluation_summary": evaluation_summaries.get(candidate_id),
            }
        )
    return tuple(comparison_inputs)


def _strict_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value_int = int(value)
        return value_int if value_int > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value_int = int(text)
        except ValueError:
            return None
        return value_int if value_int > 0 else None
    return None


def _strict_optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _candidate_prior_identity_conflicts(
    *,
    expected: Mapping[str, object] | None,
    observed: Mapping[str, object] | None,
) -> bool:
    expected_view = _as_dict(expected)
    observed_view = _as_dict(observed)
    for field in ("candidate_id", "variant_id", "variant_origin"):
        expected_value = _optional_str(expected_view.get(field))
        observed_value = _optional_str(observed_view.get(field))
        if (
            expected_value is not None
            and observed_value is not None
            and expected_value != observed_value
        ):
            return True
    return False


def _duplicate_candidate_id(
    candidates: Iterable[Mapping[str, object]],
) -> str | None:
    seen: set[str] = set()
    for candidate in candidates:
        candidate_id = _optional_str(candidate.get("candidate_id"))
        if candidate_id is None:
            continue
        if candidate_id in seen:
            return candidate_id
        seen.add(candidate_id)
    return None


def _canonicalize_candidate_prior_comparison_inputs(
    ranked_candidate_comparison_inputs: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]] | None:
    comparison_by_id: dict[str, dict[str, Any]] = {}
    for raw_candidate in ranked_candidate_comparison_inputs:
        if not isinstance(raw_candidate, Mapping):
            return None
        candidate_id = _optional_str(raw_candidate.get("candidate_id"))
        rank = _strict_positive_int(raw_candidate.get("rank"))
        evaluation_status = _optional_str(raw_candidate.get("evaluation_status"))
        passed = raw_candidate.get("passed")
        ranking_score = _strict_optional_float(raw_candidate.get("ranking_score"))
        if (
            candidate_id is None
            or rank is None
            or evaluation_status is None
            or not isinstance(passed, bool)
            or ranking_score is None
            or candidate_id in comparison_by_id
        ):
            return None
        comparison_by_id[candidate_id] = {
            "candidate_id": candidate_id,
            "rank": rank,
            "variant_id": _optional_str(raw_candidate.get("variant_id")),
            "variant_origin": _optional_str(raw_candidate.get("variant_origin")),
            "ordinal": _as_int(raw_candidate.get("ordinal"), default=0),
            "evaluation_status": evaluation_status,
            "passed": passed,
            "ranking_score": ranking_score,
            "evaluation_summary": _optional_str(
                raw_candidate.get("evaluation_summary")
            ),
        }
    return comparison_by_id


def _candidate_prior_identity_disagrees_with_current_comparison(
    *,
    candidate: Mapping[str, object] | None,
    comparison_candidate: Mapping[str, object] | None,
) -> bool:
    return _candidate_prior_identity_conflicts(
        expected=candidate,
        observed=comparison_candidate,
    )


def _candidate_prior_identity_supported(identity: Mapping[str, object]) -> bool:
    return bool(_optional_str(identity.get("variant_id"))) and bool(
        _optional_str(identity.get("variant_origin"))
    )


def _selected_winner_candidate_identity(
    receipt: ModuleSynthesisReceiptEvidence,
) -> dict[str, Any] | None:
    selected_candidate_id = _optional_str(receipt.selected_candidate_id)
    if selected_candidate_id is None:
        return None

    synthesis = receipt.synthesis
    if isinstance(synthesis, Mapping):
        raw_candidates = synthesis.get("candidates")
        if isinstance(raw_candidates, list):
            for raw_candidate in raw_candidates:
                if not isinstance(raw_candidate, Mapping):
                    continue
                if (
                    _optional_str(raw_candidate.get("candidate_id"))
                    != selected_candidate_id
                ):
                    continue
                extracted = extract_module_synthesis_candidate_prior_inputs(
                    {"candidates": [dict(raw_candidate)]}
                )
                if extracted:
                    return extracted[0]
                break

    for raw_candidate in receipt.synthesis_ranked_candidates:
        if _optional_str(raw_candidate.get("candidate_id")) != selected_candidate_id:
            continue
        return {
            "candidate_id": selected_candidate_id,
            "variant_id": _optional_str(raw_candidate.get("variant_id")),
            "variant_origin": None,
            "ordinal": _as_int(raw_candidate.get("ordinal"), default=0),
        }

    return {
        "candidate_id": selected_candidate_id,
        "variant_id": None,
        "variant_origin": None,
        "ordinal": None,
    }


def _candidate_prior_receipt_identity(
    match: ModuleSynthesisEvidenceMatch,
    *,
    winner_identity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "receipt_path": match.receipt.receipt_path,
        "created_at": match.receipt.created_at,
        "selected_candidate_id": match.receipt.selected_candidate_id,
        "output_hash": match.receipt.output_hash,
        "cache_key": match.receipt.cache_key,
        "variant_id": _optional_str(winner_identity.get("variant_id")),
        "variant_origin": _optional_str(winner_identity.get("variant_origin")),
        "positive_evidence": True,
    }


def _append_unique_note(notes: list[str], note: str | None) -> None:
    if note and note not in notes:
        notes.append(note)


def _candidate_prior_rank_map(
    *,
    ranked_candidates: tuple[dict[str, Any], ...],
) -> dict[str, int]:
    rank_map: dict[str, int] = {}
    for candidate in ranked_candidates:
        candidate_id = _optional_str(candidate.get("candidate_id"))
        if candidate_id is None or candidate_id in rank_map:
            continue
        rank = _as_int(candidate.get("rank"), default=0)
        if rank <= 0:
            continue
        rank_map[candidate_id] = rank
    return rank_map


def _candidate_prior_audit_candidate_view(
    *,
    candidate_prior: Mapping[str, Any],
    rank_map: Mapping[str, int],
) -> dict[str, Any]:
    candidate_id = _optional_str(candidate_prior.get("candidate_id"))
    return {
        "candidate_id": candidate_id,
        "variant_id": _optional_str(candidate_prior.get("variant_id")),
        "variant_origin": _optional_str(candidate_prior.get("variant_origin")),
        "prior_status": _optional_str(candidate_prior.get("status")),
        "rank": rank_map.get(candidate_id) if candidate_id is not None else None,
    }


def build_unavailable_module_synthesis_candidate_winner_priors(
    *,
    current_candidates: tuple[dict[str, Any], ...] = (),
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "status": "unavailable",
        "history_summary": {
            "exact_match_receipt_count": 0,
            "positive_evidence_count": 0,
            "oracle_neighbor_count": 0,
            "candidate_count": len(current_candidates),
        },
        "candidate_priors": [],
        "notes": list(notes or ["candidate winner-prior payload unavailable"]),
    }


def build_module_synthesis_candidate_winner_priors(
    bundle: ModuleSynthesisEvidenceBundle,
    *,
    current_candidates: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    history_summary = {
        "exact_match_receipt_count": len(bundle.exact_match_receipts),
        "positive_evidence_count": bundle.positive_evidence_count,
        "oracle_neighbor_count": len(bundle.oracle_neighbors),
        "candidate_count": len(current_candidates),
    }

    positive_winner_identities: list[
        tuple[ModuleSynthesisEvidenceMatch, dict[str, Any]]
    ] = []
    unresolved_positive_winners = 0
    for match in bundle.exact_match_receipts:
        if not match.positive_evidence:
            continue
        winner_identity = _selected_winner_candidate_identity(match.receipt)
        if winner_identity is None or not _candidate_prior_identity_supported(
            winner_identity
        ):
            unresolved_positive_winners += 1
            continue
        positive_winner_identities.append((match, winner_identity))

    has_exact_match_history = bool(bundle.exact_match_receipts) or bool(
        bundle.exact_match_receipt_scan_errors
    )
    has_positive_winner_authority = bool(positive_winner_identities)
    notes = [
        "candidate winner priors are advisory only; V7 ranking and promotion remain unchanged"
    ]
    if not has_exact_match_history:
        notes.append("no exact-match receipts retrieved")
    elif not bundle.positive_evidence_count:
        notes.append(
            "exact-match history exists but no replay-healthy prior winners qualify as positive authority"
        )
    elif not has_positive_winner_authority:
        notes.append(
            "replay-healthy exact-match history exists, but selected winners could not be resolved to stable candidate identity"
        )

    if unresolved_positive_winners:
        notes.append(
            "ignored "
            f"{unresolved_positive_winners} replay-healthy exact-match winner(s) without stable variant identity"
        )
    if bundle.oracle_lookup_status == "unavailable":
        notes.append(
            "oracle lookup unavailable; candidate priors anchored on exact-match winner history only"
        )
    elif bundle.oracle_lookup_status == "missing":
        notes.append(
            "oracle index missing; candidate priors anchored on exact-match winner history only"
        )
    if bundle.exact_match_receipt_scan_errors:
        notes.append(
            "ignored "
            f"{bundle.exact_match_receipt_scan_error_count} malformed exact-match receipt(s) during evidence retrieval"
        )
    elif bundle.receipt_scan_errors:
        notes.append(
            "ignored malformed non-attributable receipt scan errors outside exact-match authority"
        )

    candidate_priors: list[dict[str, Any]] = []
    for candidate in current_candidates:
        candidate_id = _optional_str(candidate.get("candidate_id"))
        if candidate_id is None:
            continue
        variant_id = _optional_str(candidate.get("variant_id"))
        variant_origin = _optional_str(candidate.get("variant_origin"))
        matching_positive_receipts = [
            _candidate_prior_receipt_identity(match, winner_identity=winner_identity)
            for match, winner_identity in positive_winner_identities
            if _optional_str(winner_identity.get("variant_id")) == variant_id
            and _optional_str(winner_identity.get("variant_origin")) == variant_origin
        ]
        candidate_notes: list[str] = []
        if not _candidate_prior_identity_supported(candidate):
            status = "unsupported_candidate_identity"
            candidate_notes.append(
                "candidate lacks variant_id or variant_origin required by candidate-prior contract v1"
            )
        elif matching_positive_receipts:
            status = "matches_positive_winner_history"
            candidate_notes.append(
                "candidate matches replay-healthy exact-match prior winner history by variant identity"
            )
        elif has_exact_match_history and not has_positive_winner_authority:
            status = "degraded_history_only"
            candidate_notes.append(
                "exact-match history exists but no replay-healthy winner evidence qualifies as positive authority"
            )
        else:
            status = "no_positive_winner_history"
            candidate_notes.append(
                "no replay-healthy exact-match prior winner matches this candidate identity"
            )

        candidate_priors.append(
            {
                "candidate_id": candidate_id,
                "variant_id": variant_id,
                "variant_origin": variant_origin,
                "status": status,
                "positive_winner_match_count": len(matching_positive_receipts),
                "matching_positive_receipts": matching_positive_receipts,
                "notes": candidate_notes,
            }
        )

    return {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "history_summary": history_summary,
        "candidate_priors": candidate_priors,
        "notes": notes,
    }


def build_unavailable_module_synthesis_candidate_prior_audit(
    *,
    selected_candidate_id: str | None,
    current_candidates: tuple[dict[str, Any], ...] = (),
    notes: list[str] | None = None,
) -> dict[str, Any]:
    selected_candidate = next(
        (
            candidate
            for candidate in current_candidates
            if _optional_str(candidate.get("candidate_id")) == selected_candidate_id
        ),
        None,
    )
    return {
        "candidate_prior_audit_version": "v1",
        "status": "candidate_priors_unavailable",
        "selected_candidate": {
            "candidate_id": selected_candidate_id,
            "variant_id": (
                _optional_str(selected_candidate.get("variant_id"))
                if isinstance(selected_candidate, Mapping)
                else None
            ),
            "variant_origin": (
                _optional_str(selected_candidate.get("variant_origin"))
                if isinstance(selected_candidate, Mapping)
                else None
            ),
            "prior_status": None,
            "rank": None,
        },
        "history_summary": {
            "exact_match_receipt_count": 0,
            "positive_evidence_count": 0,
            "candidate_count": len(current_candidates),
            "positive_prior_candidate_count": 0,
        },
        "positive_prior_candidates": [],
        "non_selected_positive_prior_candidates": [],
        "notes": list(notes or ["candidate-prior audit unavailable"]),
    }


def build_module_synthesis_candidate_prior_audit(
    candidate_winner_priors: Mapping[str, Any] | None,
    *,
    current_candidates: tuple[dict[str, Any], ...],
    ranked_candidates: tuple[dict[str, Any], ...],
    selected_candidate_id: str | None,
) -> dict[str, Any]:
    if not isinstance(candidate_winner_priors, Mapping):
        return build_unavailable_module_synthesis_candidate_prior_audit(
            selected_candidate_id=selected_candidate_id,
            current_candidates=current_candidates,
            notes=[
                "candidate-prior audit unavailable because candidate priors are missing"
            ],
        )
    if _optional_str(candidate_winner_priors.get("status")) == "unavailable":
        return build_unavailable_module_synthesis_candidate_prior_audit(
            selected_candidate_id=selected_candidate_id,
            current_candidates=current_candidates,
            notes=[
                "candidate-prior audit unavailable because candidate winner-prior payload is unavailable"
            ],
        )
    if selected_candidate_id in {None, ""}:
        return build_unavailable_module_synthesis_candidate_prior_audit(
            selected_candidate_id=None,
            current_candidates=current_candidates,
            notes=[
                "candidate-prior audit unavailable because selected candidate identity is missing"
            ],
        )

    rank_map = _candidate_prior_rank_map(ranked_candidates=ranked_candidates)
    raw_candidate_priors = candidate_winner_priors.get("candidate_priors")
    if not isinstance(raw_candidate_priors, list):
        return build_unavailable_module_synthesis_candidate_prior_audit(
            selected_candidate_id=selected_candidate_id,
            current_candidates=current_candidates,
            notes=[
                "candidate-prior audit unavailable because candidate priors are malformed"
            ],
        )

    candidate_prior_entries = [
        dict(item) for item in raw_candidate_priors if isinstance(item, Mapping)
    ]
    candidate_priors_by_id = {
        candidate_id: item
        for item in candidate_prior_entries
        if (candidate_id := _optional_str(item.get("candidate_id"))) is not None
    }
    expected_rank_candidate_ids = set(candidate_priors_by_id)
    incomplete_rank_context = bool(
        rank_map
    ) and not expected_rank_candidate_ids.issubset(set(rank_map))
    if incomplete_rank_context:
        rank_map = {}
    selected_candidate_prior = candidate_priors_by_id.get(selected_candidate_id)
    if selected_candidate_prior is None:
        return build_unavailable_module_synthesis_candidate_prior_audit(
            selected_candidate_id=selected_candidate_id,
            current_candidates=current_candidates,
            notes=[
                "candidate-prior audit unavailable because selected candidate has no prior entry"
            ],
        )

    positive_prior_candidates = [
        _candidate_prior_audit_candidate_view(candidate_prior=item, rank_map=rank_map)
        for item in candidate_prior_entries
        if _optional_str(item.get("status")) == "matches_positive_winner_history"
    ]
    positive_prior_candidates.sort(
        key=lambda item: (
            item.get("rank") is None,
            _as_int(item.get("rank"), default=0),
            _optional_str(item.get("candidate_id")) or "",
        )
    )
    non_selected_positive_prior_candidates = [
        item
        for item in positive_prior_candidates
        if _optional_str(item.get("candidate_id")) != selected_candidate_id
    ]

    history_summary_raw = _as_dict(candidate_winner_priors.get("history_summary"))
    history_summary = {
        "exact_match_receipt_count": _as_int(
            history_summary_raw.get("exact_match_receipt_count"), default=0
        ),
        "positive_evidence_count": _as_int(
            history_summary_raw.get("positive_evidence_count"), default=0
        ),
        "candidate_count": _as_int(
            history_summary_raw.get("candidate_count"),
            default=len(candidate_prior_entries),
        ),
        "positive_prior_candidate_count": len(positive_prior_candidates),
    }

    selected_candidate = _candidate_prior_audit_candidate_view(
        candidate_prior=selected_candidate_prior,
        rank_map=rank_map,
    )
    selected_prior_status = selected_candidate["prior_status"]
    notes = [
        "candidate-prior audit is descriptive only; V7 ranking and promotion remain unchanged"
    ]

    if selected_prior_status == "unsupported_candidate_identity":
        status = "selected_candidate_prior_unsupported"
        _append_unique_note(
            notes,
            "selected candidate lacks variant_id or variant_origin required by candidate-prior contract v1",
        )
    elif selected_prior_status == "degraded_history_only":
        status = "selected_candidate_prior_degraded"
        _append_unique_note(
            notes,
            "exact-match history exists, but selected candidate has only degraded prior authority",
        )
    elif selected_prior_status == "matches_positive_winner_history":
        status = "selected_matches_positive_winner_history"
        _append_unique_note(
            notes,
            "selected candidate matches replay-healthy exact-match winner history under candidate-prior contract v1",
        )
    elif not positive_prior_candidates:
        status = "no_positive_prior_candidates"
        _append_unique_note(
            notes,
            "no current candidate has positive winner support under candidate-prior contract v1",
        )
    else:
        status = "positive_prior_candidates_present_but_not_selected"
        _append_unique_note(
            notes,
            "non-selected candidates have positive winner support while the V7-selected candidate does not",
        )

    raw_notes = candidate_winner_priors.get("notes")
    if isinstance(raw_notes, list):
        for note in raw_notes:
            if isinstance(note, str):
                _append_unique_note(notes, note)
    if incomplete_rank_context:
        _append_unique_note(
            notes,
            "ranked-candidate order incomplete; audit omitted rank context to avoid reporting a partial ordering",
        )
    elif not rank_map:
        _append_unique_note(
            notes,
            "ranked-candidate order unavailable; audit reported without stable rank context",
        )

    return {
        "candidate_prior_audit_version": "v1",
        "status": status,
        "selected_candidate": selected_candidate,
        "history_summary": history_summary,
        "positive_prior_candidates": positive_prior_candidates,
        "non_selected_positive_prior_candidates": non_selected_positive_prior_candidates,
        "notes": notes,
    }


def _candidate_prior_divergence_history_summary(
    candidate_prior_audit: Mapping[str, Any] | None,
    *,
    compared_candidate_count: int,
) -> dict[str, int]:
    history_summary_raw = _as_dict(
        _as_dict(candidate_prior_audit).get("history_summary")
    )
    return {
        "exact_match_receipt_count": _as_int(
            history_summary_raw.get("exact_match_receipt_count"), default=0
        ),
        "positive_evidence_count": _as_int(
            history_summary_raw.get("positive_evidence_count"), default=0
        ),
        "positive_prior_candidate_count": _as_int(
            history_summary_raw.get("positive_prior_candidate_count"), default=0
        ),
        "compared_candidate_count": max(0, int(compared_candidate_count)),
    }


def _candidate_prior_divergence_selected_candidate_view(
    *,
    audit_candidate: Mapping[str, Any] | None,
    comparison_candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    audit = _as_dict(audit_candidate)
    comparison = _as_dict(comparison_candidate)
    rank = _as_int(comparison.get("rank"), default=0)
    if rank <= 0:
        rank = _as_int(audit.get("rank"), default=0)
    return {
        "candidate_id": _optional_str(audit.get("candidate_id")),
        "variant_id": _optional_str(audit.get("variant_id")),
        "variant_origin": _optional_str(audit.get("variant_origin")),
        "prior_status": _optional_str(audit.get("prior_status")),
        "rank": rank if rank > 0 else None,
        "ranking_score": _optional_float(comparison.get("ranking_score")),
    }


def _candidate_prior_divergence_comparison_supported(
    comparison_candidate: Mapping[str, Any] | None,
) -> bool:
    comparison = _as_dict(comparison_candidate)
    return (
        _optional_str(comparison.get("candidate_id")) is not None
        and _strict_positive_int(comparison.get("rank")) is not None
        and _optional_str(comparison.get("evaluation_status")) is not None
        and isinstance(comparison.get("passed"), bool)
        and _strict_optional_float(comparison.get("ranking_score")) is not None
    )


def _candidate_prior_divergence_compared_candidate_view(
    *,
    audit_candidate: Mapping[str, Any],
    comparison_candidate: Mapping[str, Any],
    comparison_status: str,
    notes: list[str],
) -> dict[str, Any]:
    comparison = _as_dict(comparison_candidate)
    return {
        "candidate_id": _optional_str(audit_candidate.get("candidate_id")),
        "variant_id": _optional_str(audit_candidate.get("variant_id")),
        "variant_origin": _optional_str(audit_candidate.get("variant_origin")),
        "rank": _as_int(comparison.get("rank"), default=0),
        "ranking_score": _optional_float(comparison.get("ranking_score")),
        "evaluation_status": _optional_str(comparison.get("evaluation_status")),
        "comparison_status": comparison_status,
        "notes": list(notes),
    }


def build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
    *,
    candidate_prior_audit: Mapping[str, Any] | None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    audit = _as_dict(candidate_prior_audit)
    raw_compared_candidates = audit.get("non_selected_positive_prior_candidates")
    compared_candidate_count = (
        len([item for item in raw_compared_candidates if isinstance(item, Mapping)])
        if isinstance(raw_compared_candidates, list)
        else 0
    )
    return {
        "candidate_prior_divergence_explanation_version": "v1",
        "status": "candidate_prior_divergence_unavailable",
        "candidate_prior_audit_status": _optional_str(audit.get("status")),
        "selected_candidate": _candidate_prior_divergence_selected_candidate_view(
            audit_candidate=_as_dict(audit.get("selected_candidate")),
            comparison_candidate=None,
        ),
        "history_summary": _candidate_prior_divergence_history_summary(
            audit,
            compared_candidate_count=compared_candidate_count,
        ),
        "compared_positive_prior_candidates": [],
        "notes": list(notes or ["candidate-prior divergence explanation unavailable"]),
    }


def build_module_synthesis_candidate_prior_divergence_explanation(
    candidate_prior_audit: Mapping[str, Any] | None,
    *,
    ranked_candidate_comparison_inputs: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if not isinstance(candidate_prior_audit, Mapping):
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=None,
            notes=[
                "candidate-prior divergence explanation unavailable because candidate-prior audit is missing"
            ],
        )

    audit_status = _optional_str(candidate_prior_audit.get("status"))
    if audit_status is None:
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because candidate-prior audit is malformed"
            ],
        )
    if audit_status == "candidate_priors_unavailable":
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because candidate-prior audit is unavailable"
            ],
        )

    selected_candidate_audit = _as_dict(candidate_prior_audit.get("selected_candidate"))
    selected_candidate_id = _optional_str(selected_candidate_audit.get("candidate_id"))
    compared_candidates_raw = candidate_prior_audit.get(
        "non_selected_positive_prior_candidates"
    )
    if not isinstance(compared_candidates_raw, list) or any(
        not isinstance(item, Mapping) for item in compared_candidates_raw
    ):
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because compared positive-prior candidates are malformed"
            ],
        )
    compared_candidates = [_as_dict(item) for item in compared_candidates_raw]
    history_summary = _candidate_prior_divergence_history_summary(
        candidate_prior_audit,
        compared_candidate_count=len(compared_candidates),
    )
    duplicate_compared_candidate_id = _duplicate_candidate_id(compared_candidates)
    if duplicate_compared_candidate_id is not None:
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because the audit comparison set contains duplicate candidate_id entries"
            ],
        )
    comparison_by_id = _canonicalize_candidate_prior_comparison_inputs(
        ranked_candidate_comparison_inputs
    )
    if comparison_by_id is None:
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because trusted current comparison metadata is malformed or duplicated"
            ],
        )
    selected_comparison_candidate = (
        comparison_by_id.get(selected_candidate_id)
        if selected_candidate_id is not None
        else None
    )
    selected_candidate = _candidate_prior_divergence_selected_candidate_view(
        audit_candidate=selected_candidate_audit,
        comparison_candidate=selected_comparison_candidate,
    )
    notes = [
        "candidate-prior divergence explanation is descriptive only; V7 ranking and promotion remain unchanged"
    ]
    raw_audit_notes = candidate_prior_audit.get("notes")
    if isinstance(raw_audit_notes, list):
        for note in raw_audit_notes:
            if isinstance(note, str):
                _append_unique_note(notes, note)

    if audit_status in {
        "selected_matches_positive_winner_history",
        "no_positive_prior_candidates",
    }:
        if audit_status == "selected_matches_positive_winner_history":
            _append_unique_note(
                notes,
                "candidate-prior audit found no selected-vs-prior divergence to explain",
            )
        else:
            _append_unique_note(
                notes,
                "candidate-prior audit found no positive-prior-supported alternative to compare",
            )
        return {
            "candidate_prior_divergence_explanation_version": "v1",
            "status": "no_divergence_to_explain",
            "candidate_prior_audit_status": audit_status,
            "selected_candidate": selected_candidate,
            "history_summary": history_summary,
            "compared_positive_prior_candidates": [],
            "notes": notes,
        }

    if audit_status in {
        "selected_candidate_prior_unsupported",
        "selected_candidate_prior_degraded",
    }:
        if audit_status == "selected_candidate_prior_unsupported":
            _append_unique_note(
                notes,
                "selected candidate lacks stable prior identity, so DSPx must not over-interpret divergence",
            )
        else:
            _append_unique_note(
                notes,
                "selected candidate prior authority is degraded, so DSPx must not over-interpret divergence",
            )
        return {
            "candidate_prior_divergence_explanation_version": "v1",
            "status": "selected_candidate_prior_unresolved",
            "candidate_prior_audit_status": audit_status,
            "selected_candidate": selected_candidate,
            "history_summary": history_summary,
            "compared_positive_prior_candidates": [],
            "notes": notes,
        }

    if audit_status != "positive_prior_candidates_present_but_not_selected":
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because candidate-prior audit status is unsupported"
            ],
        )
    if selected_candidate_id is None:
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because selected candidate identity is missing"
            ],
        )
    if not compared_candidates:
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because the audit has no compared positive-prior candidates"
            ],
        )

    selected_comparison = comparison_by_id.get(selected_candidate_id)
    if selected_comparison is None:
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because trusted current comparison metadata for the selected candidate is incomplete"
            ],
        )
    if not _candidate_prior_divergence_comparison_supported(selected_comparison):
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because trusted current comparison metadata for the selected candidate is incomplete"
            ],
        )
    if selected_comparison.get("passed") is not True:
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because the selected candidate lacks a trusted passing runtime result"
            ],
        )
    if _candidate_prior_identity_disagrees_with_current_comparison(
        candidate=selected_candidate_audit,
        comparison_candidate=selected_comparison,
    ):
        return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior divergence explanation unavailable because selected candidate identity disagrees with trusted current comparison metadata"
            ],
        )

    selected_candidate = _candidate_prior_divergence_selected_candidate_view(
        audit_candidate=selected_candidate_audit,
        comparison_candidate=selected_comparison,
    )
    selected_rank = _as_int(selected_comparison.get("rank"), default=0)

    compared_candidate_views: list[dict[str, Any]] = []
    comparison_statuses: list[str] = []
    for compared_candidate in compared_candidates:
        candidate_id = _optional_str(compared_candidate.get("candidate_id"))
        if candidate_id is None:
            return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
                candidate_prior_audit=candidate_prior_audit,
                notes=[
                    "candidate-prior divergence explanation unavailable because a compared positive-prior candidate is missing candidate_id"
                ],
            )
        comparison_candidate = comparison_by_id.get(candidate_id)
        if comparison_candidate is None:
            return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
                candidate_prior_audit=candidate_prior_audit,
                notes=[
                    "candidate-prior divergence explanation unavailable because a compared positive-prior candidate is absent from trusted current comparison metadata"
                ],
            )
        if not _candidate_prior_divergence_comparison_supported(comparison_candidate):
            return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
                candidate_prior_audit=candidate_prior_audit,
                notes=[
                    "candidate-prior divergence explanation unavailable because trusted current comparison metadata is incomplete for at least one compared positive-prior candidate"
                ],
            )
        if _candidate_prior_identity_disagrees_with_current_comparison(
            candidate=compared_candidate,
            comparison_candidate=comparison_candidate,
        ):
            return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
                candidate_prior_audit=candidate_prior_audit,
                notes=[
                    "candidate-prior divergence explanation unavailable because a compared positive-prior candidate identity disagrees with trusted current comparison metadata"
                ],
            )

        candidate_rank = _as_int(comparison_candidate.get("rank"), default=0)
        candidate_notes: list[str] = []
        evaluation_summary = _optional_str(
            comparison_candidate.get("evaluation_summary")
        )
        if comparison_candidate.get("passed") is True:
            if candidate_rank <= selected_rank:
                return build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
                    candidate_prior_audit=candidate_prior_audit,
                    notes=[
                        "candidate-prior divergence explanation unavailable because trusted current rank metadata does not show the selected candidate outranking all passing compared candidates"
                    ],
                )
            comparison_status = "lower_ranked_pass"
            candidate_notes.append(
                "candidate passed current runtime validation but still ranked below the selected candidate"
            )
        else:
            comparison_status = "failed_runtime_validation"
            candidate_notes.append(
                "candidate failed current runtime validation and therefore was not a viable V7 winner"
            )
        if evaluation_summary is not None:
            candidate_notes.append(evaluation_summary)

        compared_candidate_views.append(
            _candidate_prior_divergence_compared_candidate_view(
                audit_candidate=compared_candidate,
                comparison_candidate=comparison_candidate,
                comparison_status=comparison_status,
                notes=candidate_notes,
            )
        )
        comparison_statuses.append(comparison_status)

    if all(status == "failed_runtime_validation" for status in comparison_statuses):
        status = "divergence_explained_by_runtime_failures"
        _append_unique_note(
            notes,
            "every compared positive-prior candidate failed current runtime validation",
        )
    elif all(status == "lower_ranked_pass" for status in comparison_statuses):
        status = "divergence_explained_by_runtime_scoring"
        _append_unique_note(
            notes,
            "at least one compared positive-prior candidate passed current validation, but the selected candidate still outranked them all",
        )
    else:
        status = "divergence_explained_by_mixed_runtime_outcomes"
        _append_unique_note(
            notes,
            "compared positive-prior candidates split across runtime failures and lower-ranked passing outcomes",
        )

    return {
        "candidate_prior_divergence_explanation_version": "v1",
        "status": status,
        "candidate_prior_audit_status": audit_status,
        "selected_candidate": selected_candidate,
        "history_summary": history_summary,
        "compared_positive_prior_candidates": compared_candidate_views,
        "notes": notes,
    }


_MIN_USABLE_READINESS_RECEIPTS = 3
_MIN_POSITIVE_SIGNAL_READINESS_RECEIPTS = 2
_READINESS_DOMINANCE_NUMERATOR = 2
_READINESS_DOMINANCE_DENOMINATOR = 3


def _candidate_prior_readiness_history_summary(
    *,
    exact_match_receipt_count: int,
    replay_healthy_receipt_count: int,
    usable_receipt_count: int,
    convergent_receipt_count: int,
    no_positive_prior_receipt_count: int,
    runtime_failure_divergence_count: int,
    runtime_scoring_divergence_count: int,
    mixed_divergence_count: int,
    unresolved_receipt_count: int,
    unusable_receipt_count: int,
) -> dict[str, int]:
    return {
        "exact_match_receipt_count": max(0, int(exact_match_receipt_count)),
        "replay_healthy_receipt_count": max(0, int(replay_healthy_receipt_count)),
        "usable_receipt_count": max(0, int(usable_receipt_count)),
        "convergent_receipt_count": max(0, int(convergent_receipt_count)),
        "no_positive_prior_receipt_count": max(0, int(no_positive_prior_receipt_count)),
        "runtime_failure_divergence_count": max(
            0, int(runtime_failure_divergence_count)
        ),
        "runtime_scoring_divergence_count": max(
            0, int(runtime_scoring_divergence_count)
        ),
        "mixed_divergence_count": max(0, int(mixed_divergence_count)),
        "unresolved_receipt_count": max(0, int(unresolved_receipt_count)),
        "unusable_receipt_count": max(0, int(unusable_receipt_count)),
    }


def _candidate_prior_readiness_considered_receipt(
    *,
    match: ModuleSynthesisEvidenceMatch,
) -> tuple[dict[str, Any], str | None, bool]:
    historical_diagnostics = match.receipt.historical_diagnostics
    considered = {
        "receipt_path": match.receipt.receipt_path,
        "created_at": match.receipt.created_at,
        "candidate_prior_audit_status": None,
        "candidate_prior_divergence_explanation_status": None,
        "usable_for_readiness": False,
        "notes": [],
    }
    notes: list[str] = considered["notes"]

    if historical_diagnostics is None:
        notes.append(
            "receipt missing persisted synthesis_diagnostics required for candidate-prior readiness"
        )
        return considered, None, False

    candidate_prior_audit = historical_diagnostics.candidate_prior_audit
    if not isinstance(candidate_prior_audit, Mapping):
        notes.append(
            "receipt missing persisted candidate_prior_audit required for candidate-prior readiness"
        )
        return considered, None, False
    candidate_prior_divergence_explanation = (
        historical_diagnostics.candidate_prior_divergence_explanation
    )
    if not isinstance(candidate_prior_divergence_explanation, Mapping):
        notes.append(
            "receipt missing persisted candidate_prior_divergence_explanation required for candidate-prior readiness"
        )
        return considered, None, False

    audit_status = _optional_str(candidate_prior_audit.get("status"))
    divergence_status = _optional_str(
        candidate_prior_divergence_explanation.get("status")
    )
    considered["candidate_prior_audit_status"] = audit_status
    considered["candidate_prior_divergence_explanation_status"] = divergence_status

    if audit_status is None or divergence_status is None:
        notes.append(
            "receipt persisted candidate-prior audit/divergence status fields are malformed"
        )
        return considered, None, False
    if divergence_status == "candidate_prior_divergence_unavailable":
        notes.append(
            "receipt persisted candidate_prior_divergence_explanation is unavailable and cannot support readiness rollup"
        )
        return considered, None, False

    if audit_status == "selected_matches_positive_winner_history":
        if divergence_status != "no_divergence_to_explain":
            notes.append(
                "receipt persisted candidate-prior audit/divergence statuses disagree for a convergent outcome"
            )
            return considered, None, False
        considered["usable_for_readiness"] = True
        notes.append(
            "receipt shows selected candidate aligned with positive prior support"
        )
        return considered, "convergent", True

    if audit_status == "no_positive_prior_candidates":
        if divergence_status != "no_divergence_to_explain":
            notes.append(
                "receipt persisted candidate-prior audit/divergence statuses disagree for a no-positive-prior outcome"
            )
            return considered, None, False
        considered["usable_for_readiness"] = True
        notes.append(
            "receipt has no positive-prior-supported candidates under current exact-match history"
        )
        return considered, "no_positive_prior", True

    if audit_status in {
        "selected_candidate_prior_unsupported",
        "selected_candidate_prior_degraded",
    }:
        if divergence_status != "selected_candidate_prior_unresolved":
            notes.append(
                "receipt persisted candidate-prior audit/divergence statuses disagree for an unresolved selected-candidate prior outcome"
            )
            return considered, None, False
        considered["usable_for_readiness"] = True
        notes.append(
            "receipt prior divergence remains unresolved under bounded prior authority"
        )
        return considered, "unresolved", True

    if audit_status != "positive_prior_candidates_present_but_not_selected":
        notes.append(
            "receipt persisted candidate-prior audit status is unsupported for readiness rollup"
        )
        return considered, None, False

    if divergence_status == "divergence_explained_by_runtime_failures":
        considered["usable_for_readiness"] = True
        notes.append("receipt divergence was explained by current runtime failures")
        return considered, "runtime_failure", True
    if divergence_status == "divergence_explained_by_runtime_scoring":
        considered["usable_for_readiness"] = True
        notes.append("receipt divergence was explained by current V7 runtime scoring")
        return considered, "runtime_scoring", True
    if divergence_status == "divergence_explained_by_mixed_runtime_outcomes":
        considered["usable_for_readiness"] = True
        notes.append(
            "receipt divergence split across runtime failures and lower-ranked passing outcomes"
        )
        return considered, "mixed", True

    notes.append(
        "receipt persisted candidate-prior divergence status is unsupported for readiness rollup"
    )
    return considered, None, False


def build_unavailable_module_synthesis_candidate_prior_readiness_advisory(
    *,
    bundle: ModuleSynthesisEvidenceBundle | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    exact_match_receipt_count = (
        len(bundle.exact_match_receipts) if bundle is not None else 0
    )
    replay_healthy_receipt_count = (
        bundle.positive_evidence_count if bundle is not None else 0
    )
    return {
        "candidate_prior_readiness_advisory_version": "v1",
        "status": "candidate_prior_readiness_unavailable",
        "history_summary": _candidate_prior_readiness_history_summary(
            exact_match_receipt_count=exact_match_receipt_count,
            replay_healthy_receipt_count=replay_healthy_receipt_count,
            usable_receipt_count=0,
            convergent_receipt_count=0,
            no_positive_prior_receipt_count=0,
            runtime_failure_divergence_count=0,
            runtime_scoring_divergence_count=0,
            mixed_divergence_count=0,
            unresolved_receipt_count=0,
            unusable_receipt_count=replay_healthy_receipt_count,
        ),
        "considered_receipts": [],
        "notes": list(notes or ["candidate-prior readiness advisory unavailable"]),
    }


def build_module_synthesis_candidate_prior_readiness_advisory(
    bundle: ModuleSynthesisEvidenceBundle,
) -> dict[str, Any]:
    replay_healthy_matches = [
        match for match in bundle.exact_match_receipts if match.positive_evidence
    ]
    notes = [
        "candidate-prior readiness advisory is descriptive only; V7 ranking and promotion remain unchanged"
    ]
    if not bundle.exact_match_receipts:
        notes.append("no exact-match receipts retrieved for candidate-prior readiness")
    elif not replay_healthy_matches:
        notes.append(
            "exact-match history exists, but no replay-healthy receipts qualify for candidate-prior readiness"
        )

    if bundle.exact_match_receipt_scan_errors:
        notes.append(
            "exact-match receipt scan errors prevent a bounded candidate-prior readiness rollup"
        )
        return {
            "candidate_prior_readiness_advisory_version": "v1",
            "status": "candidate_prior_readiness_unavailable",
            "history_summary": _candidate_prior_readiness_history_summary(
                exact_match_receipt_count=len(bundle.exact_match_receipts),
                replay_healthy_receipt_count=len(replay_healthy_matches),
                usable_receipt_count=0,
                convergent_receipt_count=0,
                no_positive_prior_receipt_count=0,
                runtime_failure_divergence_count=0,
                runtime_scoring_divergence_count=0,
                mixed_divergence_count=0,
                unresolved_receipt_count=0,
                unusable_receipt_count=0,
            ),
            "considered_receipts": [],
            "notes": notes,
        }

    considered_receipts: list[dict[str, Any]] = []
    counts = {
        "convergent": 0,
        "no_positive_prior": 0,
        "runtime_failure": 0,
        "runtime_scoring": 0,
        "mixed": 0,
        "unresolved": 0,
        "unusable": 0,
    }
    for match in replay_healthy_matches:
        considered_receipt, category, usable = (
            _candidate_prior_readiness_considered_receipt(
                match=match,
            )
        )
        considered_receipts.append(considered_receipt)
        if usable and category is not None:
            counts[category] += 1
        else:
            counts["unusable"] += 1

    history_summary = _candidate_prior_readiness_history_summary(
        exact_match_receipt_count=len(bundle.exact_match_receipts),
        replay_healthy_receipt_count=len(replay_healthy_matches),
        usable_receipt_count=(
            counts["convergent"]
            + counts["no_positive_prior"]
            + counts["runtime_failure"]
            + counts["runtime_scoring"]
            + counts["mixed"]
            + counts["unresolved"]
        ),
        convergent_receipt_count=counts["convergent"],
        no_positive_prior_receipt_count=counts["no_positive_prior"],
        runtime_failure_divergence_count=counts["runtime_failure"],
        runtime_scoring_divergence_count=counts["runtime_scoring"],
        mixed_divergence_count=counts["mixed"],
        unresolved_receipt_count=counts["unresolved"],
        unusable_receipt_count=counts["unusable"],
    )

    if counts["unusable"] > 0:
        notes.append(
            "at least one replay-healthy exact-match receipt lacks well-formed persisted candidate-prior readiness inputs"
        )
        return {
            "candidate_prior_readiness_advisory_version": "v1",
            "status": "candidate_prior_readiness_unavailable",
            "history_summary": history_summary,
            "considered_receipts": considered_receipts,
            "notes": notes,
        }

    positive_signal_receipt_count = (
        counts["convergent"]
        + counts["runtime_failure"]
        + counts["runtime_scoring"]
        + counts["mixed"]
        + counts["unresolved"]
    )
    usable_receipt_count = history_summary["usable_receipt_count"]
    if (
        usable_receipt_count < _MIN_USABLE_READINESS_RECEIPTS
        or positive_signal_receipt_count < _MIN_POSITIVE_SIGNAL_READINESS_RECEIPTS
    ):
        notes.append(
            "candidate-prior readiness remains sparse until at least three usable replay-healthy exact-match receipts and at least two receipts with positive-prior signal exist"
        )
        return {
            "candidate_prior_readiness_advisory_version": "v1",
            "status": "insufficient_prior_history",
            "history_summary": history_summary,
            "considered_receipts": considered_receipts,
            "notes": notes,
        }

    if counts["mixed"] > 0 or counts["unresolved"] > 0:
        notes.append(
            "candidate-prior readiness remains mixed or unresolved across replay-healthy exact-match history"
        )
        return {
            "candidate_prior_readiness_advisory_version": "v1",
            "status": "priors_mixed_or_inconclusive",
            "history_summary": history_summary,
            "considered_receipts": considered_receipts,
            "notes": notes,
        }

    divergence_receipt_count = counts["runtime_failure"] + counts["runtime_scoring"]
    if divergence_receipt_count > 0:
        if (
            counts["runtime_failure"] * _READINESS_DOMINANCE_DENOMINATOR
            >= divergence_receipt_count * _READINESS_DOMINANCE_NUMERATOR
            and counts["runtime_failure"] > counts["runtime_scoring"]
        ):
            notes.append(
                "replay-healthy divergence cases are mostly blocked by current runtime failures"
            )
            status = "priors_mostly_blocked_by_runtime_failures"
        elif (
            counts["runtime_scoring"] * _READINESS_DOMINANCE_DENOMINATOR
            >= divergence_receipt_count * _READINESS_DOMINANCE_NUMERATOR
            and counts["runtime_scoring"] > counts["runtime_failure"]
        ):
            notes.append(
                "replay-healthy divergence cases are mostly viable but still lose under current V7 scoring"
            )
            status = "priors_mostly_outscored_under_v7"
        else:
            notes.append(
                "replay-healthy divergence cases split too evenly across runtime-failure and runtime-scoring outcomes"
            )
            status = "priors_mixed_or_inconclusive"
        return {
            "candidate_prior_readiness_advisory_version": "v1",
            "status": status,
            "history_summary": history_summary,
            "considered_receipts": considered_receipts,
            "notes": notes,
        }

    notes.append(
        "usable replay-healthy exact-match history shows prior-supported outcomes without persistent divergence cases"
    )
    return {
        "candidate_prior_readiness_advisory_version": "v1",
        "status": "priors_consistently_convergent",
        "history_summary": history_summary,
        "considered_receipts": considered_receipts,
        "notes": notes,
    }


def _candidate_prior_counterfactual_history_summary(
    candidate_prior_readiness_advisory: Mapping[str, Any] | None,
    *,
    passing_positive_prior_candidate_count: int,
) -> dict[str, int]:
    history_summary_raw = _as_dict(
        _as_dict(candidate_prior_readiness_advisory).get("history_summary")
    )
    positive_prior_signal_receipt_count = (
        _as_int(history_summary_raw.get("convergent_receipt_count"), default=0)
        + _as_int(
            history_summary_raw.get("runtime_failure_divergence_count"), default=0
        )
        + _as_int(
            history_summary_raw.get("runtime_scoring_divergence_count"), default=0
        )
        + _as_int(history_summary_raw.get("mixed_divergence_count"), default=0)
        + _as_int(history_summary_raw.get("unresolved_receipt_count"), default=0)
    )
    return {
        "exact_match_receipt_count": _as_int(
            history_summary_raw.get("exact_match_receipt_count"), default=0
        ),
        "replay_healthy_receipt_count": _as_int(
            history_summary_raw.get("replay_healthy_receipt_count"), default=0
        ),
        "usable_receipt_count": _as_int(
            history_summary_raw.get("usable_receipt_count"), default=0
        ),
        "positive_prior_signal_receipt_count": positive_prior_signal_receipt_count,
        "passing_positive_prior_candidate_count": max(
            0, int(passing_positive_prior_candidate_count)
        ),
    }


def _candidate_prior_counterfactual_selected_candidate_view(
    *,
    audit_candidate: Mapping[str, Any] | None,
    divergence_candidate: Mapping[str, Any] | None,
    comparison_candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    audit = _as_dict(audit_candidate)
    divergence = _as_dict(divergence_candidate)
    comparison = _as_dict(comparison_candidate)
    rank = _as_int(comparison.get("rank"), default=0)
    if rank <= 0:
        rank = _as_int(divergence.get("rank"), default=0)
    comparison_ranking_score = _optional_float(comparison.get("ranking_score"))
    divergence_ranking_score = _optional_float(divergence.get("ranking_score"))
    return {
        "candidate_id": _optional_str(audit.get("candidate_id"))
        or _optional_str(divergence.get("candidate_id")),
        "variant_id": _optional_str(audit.get("variant_id"))
        or _optional_str(divergence.get("variant_id")),
        "variant_origin": _optional_str(audit.get("variant_origin"))
        or _optional_str(divergence.get("variant_origin")),
        "rank": rank if rank > 0 else None,
        "ranking_score": (
            comparison_ranking_score
            if comparison_ranking_score is not None
            else divergence_ranking_score
        ),
    }


def _candidate_prior_counterfactual_candidate_view(
    *,
    audit_candidate: Mapping[str, Any],
    comparison_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    comparison = _as_dict(comparison_candidate)
    notes = [
        "candidate passed current runtime validation but still ranked below the selected candidate under trusted V7 scoring"
    ]
    evaluation_summary = _optional_str(comparison.get("evaluation_summary"))
    if evaluation_summary is not None:
        notes.append(evaluation_summary)
    return {
        "candidate_id": _optional_str(audit_candidate.get("candidate_id")),
        "variant_id": _optional_str(audit_candidate.get("variant_id")),
        "variant_origin": _optional_str(audit_candidate.get("variant_origin")),
        "rank": _as_int(comparison.get("rank"), default=0),
        "ranking_score": _optional_float(comparison.get("ranking_score")),
        "evaluation_status": _optional_str(comparison.get("evaluation_status")),
        "notes": notes,
    }


def build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
    *,
    candidate_prior_readiness_advisory: Mapping[str, Any] | None,
    candidate_prior_divergence_explanation: Mapping[str, Any] | None,
    candidate_prior_audit: Mapping[str, Any] | None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    readiness = _as_dict(candidate_prior_readiness_advisory)
    divergence = _as_dict(candidate_prior_divergence_explanation)
    audit = _as_dict(candidate_prior_audit)
    return {
        "candidate_prior_counterfactual_advisory_version": "v1",
        "status": "candidate_prior_counterfactual_unavailable",
        "candidate_prior_readiness_status": _optional_str(readiness.get("status")),
        "candidate_prior_divergence_explanation_status": _optional_str(
            divergence.get("status")
        ),
        "selected_candidate": _candidate_prior_counterfactual_selected_candidate_view(
            audit_candidate=_as_dict(audit.get("selected_candidate")),
            divergence_candidate=_as_dict(divergence.get("selected_candidate")),
            comparison_candidate=None,
        ),
        "history_summary": _candidate_prior_counterfactual_history_summary(
            readiness,
            passing_positive_prior_candidate_count=0,
        ),
        "counterfactual_positive_prior_candidates": [],
        "notes": list(notes or ["candidate-prior counterfactual advisory unavailable"]),
    }


_COUNTERFACTUAL_ALLOWED_READINESS_STATUSES = {
    "candidate_prior_readiness_unavailable",
    "insufficient_prior_history",
    "priors_consistently_convergent",
    "priors_mostly_blocked_by_runtime_failures",
    "priors_mostly_outscored_under_v7",
    "priors_mixed_or_inconclusive",
}

_COUNTERFACTUAL_ALLOWED_AUDIT_STATUSES = {
    "candidate_priors_unavailable",
    "selected_matches_positive_winner_history",
    "no_positive_prior_candidates",
    "selected_candidate_prior_unsupported",
    "selected_candidate_prior_degraded",
    "positive_prior_candidates_present_but_not_selected",
}

_COUNTERFACTUAL_ALLOWED_DIVERGENCE_STATUSES = {
    "candidate_prior_divergence_unavailable",
    "no_divergence_to_explain",
    "selected_candidate_prior_unresolved",
    "divergence_explained_by_runtime_failures",
    "divergence_explained_by_runtime_scoring",
    "divergence_explained_by_mixed_runtime_outcomes",
}


def _candidate_prior_counterfactual_identity(
    candidate: Mapping[str, Any] | None,
) -> tuple[str | None, str | None, str | None]:
    candidate_view = _as_dict(candidate)
    return (
        _optional_str(candidate_view.get("candidate_id")),
        _optional_str(candidate_view.get("variant_id")),
        _optional_str(candidate_view.get("variant_origin")),
    )


def build_module_synthesis_candidate_prior_counterfactual_advisory(
    candidate_prior_readiness_advisory: Mapping[str, Any] | None,
    candidate_prior_divergence_explanation: Mapping[str, Any] | None,
    candidate_prior_audit: Mapping[str, Any] | None,
    *,
    ranked_candidate_comparison_inputs: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if not isinstance(candidate_prior_readiness_advisory, Mapping):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=None,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior readiness advisory is missing"
            ],
        )
    if not isinstance(candidate_prior_divergence_explanation, Mapping):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=None,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior divergence explanation is missing"
            ],
        )
    if not isinstance(candidate_prior_audit, Mapping):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=None,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior audit is missing"
            ],
        )

    readiness_status = _optional_str(candidate_prior_readiness_advisory.get("status"))
    divergence_status = _optional_str(
        candidate_prior_divergence_explanation.get("status")
    )
    audit_status = _optional_str(candidate_prior_audit.get("status"))
    if readiness_status is None or divergence_status is None or audit_status is None:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because required SG2 status fields are malformed"
            ],
        )
    if readiness_status not in _COUNTERFACTUAL_ALLOWED_READINESS_STATUSES:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior readiness advisory status is unsupported"
            ],
        )
    if divergence_status not in _COUNTERFACTUAL_ALLOWED_DIVERGENCE_STATUSES:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior divergence explanation status is unsupported"
            ],
        )
    if audit_status not in _COUNTERFACTUAL_ALLOWED_AUDIT_STATUSES:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior audit status is unsupported"
            ],
        )
    if readiness_status == "candidate_prior_readiness_unavailable":
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior readiness advisory is unavailable"
            ],
        )
    if divergence_status == "candidate_prior_divergence_unavailable":
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior divergence explanation is unavailable"
            ],
        )
    if audit_status == "candidate_priors_unavailable":
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior audit is unavailable"
            ],
        )

    if (
        audit_status
        in {
            "selected_matches_positive_winner_history",
            "no_positive_prior_candidates",
        }
        and divergence_status != "no_divergence_to_explain"
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior audit/divergence surfaces disagree about whether divergence exists"
            ],
        )
    if (
        audit_status
        in {
            "selected_candidate_prior_unsupported",
            "selected_candidate_prior_degraded",
        }
        and divergence_status != "selected_candidate_prior_unresolved"
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior audit/divergence surfaces disagree about selected-candidate prior resolution"
            ],
        )
    if (
        audit_status == "positive_prior_candidates_present_but_not_selected"
        and divergence_status
        not in {
            "divergence_explained_by_runtime_failures",
            "divergence_explained_by_runtime_scoring",
            "divergence_explained_by_mixed_runtime_outcomes",
        }
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because candidate-prior audit/divergence surfaces disagree about the divergence class"
            ],
        )

    selected_candidate_audit = _as_dict(candidate_prior_audit.get("selected_candidate"))
    selected_candidate_divergence = _as_dict(
        candidate_prior_divergence_explanation.get("selected_candidate")
    )
    if _candidate_prior_counterfactual_identity(
        selected_candidate_audit
    ) != _candidate_prior_counterfactual_identity(selected_candidate_divergence):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because selected-candidate identity disagrees across SG2 surfaces"
            ],
        )
    selected_candidate_id = _optional_str(selected_candidate_audit.get("candidate_id"))
    if selected_candidate_id is None:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because selected candidate identity is missing"
            ],
        )

    raw_compared_candidates = candidate_prior_audit.get(
        "non_selected_positive_prior_candidates"
    )
    if not isinstance(raw_compared_candidates, list) or any(
        not isinstance(item, Mapping) for item in raw_compared_candidates
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because compared positive-prior candidates are malformed"
            ],
        )
    compared_candidates = [_as_dict(item) for item in raw_compared_candidates]
    divergence_compared_candidates_raw = candidate_prior_divergence_explanation.get(
        "compared_positive_prior_candidates"
    )
    if not isinstance(divergence_compared_candidates_raw, list) or any(
        not isinstance(item, Mapping) for item in divergence_compared_candidates_raw
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because divergence compared-candidate payload is malformed"
            ],
        )
    duplicate_compared_candidate_id = _duplicate_candidate_id(compared_candidates)
    if duplicate_compared_candidate_id is not None:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because the audit comparison set contains duplicate candidate_id entries"
            ],
        )
    duplicate_divergence_compared_candidate_id = _duplicate_candidate_id(
        [_as_dict(item) for item in divergence_compared_candidates_raw]
    )
    if duplicate_divergence_compared_candidate_id is not None:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because divergence compared-candidate payload contains duplicate candidate_id entries"
            ],
        )
    divergence_compared_candidate_ids = {
        candidate_id
        for item in divergence_compared_candidates_raw
        if (candidate_id := _optional_str(item.get("candidate_id"))) is not None
    }
    audit_compared_candidate_ids = {
        candidate_id
        for item in compared_candidates
        if (candidate_id := _optional_str(item.get("candidate_id"))) is not None
    }
    if divergence_compared_candidate_ids != audit_compared_candidate_ids:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because divergence compared-candidate identity disagrees with the audit comparison set"
            ],
        )

    comparison_by_id = _canonicalize_candidate_prior_comparison_inputs(
        ranked_candidate_comparison_inputs
    )
    if comparison_by_id is None:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because trusted current comparison metadata is malformed or duplicated"
            ],
        )
    selected_comparison = comparison_by_id.get(selected_candidate_id)
    if selected_comparison is None:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because trusted current comparison metadata for the selected candidate is incomplete"
            ],
        )
    if not _candidate_prior_divergence_comparison_supported(selected_comparison):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because trusted current comparison metadata for the selected candidate is incomplete"
            ],
        )
    if selected_comparison.get("passed") is not True:
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because the selected candidate lacks a trusted passing runtime result"
            ],
        )
    if _candidate_prior_identity_disagrees_with_current_comparison(
        candidate=selected_candidate_audit,
        comparison_candidate=selected_comparison,
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because selected candidate identity disagrees with trusted current comparison metadata"
            ],
        )

    selected_candidate = _candidate_prior_counterfactual_selected_candidate_view(
        audit_candidate=selected_candidate_audit,
        divergence_candidate=selected_candidate_divergence,
        comparison_candidate=selected_comparison,
    )
    selected_rank = _as_int(selected_comparison.get("rank"), default=0)
    notes = [
        "candidate-prior counterfactual advisory is descriptive only; V7 ranking and promotion remain unchanged"
    ]
    for source in (
        candidate_prior_audit.get("notes"),
        candidate_prior_divergence_explanation.get("notes"),
        candidate_prior_readiness_advisory.get("notes"),
    ):
        if isinstance(source, list):
            for note in source:
                if isinstance(note, str):
                    _append_unique_note(notes, note)

    passing_candidate_views: list[dict[str, Any]] = []
    failed_candidate_count = 0
    for compared_candidate in compared_candidates:
        candidate_id = _optional_str(compared_candidate.get("candidate_id"))
        if candidate_id is None:
            return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
                candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
                candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
                candidate_prior_audit=candidate_prior_audit,
                notes=[
                    "candidate-prior counterfactual advisory unavailable because a compared positive-prior candidate is missing candidate_id"
                ],
            )
        comparison_candidate = comparison_by_id.get(candidate_id)
        if comparison_candidate is None:
            return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
                candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
                candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
                candidate_prior_audit=candidate_prior_audit,
                notes=[
                    "candidate-prior counterfactual advisory unavailable because a compared positive-prior candidate is absent from trusted current comparison metadata"
                ],
            )
        if not _candidate_prior_divergence_comparison_supported(comparison_candidate):
            return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
                candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
                candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
                candidate_prior_audit=candidate_prior_audit,
                notes=[
                    "candidate-prior counterfactual advisory unavailable because trusted current comparison metadata is incomplete for at least one compared positive-prior candidate"
                ],
            )
        if _candidate_prior_identity_disagrees_with_current_comparison(
            candidate=compared_candidate,
            comparison_candidate=comparison_candidate,
        ):
            return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
                candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
                candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
                candidate_prior_audit=candidate_prior_audit,
                notes=[
                    "candidate-prior counterfactual advisory unavailable because a compared positive-prior candidate identity disagrees with trusted current comparison metadata"
                ],
            )

        candidate_rank = _as_int(comparison_candidate.get("rank"), default=0)
        if comparison_candidate.get("passed") is True:
            if candidate_rank <= selected_rank:
                return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
                    candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
                    candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
                    candidate_prior_audit=candidate_prior_audit,
                    notes=[
                        "candidate-prior counterfactual advisory unavailable because trusted current rank metadata does not show the selected candidate outranking all passing compared candidates"
                    ],
                )
            passing_candidate_views.append(
                _candidate_prior_counterfactual_candidate_view(
                    audit_candidate=compared_candidate,
                    comparison_candidate=comparison_candidate,
                )
            )
        else:
            failed_candidate_count += 1

    if (
        divergence_status == "divergence_explained_by_runtime_failures"
        and passing_candidate_views
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because divergence says runtime failures only, but current comparison metadata shows passing positive-prior candidates"
            ],
        )
    if divergence_status == "divergence_explained_by_runtime_scoring" and (
        failed_candidate_count > 0 or not passing_candidate_views
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because divergence says runtime scoring only, but current comparison metadata does not show an all-passing comparison set"
            ],
        )
    if divergence_status == "divergence_explained_by_mixed_runtime_outcomes" and (
        failed_candidate_count == 0 or not passing_candidate_views
    ):
        return build_unavailable_module_synthesis_candidate_prior_counterfactual_advisory(
            candidate_prior_readiness_advisory=candidate_prior_readiness_advisory,
            candidate_prior_divergence_explanation=candidate_prior_divergence_explanation,
            candidate_prior_audit=candidate_prior_audit,
            notes=[
                "candidate-prior counterfactual advisory unavailable because divergence says runtime outcomes were mixed, but current comparison metadata does not show both failed and passing positive-prior candidates"
            ],
        )

    history_summary = _candidate_prior_counterfactual_history_summary(
        candidate_prior_readiness_advisory,
        passing_positive_prior_candidate_count=len(passing_candidate_views),
    )

    if readiness_status == "insufficient_prior_history":
        status = "counterfactual_signal_sparse"
        _append_unique_note(
            notes,
            "candidate-prior history is still too sparse to treat the current run as meaningful predictive signal",
        )
    elif readiness_status in {
        "priors_consistently_convergent",
        "priors_mostly_blocked_by_runtime_failures",
    }:
        status = "no_counterfactual_signal"
        if readiness_status == "priors_consistently_convergent":
            _append_unique_note(
                notes,
                "historical readiness is convergent, so DSPx should not frame the current run as a counterfactual prior signal",
            )
        else:
            _append_unique_note(
                notes,
                "historical readiness is mostly blocked by runtime failures, so DSPx should not frame the current run as a counterfactual prior signal",
            )
    elif divergence_status == "no_divergence_to_explain":
        status = "no_counterfactual_signal"
        _append_unique_note(
            notes,
            "the current run has no selected-vs-prior divergence that would make a counterfactual comparison meaningful",
        )
    elif divergence_status == "divergence_explained_by_runtime_failures":
        status = "no_counterfactual_signal"
        _append_unique_note(
            notes,
            "all positive-prior-supported alternatives failed current runtime validation",
        )
    elif readiness_status == "priors_mixed_or_inconclusive" or divergence_status in {
        "selected_candidate_prior_unresolved",
        "divergence_explained_by_mixed_runtime_outcomes",
    }:
        status = "counterfactual_signal_mixed_or_inconclusive"
        _append_unique_note(
            notes,
            "historical readiness or current divergence remains too mixed to support a narrower counterfactual claim",
        )
    elif (
        readiness_status == "priors_mostly_outscored_under_v7"
        and divergence_status == "divergence_explained_by_runtime_scoring"
    ):
        status = "counterfactual_positive_prior_alternatives_present"
        _append_unique_note(
            notes,
            "the current run contains passing positive-prior-supported alternatives that still lost under trusted V7 scoring",
        )
    else:
        status = "counterfactual_signal_mixed_or_inconclusive"
        _append_unique_note(
            notes,
            "readiness and divergence inputs do not support a narrower counterfactual claim under contract v1",
        )

    return {
        "candidate_prior_counterfactual_advisory_version": "v1",
        "status": status,
        "candidate_prior_readiness_status": readiness_status,
        "candidate_prior_divergence_explanation_status": divergence_status,
        "selected_candidate": selected_candidate,
        "history_summary": history_summary,
        "counterfactual_positive_prior_candidates": passing_candidate_views,
        "notes": notes,
    }


def retrieve_module_synthesis_evidence(
    spec: ModuleSpec,
    *,
    use_signature: bool = False,
    receipts_path: Path | None = None,
    oracle_index_path: Path | None = None,
    oracle_top_k: int = 5,
) -> ModuleSynthesisEvidenceBundle:
    request = ModuleSynthesisEvidenceRequest.from_spec(
        spec, use_signature=use_signature
    )
    resolved_receipts_path = (receipts_path or (Path.cwd() / "generated")).resolve()
    resolved_oracle_index_path = (
        oracle_index_path.resolve()
        if oracle_index_path is not None
        else get_default_index_path().resolve()
    )

    matches: list[ModuleSynthesisEvidenceMatch] = []
    receipt_scan_errors: list[dict[str, Any]] = []
    exact_match_receipt_scan_errors: list[dict[str, Any]] = []
    receipt_paths = _receipt_paths(resolved_receipts_path)
    for meta_path in receipt_paths:
        receipt, receipt_load_error = _load_receipt_for_evidence(meta_path)
        if receipt_load_error is not None:
            receipt_scan_errors.append(receipt_load_error)
            continue
        if receipt is None:
            continue
        if not _exact_match_request(receipt, request):
            continue

        receipt_issue = _exact_match_receipt_issue(meta_path, receipt)
        if receipt_issue is not None:
            receipt_scan_errors.append(receipt_issue)
            exact_match_receipt_scan_errors.append(receipt_issue)
            continue

        try:
            matches.append(
                ModuleSynthesisEvidenceMatch(
                    receipt=_build_receipt_evidence(meta_path, receipt),
                    replay=_build_replay_evidence(meta_path),
                )
            )
        except Exception as exc:
            error = {
                "receipt_path": str(meta_path),
                "code": "receipt_evidence_build_failed",
                "message": str(exc),
                "error_type": exc.__class__.__name__,
                "stage": "evidence_build",
            }
            receipt_scan_errors.append(error)
            exact_match_receipt_scan_errors.append(error)

    matches.sort(
        key=lambda item: _parse_created_at(item.receipt.created_at),
        reverse=True,
    )

    oracle_lookup_status, oracle_neighbors, oracle_lookup_error = (
        _retrieve_oracle_neighbors(
            request,
            oracle_index_path=resolved_oracle_index_path,
            oracle_top_k=oracle_top_k,
        )
    )

    return ModuleSynthesisEvidenceBundle(
        request=request,
        retrieval_order=(
            "exact_match_receipts",
            "replay_verification",
            "oracle_neighbors",
        ),
        exact_match_receipts=tuple(matches),
        oracle_neighbors=oracle_neighbors,
        receipts_path=str(resolved_receipts_path),
        oracle_index_path=str(resolved_oracle_index_path),
        receipts_scanned=len(receipt_paths),
        oracle_query_text=request.oracle_query_text(),
        receipt_scan_errors=tuple(receipt_scan_errors),
        exact_match_receipt_scan_errors=tuple(exact_match_receipt_scan_errors),
        oracle_lookup_status=oracle_lookup_status,
        oracle_lookup_error=oracle_lookup_error,
    )
