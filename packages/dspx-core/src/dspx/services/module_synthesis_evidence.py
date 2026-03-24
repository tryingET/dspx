from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from dspx.coordinates.storage import CoordinateIndex, get_default_index_path
from dspx.dtos import ModuleSpec
from dspx.run_receipts import load_run_receipt
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
    oracle_index_available: bool

    @property
    def positive_evidence_count(self) -> int:
        return sum(1 for item in self.exact_match_receipts if item.positive_evidence)

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
            "oracle_index_available": self.oracle_index_available,
            "positive_evidence_count": self.positive_evidence_count,
        }


def _parse_created_at(raw: Any) -> datetime:
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_str_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _as_ranked_candidates(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            out.append(dict(item))
    return tuple(out)


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


def _eligible_module_synthesis_receipt(
    receipt: Mapping[str, Any],
    request: ModuleSynthesisEvidenceRequest,
) -> bool:
    if str(receipt.get("run_kind") or "") != "module-gen":
        return False

    replay_inputs = _as_dict(receipt.get("replay_inputs"))
    if _request_tuple_from_replay_inputs(replay_inputs) != _request_tuple_from_request(
        request
    ):
        return False

    run_summary = _as_dict(receipt.get("run_summary"))
    if str(run_summary.get("backend") or "") != "synthesis_runtime":
        return False

    selected_candidate_id = str(run_summary.get("selected_candidate_id") or "").strip()
    if not selected_candidate_id:
        return False

    selected_candidate_rank = int(run_summary.get("selected_candidate_rank") or 0)
    if selected_candidate_rank <= 0:
        return False

    ranked_candidate_ids = _as_str_list(run_summary.get("ranked_candidate_ids"))
    if not ranked_candidate_ids:
        return False
    if selected_candidate_id not in ranked_candidate_ids:
        return False

    ranking_policy_id = str(run_summary.get("ranking_policy_id") or "").strip()
    if not ranking_policy_id:
        return False

    return True


def _build_receipt_evidence(
    meta_path: Path,
    receipt: Mapping[str, Any],
) -> ModuleSynthesisReceiptEvidence:
    replay_inputs = _as_dict(receipt.get("replay_inputs"))
    run_summary = _as_dict(receipt.get("run_summary"))
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
        selected_candidate_rank=int(run_summary.get("selected_candidate_rank") or 0),
        ranked_candidate_ids=_as_str_list(run_summary.get("ranked_candidate_ids")),
        ranking_policy_id=str(run_summary.get("ranking_policy_id") or ""),
        ranking_policy_version=(
            str(run_summary.get("ranking_policy_version"))
            if run_summary.get("ranking_policy_version") not in {None, ""}
            else None
        ),
        validation_pass_count=int(run_summary.get("validation_pass_count") or 0),
        validation_total=int(run_summary.get("validation_total") or 0),
        smoke_pass_count=int(run_summary.get("smoke_pass_count") or 0),
        smoke_total=int(run_summary.get("smoke_total") or 0),
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
) -> tuple[bool, tuple[ModuleSynthesisOracleNeighbor, ...]]:
    if not oracle_index_path.exists():
        return False, ()

    try:
        index = CoordinateIndex(db_path=oracle_index_path)
        results = index.search_by_text(
            request.oracle_query_text(),
            top_k=oracle_top_k,
            run_kind="module-gen",
        )
    except Exception:
        return False, ()

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
    return True, tuple(neighbors)


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
    receipt_paths = _receipt_paths(resolved_receipts_path)
    for meta_path in receipt_paths:
        receipt = load_run_receipt(meta_path)
        if not isinstance(receipt, dict):
            continue
        if not _eligible_module_synthesis_receipt(receipt, request):
            continue
        matches.append(
            ModuleSynthesisEvidenceMatch(
                receipt=_build_receipt_evidence(meta_path, receipt),
                replay=_build_replay_evidence(meta_path),
            )
        )

    matches.sort(
        key=lambda item: _parse_created_at(item.receipt.created_at),
        reverse=True,
    )

    oracle_index_available, oracle_neighbors = _retrieve_oracle_neighbors(
        request,
        oracle_index_path=resolved_oracle_index_path,
        oracle_top_k=oracle_top_k,
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
        oracle_index_available=oracle_index_available,
    )
