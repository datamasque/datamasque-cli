from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app

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

    assert result.exit_code != 0
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

    assert file_gone.exit_code != 0
    assert db_still.exit_code == 0
    assert "mask_table" in db_still.stdout
