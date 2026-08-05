"""Discovery config library management commands (configurable discovery)."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from pathlib import Path

import typer
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.discovery_config_library import DiscoveryConfigLibrary
from datamasque.client.models.status import ValidationStatus

from datamasque_cli.client import get_client
from datamasque_cli.errors import ErrorCode, ExitCode, abort, abort_api_error, confirm_or_abort
from datamasque_cli.fileio import FileKind, read_text_or_abort
from datamasque_cli.output import print_success, print_warning, render_output

app = typer.Typer(help="Manage discovery config libraries (configurable discovery).", no_args_is_help=True)


def _format_library_label(name: str, namespace: str) -> str:
    """Render a library's display label as `namespace/name`, or bare `name` in the default namespace."""
    return f"{namespace}/{name}" if namespace else name


@app.command("list")
def list_libraries(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all discovery config libraries."""
    client = get_client(profile)
    libraries = client.list_discovery_config_libraries()

    data = [
        {
            "id": lib.id,
            "namespace": lib.namespace or "",
            "name": lib.name,
            "valid": lib.is_valid.value if lib.is_valid else "unknown",
            "used_by": lib.usage_count,
        }
        for lib in libraries
    ]

    render_output(
        data,
        is_json=is_json,
        columns=["id", "namespace", "name", "valid", "used_by"],
        title="Discovery Config Libraries",
    )


@app.command("get")
def get_library(
    name: str = typer.Argument(help="Library name"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a discovery config library's details or YAML content."""
    client = get_client(profile)
    lib = client.get_discovery_config_library_by_name(name, namespace)

    if lib is None:
        abort(
            f"Discovery config library '{_format_library_label(name, namespace)}' not found.",
            code=ErrorCode.NOT_FOUND,
        )

    if is_yaml:
        typer.echo(lib.yaml)
        return

    data: dict[str, object] = {
        "id": lib.id,
        "namespace": lib.namespace,
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
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a discovery config library from a YAML file."""
    yaml_content = read_text_or_abort(file, FileKind.DISCOVERY_CONFIG_LIBRARY)

    client = get_client(profile)
    library = DiscoveryConfigLibrary(name=name, namespace=namespace, yaml=yaml_content)
    client.create_or_update_discovery_config_library(library)
    print_success(f"Discovery config library '{_format_library_label(name, namespace)}' created/updated.")


@app.command("delete")
def delete_library(
    name: str = typer.Argument(help="Library name to delete"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    force: bool = typer.Option(False, "--force", help="Force delete even if imported by discovery configs"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a discovery config library by name.

    If the library is imported by any discovery configs,
    the server rejects the delete unless --force is passed.
    """
    label = _format_library_label(name, namespace)

    client = get_client(profile)
    if client.get_discovery_config_library_by_name(name, namespace) is None:
        abort(f"Discovery config library '{label}' not found.", code=ErrorCode.NOT_FOUND)

    if not is_confirmed:
        confirm_or_abort(f"Delete discovery config library '{label}'?")

    try:
        client.delete_discovery_config_library_by_name_if_exists(name, namespace, force=force)
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
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Validate a discovery config library YAML file against the DataMasque server.

    Creates a temporary library to trigger server-side validation,
    then deletes it. Reports any validation errors.
    """
    yaml_content = read_text_or_abort(file, FileKind.DISCOVERY_CONFIG_LIBRARY)
    temp_name = f"__dm_cli_validate_{uuid.uuid4().hex}"

    client = get_client(profile)
    library = DiscoveryConfigLibrary(name=temp_name, yaml=yaml_content)

    try:
        created = client.create_discovery_config_library(library)
    except DataMasqueApiError as exc:
        abort_api_error(
            f'Validation of discovery config library "{file.name}" failed',
            exc,
            status_codes={HTTPStatus.BAD_REQUEST: ErrorCode.INVALID_INPUT},
        )

    try:
        if created.is_valid is ValidationStatus.invalid:
            abort(
                f'Discovery config library "{file.name}" is invalid: {created.validation_error}',
                code=ErrorCode.INVALID_INPUT,
            )

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
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a discovery config library's validation status.

    Exits 0 when valid, 4 when invalid.
    """
    client = get_client(profile)
    lib = client.get_discovery_config_library_by_name(name, namespace)

    if lib is None:
        abort(
            f"Discovery config library '{_format_library_label(name, namespace)}' not found.",
            code=ErrorCode.NOT_FOUND,
        )

    status = lib.is_valid.value if lib.is_valid else "unknown"
    data: dict[str, object] = {
        "namespace": lib.namespace,
        "name": lib.name,
        "status": status,
        "validation_error": lib.validation_error,
    }
    render_output(data, is_json=is_json, title=f"Discovery Config Library: {lib.name}")

    if lib.is_valid is ValidationStatus.invalid:
        raise SystemExit(ExitCode.INVALID_INPUT)
