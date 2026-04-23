from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from datamasque.client.models.files import SnowflakeKeyFile
from typer.testing import CliRunner

from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.files"


@patch(f"{MODULE}.get_client")
def test_delete_file_proceeds_when_present(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    match = SnowflakeKeyFile(id="abc", name="mykey", created_date=datetime.now(tz=UTC))
    client.get_file_of_type_by_name.return_value = match

    result = runner.invoke(app, ["files", "delete", "snowflake-key", "mykey", "--yes"])

    assert result.exit_code == 0
    client.delete_file_if_exists.assert_called_once_with(match)


@patch(f"{MODULE}.get_client")
def test_delete_file_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_file_of_type_by_name.return_value = None

    result = runner.invoke(app, ["files", "delete", "snowflake-key", "nope", "--yes"])

    assert result.exit_code != 0
    client.delete_file_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_file_rejects_unknown_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["files", "delete", "not-a-type", "x", "--yes"])
    assert result.exit_code != 0
