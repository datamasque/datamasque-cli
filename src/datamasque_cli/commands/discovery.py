"""Schema discovery and sensitive data discovery commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient, RunId
from datamasque.client.models.connection import ConnectionId
from datamasque.client.models.discovery import (
    InDataDiscoveryConfig,
    SafeDataPreviewOptions,
    SchemaDiscoveryFromConfigRequest,
    SchemaDiscoveryRequest,
)
from datamasque.client.models.discovery_config import DiscoveryConfigId

from datamasque_cli.client import get_client
from datamasque_cli.output import ErrorCode, abort, print_json, print_success, render_output, should_emit_json

app = typer.Typer(help="Data discovery operations.", no_args_is_help=True)


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


def _resolve_discovery_config_id(client: DataMasqueClient, name_or_id: str) -> str:
    """Resolve a discovery config name or ID to its UUID string."""
    match = next((c for c in client.list_discovery_configs() if c.name == name_or_id or str(c.id) == name_or_id), None)
    if match is None:
        abort(f"Discovery config '{name_or_id}' not found.", code=ErrorCode.NOT_FOUND)
    return str(match.id)


@app.command("schema")
def schema_discovery(
    connection: str = typer.Argument(help="Connection name or ID"),
    config: str | None = typer.Option(
        None, "--config", help="Discovery config name or ID to run with (holds IDD rules and preview settings)"
    ),
    idd: bool | None = typer.Option(None, "--idd/--no-idd", help="Enable or disable in-data discovery"),
    preview: bool | None = typer.Option(
        None, "--preview/--no-preview", help="Enable or disable Safe Data Preview (requires --idd)"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Start a schema-discovery run on a connection.

    Results are scoped to a run ID, not a connection, so use
    `dm discover schema-results <run-id>` once this run reaches a terminal state
    (poll with `dm run status <run-id>`).
    """
    if config is not None and (idd is not None or preview is not None):
        abort("--config carries its own IDD and preview settings; drop --idd/--preview.", code=ErrorCode.INVALID_INPUT)
    if preview is not None and idd is None:
        abort(
            "--preview/--no-preview requires --idd (the preview rides on in-data discovery).",
            code=ErrorCode.INVALID_INPUT,
        )

    client = get_client(profile)
    conn_id = _resolve_connection_id(client, connection)

    if config is not None:
        config_id = _resolve_discovery_config_id(client, config)
        from_config_request = SchemaDiscoveryFromConfigRequest(
            connection=ConnectionId(conn_id), discovery_config=DiscoveryConfigId(config_id)
        )
        run_id = client.start_schema_discovery_run_from_config(from_config_request)
        print_success(
            f"Schema discovery run {run_id} started for connection '{connection}' with config '{config}'. "
            f"Once finished, list results with: dm discover schema-results {run_id}"
        )
        return

    in_data_discovery = None
    if idd is not None:
        safe_data_preview = SafeDataPreviewOptions(enabled=preview) if preview is not None else None
        in_data_discovery = InDataDiscoveryConfig(enabled=idd, safe_data_preview=safe_data_preview)

    request = SchemaDiscoveryRequest(connection=ConnectionId(conn_id), in_data_discovery=in_data_discovery)
    run_id = client.start_schema_discovery_run(request)
    print_success(
        f"Schema discovery run {run_id} started for connection '{connection}'. "
        f"Once finished, list results with: dm discover schema-results {run_id}"
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
            "matches": ", ".join(m.label for m in r.data.discovery_matches) or "-",
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
