"""Ruleset library management commands."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client.models.ruleset_library import RulesetLibrary

from datamasque_cli.client import get_client
from datamasque_cli.output import abort, print_success, render_output

app = typer.Typer(help="Manage ruleset libraries.")


@app.command("list")
def list_libraries(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all ruleset libraries."""
    client = get_client(profile)
    libraries = client.list_ruleset_libraries()

    data = [
        {
            "id": lib.id,
            "namespace": lib.namespace or "",
            "name": lib.name,
            "valid": lib.is_valid.value if lib.is_valid else "unknown",
        }
        for lib in libraries
    ]

    render_output(data, is_json=is_json, columns=["id", "namespace", "name", "valid"], title="Ruleset Libraries")


@app.command("get")
def get_library(
    name: str = typer.Argument(help="Library name"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a library's details or YAML content."""
    client = get_client(profile)
    lib = client.get_ruleset_library_by_name(name, namespace)

    if lib is None:
        label = f"{namespace}/{name}" if namespace else name
        abort(f"Library '{label}' not found.")

    if is_yaml:
        typer.echo(lib.yaml)
        return

    data: dict[str, object] = {
        "id": lib.id,
        "namespace": lib.namespace,
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
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a ruleset library from a YAML file."""
    yaml_content = file.read_text()
    client = get_client(profile)

    library = RulesetLibrary(name=name, namespace=namespace, yaml=yaml_content)
    client.create_or_update_ruleset_library(library)
    print_success(f"Library '{name}' created/updated.")


@app.command("delete")
def delete_library(
    name: str = typer.Argument(help="Library name to delete"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    force: bool = typer.Option(False, "--force", help="Force delete even if imported by rulesets"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a ruleset library by name."""
    label = f"{namespace}/{name}" if namespace else name

    client = get_client(profile)
    if client.get_ruleset_library_by_name(name, namespace) is None:
        abort(f"Library '{label}' not found.")

    if not is_confirmed:
        typer.confirm(f"Delete library '{label}'?", abort=True)

    client.delete_ruleset_library_by_name_if_exists(name, namespace, force=force)
    print_success(f"Library '{label}' deleted.")


@app.command("validate")
def validate_library(
    name: str = typer.Argument(help="Library name"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Re-validate a ruleset library against the current server schema.

    Triggers a server-side validation pass on an existing library and reports the result.
    """
    client = get_client(profile)
    lib = client.get_ruleset_library_by_name(name, namespace)

    if lib is None:
        label = f"{namespace}/{name}" if namespace else name
        abort(f"Library '{label}' not found.")

    validated = client.validate_ruleset_library(lib.id)
    status = validated.is_valid.value if validated.is_valid else "unknown"
    label = f"{namespace}/{name}" if namespace else name
    print_success(f"Library '{label}' validation status: {status}")


@app.command("usage")
def library_usage(
    name: str = typer.Argument(help="Library name"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show which rulesets import a given library."""
    client = get_client(profile)
    lib = client.get_ruleset_library_by_name(name, namespace)

    if lib is None:
        label = f"{namespace}/{name}" if namespace else name
        abort(f"Library '{label}' not found.")

    rulesets = client.list_rulesets_using_library(lib.id)

    data = [
        {
            "id": rs.id,
            "name": rs.name,
            "type": rs.ruleset_type.value,
        }
        for rs in rulesets
    ]

    render_output(data, is_json=is_json, columns=["id", "name", "type"], title=f"Rulesets using '{name}'")
