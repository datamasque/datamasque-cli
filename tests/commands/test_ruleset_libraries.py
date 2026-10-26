from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ruleset import RulesetType
from datamasque.client.models.status import ValidationErrorDetails, ValidationStatus
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.conftest import DEFAULT_PROJECT_REFERENCE, make_project, with_projects

MODULE = "datamasque_cli.commands.ruleset_libraries"


def _make_ruleset_library(
    name: str,
    project: str = DEFAULT_PROJECT_REFERENCE,
    library_id: str = "lib-uuid",
    is_valid: ValidationStatus | None = None,
    validation_errors: list[ValidationErrorDetails] | None = None,
    yaml: str = "",
) -> SimpleNamespace:
    """A ruleset library as the server returns it, carrying its validation status."""
    return SimpleNamespace(
        id=library_id,
        name=name,
        project=project,
        is_valid=is_valid,
        validation_errors=validation_errors or [],
        yaml=yaml,
        created=None,
        modified=None,
    )


ORG = make_project(2, "Org")
ORG_REFERENCE = ORG.reference


def _given_libraries(client: MagicMock, *libraries: SimpleNamespace) -> None:
    """Make the mock serve `libraries` from the listing and, by id, with their YAML, in `Default` and `Org`."""
    with_projects(client, make_project(), ORG)
    client.list_ruleset_libraries.return_value = list(libraries)
    client.get_ruleset_library.side_effect = lambda library_id: next(lib for lib in libraries if lib.id == library_id)


@patch(f"{MODULE}.get_client")
def test_list_project_keeps_only_that_projects_libraries(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(
        client,
        _make_ruleset_library("finance", library_id="default-lib"),
        _make_ruleset_library("payroll", project=ORG_REFERENCE, library_id="org-lib"),
    )

    result = runner.invoke(app, ["libraries", "list", "--project", "org", "--json"])

    assert result.exit_code == 0
    assert [lib["name"] for lib in json.loads(result.stdout)] == ["payroll"]


@patch(f"{MODULE}.get_client")
def test_list_names_the_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, _make_ruleset_library("payroll", project=ORG_REFERENCE, library_id="org-lib"))

    result = runner.invoke(app, ["libraries", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"id": "org-lib", "project": "Org", "name": "payroll", "valid": "unknown"}]


@patch(f"{MODULE}.get_client")
def test_usage_names_each_rulesets_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, _make_ruleset_library("finance", library_id="lib-1"))
    client.list_rulesets_using_library.return_value = [
        SimpleNamespace(id="rs-1", name="customers", ruleset_type=RulesetType.database, project=ORG_REFERENCE)
    ]

    result = runner.invoke(app, ["libraries", "usage", "finance", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"id": "rs-1", "project": "Org", "name": "customers", "type": "database"}]


@patch(f"{MODULE}.get_client")
def test_get_yaml_fetches_the_named_projects_library(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(
        client,
        _make_ruleset_library("finance", library_id="default-lib", yaml="default: []\n"),
        _make_ruleset_library("finance", project=ORG_REFERENCE, library_id="org-lib", yaml="org: []\n"),
    )

    result = runner.invoke(app, ["libraries", "get", "finance", "--project", "Org", "--yaml"])

    assert result.exit_code == 0
    assert result.stdout == "org: []\n\n"
    client.get_ruleset_library.assert_called_once_with("org-lib")


@patch(f"{MODULE}.get_client")
def test_get_name_in_two_projects_asks_for_the_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(
        client,
        _make_ruleset_library("finance", library_id="default-lib"),
        _make_ruleset_library("finance", project=ORG_REFERENCE, library_id="org-lib"),
    )

    result = runner.invoke(app, ["libraries", "get", "finance"])

    assert result.exit_code == ExitCode.AMBIGUOUS
    assert result.stderr == (
        "Error: Library 'finance' exists in more than one project:\n"
        "  project=Default\n"
        "  project=Org\n"
        "Hint: Pass --project to disambiguate.\n"
    )
    client.get_ruleset_library.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_sends_the_named_project(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client)
    lib = tmp_path / "lib.yaml"
    lib.write_text("version: '1.0'\n")

    result = runner.invoke(app, ["libraries", "create", "--name", "finance", "--project", "Org", "-f", str(lib)])

    assert result.exit_code == 0
    created = client.create_or_update_ruleset_library.call_args.args[0]
    assert created.name == "finance"
    assert created.project == ORG_REFERENCE


@patch(f"{MODULE}.get_client")
def test_delete_in_use_reports_server_reason(mock_get_client: MagicMock, runner: CliRunner) -> None:
    """A 409 must surface the server's explanation, not a traceback.

    The server refuses to delete a library that active rulesets still import, and
    its `detail` names the count. Without handling, the raised `DataMasqueApiError`
    escapes as an unhandled exception and the user only sees a stack trace.
    """
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, _make_ruleset_library("lib"))
    response = MagicMock()
    response.status_code = HTTPStatus.CONFLICT
    response.json.return_value = {
        "detail": 'Cannot delete library "lib": used by 3 active ruleset(s)',
        "rulesets": [{"id": "rs-1", "name": "customers"}],
    }
    client.delete_ruleset_library_by_id_if_exists.side_effect = DataMasqueApiError(
        "API request to https://dm/api/ruleset-libraries/lib-uuid/ failed with status 409", response=response
    )

    result = runner.invoke(app, ["libraries", "delete", "lib", "--yes"])

    assert result.exit_code == ExitCode.CONFLICT
    assert "used by 3 active ruleset(s)" in result.stderr
    assert "--force" in result.stderr


@patch(f"{MODULE}.get_client")
def test_delete_library_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client)

    result = runner.invoke(app, ["libraries", "delete", "nope", "--yes"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.delete_ruleset_library_by_id_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_library_proceeds_when_present(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, SimpleNamespace(id=1, name="lib", project=DEFAULT_PROJECT_REFERENCE))

    result = runner.invoke(app, ["libraries", "delete", "lib", "--yes"])

    assert result.exit_code == 0
    client.delete_ruleset_library_by_id_if_exists.assert_called_once_with(1, force=False)


@patch(f"{MODULE}.get_client")
def test_validate_library_reports_status(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, _make_ruleset_library("my-lib"))
    client.validate_ruleset_library.return_value = _make_ruleset_library("my-lib", is_valid=ValidationStatus.valid)

    result = runner.invoke(app, ["libraries", "validate", "my-lib"])

    assert result.exit_code == 0
    client.validate_ruleset_library.assert_called_once_with("lib-uuid")
    assert "valid" in result.stderr


@patch(f"{MODULE}.get_client")
def test_validate_library_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client)

    result = runner.invoke(app, ["libraries", "validate", "missing"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.validate_ruleset_library.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_library_invalid_prints_errors_and_exits_4(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, _make_ruleset_library("my-lib"))
    client.validate_ruleset_library.return_value = _make_ruleset_library(
        "my-lib",
        is_valid=ValidationStatus.invalid,
        validation_errors=[
            ValidationErrorDetails(message="unknown mask type 'from_nowhere'", line_number=3),
            ValidationErrorDetails(message="duplicate anchor 'email'", line_number=None),
        ],
    )

    result = runner.invoke(app, ["libraries", "validate", "my-lib"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "unknown mask type 'from_nowhere'" in result.stderr
    assert "line 3" in result.stderr
    assert "duplicate anchor 'email'" in result.stderr


@patch(f"{MODULE}.get_client")
def test_validate_library_puts_every_reason_in_the_agent_envelope(
    mock_get_client: MagicMock, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, _make_ruleset_library("my-lib"))
    client.validate_ruleset_library.return_value = _make_ruleset_library(
        "my-lib",
        is_valid=ValidationStatus.invalid,
        validation_errors=[
            ValidationErrorDetails(message="unknown mask type 'from_nowhere'", line_number=3, column_number=5),
            ValidationErrorDetails(message="duplicate anchor 'email'"),
        ],
    )

    result = runner.invoke(app, ["libraries", "validate", "my-lib"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "invalid_input"
    assert payload["error"]["message"] == (
        "Library 'my-lib' is invalid: unknown mask type 'from_nowhere' (line 3, column 5); duplicate anchor 'email'"
    )


@patch(f"{MODULE}.get_client")
def test_validate_library_nonterminal_status_passes_through(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, _make_ruleset_library("my-lib"))
    client.validate_ruleset_library.return_value = _make_ruleset_library(
        "my-lib", is_valid=ValidationStatus.in_progress
    )

    result = runner.invoke(app, ["libraries", "validate", "my-lib"])

    assert result.exit_code == 0
    assert "in_progress" in result.stderr


@pytest.mark.parametrize(
    ("is_valid", "errors"),
    [
        (ValidationStatus.valid, []),
        (
            ValidationStatus.invalid,
            [ValidationErrorDetails(message="Unknown mask `nope`.")],
        ),
    ],
    ids=["valid", "invalid"],
)
@patch(f"{MODULE}.get_client")
def test_status_reports_state(
    mock_get_client: MagicMock,
    runner: CliRunner,
    is_valid: ValidationStatus,
    errors: list[ValidationErrorDetails],
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    _given_libraries(client, _make_ruleset_library("lib", is_valid=is_valid, validation_errors=errors))

    result = runner.invoke(app, ["libraries", "status", "lib", "--json"])

    assert result.exit_code == ExitCode.OK
    assert f'"status": "{is_valid.value}"' in result.stdout
    for error in errors:
        assert error.message in result.stdout
