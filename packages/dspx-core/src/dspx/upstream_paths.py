from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root(start: Path | None = None) -> Path | None:
    cur = (start or Path(__file__).resolve()).parent
    for _ in range(10):
        if (cur / ".git").exists() or (cur / "pyproject.toml").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def vibe_src_candidates() -> list[Path]:
    candidates: list[Path] = []

    env_src = (os.getenv("DSPX_VIBE_DSPY_SRC") or "").strip()
    if env_src:
        candidates.append(Path(env_src).expanduser())

    env_upstream = (os.getenv("DSPX_UPSTREAM_DIR") or "").strip()
    if env_upstream:
        candidates.append(Path(env_upstream).expanduser() / "vibe-dspy" / "src")

    candidates.append(Path("~/programming/upstream/vibe-dspy/src").expanduser())

    root = _repo_root(Path(__file__).resolve())
    if root is not None:
        candidates.append(root / "submodules" / "vibe-dspy" / "src")

    uniq: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def ensure_vibe_on_path() -> Path | None:
    try:
        import signature_generator  # type: ignore  # noqa: F401

        return None
    except Exception:
        pass

    for candidate in vibe_src_candidates():
        if not candidate.is_dir():
            continue
        c = str(candidate)
        if c not in sys.path:
            sys.path.insert(0, c)
        try:
            import signature_generator  # type: ignore  # noqa: F401

            return candidate
        except Exception:
            continue
    return None


def require_vibe_on_path() -> Path | None:
    found = ensure_vibe_on_path()
    try:
        import signature_generator  # type: ignore  # noqa: F401

        return found
    except Exception as exc:  # pragma: no cover - exercised by CLIs/services directly
        looked_in = "\n".join(f"- {p}" for p in vibe_src_candidates())
        raise RuntimeError(
            "Could not import vibe-dspy SignatureGenerator (module `signature_generator`).\n"
            "Set DSPX_VIBE_DSPY_SRC=/absolute/path/to/vibe-dspy/src,\n"
            "or clone to ~/programming/upstream/vibe-dspy.\n"
            f"Candidates checked:\n{looked_in}"
        ) from exc
