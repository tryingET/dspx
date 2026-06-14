from __future__ import annotations

from typing import Any, Dict, List, Optional, cast
from collections.abc import Callable
from datetime import datetime, timezone
import json
import logging
import os
import re
import shutil
from tempfile import TemporaryDirectory
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dspx.cache import make_key, sha256_text
from dspx.cli.utils import log_artifacts_to_mlflow, write_receipt_for_output
from dspx.dtos import SignatureGenRequest, ModuleSpec
from dspx.redaction import sanitize_diagnostic_text
from dspx.security import PathEscapeError, confine_path
from dspx.services.signatures_service import run_generate_dto
from dspx.services.module_service import run_generate as module_run_generate
from dspx.services.mermaid_workflow_service import generate_programs
from dspx.server.security import (
    AuthGuard,
    BodySizeLimitConfig,
    BodySizeLimitMiddleware,
    RateLimitConfig,
    RateLimitMiddleware,
    RequestStatsMiddleware,
    UnauthorizedError,
    stats as _stats,
)


class SignatureRequest(BaseModel):
    prompt: str
    template_version: Optional[str] = "simple-v1"
    class_name: Optional[str] = None


class SignatureResponse(BaseModel):
    code: str
    signature_name: Optional[str] = None
    output_path: Optional[str] = None
    receipt_path: Optional[str] = None
    output_hash: Optional[str] = None


class ModuleRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    inputs: List[str] = []
    outputs: List[str] = []
    template_version: Optional[str] = "simple-v1"
    use_signature: bool = False


class ModuleResponse(BaseModel):
    name: str
    code: str
    output_path: Optional[str] = None
    receipt_path: Optional[str] = None
    output_hash: Optional[str] = None


class MermaidRequest(BaseModel):
    mermaid: str
    name: Optional[str] = None
    variants: List[str] = ["predict", "cot", "react"]


class MermaidResponse(BaseModel):
    name: str
    produced: List[str]
    manifest: Optional[Dict[str, Any]] = None
    output_dir: Optional[str] = None
    manifest_path: Optional[str] = None


_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_TRUE_VALUES = {"1", "true", "yes"}
_LOG = logging.getLogger("dspx.server")


def _server_output_root() -> Path:
    raw = os.getenv("DSPX_SERVER_OUTPUT_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / "generated" / "server").resolve()


def _sanitize_stem(value: str | None, *, fallback: str) -> str:
    text = (value or "").strip() or fallback
    text = _IDENTIFIER_RE.sub("-", text).strip(".-")
    return text or fallback


def _timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _artifact_token() -> str:
    return f"{_timestamp_token()}-{uuid4().hex[:12]}"


def _redacted_text_preview(value: object) -> str:
    return sanitize_diagnostic_text(str(value or ""), limit=512)


def _replay_text_ref(name: str, value: object) -> dict[str, Any]:
    text = str(value or "")
    return {
        f"{name}_sha256": sha256_text(text),
        f"{name}_preview_redacted": _redacted_text_preview(text),
        f"{name}_raw_persisted": False,
    }


def _code_output_path(kind: str, stem: str) -> Path:
    root = _server_output_root() / kind
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{_artifact_token()}-{_sanitize_stem(stem, fallback=kind)}.py"


def _directory_output_path(kind: str, stem: str) -> Path:
    root = _server_output_root() / kind
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{_artifact_token()}-{_sanitize_stem(stem, fallback=kind)}"


def _persist_code_artifact(
    *,
    kind: str,
    stem: str,
    code: str,
    run_kind: str,
    template_version: str,
    cache_key: str,
    replay_inputs: dict[str, Any],
    extra: Optional[dict[str, Any]] = None,
    class_name: Optional[str] = None,
    run_summary: Optional[dict[str, Any]] = None,
) -> tuple[Path, Path, str]:
    output_path = _code_output_path(kind, stem)
    output_path.write_text(code, encoding="utf-8")
    write_receipt_for_output(
        output_path,
        code,
        run_kind,
        template_version,
        cache_key,
        replay_inputs,
        extra=extra,
        class_name=class_name,
        run_summary=run_summary,
    )
    receipt_path = output_path.parent / f"{output_path.name}.meta.json"
    output_hash = sha256_text(code)
    log_artifacts_to_mlflow(
        output_path,
        run_kind,
        template_version,
        cache_key,
        output_hash,
    )
    return output_path, receipt_path, output_hash


def _module_receipt_extra(metadata: dict[str, Any]) -> dict[str, Any]:
    synthesis_extra: dict[str, Any] = {}
    synthesis = metadata.get("synthesis")
    if not isinstance(synthesis, dict):
        return synthesis_extra

    synthesis_extra["synthesis"] = synthesis
    request = synthesis.get("request")
    if isinstance(request, dict) and request.get("request_id"):
        synthesis_extra["synthesis_request_id"] = request["request_id"]
    diagnostics = metadata.get("synthesis_diagnostics")
    if isinstance(diagnostics, dict):
        synthesis_extra["synthesis_diagnostics"] = diagnostics
    candidates = synthesis.get("candidates")
    if isinstance(candidates, list):
        synthesis_extra["synthesis_candidate_ids"] = [
            item.get("candidate_id")
            for item in candidates
            if isinstance(item, dict) and item.get("candidate_id")
        ]
    evaluations = synthesis.get("evaluations")
    if isinstance(evaluations, list):
        synthesis_extra["synthesis_evaluation_ids"] = [
            item.get("evaluation_id")
            for item in evaluations
            if isinstance(item, dict) and item.get("evaluation_id")
        ]
    if isinstance(synthesis.get("promotion_shell"), dict):
        synthesis_extra["synthesis_promotion_shell"] = synthesis["promotion_shell"]
    if isinstance(synthesis.get("promotion_decision"), dict):
        synthesis_extra["synthesis_promotion_decision"] = synthesis[
            "promotion_decision"
        ]
        ranked = (
            synthesis["promotion_decision"].get("metadata", {})
            if isinstance(synthesis["promotion_decision"].get("metadata"), dict)
            else {}
        )
        if isinstance(ranked.get("ranked_candidates"), list):
            synthesis_extra["synthesis_ranked_candidates"] = ranked["ranked_candidates"]
    if isinstance(synthesis.get("selection_policy"), dict):
        synthesis_extra["synthesis_selection_policy"] = synthesis["selection_policy"]
    return synthesis_extra


def _persist_generated_directory(
    *, kind: str, stem: str, source_dir: Path
) -> tuple[Path, Optional[dict[str, Any]], Optional[Path]]:
    output_dir = _directory_output_path(kind, stem)
    shutil.copytree(source_dir, output_dir)
    manifest_path = output_dir / "manifest.json"
    manifest = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = None
    return output_dir, manifest, (manifest_path if manifest_path.exists() else None)


def _to_public_artifact_ref(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        resolved = path.resolve()
        root = _server_output_root().resolve()
        return resolved.relative_to(root).as_posix()
    except Exception:
        return path.name


def _invalid_request_response(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": "invalid_request",
            "detail": detail,
            "status": 400,
        },
    )


def _artifact_persistence_failed_response(kind: str, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "artifact_persistence_failed",
            "detail": f"failed to persist {kind} artifacts: {exc}",
            "status": 500,
        },
    )


def _require_mutation_confirmation(
    x_dspx_confirm: Optional[str],
) -> Optional[JSONResponse]:
    if (
        str(os.getenv("DSPX_CONFIRM_MUTATIONS", "0")).strip().lower()
        not in _TRUE_VALUES
    ):
        return None
    if str(x_dspx_confirm or "").strip().lower() in _TRUE_VALUES:
        return None
    return JSONResponse(
        status_code=403,
        content={
            "error": "confirmation_required",
            "detail": "Mutation requires confirmation header X-DSPX-Confirm: 1",
            "status": 403,
        },
    )


def _try_persist_code_artifact(
    *,
    kind: str,
    stem: str,
    code: str,
    run_kind: str,
    template_version: str,
    cache_key: str,
    replay_inputs: dict[str, Any],
    extra: Optional[dict[str, Any]] = None,
    class_name: Optional[str] = None,
    run_summary: Optional[dict[str, Any]] = None,
) -> tuple[Optional[Path], Optional[Path], str]:
    output_hash = sha256_text(code)
    try:
        return _persist_code_artifact(
            kind=kind,
            stem=stem,
            code=code,
            run_kind=run_kind,
            template_version=template_version,
            cache_key=cache_key,
            replay_inputs=replay_inputs,
            extra=extra,
            class_name=class_name,
            run_summary=run_summary,
        )
    except Exception:
        _LOG.exception("failed to persist %s artifact", kind)
        return None, None, output_hash


def create_app() -> FastAPI:
    _stats.reset()
    app = FastAPI(title="DSPx Server", version="0.1.0")
    guard = AuthGuard.from_env()
    # Install middleware unconditionally so request/response metrics stay truthful
    # even when rate limiting itself is disabled.
    rl_cfg = RateLimitConfig.from_env(valid_tokens=guard.config.tokens)
    app.add_middleware(cast(Any, RateLimitMiddleware), config=rl_cfg)
    body_cfg = BodySizeLimitConfig.from_env()
    app.add_middleware(cast(Any, BodySizeLimitMiddleware), config=body_cfg)
    app.add_middleware(cast(Any, RequestStatsMiddleware))

    @app.exception_handler(UnauthorizedError)
    async def _unauth_handler(request: Request, exc: UnauthorizedError):
        return JSONResponse(
            status_code=401,
            content={
                "error": "unauthorized",
                "detail": str(exc) or "unauthorized",
                "status": 401,
            },
        )

    @app.post("/signature", response_model=SignatureResponse)
    def post_signature(
        req: SignatureRequest,
        authorization: Optional[str] = Header(default=None),
        x_dspx_confirm: Optional[str] = Header(default=None),
    ):
        guard.check(authorization)
        confirmation = _require_mutation_confirmation(x_dspx_confirm)
        if confirmation is not None:
            return confirmation
        os.environ.setdefault("MLFLOW_ENABLE", "0")
        template_version = req.template_version or "simple-v1"
        options = {"class_name": req.class_name} if req.class_name else {}
        dto = SignatureGenRequest(
            prompt=req.prompt, template_version=template_version, options=options
        )
        res = run_generate_dto(dto)

        class_name = req.class_name or res.signature_name or "GeneratedSignature"
        cache_key = make_key(
            {
                "kind": "signature",
                "prompt": req.prompt,
                "template_version": template_version,
                "class_name": class_name,
                "options": options,
            }
        )
        output_path, receipt_path, output_hash = _try_persist_code_artifact(
            kind="signature",
            stem=class_name,
            code=res.code,
            run_kind="signature-gen",
            template_version=template_version,
            cache_key=cache_key,
            replay_inputs={
                **_replay_text_ref("prompt", req.prompt),
                "template_version": template_version,
                "class_name": req.class_name,
                "options": options,
            },
            extra={
                "signature_name": res.signature_name or "",
                "task_description_preview_redacted": _redacted_text_preview(
                    res.task_description or req.prompt
                ),
            },
            class_name=class_name,
            run_summary=(res.metadata if isinstance(res.metadata, dict) else None),
        )
        return SignatureResponse(
            code=res.code,
            signature_name=res.signature_name,
            output_path=_to_public_artifact_ref(output_path),
            receipt_path=_to_public_artifact_ref(receipt_path),
            output_hash=output_hash,
        )

    @app.post("/module", response_model=ModuleResponse)
    def post_module(
        req: ModuleRequest,
        authorization: Optional[str] = Header(default=None),
        x_dspx_confirm: Optional[str] = Header(default=None),
    ):
        guard.check(authorization)
        confirmation = _require_mutation_confirmation(x_dspx_confirm)
        if confirmation is not None:
            return confirmation
        os.environ.setdefault("MLFLOW_ENABLE", "0")
        template_version = req.template_version or "simple-v1"
        spec = ModuleSpec(
            name=req.name,
            description=req.description or "",
            inputs=list(req.inputs or []),
            outputs=list(req.outputs or []),
            options={"template_version": template_version},
        )
        try:
            art = module_run_generate(spec, use_signature=bool(req.use_signature))
        except ValueError as exc:
            return _invalid_request_response(str(exc))

        cache_key = make_key(
            {
                "kind": "module",
                "name": req.name,
                "description": req.description or "",
                "inputs": list(req.inputs or []),
                "outputs": list(req.outputs or []),
                "use_signature": bool(req.use_signature),
                "template_version": template_version,
            }
        )
        output_path, receipt_path, output_hash = _try_persist_code_artifact(
            kind="module",
            stem=art.name,
            code=art.code,
            run_kind="module-gen",
            template_version=template_version,
            cache_key=cache_key,
            replay_inputs={
                "name": req.name,
                "description": req.description or "",
                "inputs": list(req.inputs or []),
                "outputs": list(req.outputs or []),
                "use_signature": bool(req.use_signature),
                "template_version": template_version,
            },
            extra=_module_receipt_extra(art.metadata),
            run_summary=(
                art.metadata.get("run_summary")
                if isinstance(art.metadata.get("run_summary"), dict)
                else None
            ),
        )
        return ModuleResponse(
            name=art.name,
            code=art.code,
            output_path=_to_public_artifact_ref(output_path),
            receipt_path=_to_public_artifact_ref(receipt_path),
            output_hash=output_hash,
        )

    @app.post("/mermaid", response_model=MermaidResponse)
    def post_mermaid(
        req: MermaidRequest,
        authorization: Optional[str] = Header(default=None),
        x_dspx_confirm: Optional[str] = Header(default=None),
    ):
        guard.check(authorization)
        confirmation = _require_mutation_confirmation(x_dspx_confirm)
        if confirmation is not None:
            return confirmation
        os.environ.setdefault("MLFLOW_ENABLE", "0")
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            try:
                out = generate_programs(
                    req.mermaid,
                    name=req.name,
                    out_dir=td,
                    variants=list(req.variants or []),
                )
            except ValueError as exc:
                return _invalid_request_response(str(exc))
            name = req.name or "workflow"
            try:
                output_dir, manifest, manifest_path = _persist_generated_directory(
                    kind="mermaid",
                    stem=name,
                    source_dir=temp_root,
                )
            except Exception as exc:
                _LOG.exception("failed to persist mermaid artifacts")
                return _artifact_persistence_failed_response("mermaid", exc)
            produced: list[str] = []
            for raw_path in out:
                source_path = Path(raw_path)
                try:
                    if source_path.is_absolute():
                        source_path = confine_path(temp_root, source_path)
                    else:
                        source_path = confine_path(temp_root, source_path)
                    relative_path = source_path.relative_to(temp_root.resolve())
                except PathEscapeError as exc:
                    _LOG.exception("mermaid service produced escaped artifact path")
                    return _artifact_persistence_failed_response("mermaid", exc)
                produced_path = output_dir / relative_path
                produced.append(
                    _to_public_artifact_ref(produced_path) or produced_path.name
                )
            return MermaidResponse(
                name=name,
                produced=produced,
                manifest=manifest,
                output_dir=_to_public_artifact_ref(output_dir),
                manifest_path=_to_public_artifact_ref(manifest_path),
            )

    # Optional /metrics endpoint (guarded by env DSPX_METRICS_ENABLED)
    if str(os.getenv("DSPX_METRICS_ENABLED", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
    }:

        @app.get("/metrics")
        def get_metrics(
            request: Request,
            authorization: Optional[str] = Header(default=None),
        ):
            guard.check(authorization)
            # Content negotiation: Prometheus text when requested
            fmt = request.query_params.get("format")
            accept = (request.headers.get("accept") or "").lower()
            if fmt == "prom" or "text/plain" in accept:
                c = _stats.snapshot()
                lines = [
                    "# HELP dspx_requests_total Total HTTP requests.",
                    "# TYPE dspx_requests_total counter",
                    f"dspx_requests_total {c.get('requests_total', 0)}",
                    "# HELP dspx_status_401_total Unauthorized responses.",
                    "# TYPE dspx_status_401_total counter",
                    f"dspx_status_401_total {c.get('status_401', 0)}",
                    "# HELP dspx_status_429_total Rate-limited responses.",
                    "# TYPE dspx_status_429_total counter",
                    f"dspx_status_429_total {c.get('status_429', 0)}",
                    "# HELP dspx_status_413_total Body-size rejection responses.",
                    "# TYPE dspx_status_413_total counter",
                    f"dspx_status_413_total {c.get('status_413', 0)}",
                ]
                from fastapi import Response

                return Response(
                    "\n".join(lines) + "\n",
                    media_type="text/plain; version=0.0.4; charset=utf-8",
                )
            c = _stats.snapshot()
            return {"status": "ok", **c}

        @app.get("/metrics-prom")
        def get_metrics_prom(authorization: Optional[str] = Header(default=None)):
            guard.check(authorization)
            c = _stats.snapshot()
            lines = [
                "# HELP dspx_requests_total Total HTTP requests.",
                "# TYPE dspx_requests_total counter",
                f"dspx_requests_total {c.get('requests_total', 0)}",
                "# HELP dspx_status_401_total Unauthorized responses.",
                "# TYPE dspx_status_401_total counter",
                f"dspx_status_401_total {c.get('status_401', 0)}",
                "# HELP dspx_status_429_total Rate-limited responses.",
                "# TYPE dspx_status_429_total counter",
                f"dspx_status_429_total {c.get('status_429', 0)}",
                "# HELP dspx_status_413_total Body-size rejection responses.",
                "# TYPE dspx_status_413_total counter",
                f"dspx_status_413_total {c.get('status_413', 0)}",
            ]
            from fastapi import Response

            return Response(
                "\n".join(lines) + "\n",
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

    return app


class _LazyASGIApp:
    def __init__(self, factory: Callable[[], FastAPI]) -> None:
        self._factory = factory
        self._app: FastAPI | None = None
        self._lock = Lock()

    def _get_app(self) -> FastAPI:
        app = self._app
        if app is not None:
            return app
        with self._lock:
            if self._app is None:
                self._app = self._factory()
            return self._app

    async def __call__(self, scope, receive, send) -> None:
        await self._get_app()(scope, receive, send)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_app(), name)


def main() -> None:
    """Start the ASGI server using Granian.

    Environment variables:
    - DSPX_SERVER_HOST (default localhost)
    - DSPX_SERVER_PORT (default 33213)
    """
    host = os.getenv("DSPX_SERVER_HOST", "localhost")
    os.environ.setdefault("DSPX_SERVER_HOST", host)
    port = int(os.getenv("DSPX_SERVER_PORT", "33213"))
    try:
        from granian import Granian
        from granian.constants import Interfaces

        # Use module:var target to avoid re-creating app per worker
        target = "dspx.server.app:app"
        server = Granian(target, address=host, port=port, interface=Interfaces.ASGI)
        server.serve()
    except Exception as e:  # pragma: no cover - granian may be missing in some envs
        raise SystemExit(
            f"Granian is required to run the server. Install with `pip install granian` and run:\n"
            f"  granian --interface asgi --host {host} --port {port} dspx.server.app:app\n"
            f"Error: {e}"
        )


if __name__ == "__main__":
    main()

# Global lazy ASGI app for Granian target convenience; defer env-sensitive
# configuration loading until first use so import order does not freeze runtime
# auth/rate-limit settings.
app = _LazyASGIApp(create_app)
