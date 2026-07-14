from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lambda" / "src"))

from errors import UserNotFoundError
from pypi_client import PyPIClient


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

    def test_raises_user_not_found_for_missing_profile(self) -> None:
        def requestor(method, url, **kwargs):
            return FakeResponse(404, text="")

        client = PyPIClient(requestor=requestor)

        with self.assertRaises(UserNotFoundError):
            client.get_projects("missing-user")
