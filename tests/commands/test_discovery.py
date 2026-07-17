from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datamasque.client.models.discovery_config import DiscoveryConfigType
from typer.testing import CliRunner

from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.discovery"


@patch(f"{MODULE}.get_client")
def test_sdd_report_writes_to_output_file(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_sdd_report.return_value = "col1,col2\na,b\n"

    out = tmp_path / "report.csv"
    result = runner.invoke(app, ["discover", "sdd-report", "42", "--output", str(out)])

    assert result.exit_code == 0
    assert out.read_text() == "col1,col2\na,b\n"


@patch(f"{MODULE}.get_client")
def test_sdd_report_echoes_to_stdout_without_output(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_sdd_report.return_value = "col1,col2\na,b\n"

    result = runner.invoke(app, ["discover", "sdd-report", "42"])

    assert result.exit_code == 0
    assert "col1,col2" in result.stdout


@patch(f"{MODULE}.get_client")
def test_db_report_writes_to_output_file(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_db_discovery_result_report.return_value = "header\nrow1\n"

    out = tmp_path / "db.csv"
    result = runner.invoke(app, ["discover", "db-report", "42", "--output", str(out)])

    assert result.exit_code == 0
    assert out.read_text() == "header\nrow1\n"


@patch(f"{MODULE}.get_client")
def test_db_report_writes_zip_bytes_to_output_file(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_db_discovery_result_report.return_value = b"PK\x03\x04fake-zip-bytes"

    out = tmp_path / "db.zip"
    result = runner.invoke(app, ["discover", "db-report", "42", "--output", str(out)])

    assert result.exit_code == 0
    assert out.read_bytes() == b"PK\x03\x04fake-zip-bytes"
    assert "zip" in result.stderr


@patch(f"{MODULE}.get_client")
def test_db_report_zip_without_output_aborts_with_hint(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_db_discovery_result_report.return_value = b"PK\x03\x04fake-zip-bytes"

    result = runner.invoke(app, ["discover", "db-report", "42"])

    assert result.exit_code == 4  # invalid_input
    assert "--output" in result.stderr
    assert "PK" not in result.stdout


@patch(f"{MODULE}.get_client")
def test_file_report_writes_json_to_output(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_file_data_discovery_report.return_value = [{"file": "a"}]

    out = tmp_path / "file.json"
    result = runner.invoke(app, ["discover", "file-report", "42", "--output", str(out)])

    assert result.exit_code == 0
    assert '"file": "a"' in out.read_text()


# -- schema discovery trigger ---------------------------------------------


@patch(f"{MODULE}.get_client")
def test_schema_starts_discovery_run_and_points_at_results(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [
        SimpleNamespace(id="abc-123", name="my_db", mask_type="database"),
    ]
    client.start_schema_discovery_run.return_value = 99

    result = runner.invoke(app, ["discover", "schema", "my_db"])

    assert result.exit_code == 0
    (call,) = client.start_schema_discovery_run.call_args_list
    (request,) = call.args
    assert request.connection == "abc-123"
    assert "dm discover schema-results 99" in result.stderr


@patch(f"{MODULE}.get_client")
def test_schema_results_lists_with_flattened_rows(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_schema_discovery_results.return_value = [
        SimpleNamespace(
            id=1,
            column="email",
            table="users",
            schema_name="public",
            data=SimpleNamespace(
                data_type="varchar",
                discovery_matches=[SimpleNamespace(label="EMAIL_ADDRESS")],
                constraint="",
            ),
        ),
        SimpleNamespace(
            id=2,
            column="ssn",
            table="profiles",
            schema_name=None,
            data=SimpleNamespace(
                data_type="varchar",
                discovery_matches=[
                    SimpleNamespace(label="US_SSN"),
                    SimpleNamespace(label="PII"),
                ],
                constraint="Primary",
            ),
        ),
    ]

    result = runner.invoke(app, ["discover", "schema-results", "42", "--json"])

    assert result.exit_code == 0
    assert '"email"' in result.stdout
    assert '"ssn"' in result.stdout
    assert '"EMAIL_ADDRESS"' in result.stdout
    assert '"US_SSN, PII"' in result.stdout
    assert '"Primary"' in result.stdout


@patch(f"{MODULE}.get_client")
def test_schema_results_skips_unlabelled_matches(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_schema_discovery_results.return_value = [
        SimpleNamespace(
            id=1,
            column="email",
            table="users",
            schema_name="public",
            data=SimpleNamespace(
                data_type="varchar",
                discovery_matches=[
                    SimpleNamespace(label="EMAIL_ADDRESS"),
                    SimpleNamespace(label=None),
                ],
                constraint="",
            ),
        ),
        SimpleNamespace(
            id=2,
            column="notes",
            table="users",
            schema_name="public",
            data=SimpleNamespace(
                data_type="text",
                discovery_matches=[SimpleNamespace(label=None)],
                constraint="",
            ),
        ),
    ]

    result = runner.invoke(app, ["discover", "schema-results", "42", "--json"])

    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert rows[0]["matches"] == "EMAIL_ADDRESS"
    assert rows[1]["matches"] == "-"


# -- configurable-discovery run triggers ----------------------------------


@patch(f"{MODULE}.get_client")
def test_schema_with_config_runs_from_saved_config(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="abc-123", name="my_db", mask_type="database")]
    client.list_discovery_configs.return_value = [
        SimpleNamespace(id="cfg-1", name="emp", config_type=DiscoveryConfigType.database),
    ]
    client.start_schema_discovery_run_from_config.return_value = 77

    result = runner.invoke(app, ["discover", "schema", "my_db", "--config", "emp"])

    assert result.exit_code == 0
    client.start_schema_discovery_run.assert_not_called()
    (call,) = client.start_schema_discovery_run_from_config.call_args_list
    (request,) = call.args
    assert request.connection == "abc-123"
    assert request.discovery_config == "cfg-1"
    assert "dm discover schema-results 77" in result.stderr


@patch(f"{MODULE}.get_client")
def test_schema_config_wrong_type_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="abc-123", name="my_db", mask_type="database")]
    client.list_discovery_configs.return_value = [
        SimpleNamespace(id="cfg-2", name="docs", config_type=DiscoveryConfigType.file),
    ]

    result = runner.invoke(app, ["discover", "schema", "my_db", "--config", "docs"])

    assert result.exit_code == 4  # invalid_input
    client.start_schema_discovery_run_from_config.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_file_without_config_runs_keyword_discovery(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="fs-1", name="my_files", mask_type="file")]
    client.start_file_data_discovery_run.return_value = 88

    result = runner.invoke(app, ["discover", "file", "my_files"])

    assert result.exit_code == 0
    client.start_file_data_discovery_run_from_config.assert_not_called()
    (call,) = client.start_file_data_discovery_run.call_args_list
    (request,) = call.args
    assert request.connection == "fs-1"
    assert "dm discover file-report 88" in result.stderr


@patch(f"{MODULE}.get_client")
def test_file_with_config_runs_from_saved_config(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="fs-1", name="my_files", mask_type="file")]
    client.list_discovery_configs.return_value = [
        SimpleNamespace(id="cfg-3", name="docs", config_type=DiscoveryConfigType.file),
    ]
    client.start_file_data_discovery_run_from_config.return_value = 89

    result = runner.invoke(app, ["discover", "file", "my_files", "--config", "docs"])

    assert result.exit_code == 0
    client.start_file_data_discovery_run.assert_not_called()
    (call,) = client.start_file_data_discovery_run_from_config.call_args_list
    (request,) = call.args
    assert request.discovery_config == "cfg-3"


@patch(f"{MODULE}.get_client")
def test_config_snapshot_writes_to_output(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_discovery_run_config_snapshot_yaml.return_value = "# provenance\nlabels: []\n"

    out = tmp_path / "used.yaml"
    result = runner.invoke(app, ["discover", "config-snapshot", "42", "--output", str(out)])

    assert result.exit_code == 0
    assert out.read_text() == "# provenance\nlabels: []\n"
    client.get_discovery_run_config_snapshot_yaml.assert_called_once_with(42)
