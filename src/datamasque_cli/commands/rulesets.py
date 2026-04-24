"""Ruleset management commands."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.base import UploadFile
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ruleset import Ruleset, RulesetType

from datamasque_cli.client import get_client
from datamasque_cli.output import abort, print_error, print_info, print_success, print_warning, render_output

app = typer.Typer(help="Manage masking rulesets.", no_args_is_help=True)


def _find_by_name(
    client: DataMasqueClient,
    name: str,
    mask_type: RulesetType | None = None,
) -> list[Ruleset]:
    """Return all rulesets matching `name`, optionally narrowed by `mask_type`."""
    matches = [rs for rs in client.list_rulesets() if rs.name == name]
    if mask_type is not None:
        matches = [rs for rs in matches if rs.ruleset_type == mask_type]
    return matches


def _pick_single(matches: list[Ruleset], name: str) -> Ruleset:
    """Return the sole match or abort with a disambiguation message."""
    if not matches:
        abort(f"Ruleset '{name}' not found.")
    if len(matches) > 1:
        options = "\n  ".join(f"id={rs.id} type={rs.ruleset_type.value}" for rs in matches)
        abort(f"Multiple rulesets named '{name}':\n  {options}\nPass --type file|database to disambiguate.")
    return matches[0]


@app.command("list")
def list_rulesets(
    ruleset_type: str | None = typer.Option(None, "--type", "-t", help="Filter by type: database or file"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all rulesets."""
    client = get_client(profile)
    rulesets = client.list_rulesets()

    if ruleset_type is not None:
        wanted = RulesetType(ruleset_type)
        rulesets = [rs for rs in rulesets if rs.ruleset_type == wanted]

    data = [
        {
            "id": rs.id,
            "name": rs.name,
            "type": rs.ruleset_type.value,
        }
        for rs in rulesets
    ]

    render_output(data, is_json=is_json, columns=["id", "name", "type"], title="Rulesets")


@app.command("get")
def get_ruleset(
    name: str = typer.Argument(help="Ruleset name"),
    ruleset_type: str | None = typer.Option(None, "--type", "-t", help="Required when two rulesets share a name"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a ruleset's details or YAML content."""
    client = get_client(profile)
    wanted = RulesetType(ruleset_type) if ruleset_type is not None else None
    match = _pick_single(_find_by_name(client, name, wanted), name)

    # `list_rulesets` omits the YAML body for performance; fetch the single ruleset
    # to populate `yaml` via the Ruleset pydantic model's `config_yaml` alias.
    response = client.make_request("GET", f"/api/rulesets/{match.id}/")
    full = Ruleset.model_validate(response.json())

    if is_yaml:
        typer.echo(full.yaml)
        return

    data: dict[str, object] = {
        "id": full.id,
        "name": full.name,
        "type": full.ruleset_type.value,
        "yaml": full.yaml,
    }
    render_output(data, is_json=is_json, title=f"Ruleset: {name}")


@app.command("create")
def create_ruleset(
    name: str = typer.Option(..., help="Ruleset name"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML ruleset file", exists=True, readable=True),
    ruleset_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Ruleset type: database or file. "
            "Required when the ruleset does not yet exist; defaults to the existing type on updates."
        ),
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a ruleset from a YAML file.

    Read the server first to decide which namespace the upload belongs in. A
    brand-new ruleset needs --type because there is no stored row to copy the
    type from; an update defaults to whatever the existing row is stored as.
    """
    client = get_client(profile)
    existing = _find_by_name(client, name)
    explicit = RulesetType(ruleset_type) if ruleset_type is not None else None

    if explicit is not None:
        rs_type = explicit
    elif len(existing) == 1:
        rs_type = existing[0].ruleset_type
        print_info(f"Updating existing {rs_type.value}-type ruleset '{name}'.")
    elif not existing:
        abort(f"No ruleset named '{name}' exists. Pass --type file|database to create a new one.")
    else:
        options = ", ".join(r.ruleset_type.value for r in existing)
        abort(f"Multiple rulesets named '{name}' ({options}). Pass --type file|database to pick which one to update.")

    yaml_content = file.read_text()
    ruleset = Ruleset(name=name, yaml=yaml_content, ruleset_type=rs_type)
    client.create_or_update_ruleset(ruleset)
    print_success(f"Ruleset '{name}' ({rs_type.value}) created/updated.")


@app.command("delete")
def delete_ruleset(
    name: str = typer.Argument(help="Ruleset name to delete"),
    ruleset_type: str | None = typer.Option(None, "--type", "-t", help="Required when two rulesets share a name"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a ruleset by name."""
    client = get_client(profile)
    wanted = RulesetType(ruleset_type) if ruleset_type is not None else None
    match = _pick_single(_find_by_name(client, name, wanted), name)

    if not is_confirmed:
        typer.confirm(f"Delete ruleset '{name}' ({match.ruleset_type.value})?", abort=True)

    assert match.id is not None  # Populated by list_rulesets
    client.delete_ruleset_by_id_if_exists(match.id)
    print_success(f"Ruleset '{name}' ({match.ruleset_type.value}) deleted.")


@app.command("validate")
def validate_ruleset(
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML ruleset file", exists=True, readable=True),
    ruleset_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Ruleset type: database or file",
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Validate a ruleset YAML file against the DataMasque server.

    Creates a temporary ruleset to trigger server-side validation,
    then deletes it. Reports any validation errors.
    """
    yaml_content = file.read_text()
    rs_type = RulesetType(ruleset_type)
    # `uuid` guards against collisions between concurrent `validate` runs.
    temp_name = f"__dm_cli_validate_{uuid.uuid4().hex}"

    client = get_client(profile)
    ruleset = Ruleset(name=temp_name, yaml=yaml_content, ruleset_type=rs_type)

    try:
        created = client.create_or_update_ruleset(ruleset)
    except DataMasqueApiError as exc:
        print_error(f"Validation failed: {exc}")
        raise SystemExit(1) from None

    # `try/finally` so a Ctrl-C or unexpected exception between create and
    # delete still cleans up the temp ruleset on the server.
    try:
        print_success(f"Ruleset '{file.name}' ({rs_type.value}) is valid.")
    finally:
        if created.id is not None:
            try:
                client.delete_ruleset_by_id_if_exists(created.id)
            except DataMasqueApiError as exc:
                print_warning(f"Validation ruleset '{temp_name}' left on server; delete manually. Reason: {exc}")


@app.command("export-bundle")
def export_bundle(
    output_path: Path = typer.Option("datamasque-bundle.zip", "--output", "-o", help="Where to save the ZIP bundle"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Export rulesets, ruleset libraries, and any referenced seed files as a ZIP bundle.

    Bundles only rulesets + libraries + optional seed files — not connections,
    users, licences, or instance settings.
    """
    client = get_client(profile)
    # `export_configuration` is not yet wrapped in datamasque-python; hit the endpoint directly.
    response = client.make_request("GET", "/api/export/v1/")
    output_path.write_bytes(response.content)
    print_success(f"Bundle exported to {output_path}")


@app.command("import-bundle")
def import_bundle(
    file: Path = typer.Option(..., "--file", "-f", help="Path to bundle ZIP", exists=True, readable=True),
    overwrite_rulesets: bool = typer.Option(
        False, "--overwrite-rulesets", help="Overwrite rulesets that already exist with the same name"
    ),
    overwrite_libraries: bool = typer.Option(
        False, "--overwrite-libraries", help="Overwrite ruleset libraries that already exist with the same name"
    ),
    overwrite_seeds: bool = typer.Option(
        False, "--overwrite-seeds", help="Overwrite seed files that already exist with the same name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Import rulesets, ruleset libraries, and seed files from a ZIP bundle.

    Bundle must have been produced by `dm rulesets export-bundle` or the
    server's `/api/export/v1/` endpoint. By default, duplicates are skipped;
    pass `--overwrite-*` flags to replace existing entries.
    """
    if not is_confirmed:
        typer.confirm("This will modify rulesets, libraries, and seed files. Continue?", abort=True)

    client = get_client(profile)
    # `/api/import/v1/` expects a multipart `zip_archive` upload plus three
    # optional boolean overwrite flags; `import_configuration` is not yet
    # wrapped in datamasque-python, so we call `make_request` directly.
    with file.open("rb") as zip_content:
        response = client.make_request(
            "POST",
            "/api/import/v1/",
            data={
                "overwrite_rulesets": str(overwrite_rulesets).lower(),
                "overwrite_libraries": str(overwrite_libraries).lower(),
                "overwrite_seed_files": str(overwrite_seeds).lower(),
            },
            files=[
                UploadFile(
                    field_name="zip_archive",
                    filename=file.name,
                    content=zip_content,
                    content_type="application/zip",
                ),
            ],
        )

    print_success("Bundle imported successfully.")
    if response.content:
        try:
            summary = response.json()
        except ValueError:
            return
        if isinstance(summary, dict):
            render_output(summary, is_json=False, title="Import summary")


@app.command("generate")
def generate_ruleset(
    request_file: Path = typer.Option(
        ..., "--file", "-f", help="Path to JSON generation request", exists=True, readable=True
    ),
    is_file_ruleset: bool = typer.Option(False, "--file-ruleset", help="Generate a file masking ruleset"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write generated YAML to file"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Generate a ruleset from a generation request (JSON).

    The request JSON format matches the DataMasque API's /api/generate-ruleset/v2/ endpoint.
    """
    client = get_client(profile)
    generation_request = json.loads(request_file.read_text())

    if is_file_ruleset:
        yaml_content = client.generate_file_ruleset(generation_request)
    else:
        yaml_content = client.generate_ruleset(generation_request)

    if output is not None:
        output.write_text(yaml_content)
        print_success(f"Generated ruleset written to {output}")
    else:
        typer.echo(yaml_content)
