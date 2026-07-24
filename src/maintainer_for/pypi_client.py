from __future__ import annotations

import re
import xmlrpc.client
from typing import Any, Callable
from urllib.parse import urlparse
from xml.parsers.expat import ExpatError

import requests
from bs4 import BeautifulSoup, Tag

from maintainer_for.errors import UpstreamServiceError, UserNotFoundError


Requestor = Callable[..., requests.Response]

PROJECT_PATH_RE = re.compile(r"^/project/([^/]+)/?$")


class PyPIClient:
    def __init__(
        self,
        timeout: float = 10.0,
        base_url: str = "https://pypi.org",
        requestor: Requestor | None = None,
    ) -> None:
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self.requestor = requestor or requests.request

    def get_projects(self, username: str) -> list[str]:
        response = self._request("GET", f"/user/{username}/")
        if response.status_code == 404:
            raise UserNotFoundError("pypi", username)
        self._ensure_success(response, "failed to fetch PyPI profile")
        if self._is_client_challenge(response.text):
            return self._get_projects_xmlrpc(username)
        return self.parse_projects(response.text)

    def _get_projects_xmlrpc(self, username: str) -> list[str]:
        request_body = xmlrpc.client.dumps(
            (username,),
            methodname="user_packages",
            allow_none=False,
        )
        response = self._request(
            "POST",
            "/pypi",
            headers={"Content-Type": "text/xml"},
            data=request_body,
        )
        self._ensure_success(response, "failed to fetch PyPI projects")

        try:
            params, _ = xmlrpc.client.loads(response.text)
            roles = params[0]
            return sorted({entry[1] for entry in roles})
        except (ExpatError, IndexError, TypeError, xmlrpc.client.Error) as exc:
            raise UpstreamServiceError(
                "pypi",
                f"invalid response from PyPI user_packages: {exc}",
            ) from exc

    def parse_projects(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup

        project_names: set[str]
        projects_section = self._find_section(main, "projects")
        if projects_section is not None:
            project_names = self._extract_project_links(projects_section)
        else:
            project_names = self._extract_project_links(main)

        archived_section = self._find_section(main, "archived projects")
        if archived_section is not None:
            project_names -= self._extract_project_links(archived_section)

        return sorted(project_names)

    @staticmethod
    def _is_client_challenge(html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True).casefold() if soup.title else ""
        return title == "client challenge" or soup.find(
            lambda tag: (
                isinstance(tag, Tag)
                and tag.name in {"script", "link"}
                and any(
                    value.startswith("/_fs-ch-")
                    for attribute in ("src", "href")
                    for value in [tag.get(attribute)]
                    if isinstance(value, str)
                )
            )
        ) is not None

    def _find_section(self, root: Tag, heading_text: str) -> Tag | None:
        target = heading_text.casefold()
        for heading in root.find_all(re.compile(r"^h[1-6]$")):
            text = " ".join(heading.get_text(" ", strip=True).split()).casefold()
            if text == target:
                return heading.find_parent("section") or heading.parent
        return None

    def _extract_project_links(self, node: Tag) -> set[str]:
        names: set[str] = set()
        for link in node.find_all("a", href=True):
            parsed = urlparse(link["href"])
            match = PROJECT_PATH_RE.match(parsed.path)
            if match:
                names.add(match.group(1))
        return names

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers = {"User-Agent": "maintainer-for-lambda"}
        headers.update(kwargs.pop("headers", {}))
        try:
            return self.requestor(method, url, headers=headers, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise UpstreamServiceError("pypi", f"PyPI request failed: {exc}") from exc

    @staticmethod
    def _ensure_success(response: requests.Response, message: str) -> None:
        if 200 <= response.status_code < 300:
            return
        raise UpstreamServiceError("pypi", f"{message} (status {response.status_code})")
