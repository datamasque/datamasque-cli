"""DataMasque CLI entry point.

Usage:
    dm auth login
    dm run start --connection mydb --ruleset myrules
    dm run list --status running
    dm rulesets list --json
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import version as pkg_version

import typer
from datamasque.client.exceptions import (
    DataMasqueApiError,
    DataMasqueException,
    DataMasqueTransportError,
)
from rich.console import Console
from typer.main import get_command

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
    table_references,
    users,
)
from datamasque_cli.errors import ErrorCode, abort, abort_api_error
from datamasque_cli.output import print_json, should_emit_json, stdout_console
from datamasque_cli.protocols import (
    Argument,
    ArgumentEntry,
    CommandEntry,
    CompactEntry,
    Group,
    Option,
    OptionEntry,
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
app.add_typer(table_references.app, name="table-references")


@app.command()
def version() -> None:
    """Show the CLI version."""
    console = Console(stderr=True)
    console.print("  [#7B36F5]▷◁[/#7B36F5]  ", end="")
    console.print("[bold #7B36F5]DataMasque[/bold #7B36F5] CLI", end="  ")
    typer.echo(f"v{pkg_version('datamasque-cli')}")


def walk_commands(group: Group, path_prefix: str = "") -> list[CommandEntry]:
    """Walk a command group recursively and yield one entry per leaf command."""
    items: list[CommandEntry] = []
    for name, cmd in sorted(group.commands.items()):
        if cmd.hidden:
            continue
        path = f"{path_prefix} {name}".strip()
        if isinstance(cmd, Group):
            items.extend(walk_commands(cmd, path))
            continue
        options: list[OptionEntry | ArgumentEntry] = []
        for param in cmd.params:
            if isinstance(param, Option):
                options.append(
                    OptionEntry(
                        flags=list(param.opts),
                        help=param.help or "",
                        required=param.required,
                        is_flag=param.is_flag,
                    )
                )
            elif isinstance(param, Argument):
                options.append(
                    ArgumentEntry(
                        name=param.name,
                        required=param.required,
                        is_argument=True,
                    )
                )
        # Take only the first paragraph of help text — keeps the catalog dense.
        help_text = (cmd.help or "").strip().split("\n\n", 1)[0].replace("\n", " ")
        items.append(CommandEntry(path=path, help=help_text, options=options))
    return items


@app.command()
def catalog(
    is_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    is_compact: bool = typer.Option(
        False, "--compact", help="Drop options/arguments — show only command paths and help."
    ),
) -> None:
    """Dump the full CLI command tree for agent discovery.

    Designed to be called once at session start so an agent can introspect
    every available subcommand without parsing per-command --help screens.
    """
    root = get_command(app)
    if not isinstance(root, Group):
        raise RuntimeError("Root command is not a command group; cannot walk catalog.")
    commands = walk_commands(root)
    items: Sequence[CompactEntry] = (
        [CompactEntry(path=command["path"], help=command["help"]) for command in commands] if is_compact else commands
    )

    if should_emit_json(is_json):
        print_json({"commands": items})
        return

    # Human mode: render a flat indented list. Tables would balloon the width
    # and obscure that the structure is `<group> <subcommand>`.
    width = max(len(item["path"]) for item in items) if items else 0
    for item in items:
        stdout_console.print(f"  [bold]{item['path']:<{width}}[/bold]  [dim]{item['help']}[/dim]")


def main() -> None:
    try:
        app()
    except DataMasqueApiError as exc:
        abort_api_error("Request failed", exc)
    except DataMasqueTransportError as exc:
        abort(str(exc), code=ErrorCode.TRANSPORT_ERROR)
    except DataMasqueException as exc:
        abort(str(exc), code=ErrorCode.ERROR)


if __name__ == "__main__":
    main()
