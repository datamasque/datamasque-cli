"""Ruleset management commands."""

from __future__ import annotations

import uuid
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.base import UploadFile
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.discovery import FileRulesetGenerationRequest, RulesetGenerationRequest
from datamasque.client.models.ruleset import Ruleset, RulesetType
from datamasque.client.models.status import ValidationStatus
from pydantic import ValidationError

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
    read_json_object_or_abort,
    read_text_or_abort,
    write_bytes_or_abort,
    write_text_or_abort,
)
from datamasque_cli.output import print_info, print_success, print_warning, render_output, should_emit_json
from datamasque_cli.projects import (
    PROJECT_OPTION_HELP,
    in_project,
    project_label,
    project_names,
    resolve_create_project,
    resolve_optional_project,
    resolve_project,
    resolve_target_project,
)

app = typer.Typer(help="Manage masking rulesets.", no_args_is_help=True)


def _find_by_name(
    client: DataMasqueClient,
    name: str,
    mask_type: RulesetType | None = None,
    project: str | None = None,
) -> list[Ruleset]:
    """Return all rulesets matching `name`, optionally narrowed by `mask_type` and by the project `--project` names."""
    matches = [rs for rs in client.list_rulesets() if rs.name == name]
    if mask_type is not None:
        matches = [rs for rs in matches if rs.ruleset_type == mask_type]
    return in_project(matches, resolve_optional_project(client, project))


def _require_single_matched_ruleset_or_abort(
    client: DataMasqueClient, matched_rulesets: list[Ruleset], name: str
) -> Ruleset:
    """Return the single ruleset matching `name`, or abort asking for `--type` or `--project`."""
    if not matched_rulesets:
        abort(f"Ruleset '{name}' not found.", code=ErrorCode.NOT_FOUND)
    if len(matched_rulesets) > 1:
        names = project_names(client)
        options = "\n  ".join(
            f"id={rs.id} type={rs.ruleset_type.value} project={project_label(names, rs.project)}"
            for rs in matched_rulesets
        )
        abort(
            f"Multiple rulesets named '{name}':\n  {options}",
            code=ErrorCode.AMBIGUOUS,
            hint="Pass --type database|file or --project to disambiguate.",
        )
    return matched_rulesets[0]


@app.command("list")
def list_rulesets(
    ruleset_type: RulesetType | None = typer.Option(None, "--type", "-t", help="Filter by type: database or file"),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all rulesets, or those in one project."""
    client = get_client(profile)
    rulesets = in_project(client.list_rulesets(), resolve_optional_project(client, project))

    if ruleset_type is not None:
        rulesets = [rs for rs in rulesets if rs.ruleset_type == ruleset_type]

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

    render_output(data, is_json=is_json, columns=["id", "project", "name", "type"], title="Rulesets")


@app.command("get")
def get_ruleset(
    name: str = typer.Argument(help="Ruleset name"),
    ruleset_type: RulesetType | None = typer.Option(
        None, "--type", "-t", help="Required when two rulesets share a name"
    ),
    project: str | None = typer.Option(
        None, "--project", help="Project name or id; required when rulesets in two projects share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_yaml: bool = typer.Option(False, "--yaml", help="Output raw YAML content only"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a ruleset's details or YAML content."""
    client = get_client(profile)
    match = _require_single_matched_ruleset_or_abort(client, _find_by_name(client, name, ruleset_type, project), name)

    # `list_rulesets` omits the YAML body for performance; fetch the single ruleset
    # to populate `yaml` via the Ruleset pydantic model's `config_yaml` alias.
    response = client.make_request("GET", f"/api/rulesets/{match.id}/")
    full = Ruleset.model_validate(response.json())

    if is_yaml:
        typer.echo(full.yaml)
        return

    data: dict[str, object] = {
        "id": full.id,
        "project": project_label(project_names(client), full.project),
        "name": full.name,
        "type": full.ruleset_type.value,
        "yaml": full.yaml,
    }
    render_output(data, is_json=is_json, title=f"Ruleset: {name}")


@app.command("create")
def create_ruleset(
    name: str = typer.Option(..., help="Ruleset name"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML ruleset file", exists=True, readable=True),
    ruleset_type: RulesetType | None = typer.Option(
        None,
        "--type",
        "-t",
        help=(
            "Ruleset type: database or file. "
            "Required when the ruleset does not yet exist; defaults to the existing type on updates."
        ),
    ),
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a ruleset from a YAML file.

    Read the server first to decide which type the upload has. A
    brand-new ruleset needs --type because there is no stored row to copy the
    type from; an update defaults to whatever the existing row is stored as.
    """
    client = get_client(profile)
    existing = _find_by_name(client, name, project=project)

    if ruleset_type is not None:
        rs_type = ruleset_type
    elif len(existing) == 1:
        rs_type = existing[0].ruleset_type
        print_info(f"Updating existing {rs_type.value}-type ruleset '{name}'.")
    elif not existing:
        abort(
            f"No ruleset named '{name}' exists.",
            code=ErrorCode.NOT_FOUND,
            hint="Pass --type database|file to create a new one.",
        )
    else:
        names = project_names(client)
        options = ", ".join(f"{r.ruleset_type.value} in {project_label(names, r.project)}" for r in existing)
        abort(
            f"Multiple rulesets named '{name}' ({options}).",
            code=ErrorCode.AMBIGUOUS,
            hint="Pass --type database|file or --project to pick which one to update.",
        )

    yaml_content = read_text_or_abort(file)
    ruleset = Ruleset(
        name=name,
        yaml=yaml_content,
        ruleset_type=rs_type,
        project=resolve_create_project(client, project, [r for r in existing if r.ruleset_type is rs_type]),
    )
    client.create_or_update_ruleset(ruleset)
    print_success(f"Ruleset '{name}' ({rs_type.value}) created/updated.")


@app.command("delete")
def delete_ruleset(
    name: str = typer.Argument(help="Ruleset name to delete"),
    ruleset_type: RulesetType | None = typer.Option(
        None, "--type", "-t", help="Required when two rulesets share a name"
    ),
    project: str | None = typer.Option(
        None, "--project", help="Project name or id; required when rulesets in two projects share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a ruleset by name."""
    client = get_client(profile)
    match = _require_single_matched_ruleset_or_abort(client, _find_by_name(client, name, ruleset_type, project), name)
    ruleset_id = require_id_or_abort(match.id, f"ruleset '{name}'")

    if not is_confirmed:
        confirm_or_abort(f"Delete ruleset '{name}' ({match.ruleset_type.value})?")

    client.delete_ruleset_by_id_if_exists(ruleset_id)
    print_success(f"Ruleset '{name}' ({match.ruleset_type.value}) deleted.")


@app.command("validate")
def validate_ruleset(
    file: Path = typer.Option(..., "--file", "-f", help="Path to YAML ruleset file", exists=True, readable=True),
    ruleset_type: RulesetType = typer.Option(
        ...,
        "--type",
        "-t",
        help="Ruleset type: database or file",
    ),
    project: str | None = typer.Option(
        None, "--project", help="Project to validate in; required when the instance has more than one"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Validate a ruleset YAML file against the DataMasque server.

    Creates a temporary ruleset in the project to trigger server-side validation,
    then deletes it. Reports any validation errors.

    Note that rulesets over 60 KiB validate asynchronously and cannot be validated here.
    """
    yaml_content = read_text_or_abort(file)
    abort_if_too_large_for_sync_validation(
        yaml_content,
        file,
        create_command=f"dm rulesets create --name <name> --type {ruleset_type.value} -f {file}",
        status_command="dm rulesets status <name>",
    )
    # `uuid` guards against collisions between concurrent `validate` runs.
    temp_name = f"__dm_cli_validate_{uuid.uuid4().hex}"

    client = get_client(profile)
    target = resolve_target_project(client, project)
    ruleset = Ruleset(name=temp_name, yaml=yaml_content, ruleset_type=ruleset_type, project=target.reference)

    try:
        created = client.create_or_update_ruleset(ruleset)
    except DataMasqueApiError as exc:
        abort_api_error(f"Validation of ruleset '{file.name}' failed", exc)

    # `try/finally` so a Ctrl-C or unexpected exception between create and
    # delete still cleans up the temp ruleset on the server.
    try:
        abort_if_invalid(f"Ruleset '{file.name}' ({ruleset_type.value})", created.is_valid, created.validation_errors)
        status = created.is_valid.value if created.is_valid else "unknown"
        print_success(f"Ruleset '{file.name}' ({ruleset_type.value}) validation status: {status}")
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
    users, licences, or instance settings. Each item is filed under its project.
    """
    client = get_client(profile)
    # `export_configuration` is not yet wrapped in datamasque-python; hit the endpoint directly.
    response = client.make_request("GET", "/api/export/v2/")
    write_bytes_or_abort(output_path, response.content)
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
    fallback_project: str | None = typer.Option(
        None,
        "--fallback-project",
        help="Project name or id for the items the bundle files under no project. "
        "Defaults to the server's default project.",
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Import rulesets, ruleset libraries, and seed files from a ZIP bundle.

    Bundle must have been produced by `dm rulesets export-bundle` or the
    server's export endpoint. Each item goes into the project the bundle files it
    under; items under no project, such as those in an older bundle, go into
    `--fallback-project`. By default, duplicates are skipped; pass `--overwrite-*`
    flags to replace existing entries.
    """
    if not is_confirmed:
        confirm_or_abort("This will modify rulesets, libraries, and seed files. Continue?")

    client = get_client(profile)
    data = {
        "overwrite_rulesets": str(overwrite_rulesets).lower(),
        "overwrite_libraries": str(overwrite_libraries).lower(),
        "overwrite_seed_files": str(overwrite_seeds).lower(),
    }
    if fallback_project is not None:
        data["fallback_project"] = str(resolve_project(client, fallback_project).id)

    # `/api/import/v2/` expects a multipart `zip_archive` upload plus the overwrite
    # flags and an optional `fallback_project`; `import_configuration` is not yet
    # wrapped in datamasque-python, so we call `make_request` directly.
    with file.open("rb") as zip_content:
        response = client.make_request(
            "POST",
            "/api/import/v2/",
            data=data,
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
    if response.headers.get("Deprecation") == "true":
        print_warning(
            "This bundle is in the older format. Items it files under no project went into the fallback project."
        )
    if response.content:
        try:
            summary = response.json()
        except ValueError:
            return
        if isinstance(summary, dict):
            render_output(summary, is_json=False, title="Import summary")


@app.command("status")
def show_ruleset_status(
    name: str = typer.Argument(help="Ruleset name"),
    ruleset_type: RulesetType | None = typer.Option(
        None, "--type", "-t", help="Required when two rulesets share a name"
    ),
    project: str | None = typer.Option(
        None, "--project", help="Project name or id; required when rulesets in two projects share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a ruleset's validation status."""
    client = get_client(profile)
    match = _require_single_matched_ruleset_or_abort(client, _find_by_name(client, name, ruleset_type, project), name)

    status = match.is_valid.value if match.is_valid else "unknown"
    errors = match.validation_errors or []
    data: dict[str, object] = {
        "project": project_label(project_names(client), match.project),
        "name": match.name,
        "type": match.ruleset_type.value,
        "status": status,
    }
    if should_emit_json(is_json):
        data["errors"] = [error.model_dump(mode="json") for error in errors]
    else:
        data["errors"] = "; ".join(error.message for error in errors)
    render_output(data, is_json=is_json, title=f"Ruleset: {match.name}")

    if match.is_valid is ValidationStatus.in_progress:
        print_info("Still validating — run this command again shortly.")


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
    raw_request = read_json_object_or_abort(request_file)

    try:
        if is_file_ruleset:
            yaml_content = client.generate_file_ruleset(FileRulesetGenerationRequest.model_validate(raw_request))
        else:
            yaml_content = client.generate_ruleset(RulesetGenerationRequest.model_validate(raw_request))
    except ValidationError as exc:
        abort(f"Invalid generation request in {request_file}: {exc}", code=ErrorCode.INVALID_INPUT)

    if output is not None:
        write_text_or_abort(output, yaml_content)
        print_success(f"Generated ruleset written to {output}")
    else:
        typer.echo(yaml_content)
