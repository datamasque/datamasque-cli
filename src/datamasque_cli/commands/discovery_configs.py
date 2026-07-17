"""Discovery config management commands (configurable discovery)."""

from __future__ import annotations

from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.models.discovery_config import DiscoveryConfig, DiscoveryConfigType
from datamasque.client.models.status import ValidationStatus

from datamasque_cli.client import get_client
from datamasque_cli.output import ErrorCode, abort, print_info, print_success, render_output

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


def _pick_single(matches: list[DiscoveryConfig], name: str) -> DiscoveryConfig:
    """Return the sole match or abort with a disambiguation message."""
    if not matches:
        abort(f"Discovery config '{name}' not found.", code=ErrorCode.NOT_FOUND)
    if len(matches) > 1:
        options = "\n  ".join(f"id={c.id} type={c.config_type.value}" for c in matches)
        abort(
            f"Multiple discovery configs named '{name}':\n  {options}",
            code=ErrorCode.AMBIGUOUS,
            hint="Pass --type file|database to disambiguate.",
        )
    return matches[0]


@app.command("list")
def list_configs(
    config_type: str | None = typer.Option(None, "--type", "-t", help="Filter by type: database or file"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all discovery configs."""
    client = get_client(profile)
    configs = client.list_discovery_configs()

    if config_type is not None:
        wanted = DiscoveryConfigType(config_type)
        configs = [c for c in configs if c.config_type is wanted]

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
    config_type: str | None = typer.Option(None, "--type", "-t", help="Required when two configs share a name"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a discovery config's details or YAML content."""
    client = get_client(profile)
    wanted = DiscoveryConfigType(config_type) if config_type is not None else None
    match = _pick_single(_find_by_name(client, name, wanted), name)

    assert match.id is not None
    full = client.get_discovery_config(match.id)

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
def config_defaults(
    config_type: str = typer.Option("database", "--type", "-t", help="Config type: database or file"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write YAML to this path"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Print the server's built-in default discovery config as YAML."""
    client = get_client(profile)
    wanted = DiscoveryConfigType(config_type)
    # `get_default_discovery_config_yaml` takes no config type, so call `make_request` to pass one.
    response = client.make_request("GET", "/api/discovery/configs/defaults/", params={"config_type": wanted.value})
    yaml_content = response.content.decode("utf-8")

    if output is not None:
        output.write_text(yaml_content)
        print_success(f"Default {wanted.value} discovery config written to {output}")
        return

    typer.echo(yaml_content)


@app.command("create")
def create_config(
    name: str = typer.Option(..., help="Discovery config name"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML config file", exists=True, readable=True),
    config_type: str | None = typer.Option(
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
    explicit = DiscoveryConfigType(config_type) if config_type is not None else None

    if explicit is not None:
        cfg_type = explicit
    elif len(existing) == 1:
        cfg_type = existing[0].config_type
        print_info(f"Updating existing {cfg_type.value}-type discovery config '{name}'.")
    elif not existing:
        abort(
            f"No discovery config named '{name}' exists.",
            code=ErrorCode.NOT_FOUND,
            hint="Pass --type file|database to create a new one.",
        )
    else:
        options = ", ".join(c.config_type.value for c in existing)
        abort(
            f"Multiple discovery configs named '{name}' ({options}).",
            code=ErrorCode.AMBIGUOUS,
            hint="Pass --type file|database to pick which one to update.",
        )

    yaml_content = file.read_text()
    config = DiscoveryConfig(name=name, yaml=yaml_content, config_type=cfg_type)
    client.create_or_update_discovery_config(config)
    print_success(f"Discovery config '{name}' ({cfg_type.value}) created/updated.")


@app.command("delete")
def delete_config(
    name: str = typer.Argument(help="Discovery config name to delete"),
    config_type: str | None = typer.Option(None, "--type", "-t", help="Required when two configs share a name"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a discovery config by name."""
    client = get_client(profile)
    wanted = DiscoveryConfigType(config_type) if config_type is not None else None
    match = _pick_single(_find_by_name(client, name, wanted), name)

    if not is_confirmed:
        typer.confirm(f"Delete discovery config '{name}' ({match.config_type.value})?", abort=True)

    assert match.id is not None
    client.delete_discovery_config_by_id_if_exists(match.id)
    print_success(f"Discovery config '{name}' ({match.config_type.value}) deleted.")


@app.command("validate")
def validate_config(
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML config file", exists=True, readable=True),
    config_type: str = typer.Option(..., "--type", "-t", help="Config type: database or file"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Validate a discovery config YAML file against the DataMasque server."""
    yaml_content = file.read_text()
    cfg_type = DiscoveryConfigType(config_type)

    client = get_client(profile)
    config = DiscoveryConfig(name=file.stem, yaml=yaml_content, config_type=cfg_type)
    validated = client.validate_discovery_config(config)

    if validated.is_valid is ValidationStatus.invalid:
        abort(
            f'Discovery config "{file.name}" is invalid: {validated.validation_error}',
            code=ErrorCode.INVALID_INPUT,
        )

    status = validated.is_valid.value if validated.is_valid else "unknown"
    print_success(f'Discovery config "{file.name}" validation status: {status}')
