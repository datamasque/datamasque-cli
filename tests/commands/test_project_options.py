"""`--project` on list and create commands, and the project in their output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datamasque.client.models.discovery_config import DiscoveryConfigType
from datamasque.client.models.files import SeedFile, SnowflakeKeyFile
from datamasque.client.models.ruleset import RulesetType
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.conftest import make_api_response, make_project, with_projects

DEFAULT = make_project(1, "Default")
FINANCE = make_project(2, "Finance")


def _client() -> MagicMock:
    return with_projects(MagicMock(), DEFAULT, FINANCE)


def _ruleset(id_: int | str, name: str, project: str) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name, ruleset_type=RulesetType.database, yaml="", project=project)


@patch("datamasque_cli.commands.rulesets.get_client")
def test_rulesets_list_names_the_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [_ruleset(1, "customers", FINANCE.reference)]

    result = runner.invoke(app, ["rulesets", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"id": 1, "project": "Finance", "name": "customers", "type": "database"}]


@patch("datamasque_cli.commands.rulesets.get_client")
def test_rulesets_list_project_keeps_only_that_projects_rulesets(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "customers", DEFAULT.reference),
        _ruleset(2, "payroll", FINANCE.reference),
    ]

    result = runner.invoke(app, ["rulesets", "list", "--project", "finance", "--json"])

    assert result.exit_code == 0
    assert [row["name"] for row in json.loads(result.stdout)] == ["payroll"]


@patch("datamasque_cli.commands.rulesets.get_client")
def test_rulesets_create_sends_the_project(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = []
    ruleset_file = tmp_path / "rules.yaml"
    ruleset_file.write_text("version: '1.0'\ntasks: []\n")

    result = runner.invoke(
        app,
        [
            "rulesets",
            "create",
            "--name",
            "customers",
            "--type",
            "database",
            "-f",
            str(ruleset_file),
            "--project",
            "Finance",
        ],
    )

    assert result.exit_code == 0
    assert client.create_or_update_ruleset.call_args.args[0].project == FINANCE.reference


@patch("datamasque_cli.commands.rulesets.get_client")
def test_rulesets_create_updates_where_the_name_already_is(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [_ruleset(1, "customers", FINANCE.reference)]
    ruleset_file = tmp_path / "rules.yaml"
    ruleset_file.write_text("version: '1.0'\ntasks: []\n")

    result = runner.invoke(app, ["rulesets", "create", "--name", "customers", "-f", str(ruleset_file)])

    assert result.exit_code == 0
    assert client.create_or_update_ruleset.call_args.args[0].project == FINANCE.reference


@patch("datamasque_cli.commands.rulesets.get_client")
def test_rulesets_create_new_name_needs_a_project_once_there_are_two(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = []
    ruleset_file = tmp_path / "rules.yaml"
    ruleset_file.write_text("version: '1.0'\ntasks: []\n")

    result = runner.invoke(
        app, ["rulesets", "create", "--name", "customers", "--type", "database", "-f", str(ruleset_file)]
    )

    assert result.exit_code == ExitCode.AMBIGUOUS
    assert result.stderr == "Error: The instance has 2 active projects.\nHint: Pass --project to choose one.\n"
    client.create_or_update_ruleset.assert_not_called()


@patch("datamasque_cli.commands.rulesets.get_client")
def test_rulesets_get_name_in_two_projects_asks_for_the_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "customers", DEFAULT.reference),
        _ruleset(2, "customers", FINANCE.reference),
    ]

    result = runner.invoke(app, ["rulesets", "get", "customers"])

    assert result.exit_code == ExitCode.AMBIGUOUS
    assert result.stderr == (
        "Error: Multiple rulesets named 'customers':\n"
        "  id=1 type=database project=Default\n"
        "  id=2 type=database project=Finance\n"
        "Hint: Pass --type database|file or --project to disambiguate.\n"
    )


@patch("datamasque_cli.commands.rulesets.get_client")
def test_rulesets_get_project_picks_between_same_named_rulesets(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset("rs-1", "customers", DEFAULT.reference),
        _ruleset("rs-2", "customers", FINANCE.reference),
    ]
    client.make_request.return_value = make_api_response(
        {"id": "rs-2", "name": "customers", "mask_type": "database", "config_yaml": "x", "project": FINANCE.reference}
    )

    result = runner.invoke(app, ["rulesets", "get", "customers", "--project", "Finance", "--json"])

    assert result.exit_code == 0
    client.make_request.assert_called_once_with("GET", "/api/rulesets/rs-2/")
    assert json.loads(result.stdout)["project"] == "Finance"


@patch("datamasque_cli.commands.connections.get_client")
def test_connections_create_sends_the_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _client()
    mock_get_client.return_value = client

    result = runner.invoke(
        app,
        [
            "connections",
            "create",
            "--name",
            "share",
            "--type",
            "mounted_share",
            "--base-dir",
            "in",
            "--source",
            "--project",
            "Finance",
        ],
    )

    assert result.exit_code == 0
    assert client.create_or_update_connection.call_args.args[0].project == FINANCE.reference


@patch("datamasque_cli.commands.connections.get_client")
def test_connections_list_names_the_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [
        SimpleNamespace(id=1, name="db", project=FINANCE.reference, is_file_mask_source=False)
    ]

    result = runner.invoke(app, ["connections", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)[0]["project"] == "Finance"


@patch("datamasque_cli.commands.seeds.get_client")
def test_seeds_upload_needs_a_project_once_there_are_two(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = _client()
    mock_get_client.return_value = client
    seed = tmp_path / "names.csv"
    seed.write_text("name\nann\n")

    result = runner.invoke(app, ["seeds", "upload", str(seed)])

    assert result.exit_code == ExitCode.AMBIGUOUS
    assert result.stderr == "Error: The instance has 2 active projects.\nHint: Pass --project to choose one.\n"
    client.upload_file.assert_not_called()


@patch("datamasque_cli.commands.seeds.get_client")
def test_seeds_upload_goes_to_the_named_project(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = _client()
    mock_get_client.return_value = client
    seed = tmp_path / "names.csv"
    seed.write_text("name\nann\n")

    result = runner.invoke(app, ["seeds", "upload", str(seed), "--project", "Finance"])

    assert result.exit_code == 0
    client.upload_file.assert_called_once_with(SeedFile, "names.csv", seed, project=FINANCE.id)


@patch("datamasque_cli.commands.seeds.get_client")
def test_seeds_list_project_asks_the_server_and_names_built_ins_blank(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = _client()
    mock_get_client.return_value = client
    stamp = datetime.now(tz=UTC)
    client.list_files_of_type.return_value = [
        SeedFile(id="a", name="names.csv", created_date=stamp, project=FINANCE.reference),
        SeedFile(id="b", name="DataMasque_first_names.csv", created_date=stamp, project=None),
    ]

    result = runner.invoke(app, ["seeds", "list", "--project", "Finance", "--json"])

    assert result.exit_code == 0
    client.list_files_of_type.assert_called_once_with(SeedFile, project=FINANCE.id)
    assert [row["project"] for row in json.loads(result.stdout)] == ["Finance", ""]


@patch("datamasque_cli.commands.runs.get_client")
def test_runs_list_project_is_filtered_on_the_server(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.make_request.return_value = make_api_response(
        {"results": [{"id": 7, "run_status": "finished", "project": FINANCE.reference}]}
    )

    result = runner.invoke(app, ["run", "list", "--project", "Finance", "--json"])

    assert result.exit_code == 0
    query = client.make_request.call_args.args[1]
    assert "project=2" in query
    assert json.loads(result.stdout)[0]["project"] == "Finance"


@patch("datamasque_cli.commands.table_references.get_client")
def test_table_references_create_sends_the_project(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_table_references.return_value = []
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input", project=FINANCE.reference)]

    result = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            "ids",
            "--connection",
            "input",
            "--source",
            "a.csv",
            "--project",
            "Finance",
        ],
    )

    assert result.exit_code == 0
    assert client.create_or_update_table_reference.call_args.args[0].project == FINANCE.reference


@patch("datamasque_cli.commands.connections.get_client")
def test_connections_list_project_keeps_only_that_projects_connections(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [
        SimpleNamespace(id=1, name="db", project=DEFAULT.reference, is_file_mask_source=False),
        SimpleNamespace(id=2, name="warehouse", project=FINANCE.reference, is_file_mask_source=False),
    ]

    result = runner.invoke(app, ["connections", "list", "--project", "Finance", "--json"])

    assert result.exit_code == 0
    assert [row["name"] for row in json.loads(result.stdout)] == ["warehouse"]


def _discovery_config(id_: str, name: str, project: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, name=name, config_type=DiscoveryConfigType.database, is_valid=None, yaml="", project=project
    )


@patch("datamasque_cli.commands.discovery_configs.get_client")
def test_discovery_configs_list_names_the_project_and_keeps_only_that_projects_configs(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = [
        _discovery_config("c-1", "pii", DEFAULT.reference),
        _discovery_config("c-2", "payroll", FINANCE.reference),
    ]

    result = runner.invoke(app, ["discover", "configs", "list", "--project", "Finance", "--json"])

    assert result.exit_code == 0
    assert [(row["name"], row["project"]) for row in json.loads(result.stdout)] == [("payroll", "Finance")]


@patch("datamasque_cli.commands.discovery_configs.get_client")
def test_discovery_configs_create_sends_the_project(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_discovery_configs.return_value = []
    config_file = tmp_path / "config.yaml"
    config_file.write_text("labels: []\n")

    result = runner.invoke(
        app,
        [
            "discover",
            "configs",
            "create",
            "--name",
            "payroll",
            "--type",
            "database",
            "-f",
            str(config_file),
            "--project",
            "Finance",
        ],
    )

    assert result.exit_code == 0
    assert client.create_or_update_discovery_config.call_args.args[0].project == FINANCE.reference


@patch("datamasque_cli.commands.files.get_client")
def test_files_list_project_asks_the_server_and_names_the_project(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = _client()
    mock_get_client.return_value = client
    stamp = datetime.now(tz=UTC)
    client.list_files_of_type.return_value = [
        SnowflakeKeyFile(id="k", name="key.p8", created_date=stamp, project=FINANCE.reference)
    ]

    result = runner.invoke(app, ["files", "list", "snowflake-key", "--project", "Finance", "--json"])

    assert result.exit_code == 0
    client.list_files_of_type.assert_called_once_with(SnowflakeKeyFile, project=FINANCE.id)
    assert json.loads(result.stdout) == [{"id": "k", "project": "Finance", "name": "key.p8"}]


@patch("datamasque_cli.commands.files.get_client")
def test_files_upload_goes_to_the_named_project(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = _client()
    mock_get_client.return_value = client
    key = tmp_path / "key.p8"
    key.write_text("-----BEGIN PRIVATE KEY-----\n")

    result = runner.invoke(
        app, ["files", "upload", "snowflake-key", "-f", str(key), "--name", "key.p8", "--project", "Finance"]
    )

    assert result.exit_code == 0
    client.upload_file.assert_called_once_with(SnowflakeKeyFile, "key.p8", key, project=FINANCE.id)


@patch("datamasque_cli.commands.table_references.get_client")
def test_table_references_list_project_keeps_only_that_projects_references(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = _client()
    mock_get_client.return_value = client
    client.list_table_references.return_value = [
        SimpleNamespace(id="t-1", name="ids", connection_id="c", source="a.csv", project=DEFAULT.reference),
        SimpleNamespace(id="t-2", name="codes", connection_id="c", source="b.csv", project=FINANCE.reference),
    ]

    result = runner.invoke(app, ["table-references", "list", "--project", "Finance", "--json"])

    assert result.exit_code == 0
    assert [(row["name"], row["project"]) for row in json.loads(result.stdout)] == [("codes", "Finance")]
