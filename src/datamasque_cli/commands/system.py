"""System-level commands: health, licence, logs, admin-install."""

from __future__ import annotations

from pathlib import Path

import typer

from datamasque_cli.client import get_client
from datamasque_cli.commands.rulesets import export_bundle, import_bundle
from datamasque_cli.output import print_json, print_success, print_warning, render_output

app = typer.Typer(help="System administration commands.", no_args_is_help=True)


@app.command()
def health(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Check DataMasque instance health."""
    client = get_client(profile)
    client.healthcheck()

    if is_json:
        print_json({"status": "healthy"})
    else:
        print_success("Instance is healthy.")


@app.command("licence")
def licence(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show licence information."""
    client = get_client(profile)
    info = client.get_current_license_info()
    # Project to the fields a user actually checks. The full pydantic dump
    # also includes nested SwitchableLicenseMetadata which is noisy.
    expiry = info.expiry_date.isoformat() if info.expiry_date else None
    data = {
        "uuid": info.uuid,
        "name": info.name,
        "type": info.type,
        "is_expired": info.is_expired,
        "expiry_date": expiry,
        "days_until_expiry": info.days_until_expiry,
        "platform_name": info.platform_name,
    }
    render_output(data, is_json=is_json, title="Licence")


@app.command()
def logs(
    output_path: Path = typer.Option("datamasque-logs.tar.gz", "--output", "-o", help="Where to save the log file"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Download application logs."""
    client = get_client(profile)
    client.retrieve_application_logs(output_path)
    print_success(f"Logs saved to {output_path}")


@app.command("export", hidden=True, deprecated=True)
def export_config(
    output_path: Path = typer.Option("datamasque-export.zip", "--output", "-o", help="Where to save the export"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Deprecated alias for `dm rulesets export-bundle`."""
    print_warning("`dm system export` is deprecated; use `dm rulesets export-bundle` instead.")
    export_bundle(output_path=output_path, profile=profile)


@app.command("import", hidden=True, deprecated=True)
def import_config(
    file: Path = typer.Option(..., "--file", "-f", help="Path to import file", exists=True, readable=True),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Deprecated alias for `dm rulesets import-bundle`."""
    print_warning("`dm system import` is deprecated; use `dm rulesets import-bundle` instead.")
    import_bundle(file=file, profile=profile, is_confirmed=is_confirmed)


@app.command("upload-licence")
def upload_licence(
    file: Path = typer.Argument(help="Path to .lic licence file", exists=True, readable=True),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Upload a DataMasque licence file."""
    client = get_client(profile)
    client.upload_license_file(str(file))
    print_success(f"Licence file '{file.name}' uploaded.")


@app.command("admin-install")
def admin_install(
    email: str = typer.Option(..., help="Admin email address"),
    username: str = typer.Option("admin", help="Admin username"),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Admin password"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Initial admin setup for a fresh DataMasque instance."""
    client = get_client(profile)
    client.admin_install(email=email, username=username, password=password)
    print_success(f"Admin user '{username}' created.")


@app.command("set-locality")
def set_locality(
    locality: str = typer.Argument(help="Locality string to set"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Set the system locality."""
    client = get_client(profile)
    client.set_locality(locality)
    print_success(f"Locality set to '{locality}'.")
