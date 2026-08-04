from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app
from datamasque_cli.output import ExitCode
from tests.integration.conftest import (
    DISCOVERY_TEST_NAMESPACE,
    create_discovery_config,
    create_discovery_config_library,
)

pytestmark = pytest.mark.integration


# --- discovery configs -------------------------------------------------------


def test_config_create_get_delete_lifecycle(
    runner: CliRunner,
    discovery_config_name: str,
    db_discovery_config: Path,
) -> None:
    create_discovery_config(runner, discovery_config_name, "database", db_discovery_config)

    get_yaml = runner.invoke(app, ["discover", "configs", "get", discovery_config_name, "--yaml"])
    assert get_yaml.exit_code == 0
    assert "labels:" in get_yaml.stdout

    listing = runner.invoke(app, ["discover", "configs", "list"])
    assert discovery_config_name in listing.stdout

    delete = runner.invoke(app, ["discover", "configs", "delete", discovery_config_name, "--yes"])
    assert delete.exit_code == 0

    gone = runner.invoke(app, ["discover", "configs", "get", discovery_config_name])
    assert gone.exit_code == ExitCode.NOT_FOUND


def test_config_validate_accepts_default_config(runner: CliRunner, db_discovery_config: Path) -> None:
    result = runner.invoke(
        app, ["discover", "configs", "validate", "-f", str(db_discovery_config), "--type", "database"]
    )
    assert result.exit_code == 0, result.stdout


def test_config_validate_rejects_invalid_yaml(runner: CliRunner, invalid_discovery_yaml: Path) -> None:
    result = runner.invoke(
        app, ["discover", "configs", "validate", "-f", str(invalid_discovery_yaml), "--type", "database"]
    )
    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "invalid" in result.stderr.lower()


def test_config_same_name_coexists_across_types(
    runner: CliRunner,
    discovery_config_name: str,
    db_discovery_config: Path,
    file_discovery_config: Path,
) -> None:
    create_discovery_config(runner, discovery_config_name, "database", db_discovery_config)
    create_discovery_config(runner, discovery_config_name, "file", file_discovery_config)

    listing = runner.invoke(app, ["discover", "configs", "list"])
    matches = [line for line in listing.stdout.splitlines() if discovery_config_name in line]
    assert len(matches) == 2


def test_config_create_without_type_aborts_when_ambiguous(
    runner: CliRunner,
    discovery_config_name: str,
    db_discovery_config: Path,
    file_discovery_config: Path,
) -> None:
    create_discovery_config(runner, discovery_config_name, "database", db_discovery_config)
    create_discovery_config(runner, discovery_config_name, "file", file_discovery_config)

    result = runner.invoke(
        app, ["discover", "configs", "create", "--name", discovery_config_name, "-f", str(db_discovery_config)]
    )

    assert result.exit_code == ExitCode.AMBIGUOUS
    assert "Multiple discovery configs" in result.stderr


def test_config_get_missing_is_not_found(runner: CliRunner) -> None:
    result = runner.invoke(app, ["discover", "configs", "get", "dm_int_does_not_exist"])
    assert result.exit_code == ExitCode.NOT_FOUND


# --- discovery config libraries ----------------------------------------------


def test_library_create_get_delete_lifecycle(
    runner: CliRunner,
    discovery_library_name: str,
    discovery_library_yaml: Path,
) -> None:
    create_discovery_config_library(runner, discovery_library_name, discovery_library_yaml)

    get_yaml = runner.invoke(app, ["discover", "libraries", "get", discovery_library_name, "--yaml"])
    assert get_yaml.exit_code == 0

    listing = runner.invoke(app, ["discover", "libraries", "list"])
    assert discovery_library_name in listing.stdout

    delete = runner.invoke(app, ["discover", "libraries", "delete", discovery_library_name, "--yes"])
    assert delete.exit_code == 0

    gone = runner.invoke(app, ["discover", "libraries", "get", discovery_library_name])
    assert gone.exit_code == ExitCode.NOT_FOUND


def test_library_namespace_is_isolated(
    runner: CliRunner,
    discovery_library_name: str,
    discovery_library_yaml: Path,
) -> None:
    create_discovery_config_library(
        runner, discovery_library_name, discovery_library_yaml, namespace=DISCOVERY_TEST_NAMESPACE
    )

    in_namespace = runner.invoke(
        app, ["discover", "libraries", "get", discovery_library_name, "--namespace", DISCOVERY_TEST_NAMESPACE]
    )
    assert in_namespace.exit_code == 0

    default_namespace = runner.invoke(app, ["discover", "libraries", "get", discovery_library_name])
    assert default_namespace.exit_code == ExitCode.NOT_FOUND


def test_library_validate_rejects_invalid_yaml(runner: CliRunner, invalid_discovery_yaml: Path) -> None:
    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(invalid_discovery_yaml)])
    assert result.exit_code == ExitCode.INVALID_INPUT
