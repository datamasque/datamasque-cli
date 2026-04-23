"""Connection management commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.models.connection import (
    AzureConnectionConfig,
    ConnectionConfig,
    DatabaseConnectionConfig,
    DatabaseType,
    DynamoConnectionConfig,
    MountedShareConnectionConfig,
    S3ConnectionConfig,
    SnowflakeConnectionConfig,
)

from datamasque_cli.client import get_client
from datamasque_cli.output import abort, print_success, redact_sensitive_fields, render_output

_FILE_CONNECTION_TYPES = (MountedShareConnectionConfig, S3ConnectionConfig, AzureConnectionConfig)


def _format_role(conn: ConnectionConfig) -> str:
    """Return `source`, `destination`, `source+destination`, or `—` for a connection.

    Database-type connections always act as the source and mask in place,
    so there's no source/destination split to display.
    """
    if not isinstance(conn, _FILE_CONNECTION_TYPES):
        return "source"
    if conn.is_file_mask_source and conn.is_file_mask_destination:
        return "source+destination"
    if conn.is_file_mask_source:
        return "source"
    if conn.is_file_mask_destination:
        return "destination"
    return "—"


app = typer.Typer(help="Manage database and file connections.")

# Maps the `type` field in JSON to the right config class.
_CONNECTION_CLASSES = {
    "database": DatabaseConnectionConfig,
    "s3": S3ConnectionConfig,
    "azure": AzureConnectionConfig,
    "mounted_share": MountedShareConnectionConfig,
    "snowflake": SnowflakeConnectionConfig,
    "dynamodb": DynamoConnectionConfig,
}


@app.command("list")
def list_connections(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all configured connections."""
    client = get_client(profile)
    connections = client.list_connections()

    data = []
    for conn in connections:
        class_name = type(conn).__name__
        entry: dict[str, object] = {
            "id": conn.id,
            "name": conn.name,
            "type": class_name.replace("ConnectionConfig", "").replace("Config", ""),
            "role": _format_role(conn),
        }
        data.append(entry)

    render_output(
        data,
        is_json=is_json,
        columns=["id", "name", "type", "role"],
        title="Connections",
    )


@app.command("get")
def get_connection(
    name: str = typer.Argument(help="Connection name"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show details for a specific connection."""
    client = get_client(profile)
    connections = client.list_connections()

    match = next((c for c in connections if c.name == name), None)
    if match is None:
        abort(f"Connection '{name}' not found.")

    data = redact_sensitive_fields(match.model_dump())
    render_output(data, is_json=is_json, title=f"Connection: {name}")


@app.command("create")
def create_connection(
    file: Path | None = typer.Option(None, "--file", "-f", help="JSON file defining the connection"),
    name: str | None = typer.Option(None, help="Connection name"),
    conn_type: str | None = typer.Option(None, "--type", "-t", help="database, s3, azure, mounted_share"),
    host: str | None = typer.Option(None, help="Database host"),
    port: str | None = typer.Option(None, help="Database port"),
    database: str | None = typer.Option(None, help="Database name"),
    user: str | None = typer.Option(None, help="Database user"),
    password: str | None = typer.Option(None, help="Database password"),
    db_type: str | None = typer.Option(None, "--db-type", help="postgres, mysql, oracle, mssql, mariadb, etc."),
    schema: str | None = typer.Option(None, help="Schema name"),
    base_directory: str | None = typer.Option(None, "--base-dir", help="Base directory (file connections)"),
    is_source: bool = typer.Option(False, "--source", help="Is a file mask source"),
    is_destination: bool = typer.Option(False, "--destination", help="Is a file mask destination"),
    bucket: str | None = typer.Option(None, help="S3 bucket name"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a connection.

    Use --file for full control (JSON), or flags for quick database/file connections.

    Examples:

        # From JSON file (any connection type)
        dm connections create --file connection.json

        # Quick database connection
        dm connections create --name mydb --type database --db-type postgres \\
            --host db.example.com --port 5432 --database mydb --user admin --password secret

        # Quick mounted share
        dm connections create --name input --type mounted_share --base-dir my-data --source
    """
    client = get_client(profile)

    if file is not None:
        _create_from_file(client, file)
        return

    if name is None or conn_type is None:
        abort("Provide either --file or both --name and --type.")

    config = _build_connection_config(
        name=name,
        conn_type=conn_type,
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        db_type=db_type,
        schema=schema,
        base_directory=base_directory,
        is_source=is_source,
        is_destination=is_destination,
        bucket=bucket,
    )

    client.create_or_update_connection(config)
    print_success(f"Connection '{name}' created/updated.")


def _create_from_file(client: DataMasqueClient, file: Path) -> None:
    """Create a connection from a JSON file."""
    data = json.loads(file.read_text())
    conn_type = data.pop("type", "database")

    if conn_type not in _CONNECTION_CLASSES:
        valid = ", ".join(_CONNECTION_CLASSES)
        abort(f"Unknown connection type '{conn_type}'. Valid: {valid}")

    # Convert db_type string to enum for database connections
    if conn_type == "database" and "database_type" in data:
        data["database_type"] = DatabaseType(data["database_type"])

    klass = _CONNECTION_CLASSES[conn_type]
    config = klass(**data)
    client.create_or_update_connection(config)
    print_success(f"Connection '{config.name}' created/updated.")


def _build_connection_config(
    *,
    name: str,
    conn_type: str,
    host: str | None,
    port: str | None,
    database: str | None,
    user: str | None,
    password: str | None,
    db_type: str | None,
    schema: str | None,
    base_directory: str | None,
    is_source: bool,
    is_destination: bool,
    bucket: str | None,
) -> DatabaseConnectionConfig | S3ConnectionConfig | MountedShareConnectionConfig:
    """Build a connection config from CLI flags."""
    if conn_type == "database":
        if not all([host, port, database, user, password, db_type]):
            abort("Database connections require: --host, --port, --database, --user, --password, --db-type")
        return DatabaseConnectionConfig(
            name=name,
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            database_type=DatabaseType(db_type),
            schema=schema,
        )

    if conn_type == "mounted_share":
        if base_directory is None:
            abort("Mounted share connections require: --base-dir")
        return MountedShareConnectionConfig(
            name=name,
            base_directory=base_directory,
            is_file_mask_source=is_source,
            is_file_mask_destination=is_destination,
        )

    if conn_type == "s3":
        if base_directory is None or bucket is None:
            abort("S3 connections require: --base-dir, --bucket")
        return S3ConnectionConfig(
            name=name,
            base_directory=base_directory,
            bucket=bucket,
            is_file_mask_source=is_source,
            is_file_mask_destination=is_destination,
        )

    abort(f"Use --file for '{conn_type}' connections (too many fields for CLI flags).")


@app.command("test")
def test_connection(
    name: str = typer.Argument(help="Connection name or ID to test"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Verify a connection can reach its target.

    Posts the stored connection to the server's test endpoint, which attempts
    an actual database handshake or filesystem/bucket open and reports
    success, a warning, or a hard failure.
    """
    client = get_client(profile)

    match = next((c for c in client.list_connections() if c.name == name or str(c.id) == name), None)
    if match is None:
        abort(f"Connection '{name}' not found.")

    response = client.make_request("POST", f"/api/connections/{match.id}/test/", data={})
    body = response.json() if response.content else {}
    warning = body.get("message") if isinstance(body, dict) else None

    if warning:
        print_success(f"Connection '{match.name}' reachable (warning: {warning}).")
    else:
        print_success(f"Connection '{match.name}' reachable.")


@app.command("update")
def update_connection(
    name: str = typer.Argument(help="Connection name or ID to update"),
    host: str | None = typer.Option(None, help="New database host"),
    port: str | None = typer.Option(None, help="New database port"),
    database: str | None = typer.Option(None, help="New database name"),
    user: str | None = typer.Option(None, help="New database user"),
    password: str | None = typer.Option(None, help="New database password"),
    schema: str | None = typer.Option(None, help="New schema name"),
    base_directory: str | None = typer.Option(None, "--base-dir", help="New base directory (file connections)"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Update selected fields on an existing connection without recreating it.

    Preserves the connection's UUID, so any ruleset or run history that
    references it stays intact. Pass only the fields that should change.
    """
    client = get_client(profile)

    match = next((c for c in client.list_connections() if c.name == name or str(c.id) == name), None)
    if match is None:
        abort(f"Connection '{name}' not found.")

    updates: dict[str, object] = {
        key: value
        for key, value in {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
            "schema": schema,
            "base_directory": base_directory,
        }.items()
        if value is not None
    }
    if not updates:
        abort("Pass at least one field to update (e.g. --password, --host).")

    client.make_request("PATCH", f"/api/connections/{match.id}/", data=updates)
    print_success(f"Connection '{match.name}' updated: {', '.join(updates)}.")


@app.command("delete")
def delete_connection(
    name: str = typer.Argument(help="Connection name to delete"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a connection by name."""
    client = get_client(profile)
    if not any(c.name == name for c in client.list_connections()):
        abort(f"Connection '{name}' not found.")

    if not is_confirmed:
        typer.confirm(f"Delete connection '{name}'?", abort=True)

    client.delete_connection_by_name_if_exists(name)
    print_success(f"Connection '{name}' deleted.")
