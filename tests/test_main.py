from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import (
    DataMasqueApiError,
    DataMasqueNotReadyError,
    DataMasqueTransportError,
)

from datamasque_cli.main import main
from datamasque_cli.output import ExitCode

MODULE = "datamasque_cli.main"


@patch(f"{MODULE}.app")
def test_unhandled_api_error_aborts_cleanly(mock_app: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    response = MagicMock(status_code=500)
    response.json.return_value = {"detail": "Report storage is unavailable."}
    mock_app.side_effect = DataMasqueApiError("boom", response=response)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == ExitCode.ERROR
    assert "Report storage is unavailable." in " ".join(capsys.readouterr().err.split())


@patch(f"{MODULE}.app")
def test_unhandled_api_conflict_keeps_its_code(mock_app: MagicMock) -> None:
    response = MagicMock(status_code=409)
    response.json.return_value = {"detail": "Already running."}
    mock_app.side_effect = DataMasqueApiError("boom", response=response)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == ExitCode.CONFLICT


@patch(f"{MODULE}.app")
def test_transport_error_aborts_with_transport_code(mock_app: MagicMock) -> None:
    mock_app.side_effect = DataMasqueTransportError("Connection reset by peer")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == ExitCode.TRANSPORT_ERROR


@patch(f"{MODULE}.app")
def test_other_datamasque_errors_abort_as_unclassified(mock_app: MagicMock) -> None:
    """The base-class clause catches the rest of the exception family."""
    mock_app.side_effect = DataMasqueNotReadyError("Server is starting up")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == ExitCode.ERROR


@patch(f"{MODULE}.app")
def test_exit_status_passes_through(mock_app: MagicMock) -> None:
    """Typer signals success, and `abort()` signals failure, by raising `SystemExit`.

    Both must survive the wrapper, which they do because `SystemExit` inherits
    from `BaseException` rather than `Exception`.
    """
    mock_app.side_effect = SystemExit(ExitCode.NOT_FOUND)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == ExitCode.NOT_FOUND


@patch(f"{MODULE}.app")
def test_unrelated_exceptions_are_not_swallowed(mock_app: MagicMock) -> None:
    """Only the DataMasque family is translated; a bug in our own code still raises."""
    mock_app.side_effect = ValueError("a genuine bug")

    with pytest.raises(ValueError, match="a genuine bug"):
        main()
