from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

import httpx

from dspx.http_guard import send_with_host_allowlist
from dspx.policy import (
    allow_network_mutate as _policy_allow_mutate,
    allowed_http_methods as _policy_allowed_methods,
    disallowed_http_methods as _policy_disallowed_methods,
    enforce_network_mutate as _policy_enforce_mutate,
)


def _as_set(val: Optional[str]) -> set[str] | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return {p.strip() for p in s.split(",") if p.strip()}


def _capability_for_method(method: str) -> str:
    m = method.upper()
    return (
        "network.mutate" if m in {"POST", "PUT", "PATCH", "DELETE"} else "network.read"
    )


def _base_url_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("DSPX_GITLAB_BASE_URL must be an absolute http(s) URL")
    if parsed.params or parsed.query or parsed.fragment:
        raise RuntimeError(
            "DSPX_GITLAB_BASE_URL must not include params, query, or fragment"
        )
    return parsed.hostname


@dataclass(frozen=True)
class GitLabConfig:
    base_url: str
    token: str
    project_map: dict[str, int]
    allowed_project_keys: set[str] | None
    allowed_hosts: set[str]
    default_labels: list[str]


def load_gitlab_config_from_env() -> GitLabConfig:
    base_url = (os.getenv("DSPX_GITLAB_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("DSPX_GITLAB_BASE_URL not set")
    token = (os.getenv("DSPX_GITLAB_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("DSPX_GITLAB_TOKEN not set")

    mpj = os.getenv("DSPX_GITLAB_PROJECT_MAP_JSON")
    mpf = os.getenv("DSPX_GITLAB_PROJECT_MAP_FILE")
    data: Any = None
    if mpj:
        data = json.loads(mpj)
    elif mpf:
        data = json.loads(Path(mpf).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("DSPX_GITLAB_PROJECT_MAP_JSON/FILE not set or invalid")
    project_map: dict[str, int] = {}
    for k, v in data.items():
        raw_id: Any
        if isinstance(v, dict):
            raw_id = v.get("id")
        else:
            raw_id = v
        if raw_id is None:
            continue
        try:
            project_map[str(k)] = int(raw_id)
        except Exception:
            continue
    if not project_map:
        raise RuntimeError("GitLab project map is empty")

    allowed_keys = _as_set(os.getenv("DSPX_GITLAB_ALLOWED_PROJECT_KEYS"))
    allowed_hosts = _as_set(os.getenv("DSPX_GITLAB_ALLOWED_HOSTS"))
    host = _base_url_host(base_url)
    allowed_hosts = allowed_hosts or {host}
    if host and host not in allowed_hosts:
        raise RuntimeError(f"GitLab host '{host}' not in DSPX_GITLAB_ALLOWED_HOSTS")

    default_labels: list[str] = [
        s.strip()
        for s in (os.getenv("DSPX_GITLAB_DEFAULT_LABELS") or "").split(",")
        if s.strip()
    ]
    return GitLabConfig(
        base_url=base_url,
        token=token,
        project_map=project_map,
        allowed_project_keys=allowed_keys,
        allowed_hosts=set(allowed_hosts),
        default_labels=default_labels,
    )


class GitLabClient:
    def __init__(self, cfg: GitLabConfig, *, client: Optional[httpx.Client] = None):
        host = _base_url_host(cfg.base_url)
        if host not in cfg.allowed_hosts:
            raise PermissionError(f"Host not allowed: {host}")
        self.cfg = cfg
        self._client = client

    def _check_method_policy(self, method: str) -> None:
        allow_set = _policy_allowed_methods()
        deny_set = _policy_disallowed_methods()
        m = method.upper()
        if allow_set is not None and m not in allow_set:
            raise PermissionError(f"HTTP method '{m}' not allowed by policy")
        if m in deny_set:
            raise PermissionError(f"HTTP method '{m}' denied by policy")

        from dspx.policy import check_capability

        check_capability(_capability_for_method(m))

        if (
            _policy_enforce_mutate()
            and m in {"POST", "PUT", "PATCH", "DELETE"}
            and not _policy_allow_mutate()
        ):
            raise PermissionError(
                f"Mutating HTTP method '{m}' requires DSPX_POLICY_ALLOW_NETWORK_MUTATE=1"
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
    ) -> httpx.Response:
        self._check_method_policy(method)
        close_client = False
        client = self._client
        if client is None:
            client = httpx.Client(timeout=20.0)
            close_client = True
        try:
            url = f"{self.cfg.base_url}{path}"
            host = urlparse(url).hostname or ""
            if host and host not in self.cfg.allowed_hosts:
                raise PermissionError(f"Host not allowed: {host}")
            headers = {"Authorization": f"Bearer {self.cfg.token}"}
            for _attempt in range(3):
                req = client.build_request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
                resp = send_with_host_allowlist(
                    client,
                    req,
                    allowed_hosts=self.cfg.allowed_hosts,
                    blocked_error_prefix="Host not allowed",
                    redirect_error_prefix="Redirect target host not allowed",
                )
                if resp.status_code != 429:
                    return resp
                ra = resp.headers.get("Retry-After")
                try:
                    delay = float(ra) if ra else 1.0
                except Exception:
                    delay = 1.0
                time.sleep(min(max(delay, 0.1), 10.0))
            return resp
        finally:
            if close_client:
                client.close()

    def project_id(self, project_key: str) -> int:
        if (
            self.cfg.allowed_project_keys is not None
            and project_key not in self.cfg.allowed_project_keys
        ):
            raise PermissionError(f"project_key '{project_key}' not allowed")
        if project_key not in self.cfg.project_map:
            raise KeyError(
                f"unknown project_key '{project_key}' (missing from project map)"
            )
        return int(self.cfg.project_map[project_key])

    def list_issues(
        self, project_id: int, *, labels: list[str]
    ) -> list[dict[str, Any]]:
        page = 1
        issues: list[dict[str, Any]] = []
        while True:
            params = {
                "labels": ",".join(labels),
                "page": page,
                "per_page": 100,
            }
            resp = self._request(
                "GET",
                f"/api/v4/projects/{project_id}/issues",
                params=params,
            )
            if resp.status_code == 401 or resp.status_code == 403:
                raise PermissionError("GitLab auth failed (401/403)")
            if resp.status_code == 404:
                raise FileNotFoundError(f"GitLab project not found: {project_id}")
            resp.raise_for_status()
            data = resp.json()
            batch = data if isinstance(data, list) else []
            issues.extend(item for item in batch if isinstance(item, dict))

            next_page = str(resp.headers.get("x-next-page") or "").strip()
            if next_page:
                try:
                    page = int(next_page)
                    continue
                except Exception:
                    pass
            if len(batch) < 100:
                break
            page += 1
        return issues

    def get_issue(self, project_id: int, iid: int) -> dict[str, Any]:
        resp = self._request("GET", f"/api/v4/projects/{project_id}/issues/{iid}")
        if resp.status_code == 401 or resp.status_code == 403:
            raise PermissionError("GitLab auth failed (401/403)")
        if resp.status_code == 404:
            raise FileNotFoundError(f"GitLab issue not found: {project_id}#{iid}")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def create_issue(
        self, project_id: int, *, title: str, description: str, labels: list[str]
    ) -> dict[str, Any]:
        resp = self._request(
            "POST",
            f"/api/v4/projects/{project_id}/issues",
            json_body={
                "title": title,
                "description": description,
                "labels": ",".join(labels),
            },
        )
        if resp.status_code == 401 or resp.status_code == 403:
            raise PermissionError("GitLab auth failed (401/403)")
        if resp.status_code == 404:
            raise FileNotFoundError(f"GitLab project not found: {project_id}")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def update_issue(
        self,
        project_id: int,
        iid: int,
        *,
        title: str,
        description: str,
        labels: list[str],
    ) -> dict[str, Any]:
        resp = self._request(
            "PUT",
            f"/api/v4/projects/{project_id}/issues/{iid}",
            json_body={
                "title": title,
                "description": description,
                "labels": ",".join(labels),
            },
        )
        if resp.status_code == 401 or resp.status_code == 403:
            raise PermissionError("GitLab auth failed (401/403)")
        if resp.status_code == 404:
            raise FileNotFoundError(f"GitLab issue not found: {project_id}#{iid}")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def close_issue(self, project_id: int, iid: int) -> dict[str, Any]:
        resp = self._request(
            "PUT",
            f"/api/v4/projects/{project_id}/issues/{iid}",
            json_body={"state_event": "close"},
        )
        if resp.status_code == 401 or resp.status_code == 403:
            raise PermissionError("GitLab auth failed (401/403)")
        if resp.status_code == 404:
            raise FileNotFoundError(f"GitLab issue not found: {project_id}#{iid}")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}
