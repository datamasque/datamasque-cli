from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.discovery_config import DiscoveryConfig, DiscoveryConfigId, DiscoveryConfigType
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


def _create_returning(
    is_valid: ValidationStatus | None,
    validation_error: str | None = None,
) -> Callable[[DiscoveryConfig], DiscoveryConfig]:

    def fake_create(config: DiscoveryConfig) -> DiscoveryConfig:
        config.id = DiscoveryConfigId("cfg-uuid")
        config.is_valid = is_valid
        config.validation_error = validation_error
        config.validation_error_details = []
        return config

    return fake_create


@patch(f"{MODULE}.get_client")
def test_unknown_type_is_rejected_before_any_request(mock_get_client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["discover", "configs", "list", "--type", "banana"])

    assert result.exit_code == ExitCode.USAGE
    assert "is not one of" in result.output
    mock_get_client.assert_not_called()


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
def test_create_new_requires_type(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
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
def test_create_update_defaults_to_existing_type(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
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
def test_validate_reports_valid(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.create_discovery_config.side_effect = _create_returning(ValidationStatus.valid)
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "validate", "-f", str(cfg), "--type", "database"])

    assert result.exit_code == 0
    assert "valid" in result.stderr
    created = client.create_discovery_config.call_args.args[0]
    assert created.name.startswith("__dm_cli_validate_")
    assert created.yaml == "labels: []\n"
    assert created.config_type is DiscoveryConfigType.database
    client.delete_discovery_config_by_id_if_exists.assert_called_once_with("cfg-uuid")


@patch(f"{MODULE}.get_client")
def test_validate_invalid_exits_4(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.create_discovery_config.side_effect = _create_returning(
        ValidationStatus.invalid, validation_error="unknown label 'foo'"
    )
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "validate", "-f", str(cfg), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "unknown label 'foo'" in result.stderr
    client.delete_discovery_config_by_id_if_exists.assert_called_once_with("cfg-uuid")


@patch(f"{MODULE}.get_client")
def test_validate_rejected_create_aborts_without_delete(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    response = MagicMock()
    response.status_code = HTTPStatus.BAD_REQUEST
    response.json.return_value = {"detail": "config_yaml: invalid"}
    client.create_discovery_config.side_effect = DataMasqueApiError(
        "API request failed with status 400", response=response
    )
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "validate", "-f", str(cfg), "--type", "database"])

    assert result.exit_code == ExitCode.ERROR
    assert "config_yaml: invalid" in result.stderr
    client.delete_discovery_config_by_id_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_warns_when_temp_config_cleanup_fails(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.create_discovery_config.side_effect = _create_returning(ValidationStatus.valid)
    client.delete_discovery_config_by_id_if_exists.side_effect = DataMasqueApiError("boom", response=MagicMock())
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "validate", "-f", str(cfg), "--type", "database"])

    assert result.exit_code == 0
    assert "left on server" in result.stderr


@patch(f"{MODULE}.get_client")
def test_validate_empty_file_aborts_before_any_request(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    cfg = tmp_path / "empty.yaml"
    cfg.write_text("")

    result = runner.invoke(app, ["discover", "configs", "validate", "-f", str(cfg), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    mock_get_client.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_oversize_aborts_before_any_request(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    cfg = tmp_path / "big.yaml"
    cfg.write_text("# padding\n" * 7000)

    result = runner.invoke(app, ["discover", "configs", "validate", "-f", str(cfg), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "asynchronously" in result.stderr
    assert "dm discover configs status" in result.stderr
    mock_get_client.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_status_valid_exits_0(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [_config("emp")]

    result = runner.invoke(app, ["discover", "configs", "status", "emp", "--json"])

    assert result.exit_code == 0
    assert '"status": "valid"' in result.stdout


@patch(f"{MODULE}.get_client")
def test_status_invalid_exits_4(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    config = _config("emp", is_valid=ValidationStatus.invalid)
    config.validation_error = "unknown label 'foo'"
    client.list_discovery_configs.return_value = [config]

    result = runner.invoke(app, ["discover", "configs", "status", "emp", "--json"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "unknown label 'foo'" in result.stdout


@patch(f"{MODULE}.get_client")
def test_status_in_progress_exits_0(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [_config("emp", is_valid=ValidationStatus.in_progress)]

    result = runner.invoke(app, ["discover", "configs", "status", "emp", "--json"])

    assert result.exit_code == 0
    assert '"status": "in_progress"' in result.stdout
