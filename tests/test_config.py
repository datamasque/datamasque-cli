from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from datamasque_cli.config import Config, Profile, load_config, save_config


def test_profile_is_configured_when_all_fields_set() -> None:
    profile = Profile(url="https://dm", username="admin", password="secret")
    assert profile.is_configured is True


@pytest.mark.parametrize(
    "url,username,password",
    [
        ("", "admin", "secret"),
        ("https://dm", "", "secret"),
        ("https://dm", "admin", ""),
    ],
)
def test_profile_is_not_configured_with_missing_field(url: str, username: str, password: str) -> None:
    profile = Profile(url=url, username=username, password=password)
    assert profile.is_configured is False


def test_get_profile_returns_default_without_mutating_state() -> None:
    config = Config()
    profile = config.get_profile("new_profile")
    assert profile.is_configured is False
    assert "new_profile" not in config.profiles


def test_get_profile_uses_active_when_none() -> None:
    config = Config()
    config.active_profile = "prod"
    config.set_profile("prod", Profile(url="https://prod", username="u", password="p"))

    profile = config.get_profile(None)
    assert profile.url == "https://prod"


def test_delete_profile_removes_existing() -> None:
    config = Config()
    config.set_profile("test", Profile(url="https://test", username="u", password="p"))
    assert "test" in config.list_profile_names()

    assert config.delete_profile("test") is True
    assert "test" not in config.list_profile_names()


def test_delete_profile_nonexistent_returns_false() -> None:
    config = Config()
    assert config.delete_profile("nope") is False


def test_save_config_load_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / ".config" / "datamasque-cli"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr("datamasque_cli.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("datamasque_cli.config.CONFIG_FILE", config_file)

    config = Config()
    config.active_profile = "prod"
    config.set_profile("prod", Profile(url="https://prod", username="admin", password="s3cret"))

    save_config(config)

    assert config_file.exists()
    assert config_file.stat().st_mode & 0o777 == 0o600

    loaded = load_config()
    assert loaded.active_profile == "prod"
    assert loaded.profiles["prod"].url == "https://prod"
    assert loaded.profiles["prod"].username == "admin"
    assert loaded.profiles["prod"].password == "s3cret"


def test_load_config_returns_empty_when_file_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("datamasque_cli.config.CONFIG_FILE", tmp_path / "nonexistent.toml")
    config = load_config()
    assert config.active_profile == "default"
    assert config.profiles == {}


def test_load_config_ignores_unknown_profile_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-pydantic configs on disk may contain fields we no longer support (e.g. `verify_ssl`)."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
active_profile = "default"

[profiles.default]
url = "https://dm"
username = "admin"
password = "s3cret"
verify_ssl = false
legacy_field = "ignored"
""".lstrip()
    )
    monkeypatch.setattr("datamasque_cli.config.CONFIG_FILE", config_file)

    loaded = load_config()
    assert loaded.profiles["default"].url == "https://dm"
    assert loaded.profiles["default"].password == "s3cret"


def test_profile_rejects_non_string_url() -> None:
    """pydantic enforces field types; non-string urls should fail fast."""
    with pytest.raises(pydantic.ValidationError):
        Profile(url=123, username="u", password="p")  # type: ignore[arg-type]
