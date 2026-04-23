from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client import RunId
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ruleset import RulesetType
from datamasque.client.models.runs import MaskingRunRequest, RunInfo
from typer.testing import CliRunner

from datamasque_cli.commands.runs import (
    _LOG_LEVEL_LABELS,
    _coerce_option_value,
    _format_run_dict,
    _format_run_info,
    _parse_options,
    _print_pretty_logs,
    _resolve_connection,
    _resolve_connection_id,
    _resolve_ruleset_id,
)
from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.runs"


def _run_info(**overrides: Any) -> RunInfo:
    """Build a `RunInfo` with sensible defaults for tests."""
    data: dict[str, Any] = {
        "id": 42,
        "status": "finished",
        "mask_type": "database",
        "source_connection": "src-uuid",
        "source_connection_name": "my_src",
        "ruleset_name": "demo",
    }
    data.update(overrides)
    return RunInfo.model_validate(data)


# -- _format_run_info / _format_run_dict ----------------------------------


def test_format_run_info_uses_nested_connection_name() -> None:
    result = _format_run_info(_run_info())
    assert result["status"] == "finished"
    assert result["source"] == "my_src"


def test_format_run_dict_prefers_status_over_run_status() -> None:
    result = _format_run_dict({"id": 1, "status": "finished", "run_status": "queued"})
    assert result["status"] == "finished"


def test_format_run_dict_falls_back_to_run_status() -> None:
    result = _format_run_dict({"id": 1, "run_status": "running"})
    assert result["status"] == "running"


# -- _resolve_connection_id / _resolve_ruleset_id --------------------------


def test_resolve_connection_id_by_name(mock_client: MagicMock) -> None:
    assert _resolve_connection_id(mock_client, "my_conn") == "1"


def test_resolve_connection_id_by_id(mock_client: MagicMock) -> None:
    assert _resolve_connection_id(mock_client, "2") == "2"


def test_resolve_connection_id_not_found(mock_client: MagicMock) -> None:
    with pytest.raises(SystemExit):
        _resolve_connection_id(mock_client, "nonexistent")


def test_resolve_ruleset_id_by_name(mock_client: MagicMock) -> None:
    assert _resolve_ruleset_id(mock_client, "my_ruleset") == "10"


def test_resolve_ruleset_id_not_found(mock_client: MagicMock) -> None:
    with pytest.raises(SystemExit):
        _resolve_ruleset_id(mock_client, "nonexistent")


def test_resolve_ruleset_id_prefers_matching_mask_type() -> None:
    client = MagicMock()
    client.list_rulesets.return_value = [
        SimpleNamespace(id=1, name="demo", ruleset_type=RulesetType.database),
        SimpleNamespace(id=2, name="demo", ruleset_type=RulesetType.file),
    ]
    assert _resolve_ruleset_id(client, "demo", mask_type="file") == "2"
    assert _resolve_ruleset_id(client, "demo", mask_type="database") == "1"


def test_resolve_ruleset_id_aborts_when_type_missing() -> None:
    client = MagicMock()
    client.list_rulesets.return_value = [
        SimpleNamespace(id=1, name="demo", ruleset_type=RulesetType.database),
    ]
    with pytest.raises(SystemExit):
        _resolve_ruleset_id(client, "demo", mask_type="file")


def test_resolve_ruleset_id_ambiguous_without_type() -> None:
    client = MagicMock()
    client.list_rulesets.return_value = [
        SimpleNamespace(id=1, name="demo", ruleset_type=RulesetType.database),
        SimpleNamespace(id=2, name="demo", ruleset_type=RulesetType.file),
    ]
    with pytest.raises(SystemExit):
        _resolve_ruleset_id(client, "demo")


def test_resolve_connection_returns_name_and_type(mock_client: MagicMock) -> None:
    conn = _resolve_connection(mock_client, "my_conn")
    assert conn.name == "my_conn"
    assert conn.mask_type == "database"


# -- start_run (behaviour, not wiring) ------------------------------------


@patch(f"{MODULE}.get_client")
def test_start_run_blocks_by_default(mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner) -> None:
    mock_get_client.return_value = mock_client
    mock_client.start_masking_run.return_value = RunId(42)
    mock_client.get_run_info.return_value = _run_info(id=42, status="finished")

    runner.invoke(app, ["run", "start", "-c", "my_conn", "-r", "my_ruleset"])
    mock_client.get_run_info.assert_called()


@patch(f"{MODULE}.get_client")
def test_start_run_background_skips_wait(mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner) -> None:
    mock_get_client.return_value = mock_client
    mock_client.start_masking_run.return_value = RunId(42)

    runner.invoke(app, ["run", "start", "-c", "my_conn", "-r", "my_ruleset", "-b"])
    mock_client.get_run_info.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_start_run_uses_connection_name_for_run_label(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client
    mock_client.start_masking_run.return_value = RunId(42)
    mock_client.get_run_info.return_value = _run_info(id=42, status="finished")

    runner.invoke(app, ["run", "start", "-c", "1", "-r", "my_ruleset"])

    (call,) = mock_client.start_masking_run.call_args_list
    request: MaskingRunRequest = call.args[0]
    assert request.name is not None
    assert request.name.startswith("my_conn_")


@patch(f"{MODULE}.get_client")
def test_start_run_passes_connection_type_to_ruleset_resolver(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [
        SimpleNamespace(id=1, name="files_in", mask_type="file"),
        SimpleNamespace(id=2, name="files_out", mask_type="file"),
    ]
    client.list_rulesets.return_value = [
        SimpleNamespace(id=10, name="demo", ruleset_type=RulesetType.database),
        SimpleNamespace(id=20, name="demo", ruleset_type=RulesetType.file),
    ]
    client.start_masking_run.return_value = RunId(42)
    client.get_run_info.return_value = _run_info(id=42, status="finished", mask_type="file")

    runner.invoke(app, ["run", "start", "-c", "files_in", "-r", "demo", "-d", "files_out"])

    (call,) = client.start_masking_run.call_args_list
    request: MaskingRunRequest = call.args[0]
    assert request.ruleset == "20"


@patch(f"{MODULE}.get_client")
def test_start_run_aborts_on_destination_type_mismatch(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [
        SimpleNamespace(id=1, name="db_src", mask_type="database"),
        SimpleNamespace(id=2, name="files_dst", mask_type="file"),
    ]
    client.list_rulesets.return_value = [
        SimpleNamespace(id=10, name="demo", ruleset_type=RulesetType.database),
    ]

    result = runner.invoke(app, ["run", "start", "-c", "db_src", "-r", "demo", "-d", "files_dst"])

    assert result.exit_code != 0
    client.start_masking_run.assert_not_called()


# -- list_runs envelope handling -------------------------------------------


@patch(f"{MODULE}.get_client")
def test_list_runs_handles_dict_without_results_key(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    """A dict response without `results` should yield an empty list, not iterate dict keys."""
    mock_get_client.return_value = mock_client
    mock_client.make_request.return_value = MagicMock(json=MagicMock(return_value={"count": 0}))

    result = runner.invoke(app, ["run", "list", "--json"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"


# -- _parse_options / --options flag --------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("FALSE", False),
        ("42", 42),
        ("1.5", 1.5),
        ("snowflake", "snowflake"),
    ],
)
def test_coerce_option_value(raw: str, expected: object) -> None:
    assert _coerce_option_value(raw) == expected


def test_parse_options_builds_dict_with_coerced_values() -> None:
    result = _parse_options(["batch_size=1000", "dry_run=true"])
    assert result == {"batch_size": 1000, "dry_run": True}


def test_parse_options_rejects_missing_equals() -> None:
    with pytest.raises(SystemExit):
        _parse_options(["batch_size"])


@patch(f"{MODULE}.get_client")
def test_start_run_passes_parsed_options_into_payload(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client
    mock_client.start_masking_run.return_value = RunId(42)
    mock_client.get_run_info.return_value = _run_info(id=42, status="finished")

    runner.invoke(
        app,
        [
            "run",
            "start",
            "-c",
            "my_conn",
            "-r",
            "my_ruleset",
            "--options",
            "batch_size=500",
            "--options",
            "dry_run=true",
        ],
    )

    (call,) = mock_client.start_masking_run.call_args_list
    request: MaskingRunRequest = call.args[0]
    assert request.options.batch_size == 500
    assert request.options.dry_run is True


@patch(f"{MODULE}.get_client")
def test_start_run_aborts_when_file_source_has_no_destination(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [
        SimpleNamespace(id=1, name="files_src", mask_type="file"),
    ]
    client.list_rulesets.return_value = [
        SimpleNamespace(id=10, name="demo", ruleset_type=RulesetType.file),
    ]

    result = runner.invoke(app, ["run", "start", "-c", "files_src", "-r", "demo"])

    assert result.exit_code != 0
    assert "destination" in result.stderr.lower()
    client.start_masking_run.assert_not_called()


# -- retry -----------------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_retry_run_preserves_source_ruleset_destination_and_options(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_run_info.return_value = RunInfo.model_validate(
        {
            "id": 100,
            "source_connection": "src-uuid",
            "source_connection_name": "my_src",
            "destination_connection": "dst-uuid",
            "destination_connection_name": "my_dst",
            "ruleset": "rs-uuid",
            "ruleset_name": "demo",
            "mask_type": "database",
            "options": {"batch_size": 1000},
            "status": "failed",
        }
    )
    client.start_masking_run.return_value = RunId(101)

    runner.invoke(app, ["run", "retry", "100", "-b"])

    (call,) = client.start_masking_run.call_args_list
    request: MaskingRunRequest = call.args[0]
    assert request.connection == "src-uuid"
    assert request.destination_connection == "dst-uuid"
    assert request.ruleset == "rs-uuid"
    assert request.options.batch_size == 1000
    assert request.name is not None
    assert request.name.startswith("my_src_retry_")


@patch(f"{MODULE}.get_client")
def test_retry_run_strips_server_managed_option_keys(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    # `get_run_info` echoes server-managed option keys the POST endpoint rejects.
    client.get_run_info.return_value = RunInfo.model_validate(
        {
            "id": 300,
            "source_connection": "src-uuid",
            "source_connection_name": "my_src",
            "ruleset": "rs-uuid",
            "ruleset_name": "demo",
            "mask_type": "database",
            "options": {
                "batch_size": 500,
                "run_secret": None,
                "has_run_secret": False,
                "future_server_only_field": "ignored",
            },
            "status": "failed",
        }
    )
    client.start_masking_run.return_value = RunId(301)

    runner.invoke(app, ["run", "retry", "300", "-b"])

    (call,) = client.start_masking_run.call_args_list
    request: MaskingRunRequest = call.args[0]
    assert request.options.batch_size == 500
    assert request.options.run_secret is None


@patch(f"{MODULE}.get_client")
def test_retry_run_aborts_when_original_missing_ruleset(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_run_info.return_value = RunInfo.model_validate(
        {
            "id": 200,
            "source_connection": "src-uuid",
            "source_connection_name": "my_src",
            "ruleset": None,
            "ruleset_name": "demo",
            "mask_type": "database",
            "status": "failed",
        }
    )

    result = runner.invoke(app, ["run", "retry", "200"])

    assert result.exit_code != 0
    client.start_masking_run.assert_not_called()


# -- logs --follow ---------------------------------------------------------


@patch(f"{MODULE}.time")
@patch(f"{MODULE}.get_client")
def test_logs_follow_polls_until_terminal(mock_get_client: MagicMock, _mock_time: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_run_log.side_effect = ["line 1\n", "line 1\nline 2\n", "line 1\nline 2\nline 3\n"]
    client.get_run_info.side_effect = [
        _run_info(status="running"),
        _run_info(status="running"),
        _run_info(status="finished"),
    ]

    result = runner.invoke(app, ["run", "logs", "42", "--follow", "--json"])

    assert result.exit_code == 0
    assert client.get_run_log.call_count == 3
    assert client.get_run_info.call_count == 3
    assert "line 1" in result.stdout
    assert "line 2" in result.stdout
    assert "line 3" in result.stdout


@patch(f"{MODULE}.time")
@patch(f"{MODULE}.get_client")
def test_logs_follow_recovers_when_server_rotates_log(
    mock_get_client: MagicMock, _mock_time: MagicMock, runner: CliRunner
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    # Second poll returns a shorter log (server rotated / compacted).
    # Third poll adds a new line to the rotated buffer; it must still print.
    client.get_run_log.side_effect = [
        "old line 1\nold line 2\n",
        "fresh start\n",
        "fresh start\nnew line\n",
    ]
    client.get_run_info.side_effect = [
        _run_info(status="running"),
        _run_info(status="running"),
        _run_info(status="finished"),
    ]

    result = runner.invoke(app, ["run", "logs", "42", "--follow", "--json"])

    assert result.exit_code == 0
    assert "new line" in result.stdout


# -- _wait_for_run ---------------------------------------------------------


@patch(f"{MODULE}.time")
@patch(f"{MODULE}.get_client")
def test_wait_run_polls_until_terminal(mock_get_client: MagicMock, _mock_time: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_run_info.side_effect = [
        _run_info(id=1, status="queued"),
        _run_info(id=1, status="running"),
        _run_info(id=1, status="finished"),
    ]

    result = runner.invoke(app, ["run", "wait", "1"])
    assert result.exit_code == 0
    assert client.get_run_info.call_count == 3


@patch(f"{MODULE}.time")
@patch(f"{MODULE}.get_client")
def test_wait_run_failure_exits_1(mock_get_client: MagicMock, _mock_time: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_run_info.return_value = _run_info(id=1, status="failed")

    result = runner.invoke(app, ["run", "wait", "1"])
    assert result.exit_code == 1


# -- _print_pretty_logs ----------------------------------------------------


def test_print_pretty_logs_non_json_passthrough(capsys: pytest.CaptureFixture[str]) -> None:
    _print_pretty_logs("plain text log")
    assert "plain text log" in capsys.readouterr().out


def test_print_pretty_logs_multiline_message() -> None:
    log_data = json.dumps(
        [
            {
                "timestamp": "2025-01-01T00:00:00",
                "log_level": 40,
                "message": "line one\nline two",
            }
        ]
    )
    _print_pretty_logs(log_data)


@pytest.mark.parametrize(
    "level,expected_label",
    [
        (10, "DEBUG"),
        (20, "INFO"),
        (30, "WARN"),
        (40, "ERROR"),
        (50, "FATAL"),
    ],
)
def test_log_level_labels(level: int, expected_label: str) -> None:
    label, _style = _LOG_LEVEL_LABELS[level]
    assert label == expected_label


@patch(f"{MODULE}.get_client")
def test_run_report_echoes_to_stdout_when_no_output(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client
    mock_client.get_run_report.return_value = "id,table\n1,users\n"

    result = runner.invoke(app, ["run", "report", "42"])

    assert result.exit_code == 0
    assert "users" in result.stdout


@patch(f"{MODULE}.get_client")
def test_run_report_writes_file_when_output_given(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner, tmp_path
) -> None:
    mock_get_client.return_value = mock_client
    mock_client.get_run_report.return_value = "csv-body"

    out = tmp_path / "report.csv"
    result = runner.invoke(app, ["run", "report", "42", "--output", str(out)])

    assert result.exit_code == 0
    assert out.read_text() == "csv-body"


@patch(f"{MODULE}.get_client")
def test_run_report_aborts_with_friendly_message_on_404(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client
    mock_client.get_run_report.side_effect = DataMasqueApiError(
        "404 Not Found", response=SimpleNamespace(status_code=404)
    )

    result = runner.invoke(app, ["run", "report", "42"])

    assert result.exit_code != 0
    assert "No report available for run 42" in result.stderr
    assert "dm run status 42" in result.stderr
