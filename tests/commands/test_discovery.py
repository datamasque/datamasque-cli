from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import (
    DataMasqueApiError,
    DiscoveryConfigNotFoundError,
    InvalidDiscoveryConfigError,
)
from datamasque.client.models.discovery import (
    FileDiscoveryFile,
    FileDiscoveryLocatorResult,
    FileDiscoveryResult,
)
from datamasque.client.models.discovery_config import DiscoveryConfigType
from datamasque.client.models.runs import RunConnectionRef
from datamasque.client.models.safe_data_preview import (
    CommonStatistics,
    LengthsStatistics,
    NumericPreview,
    NumericStatistics,
    NumericSummaries,
    StringPreview,
    StringStatistics,
)
from datamasque.client.models.status import MaskingRunStatus
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.discovery"


def _make_string_preview() -> StringPreview:
    return StringPreview(
        statistics_common=CommonStatistics(count_row=100, count_null=0, count_distinct=76),
        statistics_kind=StringStatistics(
            lengths=LengthsStatistics(min=8, max=30, mean=13.4, median=13.0, most_common=[]),
        ),
    )


def _make_numeric_preview() -> NumericPreview:
    return NumericPreview(
        statistics_common=CommonStatistics(count_row=500, count_null=0, count_distinct=500),
        statistics_kind=NumericStatistics(
            summaries=NumericSummaries(mean=1.9e8, q1=9e7, q2=2.15e8, q3=2.7e8, p5=4.6e7, p95=2.78e8),
        ),
    )


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
def test_db_report_writes_csv_to_output_file(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_db_discovery_result_report.return_value = "header\nrow1\n"

    out = tmp_path / "db.csv"
    result = runner.invoke(app, ["discover", "db-report", "42", "--output", str(out)])

    assert result.exit_code == 0
    assert out.read_text() == "header\nrow1\n"


@patch(f"{MODULE}.get_client")
def test_db_report_writes_zip_when_split(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    zip_bytes = b"PK\x03\x04 fake zip bytes"
    client.get_db_discovery_result_report.return_value = zip_bytes

    out = tmp_path / "report.2026.06"
    result = runner.invoke(app, ["discover", "db-report", "42", "--output", str(out)])

    assert result.exit_code == 0
    assert not out.exists()
    assert (tmp_path / "report.2026.06.zip").read_bytes() == zip_bytes


@patch(f"{MODULE}.get_client")
def test_db_report_split_without_output_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_db_discovery_result_report.return_value = b"PK\x03\x04 fake zip bytes"

    result = runner.invoke(app, ["discover", "db-report", "42"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "-o" in result.stderr


def _make_file_report() -> list[FileDiscoveryResult]:
    return [
        FileDiscoveryResult(
            id=7,
            connection=RunConnectionRef(id="c1", name="myinput"),
            file_type="csv",
            files=[FileDiscoveryFile(path="data.csv", file_type="csv")],
            results=[
                FileDiscoveryLocatorResult(
                    locator="phone", matches=[], data_types=["int"], safe_data_preview=_make_numeric_preview()
                ),
            ],
        ),
    ]


@patch(f"{MODULE}.get_client")
def test_file_report_writes_json_to_output(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_file_data_discovery_report.return_value = _make_file_report()

    out = tmp_path / "file.json"
    result = runner.invoke(app, ["discover", "file-report", "7", "--output", str(out)])

    assert result.exit_code == 0
    payload = json.loads(out.read_text())
    assert payload[0]["results"][0]["safe_data_preview"]["kind"] == "numeric"


@patch(f"{MODULE}.get_client")
def test_file_report_table_lists_locators(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_file_data_discovery_report.return_value = _make_file_report()

    result = runner.invoke(app, ["discover", "file-report", "7"])

    assert result.exit_code == 0
    assert "phone" in result.stdout
    assert "data.csv" in result.stdout
    assert "safe_data_preview" not in result.stdout


# -- missing run output ----------------------------------------------------


_OUTPUT_COMMANDS = [
    (["discover", "sdd-report", "42"], "get_sdd_report", 404, "sensitive data discovery report"),
    (["discover", "db-report", "42"], "get_db_discovery_result_report", 404, "database discovery report"),
    (
        ["discover", "config-snapshot", "42"],
        "get_discovery_run_config_snapshot_yaml",
        404,
        "discovery config snapshot",
    ),
    (["discover", "schema-results", "42"], "list_schema_discovery_results", 400, "schema discovery results"),
    (["discover", "file-report", "42"], "get_file_data_discovery_report", 404, "file discovery report"),
]


def _client_missing_output(client_method: str, status: int, detail: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock(status_code=status)
    response.json.return_value = {"detail": detail}
    getattr(client, client_method).side_effect = DataMasqueApiError(f"{status}", response=response)
    return client


def _run_in_status(status: MaskingRunStatus) -> MagicMock:
    run = MagicMock()
    run.status = status
    return run


@pytest.mark.parametrize(("command", "client_method", "status", "expected"), _OUTPUT_COMMANDS)
@patch(f"{MODULE}.get_client")
def test_output_missing_while_run_is_unfinished_says_to_wait(
    mock_get_client: MagicMock,
    runner: CliRunner,
    command: list[str],
    client_method: str,
    status: int,
    expected: str,
) -> None:
    client = _client_missing_output(client_method, status, "not ready")
    client.get_run_info.return_value = _run_in_status(MaskingRunStatus.running)
    mock_get_client.return_value = client

    result = runner.invoke(app, command)

    assert result.exit_code == ExitCode.NOT_FOUND
    stderr = " ".join(result.stderr.split())
    assert f"No {expected} available for run 42 yet; the run is running." in stderr
    assert "dm run status 42" in stderr


@pytest.mark.parametrize(("command", "client_method", "status", "expected"), _OUTPUT_COMMANDS)
@patch(f"{MODULE}.get_client")
def test_output_missing_on_finished_run_reports_the_server_reason(
    mock_get_client: MagicMock,
    runner: CliRunner,
    command: list[str],
    client_method: str,
    status: int,
    expected: str,
) -> None:
    client = _client_missing_output(client_method, status, "Schema discovery has not been run on this connection.")
    client.get_run_info.return_value = _run_in_status(MaskingRunStatus.finished)
    mock_get_client.return_value = client

    result = runner.invoke(app, command)

    expected_code = ExitCode.INVALID_INPUT if status == 400 else ExitCode.NOT_FOUND
    assert result.exit_code == expected_code
    stderr = " ".join(result.stderr.split())
    assert f"No {expected} available for run 42: Schema discovery has not been run on this connection." in stderr
    assert "dm run status 42" not in stderr


@pytest.mark.parametrize(("command", "client_method", "status", "expected"), _OUTPUT_COMMANDS)
@patch(f"{MODULE}.get_client")
def test_output_missing_for_unknown_run_is_not_found(
    mock_get_client: MagicMock,
    runner: CliRunner,
    command: list[str],
    client_method: str,
    status: int,
    expected: str,
) -> None:
    client = _client_missing_output(client_method, status, "not ready")
    client.get_run_info.side_effect = DataMasqueApiError("404", response=MagicMock(status_code=404))
    mock_get_client.return_value = client

    result = runner.invoke(app, command)

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "Run 42 not found." in " ".join(result.stderr.split())


@patch(f"{MODULE}.get_client")
def test_unexpected_api_error_is_not_swallowed(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    response = MagicMock(status_code=500)
    response.json.return_value = {"detail": "Report generation crashed."}
    client.get_sdd_report.side_effect = DataMasqueApiError("500", response=response)

    result = runner.invoke(app, ["discover", "sdd-report", "42"])

    assert result.exit_code == ExitCode.ERROR
    assert "Report generation crashed." in " ".join(result.stderr.split())
    assert "Traceback" not in result.stderr


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
def test_schema_emits_run_id_as_json(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="abc-123", name="my_db", mask_type="database")]
    client.start_schema_discovery_run.return_value = 99

    result = runner.invoke(app, ["discover", "schema", "my_db", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"id": 99}


@patch(f"{MODULE}.get_client")
def test_file_start_failure_reports_server_detail(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="fs-1", name="my_files", mask_type="file")]
    response = MagicMock(status_code=400)
    response.json.return_value = {"detail": "Simultaneous runs on the same connection are not allowed."}
    client.start_file_data_discovery_run.side_effect = DataMasqueApiError("boom", response=response)

    result = runner.invoke(app, ["discover", "file", "my_files"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "Simultaneous runs on the same connection are not allowed." in " ".join(result.stderr.split())
    assert "Traceback" not in result.stderr


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
                safe_data_preview=None,
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
                safe_data_preview=None,
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
                safe_data_preview=None,
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
                safe_data_preview=None,
            ),
        ),
    ]

    result = runner.invoke(app, ["discover", "schema-results", "42", "--json"])

    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert rows[0]["matches"] == "EMAIL_ADDRESS"
    assert rows[1]["matches"] == "-"


@patch(f"{MODULE}.get_client")
def test_schema_results_includes_safe_data_preview_in_json(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_schema_discovery_results.return_value = [
        SimpleNamespace(
            id=1,
            column="author",
            table="books",
            schema_name="public",
            data=SimpleNamespace(
                data_type="varchar",
                discovery_matches=[SimpleNamespace(label="name")],
                constraint="",
                safe_data_preview=_make_string_preview(),
            ),
        ),
    ]

    result = runner.invoke(app, ["discover", "schema-results", "42", "--json"])

    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert rows[0]["safe_data_preview"]["kind"] == "string"
    assert rows[0]["safe_data_preview"]["statistics_kind"]["lengths"]["max"] == 30

    table = runner.invoke(app, ["discover", "schema-results", "42"])
    assert table.exit_code == 0
    assert "safe_data_preview" not in table.stdout


@pytest.mark.parametrize("has_safe_data_preview", [True, False])
@patch(f"{MODULE}.get_client")
def test_schema_results_hints_at_json_only_when_safe_data_preview_present(
    mock_get_client: MagicMock, runner: CliRunner, has_safe_data_preview: bool
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_schema_discovery_results.return_value = [
        SimpleNamespace(
            id=1,
            column="author",
            table="books",
            schema_name="public",
            data=SimpleNamespace(
                data_type="varchar",
                discovery_matches=[SimpleNamespace(label="name")],
                constraint="",
                safe_data_preview=_make_string_preview() if has_safe_data_preview else None,
            ),
        ),
    ]

    result = runner.invoke(app, ["discover", "schema-results", "42"])

    assert result.exit_code == 0
    assert ("Safe Data Preview results are not shown" in result.stderr) is has_safe_data_preview
    assert ("--json" in result.stderr) is has_safe_data_preview


# -- configurable-discovery run triggers ----------------------------------


def _fake_config_lookup(**ids_by_type: str) -> Callable[[str, DiscoveryConfigType], SimpleNamespace | None]:
    """Return a `get_discovery_config_by_name` side effect that knows only the given types."""

    def lookup(name: str, config_type: DiscoveryConfigType) -> SimpleNamespace | None:
        config_id = ids_by_type.get(config_type.value)
        if config_id is None:
            return None
        return SimpleNamespace(id=config_id, name=name, config_type=config_type)

    return lookup


@patch(f"{MODULE}.get_client")
def test_schema_with_config_runs_from_saved_config(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="abc-123", name="my_db", mask_type="database")]
    client.get_discovery_config_by_name.side_effect = _fake_config_lookup(database="cfg-1")
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
    client.get_discovery_config_by_name.side_effect = _fake_config_lookup(file="cfg-2")

    result = runner.invoke(app, ["discover", "schema", "my_db", "--config", "docs"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "exists as file" in " ".join(result.stderr.split())
    client.start_schema_discovery_run_from_config.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_schema_config_not_found_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    """Neither type holds the name, so this is not-found rather than a type mismatch."""
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="abc-123", name="my_db", mask_type="database")]
    client.get_discovery_config_by_name.side_effect = _fake_config_lookup()

    result = runner.invoke(app, ["discover", "schema", "my_db", "--config", "nope"])

    assert result.exit_code == ExitCode.NOT_FOUND
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
    client.get_discovery_config_by_name.side_effect = _fake_config_lookup(file="cfg-3")
    client.start_file_data_discovery_run_from_config.return_value = 89

    result = runner.invoke(app, ["discover", "file", "my_files", "--config", "docs"])

    assert result.exit_code == 0
    client.start_file_data_discovery_run.assert_not_called()
    (call,) = client.start_file_data_discovery_run_from_config.call_args_list
    (request,) = call.args
    assert request.discovery_config == "cfg-3"


_CONFIG_RUN_STARTS = [
    (
        ["discover", "schema", "my_db", "--config", "emp"],
        SimpleNamespace(id="abc-123", name="my_db", mask_type="database"),
        {"database": "cfg-1"},
        "start_schema_discovery_run_from_config",
    ),
    (
        ["discover", "file", "my_files", "--config", "docs"],
        SimpleNamespace(id="fs-1", name="my_files", mask_type="file"),
        {"file": "cfg-3"},
        "start_file_data_discovery_run_from_config",
    ),
]


@pytest.mark.parametrize(("command", "connection", "config_ids", "start_method"), _CONFIG_RUN_STARTS)
@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (DiscoveryConfigNotFoundError, ExitCode.NOT_FOUND),
        (InvalidDiscoveryConfigError, ExitCode.INVALID_INPUT),
    ],
)
@patch(f"{MODULE}.get_client")
def test_config_run_start_error_keeps_its_own_code(
    mock_get_client: MagicMock,
    runner: CliRunner,
    error: type[DataMasqueApiError],
    expected_code: ExitCode,
    command: list[str],
    connection: SimpleNamespace,
    config_ids: dict[str, str],
    start_method: str,
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [connection]
    client.get_discovery_config_by_name.side_effect = _fake_config_lookup(**config_ids)
    getattr(client, start_method).side_effect = error(
        "run failed to start: the config is unusable", response=MagicMock(status_code=400)
    )

    result = runner.invoke(app, command)

    assert result.exit_code == expected_code
    assert "the config is unusable" in " ".join(result.stderr.split())


@patch(f"{MODULE}.get_client")
def test_file_emits_run_id_as_json(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="fs-1", name="my_files", mask_type="file")]
    client.start_file_data_discovery_run.return_value = 88

    result = runner.invoke(app, ["discover", "file", "my_files", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"id": 88}


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
