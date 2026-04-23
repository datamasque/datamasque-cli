from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app

pytestmark = pytest.mark.integration


def test_connection_test_aborts_on_missing_connection(runner: CliRunner) -> None:
    result = runner.invoke(app, ["connections", "test", "dm_int_never_exists_xyz"])

    assert result.exit_code != 0
    assert "not found" in result.stderr.lower()


def test_connection_create_update_delete_roundtrip(runner: CliRunner, connection_name: str) -> None:
    create = runner.invoke(
        app,
        ["connections", "create", "--name", connection_name, "--type", "mounted_share", "--base-dir", "initial"],
    )
    assert create.exit_code == 0

    update = runner.invoke(app, ["connections", "update", connection_name, "--base-dir", "updated"])
    assert update.exit_code == 0

    listing = runner.invoke(app, ["connections", "list", "--json"])
    entry = next(c for c in json.loads(listing.stdout) if c["name"] == connection_name)
    assert entry["type"] == "MountedShare"

    get_detail = runner.invoke(app, ["connections", "get", connection_name])
    assert "updated" in get_detail.stdout
    assert "initial" not in get_detail.stdout

    delete = runner.invoke(app, ["connections", "delete", connection_name, "--yes"])
    assert delete.exit_code == 0


def test_connection_update_aborts_with_no_fields(runner: CliRunner, connection_name: str) -> None:
    runner.invoke(
        app,
        ["connections", "create", "--name", connection_name, "--type", "mounted_share", "--base-dir", "x"],
    )

    result = runner.invoke(app, ["connections", "update", connection_name])

    assert result.exit_code != 0
    assert "at least one field" in result.stderr.lower()
