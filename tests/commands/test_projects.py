from __future__ import annotations

import json
from collections.abc import Iterator
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import DataMasqueApiError, ProjectDeleteConflictError
from datamasque.client.models.project import (
    ProjectCreateRequest,
    ProjectDeleteConflict,
    ProjectDeleteConflictReason,
    ProjectUpdateRequest,
)
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.conftest import make_api_response, make_project, with_projects

MODULE = "datamasque_cli.commands.projects"

DEFAULT = make_project(1, "Default")
FINANCE = make_project(2, "Finance")
OLD = make_project(3, "Old")

NAME_CLASH = ProjectDeleteConflict(
    reason=ProjectDeleteConflictReason.name_in_use,
    detail='Ruleset "customers" exists.',
)

CONFLICT_ERROR = (
    'Error: The project\'s resources cannot move to the destination project:\n  Ruleset "customers" exists.\n'
)


def _api_error(status: HTTPStatus, detail: str) -> DataMasqueApiError:
    response = make_api_response({"detail": detail}, is_ok=False)
    response.status_code = status
    return DataMasqueApiError(detail, response=response)


@pytest.fixture()
def client() -> Iterator[MagicMock]:
    client = with_projects(MagicMock(), DEFAULT, FINANCE)
    with patch(f"{MODULE}.get_client", return_value=client):
        yield client


def test_list_shows_the_active_projects(client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["projects", "list", "--json"])

    assert result.exit_code == 0
    assert [(p["id"], p["name"]) for p in json.loads(result.stdout)] == [(1, "Default"), (2, "Finance")]
    client.list_projects.assert_called_once_with()


def test_list_include_deleted_marks_the_deleted_projects(client: MagicMock, runner: CliRunner) -> None:
    client.list_projects.side_effect = lambda include_archived=False: (
        [DEFAULT, FINANCE, OLD] if include_archived else [DEFAULT, FINANCE]
    )

    result = runner.invoke(app, ["projects", "list", "--include-deleted", "--json"])

    assert result.exit_code == 0
    assert [(p["name"], p["deleted"]) for p in json.loads(result.stdout)] == [
        ("Default", False),
        ("Finance", False),
        ("Old", True),
    ]


@pytest.mark.parametrize("given", ["finance", "2"])
def test_get_finds_a_project_by_name_in_any_case_or_by_id(client: MagicMock, runner: CliRunner, given: str) -> None:
    result = runner.invoke(app, ["projects", "get", given, "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["name"] == "Finance"


def test_get_of_an_unknown_project_is_not_found(client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["projects", "get", "nope"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert result.stderr == "Error: Project 'nope' not found.\n"


def test_create_sends_the_name_and_description(client: MagicMock, runner: CliRunner) -> None:
    client.create_project.return_value = make_project(4, "Sales")

    result = runner.invoke(app, ["projects", "create", "--name", "Sales", "--description", "Sales team"])

    assert result.exit_code == 0
    client.create_project.assert_called_once_with(ProjectCreateRequest(name="Sales", description="Sales team"))


def test_create_rejected_by_the_server_shows_its_reason(client: MagicMock, runner: CliRunner) -> None:
    client.create_project.side_effect = _api_error(HTTPStatus.BAD_REQUEST, "Name in use.")

    result = runner.invoke(app, ["projects", "create", "--name", "finance"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert result.stderr == "Error: Failed to create project 'finance': Name in use.\n"


@pytest.mark.parametrize(
    ("options", "request_sent"),
    [
        (["--name", "Accounts"], ProjectUpdateRequest(name="Accounts")),
        (["--description", "Accounts team"], ProjectUpdateRequest(description="Accounts team")),
    ],
    ids=["name", "description"],
)
def test_update_sends_only_the_fields_given(
    client: MagicMock, runner: CliRunner, options: list[str], request_sent: ProjectUpdateRequest
) -> None:
    client.update_project.return_value = FINANCE

    result = runner.invoke(app, ["projects", "update", "finance", *options])

    assert result.exit_code == 0
    client.update_project.assert_called_once_with(FINANCE, request_sent)


def test_update_with_nothing_to_change_is_rejected_without_a_request(client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["projects", "update", "finance"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert result.stderr == "Error: Nothing to update.\nHint: Pass --name, --description or both.\n"
    client.update_project.assert_not_called()


def test_delete_moves_the_resources_to_the_destination(client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["projects", "delete", "finance", "--to", "default", "--yes"])

    assert result.exit_code == 0
    client.delete_project.assert_called_once_with(FINANCE, DEFAULT)
    client.get_project_delete_conflicts.assert_not_called()
    client.list_projects.assert_called_once_with()


def test_delete_refused_by_a_conflict_lists_it(client: MagicMock, runner: CliRunner) -> None:
    response = make_api_response({}, is_ok=False)
    response.status_code = HTTPStatus.CONFLICT
    client.delete_project.side_effect = ProjectDeleteConflictError(
        "conflict", response=response, conflicts=[NAME_CLASH]
    )

    result = runner.invoke(app, ["projects", "delete", "finance", "--to", "default", "--yes"])

    assert result.exit_code == ExitCode.CONFLICT
    assert result.stderr == CONFLICT_ERROR


def test_delete_declined_at_the_prompt_deletes_nothing(client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["projects", "delete", "finance", "--to", "default"], input="n\n")

    assert result.exit_code == ExitCode.CANCELLED
    client.delete_project.assert_not_called()


@pytest.mark.parametrize(
    ("conflicts", "exit_code", "stderr"),
    [
        ([], 0, "Project 'Finance' can be deleted, moving its resources to 'Default'.\n"),
        ([NAME_CLASH], ExitCode.CONFLICT, CONFLICT_ERROR),
    ],
    ids=["no-conflicts", "conflict"],
)
def test_delete_check_reports_the_conflicts_without_deleting(
    client: MagicMock,
    runner: CliRunner,
    conflicts: list[ProjectDeleteConflict],
    exit_code: int,
    stderr: str,
) -> None:
    client.get_project_delete_conflicts.return_value = conflicts

    result = runner.invoke(app, ["projects", "delete", "finance", "--to", "default", "--check"])

    assert result.exit_code == exit_code
    assert result.stderr == stderr
    client.get_project_delete_conflicts.assert_called_once_with(FINANCE, DEFAULT)
    client.delete_project.assert_not_called()
