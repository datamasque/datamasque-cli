from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.discovery_config import DiscoveryConfigType
from datamasque.client.models.status import ValidationStatus
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.discovery_configs"


def _make_discovery_config(
    name: str,
    config_type: DiscoveryConfigType = DiscoveryConfigType.database,
    config_id: str = "cfg-uuid",
    is_valid: ValidationStatus | None = ValidationStatus.valid,
    yaml: str | None = None,
    validation_error: str | None = None,
) -> SimpleNamespace:
    """A discovery config as the server returns it, carrying its validation status."""
    return SimpleNamespace(
        id=config_id,
        name=name,
        config_type=config_type,
        is_valid=is_valid,
        validation_error=validation_error,
        validation_error_details=[],
        created=None,
        modified=None,
        yaml=yaml,
    )


@patch(f"{MODULE}.get_client")
def test_unknown_type_is_rejected_before_any_request(mock_get_client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["discover", "configs", "list", "--type", "banana"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert "is not one of" in result.output
    mock_get_client.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_list_filters_by_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [
        _make_discovery_config("emp", DiscoveryConfigType.database),
        _make_discovery_config("docs", DiscoveryConfigType.file),
    ]

    result = runner.invoke(app, ["discover", "configs", "list", "--type", "file"])

    assert result.exit_code == 0
    assert "docs" in result.stdout
    assert "emp" not in result.stdout


@patch(f"{MODULE}.get_client")
def test_get_yaml_fetches_full_config(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [_make_discovery_config("emp")]
    client.get_discovery_config.return_value = _make_discovery_config("emp", yaml="labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "get", "emp", "--yaml"])

    assert result.exit_code == 0
    assert "labels: []" in result.stdout
    client.get_discovery_config.assert_called_once_with("cfg-uuid")


@patch(f"{MODULE}.get_client")
def test_get_ambiguous_name_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [
        _make_discovery_config("shared", DiscoveryConfigType.database, config_id="a"),
        _make_discovery_config("shared", DiscoveryConfigType.file, config_id="b"),
    ]

    result = runner.invoke(app, ["discover", "configs", "get", "shared"])

    assert result.exit_code == ExitCode.AMBIGUOUS
    client.get_discovery_config.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_get_ambiguous_resolved_by_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [
        _make_discovery_config("shared", DiscoveryConfigType.database, config_id="a"),
        _make_discovery_config("shared", DiscoveryConfigType.file, config_id="b"),
    ]
    client.get_discovery_config.return_value = _make_discovery_config("shared", DiscoveryConfigType.file, config_id="b")

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
    client.list_discovery_configs.return_value = [_make_discovery_config("emp", DiscoveryConfigType.database)]
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("labels: []\n")

    result = runner.invoke(app, ["discover", "configs", "create", "--name", "emp", "-f", str(cfg)])

    assert result.exit_code == 0
    client.create_or_update_discovery_config.assert_called_once()


@patch(f"{MODULE}.get_client")
def test_delete_proceeds_when_present(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [_make_discovery_config("emp")]

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
    client.create_discovery_config.return_value = _make_discovery_config("emp", is_valid=ValidationStatus.valid)
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
    client.create_discovery_config.return_value = _make_discovery_config(
        "emp", is_valid=ValidationStatus.invalid, validation_error="unknown label 'foo'"
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

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "config_yaml: invalid" in result.stderr
    client.delete_discovery_config_by_id_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_warns_when_temp_config_cleanup_fails(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.create_discovery_config.return_value = _make_discovery_config("emp", is_valid=ValidationStatus.valid)
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


@pytest.mark.parametrize(
    ("is_valid", "validation_error"),
    [
        (ValidationStatus.valid, None),
        (ValidationStatus.invalid, "unknown label 'foo'"),
        (ValidationStatus.in_progress, None),
    ],
    ids=["valid", "invalid", "in_progress"],
)
@patch(f"{MODULE}.get_client")
def test_status_reports_state(
    mock_get_client: MagicMock,
    runner: CliRunner,
    is_valid: ValidationStatus,
    validation_error: str | None,
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [
        _make_discovery_config("emp", is_valid=is_valid, validation_error=validation_error)
    ]

    result = runner.invoke(app, ["discover", "configs", "status", "emp", "--json"])

    assert result.exit_code == ExitCode.OK
    assert f'"status": "{is_valid.value}"' in result.stdout
    if validation_error:
        assert validation_error in result.stdout
