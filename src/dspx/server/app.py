from __future__ import annotations

from typing import Any, Dict, List, Optional
import os
from tempfile import TemporaryDirectory
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dspx.dtos import SignatureGenRequest, ModuleSpec
from dspx.services.signatures_service import run_generate_dto
from dspx.services.module_service import run_generate as module_run_generate
from dspx.services.mermaid_workflow_service import generate_programs
from dspx.server.security import (
    AuthGuard,
    RateLimitConfig,
    RateLimitMiddleware,
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


class MermaidRequest(BaseModel):
    mermaid: str
    name: Optional[str] = None
    variants: List[str] = ["predict", "cot", "react"]


class MermaidResponse(BaseModel):
    name: str
    produced: List[str]
    manifest: Optional[Dict[str, Any]] = None


def create_app() -> FastAPI:
    app = FastAPI(title="DSPx Server", version="0.1.0")
    guard = AuthGuard.from_env()
    # Rate limiting
    rl_cfg = RateLimitConfig.from_env()
    if rl_cfg.enabled:
        app.add_middleware(RateLimitMiddleware, config=rl_cfg)

    @app.exception_handler(UnauthorizedError)
    async def _unauth_handler(request: Request, exc: UnauthorizedError):  # type: ignore[no-untyped-def]
        _stats.status_401 += 1
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
        req: SignatureRequest, authorization: Optional[str] = Header(default=None)
    ):
        _stats.requests_total += 1
        guard.check(authorization)
        os.environ.setdefault("MLFLOW_ENABLE", "0")
        options = {"class_name": req.class_name} if req.class_name else {}
        dto = SignatureGenRequest(
            prompt=req.prompt, template_version=req.template_version, options=options
        )
        res = run_generate_dto(dto)
        return SignatureResponse(code=res.code, signature_name=res.signature_name)

    @app.post("/module", response_model=ModuleResponse)
    def post_module(
        req: ModuleRequest, authorization: Optional[str] = Header(default=None)
    ):
        _stats.requests_total += 1
        guard.check(authorization)
        os.environ.setdefault("MLFLOW_ENABLE", "0")
        spec = ModuleSpec(
            name=req.name,
            description=req.description or "",
            inputs=list(req.inputs or []),
            outputs=list(req.outputs or []),
            options={"template_version": req.template_version or "simple-v1"},
        )
        art = module_run_generate(spec, use_signature=bool(req.use_signature))
        return ModuleResponse(name=art.name, code=art.code)

    @app.post("/mermaid", response_model=MermaidResponse)
    def post_mermaid(
        req: MermaidRequest, authorization: Optional[str] = Header(default=None)
    ):
        _stats.requests_total += 1
        guard.check(authorization)
        os.environ.setdefault("MLFLOW_ENABLE", "0")
        with TemporaryDirectory() as td:
            out = generate_programs(
                req.mermaid,
                name=req.name,
                out_dir=td,
                variants=list(req.variants or []),
            )
            # Load manifest.json if present
            name = req.name or "workflow"
            out_root = Path(td)
            manifest_path = out_root / "manifest.json"
            manifest = None
            if manifest_path.exists():
                try:
                    import json as _json

                    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    manifest = None
            # Convert produced to basenames for response
            produced = [Path(p).name for p in out]
            return MermaidResponse(name=name, produced=produced, manifest=manifest)

    return app


def main() -> None:
    """Start the ASGI server using Granian.

    Environment variables:
    - DSPX_SERVER_HOST (default 127.0.0.1)
    - DSPX_SERVER_PORT (default 8000)
    """
    host = os.getenv("DSPX_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("DSPX_SERVER_PORT", "8000"))
    try:
        from granian import Granian

        # Use module:var target to avoid re-creating app per worker
        target = "dspx.server.app:app"
        server = Granian(target, address=host, port=port, interface="asgi")
        server.serve()
    except Exception as e:  # pragma: no cover - granian may be missing in some envs
        raise SystemExit(
            f"Granian is required to run the server. Install with `pip install granian` and run:\n"
            f"  granian --interface asgi --host {host} --port {port} dspx.server.app:app\n"
            f"Error: {e}"
        )


if __name__ == "__main__":
    main()

# Global app for Granian target convenience
app = create_app()
