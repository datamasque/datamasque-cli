"""Ruleset library management commands."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ruleset_library import RulesetLibrary
from datamasque.client.models.status import ValidationStatus

from datamasque_cli.client import get_client
from datamasque_cli.output import (
    ErrorCode,
    ExitCode,
    abort,
    abort_api_error,
    abort_if_invalid,
    confirm_or_abort,
    print_info,
    print_success,
    render_output,
    should_emit_json,
)

app = typer.Typer(help="Manage ruleset libraries.", no_args_is_help=True)


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
        abort(f"Library '{label}' not found.", code=ErrorCode.NOT_FOUND)

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
    yaml_content = file.read_text(encoding="utf-8")
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
        abort(f"Library '{label}' not found.", code=ErrorCode.NOT_FOUND)

    if not is_confirmed:
        confirm_or_abort(f"Delete library '{label}'?")

    try:
        client.delete_ruleset_library_by_name_if_exists(name, namespace, force=force)
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
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Re-validate a ruleset library against the current server schema.

    Triggers a server-side validation pass on an existing library and reports the result.
    """
    label = f"{namespace}/{name}" if namespace else name

    client = get_client(profile)
    lib = client.get_ruleset_library_by_name(name, namespace)

    if lib is None:
        abort(f"Library '{label}' not found.", code=ErrorCode.NOT_FOUND)

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
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a ruleset library's validation status."""
    client = get_client(profile)
    lib = client.get_ruleset_library_by_name(name, namespace)

    if lib is None:
        label = f"{namespace}/{name}" if namespace else name
        abort(f"Library '{label}' not found.", code=ErrorCode.NOT_FOUND)

    status = lib.is_valid.value if lib.is_valid else "unknown"
    errors = lib.validation_errors or []
    data: dict[str, object] = {
        "namespace": lib.namespace,
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
    if lib.is_valid is ValidationStatus.invalid:
        raise SystemExit(ExitCode.INVALID_INPUT)


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
        abort(f"Library '{label}' not found.", code=ErrorCode.NOT_FOUND)

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
