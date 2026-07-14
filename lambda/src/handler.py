from __future__ import annotations

import json
from typing import Any

from errors import UpstreamServiceError, UserNotFoundError
from github_client import GitHubClient
from pypi_client import PyPIClient


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        github_username, pypi_username = _parse_usernames(event)
    except ValueError as exc:
        return _json_response(400, {"error": str(exc)})

    github_client = GitHubClient()
    pypi_client = PyPIClient()

    try:
        conda_forge_projects = github_client.get_conda_forge_projects(github_username)
        pypi_projects = pypi_client.get_projects(pypi_username)
    except UserNotFoundError as exc:
        return _json_response(
            404,
            {
                "error": {
                    "source": exc.source,
                    "username": exc.username,
                    "message": str(exc),
                }
            },
        )
    except UpstreamServiceError as exc:
        return _json_response(
            502,
            {
                "error": {
                    "source": exc.source,
                    "message": exc.message,
                }
            },
        )

    return _json_response(
        200,
        {
            "pypi": {"username": pypi_username, "projects": pypi_projects},
            "condaforge": {"username": github_username, "projects": conda_forge_projects},
        },
    )


def _parse_usernames(event: dict[str, Any]) -> tuple[str, str]:
    params = event.get("queryStringParameters") or {}

    github_username = (params.get("github_username") or "").strip()
    pypi_username = (params.get("pypi_username") or "").strip()

    if not github_username:
        raise ValueError("missing required query parameter: github_username")
    if not pypi_username:
        raise ValueError("missing required query parameter: pypi_username")

    return github_username, pypi_username


def _json_response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }
