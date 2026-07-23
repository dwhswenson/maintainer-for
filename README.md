# maintainer-for

`maintainer-for` looks up conda-forge and PyPI projects maintained by a given user.

It requires Python 3.10 or newer.

```console
python -m pip install maintainer-for
```

## CLI Usage

Pass a GitHub username with `--github`, a PyPI username with `--pypi`, or both.
For example, to list the conda-forge projects maintained by `dwhswenson`:

```console
maintainer-for --github dwhswenson
```

Example output:

```text
conda-forge (dwhswenson)
- arsenic
- cinnabar
- codemodel
- contact_map
- gufe
- kartograf
- lomap2
- openfe
- openfe-analysis
- openpathsampling
- openpathsampling-cli
- pdbeccdutils
- pdbinf
- plugcli
```

The output above reflects the user's memberships when this README was written and
may change over time. A source for which the lookup returns no projects is
displayed as `- none`.

The conda-forge lookup uses the GitHub API. Set `GITHUB_TOKEN` or `GH_TOKEN`, or
authenticate with the GitHub CLI:

```console
gh auth login
```

The same username can be used for both sources:

```console
maintainer-for --github dwhswenson --pypi dwhswenson
```

Run `maintainer-for --help` for the complete command-line help.

## API Usage

Use `get_projects_by_source` to query one or both sources from Python:

```python
from maintainer_for.handler import get_projects_by_source

projects = get_projects_by_source(
    github_username="dwhswenson",
    pypi_username="dwhswenson",
)
```

The result is a dictionary grouped by source (project lists abbreviated here):

```python
{
    "condaforge": {
        "username": "dwhswenson",
        "projects": ["arsenic", "cinnabar", ...],
    },
    "pypi": {
        "username": "dwhswenson",
        "projects": ["autorelease", "codemodel", ...],
    },
}
```

Omit either username to query only the other source:

```python
conda_forge_projects = get_projects_by_source(
    github_username="dwhswenson",
)
```

For direct access or custom client settings, instantiate the source clients:

```python
from maintainer_for.github_client import GitHubClient
from maintainer_for.pypi_client import PyPIClient

github = GitHubClient(token="github-token", timeout=20.0)
pypi = PyPIClient(timeout=20.0)

conda_forge_projects = github.get_conda_forge_projects("dwhswenson")
pypi_projects = pypi.get_projects("dwhswenson")
```

Both client methods return sorted lists of project names. If no token is passed
to `GitHubClient`, it looks for `GITHUB_TOKEN`, then `GH_TOKEN`, and finally the
token from `gh auth token`.

Lookups can raise `UserNotFoundError` when a username does not exist or
`UpstreamServiceError` when GitHub or PyPI cannot complete the request:

```python
from maintainer_for.errors import UpstreamServiceError, UserNotFoundError
```
