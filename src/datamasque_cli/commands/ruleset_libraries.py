"""Ruleset library management commands."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ruleset_library import RulesetLibrary
from datamasque.client.models.status import ValidationStatus

from datamasque_cli.client import get_client
from datamasque_cli.errors import abort_api_error, abort_if_invalid, confirm_or_abort
from datamasque_cli.fileio import read_text_or_abort
from datamasque_cli.output import print_info, print_success, render_output, should_emit_json
from datamasque_cli.projects import (
    PROJECT_OPTION_HELP,
    in_project,
    project_label,
    project_names,
    require_single_or_abort,
    resolve_create_project,
    resolve_optional_project,
)

app = typer.Typer(help="Manage ruleset libraries.", no_args_is_help=True)


def _find_library(client: DataMasqueClient, name: str, project: str | None) -> RulesetLibrary:
    """Return the library named `name`, with its YAML, in `project` or in the one project that has it."""
    matches = [lib for lib in client.list_ruleset_libraries() if lib.name == name]
    matches = in_project(matches, resolve_optional_project(client, project))
    found = require_single_or_abort(client, matches, f"Library '{name}'")
    return client.get_ruleset_library(found.id)


@app.command("list")
def list_libraries(
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all ruleset libraries, or those in one project."""
    client = get_client(profile)
    libraries = in_project(client.list_ruleset_libraries(), resolve_optional_project(client, project))
    names = project_names(client)

    data = [
        {
            "id": lib.id,
            "project": project_label(names, lib.project),
            "name": lib.name,
            "valid": lib.is_valid.value if lib.is_valid else "unknown",
        }
        for lib in libraries
    ]

    render_output(data, is_json=is_json, columns=["id", "project", "name", "valid"], title="Ruleset Libraries")


@app.command("get")
def get_library(
    name: str = typer.Argument(help="Library name"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a library's details or YAML content."""
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
        "created": lib.created,
        "modified": lib.modified,
    }
    render_output(data, is_json=is_json, title=f"Library: {lib.name}")


@app.command("create")
def create_library(
    name: str = typer.Option(..., help="Library name"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML library file", exists=True, readable=True),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a ruleset library from a YAML file."""
    yaml_content = read_text_or_abort(file)
    client = get_client(profile)

    existing = [lib for lib in client.list_ruleset_libraries() if lib.name == name]
    library = RulesetLibrary(name=name, project=resolve_create_project(client, project, existing), yaml=yaml_content)
    client.create_or_update_ruleset_library(library)
    print_success(f"Library '{name}' created/updated.")


@app.command("delete")
def delete_library(
    name: str = typer.Argument(help="Library name to delete"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    force: bool = typer.Option(False, "--force", help="Force delete even if imported by rulesets"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a ruleset library by name."""
    label = name

    client = get_client(profile)
    lib = _find_library(client, name, project)

    if not is_confirmed:
        confirm_or_abort(f"Delete library '{label}'?")

    try:
        client.delete_ruleset_library_by_id_if_exists(lib.id, force=force)
    except DataMasqueApiError as exc:
        abort_api_error(
            f"Failed to delete library '{label}'",
            exc,
            conflict_hint="Re-run with --force to delete it and flag the dependent rulesets for revalidation.",
        )

    print_success(f"Library '{label}' deleted.")


@app.command("validate")
def validate_library(
    name: str = typer.Argument(help="Library name"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Re-validate a ruleset library against the current server schema.

    Triggers a server-side validation pass on an existing library and reports the result.
    """
    label = name

    client = get_client(profile)
    lib = _find_library(client, name, project)

    try:
        validated = client.validate_ruleset_library(lib.id)
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to validate library '{label}'", exc)
    abort_if_invalid(f"Library '{label}'", validated.is_valid, validated.validation_errors)

    status = validated.is_valid.value if validated.is_valid else "unknown"
    print_success(f"Library '{label}' validation status: {status}")


@app.command("status")
def show_library_status(
    name: str = typer.Argument(help="Library name"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a ruleset library's validation status."""
    client = get_client(profile)
    lib = _find_library(client, name, project)

    status = lib.is_valid.value if lib.is_valid else "unknown"
    errors = lib.validation_errors or []
    data: dict[str, object] = {
        "project": project_label(project_names(client), lib.project),
        "name": lib.name,
        "status": status,
    }
    if should_emit_json(is_json):
        data["errors"] = [error.model_dump(mode="json") for error in errors]
    else:
        data["errors"] = "; ".join(error.message for error in errors)
    render_output(data, is_json=is_json, title=f"Library: {lib.name}")

    if lib.is_valid is ValidationStatus.in_progress:
        print_info("Still validating — run this command again shortly.")


@app.command("usage")
def library_usage(
    name: str = typer.Argument(help="Library name"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show which rulesets import a given library."""
    client = get_client(profile)
    lib = _find_library(client, name, project)

    rulesets = client.list_rulesets_using_library(lib.id)
    names = project_names(client)

    data = [
        {
            "id": rs.id,
            "project": project_label(names, rs.project),
            "name": rs.name,
            "type": rs.ruleset_type.value,
        }
        for rs in rulesets
    ]

    render_output(data, is_json=is_json, columns=["id", "project", "name", "type"], title=f"Rulesets using '{name}'")
