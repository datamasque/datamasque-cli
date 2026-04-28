"""DataMasque CLI entry point.

Usage:
    dm auth login
    dm run start --connection mydb --ruleset myrules
    dm run list --status running
    dm rulesets list --json
"""

from __future__ import annotations

from importlib.metadata import version as pkg_version

import typer
from rich.console import Console

from datamasque_cli.commands import (
    auth,
    connections,
    discovery,
    files,
    ifm,
    ruleset_libraries,
    rulesets,
    runs,
    seeds,
    system,
    users,
)

app = typer.Typer(
    name="dm",
    help="DataMasque CLI — manage data masking from the command line.",
    no_args_is_help=True,
)

app.add_typer(auth.app, name="auth")
app.add_typer(connections.app, name="connections")
app.add_typer(rulesets.app, name="rulesets")
app.add_typer(runs.app, name="run")
app.add_typer(users.app, name="users")
app.add_typer(discovery.app, name="discover")
app.add_typer(seeds.app, name="seeds")
app.add_typer(files.app, name="files")
app.add_typer(system.app, name="system")
app.add_typer(ruleset_libraries.app, name="libraries")
app.add_typer(ifm.app, name="ifm")


@app.command()
def version() -> None:
    """Show the CLI version."""
    console = Console(stderr=True)
    console.print("  [#7B36F5]▷◁[/#7B36F5]  ", end="")
    console.print("[bold #7B36F5]DataMasque[/bold #7B36F5] CLI", end="  ")
    typer.echo(f"v{pkg_version('datamasque-cli')}")


if __name__ == "__main__":
    app()
