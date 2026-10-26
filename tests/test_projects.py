from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from datamasque.client.models.project import Project

from datamasque_cli.errors import ExitCode
from datamasque_cli.projects import (
    in_project,
    project_label,
    project_names,
    require_single_or_abort,
    resolve_create_project,
    resolve_project,
    resolve_target_project,
)
from tests.conftest import make_project, with_projects

DEFAULT = make_project(1, "Default")
FINANCE = make_project(2, "Finance")


def _client(*projects: Project) -> MagicMock:
    return with_projects(MagicMock(), *projects)


@pytest.mark.parametrize("name_or_id", ["Finance", "finance", "FINANCE", "2"])
def test_resolve_project_by_name_ignoring_case_or_by_id(name_or_id: str) -> None:
    assert resolve_project(_client(DEFAULT, FINANCE), name_or_id) == FINANCE


def test_resolve_project_prefers_a_name_over_an_equal_id() -> None:
    """A project named `1` wins over the project with id 1, as names are tried first."""
    named_one = make_project(5, "1")

    assert resolve_project(_client(DEFAULT, named_one), "1") == named_one


def test_resolve_project_unknown_is_not_found() -> None:
    with pytest.raises(SystemExit) as raised:
        resolve_project(_client(DEFAULT), "Finance")

    assert raised.value.code == ExitCode.NOT_FOUND


def test_resolve_target_project_uses_the_only_project_when_none_is_given() -> None:
    assert resolve_target_project(_client(DEFAULT), None) == DEFAULT


def test_resolve_target_project_needs_a_project_once_there_are_two() -> None:
    with pytest.raises(SystemExit) as raised:
        resolve_target_project(_client(DEFAULT, FINANCE), None)

    assert raised.value.code == ExitCode.AMBIGUOUS


def test_project_names_include_archived_projects() -> None:
    client = _client(DEFAULT, FINANCE)

    assert project_names(client) == {"1-default": "Default", "2-finance": "Finance"}
    client.list_projects.assert_called_once_with(include_archived=True)


def test_project_label_names_the_project_and_leaves_a_built_in_blank() -> None:
    names = {"2-finance": "Finance"}

    assert project_label(names, "2-finance") == "Finance"
    assert project_label(names, None) == ""


def test_in_project_keeps_only_that_projects_items() -> None:
    items = [SimpleNamespace(project="1-default"), SimpleNamespace(project="2-finance")]

    assert in_project(items, FINANCE) == [items[1]]
    assert in_project(items, None) == items


def test_require_single_returns_the_only_match() -> None:
    match = SimpleNamespace(project="1-default")

    assert require_single_or_abort(_client(DEFAULT), [match], "Ruleset 'r'") is match


def test_require_single_with_no_match_is_not_found() -> None:
    with pytest.raises(SystemExit) as raised:
        require_single_or_abort(_client(DEFAULT), [], "Ruleset 'r'")

    assert raised.value.code == ExitCode.NOT_FOUND


def test_require_single_with_a_match_in_two_projects_is_ambiguous(capsys: pytest.CaptureFixture[str]) -> None:
    matches = [SimpleNamespace(project="1-default"), SimpleNamespace(project="2-finance")]

    with pytest.raises(SystemExit) as raised:
        require_single_or_abort(_client(DEFAULT, FINANCE), matches, "Ruleset 'r'")

    assert raised.value.code == ExitCode.AMBIGUOUS
    assert capsys.readouterr().err == (
        "Error: Ruleset 'r' exists in more than one project:\n"
        "  project=Default\n"
        "  project=Finance\n"
        "Hint: Pass --project to disambiguate.\n"
    )


def test_resolve_create_project_prefers_the_named_project() -> None:
    existing = [SimpleNamespace(project="1-default")]

    assert resolve_create_project(_client(DEFAULT, FINANCE), "Finance", existing) == "2-finance"


def test_resolve_create_project_updates_where_the_name_already_is() -> None:
    """An update needs no `--project` when only one project has the name, even on a multi-project instance."""
    existing = [SimpleNamespace(project="2-finance"), SimpleNamespace(project="2-finance")]

    assert resolve_create_project(_client(DEFAULT, FINANCE), None, existing) == "2-finance"


def test_resolve_create_project_with_the_name_in_two_projects_is_ambiguous() -> None:
    existing = [SimpleNamespace(project="1-default"), SimpleNamespace(project="2-finance")]

    with pytest.raises(SystemExit) as raised:
        resolve_create_project(_client(DEFAULT, FINANCE), None, existing)

    assert raised.value.code == ExitCode.AMBIGUOUS


def test_resolve_create_project_for_a_new_name_uses_the_only_project() -> None:
    assert resolve_create_project(_client(DEFAULT), None, []) == "1-default"
