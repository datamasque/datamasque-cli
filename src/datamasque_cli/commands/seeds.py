"""Seed file management commands."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client.models.files import SeedFile

from datamasque_cli.client import get_client
from datamasque_cli.errors import confirm_or_abort
from datamasque_cli.output import print_success, render_output
from datamasque_cli.projects import (
    in_project,
    project_label,
    project_names,
    require_single_or_abort,
    resolve_optional_project,
    resolve_target_project,
)

app = typer.Typer(help="Manage seed files.", no_args_is_help=True)


@app.command("list")
def list_seeds(
    project: str | None = typer.Option(None, "--project", help="Project name or id; also lists the built-in seeds"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all seed files, or those in one project plus the built-in seeds."""
    client = get_client(profile)
    target = resolve_optional_project(client, project)
    seeds = client.list_files_of_type(SeedFile, project=target.id if target else None)
    names = project_names(client)

    data = [{"id": s.id, "project": project_label(names, s.project), "name": s.name} for s in seeds]
    render_output(data, is_json=is_json, columns=["id", "project", "name"], title="Seed Files")


@app.command("upload")
def upload_seed(
    file: Path = typer.Argument(help="Path to seed file", exists=True, readable=True),
    project: str | None = typer.Option(
        None, "--project", help="Project to upload to; required when the instance has more than one"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Upload a seed file."""
    client = get_client(profile)
    target = resolve_target_project(client, project)
    client.upload_file(SeedFile, file.name, file, project=target.id)
    print_success(f"Seed file '{file.name}' uploaded.")


@app.command("delete")
def delete_seed(
    filename: str = typer.Argument(help="Seed filename to delete"),
    project: str | None = typer.Option(
        None, "--project", help="Project name or id; required when seeds in two projects share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a seed file by filename."""
    client = get_client(profile)
    named = [seed for seed in client.list_files_of_type(SeedFile) if seed.name == filename]
    match = require_single_or_abort(
        client, in_project(named, resolve_optional_project(client, project)), f"Seed file '{filename}'"
    )

    if not is_confirmed:
        confirm_or_abort(f"Delete seed file '{filename}'?")

    client.delete_file_if_exists(match)
    print_success(f"Seed file '{filename}' deleted.")
