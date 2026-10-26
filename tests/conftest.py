from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from datamasque.client.models.project import Project, ProjectId
from datamasque.client.models.ruleset import RulesetType
from typer.testing import CliRunner

from datamasque_cli.config import Config, Profile


@pytest.fixture(autouse=True)
def _force_human_output_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default tests to human-readable output mode.

    Tests run under capsys so stdout is not a TTY, which would otherwise
    trip the agent-context auto-detection in `output.is_agent_context()`.
    Tests that exercise JSON / agent-mode behaviour override this with
    `monkeypatch.setenv("DM_OUTPUT", "json")` (or pass `is_json=True`).
    """
    monkeypatch.setenv("DM_OUTPUT", "table")
    monkeypatch.delenv("AI_AGENT", raising=False)


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def mock_client() -> MagicMock:
    """Pre-configured mock with one project, two connections and one ruleset, all in `Default`."""
    client = with_projects(MagicMock())
    client.list_connections.return_value = [
        SimpleNamespace(id=1, name="my_conn", mask_type="database", project=DEFAULT_PROJECT_REFERENCE),
        SimpleNamespace(id=2, name="other_conn", mask_type="database", project=DEFAULT_PROJECT_REFERENCE),
    ]
    client.list_rulesets.return_value = [
        SimpleNamespace(
            id=10, name="my_ruleset", ruleset_type=RulesetType.database, yaml="", project=DEFAULT_PROJECT_REFERENCE
        ),
    ]
    return client


DEFAULT_PROJECT_REFERENCE = "1-default"


def make_project(project_id: int = 1, name: str = "Default") -> Project:
    """A project as `list_projects` returns it, with the `<id>-<slug>` reference the server derives from its name."""
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    return Project(
        id=ProjectId(project_id),
        reference=f"{project_id}-{name.lower()}",
        name=name,
        created=stamp,
        updated=stamp,
    )


def with_projects(client: MagicMock, *projects: Project) -> MagicMock:
    """Make `client.list_projects` return `projects`, or just `Default` when none are given."""
    client.list_projects.return_value = list(projects) or [make_project()]
    return client


def make_api_response(data: Any, *, is_ok: bool = True) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.ok = is_ok
    return resp


def make_config(
    name: str = "default",
    url: str = "https://dm.example.com",
    username: str = "admin",
    password: str = "secret",
) -> Config:
    config = Config()
    config.set_profile(name, Profile(url=url, username=username, password=password))
    config.active_profile = name
    return config
