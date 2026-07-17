"""Schema discovery and sensitive data discovery commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient, RunId
from datamasque.client.models.connection import ConnectionId
from datamasque.client.models.discovery import (
    FileDataDiscoveryFromConfigRequest,
    FileDataDiscoveryRequest,
    SchemaDiscoveryFromConfigRequest,
    SchemaDiscoveryRequest,
)
from datamasque.client.models.discovery_config import DiscoveryConfigId, DiscoveryConfigType

from datamasque_cli.client import get_client
from datamasque_cli.commands import discovery_config_libraries, discovery_configs
from datamasque_cli.output import ErrorCode, abort, print_json, print_success, render_output, should_emit_json

app = typer.Typer(help="Data discovery operations.", no_args_is_help=True)
app.add_typer(discovery_configs.app, name="configs")
app.add_typer(discovery_config_libraries.app, name="libraries")


def _write_or_echo(content: str, output: Path | None, success_label: str) -> None:
    """Write `content` to `output` when given, otherwise echo to stdout."""
    if output is None:
        typer.echo(content)
        return
    output.write_text(content)
    print_success(f"{success_label} written to {output}")


def _resolve_connection_id(client: DataMasqueClient, name_or_id: str) -> str:
    """Resolve a connection name or ID to its UUID string."""
    match = next((c for c in client.list_connections() if c.name == name_or_id or str(c.id) == name_or_id), None)
    if match is None:
        abort(f"Connection '{name_or_id}' not found.", code=ErrorCode.NOT_FOUND)
    return str(match.id)


def _resolve_discovery_config_id(
    client: DataMasqueClient, name: str, expected_type: DiscoveryConfigType
) -> DiscoveryConfigId:
    """Resolve a discovery config name to its UUID, requiring it to be of `expected_type`."""
    named = [c for c in client.list_discovery_configs() if c.name == name]
    matches = [c for c in named if c.config_type is expected_type]

    if not matches:
        if named:
            existing = ", ".join(c.config_type.value for c in named)
            abort(
                f"Discovery config '{name}' exists as {existing}, "
                f"but {expected_type.value} discovery needs a {expected_type.value} config.",
                code=ErrorCode.INVALID_INPUT,
            )
        abort(f"Discovery config '{name}' not found.", code=ErrorCode.NOT_FOUND)
    if len(matches) > 1:
        options = "\n  ".join(f"id={c.id}" for c in matches)
        abort(
            f"Multiple {expected_type.value} discovery configs named '{name}':\n  {options}",
            code=ErrorCode.AMBIGUOUS,
        )

    config_id = matches[0].id
    assert config_id is not None
    return config_id


@app.command("schema")
def schema_discovery(
    connection: str = typer.Argument(help="Connection name or ID"),
    config: str | None = typer.Option(
        None, "--config", "-c", help="Run with a saved database discovery config (configurable discovery)"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Start a schema-discovery run on a connection.

    Results are scoped to a run ID, not a connection, so use
    `dm discover schema-results <run-id>` once this run reaches a terminal state
    (poll with `dm run status <run-id>`).
    """
    client = get_client(profile)
    conn_id = _resolve_connection_id(client, connection)

    if config is not None:
        config_id = _resolve_discovery_config_id(client, config, DiscoveryConfigType.database)
        from_config = SchemaDiscoveryFromConfigRequest(connection=ConnectionId(conn_id), discovery_config=config_id)
        run_id = client.start_schema_discovery_run_from_config(from_config)
        source = f"config '{config}'"
    else:
        request = SchemaDiscoveryRequest(connection=ConnectionId(conn_id))
        run_id = client.start_schema_discovery_run(request)
        source = "default discovery"

    print_success(
        f"Schema discovery run {run_id} started for connection '{connection}' ({source}). "
        f"Once finished, list results with: dm discover schema-results {run_id}"
    )


@app.command("file")
def file_discovery(
    connection: str = typer.Argument(help="Connection name or ID"),
    config: str | None = typer.Option(
        None, "--config", "-c", help="Run with a saved file discovery config (configurable discovery)"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Start a file-data-discovery run on a file connection.

    Once finished, download the report with `dm discover file-report <run-id>`
    (poll with `dm run status <run-id>`).
    """
    client = get_client(profile)
    conn_id = _resolve_connection_id(client, connection)

    if config is not None:
        config_id = _resolve_discovery_config_id(client, config, DiscoveryConfigType.file)
        from_config = FileDataDiscoveryFromConfigRequest(connection=ConnectionId(conn_id), discovery_config=config_id)
        run_id = client.start_file_data_discovery_run_from_config(from_config)
        source = f"config '{config}'"
    else:
        request = FileDataDiscoveryRequest(connection=ConnectionId(conn_id))
        run_id = client.start_file_data_discovery_run(request)
        source = "default discovery"

    print_success(
        f"File data discovery run {run_id} started for connection '{connection}' ({source}). "
        f"Once finished, download the report with: dm discover file-report {run_id}"
    )


@app.command("schema-results")
def schema_results(
    run_id: int = typer.Argument(help="Schema discovery run ID"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List schema-discovery results for a completed run (paginates server-side).

    Surfaces the detected `data_type`, the comma-joined classifier `matches`,
    and the column `constraint` (PK/UK/empty) from each result so the table
    output reflects what discovery actually found.
    """
    client = get_client(profile)
    results = client.list_schema_discovery_results(RunId(run_id))

    data = [
        {
            "id": r.id,
            "schema": r.schema_name or "",
            "table": r.table,
            "column": r.column,
            "data_type": r.data.data_type or "",
            "matches": ", ".join(m.label for m in r.data.discovery_matches if m.label) or "-",
            "constraint": r.data.constraint or "",
        }
        for r in results
    ]
    render_output(
        data,
        is_json=is_json,
        columns=["id", "schema", "table", "column", "data_type", "matches", "constraint"],
        title=f"Schema Discovery: Run {run_id}",
    )


@app.command("sdd-report")
def sdd_report(
    run_id: int = typer.Argument(help="Run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write CSV to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Download sensitive data discovery report for a run."""
    client = get_client(profile)
    report = client.get_sdd_report(RunId(run_id))
    _write_or_echo(report, output, "SDD report")


@app.command("db-report")
def db_discovery_report(
    run_id: int = typer.Argument(help="Run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write CSV to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Download database discovery report (CSV) for a run."""
    client = get_client(profile)
    report = client.get_db_discovery_result_report(RunId(run_id))

    if isinstance(report, bytes):
        if output is None:
            abort(
                f"Database discovery report for run {run_id} is a zip archive of CSV parts; "
                "refusing to write binary data to stdout.",
                code=ErrorCode.INVALID_INPUT,
                hint="Pass --output <file>.zip to save it.",
            )
        output.write_bytes(report)
        print_success(f"Database discovery report written to {output}")
        return

    _write_or_echo(report, output, "Database discovery report")


@app.command("file-report")
def file_discovery_report(
    run_id: int = typer.Argument(help="Run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Download file discovery report for a run."""
    client = get_client(profile)
    report = client.get_file_data_discovery_report(RunId(run_id))

    if output is not None:
        output.write_text(json.dumps(report, indent=2, default=str))
        print_success(f"File discovery report written to {output}")
        return

    if should_emit_json(is_json):
        print_json(report)
    else:
        render_output(report, is_json=False, title=f"File Discovery: Run {run_id}")


@app.command("config-snapshot")
def config_snapshot(
    run_id: int = typer.Argument(help="Discovery run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write YAML to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Download the discovery config a run used (the run's snapshot)."""
    client = get_client(profile)
    snapshot = client.get_discovery_run_config_snapshot_yaml(RunId(run_id))
    _write_or_echo(snapshot, output, "Discovery config snapshot")
