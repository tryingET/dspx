# summary: "Resolves bounded local retriever corpora into deterministic inline snapshots embedded in generated program intents."
# read_when:
#   - "Changing local corpus retriever materialization, corpus bounds, snapshot normalization, or runtime isolation policy."
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_capabilities import normalize_inline_retriever_config
from dspx.services.program_intent import ProgramIntent

PROGRAM_RETRIEVER_SNAPSHOTS_SCHEMA = "program-retriever-snapshots-v1"
_MAX_LOCAL_CORPUS_TOTAL_CHARS = 200_000
_MAX_LOCAL_CORPUS_SOURCE_BYTES = 1_000_000


class ProgramRetrieverSnapshotError(ValueError):
    """Raised when a declared retriever snapshot cannot be safely materialized."""


def _json_text(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve_local_corpus_path(raw_path: object, *, intent_source: Path) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        raise ProgramRetrieverSnapshotError(
            "local_corpus_snapshot retriever.path must not be blank"
        )
    requested = Path(text).expanduser()
    if requested.is_absolute():
        raise ProgramRetrieverSnapshotError(
            "local_corpus_snapshot retriever.path must be relative to the intent file"
        )
    base = intent_source.expanduser().resolve().parent
    resolved = (base / requested).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ProgramRetrieverSnapshotError(
            "local_corpus_snapshot retriever.path must stay under the intent file directory"
        ) from exc
    if not resolved.exists() or not resolved.is_file():
        raise ProgramRetrieverSnapshotError(
            f"local_corpus_snapshot retriever.path does not exist: {text}"
        )
    return resolved


def _read_bounded_corpus_text(path: Path) -> str:
    with path.open("rb") as fh:
        data = fh.read(_MAX_LOCAL_CORPUS_SOURCE_BYTES + 1)
    if len(data) > _MAX_LOCAL_CORPUS_SOURCE_BYTES:
        raise ProgramRetrieverSnapshotError(
            "local_corpus_snapshot source file exceeds byte limit "
            f"{_MAX_LOCAL_CORPUS_SOURCE_BYTES}"
        )
    return data.decode("utf-8")


def _load_corpus_records(path: Path, *, text: str) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ProgramRetrieverSnapshotError(
                    f"local_corpus_snapshot JSONL line {line_number} is not valid JSON"
                ) from exc
            if not isinstance(payload, Mapping):
                raise ProgramRetrieverSnapshotError(
                    f"local_corpus_snapshot JSONL line {line_number} must be an object"
                )
            records.append(dict(payload))
        return records
    if suffix == ".json":
        payload = json.loads(text)
        if not isinstance(payload, list) or not all(
            isinstance(item, Mapping) for item in payload
        ):
            raise ProgramRetrieverSnapshotError(
                "local_corpus_snapshot JSON corpus must be a list of objects"
            )
        return [dict(item) for item in payload]
    raise ProgramRetrieverSnapshotError(
        "local_corpus_snapshot retriever.path supports only .jsonl or .json corpora"
    )


def _snapshot_documents(
    records: list[dict[str, Any]],
    *,
    id_field: str,
    text_field: str,
) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    total_chars = 0
    for index, record in enumerate(records):
        doc_id = str(record.get(id_field) or "").strip()
        text = str(record.get(text_field) or "")
        if not doc_id:
            raise ProgramRetrieverSnapshotError(
                f"local_corpus_snapshot record {index} missing non-empty id field {id_field!r}"
            )
        if not text.strip():
            raise ProgramRetrieverSnapshotError(
                f"local_corpus_snapshot record {doc_id!r} missing non-empty text field {text_field!r}"
            )
        total_chars += len(text)
        if total_chars > _MAX_LOCAL_CORPUS_TOTAL_CHARS:
            raise ProgramRetrieverSnapshotError(
                "local_corpus_snapshot corpus exceeds total character limit "
                f"{_MAX_LOCAL_CORPUS_TOTAL_CHARS}"
            )
        documents.append({"id": doc_id, "text": text})
    return documents


def resolve_program_retriever_snapshots(
    intent: ProgramIntent,
    *,
    intent_source: Path | None,
) -> tuple[ProgramIntent, dict[str, Any] | None]:
    """Resolve local retriever corpora into deterministic inline snapshots.

    Only ``retriever.mode=local_corpus_snapshot`` is resolved here. The source
    corpus is read once at materialization time, normalized under the same
    bounded inline retriever limits, then embedded into the generated module via
    an ``inline_corpus`` adapter. Generated runtime code does not read the source
    corpus, call a live retriever, bind tools, or access the network.
    """

    topology = dict(intent.topology or {})
    modules = topology.get("modules")
    if not isinstance(modules, list) or not modules:
        return intent, None

    resolved_modules: list[Any] = []
    snapshots: list[dict[str, Any]] = []
    for raw_module in modules:
        module = dict(raw_module) if isinstance(raw_module, Mapping) else raw_module
        if not isinstance(module, dict):
            resolved_modules.append(module)
            continue
        retriever = module.get("retriever")
        if str(module.get("primitive") or "") != "Retriever" or not isinstance(
            retriever, Mapping
        ):
            resolved_modules.append(module)
            continue
        retriever_config = dict(retriever)
        if str(retriever_config.get("mode") or "") != "local_corpus_snapshot":
            resolved_modules.append(module)
            continue
        if intent_source is None:
            raise ProgramRetrieverSnapshotError(
                "local_corpus_snapshot retriever materialization requires intent_source"
            )
        module_id = str(module.get("id") or "")
        source_path = _resolve_local_corpus_path(
            retriever_config.get("path"), intent_source=intent_source
        )
        source_text = _read_bounded_corpus_text(source_path)
        source_hash = sha256_text(source_text)
        id_field = str(retriever_config.get("id_field") or "id").strip()
        text_field = str(retriever_config.get("text_field") or "text").strip()
        if not id_field or not text_field:
            raise ProgramRetrieverSnapshotError(
                "local_corpus_snapshot id_field/text_field must not be blank"
            )
        records = _load_corpus_records(source_path, text=source_text)
        documents = _snapshot_documents(
            records, id_field=id_field, text_field=text_field
        )
        inline_retriever = normalize_inline_retriever_config(
            {
                "mode": "inline_corpus",
                "k": retriever_config.get("k", 3),
                "documents": documents,
            },
            module_id=module_id,
        )
        snapshot_payload = {
            "module_id": module_id,
            "mode": "local_corpus_snapshot",
            "source_path": str(source_path),
            "source_hash": source_hash,
            "id_field": id_field,
            "text_field": text_field,
            "document_count": len(inline_retriever["documents"]),
            "total_text_chars": sum(
                len(document["text"]) for document in inline_retriever["documents"]
            ),
            "k": inline_retriever["k"],
            "runtime_binding": "generated_bounded_snapshot_retriever_adapter",
            "effects": {
                "materialization_filesystem_read": True,
                "runtime_filesystem_read": False,
                "network": False,
                "tool_called": False,
                "provider_called": False,
                "external_authority": False,
            },
            "documents": inline_retriever["documents"],
        }
        snapshots.append(snapshot_payload)
        resolved_module = dict(module)
        resolved_module["retriever"] = inline_retriever
        resolved_modules.append(resolved_module)

    if not snapshots:
        return intent, None

    resolved_topology = {**topology, "modules": resolved_modules}
    resolved_payload = intent.model_dump(mode="json", exclude_none=True)
    resolved_payload["topology"] = resolved_topology
    bundle = {
        "schema_version": PROGRAM_RETRIEVER_SNAPSHOTS_SCHEMA,
        "status": "materialized_to_bounded_inline_adapters",
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "runtime_policy": {
            "generated_runtime_reads_source_corpus": False,
            "live_external_retriever_bound": False,
            "network_allowed": False,
            "tool_binding_allowed": False,
            "provider_call_allowed": False,
        },
        "notes": [
            "local_corpus_snapshot retrievers are read once during materialization and normalized into generated bounded inline retriever adapters.",
            "The generated program embeds the normalized documents and does not read the source corpus, bind a live retriever, call a provider, or access the network at runtime.",
        ],
    }
    return ProgramIntent.model_validate(resolved_payload), bundle


def retriever_snapshot_text(payload: Mapping[str, Any]) -> str:
    return _json_text(dict(payload))
