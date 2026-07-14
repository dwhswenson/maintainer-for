from __future__ import annotations

import os
import subprocess
from typing import Any, Callable

import requests

from errors import UpstreamServiceError, UserNotFoundError


Requestor = Callable[..., requests.Response]


class GitHubClient:
    TEAMS_QUERY = """
    query($org: String!, $username: String!, $after: String) {
      user(login: $username) {
        login
      }
      organization(login: $org) {
        teams(first: 100, after: $after, userLogins: [$username]) {
          nodes {
            slug
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
    }
    """

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 10.0,
        max_workers: int = 16,
        org: str = "conda-forge",
        base_url: str = "https://api.github.com",
        requestor: Requestor | None = None,
    ) -> None:
        self.token = self._resolve_token(token)
        self.timeout = timeout
        self.max_workers = max_workers
        self.org = org
        self.base_url = base_url.rstrip("/")
        self.requestor = requestor or requests.request

    def get_conda_forge_projects(self, username: str) -> list[str]:
        team_slugs: list[str] = []
        after: str | None = None

        while True:
            response = self._request(
                "POST",
                "/graphql",
                json={
                    "query": self.TEAMS_QUERY,
                    "variables": {
                        "org": self.org,
                        "username": username,
                        "after": after,
                    },
                },
            )
            self._ensure_success(response, "github", "failed to query conda-forge teams")

            payload = response.json()
            if not isinstance(payload, dict):
                raise UpstreamServiceError("github", "unexpected response while querying conda-forge teams")

            errors = payload.get("errors")
            if errors:
                raise UpstreamServiceError("github", self._format_graphql_errors(errors))

            data = payload.get("data")
            if not isinstance(data, dict):
                raise UpstreamServiceError("github", "missing data while querying conda-forge teams")

            if data.get("user") is None:
                raise UserNotFoundError("github", username)

            organization = data.get("organization")
            if not isinstance(organization, dict):
                raise UpstreamServiceError("github", f"organization not found: {self.org}")

            teams = organization.get("teams")
            if not isinstance(teams, dict):
                raise UpstreamServiceError("github", "missing teams connection while querying conda-forge teams")

            nodes = teams.get("nodes")
            if not isinstance(nodes, list):
                raise UpstreamServiceError("github", "unexpected teams payload while querying conda-forge teams")

            team_slugs.extend(node["slug"] for node in nodes if isinstance(node, dict) and "slug" in node)

            page_info = teams.get("pageInfo")
            if not isinstance(page_info, dict):
                raise UpstreamServiceError("github", "missing page info while querying conda-forge teams")

            if not page_info.get("hasNextPage"):
                break

            after = page_info.get("endCursor")
            if not isinstance(after, str) or not after:
                raise UpstreamServiceError("github", "missing end cursor while querying conda-forge teams")

        return sorted(team_slugs)

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "maintainer-for-lambda",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            return self.requestor(method, url, headers=headers, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise UpstreamServiceError("github", f"GitHub request failed: {exc}") from exc

    @staticmethod
    def _ensure_success(response: requests.Response, source: str, message: str) -> None:
        if 200 <= response.status_code < 300:
            return
        raise UpstreamServiceError(source, f"{message} (status {response.status_code})")

    @staticmethod
    def _format_graphql_errors(errors: Any) -> str:
        if not isinstance(errors, list):
            return "unexpected GraphQL error response"

        messages = [error.get("message") for error in errors if isinstance(error, dict) and error.get("message")]
        if not messages:
            return "unexpected GraphQL error response"

        return "; ".join(messages)

    @staticmethod
    def _resolve_token(token: str | None) -> str | None:
        if token is not None:
            return token

        env_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if env_token:
            return env_token

        return GitHubClient._get_gh_cli_token()

    @staticmethod
    def _get_gh_cli_token() -> str | None:
        try:
            completed = subprocess.run(
                ["gh", "auth", "token"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

        token = completed.stdout.strip()
        return token or None
