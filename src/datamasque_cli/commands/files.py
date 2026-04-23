"""File management commands (Oracle wallets, Snowflake keys, etc.)."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client.models.files import DataMasqueFile, SnowflakeKeyFile

from datamasque_cli.client import get_client
from datamasque_cli.output import abort, print_success, render_output

app = typer.Typer(help="Manage uploaded files (Oracle wallets, Snowflake keys).")

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
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List uploaded files of a given type."""
    klass = _resolve_file_type(file_type)
    client = get_client(profile)
    files = client.list_files_of_type(klass)

    data = [{"id": f.id, "name": f.name} for f in files]
    render_output(data, is_json=is_json, columns=["id", "name"], title=f"Files ({file_type})")


@app.command("delete")
def delete_file(
    file_type: str = typer.Argument(help="File type: snowflake-key"),
    name: str = typer.Argument(help="File name"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a previously uploaded file by name."""
    klass = _resolve_file_type(file_type)
    client = get_client(profile)

    match = client.get_file_of_type_by_name(klass, name)
    if match is None:
        abort(f"File '{name}' ({file_type}) not found.")

    if not is_confirmed:
        typer.confirm(f"Delete file '{name}' ({file_type})?", abort=True)

    client.delete_file_if_exists(match)
    print_success(f"File '{name}' deleted.")


@app.command("upload")
def upload_file(
    file_type: str = typer.Argument(help="File type: snowflake-key"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to file", exists=True, readable=True),
    name: str = typer.Option(..., help="Name for the uploaded file"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Upload a file."""
    klass = _resolve_file_type(file_type)
    client = get_client(profile)
    client.upload_file(klass, name, file)
    print_success(f"File '{name}' uploaded as {file_type}.")
