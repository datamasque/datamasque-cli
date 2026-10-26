"""Resolve `--project` and name each resource's project in output."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol, TypeVar

from datamasque.client import DataMasqueClient
from datamasque.client.models.project import Project

from datamasque_cli.errors import ErrorCode, abort

PROJECT_OPTION_HELP = "Project name or id"


class ProjectScoped(Protocol):
    """A resource that records its project as an `<id>-<slug>` reference."""

    @property
    def project(self) -> str | None: ...


ScopedT = TypeVar("ScopedT", bound=ProjectScoped)


def resolve_project(client: DataMasqueClient, name_or_id: str) -> Project:
    """Return the active project named `name_or_id`, ignoring case, or with that numeric id."""
    projects = client.list_projects()
    match = next((p for p in projects if p.name.casefold() == name_or_id.casefold()), None)
    if match is None and name_or_id.isdigit():
        match = next((p for p in projects if p.id == int(name_or_id)), None)
    if match is None:
        abort(f"Project '{name_or_id}' not found.", code=ErrorCode.NOT_FOUND)
    return match


def resolve_optional_project(client: DataMasqueClient, name_or_id: str | None) -> Project | None:
    """Return the project `name_or_id` names, or `None` when no `--project` was given."""
    return None if name_or_id is None else resolve_project(client, name_or_id)


def resolve_target_project(client: DataMasqueClient, name_or_id: str | None) -> Project:
    """
    Return the project to put a new resource in: the one `--project` names, else the only active project.

    Aborts when no `--project` was given and the instance has more than one active project,
    as the server does for a create that names no project.
    """
    if name_or_id is not None:
        return resolve_project(client, name_or_id)
    projects = client.list_projects()
    if len(projects) == 1:
        return projects[0]
    abort(
        f"The instance has {len(projects)} active projects.",
        code=ErrorCode.AMBIGUOUS,
        hint="Pass --project to choose one.",
    )


def resolve_create_project(client: DataMasqueClient, name_or_id: str | None, existing: Sequence[ProjectScoped]) -> str:
    """
    Return the `<id>-<slug>` reference of the project a create-or-update writes to.

    That is the project `--project` names; else the one project that already has a resource of that name, so an
    update needs no `--project`; else the instance's only active project.
    """
    references = {item.project for item in existing}
    if name_or_id is None and len(references) == 1:
        (reference,) = references
        if reference is not None:
            return reference
    target: str = resolve_target_project(client, name_or_id).reference
    return target


def project_names(client: DataMasqueClient) -> dict[str, str]:
    """Map each project's `<id>-<slug>` reference to its name, archived projects included."""
    return {p.reference: p.name for p in client.list_projects(include_archived=True)}


def project_label(names: dict[str, str], reference: str | None) -> str:
    """Name the project `reference` points at, or "" for a resource in no project, such as a built-in seed."""
    if reference is None:
        return ""
    return names.get(reference, reference)


def in_project(items: Sequence[ScopedT], project: Project | None) -> list[ScopedT]:
    """Keep the items in `project`, or all of them when `project` is `None`."""
    if project is None:
        return list(items)
    return [item for item in items if item.project == project.reference]


def require_single_or_abort(
    client: DataMasqueClient,
    matches: Sequence[ScopedT],
    label: str,
    *,
    describe: Callable[[ScopedT], str] | None = None,
    hint: str = "Pass --project to disambiguate.",
) -> ScopedT:
    """
    Return the one resource in `matches`, or abort when there is none or several.

    Several matches means the name exists in more than one project, so the hint asks for `--project`.
    `describe` adds a per-match detail, such as the id, to the list the error shows.
    """
    if not matches:
        abort(f"{label} not found.", code=ErrorCode.NOT_FOUND)
    if len(matches) > 1:
        names = project_names(client)
        options = "\n  ".join(
            f"project={project_label(names, item.project)}" + (f" {describe(item)}" if describe else "")
            for item in matches
        )
        abort(
            f"{label} exists in more than one project:\n  {options}",
            code=ErrorCode.AMBIGUOUS,
            hint=hint,
        )
    return matches[0]
