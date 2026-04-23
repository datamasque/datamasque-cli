from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from datamasque_cli.client import get_client
from datamasque_cli.config import Config, Profile


@patch("datamasque_cli.client.DataMasqueClient")
@patch("datamasque_cli.client.load_config")
def test_get_client_falls_back_to_active_profile(
    mock_load: MagicMock, mock_client_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATAMASQUE_URL", raising=False)
    monkeypatch.delenv("DATAMASQUE_USERNAME", raising=False)
    monkeypatch.delenv("DATAMASQUE_PASSWORD", raising=False)

    config = Config()
    config.set_profile("default", Profile(url="https://dm", username="admin", password="secret"))
    mock_load.return_value = config

    get_client()
    mock_client_cls.return_value.authenticate.assert_called_once()


@patch("datamasque_cli.client.DataMasqueClient")
@patch("datamasque_cli.client.load_config")
def test_get_client_aborts_on_unconfigured_profile(
    mock_load: MagicMock, _mock_client_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATAMASQUE_URL", raising=False)
    monkeypatch.delenv("DATAMASQUE_USERNAME", raising=False)
    monkeypatch.delenv("DATAMASQUE_PASSWORD", raising=False)

    mock_load.return_value = Config()

    with pytest.raises(SystemExit):
        get_client()
