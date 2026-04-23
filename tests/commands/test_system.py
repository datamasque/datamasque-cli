from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

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
