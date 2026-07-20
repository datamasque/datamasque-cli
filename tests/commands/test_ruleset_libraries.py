from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datamasque.client.models.status import ValidationStatus
from typer.testing import CliRunner

from datamasque_cli.main import app
from datamasque_cli.output import ExitCode

MODULE = "datamasque_cli.commands.ruleset_libraries"


def _validated_library(
    is_valid: ValidationStatus | None,
    validation_errors: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(id="lib-uuid", is_valid=is_valid, validation_errors=validation_errors or [])


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
    client.get_ruleset_library_by_name.return_value = SimpleNamespace(id="lib-uuid", name="my-lib", namespace="")
    client.validate_ruleset_library.return_value = _validated_library(ValidationStatus.valid)

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


@patch(f"{MODULE}.get_client")
def test_validate_library_invalid_prints_errors_and_exits_4(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_ruleset_library_by_name.return_value = SimpleNamespace(id="lib-uuid", name="my-lib", namespace="")
    client.validate_ruleset_library.return_value = _validated_library(
        ValidationStatus.invalid,
        [
            SimpleNamespace(message="unknown mask type 'from_nowhere'", line_number=3),
            SimpleNamespace(message="duplicate anchor 'email'", line_number=None),
        ],
    )

    result = runner.invoke(app, ["libraries", "validate", "my-lib"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "unknown mask type 'from_nowhere'" in result.stderr
    assert "line 3" in result.stderr
    assert "duplicate anchor 'email'" in result.stderr


@patch(f"{MODULE}.get_client")
def test_validate_library_nonterminal_status_passes_through(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_ruleset_library_by_name.return_value = SimpleNamespace(id="lib-uuid", name="my-lib", namespace="")
    client.validate_ruleset_library.return_value = _validated_library(ValidationStatus.in_progress)

    result = runner.invoke(app, ["libraries", "validate", "my-lib"])

    assert result.exit_code == 0
    assert "in_progress" in result.stderr
