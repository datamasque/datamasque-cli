"""Authenticated DataMasque client factory.

Resolves credentials from environment variables or the active profile,
builds a `DataMasqueClient`, and authenticates it before returning.
"""

from __future__ import annotations

import os

from datamasque.client import DataMasqueClient, DataMasqueIfmClient
from datamasque.client.exceptions import DataMasqueApiError, DataMasqueTransportError, IfmAuthError
from datamasque.client.models.dm_instance import DataMasqueInstanceConfig
from datamasque.client.models.ifm import DataMasqueIfmInstanceConfig

from datamasque_cli.config import Config, Profile, load_config
from datamasque_cli.output import ErrorCode, abort

ENV_URL = "DATAMASQUE_URL"
ENV_USERNAME = "DATAMASQUE_USERNAME"
ENV_PASSWORD = "DATAMASQUE_PASSWORD"
ENV_VERIFY_SSL = "DATAMASQUE_VERIFY_SSL"

# `false`-y env values that disable TLS verification.
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})


def _verify_ssl_from_env(default: bool) -> bool:
    """Resolve `verify_ssl` from `DATAMASQUE_VERIFY_SSL`, falling back to `default`."""
    raw = os.environ.get(ENV_VERIFY_SSL)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSE_VALUES


def profile_from_env() -> Profile | None:
    """Build a profile from environment variables, or return None if not set."""
    url = os.environ.get(ENV_URL)
    username = os.environ.get(ENV_USERNAME)
    password = os.environ.get(ENV_PASSWORD)
    if url and username and password:
        return Profile(
            url=url.rstrip("/"),
            username=username,
            password=password,
            verify_ssl=_verify_ssl_from_env(default=True),
        )
    return None


def _profile_from_env_url_only() -> Profile | None:
    """Build a URL-only profile from `DATAMASQUE_URL`, with empty username/password.

    Used by the unauthenticated client factory so callers can hit anonymous
    endpoints (admin-install, health) without setting `DATAMASQUE_USERNAME`
    and `DATAMASQUE_PASSWORD` -- those fields aren't read by anonymous calls
    and demanding them is friction for the first-run setup workflow.
    """
    url = os.environ.get(ENV_URL)
    if not url:
        return None
    return Profile(
        url=url.rstrip("/"),
        username="",
        password="",
        verify_ssl=_verify_ssl_from_env(default=True),
    )


def _resolve_profile(config: Config, profile_name: str | None) -> Profile:
    profile = config.get_profile(profile_name)
    if not profile.is_configured:
        name = profile_name or config.active_profile
        abort(
            f"Profile '{name}' is not configured.",
            code=ErrorCode.AUTH_REQUIRED,
            hint=(f"Run: dm auth login --profile {name} or set {ENV_URL}, {ENV_USERNAME}, and {ENV_PASSWORD}."),
        )
    return profile


def _resolve_profile_for_unauthenticated(profile_name: str | None) -> Profile:
    """Resolve a profile for an unauthenticated call -- only the URL is required.

    Order: explicit `--profile`, env vars (URL-only is sufficient here),
    saved active profile. If none yield a URL, abort with a clear hint.
    """
    if profile_name is not None:
        profile = load_config().get_profile(profile_name)
    else:
        profile = _profile_from_env_url_only() or load_config().get_profile()
    if not profile.url:
        abort(
            "No DataMasque URL configured.",
            code=ErrorCode.AUTH_REQUIRED,
            hint=f"Set {ENV_URL} or run: dm auth login",
        )
    return profile


def _resolve_profile_with_verify(profile_name: str | None) -> tuple[Profile, bool]:
    """Resolve the active `Profile` and apply env-var overrides for `verify_ssl`."""
    env_profile = profile_from_env() if profile_name is None else None
    if env_profile is not None:
        profile = env_profile
    else:
        config = load_config()
        profile = _resolve_profile(config, profile_name)
    return profile, _verify_ssl_from_env(default=profile.verify_ssl)


def _authenticate_or_abort(
    client: DataMasqueClient | DataMasqueIfmClient,
    url: str,
    *,
    verify_ssl: bool,
    failure_label: str = "Authentication",
    extra_auth_excs: tuple[type[Exception], ...] = (),
) -> None:
    try:
        client.authenticate()
    except DataMasqueTransportError as e:
        abort(_format_transport_error(url, e, verify_ssl=verify_ssl), code=ErrorCode.TRANSPORT_ERROR)
    except (DataMasqueApiError, *extra_auth_excs) as e:
        abort(f"{failure_label} failed: {e}", code=ErrorCode.AUTH_FAILED)


def get_client(profile_name: str | None = None) -> DataMasqueClient:
    """Build and authenticate a `DataMasqueClient`.

    Credential resolution order:
    1. Environment variables (DATAMASQUE_URL, DATAMASQUE_USERNAME, DATAMASQUE_PASSWORD)
    2. Named profile (--profile flag)
    3. Active profile from config file

    `DATAMASQUE_VERIFY_SSL` always wins over the stored profile so you can
    flip TLS verification per-call without re-running `dm auth login`.
    """
    client, profile, verify_ssl = _build_client(profile_name)
    _authenticate_or_abort(client, profile.url, verify_ssl=verify_ssl)
    return client


def get_unauthenticated_client(profile_name: str | None = None) -> DataMasqueClient:
    """Build a `DataMasqueClient` without performing the up-front login handshake.

    Used by commands that hit endpoints which don't require — or can't yet
    use — a token. `admin-install` is the canonical example: on a fresh
    server there's no user to authenticate as, so `client.authenticate()`
    would always fail before the command ran.

    Only `DATAMASQUE_URL` (or a profile with a URL) is required — username
    and password aren't read by anonymous endpoints, so demanding them
    would be unnecessary friction for first-run setup.
    """
    profile = _resolve_profile_for_unauthenticated(profile_name)
    verify_ssl = _verify_ssl_from_env(default=profile.verify_ssl)
    instance_config = DataMasqueInstanceConfig(
        base_url=profile.url,
        username=profile.username,
        password=profile.password,
        verify_ssl=verify_ssl,
    )
    return DataMasqueClient(instance_config)


def _build_client(profile_name: str | None) -> tuple[DataMasqueClient, Profile, bool]:
    profile, verify_ssl = _resolve_profile_with_verify(profile_name)
    instance_config = DataMasqueInstanceConfig(
        base_url=profile.url,
        username=profile.username,
        password=profile.password,
        verify_ssl=verify_ssl,
    )
    return DataMasqueClient(instance_config), profile, verify_ssl


# Substrings that suggest the underlying error was a TLS failure rather than
# a plain network outage, so we can point local-build users at `--insecure`.
_SSL_HINT_TERMS = ("ssl", "certificate", "verify")


def _format_transport_error(url: str, error: Exception, *, verify_ssl: bool) -> str:
    message = f"Could not connect to {url}: {error}"
    if verify_ssl and any(term in str(error).lower() for term in _SSL_HINT_TERMS):
        message += "\nIf this is a self-signed local build, retry with --insecure or set DATAMASQUE_VERIFY_SSL=false."
    return message


def get_ifm_client(profile_name: str | None = None) -> DataMasqueIfmClient:
    """Build and authenticate a `DataMasqueIfmClient`.

    Credential resolution order matches `get_client`.
    The IFM base URL is derived as `<admin_url>/ifm`,
    matching the standard nginx topology that proxies `/ifm/` to the IFM container on the same hostname.
    """
    profile, verify_ssl = _resolve_profile_with_verify(profile_name)
    instance_config = DataMasqueIfmInstanceConfig(
        admin_server_base_url=profile.url,
        ifm_base_url=f"{profile.url.rstrip('/')}/ifm",
        username=profile.username,
        password=profile.password,
        verify_ssl=verify_ssl,
    )

    client = DataMasqueIfmClient(instance_config)
    _authenticate_or_abort(
        client,
        profile.url,
        verify_ssl=verify_ssl,
        failure_label="IFM authentication",
        extra_auth_excs=(IfmAuthError,),
    )
    return client
