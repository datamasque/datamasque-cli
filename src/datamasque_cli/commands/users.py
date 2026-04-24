"""User management commands."""

from __future__ import annotations

import typer
from datamasque.client.models.user import User, UserRole

from datamasque_cli.client import get_client
from datamasque_cli.output import abort, print_success, render_output

app = typer.Typer(help="Manage users.", no_args_is_help=True)


@app.command("list")
def list_users(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all users."""
    client = get_client(profile)
    users = client.list_users()

    data = [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "roles": ", ".join(r.value for r in u.roles),
        }
        for u in users
    ]

    render_output(data, is_json=is_json, columns=["id", "username", "email", "roles"], title="Users")


@app.command("create")
def create_user(
    username: str = typer.Option(..., help="Username"),
    email: str = typer.Option(..., help="Email address"),
    role: list[str] = typer.Option(..., help="Role(s): superuser, mask_builder, mask_runner"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Create a new user."""
    roles = [UserRole(r) for r in role]
    user = User(username=username, email=email, password="", roles=roles)

    client = get_client(profile)
    created = client.create_or_update_user(user)
    print_success(f"User '{username}' created. Temporary password: {created.password}")


@app.command("delete")
def delete_user(
    username: str = typer.Argument(help="Username to delete"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
    is_confirmed: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a user by username."""
    client = get_client(profile)
    users = client.list_users()

    if not any(u.username == username for u in users):
        abort(f"User '{username}' not found.")

    if not is_confirmed:
        typer.confirm(f"Delete user '{username}'?", abort=True)

    client.delete_user_by_username_if_exists(username)
    print_success(f"User '{username}' deleted.")


@app.command("reset-password")
def reset_password(
    username: str = typer.Argument(help="Username to reset password for"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile to use"),
) -> None:
    """Reset a user's password."""
    client = get_client(profile)
    users = client.list_users()

    match = next((u for u in users if u.username == username), None)
    if match is None:
        abort(f"User '{username}' not found.")

    new_password = client.reset_password_for_user(match)
    print_success(f"Password reset for '{username}'. New temporary password: {new_password}")
