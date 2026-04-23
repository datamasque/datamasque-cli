"""Authentication and profile management commands."""

from __future__ import annotations

import typer

from datamasque_cli.client import get_client, profile_from_env
from datamasque_cli.config import DEFAULT_PROFILE, Profile, load_config, save_config
from datamasque_cli.output import abort, print_info, print_success, print_table

# `login` and `status` handle connection errors locally
# because they need softer behaviour than `get_client`'s hard abort:
# login saves credentials even when the server is unreachable,
# and status prints profile info before attempting connection.

app = typer.Typer(help="Authentication and profile management.")


@app.command()
def login(
    profile: str = typer.Option("default", help="Profile name to store credentials under"),
    is_insecure: bool = typer.Option(
        False,
        "--insecure",
        help="Skip TLS verification when talking to this instance (self-signed / expired cert).",
    ),
) -> None:
    """Save credentials for a DataMasque instance.

    Fully interactive: prompts for URL, username, and password. Credentials
    are saved to `~/.config/datamasque-cli/config.toml` (mode 0600). For
    non-interactive / CI use, set `DATAMASQUE_URL`, `DATAMASQUE_USERNAME`,
    and `DATAMASQUE_PASSWORD` env vars instead — `dm` reads them directly
    without a saved profile. Pair with `DATAMASQUE_VERIFY_SSL=false` to
    skip TLS verification on a per-call basis.
    """
    url = typer.prompt("DataMasque URL").rstrip("/")
    if not url.startswith(("http://", "https://")):
        abort(f"URL must start with http:// or https:// (got '{url}').")

    username = typer.prompt("Username")
    password = typer.prompt("Password", hide_input=True)
    config = load_config()

    config.set_profile(
        profile,
        Profile(url=url, username=username, password=password, verify_ssl=not is_insecure),
    )
    config.active_profile = profile
    save_config(config)
    print_success(f"Credentials saved to profile '{profile}'.")

    print_info("Verifying connection...")
    try:
        get_client(profile)
    except SystemExit:
        # Credentials are already saved; connection verification is best-effort.
        return
    print_success("Authentication successful.")


@app.command()
def logout(
    profile: str | None = typer.Option(None, help="Profile to remove. Removes active profile if omitted."),
) -> None:
    """Remove stored credentials for a profile."""
    config = load_config()
    name = profile or config.active_profile

    if not config.delete_profile(name):
        abort(f"Profile '{name}' does not exist.")

    # If we just deleted the active profile, fall back to another one.
    if name == config.active_profile:
        remaining = config.list_profile_names()
        config.active_profile = remaining[0] if remaining else DEFAULT_PROFILE

    save_config(config)
    print_success(f"Profile '{name}' removed.")


@app.command("use")
def use_profile(
    profile: str = typer.Argument(help="Profile name to set as active"),
) -> None:
    """Set the active profile."""
    config = load_config()

    if profile not in config.profiles:
        abort(f"Profile '{profile}' does not exist. Run: dm auth login --profile {profile}")

    config.active_profile = profile
    save_config(config)
    print_success(f"Active profile set to '{profile}'.")


@app.command("list")
def list_profiles() -> None:
    """List all configured profiles."""
    config = load_config()
    names = config.list_profile_names()

    if not names:
        print_info("No profiles configured. Run: dm auth login")
        return

    rows = []
    for name in names:
        p = config.profiles[name]
        is_active = name == config.active_profile
        rows.append(
            [
                "*" if is_active else "",
                name,
                p.url,
                p.username,
            ]
        )

    print_table(["", "Profile", "URL", "Username"], rows)


@app.command()
def status() -> None:
    """Show current authentication status and instance info."""
    # Env vars take precedence over any saved profile in `get_client`,
    # so report them here as the actual source rather than the stale profile.
    env_profile = profile_from_env()
    if env_profile is not None:
        profile_label = "(env)"
        profile = env_profile
    else:
        config = load_config()
        profile = config.get_profile()
        if not profile.is_configured:
            abort(f"Profile '{config.active_profile}' is not configured. Run: dm auth login")
        profile_label = config.active_profile

    print_info(f"Profile: {profile_label}")
    print_info(f"URL: {profile.url}")
    print_info(f"Username: {profile.username}")

    try:
        client = get_client()
    except SystemExit:
        # `get_client` aborts on connection/auth failure,
        # but here we want a softer warning since profile info was already printed.
        return

    license_info = client.get_current_license_info()
    print_success("Authenticated.")
    print_info(f"Licence: {license_info.uuid}")
    expiry = license_info.expiry_date.isoformat() if license_info.expiry_date else "unknown"
    print_info(f"Expiry: {expiry}")
