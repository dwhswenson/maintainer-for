from __future__ import annotations

import xmlrpc.client
from pathlib import Path
from unittest import TestCase

import requests

from maintainer_for.errors import UpstreamServiceError, UserNotFoundError
from maintainer_for.pypi_client import PyPIClient


class FakeResponse:
    def __init__(self, status_code: int, *, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class PyPIClientTests(TestCase):
    def test_live_profile_for_dwhswenson_returns_multiple_packages(self) -> None:
        try:
            requests.get("https://pypi.org/simple/", timeout=5.0)
        except requests.RequestException as exc:
            self.skipTest(f"PyPI is unreachable from this environment: {exc}")

        client = PyPIClient(timeout=10.0)

        projects = client.get_projects("dwhswenson")

        self.assertGreater(len(projects), 1)

    def test_parses_projects_and_excludes_archived_projects(self) -> None:
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "pypi_profile.html"
        html = fixture_path.read_text()
        client = PyPIClient()

        projects = client.parse_projects(html)

        self.assertEqual(projects, ["alpha", "bravo", "charlie"])

    def test_falls_back_to_xmlrpc_when_pypi_returns_client_challenge(self) -> None:
        responses = [
            FakeResponse(
                200,
                text=(
                    "<html><head><title>Client Challenge</title>"
                    '<script src="/_fs-ch-example/script.js"></script>'
                    "</head></html>"
                ),
            ),
            FakeResponse(
                200,
                text=xmlrpc.client.dumps(
                    (
                        [
                            ["Owner", "charlie"],
                            ["Maintainer", "alpha"],
                            ["Owner", "charlie"],
                        ],
                    ),
                    methodresponse=True,
                ),
            ),
        ]
        calls = []

        def requestor(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return responses.pop(0)

        client = PyPIClient(requestor=requestor)

        projects = client.get_projects("alice")

        self.assertEqual(projects, ["alpha", "charlie"])
        self.assertEqual(calls[0][0:2], ("GET", "https://pypi.org/user/alice/"))
        self.assertEqual(calls[1][0:2], ("POST", "https://pypi.org/pypi"))
        self.assertEqual(calls[1][2]["headers"]["Content-Type"], "text/xml")
        self.assertIn("<methodName>user_packages</methodName>", calls[1][2]["data"])
        self.assertIn("<string>alice</string>", calls[1][2]["data"])

    def test_raises_upstream_error_for_invalid_xmlrpc_response(self) -> None:
        responses = [
            FakeResponse(200, text="<title>Client Challenge</title>"),
            FakeResponse(200, text="not XML"),
        ]

        def requestor(method, url, **kwargs):
            return responses.pop(0)

        client = PyPIClient(requestor=requestor)

        with self.assertRaises(UpstreamServiceError):
            client.get_projects("alice")

    def test_raises_user_not_found_for_missing_profile(self) -> None:
        def requestor(method, url, **kwargs):
            return FakeResponse(404, text="")

        client = PyPIClient(requestor=requestor)

        with self.assertRaises(UserNotFoundError):
            client.get_projects("missing-user")
