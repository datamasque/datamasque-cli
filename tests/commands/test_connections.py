from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.models.connection import (
    DatabaseConnectionConfig,
    DatabaseType,
    MountedShareConnectionConfig,
)
from typer.testing import CliRunner

from datamasque_cli.commands.connections import _format_role
from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.connections"


# -- _format_role (tests role inference per connection type) --------------


@pytest.mark.parametrize(
    ("is_source", "is_destination", "expected"),
    [
        (True, False, "source"),
        (False, True, "destination"),
        (True, True, "source+destination"),
        (False, False, "—"),
    ],
)
def test_format_role_for_file_connections(is_source: bool, is_destination: bool, expected: str) -> None:
    conn = MountedShareConnectionConfig(
        name="files",
        base_directory="/data",
        is_file_mask_source=is_source,
        is_file_mask_destination=is_destination,
    )
    assert _format_role(conn) == expected


def test_format_role_for_database_connections_is_always_source() -> None:
    conn = DatabaseConnectionConfig(
        name="db",
        host="localhost",
        port="5432",
        database="mydb",
        user="u",
        password="p",
        database_type=DatabaseType.postgres,
    )
    assert _format_role(conn) == "source"


@patch(f"{MODULE}.get_client")
def test_list_connections_includes_role_column(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [
        MountedShareConnectionConfig(
            name="input", base_directory="/in", is_file_mask_source=True, is_file_mask_destination=False
        ),
        MountedShareConnectionConfig(
            name="output", base_directory="/out", is_file_mask_source=False, is_file_mask_destination=True
        ),
    ]

    result = runner.invoke(app, ["connections", "list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    roles = {entry["name"]: entry["role"] for entry in payload}
    assert roles == {"input": "source", "output": "destination"}


# -- create (tests _build_connection_config logic) -------------------------


@patch(f"{MODULE}.get_client")
def test_create_connection_database(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    result = runner.invoke(
        app,
        [
            "connections",
            "create",
            "--name",
            "test_db",
            "--type",
            "database",
            "--db-type",
            "postgres",
            "--host",
            "localhost",
            "--port",
            "5432",
            "--database",
            "mydb",
            "--user",
            "admin",
            "--password",
            "secret",
        ],
    )
    assert result.exit_code == 0
    client.create_or_update_connection.assert_called_once()


@patch(f"{MODULE}.get_client")
def test_create_connection_mounted_share(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    result = runner.invoke(
        app,
        [
            "connections",
            "create",
            "--name",
            "input",
            "--type",
            "mounted_share",
            "--base-dir",
            "/data",
            "--source",
        ],
    )
    assert result.exit_code == 0
    client.create_or_update_connection.assert_called_once()


@patch(f"{MODULE}.get_client")
def test_create_connection_missing_name_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    mock_get_client.return_value = MagicMock()
    result = runner.invoke(app, ["connections", "create", "--type", "database"])
    assert result.exit_code != 0


@patch(f"{MODULE}.get_client")
def test_create_connection_from_json_file(mock_get_client: MagicMock, runner: CliRunner, tmp_path: MagicMock) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    conn_file = tmp_path / "conn.json"
    conn_file.write_text(
        json.dumps(
            {
                "type": "database",
                "name": "from_file",
                "host": "localhost",
                "port": "5432",
                "database": "mydb",
                "user": "admin",
                "password": "secret",
                "database_type": "postgres",
            }
        )
    )

    result = runner.invoke(app, ["connections", "create", "--file", str(conn_file)])
    assert result.exit_code == 0
    client.create_or_update_connection.assert_called_once()


# -- delete (tests confirmation logic) ------------------------------------


@patch(f"{MODULE}.get_client")
def test_delete_connection_confirmed(mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner) -> None:
    mock_get_client.return_value = mock_client

    runner.invoke(app, ["connections", "delete", "my_conn", "--yes"])
    mock_client.delete_connection_by_name_if_exists.assert_called_once_with("my_conn")


@patch(f"{MODULE}.get_client")
def test_delete_connection_declined(mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner) -> None:
    mock_get_client.return_value = mock_client

    runner.invoke(app, ["connections", "delete", "my_conn"], input="n\n")
    mock_client.delete_connection_by_name_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_connection_aborts_when_missing(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client

    result = runner.invoke(app, ["connections", "delete", "no_such_conn", "--yes"])

    assert result.exit_code != 0
    mock_client.delete_connection_by_name_if_exists.assert_not_called()


# -- test (reachability check) --------------------------------------------


@patch(f"{MODULE}.get_client")
def test_test_connection_posts_to_test_endpoint(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = b""
    mock_client.make_request.return_value = mock_response

    result = runner.invoke(app, ["connections", "test", "my_conn"])

    assert result.exit_code == 0
    mock_client.make_request.assert_called_once_with("POST", "/api/connections/1/test/", data={})


@patch(f"{MODULE}.get_client")
def test_test_connection_aborts_when_missing(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client

    result = runner.invoke(app, ["connections", "test", "no_such_conn"])

    assert result.exit_code != 0
    mock_client.make_request.assert_not_called()


# -- update (partial in-place edit) ---------------------------------------


@patch(f"{MODULE}.get_client")
def test_update_connection_patches_changed_fields(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client

    result = runner.invoke(
        app, ["connections", "update", "my_conn", "--password", "new-pw", "--host", "db2.example.com"]
    )

    assert result.exit_code == 0
    mock_client.make_request.assert_called_once_with(
        "PATCH",
        "/api/connections/1/",
        data={"host": "db2.example.com", "password": "new-pw"},
    )


@patch(f"{MODULE}.get_client")
def test_update_connection_aborts_without_any_fields(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client

    result = runner.invoke(app, ["connections", "update", "my_conn"])

    assert result.exit_code != 0
    mock_client.make_request.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_update_connection_aborts_when_missing(
    mock_get_client: MagicMock, mock_client: MagicMock, runner: CliRunner
) -> None:
    mock_get_client.return_value = mock_client

    result = runner.invoke(app, ["connections", "update", "no_such_conn", "--password", "x"])

    assert result.exit_code != 0
    mock_client.make_request.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_get_connection_redacts_password(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_connections.return_value = [
        DatabaseConnectionConfig(
            name="db",
            host="localhost",
            port="5432",
            database="mydb",
            user="admin",
            password="s3cret",
            database_type=DatabaseType.postgres,
        )
    ]

    result = runner.invoke(app, ["connections", "get", "db", "--json"])

    assert result.exit_code == 0
    assert "s3cret" not in result.stdout
    assert "<redacted>" in result.stdout
