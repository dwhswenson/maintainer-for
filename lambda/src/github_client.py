from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import requests

from errors import UpstreamServiceError, UserNotFoundError


Requestor = Callable[..., requests.Response]


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        timeout: float = 10.0,
        max_workers: int = 16,
        org: str = "conda-forge",
        base_url: str = "https://api.github.com",
        requestor: Requestor | None = None,
    ) -> None:
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self.timeout = timeout
        self.max_workers = max_workers
        self.org = org
        self.base_url = base_url.rstrip("/")
        self.requestor = requestor or requests.request

    def get_conda_forge_projects(self, username: str) -> list[str]:
        self._verify_user_exists(username)
        team_slugs = self._list_team_slugs()
        if not team_slugs:
            return []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(team_slugs))) as executor:
            memberships = executor.map(lambda slug: self._is_team_member(slug, username), team_slugs)
            projects = [slug for slug, is_member in zip(team_slugs, memberships, strict=True) if is_member]

        return sorted(projects)

    def _verify_user_exists(self, username: str) -> None:
        response = self._request("GET", f"/users/{username}")
        if response.status_code == 404:
            raise UserNotFoundError("github", username)
        self._ensure_success(response, "github", f"failed to verify GitHub user {username}")

    def _list_team_slugs(self) -> list[str]:
        team_slugs: list[str] = []
        page = 1

        while True:
            response = self._request(
                "GET",
                f"/orgs/{self.org}/teams",
                params={"per_page": 100, "page": page},
            )
            self._ensure_success(response, "github", "failed to list conda-forge teams")

            teams = response.json()
            if not isinstance(teams, list):
                raise UpstreamServiceError("github", "unexpected response while listing conda-forge teams")

            if not teams:
                break

            team_slugs.extend(team["slug"] for team in teams if isinstance(team, dict) and "slug" in team)
            page += 1

        return team_slugs

    def _is_team_member(self, team_slug: str, username: str) -> bool:
        response = self._request(
            "GET",
            f"/orgs/{self.org}/teams/{team_slug}/memberships/{username}",
        )
        if response.status_code == 404:
            return False
        self._ensure_success(
            response,
            "github",
            f"failed to check membership for {username} in team {team_slug}",
        )
        return True

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
