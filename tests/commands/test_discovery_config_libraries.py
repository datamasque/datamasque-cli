from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.status import ValidationStatus
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.conftest import DEFAULT_PROJECT_REFERENCE, make_project, with_projects

MODULE = "datamasque_cli.commands.discovery_config_libraries"


def _make_library(
    name: str,
    project: str = DEFAULT_PROJECT_REFERENCE,
    library_id: str = "lib-uuid",
    is_valid: ValidationStatus | None = ValidationStatus.valid,
    usage_count: int = 0,
    yaml: str | None = None,
    validation_error: str | None = None,
) -> SimpleNamespace:
    """A discovery config library as the server returns it, carrying its validation status."""
    return SimpleNamespace(
        id=library_id,
        name=name,
        project=project,
        is_valid=is_valid,
        validation_error=validation_error,
        usage_count=usage_count,
        created=None,
        modified=None,
        yaml=yaml,
    )


ORG = make_project(2, "Org")
ORG_REFERENCE = ORG.reference


def _given_libraries(client: MagicMock, *libraries: SimpleNamespace) -> None:
    """Make the mock serve `libraries` from the listing and, by id, with their YAML, in `Default` and `Org`."""
    with_projects(client, make_project(), ORG)
    client.list_discovery_config_libraries.return_value = list(libraries)
    client.get_discovery_config_library.side_effect = lambda library_id: next(
        lib for lib in libraries if lib.id == library_id
    )


@patch(f"{MODULE}.get_client")
def test_list_shows_project_and_usage(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(client, _make_library("finance", project=ORG_REFERENCE, usage_count=3))

    result = runner.invoke(app, ["discover", "libraries", "list", "--json"])

    assert result.exit_code == 0
    assert '"finance"' in result.stdout
    assert '"project": "Org"' in result.stdout
    assert '"used_by": 3' in result.stdout


@patch(f"{MODULE}.get_client")
def test_list_project_keeps_only_that_projects_libraries(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(
        client,
        _make_library("finance", library_id="default-lib"),
        _make_library("payroll", project=ORG_REFERENCE, library_id="org-lib"),
    )

    result = runner.invoke(app, ["discover", "libraries", "list", "--project", "org", "--json"])

    assert result.exit_code == 0
    assert '"payroll"' in result.stdout
    assert '"finance"' not in result.stdout


@patch(f"{MODULE}.get_client")
def test_get_yaml_fetches_the_named_projects_library(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(
        client,
        _make_library("finance", library_id="default-lib", yaml="default: []\n"),
        _make_library("finance", project=ORG_REFERENCE, library_id="org-lib", yaml="labels: []\n"),
    )

    result = runner.invoke(app, ["discover", "libraries", "get", "finance", "--project", "Org", "--yaml"])

    assert result.exit_code == 0
    assert "labels: []" in result.stdout
    client.get_discovery_config_library.assert_called_once_with("org-lib")


@patch(f"{MODULE}.get_client")
def test_get_name_in_two_projects_asks_for_the_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(
        client,
        _make_library("finance", library_id="default-lib"),
        _make_library("finance", project=ORG_REFERENCE, library_id="org-lib"),
    )

    result = runner.invoke(app, ["discover", "libraries", "get", "finance"])

    assert result.exit_code == ExitCode.AMBIGUOUS
    assert result.stderr == (
        "Error: Discovery config library 'finance' exists in more than one project:\n"
        "  project=Default\n"
        "  project=Org\n"
        "Hint: Pass --project to disambiguate.\n"
    )
    client.get_discovery_config_library.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_get_unknown_name_is_not_found(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(client)

    result = runner.invoke(app, ["discover", "libraries", "get", "finance"])

    assert result.exit_code == ExitCode.NOT_FOUND


@patch(f"{MODULE}.get_client")
def test_get_unknown_project_is_not_found(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(client, _make_library("finance"))

    result = runner.invoke(app, ["discover", "libraries", "get", "finance", "--project", "nope"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "Project 'nope' not found" in result.stderr


@patch(f"{MODULE}.get_client")
def test_create_posts_library(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = with_projects(MagicMock(), make_project(), ORG)
    mock_get_client.return_value = client
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(
        app,
        ["discover", "libraries", "create", "--name", "finance", "--project", "Org", "-f", str(lib)],
    )

    assert result.exit_code == 0
    client.create_or_update_discovery_config_library.assert_called_once()
    created = client.create_or_update_discovery_config_library.call_args.args[0]
    assert created.name == "finance"
    assert created.project == ORG_REFERENCE


@patch(f"{MODULE}.get_client")
def test_delete_force_passes_through(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(client, _make_library("finance", project=ORG_REFERENCE, library_id="org-lib"))

    result = runner.invoke(app, ["discover", "libraries", "delete", "finance", "--project", "Org", "--force", "--yes"])

    assert result.exit_code == 0
    client.delete_discovery_config_library_by_id_if_exists.assert_called_once_with("org-lib", force=True)


@patch(f"{MODULE}.get_client")
def test_delete_in_use_reports_server_reason(mock_get_client: MagicMock, runner: CliRunner) -> None:
    """A 409 must surface the server's explanation, not a traceback.

    The server refuses to delete a library that active configs still import, and
    its `detail` names the count. Without handling, the raised `DataMasqueApiError`
    escapes as an unhandled exception and the user only sees a stack trace.
    """
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(client, _make_library("finance"))
    response = MagicMock()
    response.status_code = HTTPStatus.CONFLICT
    response.json.return_value = {
        "detail": 'Cannot delete library "finance": used by 2 active config(s)',
        "configs": [{"id": "cfg-1", "name": "employees"}],
    }
    client.delete_discovery_config_library_by_id_if_exists.side_effect = DataMasqueApiError(
        "API request to https://dm/api/discovery/config-libraries/lib-uuid/ failed with status 409",
        response=response,
    )

    result = runner.invoke(app, ["discover", "libraries", "delete", "finance", "--yes"])

    assert result.exit_code == ExitCode.CONFLICT
    assert "used by 2 active config(s)" in result.stderr
    assert "--force" in result.stderr


@patch(f"{MODULE}.get_client")
def test_delete_other_api_error_is_generic_failure(mock_get_client: MagicMock, runner: CliRunner) -> None:
    """Non-409 API failures still abort cleanly rather than raising."""
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(client, _make_library("finance"))
    response = MagicMock()
    response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    response.json.side_effect = ValueError("no body")
    client.delete_discovery_config_library_by_id_if_exists.side_effect = DataMasqueApiError(
        "API request failed with status 500", response=response
    )

    result = runner.invoke(app, ["discover", "libraries", "delete", "finance", "--yes"])

    assert result.exit_code == ExitCode.ERROR
    assert "Failed to delete discovery config library 'finance'" in result.stderr


@patch(f"{MODULE}.get_client")
def test_delete_missing_is_not_found(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(client)

    result = runner.invoke(app, ["discover", "libraries", "delete", "finance", "--yes"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.delete_discovery_config_library_by_id_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_empty_file_aborts_before_any_request(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    lib = tmp_path / "empty.yaml"
    lib.write_text("")

    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(lib)])

    assert result.exit_code == ExitCode.INVALID_INPUT
    mock_get_client.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_reports_valid(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_discovery_config_library.return_value = _make_library("finance", is_valid=ValidationStatus.valid)
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(lib)])

    assert result.exit_code == 0
    assert "valid" in result.stderr
    created = client.create_discovery_config_library.call_args.args[0]
    assert created.name.startswith("__dm_cli_validate_")
    assert created.yaml == "labels: []\n"
    client.delete_discovery_config_library_by_id_if_exists.assert_called_once_with("lib-uuid")


@patch(f"{MODULE}.get_client")
def test_validate_rejected_create_aborts_without_delete(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    response = MagicMock()
    response.status_code = HTTPStatus.BAD_REQUEST
    response.json.return_value = {"detail": "config_yaml: invalid"}
    client.create_discovery_config_library.side_effect = DataMasqueApiError(
        "API request failed with status 400", response=response
    )
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(lib)])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "config_yaml: invalid" in " ".join(result.stderr.split())
    client.delete_discovery_config_library_by_id_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_invalid_exits_4(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_discovery_config_library.return_value = _make_library(
        "finance", is_valid=ValidationStatus.invalid, validation_error="duplicate label 'email'"
    )
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(lib)])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "duplicate label 'email'" in result.stderr
    client.delete_discovery_config_library_by_id_if_exists.assert_called_once_with("lib-uuid")


@patch(f"{MODULE}.get_client")
def test_validate_puts_the_reason_in_the_agent_envelope(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_discovery_config_library.return_value = _make_library(
        "finance", is_valid=ValidationStatus.invalid, validation_error="duplicate label 'email'"
    )
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(lib)])

    assert result.exit_code == ExitCode.INVALID_INPUT
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "invalid_input"
    assert payload["error"]["message"] == ('Discovery config library "lib.yaml" is invalid: duplicate label \'email\'')


@patch(f"{MODULE}.get_client")
def test_validate_warns_when_temp_library_cleanup_fails(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_discovery_config_library.return_value = _make_library("finance", is_valid=ValidationStatus.valid)
    client.delete_discovery_config_library_by_id_if_exists.side_effect = DataMasqueApiError(
        "boom", response=MagicMock()
    )
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(lib)])

    assert result.exit_code == 0
    assert "left on server" in result.stderr


@pytest.mark.parametrize(
    ("is_valid", "validation_error"),
    [
        (ValidationStatus.valid, None),
        (ValidationStatus.invalid, "duplicate label 'email'"),
    ],
    ids=["valid", "invalid"],
)
@patch(f"{MODULE}.get_client")
def test_status_reports_state(
    mock_get_client: MagicMock,
    runner: CliRunner,
    is_valid: ValidationStatus,
    validation_error: str | None,
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    _given_libraries(client, _make_library("finance", is_valid=is_valid, validation_error=validation_error))

    result = runner.invoke(app, ["discover", "libraries", "status", "finance", "--json"])

    assert result.exit_code == ExitCode.OK
    assert f'"status": "{is_valid.value}"' in result.stdout
    if validation_error:
        assert validation_error in result.stdout
