"""Schema discovery and sensitive data discovery commands."""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient, RunId
from datamasque.client.exceptions import (
    DataMasqueApiError,
    DiscoveryConfigNotFoundError,
    InvalidDiscoveryConfigError,
)
from datamasque.client.models.connection import ConnectionId
from datamasque.client.models.discovery import (
    FileDataDiscoveryFromConfigRequest,
    FileDataDiscoveryRequest,
    SchemaDiscoveryFromConfigRequest,
    SchemaDiscoveryRequest,
)
from datamasque.client.models.discovery_config import DiscoveryConfigId, DiscoveryConfigType
from datamasque.client.models.status import MaskingRunStatus

from datamasque_cli.client import get_client
from datamasque_cli.commands import discovery_config_libraries, discovery_configs
from datamasque_cli.errors import (
    ErrorCode,
    abort,
    abort_api_error,
    abort_if_not_found,
    require_id_or_abort,
)
from datamasque_cli.fileio import write_bytes_or_abort, write_text_or_abort
from datamasque_cli.output import print_info, print_json, print_success, render_output, should_emit_json

app = typer.Typer(help="Data discovery operations.", no_args_is_help=True)
app.add_typer(discovery_configs.app, name="configs")
app.add_typer(discovery_config_libraries.app, name="libraries")


def _run_status_or_abort_if_absent(client: DataMasqueClient, run_id: int) -> MaskingRunStatus | None:
    """Return the run's status, `None` when it cannot be read, and abort when the run does not exist."""
    try:
        return client.get_run_info(RunId(run_id)).status
    except DataMasqueApiError as exc:
        abort_if_not_found(exc, f"Run {run_id}")
        return None


def _abort_if_run_output_missing(
    client: DataMasqueClient,
    exc: DataMasqueApiError,
    run_id: int,
    output_label: str,
) -> None:
    """Explain a missing run output from the run's own state."""
    if exc.response.status_code not in (HTTPStatus.NOT_FOUND, HTTPStatus.BAD_REQUEST):
        return

    status = _run_status_or_abort_if_absent(client, run_id)
    if status is not None and not status.is_in_final_state:
        abort(
            f"No {output_label} available for run {run_id} yet; the run is {status.value}.",
            code=ErrorCode.NOT_FOUND,
            hint=f"Check progress with `dm run status {run_id}`.",
        )

    abort_api_error(f"No {output_label} available for run {run_id}", exc)


def _write_or_echo(content: str, output: Path | None, success_label: str) -> None:
    """Write `content` to `output` when given, otherwise echo to stdout."""
    if output is None:
        typer.echo(content)
        return
    write_text_or_abort(output, content)
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
    """Resolve a discovery config name to its UUID, requiring it to be of `expected_type`.

    Config names are unique per type, so name plus type identifies at most one config.
    """
    match = client.get_discovery_config_by_name(name, expected_type)
    if match is not None:
        return require_id_or_abort(match.id, f"discovery config '{name}'")

    other_type = (
        DiscoveryConfigType.file if expected_type is DiscoveryConfigType.database else DiscoveryConfigType.database
    )
    if client.get_discovery_config_by_name(name, other_type) is not None:
        abort(
            f"Discovery config '{name}' exists as {other_type.value}, "
            f"but {expected_type.value} discovery needs a {expected_type.value} config.",
            code=ErrorCode.INVALID_INPUT,
        )
    abort(f"Discovery config '{name}' not found.", code=ErrorCode.NOT_FOUND)


@app.command("schema")
def schema_discovery(
    connection: str = typer.Argument(help="Connection name or ID"),
    config: str | None = typer.Option(
        None, "--config", "-c", help="Run with a saved database discovery config (configurable discovery)"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Start a schema-discovery run on a connection.

    Results are scoped to a run ID, not a connection, so use
    `dm discover schema-results <run-id>` once this run reaches a terminal state
    (poll with `dm run status <run-id>`).
    """
    client = get_client(profile)
    conn_id = _resolve_connection_id(client, connection)

    try:
        if config is not None:
            config_id = _resolve_discovery_config_id(client, config, DiscoveryConfigType.database)
            from_config = SchemaDiscoveryFromConfigRequest(connection=ConnectionId(conn_id), discovery_config=config_id)
            run_id = client.start_schema_discovery_run_from_config(from_config)
            config_source = f"config '{config}'"
        else:
            request = SchemaDiscoveryRequest(connection=ConnectionId(conn_id))
            run_id = client.start_schema_discovery_run(request)
            config_source = "default discovery"
    except DiscoveryConfigNotFoundError as exc:
        abort(str(exc), code=ErrorCode.NOT_FOUND)
    except InvalidDiscoveryConfigError as exc:
        abort(str(exc), code=ErrorCode.INVALID_INPUT)
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to start schema discovery on '{connection}'", exc)

    print_success(
        f"Schema discovery run {run_id} started for connection '{connection}' ({config_source}). "
        f"Once finished, list results with: dm discover schema-results {run_id}"
    )
    if should_emit_json(is_json):
        print_json({"id": int(run_id)})


@app.command("file")
def start_file_discovery(
    connection: str = typer.Argument(help="Connection name or ID"),
    config: str | None = typer.Option(
        None, "--config", "-c", help="Run with a saved file discovery config (configurable discovery)"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Start a file-data-discovery run on a file connection.

    Once finished, download the report with `dm discover file-report <run-id>`
    (poll with `dm run status <run-id>`).
    """
    client = get_client(profile)
    conn_id = _resolve_connection_id(client, connection)

    try:
        if config is not None:
            config_id = _resolve_discovery_config_id(client, config, DiscoveryConfigType.file)
            from_config = FileDataDiscoveryFromConfigRequest(
                connection=ConnectionId(conn_id), discovery_config=config_id
            )
            run_id = client.start_file_data_discovery_run_from_config(from_config)
            config_source = f"config '{config}'"
        else:
            request = FileDataDiscoveryRequest(connection=ConnectionId(conn_id))
            run_id = client.start_file_data_discovery_run(request)
            config_source = "default discovery"
    except DiscoveryConfigNotFoundError as exc:
        abort(str(exc), code=ErrorCode.NOT_FOUND)
    except InvalidDiscoveryConfigError as exc:
        abort(str(exc), code=ErrorCode.INVALID_INPUT)
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to start file data discovery on '{connection}'", exc)

    print_success(
        f"File data discovery run {run_id} started for connection '{connection}' ({config_source}). "
        f"Once finished, download the report with: dm discover file-report {run_id}"
    )
    if should_emit_json(is_json):
        print_json({"id": int(run_id)})


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
    try:
        results = client.list_schema_discovery_results(RunId(run_id))
    except DataMasqueApiError as exc:
        _abort_if_run_output_missing(client, exc, run_id, "schema discovery results")
        abort_api_error(f"Failed to list schema discovery results for run {run_id}", exc)

    data = [
        {
            "id": r.id,
            "schema": r.schema_name or "",
            "table": r.table,
            "column": r.column,
            "data_type": r.data.data_type or "",
            "matches": ", ".join(m.label for m in r.data.discovery_matches if m.label) or "-",
            "constraint": r.data.constraint or "",
            "safe_data_preview": (
                r.data.safe_data_preview.model_dump(mode="json") if r.data.safe_data_preview else None
            ),
        }
        for r in results
    ]
    render_output(
        data,
        is_json=is_json,
        columns=["id", "schema", "table", "column", "data_type", "matches", "constraint"],
        title=f"Schema Discovery: Run {run_id}",
    )
    if not should_emit_json(is_json) and any(row["safe_data_preview"] for row in data):
        print_info("Safe Data Preview results are not shown in the table. Use --json to view them.")


@app.command("sdd-report")
def sdd_report(
    run_id: int = typer.Argument(help="Run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write CSV to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Download sensitive data discovery report for a run."""
    client = get_client(profile)
    try:
        report = client.get_sdd_report(RunId(run_id))
    except DataMasqueApiError as exc:
        _abort_if_run_output_missing(client, exc, run_id, "sensitive data discovery report")
        abort_api_error(f"Failed to download sensitive data discovery report for run {run_id}", exc)
    _write_or_echo(report, output, "SDD report")


@app.command("db-report")
def db_discovery_report(
    run_id: int = typer.Argument(help="Run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write CSV (or zip) to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Download database discovery report for a run.

    Reports within Excel's row limit download as a single CSV. Larger reports are split
    server-side into a zip of numbered CSV parts, written out as a binary `.zip`; that case
    requires `-o`, since a zip can't be streamed to stdout.
    """
    client = get_client(profile)
    try:
        report = client.get_db_discovery_result_report(RunId(run_id))
    except DataMasqueApiError as exc:
        _abort_if_run_output_missing(client, exc, run_id, "database discovery report")
        abort_api_error(f"Failed to download database discovery report for run {run_id}", exc)

    if isinstance(report, bytes):
        if output is None:
            abort(
                "This report was split into a zip and can't be written to stdout.",
                code=ErrorCode.INVALID_INPUT,
                hint=f"Re-run with -o <path>.zip (e.g. -o discovery_report_{run_id}.zip).",
            )
        target = output if output.suffix.lower() == ".zip" else output.parent / (output.name + ".zip")
        write_bytes_or_abort(target, report)
        print_success(f"Database discovery report (split, zip) written to {target}")
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
    try:
        report = client.get_file_data_discovery_report(RunId(run_id))
    except DataMasqueApiError as exc:
        _abort_if_run_output_missing(client, exc, run_id, "file discovery report")
        abort_api_error(f"Failed to download file discovery report for run {run_id}", exc)
    serialised_report = [result.model_dump(mode="json") for result in report]

    if output is not None:
        write_text_or_abort(output, json.dumps(serialised_report, indent=2, default=str))
        print_success(f"File discovery report written to {output}")
        return

    if should_emit_json(is_json):
        print_json(serialised_report)
        return

    rows = [
        {
            "id": result.id,
            "files": ", ".join(f.path for f in result.files),
            "locator": locator.locator,
            "matches": ", ".join(m.label for m in locator.matches if m.label) or "-",
            "data_types": ", ".join(locator.data_types) or "-",
        }
        for result in report
        for locator in result.results
    ]
    render_output(
        rows,
        is_json=False,
        columns=["id", "files", "locator", "matches", "data_types"],
        title=f"File Discovery: Run {run_id}",
    )


@app.command("config-snapshot")
def download_config_snapshot(
    run_id: int = typer.Argument(help="Discovery run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write YAML to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Download the discovery config a run used (the run's snapshot)."""
    client = get_client(profile)
    try:
        snapshot = client.get_discovery_run_config_snapshot_yaml(RunId(run_id))
    except DataMasqueApiError as exc:
        _abort_if_run_output_missing(client, exc, run_id, "discovery config snapshot")
        abort_api_error(f"Failed to download discovery config snapshot for run {run_id}", exc)
    _write_or_echo(snapshot, output, "Discovery config snapshot")
