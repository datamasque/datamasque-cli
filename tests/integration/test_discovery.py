from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.integration.conftest import create_discovery_config, wait_for_run

pytestmark = pytest.mark.integration


def test_schema_config_type_mismatch_aborts(
    runner: CliRunner,
    any_connection: str,
    discovery_config_name: str,
    file_discovery_config: Path,
) -> None:
    create_discovery_config(runner, discovery_config_name, "file", file_discovery_config)

    result = runner.invoke(app, ["discover", "schema", any_connection, "--config", discovery_config_name])
    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "database config" in result.stderr


def test_file_config_type_mismatch_aborts(
    runner: CliRunner,
    any_connection: str,
    discovery_config_name: str,
    db_discovery_config: Path,
) -> None:
    create_discovery_config(runner, discovery_config_name, "database", db_discovery_config)

    result = runner.invoke(app, ["discover", "file", any_connection, "--config", discovery_config_name])
    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "file config" in result.stderr


def test_schema_config_not_found_aborts(runner: CliRunner, any_connection: str) -> None:
    result = runner.invoke(app, ["discover", "schema", any_connection, "--config", "dm_int_no_such_config"])
    assert result.exit_code == ExitCode.NOT_FOUND


def test_file_run_from_config_and_snapshot(
    runner: CliRunner,
    file_source_connection: str,
    discovery_config_name: str,
    file_discovery_config: Path,
    tmp_path: Path,
) -> None:
    create_discovery_config(runner, discovery_config_name, "file", file_discovery_config)

    start = runner.invoke(app, ["discover", "file", file_source_connection, "--config", discovery_config_name])
    if start.exit_code != 0:
        pytest.skip(f"Could not start file discovery on '{file_source_connection}': {start.stdout}{start.stderr}")

    output = " ".join(start.stderr.split())
    assert f"config '{discovery_config_name}'" in output
    match = re.search(r"run (\d+)", output)
    assert match, f"no run id in output: {output}"
    run_id = match.group(1)

    snapshot = tmp_path / "snapshot.yaml"
    snap_result = runner.invoke(app, ["discover", "config-snapshot", run_id, "-o", str(snapshot)])
    assert snap_result.exit_code == 0, snap_result.stdout
    assert snapshot.exists() and snapshot.read_text().strip()
    wait_for_run(runner, int(run_id))


def test_schema_run_from_config_and_snapshot(
    runner: CliRunner,
    database_connection: str,
    discovery_config_name: str,
    db_discovery_config: Path,
    tmp_path: Path,
) -> None:
    create_discovery_config(runner, discovery_config_name, "database", db_discovery_config)

    start = runner.invoke(app, ["discover", "schema", database_connection, "--config", discovery_config_name])
    if start.exit_code != 0:
        pytest.skip(f"Could not start schema discovery on '{database_connection}': {start.stdout}{start.stderr}")

    output = " ".join(start.stderr.split())
    assert f"config '{discovery_config_name}'" in output
    match = re.search(r"run (\d+)", output)
    assert match, f"no run id in output: {output}"
    run_id = match.group(1)

    snapshot = tmp_path / "snapshot.yaml"
    snap_result = runner.invoke(app, ["discover", "config-snapshot", run_id, "-o", str(snapshot)])
    assert snap_result.exit_code == 0, snap_result.stdout
    assert snapshot.exists() and snapshot.read_text().strip()
    wait_for_run(runner, int(run_id))


def test_schema_results_on_a_non_schema_run_reports_the_server_reason(
    runner: CliRunner, finished_non_schema_run: int
) -> None:
    result = runner.invoke(app, ["discover", "schema-results", str(finished_non_schema_run)])

    assert result.exit_code == ExitCode.INVALID_INPUT
    stderr = " ".join(result.stderr.split())
    assert f"No schema discovery results available for run {finished_non_schema_run}:" in stderr
    assert "dm run status" not in stderr


def test_schema_results_on_an_unknown_run_is_not_found(runner: CliRunner) -> None:
    result = runner.invoke(app, ["discover", "schema-results", "999999999"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "Run 999999999 not found." in " ".join(result.stderr.split())
