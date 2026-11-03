from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.models.resource import (
    Resource,
    ResourceMoveConflict,
    ResourceMoveConflictReason,
    ResourceMoveResult,
)
from datamasque.client.models.resource_type import ResourceTypeName
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.conftest import make_project, with_projects

MODULE = "datamasque_cli.commands.resources"

DEFAULT = make_project(1, "Default")
FINANCE = make_project(2, "Finance")

CUSTOMERS = Resource(id="r1", name="customers", project=FINANCE.reference)
ORDERS = Resource(id="r2", name="orders", project=FINANCE.reference)
ALREADY_THERE = Resource(id="r3", name="customers", project=DEFAULT.reference)
BUILT_IN_SEED = Resource(id="s1", name="first_names.csv", project=None)

CUSTOMERS_CLASH = ResourceMoveConflict(
    reason=ResourceMoveConflictReason.name_in_use,
    detail='Ruleset "customers" exists.',
    type=ResourceTypeName.rulesets,
    id="r1",
    name="customers",
)


@pytest.fixture()
def client() -> Iterator[MagicMock]:
    client = with_projects(MagicMock(), DEFAULT, FINANCE)
    client.list_resources.return_value = {
        ResourceTypeName.rulesets: [CUSTOMERS, ORDERS, ALREADY_THERE],
        ResourceTypeName.seeds: [BUILT_IN_SEED],
    }
    client.move_resources.return_value = ResourceMoveResult(moved=2, conflicts=[])
    with patch(f"{MODULE}.get_client", return_value=client):
        yield client


def test_move_project_sends_its_resources_and_filters(client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "resources",
            "move",
            "--project",
            "finance",
            "--type",
            "rulesets",
            "--search",
            "cust",
            "--to",
            "default",
            "-y",
        ],
    )

    assert result.exit_code == 0
    client.list_projects.assert_called_once_with()
    client.list_resources.assert_called_once_with(projects=[FINANCE], types=[ResourceTypeName.rulesets], search="cust")
    client.move_resources.assert_called_once_with({ResourceTypeName.rulesets: [CUSTOMERS, ORDERS]}, DEFAULT)


def test_move_names_select_exact_names_only(client: MagicMock, runner: CliRunner) -> None:
    client.list_resources.return_value = {
        ResourceTypeName.rulesets: [CUSTOMERS, Resource(id="r4", name="customers_v2", project=FINANCE.reference)],
    }

    result = runner.invoke(app, ["resources", "move", "customers", "--to", "default", "-y"])

    assert result.exit_code == 0
    client.move_resources.assert_called_once_with({ResourceTypeName.rulesets: [CUSTOMERS]}, DEFAULT)


def test_move_without_any_selection_is_rejected_without_a_request(client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["resources", "move", "--to", "default", "-y"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert result.stderr == (
        "Error: Select the resources to move.\nHint: Pass resource names, --project, --type or --search.\n"
    )
    client.list_resources.assert_not_called()


def test_move_with_nothing_outside_the_destination_is_not_found(client: MagicMock, runner: CliRunner) -> None:
    client.list_resources.return_value = {
        ResourceTypeName.rulesets: [ALREADY_THERE],
        ResourceTypeName.seeds: [BUILT_IN_SEED],
    }

    result = runner.invoke(app, ["resources", "move", "--search", "c", "--to", "default", "-y"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert result.stderr == "Error: No resources to move to 'Default'.\n"
    client.move_resources.assert_not_called()


def test_move_that_leaves_resources_behind_names_them_and_fails(client: MagicMock, runner: CliRunner) -> None:
    client.move_resources.return_value = ResourceMoveResult(moved=1, conflicts=[CUSTOMERS_CLASH])

    result = runner.invoke(app, ["resources", "move", "--project", "finance", "--to", "default", "-y"])

    assert result.exit_code == ExitCode.CONFLICT
    assert result.stderr == (
        "Error: Some resources did not move; 1 moved to 'Default':\n  Ruleset \"customers\" exists.\n"
    )


def test_move_that_moves_nothing_says_none_moved(client: MagicMock, runner: CliRunner) -> None:
    client.move_resources.return_value = ResourceMoveResult(moved=0, conflicts=[CUSTOMERS_CLASH])

    result = runner.invoke(app, ["resources", "move", "--project", "finance", "--to", "default", "-y"])

    assert result.exit_code == ExitCode.CONFLICT
    assert result.stderr == "Error: No resources moved to 'Default':\n  Ruleset \"customers\" exists.\n"


def test_move_lists_a_detail_shared_by_several_conflicts_once(client: MagicMock, runner: CliRunner) -> None:
    orders_clash = CUSTOMERS_CLASH.model_copy(update={"id": "r2", "name": "orders"})
    client.get_resource_move_conflicts.return_value = [CUSTOMERS_CLASH, orders_clash]

    result = runner.invoke(app, ["resources", "move", "--project", "finance", "--to", "default", "--check"])

    assert result.exit_code == ExitCode.CONFLICT
    assert result.stderr == 'Error: Some resources would not move:\n  Ruleset "customers" exists.\n'


def test_move_declined_at_the_prompt_moves_nothing(client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["resources", "move", "--project", "finance", "--to", "default"], input="n\n")

    assert result.exit_code == ExitCode.CANCELLED
    client.move_resources.assert_not_called()


@pytest.mark.parametrize(
    ("conflicts", "exit_code", "stderr"),
    [
        ([], 0, "All 2 resources can move to 'Default'.\n"),
        (
            [CUSTOMERS_CLASH],
            ExitCode.CONFLICT,
            'Error: Some resources would not move:\n  Ruleset "customers" exists.\n',
        ),
    ],
    ids=["no-conflicts", "conflict"],
)
def test_move_check_reports_the_conflicts_without_moving(
    client: MagicMock, runner: CliRunner, conflicts: list[ResourceMoveConflict], exit_code: int, stderr: str
) -> None:
    client.get_resource_move_conflicts.return_value = conflicts

    result = runner.invoke(app, ["resources", "move", "--project", "finance", "--to", "default", "--check"])

    assert result.exit_code == exit_code
    assert result.stderr == stderr
    client.get_resource_move_conflicts.assert_called_once_with(
        {ResourceTypeName.rulesets: [CUSTOMERS, ORDERS]}, DEFAULT
    )
    client.move_resources.assert_not_called()
