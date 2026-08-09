"""Discovery config management commands (configurable discovery)."""

from __future__ import annotations

import uuid
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.discovery_config import DiscoveryConfig, DiscoveryConfigType
from datamasque.client.models.status import ValidationErrorDetails, ValidationStatus

from datamasque_cli.client import get_client
from datamasque_cli.errors import (
    ErrorCode,
    abort,
    abort_api_error,
    abort_if_invalid,
    confirm_or_abort,
    require_id_or_abort,
)
from datamasque_cli.fileio import (
    abort_if_too_large_for_sync_validation,
    read_text_or_abort,
    write_text_or_abort,
)
from datamasque_cli.output import print_info, print_success, print_warning, render_output

app = typer.Typer(help="Manage discovery configs (configurable discovery).", no_args_is_help=True)


def _find_by_name(
    client: DataMasqueClient,
    name: str,
    config_type: DiscoveryConfigType | None = None,
) -> list[DiscoveryConfig]:
    """Return all discovery configs matching `name`, optionally narrowed by `config_type`."""
    matches = [c for c in client.list_discovery_configs() if c.name == name]
    if config_type is not None:
        matches = [c for c in matches if c.config_type is config_type]
    return matches


def _collapse_to_one_or_abort(matches: list[DiscoveryConfig], name: str) -> DiscoveryConfig:
    """Return the single discovery config matching `name`, or abort asking for `--type`."""
    if not matches:
        abort(f"Discovery config '{name}' not found.", code=ErrorCode.NOT_FOUND)
    if len(matches) > 1:
        options = "\n  ".join(f"id={c.id} type={c.config_type.value}" for c in matches)
        abort(
            f"Multiple discovery configs named '{name}':\n  {options}",
            code=ErrorCode.AMBIGUOUS,
            hint="Pass --type database|file to disambiguate.",
        )
    return matches[0]


@app.command("list")
def list_configs(
    config_type: DiscoveryConfigType | None = typer.Option(
        None, "--type", "-t", help="Filter by type: database or file"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all discovery configs."""
    client = get_client(profile)
    configs = client.list_discovery_configs()

    if config_type is not None:
        configs = [c for c in configs if c.config_type is config_type]

    data = [
        {
            "id": c.id,
            "name": c.name,
            "type": c.config_type.value,
            "valid": c.is_valid.value if c.is_valid else "unknown",
        }
        for c in configs
    ]

    render_output(data, is_json=is_json, columns=["id", "name", "type", "valid"], title="Discovery Configs")


@app.command("get")
def get_config(
    name: str = typer.Argument(help="Discovery config name"),
    config_type: DiscoveryConfigType | None = typer.Option(
        None, "--type", "-t", help="Required when two configs share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a discovery config's details or YAML content."""
    client = get_client(profile)
    match = _collapse_to_one_or_abort(_find_by_name(client, name, config_type), name)

    config_id = require_id_or_abort(match.id, f"discovery config '{name}'")
    full = client.get_discovery_config(config_id)

    if is_yaml:
        typer.echo(full.yaml)
        return

    data: dict[str, object] = {
        "id": full.id,
        "name": full.name,
        "type": full.config_type.value,
        "valid": full.is_valid.value if full.is_valid else "unknown",
        "created": full.created,
        "modified": full.modified,
    }
    render_output(data, is_json=is_json, title=f"Discovery Config: {full.name}")


@app.command("defaults")
def get_default_config(
    config_type: DiscoveryConfigType = typer.Option(
        DiscoveryConfigType.database, "--type", "-t", help="Config type: database or file"
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write YAML to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Print the server's built-in default discovery config as YAML."""
    client = get_client(profile)
    # `get_default_discovery_config_yaml` takes no config type, so call `make_request` to pass one.
    response = client.make_request("GET", "/api/discovery/configs/defaults/", params={"config_type": config_type.value})
    yaml_content = response.content.decode("utf-8")

    if output is not None:
        write_text_or_abort(output, yaml_content)
        print_success(f"Default {config_type.value} discovery config written to {output}")
        return

    typer.echo(yaml_content)


@app.command("create")
def create_config(
    name: str = typer.Option(..., help="Discovery config name"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML config file", exists=True, readable=True),
    config_type: DiscoveryConfigType | None = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Config type: database or file. "
            "Required when the config does not yet exist; defaults to the existing type on updates."
        ),
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a discovery config from a YAML file.

    A brand-new config needs --type because there is no stored row to copy the
    type from; an update defaults to whatever the existing row is stored as.
    """
    client = get_client(profile)
    existing = _find_by_name(client, name)

    if config_type is not None:
        resolved_type = config_type
    elif len(existing) == 1:
        resolved_type = existing[0].config_type
        print_info(f"Updating existing {resolved_type.value}-type discovery config '{name}'.")
    elif not existing:
        abort(
            f"No discovery config named '{name}' exists.",
            code=ErrorCode.NOT_FOUND,
            hint="Pass --type database|file to create a new one.",
        )
    else:
        options = ", ".join(c.config_type.value for c in existing)
        abort(
            f"Multiple discovery configs named '{name}' ({options}).",
            code=ErrorCode.AMBIGUOUS,
            hint="Pass --type database|file to pick which one to update.",
        )

    yaml_content = read_text_or_abort(file)

    config = DiscoveryConfig(name=name, yaml=yaml_content, config_type=resolved_type)
    client.create_or_update_discovery_config(config)
    print_success(f"Discovery config '{name}' ({resolved_type.value}) created/updated.")


@app.command("delete")
def delete_config(
    name: str = typer.Argument(help="Discovery config name to delete"),
    config_type: DiscoveryConfigType | None = typer.Option(
        None, "--type", "-t", help="Required when two configs share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a discovery config by name."""
    client = get_client(profile)
    match = _collapse_to_one_or_abort(_find_by_name(client, name, config_type), name)
    config_id = require_id_or_abort(match.id, f"discovery config '{name}'")

    if not is_confirmed:
        confirm_or_abort(f"Delete discovery config '{name}' ({match.config_type.value})?")

    client.delete_discovery_config_by_id_if_exists(config_id)
    print_success(f"Discovery config '{name}' ({match.config_type.value}) deleted.")


@app.command("validate")
def validate_config(
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML config file", exists=True, readable=True),
    config_type: DiscoveryConfigType = typer.Option(..., "--type", "-t", help="Config type: database or file"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Validate a discovery config YAML file against the DataMasque server.

    Creates a temporary config to trigger server-side validation,
    then deletes it. Reports any validation errors.

    Note that configs over 60 KiB validate asynchronously and cannot be validated here.
    """
    yaml_content = read_text_or_abort(file)
    abort_if_too_large_for_sync_validation(
        yaml_content,
        file,
        create_command=f"dm discover configs create --name <name> --type {config_type.value} -f {file}",
        status_command="dm discover configs status <name>",
    )
    temp_name = f"__dm_cli_validate_{uuid.uuid4().hex}"

    client = get_client(profile)
    config = DiscoveryConfig(name=temp_name, yaml=yaml_content, config_type=config_type)

    try:
        created = client.create_discovery_config(config)
    except DataMasqueApiError as exc:
        abort_api_error(f'Validation of discovery config "{file.name}" failed', exc)

    try:
        errors = created.validation_error_details
        if not errors and created.validation_error:
            errors = [ValidationErrorDetails(message=created.validation_error)]
        abort_if_invalid(f'Discovery config "{file.name}"', created.is_valid, errors)

        status = created.is_valid.value if created.is_valid else "unknown"
        print_success(f'Discovery config "{file.name}" validation status: {status}')
    finally:
        if created.id is not None:
            try:
                client.delete_discovery_config_by_id_if_exists(created.id)
            except DataMasqueApiError as exc:
                print_warning(f"Validation config '{temp_name}' left on server; delete manually. Reason: {exc}")


@app.command("status")
def show_config_status(
    name: str = typer.Argument(help="Discovery config name"),
    config_type: DiscoveryConfigType | None = typer.Option(
        None, "--type", "-t", help="Required when two configs share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a discovery config's validation status."""
    client = get_client(profile)
    match = _collapse_to_one_or_abort(_find_by_name(client, name, config_type), name)

    status = match.is_valid.value if match.is_valid else "unknown"
    data: dict[str, object] = {
        "name": match.name,
        "type": match.config_type.value,
        "status": status,
        "validation_error": match.validation_error,
    }
    render_output(data, is_json=is_json, title=f"Discovery Config: {match.name}")

    if match.is_valid is ValidationStatus.in_progress:
        print_info("Still validating — run this command again shortly.")
