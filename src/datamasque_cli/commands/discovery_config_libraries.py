"""Discovery config library management commands (configurable discovery)."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.models.discovery_config import DiscoveryConfigType
from datamasque.client.models.discovery_config_library import DiscoveryConfigLibrary
from datamasque.client.models.status import ValidationStatus

from datamasque_cli.client import get_client
from datamasque_cli.output import ErrorCode, abort, print_info, print_success, render_output

app = typer.Typer(help="Manage discovery config libraries (configurable discovery).", no_args_is_help=True)


def _label(name: str, namespace: str) -> str:
    """Render a library's display label as `namespace/name`, or bare `name` in the default namespace."""
    return f"{namespace}/{name}" if namespace else name


def _find_by_name(
    client: DataMasqueClient,
    name: str,
    config_type: DiscoveryConfigType | None = None,
    namespace: str | None = None,
) -> list[DiscoveryConfigLibrary]:
    """Return all libraries matching `name`, optionally narrowed by `namespace` and `config_type`."""
    matches = [lib for lib in client.list_discovery_config_libraries() if lib.name == name]
    if namespace is not None:
        matches = [lib for lib in matches if lib.namespace == namespace]
    if config_type is not None:
        matches = [lib for lib in matches if lib.config_type is config_type]
    return matches


def _pick_single(matches: list[DiscoveryConfigLibrary], name: str) -> DiscoveryConfigLibrary:
    """Return the sole match or abort with a disambiguation message."""
    if not matches:
        abort(f"Discovery config library '{name}' not found.", code=ErrorCode.NOT_FOUND)
    if len(matches) > 1:
        options = "\n  ".join(
            f"id={lib.id} namespace={lib.namespace or '(default)'} type={lib.config_type.value}" for lib in matches
        )
        abort(
            f"Multiple discovery config libraries named '{name}':\n  {options}",
            code=ErrorCode.AMBIGUOUS,
            hint="Pass --type file|database and/or --namespace to disambiguate.",
        )
    return matches[0]


@app.command("list")
def list_libraries(
    config_type: str | None = typer.Option(None, "--type", "-t", help="Filter by type: database or file"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all discovery config libraries."""
    client = get_client(profile)
    libraries = client.list_discovery_config_libraries()

    if config_type is not None:
        wanted = DiscoveryConfigType(config_type)
        libraries = [lib for lib in libraries if lib.config_type is wanted]

    data = [
        {
            "id": lib.id,
            "namespace": lib.namespace or "",
            "name": lib.name,
            "type": lib.config_type.value,
            "valid": lib.is_valid.value if lib.is_valid else "unknown",
        }
        for lib in libraries
    ]

    render_output(
        data,
        is_json=is_json,
        columns=["id", "namespace", "name", "type", "valid"],
        title="Discovery Config Libraries",
    )


@app.command("get")
def get_library(
    name: str = typer.Argument(help="Library name"),
    config_type: str | None = typer.Option(None, "--type", "-t", help="Required when two libraries share a name"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a discovery config library's details or YAML content."""
    client = get_client(profile)
    wanted = DiscoveryConfigType(config_type) if config_type is not None else None
    match = _pick_single(_find_by_name(client, name, wanted, namespace), name)

    # `list_discovery_config_libraries` omits the YAML body; fetch the single library for it.
    assert match.id is not None
    full = client.get_discovery_config_library(match.id)

    if is_yaml:
        typer.echo(full.yaml)
        return

    data: dict[str, object] = {
        "id": full.id,
        "namespace": full.namespace,
        "name": full.name,
        "type": full.config_type.value,
        "valid": full.is_valid.value if full.is_valid else "unknown",
        "created": full.created,
        "modified": full.modified,
    }
    render_output(data, is_json=is_json, title=f"Discovery Config Library: {full.name}")


@app.command("create")
def create_library(
    name: str = typer.Option(..., help="Library name"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML library file", exists=True, readable=True),
    config_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Config type: database or file. "
            "Required when the library does not yet exist; defaults to the existing type on updates."
        ),
    ),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a discovery config library from a YAML file."""
    client = get_client(profile)
    existing = _find_by_name(client, name, namespace=namespace)
    explicit = DiscoveryConfigType(config_type) if config_type is not None else None

    if explicit is not None:
        lib_type = explicit
    elif len(existing) == 1:
        lib_type = existing[0].config_type
        print_info(f"Updating existing {lib_type.value}-type library '{_label(name, namespace)}'.")
    elif not existing:
        abort(
            f"No discovery config library named '{_label(name, namespace)}' exists.",
            code=ErrorCode.NOT_FOUND,
            hint="Pass --type file|database to create a new one.",
        )
    else:
        options = ", ".join(lib.config_type.value for lib in existing)
        abort(
            f"Multiple libraries named '{_label(name, namespace)}' ({options}).",
            code=ErrorCode.AMBIGUOUS,
            hint="Pass --type file|database to pick which one to update.",
        )

    yaml_content = file.read_text()
    library = DiscoveryConfigLibrary(name=name, namespace=namespace, yaml=yaml_content, config_type=lib_type)
    client.create_or_update_discovery_config_library(library)
    print_success(f"Discovery config library '{_label(name, namespace)}' ({lib_type.value}) created/updated.")


@app.command("delete")
def delete_library(
    name: str = typer.Argument(help="Library name to delete"),
    config_type: str | None = typer.Option(None, "--type", "-t", help="Required when two libraries share a name"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    force: bool = typer.Option(False, "--force", help="Force delete even if imported by discovery configs"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a discovery config library by name.

    If the library is imported by any discovery configs,
    the server rejects the delete unless --force is passed.
    """
    client = get_client(profile)
    wanted = DiscoveryConfigType(config_type) if config_type is not None else None
    match = _pick_single(_find_by_name(client, name, wanted, namespace), name)
    label = _label(name, namespace)

    if not is_confirmed:
        typer.confirm(f"Delete discovery config library '{label}' ({match.config_type.value})?", abort=True)

    assert match.id is not None
    client.delete_discovery_config_library_by_id_if_exists(match.id, force=force)
    print_success(f"Discovery config library '{label}' deleted.")


@app.command("validate")
def validate_library(
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML library file", exists=True, readable=True),
    config_type: str = typer.Option(..., "--type", "-t", help="Config type: database or file"),
    namespace: str = typer.Option("", "--namespace", "-n", help="Library namespace"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Validate a discovery config library YAML file against the DataMasque server."""
    yaml_content = file.read_text()
    lib_type = DiscoveryConfigType(config_type)

    client = get_client(profile)
    library = DiscoveryConfigLibrary(name=file.stem, namespace=namespace, yaml=yaml_content, config_type=lib_type)
    validated = client.validate_discovery_config_library(library)

    if validated.is_valid is ValidationStatus.invalid:
        abort(
            f'Discovery config library "{file.name}" is invalid: {validated.validation_error}',
            code=ErrorCode.INVALID_INPUT,
        )

    status = validated.is_valid.value if validated.is_valid else "unknown"
    print_success(f'Discovery config library "{file.name}" validation status: {status}')
