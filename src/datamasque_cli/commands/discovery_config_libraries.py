"""Discovery config library management commands (configurable discovery)."""

from __future__ import annotations

import uuid
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.discovery_config_library import DiscoveryConfigLibrary
from datamasque.client.models.status import ValidationErrorDetails

from datamasque_cli.client import get_client
from datamasque_cli.errors import abort_api_error, abort_if_invalid, confirm_or_abort
from datamasque_cli.fileio import read_text_or_abort
from datamasque_cli.output import print_success, print_warning, render_output
from datamasque_cli.projects import (
    PROJECT_OPTION_HELP,
    in_project,
    project_label,
    project_names,
    require_single_or_abort,
    resolve_create_project,
    resolve_optional_project,
    resolve_target_project,
)

app = typer.Typer(help="Manage discovery config libraries (configurable discovery).", no_args_is_help=True)


def _find_library(client: DataMasqueClient, name: str, project: str | None) -> DiscoveryConfigLibrary:
    """Return the library named `name`, with its YAML, in `project` or in the one project that has it."""
    matches = [lib for lib in client.list_discovery_config_libraries() if lib.name == name]
    matches = in_project(matches, resolve_optional_project(client, project))
    found = require_single_or_abort(client, matches, f"Discovery config library '{name}'")
    return client.get_discovery_config_library(found.id)


@app.command("list")
def list_libraries(
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all discovery config libraries, or those in one project."""
    client = get_client(profile)
    libraries = in_project(client.list_discovery_config_libraries(), resolve_optional_project(client, project))
    names = project_names(client)

    data = [
        {
            "id": lib.id,
            "project": project_label(names, lib.project),
            "name": lib.name,
            "valid": lib.is_valid.value if lib.is_valid else "unknown",
            "used_by": lib.usage_count,
        }
        for lib in libraries
    ]

    render_output(
        data,
        is_json=is_json,
        columns=["id", "project", "name", "valid", "used_by"],
        title="Discovery Config Libraries",
    )


@app.command("get")
def get_library(
    name: str = typer.Argument(help="Library name"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a discovery config library's details or YAML content."""
    client = get_client(profile)
    lib = _find_library(client, name, project)

    if is_yaml:
        typer.echo(lib.yaml)
        return

    data: dict[str, object] = {
        "id": lib.id,
        "project": project_label(project_names(client), lib.project),
        "name": lib.name,
        "valid": lib.is_valid.value if lib.is_valid else "unknown",
        "used_by": lib.usage_count,
        "created": lib.created,
        "modified": lib.modified,
    }
    render_output(data, is_json=is_json, title=f"Discovery Config Library: {lib.name}")


@app.command("create")
def create_library(
    name: str = typer.Option(..., help="Library name"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML library file", exists=True, readable=True),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a discovery config library from a YAML file."""
    yaml_content = read_text_or_abort(file)

    client = get_client(profile)
    existing = [lib for lib in client.list_discovery_config_libraries() if lib.name == name]
    library = DiscoveryConfigLibrary(
        name=name, project=resolve_create_project(client, project, existing), yaml=yaml_content
    )
    client.create_or_update_discovery_config_library(library)
    print_success(f"Discovery config library '{name}' created/updated.")


@app.command("delete")
def delete_library(
    name: str = typer.Argument(help="Library name to delete"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    force: bool = typer.Option(False, "--force", help="Force delete even if imported by discovery configs"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a discovery config library by name.

    If the library is imported by any discovery configs,
    the server rejects the delete unless --force is passed.
    """
    label = name

    client = get_client(profile)
    lib = _find_library(client, name, project)

    if not is_confirmed:
        confirm_or_abort(f"Delete discovery config library '{label}'?")

    try:
        client.delete_discovery_config_library_by_id_if_exists(lib.id, force=force)
    except DataMasqueApiError as exc:
        abort_api_error(
            f"Failed to delete discovery config library '{label}'",
            exc,
            conflict_hint="Re-run with --force to delete it and mark the dependent configs invalid.",
        )

    print_success(f"Discovery config library '{label}' deleted.")


@app.command("validate")
def validate_library(
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML library file", exists=True, readable=True),
    project: str | None = typer.Option(
        None, "--project", help="Project to validate in; required when the instance has more than one"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Validate a discovery config library YAML file against the DataMasque server.

    Creates a temporary library in the project to trigger server-side validation,
    then deletes it. Reports any validation errors.
    """
    yaml_content = read_text_or_abort(file)
    temp_name = f"__dm_cli_validate_{uuid.uuid4().hex}"

    client = get_client(profile)
    target = resolve_target_project(client, project)
    library = DiscoveryConfigLibrary(name=temp_name, project=target.reference, yaml=yaml_content)

    try:
        created = client.create_discovery_config_library(library)
    except DataMasqueApiError as exc:
        abort_api_error(f'Validation of discovery config library "{file.name}" failed', exc)

    try:
        errors = [ValidationErrorDetails(message=created.validation_error)] if created.validation_error else []
        abort_if_invalid(f'Discovery config library "{file.name}"', created.is_valid, errors)

        status = created.is_valid.value if created.is_valid else "unknown"
        print_success(f'Discovery config library "{file.name}" validation status: {status}')
    finally:
        if created.id is not None:
            try:
                client.delete_discovery_config_library_by_id_if_exists(created.id)
            except DataMasqueApiError as exc:
                print_warning(f"Validation library '{temp_name}' left on server; delete manually. Reason: {exc}")


@app.command("status")
def show_library_status(
    name: str = typer.Argument(help="Library name"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a discovery config library's validation status."""
    client = get_client(profile)
    lib = _find_library(client, name, project)

    status = lib.is_valid.value if lib.is_valid else "unknown"
    data: dict[str, object] = {
        "project": project_label(project_names(client), lib.project),
        "name": lib.name,
        "status": status,
        "validation_error": lib.validation_error,
    }
    render_output(data, is_json=is_json, title=f"Discovery Config Library: {lib.name}")
