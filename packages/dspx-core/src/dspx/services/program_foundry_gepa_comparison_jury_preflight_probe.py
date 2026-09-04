"""Isolated credential/catalog probe child for the foundry jury preflight.

Run as ``python -I -B <this file> '<json config>'`` by the parent preflight.
It imports only the standard library and ``httpx``; it never imports ``dspx``
or the ``dspy_lm_auth`` package. The owner's hash-pinned ``auth.py`` is loaded
from a file location under a non-package alias so the bearer token is read
through the owner's own no-refresh reader and never leaves this process.
``pi-api-key`` families (OpenCode Go) read one ``{"type": "api_key"}`` entry
with a verbatim copy of the owner's ``_chat_credential.read_existing_api_key_credential``
rules (that module imports the owner package, so it cannot be aliased in);
the owner file's hash is still verified before the copy is used.

Output is exactly one closed JSON object on stdout:

``{"credential_present": bool, "expiry_ok": bool, "expires_ms": int,
"endpoint_fixed": bool, "catalog": {"status_class": str, "catalog_count": int,
"catalog_ids_sha256": str, "model_listed": bool} | null}``

The catalog fact is one GET of the family's model listing (never a completion),
bounded to 10 s, no retries, ``Accept-Encoding: identity``, 1 MiB body cap.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

# Copied from the owner's GITHUB_COPILOT_HEADERS + COPILOT_ROUTE_EXTRA_HEADERS
# (dspy_lm_auth.auth / dspy_lm_auth._copilot_credential): non-secret, fixed.
COPILOT_CATALOG_HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "User-Agent": "GitHubCopilotChat/0.35.0",
    "Editor-Version": "vscode/1.107.0",
    "Editor-Plugin-Version": "copilot-chat/0.35.0",
    "Copilot-Integration-Id": "vscode-chat",
    "X-GitHub-Api-Version": "2026-06-01",
    "X-Initiator": "user",
    "Openai-Intent": "conversation-edits",
}
CATALOG_TIMEOUT_SECONDS = 10.0
CATALOG_MAX_BODY_BYTES = 1024 * 1024
_AUTH_ALIAS = "_dspx_foundry_preflight_owner_auth"
_BEARER_PROVIDERS = frozenset({"github-copilot", "xai", "opencode-go"})
AUTH_MODE_PI_OAUTH = "pi-oauth-no-refresh"
AUTH_MODE_PI_API_KEY = "pi-api-key"
AUTH_MODE_NONE = "none"


def _load_owner_auth(path: Path, expected_sha256: str) -> ModuleType:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("owner auth module hash drift")
    spec = importlib.util.spec_from_file_location(_AUTH_ALIAS, path)
    if spec is None or spec.loader is None:
        raise ValueError("owner auth module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_AUTH_ALIAS] = module
    spec.loader.exec_module(module)
    return module


def _read_credential(
    auth: ModuleType, *, auth_path: str | None, auth_provider: str
) -> tuple[str | None, bool, int, bool]:
    """Return (token, expiry_ok, expires_ms, endpoint_fixed) without refresh."""

    target = auth.DEFAULT_PI_AUTH_PATH if auth_path is None else Path(auth_path)
    try:
        token, _account, expires = auth.read_existing_oauth_credential_without_refresh(
            target, auth_provider
        )
    except ValueError:
        return None, False, 0, False
    try:
        auth.validate_oauth_credential_expiry(expires)
        expiry_ok = True
    except ValueError:
        expiry_ok = False
    endpoint_fixed = True
    if auth_provider == "github-copilot":
        try:
            endpoint_fixed = (
                auth.github_copilot_base_url(token) == auth.GITHUB_COPILOT_API_BASE
            )
        except ValueError:
            endpoint_fixed = False
    expires_ms = int(expires) if isinstance(expires, (int, float)) else 0
    return token, expiry_ok, expires_ms, endpoint_fixed


def _verify_owner_file(path: Path, expected_sha256: str) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("owner credential module hash drift")


def _read_api_key_credential(*, auth_path: str | None, auth_entry: str) -> str | None:
    """Mirror ``read_existing_api_key_credential``: read-only, no refresh, no expiry.

    Returns the key only inside this process; the caller reduces it to booleans.
    """

    target = Path("~/.pi/agent/auth.json") if auth_path is None else Path(auth_path)
    try:
        with target.expanduser().open("r", encoding="utf-8") as handle:
            current = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    credential = current.get(auth_entry) if isinstance(current, dict) else None
    if not isinstance(credential, dict) or credential.get("type") != "api_key":
        return None
    key = credential.get("key")
    if (
        not isinstance(key, str)
        or not key
        or not all(0x21 <= ord(char) <= 0x7E for char in key)
    ):
        return None
    return key


def _catalog_ids(body: bytes) -> list[str]:
    payload = json.loads(body.decode("utf-8"))
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("catalog body is not a model list")
    ids: list[str] = []
    for row in rows:
        identifier = row.get("id") if isinstance(row, dict) else None
        if isinstance(identifier, str) and identifier:
            ids.append(identifier)
    return sorted(set(ids))


def fetch_catalog(
    url: str, *, model: str, token: str | None, auth_provider: str
) -> dict[str, Any]:
    """One bounded GET of a model listing; closed facts, never a completion."""

    import httpx

    headers = {"Accept-Encoding": "identity", "Accept": "application/json"}
    if auth_provider == "github-copilot":
        headers.update(COPILOT_CATALOG_HEADERS)
    if token is not None and auth_provider in _BEARER_PROVIDERS:
        headers["Authorization"] = f"Bearer {token}"
    status_class = "transport_error"
    body = b""
    status_code = 0
    try:
        with httpx.Client(
            timeout=CATALOG_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream("GET", url, headers=headers) as response:
                status_code = response.status_code
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > CATALOG_MAX_BODY_BYTES:
                        status_class = "body_too_large"
                        body = b""
                        break
                else:
                    status_class = f"{status_code // 100}xx"
    except httpx.TimeoutException:
        status_class = "timeout"
    except httpx.HTTPError:
        status_class = "transport_error"
    ids: list[str] = []
    if status_class == "2xx":
        try:
            ids = _catalog_ids(body)
        except (UnicodeDecodeError, ValueError):
            status_class = "non_json"
            ids = []
    return {
        "status_class": status_class,
        "status_code": status_code,
        "catalog_count": len(ids),
        "catalog_ids_sha256": hashlib.sha256(
            json.dumps(ids, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "model_listed": status_class == "2xx" and model in ids,
    }


def run(config: dict[str, Any]) -> dict[str, Any]:
    auth_provider = str(config["auth_provider"])
    auth_mode = str(config["auth_mode"])
    model = str(config["model"])
    catalog_url = config.get("catalog_url")
    token: str | None = None
    credential = {
        "credential_present": False,
        "expiry_ok": False,
        "expires_ms": 0,
        "endpoint_fixed": False,
    }
    if auth_mode == AUTH_MODE_PI_API_KEY:
        _verify_owner_file(
            Path(str(config["credential_module_path"])),
            str(config["credential_module_sha256"]),
        )
        token = _read_api_key_credential(
            auth_path=config.get("auth_path"), auth_entry=auth_provider
        )
        # Pi api_key entries carry no expiry and the owner endpoint is fixed.
        credential = {
            "credential_present": token is not None,
            "expiry_ok": token is not None,
            "expires_ms": 0,
            "endpoint_fixed": token is not None,
        }
    elif auth_mode == AUTH_MODE_PI_OAUTH:
        auth = _load_owner_auth(
            Path(str(config["auth_module_path"])),
            str(config["auth_module_sha256"]),
        )
        token, expiry_ok, expires_ms, endpoint_fixed = _read_credential(
            auth,
            auth_path=config.get("auth_path"),
            auth_provider=auth_provider,
        )
        credential = {
            "credential_present": token is not None,
            "expiry_ok": expiry_ok,
            "expires_ms": expires_ms,
            "endpoint_fixed": endpoint_fixed,
        }
    elif auth_mode == AUTH_MODE_NONE:
        credential = {
            "credential_present": True,
            "expiry_ok": True,
            "expires_ms": 0,
            "endpoint_fixed": True,
        }
    else:
        raise ValueError("unknown auth mode")
    catalog: dict[str, Any] | None = None
    credential_ok = (
        credential["credential_present"]
        and credential["expiry_ok"]
        and credential["endpoint_fixed"]
    )
    if isinstance(catalog_url, str) and catalog_url and credential_ok:
        catalog = fetch_catalog(
            catalog_url, model=model, token=token, auth_provider=auth_provider
        )
    return {**credential, "catalog": catalog}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return 2
    try:
        config = json.loads(argv[1])
        facts = run(config)
    except Exception:  # noqa: BLE001 - the child must never leak diagnostics
        return 1
    sys.stdout.write(json.dumps(facts, separators=(",", ":"), sort_keys=True))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
