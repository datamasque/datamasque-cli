from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.ruleset_libraries"


@patch(f"{MODULE}.get_client")
def test_delete_library_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_ruleset_library_by_name.return_value = None

    result = runner.invoke(app, ["libraries", "delete", "nope", "--yes"])

    assert result.exit_code != 0
    client.delete_ruleset_library_by_name_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_library_proceeds_when_present(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_ruleset_library_by_name.return_value = SimpleNamespace(id=1, name="lib", namespace="")

    result = runner.invoke(app, ["libraries", "delete", "lib", "--yes"])

    assert result.exit_code == 0
    client.delete_ruleset_library_by_name_if_exists.assert_called_once_with("lib", "", force=False)


@patch(f"{MODULE}.get_client")
def test_validate_library_reports_status(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    original = MagicMock()
    original.id = "lib-uuid"
    client.get_ruleset_library_by_name.return_value = original

    validated = MagicMock()
    validated.is_valid = MagicMock(value="valid")
    client.validate_ruleset_library.return_value = validated

    result = runner.invoke(app, ["libraries", "validate", "my-lib"])

    assert result.exit_code == 0
    client.validate_ruleset_library.assert_called_once_with("lib-uuid")
    assert "valid" in result.stderr


@patch(f"{MODULE}.get_client")
def test_validate_library_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_ruleset_library_by_name.return_value = None

    result = runner.invoke(app, ["libraries", "validate", "missing"])

    assert result.exit_code != 0
    client.validate_ruleset_library.assert_not_called()
