from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app

pytestmark = pytest.mark.integration


def test_table_reference_get_aborts_on_missing(runner: CliRunner) -> None:
    result = runner.invoke(app, ["table-references", "get", "dm_int_never_exists_xyz"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not found" in result.stderr.lower()


def test_table_reference_create_update_delete_roundtrip(
    runner: CliRunner, connection_name: str, table_reference_name: str
) -> None:
    connection = runner.invoke(
        app,
        ["connections", "create", "--name", connection_name, "--type", "mounted_share", "--base-dir", "initial"],
    )
    assert connection.exit_code == 0

    create = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            table_reference_name,
            "--connection",
            connection_name,
            "--source",
            "identities/customers.csv",
        ],
    )
    assert create.exit_code == 0

    update = runner.invoke(
        app, ["table-references", "update", table_reference_name, "--source", "identities/updated.csv"]
    )
    assert update.exit_code == 0

    listing = runner.invoke(app, ["table-references", "list", "--json"])
    assert listing.exit_code == 0
    entry = next(r for r in json.loads(listing.stdout) if r["name"] == table_reference_name)
    assert entry["source"] == "identities/updated.csv"

    get_detail = runner.invoke(app, ["table-references", "get", table_reference_name])
    assert get_detail.exit_code == 0
    assert "identities/updated.csv" in get_detail.stdout

    delete = runner.invoke(app, ["table-references", "delete", table_reference_name, "--yes"])
    assert delete.exit_code == 0


def test_table_reference_update_aborts_with_no_fields(
    runner: CliRunner, connection_name: str, table_reference_name: str
) -> None:
    connection = runner.invoke(
        app, ["connections", "create", "--name", connection_name, "--type", "mounted_share", "--base-dir", "x"]
    )
    assert connection.exit_code == 0
    create = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            table_reference_name,
            "--connection",
            connection_name,
            "--source",
            "identities/customers.csv",
        ],
    )
    assert create.exit_code == 0

    result = runner.invoke(app, ["table-references", "update", table_reference_name])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "at least one field" in result.stderr.lower()
