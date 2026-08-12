"""Reading and writing the files a user passes on the command line.

Every read and write goes through here, so a bad path, a bad encoding, or bad
content ends the command with a coded error naming the file, not a traceback.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import JsonValue

from datamasque_cli.errors import ErrorCode, abort

# Mirrors the server's limit: at or above this, validation is queued and returns no verdict.
MAX_SYNC_VALIDATION_KIB = 60
_BYTES_PER_KIB = 1024


def abort_if_too_large_for_sync_validation(
    yaml_content: str, file: Path, *, create_command: str, status_command: str
) -> None:
    """Abort when `yaml_content` is too large for the server to validate synchronously."""
    size = len(yaml_content.encode("utf-8"))
    if size < MAX_SYNC_VALIDATION_KIB * _BYTES_PER_KIB:
        return
    abort(
        f"{file} is {size // _BYTES_PER_KIB} KiB; "
        f"validation for YAML of {MAX_SYNC_VALIDATION_KIB} KiB or larger runs asynchronously.",
        code=ErrorCode.INVALID_INPUT,
        hint=f"Create it with `{create_command}`, then check `{status_command}` until validation finishes.",
    )


def read_text_or_abort(file: Path) -> str:
    """Read `file` as UTF-8, and abort when it cannot be read or decoded."""
    try:
        content = file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        abort(f"{file} is not valid UTF-8.", code=ErrorCode.INVALID_INPUT, hint="Re-save the file as UTF-8.")
    except OSError as exc:
        code = ErrorCode.NOT_FOUND if isinstance(exc, FileNotFoundError) else ErrorCode.INVALID_INPUT
        abort(f"Could not read {file}: {exc.strerror or exc}", code=code)

    if not content.strip():
        abort(f"{file} is empty.", code=ErrorCode.INVALID_INPUT)
    return content


def read_json_object_or_abort(file: Path) -> dict[str, JsonValue]:
    """Read `file` as a UTF-8 JSON object, and abort when it cannot be read or parsed."""
    content = read_text_or_abort(file)
    try:
        parsed: JsonValue = json.loads(content)
    except json.JSONDecodeError as exc:
        abort(f"{file} is not valid JSON: {exc}", code=ErrorCode.INVALID_INPUT)
    if not isinstance(parsed, dict):
        abort(f"{file} must contain a JSON object.", code=ErrorCode.INVALID_INPUT)
    return parsed


def write_bytes_or_abort(path: Path, content: bytes) -> None:
    """Write `content` to `path`, and abort when the path cannot be written."""
    try:
        path.write_bytes(content)
    except OSError as exc:
        abort(f"Could not write {path}: {exc.strerror or exc}", code=ErrorCode.INVALID_INPUT)


def write_text_or_abort(path: Path, content: str) -> None:
    """Write `content` to `path` as UTF-8, and abort when the path cannot be written."""
    write_bytes_or_abort(path, content.encode("utf-8"))
