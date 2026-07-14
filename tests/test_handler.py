from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lambda" / "src"))

import handler
from errors import UpstreamServiceError, UserNotFoundError


class HandlerTests(TestCase):
    @patch("handler.PyPIClient")
    @patch("handler.GitHubClient")
    def test_returns_400_when_query_params_are_missing(self, github_client_cls, pypi_client_cls) -> None:
        response = handler.lambda_handler({}, None)

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(
            json.loads(response["body"]),
            {"error": "missing required query parameter: github_username"},
        )
        github_client_cls.assert_not_called()
        pypi_client_cls.assert_not_called()

    @patch("handler.PyPIClient")
    @patch("handler.GitHubClient")
    def test_returns_400_when_query_param_is_blank(self, github_client_cls, pypi_client_cls) -> None:
        response = handler.lambda_handler(
            {"queryStringParameters": {"github_username": "alice", "pypi_username": "   "}},
            None,
        )

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(
            json.loads(response["body"]),
            {"error": "missing required query parameter: pypi_username"},
        )
        github_client_cls.assert_not_called()
        pypi_client_cls.assert_not_called()

    @patch("handler.PyPIClient")
    @patch("handler.GitHubClient")
    def test_returns_combined_success_payload(self, github_client_cls, pypi_client_cls) -> None:
        github_client_cls.return_value.get_conda_forge_projects.return_value = ["alpha-feedstock", "beta-feedstock"]
        pypi_client_cls.return_value.get_projects.return_value = ["package-a", "package-b"]

        response = handler.lambda_handler(
            {"queryStringParameters": {"github_username": "alice", "pypi_username": "alice-pypi"}},
            None,
        )

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            json.loads(response["body"]),
            {
                "pypi": {"username": "alice-pypi", "projects": ["package-a", "package-b"]},
                "condaforge": {"username": "alice", "projects": ["alpha-feedstock", "beta-feedstock"]},
            },
        )

    @patch("handler.PyPIClient")
    @patch("handler.GitHubClient")
    def test_returns_empty_condaforge_projects_for_valid_user_without_memberships(
        self,
        github_client_cls,
        pypi_client_cls,
    ) -> None:
        github_client_cls.return_value.get_conda_forge_projects.return_value = []
        pypi_client_cls.return_value.get_projects.return_value = ["package-a"]

        response = handler.lambda_handler(
            {"queryStringParameters": {"github_username": "alice", "pypi_username": "alice-pypi"}},
            None,
        )

        self.assertEqual(response["statusCode"], 200)
        payload = json.loads(response["body"])
        self.assertEqual(payload["condaforge"]["projects"], [])

    @patch("handler.PyPIClient")
    @patch("handler.GitHubClient")
    def test_returns_404_for_missing_github_user(self, github_client_cls, pypi_client_cls) -> None:
        github_client_cls.return_value.get_conda_forge_projects.side_effect = UserNotFoundError("github", "missing-user")

        response = handler.lambda_handler(
            {"queryStringParameters": {"github_username": "missing-user", "pypi_username": "alice-pypi"}},
            None,
        )

        self.assertEqual(response["statusCode"], 404)
        self.assertEqual(
            json.loads(response["body"]),
            {
                "error": {
                    "source": "github",
                    "username": "missing-user",
                    "message": "github user not found: missing-user",
                }
            },
        )
        pypi_client_cls.return_value.get_projects.assert_not_called()

    @patch("handler.PyPIClient")
    @patch("handler.GitHubClient")
    def test_returns_404_for_missing_pypi_user(self, github_client_cls, pypi_client_cls) -> None:
        github_client_cls.return_value.get_conda_forge_projects.return_value = ["alpha-feedstock"]
        pypi_client_cls.return_value.get_projects.side_effect = UserNotFoundError("pypi", "missing-pypi")

        response = handler.lambda_handler(
            {"queryStringParameters": {"github_username": "alice", "pypi_username": "missing-pypi"}},
            None,
        )

        self.assertEqual(response["statusCode"], 404)
        self.assertEqual(
            json.loads(response["body"]),
            {
                "error": {
                    "source": "pypi",
                    "username": "missing-pypi",
                    "message": "pypi user not found: missing-pypi",
                }
            },
        )

    @patch("handler.PyPIClient")
    @patch("handler.GitHubClient")
    def test_returns_502_for_upstream_failure(self, github_client_cls, pypi_client_cls) -> None:
        github_client_cls.return_value.get_conda_forge_projects.side_effect = UpstreamServiceError(
            "github",
            "GitHub request failed: timed out",
        )

        response = handler.lambda_handler(
            {"queryStringParameters": {"github_username": "alice", "pypi_username": "alice-pypi"}},
            None,
        )

        self.assertEqual(response["statusCode"], 502)
        self.assertEqual(
            json.loads(response["body"]),
            {
                "error": {
                    "source": "github",
                    "message": "GitHub request failed: timed out",
                }
            },
        )
