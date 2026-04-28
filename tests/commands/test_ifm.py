from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.ifm"


def _options(enabled: bool | None = None, log_level: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(enabled=enabled, default_log_level=log_level)


def _plan(
    name: str = "p1",
    serial: int = 1,
    *,
    yaml: str | None = "tasks: []\n",
    options: SimpleNamespace | None = None,
    url: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        serial=serial,
        created_time=datetime(2026, 1, 1, tzinfo=UTC),
        modified_time=datetime(2026, 1, 2, tzinfo=UTC),
        ruleset_yaml=yaml,
        options=options or _options(enabled=True),
        url=url,
        logs=[],
    )


@patch(f"{MODULE}.get_ifm_client")
def test_list_renders_plans_as_json(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_ruleset_plans.return_value = [_plan("a", 1), _plan("b", 2)]

    result = runner.invoke(app, ["ifm", "list", "--json"])

    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert [r["name"] for r in rows] == ["a", "b"]
    assert rows[0]["serial"] == 1


@patch(f"{MODULE}.get_ifm_client")
def test_list_renders_table(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_ruleset_plans.return_value = [_plan("only-plan", 7)]

    result = runner.invoke(app, ["ifm", "list"])

    assert result.exit_code == 0
    assert "only-plan" in result.stdout


@patch(f"{MODULE}.get_ifm_client")
def test_get_yaml_prints_only_yaml(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_ruleset_plan.return_value = _plan("p1", yaml="version: '1.0'\ntasks: []\n")

    result = runner.invoke(app, ["ifm", "get", "p1", "--yaml"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "version: '1.0'\ntasks: []"
    client.get_ruleset_plan.assert_called_once_with("p1")


@patch(f"{MODULE}.get_ifm_client")
def test_get_json_dumps_plan(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_ruleset_plan.return_value = _plan("p1", options=_options(enabled=False, log_level="DEBUG"))

    result = runner.invoke(app, ["ifm", "get", "p1", "--json"])

    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["name"] == "p1"
    assert body["enabled"] is False
    assert body["default_log_level"] == "DEBUG"


@patch(f"{MODULE}.get_ifm_client")
def test_create_minimal_omits_options(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.create_ruleset_plan.return_value = _plan("smoke-abc123", url="http://ifm/ruleset-plans/smoke-abc123/")

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(app, ["ifm", "create", "--name", "smoke", "--file", str(yaml_file)])

    assert result.exit_code == 0
    (sent,), _ = client.create_ruleset_plan.call_args
    assert sent.name == "smoke"
    assert sent.ruleset_yaml == "tasks: []\n"
    assert sent.options is None


@patch(f"{MODULE}.get_ifm_client")
def test_create_with_options(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.create_ruleset_plan.return_value = _plan("smoke-abc123")

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(
        app,
        ["ifm", "create", "--name", "smoke", "--file", str(yaml_file), "--disabled", "--log-level", "DEBUG"],
    )

    assert result.exit_code == 0
    (sent,), _ = client.create_ruleset_plan.call_args
    assert sent.options is not None
    assert sent.options.enabled is False
    assert sent.options.default_log_level == "DEBUG"


@patch(f"{MODULE}.get_ifm_client")
def test_update_with_file_sends_yaml(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.patch_ruleset_plan.return_value = _plan("p1", serial=2)

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("version: '2.0'\n")

    result = runner.invoke(app, ["ifm", "update", "p1", "--file", str(yaml_file)])

    assert result.exit_code == 0
    name, sent = client.patch_ruleset_plan.call_args.args
    assert name == "p1"
    assert sent.ruleset_yaml == "version: '2.0'\n"


@patch(f"{MODULE}.get_ifm_client")
def test_update_only_options_omits_yaml(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.patch_ruleset_plan.return_value = _plan("p1", serial=3)

    result = runner.invoke(app, ["ifm", "update", "p1", "--enabled"])

    assert result.exit_code == 0
    name, sent = client.patch_ruleset_plan.call_args.args
    assert name == "p1"
    assert sent.ruleset_yaml is None
    body = sent.model_dump(exclude_none=True, mode="json")
    assert body == {"options": {"enabled": True}}


@patch(f"{MODULE}.get_ifm_client")
def test_update_aborts_when_no_fields_provided(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    result = runner.invoke(app, ["ifm", "update", "p1"])

    assert result.exit_code != 0
    client.patch_ruleset_plan.assert_not_called()


@patch(f"{MODULE}.get_ifm_client")
def test_delete_with_yes_skips_prompt(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    result = runner.invoke(app, ["ifm", "delete", "p1", "--yes"])

    assert result.exit_code == 0
    client.delete_ruleset_plan.assert_called_once_with("p1")


@patch(f"{MODULE}.get_ifm_client")
def test_delete_without_confirmation_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    result = runner.invoke(app, ["ifm", "delete", "p1"], input="n\n")

    assert result.exit_code != 0
    client.delete_ruleset_plan.assert_not_called()


@patch(f"{MODULE}.get_ifm_client")
def test_mask_success_prints_masked_data(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.mask.return_value = SimpleNamespace(
        success=True,
        data=[{"id": 1, "email": "***@***.***"}],
        logs=[],
    )

    data_file = tmp_path / "in.json"
    data_file.write_text(json.dumps([{"id": 1, "email": "a@b.com"}]))

    result = runner.invoke(app, ["ifm", "mask", "p1", "--data", str(data_file)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"id": 1, "email": "***@***.***"}]
    name, sent = client.mask.call_args.args
    assert name == "p1"
    assert sent.data == [{"id": 1, "email": "a@b.com"}]


@patch(f"{MODULE}.get_ifm_client")
def test_mask_soft_failure_exits_nonzero_and_logs(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.mask.return_value = SimpleNamespace(
        success=False,
        data=None,
        logs=[SimpleNamespace(log_level="error", timestamp="2026-04-20T12:00:00Z", message="bad input")],
    )

    data_file = tmp_path / "in.json"
    data_file.write_text("[]")

    result = runner.invoke(app, ["ifm", "mask", "p1", "--data", str(data_file)])

    assert result.exit_code == 1
    assert "Mask failed." in result.stderr
    assert "bad input" in result.stderr


@patch(f"{MODULE}.get_ifm_client")
def test_mask_rejects_non_list_input(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    data_file = tmp_path / "in.json"
    data_file.write_text(json.dumps({"not": "a list"}))

    result = runner.invoke(app, ["ifm", "mask", "p1", "--data", str(data_file)])

    assert result.exit_code != 0
    client.mask.assert_not_called()


@patch(f"{MODULE}.get_ifm_client")
def test_verify_token_lists_scopes(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.verify_token.return_value = SimpleNamespace(scopes=["ifm/mask", "ifm/rules:list"])

    result = runner.invoke(app, ["ifm", "verify-token", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"scopes": ["ifm/mask", "ifm/rules:list"]}


@patch(f"{MODULE}.get_ifm_client")
def test_verify_token_table_lists_each_scope(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.verify_token.return_value = SimpleNamespace(scopes=["ifm/mask", "ifm/rules:list"])

    result = runner.invoke(app, ["ifm", "verify-token"])

    assert result.exit_code == 0
    assert "ifm/mask" in result.stdout
    assert "ifm/rules:list" in result.stdout


@patch(f"{MODULE}.get_ifm_client")
def test_create_rejects_invalid_log_level(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(
        app,
        ["ifm", "create", "--name", "smoke", "--file", str(yaml_file), "--log-level", "TRACE"],
    )

    assert result.exit_code != 0
    client.create_ruleset_plan.assert_not_called()
