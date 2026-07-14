from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest import TestCase
from unittest.mock import patch

from maintainer_for import handler
from maintainer_for.errors import UpstreamServiceError, UserNotFoundError


class HandlerTests(TestCase):
    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
    def test_returns_400_when_query_params_are_missing(self, github_client_cls, pypi_client_cls) -> None:
        response = handler.lambda_handler({}, None)

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(
            json.loads(response["body"]),
            {"error": "missing required query parameter: github_username"},
        )
        github_client_cls.assert_not_called()
        pypi_client_cls.assert_not_called()

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
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

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
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

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
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

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
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

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
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

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
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

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
    def test_cli_prints_both_requested_sections(self, github_client_cls, pypi_client_cls) -> None:
        github_client_cls.return_value.get_conda_forge_projects.return_value = ["alpha-feedstock", "beta-feedstock"]
        pypi_client_cls.return_value.get_projects.return_value = ["package-a", "package-b"]
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = handler.main(["--github", "alice", "--pypi", "alice-pypi"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stdout.getvalue(),
            "conda-forge (alice)\n"
            "- alpha-feedstock\n"
            "- beta-feedstock\n\n"
            "PyPI (alice-pypi)\n"
            "- package-a\n"
            "- package-b\n",
        )

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
    def test_cli_accepts_single_source(self, github_client_cls, pypi_client_cls) -> None:
        pypi_client_cls.return_value.get_projects.return_value = ["package-a"]
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = handler.main(["--pypi", "alice-pypi"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "PyPI (alice-pypi)\n- package-a\n")
        github_client_cls.assert_not_called()

    def test_cli_requires_at_least_one_username(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exc:
                handler.main([])

        self.assertEqual(exc.exception.code, 2)
        self.assertIn("at least one of --github or --pypi is required", stderr.getvalue())

    @patch("maintainer_for.handler.PyPIClient")
    @patch("maintainer_for.handler.GitHubClient")
    def test_cli_reports_user_not_found(self, github_client_cls, pypi_client_cls) -> None:
        github_client_cls.return_value.get_conda_forge_projects.side_effect = UserNotFoundError("github", "missing")
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            exit_code = handler.main(["--github", "missing"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue(), "github user not found: missing\n")
