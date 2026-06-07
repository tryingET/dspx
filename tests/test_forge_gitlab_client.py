from __future__ import annotations

import httpx
import pytest

from dspx_forge.gitlab_client import (
    GitLabClient,
    GitLabConfig,
    load_gitlab_config_from_env,
)


@pytest.mark.forge
def test_gitlab_config_rejects_schemeless_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_GITLAB_BASE_URL", "gitlab.example.com")
    monkeypatch.setenv("DSPX_GITLAB_TOKEN", "tok")
    monkeypatch.setenv("DSPX_GITLAB_PROJECT_MAP_JSON", '{"core": 101}')

    with pytest.raises(RuntimeError, match=r"absolute http\(s\) URL"):
        load_gitlab_config_from_env()


@pytest.mark.forge
def test_gitlab_client_rejects_manually_constructed_schemeless_base_url() -> None:
    cfg = GitLabConfig(
        base_url="gitlab.example.com",
        token="tok",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )

    with pytest.raises(RuntimeError, match=r"absolute http\(s\) URL"):
        GitLabClient(cfg)


@pytest.mark.forge
def test_gitlab_client_rejects_redirect_to_unallowed_host() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "gitlab.example.com":
            return httpx.Response(
                302,
                headers={"location": "https://evil.example/leak"},
                request=request,
            )
        return httpx.Response(200, json={"ok": True}, request=request)

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com",
        token="tok",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )
    client = GitLabClient(
        cfg,
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
        ),
    )

    with pytest.raises(PermissionError):
        client._request("GET", "/api/v4/projects/101/issues")

    assert seen == ["https://gitlab.example.com/api/v4/projects/101/issues"]


@pytest.mark.forge
def test_gitlab_client_allows_non_default_port_when_origin_is_allowed() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=[], request=request)

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com:8443",
        token="tok",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"https://gitlab.example.com:8443"},
        default_labels=[],
    )
    client = GitLabClient(
        cfg,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.list_issues(101, labels=["dspx-wo:abc12345"])

    assert seen_urls == [
        "https://gitlab.example.com:8443/api/v4/projects/101/issues?labels=dspx-wo%3Aabc12345&page=1&per_page=100"
    ]


@pytest.mark.forge
def test_gitlab_client_uses_private_token_header_for_gitlab_pat() -> None:
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json=[], request=request)

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com",
        token="glpat-xxxxxxxxxx",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )
    client = GitLabClient(
        cfg,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.list_issues(101, labels=["dspx-wo:abc12345"])

    assert seen_headers.get("private-token") == "glpat-xxxxxxxxxx"
    assert seen_headers.get("authorization") is None


@pytest.mark.forge
def test_gitlab_client_list_issues_follows_pagination() -> None:
    seen_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        seen_pages.append(page)
        if page == "1":
            return httpx.Response(
                200,
                json=[{"iid": 1}],
                headers={"x-next-page": "2"},
                request=request,
            )
        if page == "2":
            return httpx.Response(200, json=[{"iid": 2}], request=request)
        return httpx.Response(200, json=[], request=request)

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com",
        token="tok",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )
    client = GitLabClient(
        cfg,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    issues = client.list_issues(101, labels=["dspx-wo:abc12345"])

    assert [issue["iid"] for issue in issues] == [1, 2]
    assert seen_pages == ["1", "2"]
