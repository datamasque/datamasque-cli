"""Project management commands."""

from __future__ import annotations

import typer
from datamasque.client import DataMasqueClient
from datamasque.client.exceptions import DataMasqueApiError, ProjectDeleteConflictError
from datamasque.client.models.project import Project, ProjectCreateRequest, ProjectUpdateRequest

from datamasque_cli.client import get_client
from datamasque_cli.errors import ErrorCode, abort, abort_api_error, confirm_or_abort
from datamasque_cli.output import print_success, render_output
from datamasque_cli.projects import PROJECT_OPTION_HELP, find_named_project, get_named_project, resolve_project

app = typer.Typer(help="Manage projects.", no_args_is_help=True)

DELETE_CONFLICT_MESSAGE = "The project's resources cannot move to the destination project"


def _build_project_row(project: Project) -> dict[str, object]:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created": project.created,
    }


def _find_project_for_get(client: DataMasqueClient, name_or_id: str) -> tuple[Project, bool]:
    """
    Return the project `name_or_id` names, and whether it is deleted.

    A name resolves among the active projects only, because a deleted project can share an active project's name.
    An id that no active project has also finds a deleted project, as `list --include-deleted` shows it.
    """
    active = client.list_projects()
    found = find_named_project(active, name_or_id)
    if found is not None:
        return found, False

    deleted = next(
        (project for project in client.list_projects(include_archived=True) if str(project.id) == name_or_id), None
    )
    if deleted is None:
        abort(f"Project '{name_or_id}' not found.", code=ErrorCode.NOT_FOUND)
    return deleted, True


@app.command("list")
def list_projects(
    is_deleted_included: bool = typer.Option(False, "--include-deleted", help="Also list deleted projects"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List the active projects, or every project with --include-deleted."""
    client = get_client(profile)
    columns = ["id", "name", "description", "created"]
    if not is_deleted_included:
        data = [_build_project_row(project) for project in client.list_projects()]
        render_output(data, is_json=is_json, columns=columns, title="Projects")
        return

    active_ids = {project.id for project in client.list_projects()}
    data = [
        {**_build_project_row(project), "deleted": project.id not in active_ids}
        for project in client.list_projects(include_archived=True)
    ]
    render_output(data, is_json=is_json, columns=[*columns, "deleted"], title="Projects")


@app.command("get")
def get_project(
    project: str = typer.Argument(help=PROJECT_OPTION_HELP),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show a project's details, or a deleted project's by its id."""
    client = get_client(profile)
    found, is_deleted = _find_project_for_get(client, project)
    data = {**_build_project_row(found), "updated": found.updated, "deleted": is_deleted}
    render_output(data, is_json=is_json, title=f"Project: {found.name}")


@app.command("create")
def create_project(
    name: str = typer.Option(..., help="Project name"),
    description: str = typer.Option("", help="Project description"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create a project."""
    client = get_client(profile)
    try:
        created = client.create_project(ProjectCreateRequest(name=name, description=description))
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to create project '{name}'", exc)
    print_success(f"Project '{created.name}' created (id {created.id}).")


@app.command("update")
def update_project(
    project: str = typer.Argument(help=PROJECT_OPTION_HELP),
    new_name: str | None = typer.Option(None, "--name", help="New project name"),
    description: str | None = typer.Option(None, help="New project description"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """
    Rename a project or change its description.

    Renaming moves the project's seed and credential files.
    Rulesets and configurations that import one of its libraries by the old project name become invalid,
    and seed and table references that name the old project are not changed.
    """
    if new_name is None and description is None:
        abort("Nothing to update.", code=ErrorCode.INVALID_INPUT, hint="Pass --name, --description or both.")

    client = get_client(profile)
    found = resolve_project(client, project)
    try:
        updated = client.update_project(found, ProjectUpdateRequest(name=new_name, description=description))
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to update project '{found.name}'", exc)
    print_success(f"Project '{updated.name}' updated.")


@app.command("delete")
def delete_project(
    project: str = typer.Argument(help=PROJECT_OPTION_HELP),
    destination: str = typer.Option(..., "--to", help="Project to move the resources to: name or id"),
    is_check_only: bool = typer.Option(False, "--check", help="Only list what would stop the delete"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a project, after moving all of its resources to another project."""
    client = get_client(profile)
    projects = client.list_projects()
    found = get_named_project(projects, project)
    target = get_named_project(projects, destination)

    if is_check_only:
        try:
            conflicts = client.get_project_delete_conflicts(found, target)
        except DataMasqueApiError as exc:
            abort_api_error(f"Failed to check project '{found.name}'", exc)
        if conflicts:
            abort(DELETE_CONFLICT_MESSAGE, code=ErrorCode.CONFLICT, details=[c.detail for c in conflicts])
        print_success(f"Project '{found.name}' can be deleted, moving its resources to '{target.name}'.")
        return

    if not is_confirmed:
        confirm_or_abort(f"Delete project '{found.name}' and move its resources to '{target.name}'?")

    try:
        client.delete_project(found, target)
    except ProjectDeleteConflictError as exc:
        abort(DELETE_CONFLICT_MESSAGE, code=ErrorCode.CONFLICT, details=[c.detail for c in exc.conflicts])
    except DataMasqueApiError as exc:
        abort_api_error(f"Failed to delete project '{found.name}'", exc)
    print_success(f"Project '{found.name}' deleted; its resources moved to '{target.name}'.")
