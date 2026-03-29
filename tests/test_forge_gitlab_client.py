from __future__ import annotations

import httpx
import pytest

from dspx_forge.gitlab_client import GitLabClient, GitLabConfig


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
