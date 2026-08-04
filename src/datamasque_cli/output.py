"""Output formatting for the CLI.

Supports JSON output (--json) for machine consumption,
and rich tables for human-readable display.

JSON mode is auto-selected when stdout is not a TTY, when `DM_OUTPUT=json`
is set, or when an `AI_AGENT` env var is present (a vendor-neutral signal
that an AI agent is driving the CLI). Set `DM_OUTPUT=table` to force
human output regardless.
"""

from __future__ import annotations

import json
import os
import sys
from enum import IntEnum, StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Any, NoReturn

import typer
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.status import ValidationErrorDetails, ValidationStatus
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

_DM_THEME = Theme(
    {
        "status.finished": "bold green",
        "status.finished_with_warnings": "bold yellow",
        "status.running": "bold cyan",
        "status.queued": "dim",
        "status.failed": "bold red",
        "status.cancelled": "dim strike",
    }
)

# Diagnostic messages go to stderr so piped JSON output stays clean.
console = Console(stderr=True, theme=_DM_THEME)
stdout_console = Console(theme=_DM_THEME)


# Any top-level field whose lowercased name contains one of these substrings
# is replaced by `<redacted>` when a value dict passes through
# `redact_sensitive_fields`. Matches datamasque-python's SENSITIVE_REQUEST_DATA_KEYS.
_SENSITIVE_FIELD_SUBSTRINGS = ("password", "secret", "token", "key", "credential")
_REDACTED = "<redacted>"

# Mirrors the server's limit: at or above this, validation is queued and returns no verdict.
MAX_SYNC_VALIDATION_KIB = 60
_BYTES_PER_KIB = 1024


class ErrorCode(StrEnum):
    """Stable, machine-readable error categories.

    StrEnum members are str subclasses, so the value flows directly into
    the JSON envelope's `error.code` field via `json.dumps`.
    """

    ERROR = "error"
    NOT_FOUND = "not_found"
    INVALID_INPUT = "invalid_input"
    AMBIGUOUS = "ambiguous"
    AUTH_REQUIRED = "auth_required"
    AUTH_FAILED = "auth_failed"
    CONFLICT = "conflict"
    TRANSPORT_ERROR = "transport_error"
    CANCELLED = "cancelled"


class ExitCode(IntEnum):
    """Every process exit status the CLI can return."""

    OK = 0
    ERROR = 1
    USAGE_ERROR = 2
    NOT_FOUND = 3
    INVALID_INPUT = 4
    AMBIGUOUS = 5
    AUTH_REQUIRED = 6
    AUTH_FAILED = 7
    CONFLICT = 8
    TRANSPORT_ERROR = 9
    CANCELLED = 10


# Stable across minor versions so agents can branch on them. `OK` and `USAGE_ERROR`
# are absent because `abort()` never produces them; typer returns 2 by itself.
EXIT_CODE_BY_ERROR: dict[ErrorCode, ExitCode] = {
    ErrorCode.ERROR: ExitCode.ERROR,
    ErrorCode.NOT_FOUND: ExitCode.NOT_FOUND,
    ErrorCode.INVALID_INPUT: ExitCode.INVALID_INPUT,
    ErrorCode.AMBIGUOUS: ExitCode.AMBIGUOUS,
    ErrorCode.AUTH_REQUIRED: ExitCode.AUTH_REQUIRED,
    ErrorCode.AUTH_FAILED: ExitCode.AUTH_FAILED,
    ErrorCode.CONFLICT: ExitCode.CONFLICT,
    ErrorCode.TRANSPORT_ERROR: ExitCode.TRANSPORT_ERROR,
    ErrorCode.CANCELLED: ExitCode.CANCELLED,
}


def redact_sensitive_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `data` with values of sensitive-named keys replaced by `<redacted>`.

    Matches any key whose lowercased name contains `password`, `secret`, `token`,
    `key`, or `credential`. Does not recurse into nested dicts/lists.
    """
    return {
        key: _REDACTED if any(word in key.lower() for word in _SENSITIVE_FIELD_SUBSTRINGS) else value
        for key, value in data.items()
    }


def is_agent_context() -> bool:
    """True when output is being consumed by a script or agent rather than a human.

    Detects, in order:
    - `DM_OUTPUT=table` → forced human (returns False)
    - `DM_OUTPUT=json`  → forced agent
    - `AI_AGENT` set    → vendor-neutral agent signal
    - stdout is not a TTY (piped, captured, redirected)
    """
    output_pref = os.environ.get("DM_OUTPUT", "").strip().lower()
    if output_pref == "table":
        return False
    if output_pref == "json":
        return True
    if os.environ.get("AI_AGENT"):
        return True
    return not sys.stdout.isatty()


def should_emit_json(is_json_flag: bool = False) -> bool:
    """Resolve whether the CLI should emit JSON for this command.

    `--json` always wins; otherwise we fall through to `is_agent_context()`.
    """
    if is_json_flag:
        return True
    return is_agent_context()


def print_json(data: object) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


def _cell(value: object) -> Text:
    """Coerce a cell value into a `Text` so Rich treats it literally.

    Without this, square brackets in YAML inline lists (e.g. `path: [a, b]`)
    are parsed by Rich as console markup tags and silently dropped from the
    rendered cell. `Text` instances pass through unchanged so callers that
    *want* styling (see `style_status`) still work.
    """
    if value is None:
        return Text("")
    if isinstance(value, Text):
        return value
    return Text(str(value))


def print_table(
    columns: list[str],
    rows: list[list[Any]],
    title: str | None = None,
) -> None:
    table = Table(title=title, show_header=True, header_style="bold cyan")
    for col in columns:
        # overflow="fold" wraps long values (e.g. UUIDs) onto multiple lines
        # rather than silently ellipsizing them, so IDs stay copyable in narrow terminals.
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(*[_cell(v) for v in row])
    stdout_console.print(table)


def print_kv(data: dict[str, Any], title: str | None = None) -> None:
    """Print key-value pairs as a two-column table."""
    table = Table(title=title, show_header=False, show_edge=False, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value", overflow="fold")
    for key, value in data.items():
        table.add_row(key, _cell(value))
    stdout_console.print(table)


def print_success(message: str) -> None:
    # Decorative confirmation. Suppressed in agent mode — exit code 0 already
    # signals success and an agent doesn't need the prose.
    if is_agent_context():
        return
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[yellow]Warning:[/yellow] {message}")


def print_info(message: str) -> None:
    if is_agent_context():
        return
    console.print(f"[dim]{message}[/dim]")


def style_status(status: str) -> Text:
    """Wrap a run status string in the appropriate colour tag.

    Returns a `Text` (not a markup string) so it passes through `print_table`
    and `print_kv` unchanged. Returning a raw markup string would be re-escaped
    by `_cell` and lose its colour.
    """
    return Text(status, style=f"status.{status}")


def render_output(
    data: object,
    *,
    is_json: bool,
    columns: list[str] | None = None,
    title: str | None = None,
) -> None:
    """Unified output dispatcher.

    Emits JSON to stdout when `should_emit_json(is_json)` is True (i.e. the
    `--json` flag was passed or we detected an agent context). Otherwise
    renders a rich table from a list-of-dicts or a key-value dict.
    """
    if should_emit_json(is_json):
        print_json(data)
        return

    if not data:
        print_info("No results.")
        return

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        cols = columns or list(data[0].keys())
        rows = [[item.get(c) for c in cols] for item in data]
        print_table(cols, rows, title=title)
    elif isinstance(data, dict):
        print_kv(data, title=title)
    else:
        typer.echo(data)


def abort(message: str, *, code: ErrorCode = ErrorCode.ERROR, hint: str | None = None) -> NoReturn:
    """Print an error and exit with the exit code mapped to `code`.

    In agent mode, emits a structured error envelope to stderr:
        {"error": {"code": "...", "message": "...", "hint": "..."}}
    In human mode, prints a red 'Error: …' line plus an optional hint.

    `code` is an `ErrorCode` member (StrEnum), so it serializes directly
    into the envelope's `error.code` field as the underlying string.
    """
    if is_agent_context():
        envelope: dict[str, Any] = {"error": {"code": code, "message": message}}
        if hint:
            envelope["error"]["hint"] = hint
        typer.echo(json.dumps(envelope), err=True)
    else:
        print_error(message)
        if hint:
            console.print(f"[dim]Hint: {hint}[/dim]")
    raise SystemExit(EXIT_CODE_BY_ERROR[code])


def confirm_or_abort(message: str) -> None:
    """Ask `message`, and abort with `cancelled` when the answer is no."""
    if typer.confirm(message):
        return
    abort("Cancelled.", code=ErrorCode.CANCELLED)


def abort_api_error(prefix: str, exc: DataMasqueApiError, *, conflict_hint: str | None = None) -> NoReturn:
    """Abort with DataMasque's explanation of a failed request."""
    try:
        body = exc.response.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    reason = detail if isinstance(detail, str) else str(exc)

    if exc.response.status_code == HTTPStatus.CONFLICT:
        abort(reason, code=ErrorCode.CONFLICT, hint=conflict_hint)
    abort(f"{prefix}: {reason}", code=ErrorCode.ERROR)


def abort_if_invalid(subject: str, is_valid: ValidationStatus | None, errors: list[ValidationErrorDetails]) -> None:
    """Print each server-side validation error for `subject` and exit, if it failed validation."""
    if is_valid is not ValidationStatus.invalid and not errors:
        return
    for error in errors:
        location = f" (line {error.line_number})" if error.line_number is not None else ""
        print_error(f"{error.message}{location}")
    abort(f"{subject} is invalid.", code=ErrorCode.INVALID_INPUT)


def abort_if_empty(yaml_content: str, file: Path) -> None:
    """Abort when `file` holds no YAML for the server to act on."""
    if yaml_content:
        return
    abort(f"{file} contains no YAML content.", code=ErrorCode.INVALID_INPUT)


def abort_if_too_large_for_sync_validation(
    yaml_content: str, *, subject: str, create_command: str, status_command: str
) -> None:
    """Abort when `yaml_content` is too large for the server to validate synchronously."""
    size = len(yaml_content.encode("utf-8"))
    if size < MAX_SYNC_VALIDATION_KIB * _BYTES_PER_KIB:
        return
    abort(
        f"{subject} is {size // _BYTES_PER_KIB} KiB; "
        f"validation for YAML of {MAX_SYNC_VALIDATION_KIB} KiB or larger runs asynchronously.",
        code=ErrorCode.INVALID_INPUT,
        hint=f"Create it with `{create_command}`, then check `{status_command}` until validation finishes.",
    )
