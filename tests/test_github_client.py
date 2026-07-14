from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from maintainer_for.errors import UpstreamServiceError, UserNotFoundError
from maintainer_for.github_client import GitHubClient


class FakeResponse:
    def __init__(self, status_code: int, *, json_data=None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class GitHubClientTests(TestCase):
    @patch("maintainer_for.github_client.subprocess.run")
    @patch("maintainer_for.github_client.os.getenv")
    def test_prefers_explicit_token_over_env_and_gh(self, getenv, subprocess_run) -> None:
        client = GitHubClient(token="explicit-token")

        self.assertEqual(client.token, "explicit-token")
        getenv.assert_not_called()
        subprocess_run.assert_not_called()

    @patch("maintainer_for.github_client.subprocess.run")
    @patch("maintainer_for.github_client.os.getenv")
    def test_falls_back_to_gh_token_env(self, getenv, subprocess_run) -> None:
        def getenv_side_effect(name: str) -> str | None:
            return {"GITHUB_TOKEN": None, "GH_TOKEN": "gh-env-token"}.get(name)

        getenv.side_effect = getenv_side_effect

        client = GitHubClient()

        self.assertEqual(client.token, "gh-env-token")
        subprocess_run.assert_not_called()

    @patch("maintainer_for.github_client.subprocess.run")
    @patch("maintainer_for.github_client.os.getenv")
    def test_falls_back_to_gh_cli_token(self, getenv, subprocess_run) -> None:
        getenv.return_value = None
        subprocess_run.return_value.stdout = "token-from-gh\n"

        client = GitHubClient()

        self.assertEqual(client.token, "token-from-gh")
        subprocess_run.assert_called_once_with(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("maintainer_for.github_client.subprocess.run")
    @patch("maintainer_for.github_client.os.getenv")
    def test_uses_no_token_when_gh_cli_lookup_fails(self, getenv, subprocess_run) -> None:
        getenv.return_value = None
        subprocess_run.side_effect = FileNotFoundError()

        client = GitHubClient()

        self.assertIsNone(client.token)

    def test_paginates_graphql_team_list_across_pages(self) -> None:
        responses = [
            FakeResponse(
                200,
                json_data={
                    "data": {
                        "user": {"login": "alice"},
                        "organization": {
                            "teams": {
                                "nodes": [{"slug": "beta"}, {"slug": "all-members"}, {"slug": "alpha"}],
                                "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                            }
                        },
                    }
                },
            ),
            FakeResponse(
                200,
                json_data={
                    "data": {
                        "user": {"login": "alice"},
                        "organization": {
                            "teams": {
                                "nodes": [{"slug": "gamma"}],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        },
                    }
                },
            ),
        ]
        calls = []

        def requestor(method, url, **kwargs):
            calls.append((method, url, kwargs["json"]["variables"]["after"]))
            return responses.pop(0)

        client = GitHubClient(requestor=requestor)

        projects = client.get_conda_forge_projects("alice")

        self.assertEqual(projects, ["alpha", "beta", "gamma"])
        self.assertEqual(
            calls,
            [
                ("POST", "https://api.github.com/graphql", None),
                ("POST", "https://api.github.com/graphql", "cursor-1"),
            ],
        )

    def test_returns_empty_list_when_user_has_no_matching_teams(self) -> None:
        def requestor(method, url, **kwargs):
            return FakeResponse(
                200,
                json_data={
                    "data": {
                        "user": {"login": "alice"},
                        "organization": {
                            "teams": {
                                "nodes": [],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        },
                    }
                },
            )

        client = GitHubClient(requestor=requestor)

        projects = client.get_conda_forge_projects("alice")

        self.assertEqual(projects, [])

    def test_raises_user_not_found_when_graphql_user_is_null(self) -> None:
        def requestor(method, url, **kwargs):
            return FakeResponse(
                200,
                json_data={
                    "data": {
                        "user": None,
                        "organization": {
                            "teams": {
                                "nodes": [],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        },
                    }
                },
            )

        client = GitHubClient(requestor=requestor)

        with self.assertRaises(UserNotFoundError):
            client.get_conda_forge_projects("missing-user")

    def test_raises_upstream_error_on_graphql_error(self) -> None:
        def requestor(method, url, **kwargs):
            return FakeResponse(
                200,
                json_data={"errors": [{"message": "boom"}]},
            )

        client = GitHubClient(requestor=requestor)

        with self.assertRaises(UpstreamServiceError) as exc:
            client.get_conda_forge_projects("alice")

        self.assertIn("boom", str(exc.exception))

    def test_raises_upstream_error_on_graphql_http_failure(self) -> None:
        def requestor(method, url, **kwargs):
            return FakeResponse(500, json_data={"message": "boom"})

        client = GitHubClient(requestor=requestor)

        with self.assertRaises(UpstreamServiceError):
            client.get_conda_forge_projects("alice")
