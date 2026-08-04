from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.status import ValidationStatus
from typer.testing import CliRunner

from datamasque_cli.main import app
from datamasque_cli.output import ExitCode

MODULE = "datamasque_cli.commands.discovery_config_libraries"


def _make_library(
    name: str,
    namespace: str = "",
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
        namespace=namespace,
        is_valid=is_valid,
        validation_error=validation_error,
        usage_count=usage_count,
        created=None,
        modified=None,
        yaml=yaml,
    )


@patch(f"{MODULE}.get_client")
def test_list_shows_namespace_and_usage(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_config_libraries.return_value = [
        _make_library("finance", namespace="org", usage_count=3),
    ]

    result = runner.invoke(app, ["discover", "libraries", "list", "--json"])

    assert result.exit_code == 0
    assert '"finance"' in result.stdout
    assert '"org"' in result.stdout
    assert '"used_by": 3' in result.stdout


@patch(f"{MODULE}.get_client")
def test_get_yaml_fetches_full_library(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_discovery_config_library_by_name.return_value = _make_library(
        "finance", namespace="org", yaml="labels: []\n"
    )

    result = runner.invoke(app, ["discover", "libraries", "get", "finance", "--namespace", "org", "--yaml"])

    assert result.exit_code == 0
    assert "labels: []" in result.stdout
    client.get_discovery_config_library_by_name.assert_called_once_with("finance", "org")


@patch(f"{MODULE}.get_client")
def test_get_namespace_scopes_lookup(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_discovery_config_library_by_name.return_value = None

    result = runner.invoke(app, ["discover", "libraries", "get", "finance"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.get_discovery_config_library_by_name.assert_called_once_with("finance", "")


@patch(f"{MODULE}.get_client")
def test_create_posts_library(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(
        app,
        ["discover", "libraries", "create", "--name", "finance", "-n", "org", "-f", str(lib)],
    )

    assert result.exit_code == 0
    client.create_or_update_discovery_config_library.assert_called_once()
    created = client.create_or_update_discovery_config_library.call_args.args[0]
    assert created.name == "finance"
    assert created.namespace == "org"


@patch(f"{MODULE}.get_client")
def test_delete_force_passes_through(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_discovery_config_library_by_name.return_value = _make_library("finance", namespace="org")

    result = runner.invoke(app, ["discover", "libraries", "delete", "finance", "-n", "org", "--force", "--yes"])

    assert result.exit_code == 0
    client.delete_discovery_config_library_by_name_if_exists.assert_called_once_with("finance", "org", force=True)


@patch(f"{MODULE}.get_client")
def test_delete_in_use_reports_server_reason(mock_get_client: MagicMock, runner: CliRunner) -> None:
    """A 409 must surface the server's explanation, not a traceback.

    The server refuses to delete a library that active configs still import, and
    its `detail` names the count. Without handling, the raised `DataMasqueApiError`
    escapes as an unhandled exception and the user only sees a stack trace.
    """
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_discovery_config_library_by_name.return_value = _make_library("finance")
    response = MagicMock()
    response.status_code = HTTPStatus.CONFLICT
    response.json.return_value = {
        "detail": 'Cannot delete library "finance": used by 2 active config(s)',
        "configs": [{"id": "cfg-1", "name": "employees"}],
    }
    client.delete_discovery_config_library_by_name_if_exists.side_effect = DataMasqueApiError(
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
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_discovery_config_library_by_name.return_value = _make_library("finance")
    response = MagicMock()
    response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    response.json.side_effect = ValueError("no body")
    client.delete_discovery_config_library_by_name_if_exists.side_effect = DataMasqueApiError(
        "API request failed with status 500", response=response
    )

    result = runner.invoke(app, ["discover", "libraries", "delete", "finance", "--yes"])

    assert result.exit_code == ExitCode.ERROR
    assert "Failed to delete discovery config library 'finance'" in result.stderr


@patch(f"{MODULE}.get_client")
def test_delete_missing_is_not_found(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_discovery_config_library_by_name.return_value = None

    result = runner.invoke(app, ["discover", "libraries", "delete", "finance", "--yes"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.delete_discovery_config_library_by_name_if_exists.assert_not_called()


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
    client = MagicMock()
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
def test_validate_invalid_exits_4(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
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
def test_validate_warns_when_temp_library_cleanup_fails(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
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
    ("is_valid", "validation_error", "expected_exit"),
    [
        (ValidationStatus.valid, None, ExitCode.OK),
        (ValidationStatus.invalid, "duplicate label 'email'", ExitCode.INVALID_INPUT),
    ],
    ids=["valid", "invalid"],
)
@patch(f"{MODULE}.get_client")
def test_status_reports_state_and_exit_code(
    mock_get_client: MagicMock,
    runner: CliRunner,
    is_valid: ValidationStatus,
    validation_error: str | None,
    expected_exit: ExitCode,
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_discovery_config_library_by_name.return_value = _make_library(
        "finance", is_valid=is_valid, validation_error=validation_error
    )

    result = runner.invoke(app, ["discover", "libraries", "status", "finance", "--json"])

    assert result.exit_code == expected_exit
    assert f'"status": "{is_valid.value}"' in result.stdout
    if validation_error:
        assert validation_error in result.stdout
