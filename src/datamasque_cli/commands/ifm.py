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
from typing import Any, NoReturn

import typer
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ifm import (
    IfmMaskRequest,
    RulesetPlanCreateRequest,
    RulesetPlanOptions,
    RulesetPlanPartialUpdateRequest,
)

from datamasque_cli.client import get_ifm_client
from datamasque_cli.output import (
    ErrorCode,
    FileKind,
    abort,
    confirm_or_abort,
    print_error,
    print_json,
    print_success,
    read_text_or_abort,
    render_output,
)

app = typer.Typer(help="Manage in-flight-masking (IFM) ruleset plans and execute masks.", no_args_is_help=True)


# IFM service maps HTTP statuses to the CLI's stable `ErrorCode` taxonomy so
# agents and scripts get the right exit code (see "Exit codes" in `README.md`).
# Anything not listed falls through to `ErrorCode.ERROR` (exit 1).
_STATUS_TO_ERROR_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_INPUT,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.INVALID_INPUT,
}


def _format_pydantic_errors(errors: list[Any]) -> str:
    """Flatten FastAPI's `detail` list (Pydantic `e.errors()`) into a readable string.

    Each entry looks like `{"loc": [...], "msg": "...", "type": "..."}`;
    we render `field.path: message` per entry, joined with `; `.
    Entries that don't match the shape fall back to `str(entry)`.
    """
    parts: list[str] = []
    for entry in errors:
        if isinstance(entry, dict) and "msg" in entry:
            loc = entry.get("loc") or []
            location = ".".join(str(part) for part in loc if part != "body") if isinstance(loc, (list, tuple)) else ""
            parts.append(f"{location}: {entry['msg']}" if location else str(entry["msg"]))
        else:
            parts.append(str(entry))
    return "; ".join(parts)


def _server_error_detail(exc: DataMasqueApiError) -> str | None:
    """Pull a human-readable error string from the IFM response body, if present.

    The IFM service returns `{"error": "..."}`;
    FastAPI validation errors come back as `{"detail": ...}`,
    where `detail` is either a string or a list of Pydantic error dicts (422s).
    Falls through to `None` if the body is missing or not parseable.
    """
    try:
        body = exc.response.json()
    except (ValueError, AttributeError):
        return None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, str):
            return error
        if "detail" in body:
            detail = body["detail"]
            if isinstance(detail, str):
                return detail
            if isinstance(detail, list):
                return _format_pydantic_errors(detail)
            return str(detail)
    return None


def _abort_api_error(prefix: str, exc: DataMasqueApiError) -> NoReturn:
    """Map an `DataMasqueApiError` to the right `ErrorCode` and surface the body.

    The default `str(exc)` only includes the HTTP status,
    so the actual server message is hidden without this.
    """
    status_code = getattr(exc.response, "status_code", None)
    code = _STATUS_TO_ERROR_CODE.get(status_code, ErrorCode.ERROR) if isinstance(status_code, int) else ErrorCode.ERROR
    detail = _server_error_detail(exc)
    message = f"{prefix}: {detail}" if detail else f"{prefix}: {exc}"
    abort(message, code=code)


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
        raw = read_text_or_abort(Path(data), FileKind.MASK_INPUT)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        abort(f"Failed to parse mask input as JSON: {exc}", code=ErrorCode.INVALID_INPUT)

    if not isinstance(parsed, list):
        abort("Mask input must be a JSON list (array) of records.", code=ErrorCode.INVALID_INPUT)
    return parsed


@app.command("list")
def list_plans(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all IFM ruleset plans."""
    client = get_ifm_client(profile)
    try:
        plans = client.list_ruleset_plans()
    except DataMasqueApiError as exc:
        _abort_api_error("Failed to list IFM ruleset plans", exc)

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
    try:
        plan = client.get_ruleset_plan(name)
    except DataMasqueApiError as exc:
        _abort_api_error(f"Failed to get IFM ruleset plan '{name}'", exc)

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
        ruleset_yaml=read_text_or_abort(file, FileKind.RULESET),
        options=_options_from_flags(enabled, log_level),
    )
    try:
        created = client.create_ruleset_plan(request)
    except DataMasqueApiError as exc:
        _abort_api_error("Failed to create IFM ruleset plan", exc)

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
        abort(
            "Pass at least one of --file, --enabled/--disabled, or --log-level.",
            code=ErrorCode.INVALID_INPUT,
        )

    client = get_ifm_client(profile)
    request = RulesetPlanPartialUpdateRequest(
        ruleset_yaml=read_text_or_abort(file, FileKind.RULESET) if file is not None else None,
        options=_options_from_flags(enabled, log_level),
    )
    try:
        updated = client.patch_ruleset_plan(name, request)
    except DataMasqueApiError as exc:
        _abort_api_error(f"Failed to update IFM ruleset plan '{name}'", exc)

    print_success(f"IFM ruleset plan '{name}' updated (serial {updated.serial}).")


@app.command("delete")
def delete_plan(
    name: str = typer.Argument(help="Ruleset plan name to delete"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete an IFM ruleset plan."""
    if not is_confirmed:
        confirm_or_abort(f"Delete IFM ruleset plan '{name}'?")

    client = get_ifm_client(profile)
    try:
        client.delete_ruleset_plan(name)
    except DataMasqueApiError as exc:
        _abort_api_error(f"Failed to delete IFM ruleset plan '{name}'", exc)

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
        _abort_api_error("Mask request failed", exc)

    if not result.success:
        print_error("Mask failed.")
        for log in result.logs or []:
            print_error(f"  [{log.log_level}] {log.timestamp} {log.message}")
        raise SystemExit(1)

    if is_json:
        print_json(result.data or [])
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
    try:
        info = client.verify_token()
    except DataMasqueApiError as exc:
        _abort_api_error("Failed to verify IFM token", exc)
    if is_json:
        print_json({"scopes": info.scopes})
        return
    render_output(
        [{"scope": scope} for scope in info.scopes],
        is_json=False,
        columns=["scope"],
        title="IFM token scopes",
    )
