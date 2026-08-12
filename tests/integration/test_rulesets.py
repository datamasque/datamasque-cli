from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.integration.conftest import get_error_envelope_from_stderr

pytestmark = pytest.mark.integration


def test_same_name_different_types_coexist(
    runner: CliRunner,
    ruleset_name: str,
    file_yaml: Path,
    db_yaml: Path,
) -> None:
    file_create = runner.invoke(
        app, ["rulesets", "create", "--name", ruleset_name, "--file", str(file_yaml), "--type", "file"]
    )
    db_create = runner.invoke(
        app, ["rulesets", "create", "--name", ruleset_name, "--file", str(db_yaml), "--type", "database"]
    )
    listing = runner.invoke(app, ["rulesets", "list"])

    assert file_create.exit_code == 0
    assert db_create.exit_code == 0
    matches = [line for line in listing.stdout.splitlines() if ruleset_name in line]
    assert len(matches) == 2


def test_create_without_type_aborts_when_name_is_ambiguous(
    runner: CliRunner,
    ruleset_name: str,
    file_yaml: Path,
    db_yaml: Path,
) -> None:
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(file_yaml), "--type", "file"])
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(db_yaml), "--type", "database"])

    result = runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(file_yaml)])

    assert result.exit_code == ExitCode.AMBIGUOUS
    assert "Multiple rulesets" in result.stderr


def test_create_with_type_updates_only_matching_namespace(
    runner: CliRunner,
    ruleset_name: str,
    file_yaml: Path,
    db_yaml: Path,
    tmp_path: Path,
) -> None:
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(file_yaml), "--type", "file"])
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(db_yaml), "--type", "database"])

    updated_file = tmp_path / "updated.yaml"
    updated_file.write_text(file_yaml.read_text().replace("EMAIL", "PHONE"))
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(updated_file), "--type", "file"])

    file_after = runner.invoke(app, ["rulesets", "get", ruleset_name, "--type", "file", "--yaml"])
    db_after = runner.invoke(app, ["rulesets", "get", ruleset_name, "--type", "database", "--yaml"])

    assert "PHONE" in file_after.stdout
    assert "mask_table" in db_after.stdout


def test_delete_with_type_leaves_other_namespace_intact(
    runner: CliRunner,
    ruleset_name: str,
    file_yaml: Path,
    db_yaml: Path,
) -> None:
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(file_yaml), "--type", "file"])
    runner.invoke(app, ["rulesets", "create", "--name", ruleset_name, "--file", str(db_yaml), "--type", "database"])

    runner.invoke(app, ["rulesets", "delete", ruleset_name, "--type", "file", "--yes"])
    file_gone = runner.invoke(app, ["rulesets", "get", ruleset_name, "--type", "file", "--yaml"])
    db_still = runner.invoke(app, ["rulesets", "get", ruleset_name, "--type", "database", "--yaml"])

    assert file_gone.exit_code == ExitCode.NOT_FOUND
    assert db_still.exit_code == 0
    assert "mask_table" in db_still.stdout


# --- validate ----------------------------------------------------------------


def test_ruleset_validate_puts_the_reason_in_the_envelope(
    runner: CliRunner,
    invalid_ruleset_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(invalid_ruleset_yaml), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    error = get_error_envelope_from_stderr(result.stderr)
    assert error["code"] == "invalid_input"
    assert error["message"].startswith(f"Ruleset '{invalid_ruleset_yaml.name}' (database) is invalid: ")


def test_ruleset_validate_reports_the_position_of_each_error(
    runner: CliRunner,
    invalid_ruleset_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guards the assumption that the server gives a position, not only a message."""
    monkeypatch.setenv("DM_OUTPUT", "json")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(invalid_ruleset_yaml), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert re.search(r"\(line \d+", get_error_envelope_from_stderr(result.stderr)["message"])


def test_ruleset_library_validate_puts_the_reason_in_the_envelope(
    runner: CliRunner,
    ruleset_library_name: str,
    invalid_ruleset_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = runner.invoke(
        app, ["libraries", "create", "--name", ruleset_library_name, "--file", str(invalid_ruleset_yaml)]
    )
    assert create.exit_code == 0, create.stdout

    monkeypatch.setenv("DM_OUTPUT", "json")
    result = runner.invoke(app, ["libraries", "validate", ruleset_library_name])

    assert result.exit_code == ExitCode.INVALID_INPUT
    error = get_error_envelope_from_stderr(result.stderr)
    assert error["code"] == "invalid_input"
    assert error["message"].startswith(f"Library '{ruleset_library_name}' is invalid: ")


# --- status ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("is_valid_yaml", "expected_status"),
    [
        (True, "valid"),
        (False, "invalid"),
    ],
    ids=["valid", "invalid"],
)
def test_ruleset_status(
    runner: CliRunner,
    ruleset_name: str,
    db_yaml: Path,
    invalid_ruleset_yaml: Path,
    is_valid_yaml: bool,
    expected_status: str,
) -> None:
    source = db_yaml if is_valid_yaml else invalid_ruleset_yaml
    create = runner.invoke(
        app, ["rulesets", "create", "--name", ruleset_name, "--file", str(source), "--type", "database"]
    )
    assert create.exit_code == 0, create.stdout

    result = runner.invoke(app, ["rulesets", "status", ruleset_name, "--type", "database", "--json"])

    assert result.exit_code == ExitCode.OK
    body = json.loads(result.stdout)
    assert body["status"] == expected_status
    if not is_valid_yaml:
        assert body["errors"]


def test_ruleset_library_status_reports_invalid(
    runner: CliRunner,
    ruleset_library_name: str,
    invalid_ruleset_yaml: Path,
) -> None:
    create = runner.invoke(
        app, ["libraries", "create", "--name", ruleset_library_name, "--file", str(invalid_ruleset_yaml)]
    )
    assert create.exit_code == 0, create.stdout

    result = runner.invoke(app, ["libraries", "status", ruleset_library_name, "--json"])

    assert result.exit_code == ExitCode.OK
    body = json.loads(result.stdout)
    assert body["status"] == "invalid"
    assert body["errors"]
