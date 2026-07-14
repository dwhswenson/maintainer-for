from __future__ import annotations

import argparse
import json
import sys
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
        payload = get_projects_by_source(
            github_username=github_username,
            pypi_username=pypi_username,
            github_client=github_client,
            pypi_client=pypi_client,
        )
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

    return _json_response(200, payload)


def get_projects_by_source(
    *,
    github_username: str | None = None,
    pypi_username: str | None = None,
    github_client: GitHubClient | None = None,
    pypi_client: PyPIClient | None = None,
) -> dict[str, dict[str, Any]]:
    if not github_username and not pypi_username:
        raise ValueError("at least one username must be provided")

    payload: dict[str, dict[str, Any]] = {}

    if github_username:
        client = github_client or GitHubClient()
        payload["condaforge"] = {
            "username": github_username,
            "projects": client.get_conda_forge_projects(github_username),
        }

    if pypi_username:
        client = pypi_client or PyPIClient()
        payload["pypi"] = {
            "username": pypi_username,
            "projects": client.get_projects(pypi_username),
        }

    return payload


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List conda-forge and/or PyPI projects maintained by a user.",
    )
    parser.add_argument("--github", help="GitHub username to query against conda-forge teams")
    parser.add_argument("--pypi", help="PyPI username to query for maintained projects")

    args = parser.parse_args(argv)

    if not args.github and not args.pypi:
        parser.error("at least one of --github or --pypi is required")

    try:
        payload = get_projects_by_source(
            github_username=args.github,
            pypi_username=args.pypi,
        )
    except UserNotFoundError as exc:
        print(f"{exc.source} user not found: {exc.username}", file=sys.stderr)
        return 1
    except UpstreamServiceError as exc:
        print(f"{exc.source} error: {exc.message}", file=sys.stderr)
        return 1

    print(_format_cli_output(payload))
    return 0


def _format_cli_output(payload: dict[str, dict[str, Any]]) -> str:
    sections: list[str] = []

    if "condaforge" in payload:
        sections.append(_format_section("GitHub", payload["condaforge"]))
    if "pypi" in payload:
        sections.append(_format_section("PyPI", payload["pypi"]))

    return "\n\n".join(sections)


def _format_section(title: str, entry: dict[str, Any]) -> str:
    username = entry["username"]
    projects = entry["projects"]
    lines = [f"{title} ({username})"]
    if projects:
        lines.extend(f"- {project}" for project in projects)
    else:
        lines.append("- none")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
