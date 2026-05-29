from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.license import LicenseInfo, SwitchableLicenseMetadata
from typer.testing import CliRunner

from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.system"


@patch(f"{MODULE}.get_client")
def test_licence_projects_to_user_facing_fields(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.get_current_license_info.return_value = LicenseInfo(
        uuid="lic-123",
        name="Test Licence",
        type="standard",
        is_expired=False,
        uploadable=True,
        expiry_date=datetime(2027, 6, 1, tzinfo=UTC),
        days_until_expiry=400,
        platform_name="DataMasque",
        # Noisy nested field that should NOT appear in the projected output.
        switchable_license_metadata=SwitchableLicenseMetadata(license_source="aws"),
    )

    result = runner.invoke(app, ["system", "licence", "--json"])

    assert result.exit_code == 0
    assert '"uuid": "lic-123"' in result.stdout
    assert '"days_until_expiry": 400' in result.stdout
    assert '"platform_name": "DataMasque"' in result.stdout
    assert "switchable_license_metadata" not in result.stdout
    assert "license_source" not in result.stdout


@pytest.mark.parametrize(
    ("extra_args", "settings_url", "expected_output"),
    [
        (["--json"], "http://engine.example.com:9021", '"dm_ai_engine_url": "http://engine.example.com:9021"'),
        ([], "http://engine.example.com:9021", "http://engine.example.com:9021"),
        ([], None, "<not configured>"),
        ([], "", "<not configured>"),
    ],
)
@patch(f"{MODULE}.get_client")
def test_ai_engine_show(
    mock_get_client: MagicMock,
    runner: CliRunner,
    extra_args: list[str],
    settings_url: str | None,
    expected_output: str,
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    response = MagicMock()
    response.json.return_value = {"dm_ai_engine_url": settings_url}
    client.make_request.return_value = response

    result = runner.invoke(app, ["system", "ai-engine", "show", *extra_args])

    assert result.exit_code == 0
    client.make_request.assert_called_once_with("GET", "/api/settings/")
    assert expected_output in result.stdout


@patch(f"{MODULE}.get_client")
def test_ai_engine_set_patches_settings_with_url(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    result = runner.invoke(app, ["system", "ai-engine", "set", "http://engine.example.com:9021"])

    assert result.exit_code == 0
    client.make_request.assert_called_once_with(
        "PATCH", "/api/settings/", data={"dm_ai_engine_url": "http://engine.example.com:9021"}
    )


# Commands that hit anonymous endpoints must use `get_unauthenticated_client`, not `get_client`.
# Using `get_client` would call `authenticate()` first, which always fails on a fresh server
# (no admin user yet → 401 → SystemExit) and never reaches the actual endpoint.


@patch(f"{MODULE}.get_unauthenticated_client")
@patch(f"{MODULE}.get_client")
def test_admin_install_uses_unauthenticated_client(
    mock_get_client: MagicMock, mock_get_unauth: MagicMock, runner: CliRunner
) -> None:
    client = MagicMock()
    mock_get_unauth.return_value = client

    result = runner.invoke(
        app,
        [
            "system",
            "admin-install",
            "--email",
            "admin@example.com",
            "--username",
            "admin",
            "--password",
            "P@ssword12",
        ],
    )

    assert result.exit_code == 0, result.output
    mock_get_unauth.assert_called_once()
    mock_get_client.assert_not_called()
    client.admin_install.assert_called_once_with(email="admin@example.com", username="admin", password="P@ssword12")


@patch(f"{MODULE}.get_unauthenticated_client")
def test_admin_install_translates_401_into_conflict(mock_get_unauth: MagicMock, runner: CliRunner) -> None:
    """A 401 from /api/users/admin-install/ means the instance is already set up.

    Translate the raw API error into a user-facing conflict message instead of
    letting the misleading "Unable to login" traceback bubble up.
    """
    client = MagicMock()
    mock_get_unauth.return_value = client
    response = MagicMock()
    response.status_code = 401
    client.admin_install.side_effect = DataMasqueApiError("401 Unauthorized", response=response)

    result = runner.invoke(
        app,
        [
            "system",
            "admin-install",
            "--email",
            "admin@example.com",
            "--username",
            "admin",
            "--password",
            "P@ssword12",
        ],
    )

    assert result.exit_code == 8  # ErrorCode.CONFLICT
    assert "already complete" in result.stderr
    assert "dm auth login" in result.stderr


@patch(f"{MODULE}.get_unauthenticated_client")
def test_admin_install_does_not_swallow_non_401_errors(mock_get_unauth: MagicMock, runner: CliRunner) -> None:
    """Only 401 is the "already installed" signal -- other errors must surface."""
    client = MagicMock()
    mock_get_unauth.return_value = client
    response = MagicMock()
    response.status_code = 400
    client.admin_install.side_effect = DataMasqueApiError("400 Bad Request", response=response)

    result = runner.invoke(
        app,
        [
            "system",
            "admin-install",
            "--email",
            "admin@example.com",
            "--username",
            "admin",
            "--password",
            "weak",
        ],
    )

    assert result.exit_code != 0
    assert "already complete" not in result.stderr


@patch(f"{MODULE}.get_unauthenticated_client")
@patch(f"{MODULE}.get_client")
def test_health_uses_unauthenticated_client(
    mock_get_client: MagicMock, mock_get_unauth: MagicMock, runner: CliRunner
) -> None:
    client = MagicMock()
    mock_get_unauth.return_value = client

    result = runner.invoke(app, ["system", "health", "--json"])

    assert result.exit_code == 0, result.output
    mock_get_unauth.assert_called_once()
    mock_get_client.assert_not_called()
    client.healthcheck.assert_called_once_with()
    assert '"status": "healthy"' in result.stdout
