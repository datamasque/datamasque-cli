"""File management commands (Oracle wallets, Snowflake keys, etc.)."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client.models.files import DataMasqueFile, SnowflakeKeyFile

from datamasque_cli.client import get_client
from datamasque_cli.errors import confirm_or_abort
from datamasque_cli.output import print_success, render_output
from datamasque_cli.projects import (
    PROJECT_OPTION_HELP,
    in_project,
    project_label,
    project_names,
    require_single_or_abort,
    resolve_optional_project,
    resolve_target_project,
)

app = typer.Typer(help="Manage uploaded files (Oracle wallets, Snowflake keys).", no_args_is_help=True)

# Map user-friendly type names to their classes.
_FILE_TYPES: dict[str, type[DataMasqueFile]] = {
    "snowflake-key": SnowflakeKeyFile,
}


def _resolve_file_type(type_name: str) -> type[DataMasqueFile]:
    if type_name not in _FILE_TYPES:
        valid = ", ".join(_FILE_TYPES)
        msg = f"Unknown file type '{type_name}'. Valid types: {valid}"
        raise typer.BadParameter(msg)
    return _FILE_TYPES[type_name]


@app.command("list")
def list_files(
    file_type: str = typer.Argument(help="File type: snowflake-key"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List uploaded files of a given type, or those in one project."""
    klass = _resolve_file_type(file_type)
    client = get_client(profile)
    target = resolve_optional_project(client, project)
    files = client.list_files_of_type(klass, project=target.id if target else None)
    names = project_names(client)

    data = [{"id": f.id, "project": project_label(names, f.project), "name": f.name} for f in files]
    render_output(data, is_json=is_json, columns=["id", "project", "name"], title=f"Files ({file_type})")


@app.command("delete")
def delete_file(
    file_type: str = typer.Argument(help="File type: snowflake-key"),
    name: str = typer.Argument(help="File name"),
    project: str | None = typer.Option(
        None, "--project", help="Project name or id; required when files in two projects share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a previously uploaded file by name."""
    klass = _resolve_file_type(file_type)
    client = get_client(profile)

    named = [f for f in client.list_files_of_type(klass) if f.name == name]
    match = require_single_or_abort(
        client, in_project(named, resolve_optional_project(client, project)), f"File '{name}' ({file_type})"
    )

    if not is_confirmed:
        confirm_or_abort(f"Delete file '{name}' ({file_type})?")

    client.delete_file_if_exists(match)
    print_success(f"File '{name}' deleted.")


@app.command("upload")
def upload_file(
    file_type: str = typer.Argument(help="File type: snowflake-key"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to file", exists=True, readable=True),
    name: str = typer.Option(..., help="Name for the uploaded file"),
    project: str | None = typer.Option(
        None, "--project", help="Project to upload to; required when the instance has more than one"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Upload a file."""
    klass = _resolve_file_type(file_type)
    client = get_client(profile)
    target = resolve_target_project(client, project)
    client.upload_file(klass, name, file, project=target.id)
    print_success(f"File '{name}' uploaded as {file_type}.")
