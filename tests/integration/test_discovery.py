"""Live-instance tests for configurable discovery."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app
from tests.integration.conftest import DISCOVERY_TEST_NAMESPACE

pytestmark = pytest.mark.integration


# --- discovery configs -------------------------------------------------------


def test_config_create_get_delete_lifecycle(
    runner: CliRunner,
    discovery_config_name: str,
    db_discovery_config: Path,
) -> None:
    create = runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            discovery_config_name,
            "--type",
            "database",
            "-f",
            str(db_discovery_config),
        ],
    )
    assert create.exit_code == 0, create.stdout

    get_yaml = runner.invoke(app, ["discover", "configs", "get", discovery_config_name, "--yaml"])
    assert get_yaml.exit_code == 0
    assert "labels:" in get_yaml.stdout

    listing = runner.invoke(app, ["discover", "configs", "list"])
    assert discovery_config_name in listing.stdout

    delete = runner.invoke(app, ["discover", "configs", "delete", discovery_config_name, "--yes"])
    assert delete.exit_code == 0

    gone = runner.invoke(app, ["discover", "configs", "get", discovery_config_name])
    assert gone.exit_code == 3


def test_config_validate_accepts_default_config(runner: CliRunner, db_discovery_config: Path) -> None:
    result = runner.invoke(
        app, ["discover", "configs", "validate", "-f", str(db_discovery_config), "--type", "database"]
    )
    assert result.exit_code == 0, result.stdout


def test_config_validate_rejects_invalid_yaml(runner: CliRunner, invalid_discovery_yaml: Path) -> None:
    result = runner.invoke(
        app, ["discover", "configs", "validate", "-f", str(invalid_discovery_yaml), "--type", "database"]
    )
    assert result.exit_code == 4
    assert "invalid" in result.stderr.lower()


def test_config_same_name_coexists_across_types(
    runner: CliRunner,
    discovery_config_name: str,
    db_discovery_config: Path,
    file_discovery_config: Path,
) -> None:
    db = runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            discovery_config_name,
            "--type",
            "database",
            "-f",
            str(db_discovery_config),
        ],
    )
    file = runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            discovery_config_name,
            "--type",
            "file",
            "-f",
            str(file_discovery_config),
        ],
    )
    assert db.exit_code == 0, db.stdout
    assert file.exit_code == 0, file.stdout

    listing = runner.invoke(app, ["discover", "configs", "list"])
    matches = [line for line in listing.stdout.splitlines() if discovery_config_name in line]
    assert len(matches) == 2


def test_config_create_without_type_aborts_when_ambiguous(
    runner: CliRunner,
    discovery_config_name: str,
    db_discovery_config: Path,
    file_discovery_config: Path,
) -> None:
    runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            discovery_config_name,
            "--type",
            "database",
            "-f",
            str(db_discovery_config),
        ],
    )
    runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            discovery_config_name,
            "--type",
            "file",
            "-f",
            str(file_discovery_config),
        ],
    )

    result = runner.invoke(
        app, ["discover", "configs", "create", "--name", discovery_config_name, "-f", str(db_discovery_config)]
    )

    assert result.exit_code != 0
    assert "Multiple discovery configs" in result.stderr


def test_config_get_missing_is_not_found(runner: CliRunner) -> None:
    result = runner.invoke(app, ["discover", "configs", "get", "dm_int_does_not_exist"])
    assert result.exit_code == 3


# --- discovery config libraries ----------------------------------------------


def test_library_create_get_delete_lifecycle(
    runner: CliRunner,
    discovery_library_name: str,
    discovery_library_yaml: Path,
) -> None:
    create = runner.invoke(
        app,
        [
            "discover",
            "libraries",
            "create",
            "--name",
            discovery_library_name,
            "--type",
            "database",
            "-f",
            str(discovery_library_yaml),
        ],
    )
    assert create.exit_code == 0, create.stdout

    get_yaml = runner.invoke(app, ["discover", "libraries", "get", discovery_library_name, "--yaml"])
    assert get_yaml.exit_code == 0

    listing = runner.invoke(app, ["discover", "libraries", "list"])
    assert discovery_library_name in listing.stdout

    delete = runner.invoke(app, ["discover", "libraries", "delete", discovery_library_name, "--yes"])
    assert delete.exit_code == 0

    gone = runner.invoke(app, ["discover", "libraries", "get", discovery_library_name])
    assert gone.exit_code == 3


def test_library_namespace_is_isolated(
    runner: CliRunner,
    discovery_library_name: str,
    discovery_library_yaml: Path,
) -> None:
    created = runner.invoke(
        app,
        [
            "discover",
            "libraries",
            "create",
            "--name",
            discovery_library_name,
            "--type",
            "database",
            "--namespace",
            DISCOVERY_TEST_NAMESPACE,
            "-f",
            str(discovery_library_yaml),
        ],
    )
    assert created.exit_code == 0, created.stdout

    in_namespace = runner.invoke(
        app, ["discover", "libraries", "get", discovery_library_name, "--namespace", DISCOVERY_TEST_NAMESPACE]
    )
    assert in_namespace.exit_code == 0

    default_namespace = runner.invoke(app, ["discover", "libraries", "get", discovery_library_name])
    assert default_namespace.exit_code == 3


def test_library_validate_rejects_invalid_yaml(runner: CliRunner, invalid_discovery_yaml: Path) -> None:
    result = runner.invoke(
        app, ["discover", "libraries", "validate", "-f", str(invalid_discovery_yaml), "--type", "database"]
    )
    assert result.exit_code == 4


# --- `--config` resolution guards (abort before any run starts) --------------


def test_schema_config_type_mismatch_aborts(
    runner: CliRunner,
    any_connection: str,
    discovery_config_name: str,
    file_discovery_config: Path,
) -> None:
    runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            discovery_config_name,
            "--type",
            "file",
            "-f",
            str(file_discovery_config),
        ],
    )
    result = runner.invoke(app, ["discover", "schema", any_connection, "--config", discovery_config_name])
    assert result.exit_code == 4
    assert "database config" in result.stderr


def test_file_config_type_mismatch_aborts(
    runner: CliRunner,
    any_connection: str,
    discovery_config_name: str,
    db_discovery_config: Path,
) -> None:
    runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            discovery_config_name,
            "--type",
            "database",
            "-f",
            str(db_discovery_config),
        ],
    )
    result = runner.invoke(app, ["discover", "file", any_connection, "--config", discovery_config_name])
    assert result.exit_code == 4
    assert "file config" in result.stderr


def test_schema_config_not_found_aborts(runner: CliRunner, any_connection: str) -> None:
    result = runner.invoke(app, ["discover", "schema", any_connection, "--config", "dm_int_no_such_config"])
    assert result.exit_code == 3


# --- run from config + config snapshot (env-gated) ---------------------------


def test_schema_run_from_config_and_snapshot(
    runner: CliRunner,
    database_connection: str,
    discovery_config_name: str,
    db_discovery_config: Path,
    tmp_path: Path,
) -> None:
    create = runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            discovery_config_name,
            "--type",
            "database",
            "-f",
            str(db_discovery_config),
        ],
    )
    assert create.exit_code == 0, create.stdout

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
