from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class Param(Protocol):
    """The parameter attributes the catalog reads."""

    name: str | None
    param_type_name: str
    opts: list[str]
    required: bool
    help: str | None
    is_flag: bool


class Command(Protocol):
    """The command attributes the catalog reads."""

    hidden: bool
    help: str | None
    params: list[Param]


@runtime_checkable
class Group(Command, Protocol):
    """A command that holds subcommands."""

    commands: dict[str, Command]


class OptionEntry(TypedDict):
    """A catalog entry for one of a command's options."""

    flags: list[str]
    help: str
    required: bool
    is_flag: bool


class ArgumentEntry(TypedDict):
    """A catalog entry for one of a command's positional arguments."""

    name: str | None
    required: bool
    is_argument: bool


class CompactEntry(TypedDict):
    """A catalog entry as `--compact` emits it, with options dropped."""

    path: str
    help: str


class CommandEntry(CompactEntry):
    """A catalog entry for a single leaf command."""

    options: list[OptionEntry | ArgumentEntry]
