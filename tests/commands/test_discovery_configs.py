from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datamasque.client.models.discovery_config import DiscoveryConfigType
from datamasque.client.models.status import ValidationStatus
from typer.testing import CliRunner

from datamasque_cli.main import app
from datamasque_cli.output import ExitCode

MODULE = "datamasque_cli.commands.discovery_configs"


def _config(
    name: str,
    config_type: DiscoveryConfigType = DiscoveryConfigType.database,
    config_id: str = "cfg-uuid",
    is_valid: ValidationStatus | None = ValidationStatus.valid,
    yaml: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=config_id,
        name=name,
        config_type=config_type,
        is_valid=is_valid,
        validation_error=None,
        created=None,
        modified=None,
        yaml=yaml,
    )


@patch(f"{MODULE}.get_client")
def test_list_filters_by_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [
        _config("emp", DiscoveryConfigType.database),
        _config("docs", DiscoveryConfigType.file),
    ]

    result = runner.invoke(app, ["discover", "configs", "list", "--type", "file"])

    assert result.exit_code == 0
    assert "docs" in result.stdout
    assert "emp" not in result.stdout


@patch(f"{MODULE}.get_client")
def test_get_yaml_fetches_full_config(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [_config("emp")]
    client.get_discovery_config.return_value = _config("emp", yaml="labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "get", "emp", "--yaml"])

    assert result.exit_code == 0
    assert "labels: []" in result.stdout
    client.get_discovery_config.assert_called_once_with("cfg-uuid")


@patch(f"{MODULE}.get_client")
def test_get_ambiguous_name_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [
        _config("shared", DiscoveryConfigType.database, config_id="a"),
        _config("shared", DiscoveryConfigType.file, config_id="b"),
    ]

    result = runner.invoke(app, ["discover", "configs", "get", "shared"])

    assert result.exit_code == ExitCode.AMBIGUOUS
    client.get_discovery_config.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_get_ambiguous_resolved_by_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [
        _config("shared", DiscoveryConfigType.database, config_id="a"),
        _config("shared", DiscoveryConfigType.file, config_id="b"),
    ]
    client.get_discovery_config.return_value = _config("shared", DiscoveryConfigType.file, config_id="b")

    result = runner.invoke(app, ["discover", "configs", "get", "shared", "--type", "file"])

    assert result.exit_code == 0
    client.get_discovery_config.assert_called_once_with("b")


@patch(f"{MODULE}.get_client")
def test_defaults_requests_typed_default(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.make_request.return_value = SimpleNamespace(content=b"labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "defaults", "--type", "file"])

    assert result.exit_code == 0
    assert "labels: []" in result.stdout
    client.make_request.assert_called_once_with(
        "GET", "/api/discovery/configs/defaults/", params={"config_type": "file"}
    )


@patch(f"{MODULE}.get_client")
def test_create_new_requires_type(mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = []
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    missing_type = runner.invoke(app, ["discover", "configs", "create", "--name", "emp", "-f", str(cfg)])
    assert missing_type.exit_code == ExitCode.NOT_FOUND
    client.create_or_update_discovery_config.assert_not_called()

    with_type = runner.invoke(
        app, ["discover", "configs", "create", "--name", "emp", "-f", str(cfg), "--type", "database"]
    )
    assert with_type.exit_code == 0
    client.create_or_update_discovery_config.assert_called_once()


@patch(f"{MODULE}.get_client")
def test_create_update_defaults_to_existing_type(mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [_config("emp", DiscoveryConfigType.database)]
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "create", "--name", "emp", "-f", str(cfg)])

    assert result.exit_code == 0
    client.create_or_update_discovery_config.assert_called_once()


@patch(f"{MODULE}.get_client")
def test_delete_proceeds_when_present(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [_config("emp")]

    result = runner.invoke(app, ["discover", "configs", "delete", "emp", "--yes"])

    assert result.exit_code == 0
    client.delete_discovery_config_by_id_if_exists.assert_called_once_with("cfg-uuid")


@patch(f"{MODULE}.get_client")
def test_delete_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = []

    result = runner.invoke(app, ["discover", "configs", "delete", "nope", "--yes"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.delete_discovery_config_by_id_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_reports_valid(mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.validate_discovery_config.return_value = SimpleNamespace(
        is_valid=ValidationStatus.valid, validation_error=None
    )
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "validate", "-f", str(cfg), "--type", "database"])

    assert result.exit_code == 0
    assert "valid" in result.stderr
    client.validate_discovery_config.assert_called_once()


@patch(f"{MODULE}.get_client")
def test_validate_invalid_exits_4(mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.validate_discovery_config.return_value = SimpleNamespace(
        is_valid=ValidationStatus.invalid, validation_error="unknown label 'foo'"
    )
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "validate", "-f", str(cfg), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "unknown label 'foo'" in result.stderr
