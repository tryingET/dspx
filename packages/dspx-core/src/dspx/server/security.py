from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set, Dict, List, Tuple
import hmac
import os
import time
import logging
import ipaddress

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class UnauthorizedError(Exception):
    """Raised when authorization is required and invalid/missing.

    Handled centrally by the server to emit a standardized JSON error.
    """

    pass


def _parse_bool_env(val: Optional[str], default: bool) -> bool:
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in {"1", "true", "yes"}:
        return True
    if s in {"0", "false", "no"}:
        return False
    return default


def _load_tokens_from_file(path: str) -> Set[str]:
    tokens: Set[str] = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                tok = line.strip()
                if tok:
                    tokens.add(tok)
    except Exception:
        # File missing or unreadable; ignore to keep server bootable in tests
        return set()
    return tokens


@dataclass(frozen=True)
class AuthConfig:
    tokens: Set[str]
    required: bool

    @staticmethod
    def from_env(env: Optional[dict[str, str]] = None) -> "AuthConfig":
        e = os.environ if env is None else env
        tokens: Set[str] = set()
        t1 = e.get("DSPX_SERVER_TOKEN")
        if t1 and t1.strip():
            tokens.add(t1.strip())
        tlist = e.get("DSPX_SERVER_TOKENS")
        if tlist:
            for part in tlist.split(","):
                tok = part.strip()
                if tok:
                    tokens.add(tok)
        tf = e.get("DSPX_SERVER_TOKEN_FILE")
        if tf and tf.strip():
            tokens.update(_load_tokens_from_file(tf.strip()))
        # If tokens provided, default to required unless explicitly disabled
        default_required = True if tokens else False
        required = _parse_bool_env(e.get("DSPX_AUTH_REQUIRED"), default_required)
        return AuthConfig(tokens=tokens, required=required)


class AuthGuard:
    def __init__(self, config: AuthConfig) -> None:
        self.config = config

    @staticmethod
    def from_env() -> "AuthGuard":
        return AuthGuard(AuthConfig.from_env())

    @staticmethod
    def _const_time_eq(a: str, b: str) -> bool:
        # hmac.compare_digest avoids timing leaks
        return hmac.compare_digest(a, b)

    def _extract_bearer(self, authorization_header: Optional[str]) -> Optional[str]:
        if not authorization_header or not authorization_header.startswith("Bearer "):
            return None
        return authorization_header.split(" ", 1)[1]

    def check(self, authorization_header: Optional[str]) -> None:
        cfg = self.config
        if not cfg.required:
            return
        provided = self._extract_bearer(authorization_header)
        if not provided:
            raise UnauthorizedError("missing bearer token")
        # Accept any one of the configured tokens
        for tok in cfg.tokens:
            if self._const_time_eq(provided, tok):
                return
        raise UnauthorizedError("invalid token")


# ---- Rate limiting ----


@dataclass(frozen=True)
class Rate:
    capacity: int
    period_seconds: float


def _parse_rate_token(tok: str) -> Rate:
    tok = tok.strip().lower()
    if not tok:
        raise ValueError("empty rate token")
    if "/" not in tok:
        raise ValueError("rate token must be like '10/sec' or '60/min'")
    n_str, per = tok.split("/", 1)
    n = int(float(n_str.strip()))
    per = per.strip()
    if per in {"s", "sec", "second", "seconds"}:
        return Rate(n, 1.0)
    if per in {"m", "min", "minute", "minutes"}:
        return Rate(n, 60.0)
    if per in {"h", "hr", "hour", "hours"}:
        return Rate(n, 3600.0)
    raise ValueError(f"unknown period '{per}' in rate token '{tok}'")


def parse_rate_spec(spec: str) -> List[Rate]:
    return [_parse_rate_token(s) for s in spec.split(",") if s.strip()]


@dataclass(frozen=True)
class RateLimitConfig:
    enabled: bool
    default: List[Rate]
    per_path: Dict[str, List[Rate]]
    identity: str  # 'token' or 'ip'
    trusted_proxies: List[ipaddress._BaseNetwork]
    global_default: List[Rate]
    global_per_path: Dict[str, List[Rate]]

    @staticmethod
    def from_env(env: Optional[dict[str, str]] = None) -> "RateLimitConfig":
        e = os.environ if env is None else env
        enabled = _parse_bool_env(e.get("DSPX_RATE_LIMIT_ENABLED"), False)
        default_spec = e.get("DSPX_RATE_LIMIT_DEFAULT", "")
        default = parse_rate_spec(default_spec) if default_spec else []
        per_path: Dict[str, List[Rate]] = {}
        import json as _json

        paths_raw = e.get("DSPX_RATE_LIMIT_PATHS")
        if paths_raw:
            try:
                mapping = _json.loads(paths_raw)
                for k, v in mapping.items():
                    if isinstance(v, str):
                        per_path[str(k)] = parse_rate_spec(v)
            except Exception:
                pass
        identity = (e.get("DSPX_RATE_LIMIT_IDENTITY") or "token").strip().lower()
        # Trusted proxies as CIDR list (comma-separated)
        trusted_proxies: List[ipaddress._BaseNetwork] = []
        tp_raw = (e.get("DSPX_TRUSTED_PROXIES") or "").strip()
        if tp_raw:
            for p in tp_raw.split(","):
                p = p.strip()
                if not p:
                    continue
                try:
                    trusted_proxies.append(ipaddress.ip_network(p, strict=False))
                except Exception:
                    continue
        # Global caps (identity-agnostic)
        global_default: List[Rate] = []
        gspec = (e.get("DSPX_RATE_LIMIT_GLOBAL") or "").strip()
        if gspec:
            try:
                global_default = parse_rate_spec(gspec)
            except Exception:
                global_default = []
        global_per_path: Dict[str, List[Rate]] = {}
        gpaths = (e.get("DSPX_RATE_LIMIT_GLOBAL_PATHS") or "").strip()
        if gpaths:
            try:
                mapping = _json.loads(gpaths)
                for k, v in mapping.items():
                    if isinstance(v, str):
                        global_per_path[str(k)] = parse_rate_spec(v)
            except Exception:
                pass
        return RateLimitConfig(
            enabled=enabled,
            default=default,
            per_path=per_path,
            identity=identity if identity in {"token", "ip"} else "token",
            trusted_proxies=trusted_proxies,
            global_default=global_default,
            global_per_path=global_per_path,
        )


class _TokenBucket:
    def __init__(
        self, capacity: int, period_seconds: float, *, now: Optional[float] = None
    ) -> None:
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.period = float(period_seconds)
        self.refill_rate = (
            self.capacity / self.period if self.period > 0 else float("inf")
        )
        self.last = now if now is not None else time.monotonic()

    def allow(self, now: Optional[float] = None) -> bool:
        t = now if now is not None else time.monotonic()
        elapsed = max(0.0, t - self.last)
        self.last = t
        # refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig):
        super().__init__(app)
        self.config = config
        # Dict: identity -> key -> list[buckets]
        self._buckets: Dict[str, Dict[str, List[_TokenBucket]]] = {}
        # Global buckets (identity-agnostic)
        self._global: Dict[str, List[_TokenBucket]] = {}
        self._log = logging.getLogger("dspx.server")

    def _identity(self, request: Request) -> Tuple[str, str]:
        # Prefer token identity when configured and header present
        if self.config.identity == "token":
            auth = request.headers.get("authorization")
            if auth and auth.startswith("Bearer "):
                return ("tok:" + auth.split(" ", 1)[1], "token")
        # Fallback to IP
        # Compute client IP considering trusted proxies
        client = request.client
        xff = request.headers.get("x-forwarded-for")
        if xff and self.config.trusted_proxies:
            chain = [ip.strip() for ip in xff.split(",") if ip.strip()]
            if chain:
                # Choose first IP in chain that is not trusted; else first in chain
                for ip in chain:
                    try:
                        addr = ipaddress.ip_address(ip)
                        if not any(addr in net for net in self.config.trusted_proxies):
                            return ("ip:" + ip, "ip")
                    except Exception:
                        continue
                return ("ip:" + chain[0], "ip")
        client = request.client
        host = client.host if client else "unknown"
        return ("ip:" + str(host), "ip")

    def _rules_for(self, method: str, path: str) -> Tuple[List[Rate], List[Rate]]:
        rules: List[Rate] = []
        grules: List[Rate] = []
        # Method-specific path first
        key = f"{method.upper()} {path}"
        if key in self.config.per_path:
            rules.extend(self.config.per_path[key])
        if key in self.config.global_per_path:
            grules.extend(self.config.global_per_path[key])
        # Generic path
        if path in self.config.per_path:
            rules.extend(self.config.per_path[path])
        if path in self.config.global_per_path:
            grules.extend(self.config.global_per_path[path])
        # Default
        if self.config.default:
            rules.extend(self.config.default)
        if self.config.global_default:
            grules.extend(self.config.global_default)
        return rules, grules

    async def dispatch(self, request: Request, call_next):
        if not self.config.enabled:
            return await call_next(request)
        start = time.monotonic()
        ident, ident_kind = self._identity(request)
        method = request.method.upper()
        path = request.url.path
        rules, grules = self._rules_for(method, path)
        # Prepare log context
        ctx = {"method": method, "path": path, "ident_kind": ident_kind}
        # Global rules first
        if grules:
            key_g = (
                f"{method} {path}"
                if f"{method} {path}" in self.config.global_per_path
                or path in self.config.global_per_path
                else "GLOBAL"
            )
            gb = self._global.get(key_g)
            if gb is None:
                gb = [_TokenBucket(r.capacity, r.period_seconds) for r in grules]
                self._global[key_g] = gb
            now = time.monotonic()
            if any(not b.allow(now) for b in gb):
                self._log.info(
                    "rate_limit", extra={"event": "ratelimit", **ctx, "scope": "global"}
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": "limit exceeded",
                        "status": 429,
                    },
                )
        if rules:
            key = (
                f"{method} {path}"
                if f"{method} {path}" in self.config.per_path
                or path in self.config.per_path
                else "GLOBAL"
            )
            buckmap = self._buckets.setdefault(ident, {})
            buckets = buckmap.get(key)
            if buckets is None:
                buckets = [_TokenBucket(r.capacity, r.period_seconds) for r in rules]
                buckmap[key] = buckets
            now = time.monotonic()
            if any(not b.allow(now) for b in buckets):
                self._log.info(
                    "rate_limit",
                    extra={"event": "ratelimit", **ctx, "scope": "identity"},
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": "limit exceeded",
                        "status": 429,
                    },
                )
        # Proceed
        resp = await call_next(request)
        # Structured access log (redact auth header)
        took = time.monotonic() - start
        self._log.info(
            "request",
            extra={
                "event": "request",
                **ctx,
                "status": resp.status_code,
                "took_ms": int(took * 1000),
            },
        )
        return resp


# ---- Lightweight counters (in-memory) ----


class _Stats:
    def __init__(self) -> None:
        self.requests_total = 0
        self.status_401 = 0
        self.status_429 = 0

    def snapshot(self) -> Dict[str, int]:
        return {
            "requests_total": self.requests_total,
            "status_401": self.status_401,
            "status_429": self.status_429,
        }


stats = _Stats()
