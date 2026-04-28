"""In-flight masking (IFM) commands.

Wraps `DataMasqueIfmClient` for managing IFM ruleset plans and running mask operations.
The IFM service exposes a separate HTTP API;
the SDK handles JWT auth transparently using the same admin-server credentials as `dm rulesets`.
"""

from __future__ import annotations

import json
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ifm import (
    IfmMaskRequest,
    RulesetPlanCreateRequest,
    RulesetPlanOptions,
    RulesetPlanPartialUpdateRequest,
)

from datamasque_cli.client import get_ifm_client
from datamasque_cli.output import abort, print_error, print_json, print_success, render_output

app = typer.Typer(help="Manage in-flight-masking (IFM) ruleset plans and execute masks.", no_args_is_help=True)


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def _options_from_flags(
    enabled: bool | None,
    log_level: LogLevel | None,
) -> RulesetPlanOptions | None:
    if enabled is None and log_level is None:
        return None
    return RulesetPlanOptions(enabled=enabled, default_log_level=log_level)


def _load_mask_input(data: str) -> list[Any]:
    if data == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(data).read_text()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        abort(f"Failed to parse mask input as JSON: {exc}")

    if not isinstance(parsed, list):
        abort("Mask input must be a JSON list (array) of records.")
    return parsed


@app.command("list")
def list_plans(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all IFM ruleset plans."""
    client = get_ifm_client(profile)
    plans = client.list_ruleset_plans()

    data = [
        {
            "name": plan.name,
            "serial": plan.serial,
            "created": plan.created_time.isoformat(),
            "modified": plan.modified_time.isoformat(),
            "enabled": plan.options.enabled,
        }
        for plan in plans
    ]

    render_output(
        data,
        is_json=is_json,
        columns=["name", "serial", "created", "modified", "enabled"],
        title="IFM ruleset plans",
    )


@app.command("get")
def get_plan(
    name: str = typer.Argument(help="Ruleset plan name"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output the ruleset YAML only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show an IFM ruleset plan's metadata or YAML."""
    client = get_ifm_client(profile)
    plan = client.get_ruleset_plan(name)

    if is_yaml:
        if plan.ruleset_yaml is None:
            abort(f"IFM ruleset plan '{name}' has no ruleset YAML.")
        typer.echo(plan.ruleset_yaml)
        return

    data: dict[str, object] = {
        "name": plan.name,
        "serial": plan.serial,
        "created": plan.created_time.isoformat(),
        "modified": plan.modified_time.isoformat(),
        "enabled": plan.options.enabled,
        "default_log_level": plan.options.default_log_level,
        "ruleset_yaml": plan.ruleset_yaml,
    }
    render_output(data, is_json=is_json, title=f"IFM plan: {name}")


@app.command("create")
def create_plan(
    name: str = typer.Option(..., "--name", help="Ruleset plan name (server may suffix a random string)"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML ruleset file", exists=True, readable=True),
    enabled: bool | None = typer.Option(
        None,
        "--enabled/--disabled",
        help="Enable or disable the plan immediately. Defaults to the server default.",
    ),
    log_level: LogLevel | None = typer.Option(
        None,
        "--log-level",
        case_sensitive=False,
        help="Default log level.",
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create a new IFM ruleset plan from a YAML file."""
    client = get_ifm_client(profile)
    request = RulesetPlanCreateRequest(
        name=name,
        ruleset_yaml=file.read_text(),
        options=_options_from_flags(enabled, log_level),
    )
    try:
        created = client.create_ruleset_plan(request)
    except DataMasqueApiError as exc:
        abort(f"Failed to create IFM ruleset plan: {exc}")

    print_success(f"IFM ruleset plan '{created.name}' created (serial {created.serial}).")
    if created.url:
        typer.echo(created.url)


@app.command("update")
def update_plan(
    name: str = typer.Argument(help="Existing ruleset plan name"),
    file: Path | None = typer.Option(
        None, "--file", "-f", help="Path to YAML ruleset file (optional)", exists=True, readable=True
    ),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Enable or disable the plan."),
    log_level: LogLevel | None = typer.Option(None, "--log-level", case_sensitive=False, help="Default log level."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Update an IFM ruleset plan: only fields you pass are sent."""
    if file is None and enabled is None and log_level is None:
        abort("Pass at least one of --file, --enabled/--disabled, or --log-level.")

    client = get_ifm_client(profile)
    request = RulesetPlanPartialUpdateRequest(
        ruleset_yaml=file.read_text() if file is not None else None,
        options=_options_from_flags(enabled, log_level),
    )
    try:
        updated = client.patch_ruleset_plan(name, request)
    except DataMasqueApiError as exc:
        abort(f"Failed to update IFM ruleset plan: {exc}")

    print_success(f"IFM ruleset plan '{name}' updated (serial {updated.serial}).")


@app.command("delete")
def delete_plan(
    name: str = typer.Argument(help="Ruleset plan name to delete"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete an IFM ruleset plan."""
    if not is_confirmed:
        typer.confirm(f"Delete IFM ruleset plan '{name}'?", abort=True)

    client = get_ifm_client(profile)
    try:
        client.delete_ruleset_plan(name)
    except DataMasqueApiError as exc:
        abort(f"Failed to delete IFM ruleset plan: {exc}")

    print_success(f"IFM ruleset plan '{name}' deleted.")


@app.command("mask")
def mask(
    name: str = typer.Argument(help="Ruleset plan name to mask against"),
    data: str = typer.Option(
        ...,
        "--data",
        "-d",
        help="Path to a JSON file containing a list of records to mask, or '-' to read from stdin.",
    ),
    disable_instance_secret: bool = typer.Option(
        False, "--disable-instance-secret", help="Disable the per-instance secret for this run."
    ),
    run_secret: str | None = typer.Option(None, "--run-secret", help="Override the run secret for this call."),
    log_level: LogLevel | None = typer.Option(
        None, "--log-level", case_sensitive=False, help="Override the plan's default log level."
    ),
    request_id: str | None = typer.Option(None, "--request-id", help="Custom request id (echoed in the response)."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(
        True,
        "--json/--no-json",
        help="Output the masked records as a JSON array (default). Use --no-json for NDJSON (one record per line).",
    ),
) -> None:
    """Run an IFM mask against a list of records."""
    records = _load_mask_input(data)
    client = get_ifm_client(profile)
    request = IfmMaskRequest(
        data=records,
        disable_instance_secret=disable_instance_secret or None,
        run_secret=run_secret,
        log_level=log_level,
        request_id=request_id,
    )

    try:
        result = client.mask(name, request)
    except DataMasqueApiError as exc:
        abort(f"Mask request failed: {exc}")

    if not result.success:
        print_error("Mask failed.")
        for log in result.logs or []:
            print_error(f"  [{log.log_level}] {log.timestamp} {log.message}")
        raise SystemExit(1)

    if is_json:
        print_json(result.data)
    else:
        for record in result.data or []:
            typer.echo(json.dumps(record, default=str))


@app.command("verify-token")
def verify_token(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Verify the current IFM token and list its scopes."""
    client = get_ifm_client(profile)
    info = client.verify_token()
    if is_json:
        print_json({"scopes": info.scopes})
        return
    render_output(
        [{"scope": scope} for scope in info.scopes],
        is_json=False,
        columns=["scope"],
        title="IFM token scopes",
    )
