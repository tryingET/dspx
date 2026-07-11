# summary: "Global pytest setup that isolates providers and MLflow while caching deterministic generated-program validation."
# read_when:
#   - "Changing suite-wide test isolation, generated-program caching, or module-evidence defaults."

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Generator, Mapping
from pathlib import Path
from typing import Any

import pytest

from program_generation_cache import (
    ProgramGenerationValidationCache,
    callable_fingerprint,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    _REPO_ROOT / "packages" / "dspx-core" / "src",
    _REPO_ROOT / "apps" / "forge" / "src",
):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)


def _default_mlflow_tracking_uri() -> str:
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    safe_worker = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_" for char in worker
    )
    db_path = (
        Path(tempfile.gettempdir())
        / f"dspx_mlflow_tests_{safe_worker}_{os.getpid()}.db"
    )
    return f"sqlite:///{db_path}"


@pytest.fixture(scope="session", autouse=True)
def _deduplicate_program_generation_validation(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None]:
    from dspx.services import module_service, program_service
    from dspx.synthesis import runtime as synthesis_runtime

    base_temp = tmp_path_factory.getbasetemp()
    session_root = (
        base_temp.parent if os.environ.get("PYTEST_XDIST_WORKER") else base_temp
    )
    cache = ProgramGenerationValidationCache(
        session_root / "program-generation-validation-cache"
    )
    original_harness = program_service._run_python_harness
    original_smoke = synthesis_runtime.smoke_module_code
    original_evidence_retriever = module_service.retrieve_module_synthesis_evidence

    def cached_harness(root: Path, filename: str, *, label: str) -> dict[str, Any]:
        execution_token = "|".join(
            (
                callable_fingerprint(original_harness),
                callable_fingerprint(program_service.subprocess.run),
            )
        )
        return cache.run_harness(
            root,
            filename,
            label=label,
            execute=lambda current_root, current_filename: original_harness(
                current_root,
                current_filename,
                label=label,
            ),
            execution_token=execution_token,
        )

    def cached_smoke(
        code: str,
        *,
        payload: Mapping[str, Any],
        timeout: int | None = None,
    ) -> tuple[bool, dict[str, bool], list[str]]:
        return cache.run_module_smoke(
            code,
            payload=payload,
            timeout=timeout,
            execute=lambda current_code, current_payload, current_timeout: (
                original_smoke(
                    current_code,
                    payload=current_payload,
                    timeout=current_timeout,
                )
            ),
            execution_token=callable_fingerprint(original_smoke),
        )

    def isolated_evidence_retriever(
        spec: Any,
        *,
        use_signature: bool = False,
        receipts_path: Path | None = None,
        oracle_index_path: Path | None = None,
        oracle_top_k: int = 5,
    ) -> Any:
        if receipts_path is None:
            evidence_root = Path(os.environ["DSPX_TEST_MODULE_SYNTHESIS_EVIDENCE_ROOT"])
            receipts_path = evidence_root / "receipts"
            oracle_index_path = evidence_root / "oracle" / "coordinates.db"
        return original_evidence_retriever(
            spec,
            use_signature=use_signature,
            receipts_path=receipts_path,
            oracle_index_path=oracle_index_path,
            oracle_top_k=oracle_top_k,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(program_service, "_run_python_harness", cached_harness)
    monkeypatch.setattr(synthesis_runtime, "smoke_module_code", cached_smoke)
    monkeypatch.setattr(
        module_service,
        "retrieve_module_synthesis_evidence",
        isolated_evidence_retriever,
    )
    try:
        yield
    finally:
        monkeypatch.undo()


@pytest.fixture(autouse=True)
def _default_provider_stub(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    # Avoid accidental MLflow HTTP calls from third-party libraries (e.g., DSPy)
    # when a user has an HTTP tracking URI in a local config.
    monkeypatch.setenv("MLFLOW_TRACKING_URI", _default_mlflow_tracking_uri())
    # Program-generation tests must not ingest machine-local generated receipts
    # or Oracle state. Dedicated evidence tests pass explicit temporary roots.
    evidence_root = tmp_path / "module-synthesis-evidence"
    monkeypatch.setenv(
        "DSPX_TEST_MODULE_SYNTHESIS_EVIDENCE_ROOT",
        str(evidence_root),
    )
