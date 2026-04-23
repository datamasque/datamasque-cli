from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.users"


@patch(f"{MODULE}.get_client")
def test_delete_user_proceeds_when_present(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_users.return_value = [SimpleNamespace(username="alice"), SimpleNamespace(username="bob")]

    result = runner.invoke(app, ["users", "delete", "alice", "--yes"])

    assert result.exit_code == 0
    client.delete_user_by_username_if_exists.assert_called_once_with("alice")


@patch(f"{MODULE}.get_client")
def test_delete_user_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_users.return_value = [SimpleNamespace(username="alice")]

    result = runner.invoke(app, ["users", "delete", "nope", "--yes"])

    assert result.exit_code != 0
    client.delete_user_by_username_if_exists.assert_not_called()
