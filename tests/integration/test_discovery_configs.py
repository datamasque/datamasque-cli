from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.integration.conftest import (
    DISCOVERY_TEST_NAMESPACE,
    create_discovery_config,
    create_discovery_config_library,
    get_error_envelope_from_stderr,
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


def test_config_validate_rejects_invalid_yaml(
    runner: CliRunner, invalid_discovery_yaml: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")

    result = runner.invoke(
        app, ["discover", "configs", "validate", "-f", str(invalid_discovery_yaml), "--type", "database"]
    )

    assert result.exit_code == ExitCode.INVALID_INPUT
    error = get_error_envelope_from_stderr(result.stderr)
    assert error["code"] == "invalid_input"
    assert error["message"].startswith(f'Discovery config "{invalid_discovery_yaml.name}" is invalid: ')


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


def test_library_validate_rejects_invalid_yaml(
    runner: CliRunner, invalid_discovery_yaml: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")

    result = runner.invoke(app, ["discover", "libraries", "validate", "-f", str(invalid_discovery_yaml)])

    assert result.exit_code == ExitCode.INVALID_INPUT
    error = get_error_envelope_from_stderr(result.stderr)
    assert error["code"] == "invalid_input"
    assert error["message"].startswith(f'Discovery config library "{invalid_discovery_yaml.name}" is invalid: ')


def test_library_delete_refuses_while_imported_then_force_succeeds(
    runner: CliRunner,
    discovery_library_name: str,
    discovery_config_name: str,
    tmp_path: Path,
) -> None:
    library = tmp_path / "importable.yaml"
    library.write_text(
        "labels:\n"
        "  - name: dm_int_label\n"
        "    description: Integration test label\n"
        "    categories: [PII]\n"
        "metadata_rules:\n"
        "  - name: DM Int Rule\n"
        "    label: dm_int_label\n"
        "    column:\n"
        "      type: regex\n"
        "      pattern: dm_int_column\n"
    )
    create_discovery_config_library(runner, discovery_library_name, library, namespace=DISCOVERY_TEST_NAMESPACE)

    ref = f"{DISCOVERY_TEST_NAMESPACE}/{discovery_library_name}"
    config = tmp_path / "importing.yaml"
    config.write_text(
        f"imports:\n"
        f"- {ref}\n"
        f"labels:\n"
        f'  $ref: "{ref}#labels"\n'
        f"metadata_rules:\n"
        f'  $ref: "{ref}#metadata_rules"\n'
        f"idd_rules: []\n"
        f"files:\n"
        f"  include:\n"
        f'  - "*.csv"\n'
    )
    create_discovery_config(runner, discovery_config_name, "file", config)

    delete = [
        "discover",
        "libraries",
        "delete",
        discovery_library_name,
        "--namespace",
        DISCOVERY_TEST_NAMESPACE,
        "--yes",
    ]

    conflict = runner.invoke(app, delete)
    assert conflict.exit_code == ExitCode.CONFLICT
    assert "--force" in " ".join(conflict.stderr.split())

    forced = runner.invoke(app, [*delete, "--force"])
    assert forced.exit_code == ExitCode.OK

    status = runner.invoke(app, ["discover", "configs", "status", discovery_config_name, "--type", "file", "--json"])
    assert json.loads(status.stdout)["status"] == "invalid"


# --- status ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("is_valid_yaml", "expected_status"),
    [
        (True, "valid"),
        (False, "invalid"),
    ],
    ids=["valid", "invalid"],
)
def test_config_status_reports_stored_validation_state(
    runner: CliRunner,
    discovery_config_name: str,
    db_discovery_config: Path,
    invalid_discovery_yaml: Path,
    is_valid_yaml: bool,
    expected_status: str,
) -> None:
    source = db_discovery_config if is_valid_yaml else invalid_discovery_yaml
    create_discovery_config(runner, discovery_config_name, "database", source)

    result = runner.invoke(app, ["discover", "configs", "status", discovery_config_name, "--json"])

    assert result.exit_code == ExitCode.OK
    body = json.loads(result.stdout)
    assert body["status"] == expected_status
    if not is_valid_yaml:
        assert body["validation_error"]


@pytest.mark.parametrize(
    ("is_valid_yaml", "expected_status"),
    [
        (True, "valid"),
        (False, "invalid"),
    ],
    ids=["valid", "invalid"],
)
def test_library_status(
    runner: CliRunner,
    discovery_library_name: str,
    discovery_library_yaml: Path,
    invalid_discovery_yaml: Path,
    is_valid_yaml: bool,
    expected_status: str,
) -> None:
    source = discovery_library_yaml if is_valid_yaml else invalid_discovery_yaml
    create_discovery_config_library(runner, discovery_library_name, source)

    result = runner.invoke(app, ["discover", "libraries", "status", discovery_library_name, "--json"])

    assert result.exit_code == ExitCode.OK
    body = json.loads(result.stdout)
    assert body["status"] == expected_status
    if not is_valid_yaml:
        assert body["validation_error"]
