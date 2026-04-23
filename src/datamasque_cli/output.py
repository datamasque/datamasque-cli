"""Output formatting for the CLI.

Supports JSON output (--json) for machine consumption,
and rich tables for human-readable display.
"""

from __future__ import annotations

import json
from typing import Any, NoReturn

import typer
from rich.console import Console
from rich.table import Table
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


def redact_sensitive_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `data` with values of sensitive-named keys replaced by `<redacted>`.

    Matches any key whose lowercased name contains `password`, `secret`, `token`,
    `key`, or `credential`. Does not recurse into nested dicts/lists.
    """
    return {
        key: _REDACTED if any(word in key.lower() for word in _SENSITIVE_FIELD_SUBSTRINGS) else value
        for key, value in data.items()
    }


def print_json(data: object) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


def print_table(
    columns: list[str],
    rows: list[list[Any]],
    title: str | None = None,
) -> None:
    table = Table(title=title, show_header=True, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(v) if v is not None else "" for v in row])
    stdout_console.print(table)


def print_kv(data: dict[str, Any], title: str | None = None) -> None:
    """Print key-value pairs as a two-column table."""
    table = Table(title=title, show_header=False, show_edge=False, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(key, str(value) if value is not None else "")
    stdout_console.print(table)


def print_success(message: str) -> None:
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[yellow]Warning:[/yellow] {message}")


def print_info(message: str) -> None:
    console.print(f"[dim]{message}[/dim]")


def style_status(status: str) -> str:
    """Wrap a run status string in the appropriate colour tag."""
    style_name = f"status.{status}"
    return f"[{style_name}]{status}[/{style_name}]"


def render_output(
    data: object,
    *,
    is_json: bool,
    columns: list[str] | None = None,
    title: str | None = None,
) -> None:
    """Unified output dispatcher.

    When `is_json` is True, dumps `data` as JSON to stdout.
    Otherwise renders a rich table from a list-of-dicts or a key-value dict.
    """
    if is_json:
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


def abort(message: str) -> NoReturn:
    print_error(message)
    raise SystemExit(1)
