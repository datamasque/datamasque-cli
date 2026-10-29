"""Table reference management commands."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.connection import ConnectionId
from datamasque.client.models.table_reference import TableReference, TableReferenceFormat, TableReferenceOptions

from datamasque_cli.client import get_client, resolve_connection
from datamasque_cli.errors import ErrorCode, abort, abort_api_error, confirm_or_abort, require_id_or_abort
from datamasque_cli.fileio import read_model_or_abort
from datamasque_cli.output import print_success, render_output
from datamasque_cli.projects import (
    PROJECT_OPTION_HELP,
    in_project,
    project_label,
    project_names,
    require_single_or_abort,
    resolve_create_project,
    resolve_optional_project,
)

app = typer.Typer(
    help=(
        "Manage table references — named pointers to identity data (a CSV/Parquet file in a file "
        "connection, or a schema.table in a database connection) that a ruleset addresses by name "
        "for cross-system consistent masking."
    ),
    no_args_is_help=True,
)

_SOURCE_HELP = "File path within the connection (file connections), or a dotted schema.table (database connections)"
_CSV_OPTION_HELP = "(file connections using --format csv only)"
_CREATE_FORMAT_HELP = "csv if unset (server default), or parquet — file connections only, never inferred from --source"
_UPDATE_FORMAT_HELP = "csv or parquet, unchanged if omitted — file connections only, never inferred from --source"


def _abort_if_unsupported(exc: DataMasqueApiError) -> None:
    """Explain a 404 from the table-references listing as an absent feature, not an absent object.

    The listing endpoint takes no name filter, so both readers below fetch the whole collection.
    A 404 from either therefore means the route itself is missing on an older server. Only the
    readers may use this: a write targets `/api/table-references/<id>/`, where a 404 means that
    one reference is gone.
    """
    if exc.response.status_code != HTTPStatus.NOT_FOUND:
        return
    abort("Table references are not supported by this DataMasque version.", code=ErrorCode.NOT_FOUND)


def _list_or_abort(client: DataMasqueClient) -> list[TableReference]:
    """Return every table reference, or abort with the reason the listing failed."""
    try:
        # `datamasque.*` is exempted from mypy's `follow_imports`, so the SDK call resolves to
        # `Any` here even though `list_table_references` itself declares `-> list[TableReference]`.
        references: list[TableReference] = client.list_table_references()
        return references
    except DataMasqueApiError as exc:
        _abort_if_unsupported(exc)
        abort_api_error("Failed to list table references", exc)


def _get_or_abort(client: DataMasqueClient, name: str, project: str | None) -> TableReference:
    """Return the table reference named `name`, in `project` or in the one project that has it, else abort."""
    named = [ref for ref in _list_or_abort(client) if ref.name == name]
    return require_single_or_abort(
        client, in_project(named, resolve_optional_project(client, project)), f"Table reference '{name}'"
    )


@app.command("list")
def list_references(
    project: str | None = typer.Option(None, "--project", help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all table references, or those in one project."""
    client = get_client(profile)
    references = in_project(_list_or_abort(client), resolve_optional_project(client, project))
    names = project_names(client)

    data = [
        {
            "id": ref.id,
            "project": project_label(names, ref.project),
            "name": ref.name,
            "connection": ref.connection_id,
            "source": ref.source,
        }
        for ref in references
    ]

    render_output(
        data, is_json=is_json, columns=["id", "project", "name", "connection", "source"], title="Table References"
    )


@app.command("get")
def get_reference(
    name: str = typer.Argument(help="Table reference name"),
    project: str | None = typer.Option(
        None, "--project", help="Project name or id; required when references in two projects share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show details for a specific table reference."""
    client = get_client(profile)
    reference = _get_or_abort(client, name, project)

    options = reference.options
    data: dict[str, object] = {
        "id": reference.id,
        "project": project_label(project_names(client), reference.project),
        "name": reference.name,
        "connection": reference.connection_id,
        "source": reference.source,
        "format": options.format.value if options else None,
        "delimiter": options.delimiter if options else None,
        "encoding": options.encoding if options else None,
        "quotechar": options.quotechar if options else None,
        "null_string": options.null_string if options else None,
        "created": reference.created,
        "modified": reference.modified,
    }
    render_output(data, is_json=is_json, title=f"Table Reference: {name}")


def _resolve_connection_id(
    client: DataMasqueClient, name_or_id: str, project: str | None, reference_project: str | None
) -> ConnectionId:
    """
    Resolve a `--connection` value (name or ID), narrowed by `--project`, to a connection ID.

    Without `--project`, a connection of that name in the reference's own project is used,
    so a name that other projects share needs no `--project`. Otherwise every project is searched.
    """
    if project is None:
        own = [c for c in client.list_connections() if c.name == name_or_id and c.project == reference_project]
        if own:
            return own[0].id
    return resolve_connection(client, name_or_id, project).id


def _option_overrides(
    file_format: TableReferenceFormat | None,
    delimiter: str | None,
    encoding: str | None,
    quotechar: str | None,
    null_string: str | None,
) -> dict[str, object]:
    """Return only the format/CSV fields that were explicitly passed."""
    overrides: dict[str, object] = {}
    if file_format is not None:
        overrides["format"] = file_format
    if delimiter is not None:
        overrides["delimiter"] = delimiter
    if encoding is not None:
        overrides["encoding"] = encoding
    if quotechar is not None:
        overrides["quotechar"] = quotechar
    if null_string is not None:
        overrides["null_string"] = null_string
    return overrides


@app.command("create")
def create_reference(
    file: Path | None = typer.Option(None, "--file", "-f", help="JSON file defining the table reference"),
    name: str | None = typer.Option(None, help="Table reference name"),
    connection: str | None = typer.Option(None, help="Connection (name or ID) the data lives in"),
    source: str | None = typer.Option(None, help=_SOURCE_HELP),
    file_format: TableReferenceFormat | None = typer.Option(None, "--format", help=_CREATE_FORMAT_HELP),
    delimiter: str | None = typer.Option(None, help=f"CSV delimiter {_CSV_OPTION_HELP}"),
    encoding: str | None = typer.Option(None, help=f"CSV encoding {_CSV_OPTION_HELP}"),
    quotechar: str | None = typer.Option(None, help=f"CSV quote character {_CSV_OPTION_HELP}"),
    null_string: str | None = typer.Option(None, help=f"String read as null {_CSV_OPTION_HELP}"),
    project: str | None = typer.Option(
        None, "--project", help="Project for the reference, also used to find --connection by name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create or update a table reference.

    Use --file for full control (JSON), or flags for the common case.

    Examples:

        # From JSON file
        dm table-references create --file reference.json

        # Quick file-connection reference
        dm table-references create --name customer_identities \\
            --connection input --source identities/customers.csv

        # Quick database-connection reference
        dm table-references create --name customer_identities \\
            --connection mydb --source public.customers
    """
    client = get_client(profile)

    if file is not None:
        other_flags_passed = any(
            value is not None
            for value in (name, connection, source, file_format, delimiter, encoding, quotechar, null_string)
        )
        if other_flags_passed:
            abort(
                "--file cannot be combined with --name/--connection/--source/--format/CSV-option flags.",
                code=ErrorCode.INVALID_INPUT,
            )
        _create_from_file(client, file, project)
        return

    if name is None or connection is None or source is None:
        abort("Provide either --file or all of --name, --connection, and --source.", code=ErrorCode.INVALID_INPUT)

    overrides = _option_overrides(file_format, delimiter, encoding, quotechar, null_string)
    existing = [ref for ref in _list_or_abort(client) if ref.name == name]
    reference_project = resolve_create_project(client, project, existing)
    reference = TableReference(
        name=name,
        connection=_resolve_connection_id(client, connection, project, reference_project),
        source=source,
        options=TableReferenceOptions(**overrides) if overrides else None,
        project=reference_project,
    )
    _create_or_update(client, reference)
    print_success(f"Table reference '{name}' created/updated.")


def _create_from_file(client: DataMasqueClient, file: Path, project: str | None) -> None:
    """Create a table reference from a JSON file, in the project `--project` names when given."""
    reference = read_model_or_abort(file, TableReference)
    existing = [ref for ref in _list_or_abort(client) if ref.name == reference.name]
    reference.project = resolve_create_project(client, project, existing)
    _create_or_update(client, reference)
    print_success(f"Table reference '{reference.name}' created/updated.")


def _create_or_update(client: DataMasqueClient, reference: TableReference) -> None:
    """Create or update `reference`."""
    try:
        client.create_or_update_table_reference(reference)
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to create/update table reference '{reference.name}'", exc)


@app.command("update")
def update_reference(
    name: str = typer.Argument(help="Table reference name to update"),
    connection: str | None = typer.Option(None, help="New connection (name or ID)"),
    source: str | None = typer.Option(None, help=f"New source. {_SOURCE_HELP}"),
    file_format: TableReferenceFormat | None = typer.Option(None, "--format", help=_UPDATE_FORMAT_HELP),
    delimiter: str | None = typer.Option(None, help=f"New CSV delimiter {_CSV_OPTION_HELP}"),
    encoding: str | None = typer.Option(None, help=f"New CSV encoding {_CSV_OPTION_HELP}"),
    quotechar: str | None = typer.Option(None, help=f"New CSV quote character {_CSV_OPTION_HELP}"),
    null_string: str | None = typer.Option(None, help=f"New null-string value {_CSV_OPTION_HELP}"),
    project: str | None = typer.Option(
        None, "--project", help="Project name or id; required when references in two projects share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Update selected fields on an existing table reference, preserving its ID."""
    overrides = _option_overrides(file_format, delimiter, encoding, quotechar, null_string)
    if connection is None and source is None and not overrides:
        abort("Pass at least one field to update (e.g. --source, --format).", code=ErrorCode.INVALID_INPUT)

    client = get_client(profile)
    reference = _get_or_abort(client, name, project)

    if connection is not None:
        reference.connection = _resolve_connection_id(client, connection, project, reference.project)
    if source is not None:
        reference.source = source
    if overrides:
        # A full PUT can't send a sparse options object, so a reference with no prior options
        # gets the untouched fields filled with `TableReferenceOptions`' own declared defaults —
        # there's no other value to send for them.
        base_options = reference.options or TableReferenceOptions()
        reference.options = base_options.model_copy(update=overrides)

    try:
        client.update_table_reference(reference)
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to update table reference '{name}'", exc)
    print_success(f"Table reference '{name}' updated.")


@app.command("delete")
def delete_reference(
    name: str = typer.Argument(help="Table reference name to delete"),
    project: str | None = typer.Option(
        None, "--project", help="Project name or id; required when references in two projects share a name"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a table reference by name."""
    client = get_client(profile)
    reference = _get_or_abort(client, name, project)

    if not is_confirmed:
        confirm_or_abort(f"Delete table reference '{name}'?")

    try:
        client.delete_table_reference_by_id_if_exists(require_id_or_abort(reference.id, f"table reference '{name}'"))
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to delete table reference '{name}'", exc)
    print_success(f"Table reference '{name}' deleted.")
