from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from datamasque_cli.config import Config, Profile
from datamasque_cli.main import app
from tests.conftest import make_config

MODULE = "datamasque_cli.commands.auth"


# -- login -----------------------------------------------------------------


@patch(f"{MODULE}.get_client")
@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config", return_value=Config())
def test_login_saves_credentials_from_prompts(
    _mock_load: MagicMock, mock_save: MagicMock, _mock_client: MagicMock, runner: CliRunner
) -> None:
    runner.invoke(app, ["auth", "login"], input="https://dm.example.com/\nadmin\nsecret\n")

    profile = mock_save.call_args[0][0].get_profile("default")
    assert profile.url == "https://dm.example.com"
    assert profile.username == "admin"
    assert profile.password == "secret"


@patch(f"{MODULE}.get_client", side_effect=SystemExit(1))
@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config", return_value=Config())
def test_login_saves_even_when_connection_fails(
    _mock_load: MagicMock, mock_save: MagicMock, _mock_client: MagicMock, runner: CliRunner
) -> None:
    runner.invoke(app, ["auth", "login"], input="https://bad.host\nadmin\nsecret\n")
    mock_save.assert_called_once()


@patch(f"{MODULE}.get_client")
@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config", return_value=Config())
def test_login_strips_trailing_slash(
    _mock_load: MagicMock, mock_save: MagicMock, _mock_client: MagicMock, runner: CliRunner
) -> None:
    runner.invoke(app, ["auth", "login"], input="https://dm.example.com///\nadmin\nsecret\n")
    assert mock_save.call_args[0][0].get_profile("default").url == "https://dm.example.com"


@patch(f"{MODULE}.get_client")
@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config", return_value=Config())
def test_login_writes_to_named_profile(
    _mock_load: MagicMock, mock_save: MagicMock, _mock_client: MagicMock, runner: CliRunner
) -> None:
    runner.invoke(app, ["auth", "login", "--profile", "staging"], input="https://dm.example.com\nadmin\nsecret\n")
    saved_config = mock_save.call_args[0][0]
    assert saved_config.active_profile == "staging"
    assert saved_config.get_profile("staging").username == "admin"


@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config", return_value=Config())
def test_login_rejects_url_without_scheme(_mock_load: MagicMock, mock_save: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["auth", "login"], input="localhost\n")

    assert result.exit_code != 0
    assert "http://" in result.stderr
    mock_save.assert_not_called()


def test_login_rejects_url_flag(runner: CliRunner) -> None:
    result = runner.invoke(app, ["auth", "login", "--url", "https://x"])
    assert result.exit_code != 0
    assert "no such option" in result.stderr.lower()


def test_login_rejects_username_flag(runner: CliRunner) -> None:
    result = runner.invoke(app, ["auth", "login", "--username", "admin"])
    assert result.exit_code != 0
    assert "no such option" in result.stderr.lower()


def test_login_rejects_password_flag(runner: CliRunner) -> None:
    result = runner.invoke(app, ["auth", "login", "--password", "secret"])
    assert result.exit_code != 0
    assert "no such option" in result.stderr.lower()


# -- logout ----------------------------------------------------------------


@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config")
def test_logout_falls_back_to_remaining_profile(mock_load: MagicMock, mock_save: MagicMock, runner: CliRunner) -> None:
    config = make_config("prod")
    config.set_profile("staging", Profile(url="https://staging", username="u", password="p"))
    mock_load.return_value = config

    runner.invoke(app, ["auth", "logout", "--profile", "prod"])
    assert mock_save.call_args[0][0].active_profile == "staging"


@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config", return_value=Config())
def test_logout_nonexistent_profile_aborts(_mock_load: MagicMock, _mock_save: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["auth", "logout", "--profile", "nope"])
    assert result.exit_code != 0


# -- use -------------------------------------------------------------------


@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config")
def test_use_profile_switches_active(mock_load: MagicMock, mock_save: MagicMock, runner: CliRunner) -> None:
    config = make_config()
    config.set_profile("prod", Profile(url="https://prod", username="u", password="p"))
    mock_load.return_value = config

    runner.invoke(app, ["auth", "use", "prod"])
    assert mock_save.call_args[0][0].active_profile == "prod"


@patch(f"{MODULE}.save_config")
@patch(f"{MODULE}.load_config", return_value=Config())
def test_use_profile_nonexistent_aborts(_mock_load: MagicMock, _mock_save: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["auth", "use", "nonexistent"])
    assert result.exit_code != 0
