from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datamasque.client.models.discovery_config import DiscoveryConfigType
from datamasque.client.models.status import ValidationStatus
from typer.testing import CliRunner

from datamasque_cli.main import app
from datamasque_cli.output import ExitCode

MODULE = "datamasque_cli.commands.discovery_config_libraries"


def _library(
    name: str,
    config_type: DiscoveryConfigType = DiscoveryConfigType.database,
    namespace: str = "",
    library_id: str = "lib-uuid",
    is_valid: ValidationStatus | None = ValidationStatus.valid,
    yaml: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=library_id,
        name=name,
        namespace=namespace,
        config_type=config_type,
        is_valid=is_valid,
        validation_error=None,
        created=None,
        modified=None,
        yaml=yaml,
    )


@patch(f"{MODULE}.get_client")
def test_list_shows_namespace_and_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_config_libraries.return_value = [
        _library("finance", namespace="org"),
    ]

    result = runner.invoke(app, ["discover", "libraries", "list", "--json"])

    assert result.exit_code == 0
    assert '"finance"' in result.stdout
    assert '"org"' in result.stdout


@patch(f"{MODULE}.get_client")
def test_get_yaml_fetches_full_library(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_config_libraries.return_value = [_library("finance", namespace="org")]
    client.get_discovery_config_library.return_value = _library("finance", namespace="org", yaml="labels: []\n")

    result = runner.invoke(app, ["discover", "libraries", "get", "finance", "--namespace", "org", "--yaml"])

    assert result.exit_code == 0
    assert "labels: []" in result.stdout
    client.get_discovery_config_library.assert_called_once_with("lib-uuid")


@patch(f"{MODULE}.get_client")
def test_get_namespace_scopes_lookup(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_config_libraries.return_value = [_library("finance", namespace="org")]

    result = runner.invoke(app, ["discover", "libraries", "get", "finance"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.get_discovery_config_library.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_new_requires_type(mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_config_libraries.return_value = []
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(
        app,
        ["discover", "libraries", "create", "--name", "finance", "-n", "org", "-f", str(lib), "--type", "database"],
    )

    assert result.exit_code == 0
    client.create_or_update_discovery_config_library.assert_called_once()


@patch(f"{MODULE}.get_client")
def test_delete_force_passes_through(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_config_libraries.return_value = [_library("finance", namespace="org")]

    result = runner.invoke(app, ["discover", "libraries", "delete", "finance", "-n", "org", "--force", "--yes"])

    assert result.exit_code == 0
    client.delete_discovery_config_library_by_id_if_exists.assert_called_once_with("lib-uuid", force=True)


@patch(f"{MODULE}.get_client")
def test_validate_invalid_exits_4(mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.validate_discovery_config_library.return_value = SimpleNamespace(
        is_valid=ValidationStatus.invalid, validation_error="duplicate label 'email'"
    )
    lib = tmp_path / "lib.yaml"
    lib.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(lib), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "duplicate label 'email'" in result.stderr
