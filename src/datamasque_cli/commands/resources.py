"""Commands that act on resources of any type."""

from __future__ import annotations

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.exceptions import DataMasqueApiError, ResourceMoveConflictError
from datamasque.client.models.project import Project
from datamasque.client.models.resource import Resource, ResourceMoveConflict
from datamasque.client.models.resource_type import ResourceTypeName

from datamasque_cli.client import get_client
from datamasque_cli.errors import ErrorCode, abort, abort_api_error, confirm_or_abort
from datamasque_cli.output import print_success, render_output
from datamasque_cli.projects import PROJECT_OPTION_HELP, get_named_project, project_label

app = typer.Typer(help="Work with resources of every type.", no_args_is_help=True)

MOVE_CHECK_CONFLICT_MESSAGE = "Some resources would not move"


def _describe_resource_count(count: int) -> str:
    return f"{count} resource" if count == 1 else f"{count} resources"


def _get_conflict_details(conflicts: list[ResourceMoveConflict]) -> list[str]:
    """Return each conflict's detail once, in order, since resources that clash the same way share a detail."""
    return list(dict.fromkeys(conflict.detail for conflict in conflicts))


def _get_resources_to_move(
    client: DataMasqueClient,
    *,
    names: list[str],
    sources: list[Project] | None,
    type_names: list[ResourceTypeName] | None,
    search: str | None,
    destination: Project,
) -> dict[ResourceTypeName, list[Resource]]:
    """
    Return the resources the filters select, by type, leaving out those already in the destination.

    Built-in seeds belong to no project and cannot move, so they are left out too.
    Aborts with not-found when a name matches none of the resources the other filters select.
    """
    listed = client.list_resources(projects=sources, types=type_names, search=search)
    listed_names = {resource.name for resources in listed.values() for resource in resources}
    if unmatched_names := [name for name in dict.fromkeys(names) if name not in listed_names]:
        abort(
            f"No resources named {', '.join(repr(name) for name in unmatched_names)}.",
            code=ErrorCode.NOT_FOUND,
            hint="Check the names, and that --project, --type and --search select them.",
        )
    selected = {
        type_name: [
            resource
            for resource in resources
            if resource.project not in (None, destination.reference) and (not names or resource.name in names)
        ]
        for type_name, resources in listed.items()
    }
    return {type_name: resources for type_name, resources in selected.items() if resources}


@app.command("move")
def move_resources(
    names: list[str] | None = typer.Argument(
        None, help="Exact names of the resources to move, of any type unless --type is given; omit to move every match"
    ),
    destination: str = typer.Option(..., "--to", help="Project to move the resources to: name or id"),
    sources: list[str] | None = typer.Option(
        None, "--project", help=f"Move from this project only. {PROJECT_OPTION_HELP}; repeatable"
    ),
    type_names: list[ResourceTypeName] | None = typer.Option(None, "--type", help="Move this type only; repeatable"),
    search: str | None = typer.Option(None, help="Move resources whose name contains every word of this, any case"),
    is_check_only: bool = typer.Option(
        False, "--check", help="Only list the resources and what would stop them moving"
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Move resources to another project, with their files and runs.

    Select them by project, type, a name search or exact names; the filters combine.
    All of them move, or none do: a resource that clashes with the destination stops the move.
    A resource already in the destination stays there, and the others move.
    Rulesets and configurations whose library imports resolve differently after the move become invalid.
    """
    if not (names or sources or type_names or search):
        abort(
            "Select the resources to move.",
            code=ErrorCode.INVALID_INPUT,
            hint="Pass resource names, --project, --type or --search.",
        )

    client = get_client(profile)
    projects = client.list_projects()
    target = get_named_project(projects, destination)
    selected = _get_resources_to_move(
        client,
        names=names or [],
        sources=[get_named_project(projects, source) for source in sources] if sources else None,
        type_names=type_names,
        search=search,
        destination=target,
    )
    if not selected:
        abort(f"No resources to move to '{target.name}'.", code=ErrorCode.NOT_FOUND)

    # The selection leaves out resources in no project, and a deleted project has no resources left.
    project_names_by_reference = {project.reference: project.name for project in projects}
    rows = [
        {
            "type": type_name.value,
            "name": resource.name,
            "project": project_label(project_names_by_reference, resource.project),
        }
        for type_name, resources in selected.items()
        for resource in resources
    ]
    render_output(
        rows, is_json=is_json, columns=["type", "name", "project"], title=f"Resources to move to {target.name}"
    )

    if is_check_only:
        try:
            conflicts = client.get_resource_move_conflicts(selected, target)
        except DataMasqueApiError as exc:
            abort_api_error("Failed to check the move", exc)
        if conflicts:
            abort(MOVE_CHECK_CONFLICT_MESSAGE, code=ErrorCode.CONFLICT, details=_get_conflict_details(conflicts))
        print_success(f"All {_describe_resource_count(len(rows))} can move to '{target.name}'.")
        return

    if not is_confirmed:
        confirm_or_abort(f"Move {_describe_resource_count(len(rows))} to '{target.name}'?")

    try:
        result = client.move_resources(selected, target)
    except ResourceMoveConflictError as exc:
        abort(
            f"No resources moved to '{target.name}'",
            code=ErrorCode.CONFLICT,
            details=_get_conflict_details(exc.conflicts),
        )
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to move resources to '{target.name}'", exc)

    print_success(f"Moved {_describe_resource_count(result.moved)} to '{target.name}'.")
