from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app
from tests.integration.conftest import wait_for_run

pytestmark = pytest.mark.integration


def _start_background_run(runner: CliRunner, source: str, destination: str, ruleset: str) -> int:
    result = runner.invoke(
        app,
        ["run", "start", "-c", source, "-r", ruleset, "-d", destination, "--background", "--json"],
    )
    assert result.exit_code == 0, f"run start failed: {result.stdout}"
    return int(json.loads(result.stdout)["id"])


def test_run_start_finishes_for_file_masking(
    runner: CliRunner,
    ruleset_name: str,
    fast_file_yaml: Path,
    file_connection_pair: tuple[str, str],
) -> None:
    source, destination = file_connection_pair
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(fast_file_yaml), "--type", "file"])

    run_id = _start_background_run(runner, source, destination, ruleset_name)
    status = wait_for_run(runner, run_id)

    assert status in {"finished", "finished_with_warnings"}


def test_run_retry_chain_starts_a_new_run(
    runner: CliRunner,
    ruleset_name: str,
    fast_file_yaml: Path,
    file_connection_pair: tuple[str, str],
) -> None:
    """Regression: v0.4.0's retry blindly echoed server-managed option keys
    like `run_secret` back to the create endpoint, triggering a 400. Fixed
    in v0.4.1. This test exercises the full chain end-to-end."""
    source, destination = file_connection_pair
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(fast_file_yaml), "--type", "file"])

    original_id = _start_background_run(runner, source, destination, ruleset_name)
    wait_for_run(runner, original_id)

    retry = runner.invoke(app, ["run", "retry", str(original_id), "--background", "--json"])

    assert retry.exit_code == 0, f"run retry failed: {retry.stdout}"
    retry_id = int(json.loads(retry.stdout)["id"])
    assert retry_id != original_id
    assert wait_for_run(runner, retry_id) in {"finished", "finished_with_warnings"}


def test_run_logs_follow_on_finished_run_prints_and_exits(
    runner: CliRunner,
    ruleset_name: str,
    fast_file_yaml: Path,
    file_connection_pair: tuple[str, str],
) -> None:
    source, destination = file_connection_pair
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(fast_file_yaml), "--type", "file"])

    run_id = _start_background_run(runner, source, destination, ruleset_name)
    wait_for_run(runner, run_id)

    result = runner.invoke(app, ["run", "logs", str(run_id), "--follow"])

    assert result.exit_code == 0
    assert "Masking" in result.stdout or "masked" in result.stdout.lower()


def test_run_start_passes_options_end_to_end(
    runner: CliRunner,
    ruleset_name: str,
    fast_file_yaml: Path,
    file_connection_pair: tuple[str, str],
) -> None:
    """The unit suite covers `--options` parsing; this proves the server
    actually accepts the resulting payload shape and the run still
    completes."""
    source, destination = file_connection_pair
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(fast_file_yaml), "--type", "file"])

    result = runner.invoke(
        app,
        [
            "run",
            "start",
            "-c",
            source,
            "-r",
            ruleset_name,
            "-d",
            destination,
            "--options",
            "continue_on_failure=false",
            "--options",
            "diagnostic_logging=false",
            "--background",
            "--json",
        ],
    )

    assert result.exit_code == 0, f"run start --options failed: {result.stdout}"
    run_id = int(json.loads(result.stdout)["id"])
    assert wait_for_run(runner, run_id) in {"finished", "finished_with_warnings"}
