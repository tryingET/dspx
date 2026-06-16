from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES


def _iter_path_values(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if (
                (key_text == "path" or key_text.endswith("_path"))
                and isinstance(item, str)
                and item.strip()
            ):
                yield item
            else:
                yield from _iter_path_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_path_values(item)


def protected_paths_from_payload(payload: Mapping[str, Any]) -> set[Path]:
    """Return resolved input/control paths declared by a sidecar payload."""

    paths: set[Path] = set()
    for raw_path in _iter_path_values(payload):
        try:
            paths.add(Path(raw_path).expanduser().resolve())
        except (OSError, RuntimeError, ValueError):
            continue
    return paths


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def protected_artifact_roots_from_payload(payload: Mapping[str, Any]) -> set[Path]:
    """Return generated-artifact roots implied by manifest paths in a payload."""

    roots: set[Path] = set()
    for path in protected_paths_from_payload(payload):
        if path.name == "manifest.json":
            roots.add(path.parent)
    return roots


def prepare_sidecar_output_path(
    out_path: Path,
    *,
    payload: Mapping[str, Any],
    artifact_label: str,
    protected_names: Iterable[str] = PROTECTED_PROGRAM_ARTIFACT_NAMES,
    extra_protected_paths: Iterable[Path] = (),
    extra_protected_roots: Iterable[Path] = (),
    protect_payload_artifact_roots: bool = False,
    allowed_names_in_protected_roots: Iterable[str] = (),
) -> Path:
    """Resolve and validate a local sidecar output path before writing.

    Sidecars summarize or adjudicate generated artifacts. They must not overwrite
    producer/control artifacts, any input path recorded in their own payload, or
    arbitrary files inside protected generated-artifact roots. Callers can opt in
    to deriving protected roots from manifest paths declared in the payload while
    preserving explicit canonical exceptions such as ``program_candidate_state.json``.
    """

    resolved = out_path.expanduser().resolve()
    protected_name_set = {str(name) for name in protected_names}
    if resolved.name in protected_name_set:
        raise ValueError(f"{artifact_label} must not overwrite {resolved.name}")

    protected_paths = protected_paths_from_payload(payload)
    protected_paths.update(
        path.expanduser().resolve() for path in extra_protected_paths
    )
    if resolved in protected_paths:
        raise ValueError(
            f"{artifact_label} output must not overwrite an input artifact: {resolved}"
        )

    protected_roots = {root.expanduser().resolve() for root in extra_protected_roots}
    if protect_payload_artifact_roots:
        protected_roots.update(protected_artifact_roots_from_payload(payload))
    allowed_root_names = {str(name) for name in allowed_names_in_protected_roots}
    for protected_root in protected_roots:
        if resolved == protected_root or _is_relative_to(resolved, protected_root):
            if resolved.name in allowed_root_names:
                continue
            raise ValueError(
                f"{artifact_label} output must not be written inside a protected artifact root: {protected_root}"
            )

    return resolved
