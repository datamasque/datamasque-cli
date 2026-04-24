"""Masking run management commands."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient, RunId
from datamasque.client.exceptions import DataMasqueApiError, RunNotCancellableError
from datamasque.client.models.connection import ConnectionConfig
from datamasque.client.models.runs import MaskingRunOptions, MaskingRunRequest, RunInfo

from datamasque_cli.client import get_client
from datamasque_cli.output import (
    abort,
    console,
    print_error,
    print_json,
    print_success,
    render_output,
    stdout_console,
    style_status,
)

app = typer.Typer(help="Manage masking runs.", no_args_is_help=True)

_POLL_INTERVAL_SECONDS = 5

_HTTP_NOT_FOUND = 404


def _format_run_info(run: RunInfo, *, is_styled: bool = False) -> dict[str, object]:
    """Extract the fields most useful for display from a `RunInfo`."""
    status = run.status.value
    destination = run.destination_connection.name if run.destination_connection else None
    return {
        "id": run.id,
        "status": style_status(status) if is_styled else status,
        "ruleset": run.ruleset_name,
        "source": run.source_connection.name,
        "destination": destination,
        "created": run.start_time.isoformat() if run.start_time else None,
    }


def _format_run_dict(run_data: dict[str, object], *, is_styled: bool = False) -> dict[str, object]:
    """Extract display fields from a raw run list-response dict (not yet modelled in dm-python 1.0.0)."""
    status = str(run_data.get("status") or run_data.get("run_status") or "")
    return {
        "id": run_data.get("id"),
        "status": style_status(status) if is_styled else status,
        "ruleset": run_data.get("ruleset_name"),
        "source": run_data.get("source_connection_name"),
        "destination": run_data.get("destination_connection_name"),
        "created": run_data.get("created_time"),
    }


def _resolve_connection(client: DataMasqueClient, name_or_id: str) -> ConnectionConfig:
    """Return the connection matching `name_or_id`, preferring name."""
    connections = client.list_connections()

    match = next((c for c in connections if c.name == name_or_id), None)
    if match is not None:
        return match

    match = next((c for c in connections if str(c.id) == name_or_id), None)
    if match is not None:
        return match

    available = ", ".join(c.name for c in connections)
    abort(f"Connection '{name_or_id}' not found. Available: {available}")


def _resolve_connection_id(client: DataMasqueClient, name_or_id: str) -> str:
    """Resolve a connection name to its UUID. Pass through if already a UUID."""
    return str(_resolve_connection(client, name_or_id).id)


def _resolve_ruleset_id(client: DataMasqueClient, name_or_id: str, mask_type: str | None = None) -> str:
    """Resolve a ruleset name to its UUID.

    `mask_type` is the source connection's type when called from `run start`.
    Providing it narrows the lookup to the matching namespace, which is what
    disambiguates same-named rulesets across the database/file split.
    """
    rulesets = client.list_rulesets()
    by_name = [r for r in rulesets if r.name == name_or_id]

    if mask_type is not None:
        by_name_and_type = [r for r in by_name if r.ruleset_type.value == mask_type]
        if len(by_name_and_type) == 1:
            return str(by_name_and_type[0].id)
        if len(by_name_and_type) == 0 and by_name:
            existing = ", ".join(f"{r.ruleset_type.value}" for r in by_name)
            abort(
                f"Ruleset '{name_or_id}' exists as {existing}, "
                f"but a {mask_type} ruleset is required for this connection."
            )

    if len(by_name) == 1:
        return str(by_name[0].id)
    if len(by_name) > 1:
        options = ", ".join(f"{r.ruleset_type.value}:{r.id}" for r in by_name)
        abort(f"Multiple rulesets named '{name_or_id}' ({options}). Pass a UUID instead, or rename one of them.")

    by_id = next((r for r in rulesets if str(r.id) == name_or_id), None)
    if by_id is not None:
        if mask_type is not None and by_id.ruleset_type.value != mask_type:
            abort(
                f"Ruleset {name_or_id} is a {by_id.ruleset_type.value} ruleset "
                f"but a {mask_type} ruleset is required for this connection."
            )
        return name_or_id

    available = ", ".join(r.name for r in rulesets)
    abort(f"Ruleset '{name_or_id}' not found. Available: {available}")


def _coerce_option_value(value: str) -> object:
    """Parse a string value into bool/int/float when it looks like one, else keep as string."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_options(pairs: list[str]) -> dict[str, object]:
    """Turn a list of `key=value` strings into a dict, coercing values to bool/int/float/str."""
    parsed: dict[str, object] = {}
    for pair in pairs:
        if "=" not in pair:
            abort(f"--options expects key=value, got '{pair}'.")
        key, _, raw = pair.partition("=")
        parsed[key.strip()] = _coerce_option_value(raw.strip())
    return parsed


@app.command("start")
def start_run(
    connection: str = typer.Option(..., "--connection", "-c", help="Source connection name or ID"),
    ruleset: str = typer.Option(..., "--ruleset", "-r", help="Ruleset name or ID"),
    destination: str | None = typer.Option(None, "--destination", "-d", help="Destination connection (optional)"),
    options: list[str] = typer.Option(
        [],
        "--options",
        help="Run options as key=value (repeatable). E.g. --options batch_size=1000 --options dry_run=true",
    ),
    is_background: bool = typer.Option(
        False, "--background", "-b", help="Return immediately without waiting for completion"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Start a new masking run."""
    client = get_client(profile)

    source = _resolve_connection(client, connection)
    ruleset_id = _resolve_ruleset_id(client, ruleset, mask_type=source.mask_type)

    # Without `destination_connection` in the payload the server defaults
    # `mask_type` to `database`, so a file source produces a confusing
    # "source must be a database connection" error. Reject client-side.
    if source.mask_type == "file" and destination is None:
        abort(
            f"File masking requires a destination connection. "
            f"Pass --destination <name> (source '{source.name}' is a file-type connection)."
        )

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    run_name = f"{source.name}_{timestamp}"

    destination_id: str | None = None
    if destination is not None:
        dest = _resolve_connection(client, destination)
        if dest.mask_type != source.mask_type:
            abort(
                f"Connection type mismatch: source '{source.name}' is {source.mask_type} "
                f"but destination '{dest.name}' is {dest.mask_type}."
            )
        destination_id = str(dest.id)

    run_request = MaskingRunRequest(
        name=run_name,
        connection=str(source.id),
        ruleset=ruleset_id,
        mask_type=source.mask_type,
        destination_connection=destination_id,
        options=MaskingRunOptions.model_validate(_parse_options(options)),
    )
    run_id = client.start_masking_run(run_request)
    print_success(f"Run {run_id} started ({run_name}).")

    if is_background:
        if is_json:
            print_json({"id": int(run_id), "status": "queued"})
        return

    _wait_for_run(client, run_id, is_json=is_json, ruleset=ruleset, connection=connection)


@app.command("status")
def run_status(
    run_id: int = typer.Argument(help="Run ID"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get status of a masking run."""
    client = get_client(profile)
    run = client.get_run_info(RunId(run_id))
    render_output(_format_run_info(run, is_styled=not is_json), is_json=is_json, title=f"Run {run_id}")


@app.command("list")
def list_runs(
    status_filter: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of runs to show"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List masking runs.

    Without --status, lists the most recent runs.
    With --status, filters to runs in that state (e.g. running, finished, failed).
    """
    client = get_client(profile)

    # `list_runs` is not yet wrapped in datamasque-python; hit the endpoint directly.
    params = []
    if status_filter is not None:
        params.append(f"run_status={status_filter}")
    if limit is not None:
        params.append(f"limit={limit}")
    query = f"?{'&'.join(params)}" if params else ""
    response = client.make_request("GET", f"/api/runs/{query}")
    body = response.json()

    # The API may return a paginated envelope or a flat list depending on version.
    # Fall back to an empty list when the dict shape is missing `results`,
    # otherwise the comprehension below would iterate over dict keys.
    if isinstance(body, dict):
        runs: list[dict[str, object]] = body.get("results", [])
    else:
        runs = body
    data = [_format_run_dict(r, is_styled=not is_json) for r in runs]

    render_output(
        data,
        is_json=is_json,
        columns=["id", "status", "ruleset", "source", "destination", "created"],
        title="Masking Runs",
    )


@app.command("logs")
def run_logs(
    run_id: int = typer.Argument(help="Run ID"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Stream logs until the run reaches a terminal state"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Show execution logs for a masking run.

    With `--follow`, polls the log and status until the run finishes,
    printing each new chunk as it appears.
    """
    client = get_client(profile)

    if not follow:
        log = client.get_run_log(RunId(run_id))
        if is_json:
            typer.echo(log)
        else:
            _print_pretty_logs(log)
        return

    printed = 0
    while True:
        log = client.get_run_log(RunId(run_id))
        # Defend against server-side log rotation shrinking the buffer:
        # reset the cursor rather than slicing past the end.
        printed = min(printed, len(log))
        if len(log) > printed:
            chunk = log[printed:]
            if is_json:
                typer.echo(chunk, nl=False)
            else:
                _print_pretty_logs(chunk)
            printed = len(log)

        info = client.get_run_info(RunId(run_id))
        if info.status.is_in_final_state:
            return
        time.sleep(_POLL_INTERVAL_SECONDS)


@app.command("cancel")
def cancel_run(
    run_id: int = typer.Argument(help="Run ID to cancel"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Cancel a running masking run."""
    client = get_client(profile)
    try:
        client.cancel_run(RunId(run_id))
    except RunNotCancellableError as exc:
        abort(str(exc))
    print_success(f"Run {run_id} cancellation requested.")


@app.command("report")
def run_report(
    run_id: int = typer.Argument(help="Run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write CSV to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Download the masking run report (CSV) for a completed run."""
    client = get_client(profile)
    try:
        report = client.get_run_report(RunId(run_id))
    except DataMasqueApiError as exc:
        # Reports are POSTed by the agent-worker as it finishes the run, so
        # `GET .../run-report/` 404s for runs that didn't produce one
        # (still in flight, failed early, or a run type that doesn't emit a
        # report). The default error string is opaque, so name the cause.
        if exc.response is not None and exc.response.status_code == _HTTP_NOT_FOUND:
            abort(
                f"No report available for run {run_id}. Reports are generated by the worker "
                f"once the run reaches a final state — check status with `dm run status {run_id}`."
            )
        raise

    if output is None:
        typer.echo(report)
    else:
        output.write_text(report)
        print_success(f"Run report written to {output}")


# `MaskingRunOptions` declares `extra="forbid"`; the server can echo back keys
# on read (e.g. `has_run_secret`) that it won't accept on create, and may add
# more in future. Drop anything the model doesn't know about — and the
# server-managed `run_secret` so a fresh per-run key is generated on retry.
_VALID_OPTION_KEYS = set(MaskingRunOptions.model_fields.keys())
_SERVER_MANAGED_OPTION_KEYS = frozenset({"run_secret"})


@app.command("retry")
def retry_run(
    run_id: int = typer.Argument(help="Run ID to retry"),
    is_background: bool = typer.Option(
        False, "--background", "-b", help="Return immediately without waiting for completion"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Start a new run with the same source, ruleset, destination, and options as an existing one.

    Useful for re-running a failed or cancelled masking job. The original
    run's config is read back from the server so any manual edits to the
    connection or ruleset since then are picked up automatically.
    """
    client = get_client(profile)
    original = client.get_run_info(RunId(run_id))

    source_id = original.source_connection.id
    ruleset_id = original.ruleset
    if not source_id or not ruleset_id:
        abort(f"Run {run_id} is missing source or ruleset — cannot retry.")

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    run_name = f"{original.source_connection.name or source_id}_retry_{timestamp}"

    original_options = original.options or {}
    options = {
        k: v for k, v in original_options.items() if k in _VALID_OPTION_KEYS and k not in _SERVER_MANAGED_OPTION_KEYS
    }

    destination_id = original.destination_connection.id if original.destination_connection else None

    run_request = MaskingRunRequest(
        name=run_name,
        connection=str(source_id),
        ruleset=str(ruleset_id),
        mask_type=original.mask_type,
        destination_connection=str(destination_id) if destination_id else None,
        options=MaskingRunOptions.model_validate(options),
    )
    new_run_id = client.start_masking_run(run_request)
    print_success(f"Run {new_run_id} started (retry of {run_id}, {run_name}).")

    if is_background:
        if is_json:
            print_json({"id": int(new_run_id), "status": "queued"})
        return

    _wait_for_run(client, new_run_id, is_json=is_json)


@app.command("wait")
def wait_run(
    run_id: int = typer.Argument(help="Run ID to wait for"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output final status as JSON"),
) -> None:
    """Block until a masking run reaches a terminal state.

    Exits 0 on success (finished/finished_with_warnings), 1 on failure/cancellation.
    """
    client = get_client(profile)
    _wait_for_run(client, RunId(run_id), is_json=is_json)


def _wait_for_run(
    client: DataMasqueClient,
    run_id: RunId,
    *,
    is_json: bool,
    ruleset: str | None = None,
    connection: str | None = None,
) -> None:
    """Poll until the run reaches a terminal state, then report result."""
    run: RunInfo | None = None
    started_at = time.monotonic()

    with console.status(f"Waiting for run {run_id}...") as spinner:
        while True:
            run = client.get_run_info(run_id)
            if run.status.is_in_final_state:
                break
            spinner.update(f"Run {run_id}: {run.status.value}")
            time.sleep(_POLL_INTERVAL_SECONDS)

    elapsed = time.monotonic() - started_at
    duration = _format_duration(int(elapsed))

    if is_json:
        print_json(_format_run_info(run))

    status = run.status
    summary_parts = [f"Run {run_id} {status.value} in {duration}"]
    if ruleset:
        summary_parts.append(f"ruleset: {ruleset}")
    if connection:
        summary_parts.append(f"source: {connection}")

    summary = summary_parts[0]
    if len(summary_parts) > 1:
        summary += f" ({', '.join(summary_parts[1:])})"

    if status.is_finished:
        print_success(summary)
    else:
        print_error(summary)
        raise SystemExit(1)


_SECONDS_PER_MINUTE = 60
_MINUTES_PER_HOUR = 60


def _format_duration(total_seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if total_seconds < _SECONDS_PER_MINUTE:
        return f"{total_seconds}s"

    minutes, seconds = divmod(total_seconds, _SECONDS_PER_MINUTE)
    if minutes < _MINUTES_PER_HOUR:
        return f"{minutes}m {seconds}s"

    hours, minutes = divmod(minutes, _MINUTES_PER_HOUR)
    return f"{hours}h {minutes}m {seconds}s"


_LOG_LEVEL_LABELS = {
    10: ("DEBUG", "dim"),
    20: ("INFO", "green"),
    30: ("WARN", "yellow"),
    40: ("ERROR", "red"),
    50: ("FATAL", "bold red"),
}


def _print_pretty_logs(raw_log: str) -> None:
    """Parse JSON log entries and print them in a human-readable format."""
    try:
        entries = json.loads(raw_log)
    except json.JSONDecodeError:
        # Not JSON — just print raw
        typer.echo(raw_log)
        return

    if not isinstance(entries, list):
        entries = [entries]

    for entry in entries:
        ts = entry.get("timestamp", "")
        level = entry.get("log_level", 20)
        message = entry.get("message", "")

        label, style = _LOG_LEVEL_LABELS.get(level, ("INFO", "green"))

        # Truncate the timestamp to seconds
        if "." in ts:
            ts = ts[: ts.index(".")]
        ts = ts.replace("T", " ")

        # Escape rich markup in the message, and indent continuation lines
        escaped = message.replace("[", "\\[")
        lines = escaped.split("\n")
        first_line = lines[0]
        stdout_console.print(f"[dim]{ts}[/dim] [{style}]{label:5}[/{style}] {first_line}")
        for continuation in lines[1:]:
            stdout_console.print(f"{'':>27}{continuation}")
