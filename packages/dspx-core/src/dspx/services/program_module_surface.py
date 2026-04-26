from __future__ import annotations

from typing import Any, Mapping

from dspx.services.program_contracts import intent_surface_names, sanitize_ident
from dspx.services.program_topology import (
    has_declared_pipeline_topology,
    module_class_name,
    validate_materializable_pipeline_topology,
)

PROGRAM_MODULE_SURFACE_SCHEMA = "program-module-surface-v1"
PROGRAM_MODULE_SURFACES_SCHEMA = "program-module-surfaces-v1"

_MODULE_SURFACE_EFFECTS = {
    "network": False,
    "filesystem_read": False,
    "filesystem_write": False,
    "external_authority": False,
}

_MODULE_SURFACE_NON_AUTHORITY = {
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "promotion_authority": False,
    "governance_authority": False,
    "external_mutation": False,
}


def _module_signature(module: Mapping[str, Any]) -> dict[str, Any]:
    signature = module.get("signature")
    return dict(signature) if isinstance(signature, Mapping) else {}


def _signature_class_name(module: Mapping[str, Any]) -> str:
    signature = _module_signature(module)
    return sanitize_ident(str(signature.get("name") or module.get("id")))


def _signature_inputs(module: Mapping[str, Any]) -> list[str]:
    signature = _module_signature(module)
    return [str(item) for item in signature.get("inputs", [])]


def _signature_outputs(module: Mapping[str, Any]) -> list[str]:
    signature = _module_signature(module)
    return [str(item) for item in signature.get("outputs", [])]


def _module_surface_contract(
    *,
    module_id: str,
    source_kind: str,
    primitive: str,
    signature_name: str,
    inputs: list[str],
    outputs: list[str],
    module_class: str,
) -> dict[str, Any]:
    signature = {
        "name": signature_name,
        "inputs": list(inputs),
        "outputs": list(outputs),
    }
    return {
        "schema_version": PROGRAM_MODULE_SURFACE_SCHEMA,
        "module_id": module_id,
        "source_kind": source_kind,
        "primitive": primitive,
        "signature": signature,
        "generated": {
            "signature_class": signature_name,
            "module_class": module_class,
            "signature_path": "signature.py",
            "module_path": "module.py",
        },
        "io": {"inputs": list(inputs), "outputs": list(outputs)},
        "effects": dict(_MODULE_SURFACE_EFFECTS),
        "authority": "module_surface_contract_only_non_authoritative",
        "non_authority": dict(_MODULE_SURFACE_NON_AUTHORITY),
    }


def build_single_module_surface_contract(intent: Any) -> dict[str, Any]:
    """Build the generated single-module scaffold module-surface contract."""

    names = intent_surface_names(intent)
    return _module_surface_contract(
        module_id="generated_module",
        source_kind="generated_single_module_scaffold",
        primitive="Predict",
        signature_name=names["signature_class"],
        inputs=[str(item) for item in getattr(intent, "inputs", [])],
        outputs=[str(item) for item in getattr(intent, "outputs", [])],
        module_class=names["module_class"],
    )


def build_pipeline_module_surface_contracts(intent: Any) -> list[dict[str, Any]]:
    """Build one generated module-surface contract per materialized pipeline module."""

    topology = validate_materializable_pipeline_topology(intent)
    modules = [dict(item) for item in topology.get("modules", [])]
    return [
        _module_surface_contract(
            module_id=str(module.get("id") or ""),
            source_kind="generated_topology_module",
            primitive=str(module.get("primitive") or "Predict"),
            signature_name=_signature_class_name(module),
            inputs=_signature_inputs(module),
            outputs=_signature_outputs(module),
            module_class=module_class_name(module),
        )
        for module in modules
    ]


def build_program_module_surfaces(intent: Any) -> dict[str, Any]:
    """Build the standalone program module-surfaces artifact payload.

    The contract describes generated module surfaces that program-gen composed.
    It does not import, execute, rank, promote, or grant authority to modules.
    """

    if has_declared_pipeline_topology(intent):
        surfaces = build_pipeline_module_surface_contracts(intent)
    else:
        surfaces = [build_single_module_surface_contract(intent)]
    return {
        "schema_version": PROGRAM_MODULE_SURFACES_SCHEMA,
        "status": "materialized",
        "module_surface_count": len(surfaces),
        "module_surfaces": surfaces,
        "authority": "module_surface_contracts_only_non_authoritative",
        "non_authority": dict(_MODULE_SURFACE_NON_AUTHORITY),
        "notes": [
            "program-gen composes generated module surfaces through this replayable contract.",
            "Future local custom module references can use the same IO-declared surface shape once a safe declared-only/import-free contract lands.",
            "This artifact does not execute arbitrary custom Python modules and carries no ranking, promotion, governance, or external mutation authority.",
        ],
    }
