from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import DataMasqueApiError, DataMasqueTransportError

from datamasque_cli.client import _format_transport_error, get_client
from datamasque_cli.config import Config, Profile


@patch("datamasque_cli.client.DataMasqueClient")
@patch("datamasque_cli.client.load_config")
def test_get_client_aborts_on_connection_error(
    mock_load: MagicMock, mock_client_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATAMASQUE_URL", raising=False)
    monkeypatch.delenv("DATAMASQUE_USERNAME", raising=False)
    monkeypatch.delenv("DATAMASQUE_PASSWORD", raising=False)

    config = Config()
    config.set_profile("default", Profile(url="https://dm", username="admin", password="secret"))
    mock_load.return_value = config
    mock_client_cls.return_value.authenticate.side_effect = DataMasqueTransportError()

    with pytest.raises(SystemExit):
        get_client()


@patch("datamasque_cli.client.DataMasqueClient")
@patch("datamasque_cli.client.load_config")
def test_get_client_aborts_on_auth_failure(
    mock_load: MagicMock, mock_client_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATAMASQUE_URL", raising=False)
    monkeypatch.delenv("DATAMASQUE_USERNAME", raising=False)
    monkeypatch.delenv("DATAMASQUE_PASSWORD", raising=False)

    config = Config()
    config.set_profile("default", Profile(url="https://dm", username="admin", password="secret"))
    mock_load.return_value = config
    mock_client_cls.return_value.authenticate.side_effect = DataMasqueApiError("401 Unauthorized", response=MagicMock())

    with pytest.raises(SystemExit) as exc_info:
        get_client()
    assert exc_info.value.code == 1


@pytest.mark.parametrize(
    ("error_message", "verify_ssl", "expect_hint"),
    [
        ("[SSL: CERTIFICATE_VERIFY_FAILED] hostname mismatch", True, True),
        ("certificate verify failed", True, True),
        ("SSL handshake error", True, True),
        ("[SSL: CERTIFICATE_VERIFY_FAILED]", False, False),
        ("Connection refused", True, False),
        ("Name or service not known", True, False),
    ],
)
def test_format_transport_error_ssl_hint(error_message: str, verify_ssl: bool, expect_hint: bool) -> None:
    message = _format_transport_error("https://dm", Exception(error_message), verify_ssl=verify_ssl)
    assert error_message in message
    assert ("--insecure" in message) is expect_hint
