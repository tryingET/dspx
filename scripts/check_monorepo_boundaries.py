from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    import_name: str
    reason: str


_SKIP_PARTS = {".git", ".venv", "__pycache__", "generated", "submodules", "dist"}


def _iter_python_files(root: Path, base: Path) -> list[Path]:
    target = root / base
    if not target.exists():
        return []
    files: list[Path] = []
    for path in target.rglob("*.py"):
        rel = path.relative_to(root)
        if any(part in _SKIP_PARTS for part in rel.parts):
            continue
        files.append(path)
    return files


def _iter_imports(tree: ast.AST) -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                items.append((int(node.lineno), alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                items.append((int(node.lineno), node.module))
            else:
                for alias in node.names:
                    items.append((int(node.lineno), alias.name))
    return items


def _is_forge_import(name: str) -> bool:
    return (
        name == "dspx.forge"
        or name.startswith("dspx.forge.")
        or name == "forge"
        or name.startswith("forge.")
    )


def _check_src_core_no_forge(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_python_files(root, Path("src/dspx")):
        rel = path.relative_to(root)
        if rel.parts[:3] == ("src", "dspx", "forge"):
            continue
        if rel.parts[:3] == ("src", "dspx", "cli"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError:
            continue
        for lineno, name in _iter_imports(tree):
            if _is_forge_import(name):
                violations.append(
                    Violation(
                        path=rel,
                        lineno=lineno,
                        import_name=name,
                        reason="core module imports forge app module",
                    )
                )
    return violations


def _check_packages_core_no_apps(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_python_files(root, Path("packages/dspx-core")):
        rel = path.relative_to(root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError:
            continue
        for lineno, name in _iter_imports(tree):
            if name == "apps" or name.startswith("apps."):
                violations.append(
                    Violation(
                        path=rel,
                        lineno=lineno,
                        import_name=name,
                        reason="dspx-core must not import apps",
                    )
                )
            elif name == "dspx.forge" or name.startswith("dspx.forge."):
                violations.append(
                    Violation(
                        path=rel,
                        lineno=lineno,
                        import_name=name,
                        reason="dspx-core must not import forge app internals",
                    )
                )
    return violations


def _check_apps_no_cross_app_imports(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    apps_root = root / "apps"
    if not apps_root.exists():
        return violations

    for path in _iter_python_files(root, Path("apps")):
        rel = path.relative_to(root)
        parts = rel.parts
        if len(parts) < 2:
            continue
        app_name = parts[1]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError:
            continue
        for lineno, name in _iter_imports(tree):
            if not name.startswith("apps."):
                continue
            imported_app = name.split(".", 2)[1] if "." in name else ""
            if imported_app and imported_app != app_name:
                violations.append(
                    Violation(
                        path=rel,
                        lineno=lineno,
                        import_name=name,
                        reason="apps must not import other app internals",
                    )
                )
    return violations


def collect_violations(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    violations.extend(_check_src_core_no_forge(root))
    violations.extend(_check_packages_core_no_apps(root))
    violations.extend(_check_apps_no_cross_app_imports(root))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check monorepo dependency direction guardrails"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root (default: current directory)",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    violations = collect_violations(root)
    if not violations:
        print("ok: monorepo boundary checks passed")
        return 0

    for item in violations:
        print(
            f"{item.path}:{item.lineno}: forbidden import '{item.import_name}' ({item.reason})"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
