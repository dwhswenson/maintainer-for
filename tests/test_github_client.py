from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lambda" / "src"))

from errors import UpstreamServiceError
from github_client import GitHubClient


class FakeResponse:
    def __init__(self, status_code: int, *, json_data=None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class GitHubClientTests(TestCase):
    def test_paginates_team_list_across_pages(self) -> None:
        responses = {
            ("GET", "https://api.github.com/users/alice"): FakeResponse(200, json_data={}),
            ("GET", "https://api.github.com/orgs/conda-forge/teams", (("page", 1), ("per_page", 100))): FakeResponse(
                200,
                json_data=[{"slug": "beta"}, {"slug": "alpha"}],
            ),
            ("GET", "https://api.github.com/orgs/conda-forge/teams", (("page", 2), ("per_page", 100))): FakeResponse(
                200,
                json_data=[{"slug": "gamma"}],
            ),
            ("GET", "https://api.github.com/orgs/conda-forge/teams", (("page", 3), ("per_page", 100))): FakeResponse(
                200,
                json_data=[],
            ),
            ("GET", "https://api.github.com/orgs/conda-forge/teams/beta/memberships/alice"): FakeResponse(200),
            ("GET", "https://api.github.com/orgs/conda-forge/teams/alpha/memberships/alice"): FakeResponse(200),
            ("GET", "https://api.github.com/orgs/conda-forge/teams/gamma/memberships/alice"): FakeResponse(200),
        }

        def requestor(method, url, **kwargs):
            params = kwargs.get("params")
            key = (method, url) if params is None else (method, url, tuple(sorted(params.items())))
            return responses[key]

        client = GitHubClient(requestor=requestor, max_workers=2)

        projects = client.get_conda_forge_projects("alice")

        self.assertEqual(projects, ["alpha", "beta", "gamma"])

    def test_filters_memberships_by_status_code(self) -> None:
        responses = {
            ("GET", "https://api.github.com/users/alice"): FakeResponse(200, json_data={}),
            ("GET", "https://api.github.com/orgs/conda-forge/teams", (("page", 1), ("per_page", 100))): FakeResponse(
                200,
                json_data=[{"slug": "member-team"}, {"slug": "other-team"}],
            ),
            ("GET", "https://api.github.com/orgs/conda-forge/teams", (("page", 2), ("per_page", 100))): FakeResponse(
                200,
                json_data=[],
            ),
            ("GET", "https://api.github.com/orgs/conda-forge/teams/member-team/memberships/alice"): FakeResponse(200),
            ("GET", "https://api.github.com/orgs/conda-forge/teams/other-team/memberships/alice"): FakeResponse(404),
        }

        def requestor(method, url, **kwargs):
            params = kwargs.get("params")
            key = (method, url) if params is None else (method, url, tuple(sorted(params.items())))
            return responses[key]

        client = GitHubClient(requestor=requestor, max_workers=2)

        projects = client.get_conda_forge_projects("alice")

        self.assertEqual(projects, ["member-team"])

    def test_raises_upstream_error_on_team_list_failure(self) -> None:
        responses = {
            ("GET", "https://api.github.com/users/alice"): FakeResponse(200, json_data={}),
            ("GET", "https://api.github.com/orgs/conda-forge/teams", (("page", 1), ("per_page", 100))): FakeResponse(
                500,
                json_data={"message": "boom"},
            ),
        }

        def requestor(method, url, **kwargs):
            params = kwargs.get("params")
            key = (method, url) if params is None else (method, url, tuple(sorted(params.items())))
            return responses[key]

        client = GitHubClient(requestor=requestor)

        with self.assertRaises(UpstreamServiceError):
            client.get_conda_forge_projects("alice")
