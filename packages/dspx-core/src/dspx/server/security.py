from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set, Dict, List, Tuple
import hashlib
import hmac
import os
import threading
import time
import logging
import ipaddress
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class UnauthorizedError(Exception):
    """Raised when authorization is required and invalid/missing.

    Handled centrally by the server to emit a standardized JSON error.
    """

    pass


class AuthConfigError(RuntimeError):
    """Raised when auth configuration cannot be loaded safely."""

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
    except OSError as exc:
        raise AuthConfigError(
            f"failed to load auth token file '{path}': {exc}"
        ) from exc
    if not tokens:
        raise AuthConfigError(f"auth token file '{path}' did not contain any tokens")
    return tokens


def _extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    if not authorization_header:
        return None
    parts = str(authorization_header).strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


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
        token_file_configured = bool(tf and tf.strip())
        if token_file_configured and tf is not None:
            tokens.update(_load_tokens_from_file(tf.strip()))
        skip_for_dev = _parse_bool_env(e.get("DSPX_AUTH_SKIP_FOR_DEV"), False)
        required = (
            False
            if skip_for_dev
            else _parse_bool_env(e.get("DSPX_AUTH_REQUIRED"), True)
        )
        if required and not tokens:
            raise AuthConfigError(
                "auth is required but no server tokens were configured; "
                "set DSPX_SERVER_TOKEN/DSPX_SERVER_TOKENS/DSPX_SERVER_TOKEN_FILE "
                "or opt into local-only bypass with DSPX_AUTH_SKIP_FOR_DEV=1"
            )
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
        return _extract_bearer_token(authorization_header)

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


_RATE_LIMIT_COUNT_RE = re.compile(r"^[1-9][0-9]*$")


def _parse_rate_token(tok: str) -> Rate:
    tok = tok.strip().lower()
    if not tok:
        raise ValueError("empty rate token")
    if "/" not in tok:
        raise ValueError("rate token must be like '10/sec' or '60/min'")
    n_str, per = tok.split("/", 1)
    count_text = n_str.strip()
    if not _RATE_LIMIT_COUNT_RE.fullmatch(count_text):
        raise ValueError(
            f"rate token count must be a positive integer in rate token '{tok}'"
        )
    n = int(count_text)
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


def _parse_rate_mapping(raw: str, *, env_name: str) -> Dict[str, List[Rate]]:
    import json as _json

    try:
        mapping = _json.loads(raw)
    except Exception as exc:
        raise ValueError(f"invalid JSON in {env_name}: {exc}") from exc
    if not isinstance(mapping, dict):
        raise ValueError(f"{env_name} must be a JSON object")

    parsed: Dict[str, List[Rate]] = {}
    for key, value in mapping.items():
        if not isinstance(value, str):
            raise ValueError(f"{env_name}[{key!r}] must be a rate spec string")
        parsed[str(key)] = parse_rate_spec(value)
    return parsed


@dataclass(frozen=True)
class RateLimitConfig:
    enabled: bool
    default: List[Rate]
    per_path: Dict[str, List[Rate]]
    identity: str  # 'token' or 'ip'
    trusted_proxies: List[ipaddress._BaseNetwork]
    global_default: List[Rate]
    global_per_path: Dict[str, List[Rate]]
    valid_tokens: frozenset[str] = frozenset()
    identity_ttl_seconds: float = 3600.0
    max_identity_entries: int = 4096

    @staticmethod
    def from_env(
        env: Optional[dict[str, str]] = None,
        *,
        valid_tokens: Optional[Set[str]] = None,
    ) -> "RateLimitConfig":
        e = os.environ if env is None else env
        enabled = _parse_bool_env(e.get("DSPX_RATE_LIMIT_ENABLED"), False)
        default_spec = e.get("DSPX_RATE_LIMIT_DEFAULT", "")
        default = parse_rate_spec(default_spec) if default_spec else []
        per_path: Dict[str, List[Rate]] = {}

        paths_raw = e.get("DSPX_RATE_LIMIT_PATHS")
        if paths_raw:
            per_path = _parse_rate_mapping(
                paths_raw,
                env_name="DSPX_RATE_LIMIT_PATHS",
            )
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
            global_default = parse_rate_spec(gspec)
        global_per_path: Dict[str, List[Rate]] = {}
        gpaths = (e.get("DSPX_RATE_LIMIT_GLOBAL_PATHS") or "").strip()
        if gpaths:
            global_per_path = _parse_rate_mapping(
                gpaths,
                env_name="DSPX_RATE_LIMIT_GLOBAL_PATHS",
            )
        ttl_raw = (e.get("DSPX_RATE_LIMIT_IDENTITY_TTL_SECONDS") or "").strip()
        try:
            identity_ttl_seconds = float(ttl_raw) if ttl_raw else 3600.0
        except Exception:
            identity_ttl_seconds = 3600.0
        max_raw = (e.get("DSPX_RATE_LIMIT_MAX_IDENTITIES") or "").strip()
        try:
            max_identity_entries = int(max_raw) if max_raw else 4096
        except Exception:
            max_identity_entries = 4096
        return RateLimitConfig(
            enabled=enabled,
            default=default,
            per_path=per_path,
            identity=identity if identity in {"token", "ip"} else "token",
            trusted_proxies=trusted_proxies,
            global_default=global_default,
            global_per_path=global_per_path,
            valid_tokens=frozenset(valid_tokens or set()),
            identity_ttl_seconds=max(0.0, identity_ttl_seconds),
            max_identity_entries=max(1, max_identity_entries),
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

    def _refilled_tokens(self, now: Optional[float] = None) -> tuple[float, float]:
        t = now if now is not None else time.monotonic()
        elapsed = max(0.0, t - self.last)
        tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        return t, tokens

    def would_allow(self, now: Optional[float] = None) -> bool:
        _, tokens = self._refilled_tokens(now)
        return tokens >= 1.0

    def consume(self, now: Optional[float] = None) -> bool:
        t, tokens = self._refilled_tokens(now)
        self.last = t
        self.tokens = tokens
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def allow(self, now: Optional[float] = None) -> bool:
        return self.consume(now)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: RateLimitConfig):
        super().__init__(app)
        self.config = config
        # Dict: identity -> key -> list[buckets]
        self._buckets: Dict[str, Dict[str, List[_TokenBucket]]] = {}
        self._bucket_last_seen: Dict[str, float] = {}
        # Global buckets (identity-agnostic)
        self._global: Dict[str, List[_TokenBucket]] = {}
        self._lock = threading.RLock()
        self._log = logging.getLogger("dspx.server")

    def _client_host(self, request: Request) -> str:
        client = request.client
        return str(client.host) if client else "unknown"

    def _is_trusted_proxy(self, host: str) -> bool:
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(addr in net for net in self.config.trusted_proxies)

    def _token_identity(self, token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
        return "tok:" + digest

    def _cleanup_identities(self, now: float) -> None:
        ttl = max(0.0, float(self.config.identity_ttl_seconds))
        with self._lock:
            if ttl > 0.0:
                expired = [
                    ident
                    for ident, seen in self._bucket_last_seen.items()
                    if (now - seen) > ttl
                ]
                for ident in expired:
                    self._bucket_last_seen.pop(ident, None)
                    self._buckets.pop(ident, None)
            max_entries = max(1, int(self.config.max_identity_entries))
            if len(self._buckets) <= max_entries:
                return
            overflow = len(self._buckets) - max_entries
            victims = sorted(self._bucket_last_seen.items(), key=lambda item: item[1])[
                0:overflow
            ]
            for ident, _ in victims:
                self._bucket_last_seen.pop(ident, None)
                self._buckets.pop(ident, None)

    def _remember_identity(self, ident: str, now: float) -> None:
        with self._lock:
            self._bucket_last_seen[ident] = now
            self._cleanup_identities(now)

    def _identity(self, request: Request) -> Tuple[str, str]:
        host = self._client_host(request)
        # Prefer validated token identity when configured and a known token is present.
        # For unauthenticated or invalid-token traffic, fall back to the immediate peer
        # instead of trusting X-Forwarded-For; otherwise clients can spray buckets by
        # spoofing forwarded IPs behind a trusted proxy.
        if self.config.identity == "token":
            token = _extract_bearer_token(request.headers.get("authorization"))
            if token and token in self.config.valid_tokens:
                return (self._token_identity(token), "token")
            return ("ip:" + host, "ip")
        # Fallback to IP
        # Only trust X-Forwarded-For when the immediate peer is a trusted proxy.
        xff = request.headers.get("x-forwarded-for")
        if xff and self.config.trusted_proxies and self._is_trusted_proxy(host):
            chain = [ip.strip() for ip in xff.split(",") if ip.strip()]
            if chain:
                # Choose first IP in chain that is not trusted; else first in chain.
                for ip in chain:
                    try:
                        addr = ipaddress.ip_address(ip)
                    except ValueError:
                        continue
                    if not any(addr in net for net in self.config.trusted_proxies):
                        return ("ip:" + ip, "ip")
                return ("ip:" + chain[0], "ip")
        return ("ip:" + host, "ip")

    def _rule_groups(
        self, method: str, path: str
    ) -> Tuple[List[Tuple[str, List[Rate]]], List[Tuple[str, List[Rate]]]]:
        rule_groups: List[Tuple[str, List[Rate]]] = []
        global_rule_groups: List[Tuple[str, List[Rate]]] = []
        method_key = f"{method.upper()} {path}"
        if method_key in self.config.per_path:
            rule_groups.append((method_key, self.config.per_path[method_key]))
        if path in self.config.per_path:
            rule_groups.append((path, self.config.per_path[path]))
        if self.config.default:
            rule_groups.append(("GLOBAL", self.config.default))
        if method_key in self.config.global_per_path:
            global_rule_groups.append(
                (method_key, self.config.global_per_path[method_key])
            )
        if path in self.config.global_per_path:
            global_rule_groups.append((path, self.config.global_per_path[path]))
        if self.config.global_default:
            global_rule_groups.append(("GLOBAL", self.config.global_default))
        return rule_groups, global_rule_groups

    def _rules_for(self, method: str, path: str) -> Tuple[List[Rate], List[Rate]]:
        """Return flattened rules for compatibility with older internal callers."""

        rule_groups, global_rule_groups = self._rule_groups(method, path)
        return (
            [rule for _, rules in rule_groups for rule in rules],
            [rule for _, rules in global_rule_groups for rule in rules],
        )

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        ident, ident_kind = self._identity(request)
        method = request.method.upper()
        path = request.url.path
        rule_groups, global_rule_groups = self._rule_groups(method, path)
        # Prepare log context
        ctx = {"method": method, "path": path, "ident_kind": ident_kind}
        if self.config.enabled:
            # Global rules first
            for key_g, grules in global_rule_groups:
                with self._lock:
                    gb = self._global.get(key_g)
                    if gb is None:
                        gb = [
                            _TokenBucket(r.capacity, r.period_seconds) for r in grules
                        ]
                        self._global[key_g] = gb
                now = time.monotonic()
                if not all(b.would_allow(now) for b in gb):
                    self._log.info(
                        "rate_limit",
                        extra={"event": "ratelimit", **ctx, "scope": "global"},
                    )
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "rate_limited",
                            "detail": "limit exceeded",
                            "status": 429,
                        },
                    )
                for bucket in gb:
                    bucket.consume(now)
            if rule_groups:
                self._remember_identity(ident, time.monotonic())
            for key, rules in rule_groups:
                now = time.monotonic()
                with self._lock:
                    buckmap = self._buckets.setdefault(ident, {})
                    buckets = buckmap.get(key)
                    if buckets is None:
                        buckets = [
                            _TokenBucket(r.capacity, r.period_seconds) for r in rules
                        ]
                        buckmap[key] = buckets
                if not all(b.would_allow(now) for b in buckets):
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
                for bucket in buckets:
                    bucket.consume(now)
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


# ---- Body size limit ----


@dataclass(frozen=True)
class BodySizeLimitConfig:
    """Configuration for request body size limiting."""

    max_bytes: int
    enabled: bool

    _DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB

    @staticmethod
    def from_env(env: Optional[dict[str, str]] = None) -> "BodySizeLimitConfig":
        e = os.environ if env is None else env
        enabled = _parse_bool_env(e.get("DSPX_BODY_SIZE_LIMIT_ENABLED"), True)
        raw = (e.get("DSPX_MAX_BODY_SIZE") or "").strip()
        if raw:
            max_bytes = _parse_size(raw)
        else:
            max_bytes = BodySizeLimitConfig._DEFAULT_MAX_BYTES
        if max_bytes < 0:
            raise ValueError(
                f"DSPX_MAX_BODY_SIZE must be non-negative, got {max_bytes}"
            )
        return BodySizeLimitConfig(max_bytes=max_bytes, enabled=enabled)


_SIZE_SUFFIXES: dict[str, int] = {
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "m": 1024 * 1024,
    "mb": 1024 * 1024,
    "g": 1024 * 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
}


def _parse_size(raw: str) -> int:
    """Parse a human-friendly size string like '10MB', '1m', '512k', '1048576'.

    Suffix values must use integer counts. Fractional inputs such as ``0.5k`` are
    rejected explicitly so operators do not accidentally get a silently truncated
    byte limit.
    """
    s = raw.strip().lower()
    if not s:
        return BodySizeLimitConfig._DEFAULT_MAX_BYTES
    # Try plain integer first
    try:
        return int(s)
    except ValueError:
        pass
    # Try <integer><suffix>
    for suffix, multiplier in sorted(
        _SIZE_SUFFIXES.items(), key=lambda kv: -len(kv[0])
    ):
        if s.endswith(suffix):
            num_part = s[: -len(suffix)].strip()
            if not num_part:
                break
            if not re.fullmatch(r"[0-9]+", num_part):
                raise ValueError(
                    f"invalid size value '{raw}': suffix-based sizes must use an integer count"
                )
            try:
                return int(num_part) * multiplier
            except (ValueError, OverflowError):
                raise ValueError(
                    f"invalid size value '{raw}': cannot parse '{num_part}' as integer"
                )
    raise ValueError(
        f"invalid size value '{raw}': expected integer bytes or <integer><suffix> "
        f"(suffixes: {', '.join(sorted(_SIZE_SUFFIXES))})"
    )


class BodySizeLimitMiddleware:
    """Reject requests once the streamed body exceeds the configured limit."""

    def __init__(self, app, config: BodySizeLimitConfig):
        self.app = app
        self.config = config
        self._log = logging.getLogger("dspx.server")

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not self.config.enabled:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        raw_content_length = headers.get("content-length")
        if raw_content_length is not None:
            try:
                content_length = int(raw_content_length)
            except (ValueError, TypeError):
                await JSONResponse(
                    status_code=400,
                    content={
                        "error": "invalid_request",
                        "detail": "invalid Content-Length header",
                        "status": 400,
                    },
                )(scope, receive, send)
                return
            if content_length > self.config.max_bytes:
                self._log_body_too_large(content_length, scope)
                await self._send_body_too_large(scope, receive, send, content_length)
                return

        buffered: list[dict[str, object]] = []
        total = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message.get("type") != "http.request":
                break
            body = message.get("body", b"")
            if isinstance(body, bytes):
                total += len(body)
            if total > self.config.max_bytes:
                self._log_body_too_large(total, scope)
                await self._send_body_too_large(scope, receive, send, total)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    def _log_body_too_large(self, length: int, scope) -> None:
        self._log.info(
            "body_too_large",
            extra={
                "event": "body_too_large",
                "content_length": length,
                "max_bytes": self.config.max_bytes,
                "path": scope.get("path", ""),
            },
        )

    async def _send_body_too_large(self, scope, receive, send, length: int) -> None:
        await JSONResponse(
            status_code=413,
            content={
                "error": "body_too_large",
                "detail": (
                    f"request body of {length} bytes exceeds "
                    f"the {self.config.max_bytes} byte limit"
                ),
                "status": 413,
            },
        )(scope, receive, send)


class _Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.requests_total = 0
            self.status_401 = 0
            self.status_429 = 0
            self.status_413 = 0

    def increment_requests(self) -> None:
        with self._lock:
            self.requests_total += 1

    def increment_status(self, code: int) -> None:
        with self._lock:
            if code == 401:
                self.status_401 += 1
            elif code == 429:
                self.status_429 += 1
            elif code == 413:
                self.status_413 += 1

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "status_401": self.status_401,
                "status_429": self.status_429,
                "status_413": self.status_413,
            }


stats = _Stats()


class RequestStatsMiddleware(BaseHTTPMiddleware):
    """Outermost middleware that tracks request/response statistics.

    Added last (runs outermost) so every request is counted regardless of which
    inner middleware short-circuits. This ensures /metrics reflects body-size
    rejections (413), rate-limit rejections (429), auth failures (401), etc.
    """

    async def dispatch(self, request: Request, call_next):
        stats.increment_requests()
        response = await call_next(request)
        stats.increment_status(response.status_code)
        return response
