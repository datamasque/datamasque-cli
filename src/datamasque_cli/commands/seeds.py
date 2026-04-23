"""Seed file management commands."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client.models.files import SeedFile

from datamasque_cli.client import get_client
from datamasque_cli.output import abort, print_success, render_output

app = typer.Typer(help="Manage seed files.", no_args_is_help=True)


@app.command("list")
def list_seeds(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all seed files."""
    client = get_client(profile)
    seeds = client.list_files_of_type(SeedFile)

    data = [{"id": s.id, "name": s.name} for s in seeds]
    render_output(data, is_json=is_json, columns=["id", "name"], title="Seed Files")


@app.command("upload")
def upload_seed(
    file: Path = typer.Argument(help="Path to seed file", exists=True, readable=True),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Upload a seed file."""
    client = get_client(profile)
    client.upload_file(SeedFile, file.name, file)
    print_success(f"Seed file '{file.name}' uploaded.")


@app.command("delete")
def delete_seed(
    filename: str = typer.Argument(help="Seed filename to delete"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a seed file by filename."""
    client = get_client(profile)
    match = client.get_file_of_type_by_name(SeedFile, filename)
    if match is None:
        abort(f"Seed file '{filename}' not found.")

    if not is_confirmed:
        typer.confirm(f"Delete seed file '{filename}'?", abort=True)

    client.delete_file_if_exists(match)
    print_success(f"Seed file '{filename}' deleted.")
