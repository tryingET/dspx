from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


class AuthorityExportAdapter:
    """Build external authority export packets from DSPx evidence.

    Authority adapters sit outside deterministic program materialization. They consume
    DSPx manifests/receipts and produce adapter-owned packets that another operator or
    integration may explicitly apply later.
    """

    name: str

    def build_export_plan(
        self,
        *,
        manifest_path: Path,
        receipt_path: Optional[Path] = None,
        external_ref: Optional[str] = None,
    ) -> dict[str, Any]:  # pragma: no cover - interface method
        raise NotImplementedError


@dataclass(frozen=True)
class AgentKernelAuthorityAdapter(AuthorityExportAdapter):
    """Plan an Agent Kernel authority export without invoking AK.

    This is deliberately a planning adapter, not a mutation adapter. It does not shell
    out to `ak`, does not write AK task state, and does not promote a candidate.
    """

    name: str = "agent_kernel"

    def build_export_plan(
        self,
        *,
        manifest_path: Path,
        receipt_path: Optional[Path] = None,
        external_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        manifest_file = manifest_path.expanduser().resolve()
        manifest = _load_json_object(manifest_file)
        receipt_file = (
            receipt_path.expanduser().resolve()
            if receipt_path is not None
            else manifest_file.with_name(f"{manifest_file.name}.meta.json")
        )
        receipt = _load_json_object(receipt_file) if receipt_file.exists() else None
        _validate_program_manifest(manifest, manifest_file)

        candidate = _object(manifest.get("candidate_assembly"))
        promotion_review = _object(manifest.get("program_promotion_review"))
        adjudication_request = _object(
            manifest.get("program_promotion_adjudication_request")
        )
        receipt_bundle = _object(manifest.get("receipt_bundle"))
        evidence = _object(receipt_bundle.get("evidence"))
        external_refs = _agent_kernel_refs(promotion_review, explicit_ref=external_ref)

        return {
            "schema_version": "dspx-agent-kernel-authority-export-plan-v1",
            "adapter": self.name,
            "status": "planned_not_exported",
            "mutation": "none",
            "source": {
                "manifest": str(manifest_file),
                "receipt": str(receipt_file) if receipt is not None else None,
                "manifest_schema_version": manifest.get("schema_version"),
                "receipt_version": receipt.get("receipt_version")
                if isinstance(receipt, Mapping)
                else None,
            },
            "candidate": {
                "assembly_id": candidate.get("assembly_id"),
                "candidate_id": candidate.get("candidate_id"),
                "request_id": candidate.get("request_id"),
                "artifact_kind": candidate.get("artifact_kind"),
                "root_path": candidate.get("root_path"),
                "entrypoint": candidate.get("entrypoint"),
                "content_hash": candidate.get("content_hash"),
                "promotion_state": promotion_review.get("promotion_state"),
            },
            "promotion": {
                "adjudicator": promotion_review.get("adjudicator"),
                "decision_authority": promotion_review.get("decision_authority"),
                "review_required": promotion_review.get("review_required"),
                "blocking_conditions": list(
                    promotion_review.get("blocking_conditions") or []
                ),
                "missing_required_evidence": list(
                    adjudication_request.get("missing_required_evidence") or []
                ),
            },
            "external_refs": external_refs,
            "evidence_packet": {
                "manifest_hash": _sha_from_receipt(receipt),
                "plan_hash": evidence.get("plan_hash"),
                "jury_hash": evidence.get("jury_hash"),
                "jury_selection_hash": evidence.get("jury_selection_hash"),
                "jury_rubric_hash": evidence.get("jury_rubric_hash"),
                "promotion_review_hash": evidence.get("promotion_review_hash"),
                "promotion_adjudication_request_hash": evidence.get(
                    "promotion_adjudication_request_hash"
                ),
                "promotion_decision_template_hash": evidence.get(
                    "promotion_decision_template_hash"
                ),
                "generated_files": list(evidence.get("generated_files") or []),
            },
            "non_authority": {
                "external_mutation": False,
                "ak_command_invoked": False,
                "program_promoted": False,
                "oracle_authority": False,
            },
            "notes": [
                "This adapter output is an explicit export plan, not an AK mutation.",
                "Apply/record steps must happen through an external operator-approved AK integration.",
                "DSPx core evidence remains non-authoritative until an external authority records a decision.",
            ],
        }


def build_agent_kernel_export_plan(
    manifest_path: Path,
    *,
    receipt_path: Optional[Path] = None,
    external_ref: Optional[str] = None,
) -> dict[str, Any]:
    """Build an Agent Kernel export plan from a program-gen manifest."""

    return AgentKernelAuthorityAdapter().build_export_plan(
        manifest_path=manifest_path,
        receipt_path=receipt_path,
        external_ref=external_ref,
    )


def write_export_plan(plan: Mapping[str, Any], out: Path) -> Path:
    """Write an authority export plan as stable, sorted JSON."""

    target = out.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"authority export input not found: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"authority export input must be a JSON object: {path}")
    return payload


def _validate_program_manifest(manifest: Mapping[str, Any], path: Path) -> None:
    if manifest.get("schema_version") != "program-candidate-assembly-v1":
        raise ValueError(f"not a program-gen candidate assembly manifest: {path}")
    candidate = _object(manifest.get("candidate_assembly"))
    if candidate.get("artifact_kind") != "program":
        raise ValueError(f"program-gen manifest artifact_kind must be program: {path}")


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _agent_kernel_refs(
    promotion_review: Mapping[str, Any], *, explicit_ref: Optional[str]
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if explicit_ref:
        refs.append(
            {
                "system": "agent_kernel",
                "ref": str(explicit_ref),
                "role": "operator_supplied_export_target",
                "status": "not_exported",
                "source": "adapter.argument.external_ref",
            }
        )
    external_authority = _object(promotion_review.get("external_authority"))
    for raw_ref in external_authority.get("refs") or []:
        if not isinstance(raw_ref, Mapping):
            continue
        system = str(raw_ref.get("system") or raw_ref.get("adapter") or "").strip()
        if system and system != "agent_kernel":
            continue
        ref_value = raw_ref.get("ref") or raw_ref.get("id")
        if ref_value is None:
            continue
        ref = {str(key): value for key, value in raw_ref.items() if value is not None}
        ref.setdefault("system", "agent_kernel")
        ref.setdefault("status", "not_exported")
        refs.append(ref)
    return refs


def _sha_from_receipt(receipt: Any) -> Optional[str]:
    if not isinstance(receipt, Mapping):
        return None
    value = receipt.get("hash") or receipt.get("output_hash")
    return str(value) if value is not None else None
