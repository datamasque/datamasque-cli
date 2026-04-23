"""Profile-based configuration management.

Stores credentials and connection details in ~/.config/datamasque-cli/config.toml.
Supports named profiles (default, staging, prod, etc.).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".config" / "datamasque-cli"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DEFAULT_PROFILE = "default"


class Profile(BaseModel):
    url: str = ""
    username: str = ""
    password: str = ""
    # Disable TLS verification for instances with self-signed or expired certs
    # (typically local dev). Persisted to config so you don't re-pass it per call.
    verify_ssl: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.username and self.password)


class Config(BaseModel):
    profiles: dict[str, Profile] = Field(default_factory=dict)
    active_profile: str = DEFAULT_PROFILE

    def get_profile(self, name: str | None = None) -> Profile:
        name = name or self.active_profile
        # Return a fresh default for unknown names so callers can check
        # `is_configured` without mutating the stored profile dict.
        return self.profiles.get(name, Profile())

    def set_profile(self, name: str, profile: Profile) -> None:
        self.profiles[name] = profile

    def delete_profile(self, name: str) -> bool:
        if name not in self.profiles:
            return False
        del self.profiles[name]
        return True

    def list_profile_names(self) -> list[str]:
        return list(self.profiles.keys())


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        return Config()

    with open(CONFIG_FILE, "rb") as f:
        data = tomllib.load(f)

    # Ignore unknown top-level or per-profile keys (e.g. the dead `verify_ssl`
    # that older configs may still carry) so on-disk files written by previous
    # releases keep loading cleanly.
    profiles_raw = data.get("profiles", {}) or {}
    profiles = {
        name: Profile.model_validate({k: v for k, v in profile.items() if k in Profile.model_fields})
        for name, profile in profiles_raw.items()
    }
    return Config(profiles=profiles, active_profile=data.get("active_profile", DEFAULT_PROFILE))


def save_config(config: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    data = config.model_dump()

    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(data, f)

    CONFIG_FILE.chmod(0o600)
