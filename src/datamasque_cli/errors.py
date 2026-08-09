from __future__ import annotations

import json
from collections.abc import Mapping
from enum import IntEnum, StrEnum
from http import HTTPStatus
from typing import Any, NoReturn, TypeVar

import typer
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.discovery_config import DiscoveryConfigId
from datamasque.client.models.discovery_config_library import DiscoveryConfigLibraryId
from datamasque.client.models.ruleset import RulesetId
from datamasque.client.models.ruleset_library import RulesetLibraryId
from datamasque.client.models.status import ValidationErrorDetails, ValidationStatus
from pydantic import BaseModel, ConfigDict, JsonValue

from datamasque_cli.output import console, is_agent_context, print_error

AnyId = TypeVar("AnyId", DiscoveryConfigId, DiscoveryConfigLibraryId, RulesetId, RulesetLibraryId)


class ErrorCode(StrEnum):
    """Stable, machine-readable error categories."""

    ERROR = "error"
    NOT_FOUND = "not_found"
    INVALID_INPUT = "invalid_input"
    AMBIGUOUS = "ambiguous"
    AUTH_REQUIRED = "auth_required"
    AUTH_FAILED = "auth_failed"
    CONFLICT = "conflict"
    TRANSPORT_ERROR = "transport_error"
    CANCELLED = "cancelled"
    FORBIDDEN = "forbidden"


class ExitCode(IntEnum):
    """Every process exit status the CLI can return."""

    OK = 0
    ERROR = 1
    USAGE_ERROR = 2
    NOT_FOUND = 3
    INVALID_INPUT = 4
    AMBIGUOUS = 5
    AUTH_REQUIRED = 6
    AUTH_FAILED = 7
    CONFLICT = 8
    TRANSPORT_ERROR = 9
    CANCELLED = 10
    FORBIDDEN = 11


# Stable across minor versions so agents can branch on them. `OK` and `USAGE_ERROR`
# are absent because `abort()` never produces them; typer returns 2 by itself.
EXIT_CODE_BY_ERROR: dict[ErrorCode, ExitCode] = {
    ErrorCode.ERROR: ExitCode.ERROR,
    ErrorCode.NOT_FOUND: ExitCode.NOT_FOUND,
    ErrorCode.INVALID_INPUT: ExitCode.INVALID_INPUT,
    ErrorCode.AMBIGUOUS: ExitCode.AMBIGUOUS,
    ErrorCode.AUTH_REQUIRED: ExitCode.AUTH_REQUIRED,
    ErrorCode.AUTH_FAILED: ExitCode.AUTH_FAILED,
    ErrorCode.CONFLICT: ExitCode.CONFLICT,
    ErrorCode.TRANSPORT_ERROR: ExitCode.TRANSPORT_ERROR,
    ErrorCode.CANCELLED: ExitCode.CANCELLED,
    ErrorCode.FORBIDDEN: ExitCode.FORBIDDEN,
}


def abort(message: str, *, code: ErrorCode = ErrorCode.ERROR, hint: str | None = None) -> NoReturn:
    """Print an error and exit with the exit code mapped to `code`.

    In agent mode, emits a structured error envelope to stderr:
        {"error": {"code": "...", "message": "...", "hint": "..."}}
    In human mode, prints a red 'Error: …' line plus an optional hint.

    `code` is an `ErrorCode` member (StrEnum), so it serializes directly
    into the envelope's `error.code` field as the underlying string.
    """
    if is_agent_context():
        envelope: dict[str, Any] = {"error": {"code": code, "message": message}}
        if hint:
            envelope["error"]["hint"] = hint
        typer.echo(json.dumps(envelope), err=True)
    else:
        print_error(message)
        if hint:
            console.print(f"[dim]Hint: {hint}[/dim]")
    raise SystemExit(EXIT_CODE_BY_ERROR[code])


def confirm_or_abort(message: str) -> None:
    """Ask `message`, and abort with `cancelled` when the answer is no."""
    if typer.confirm(message):
        return
    abort("Cancelled.", code=ErrorCode.CANCELLED)


def require_id_or_abort(id_value: AnyId | None, subject: str) -> AnyId:
    """Return `subject`'s id, or abort when it is absent."""
    if id_value is None:
        abort(f"Server returned {subject} without an id.", code=ErrorCode.ERROR)
    return id_value


class _ValidationEntry(BaseModel):
    """One entry in a validation error list."""

    model_config = ConfigDict(extra="ignore")

    loc: list[str | int] = []
    msg: str


class _ErrorBody(BaseModel):
    """The shapes a DataMasque error response body takes."""

    model_config = ConfigDict(extra="allow")

    detail: str | list[_ValidationEntry] | None = None
    error: str | None = None


def _format_validation_errors(errors: list[_ValidationEntry]) -> str:
    """Render each entry as `field.path: message`, joined with `; `."""
    parts = []
    for error in errors:
        location = ".".join(str(part) for part in error.loc if part != "body")
        parts.append(f"{location}: {error.msg}" if location else error.msg)
    return "; ".join(parts)


def _format_field_errors(fields: Mapping[str, JsonValue]) -> str | None:
    """Render each field error as `field: message`, joined with `; `."""
    parts = [
        str(message) if field == "non_field_errors" else f"{field}: {message}"
        for field, messages in fields.items()
        if isinstance(messages, list)
        for message in messages
    ]
    return "; ".join(parts) or None


def extract_server_error_reason(exc: DataMasqueApiError) -> str | None:
    """Return the reason the server gave for a failed request, or `None` when there is none."""
    try:
        body = _ErrorBody.model_validate(exc.response.json())
    except ValueError:
        return None
    if isinstance(body.detail, str):
        return body.detail
    if body.detail:
        return _format_validation_errors(body.detail)
    return body.error or _format_field_errors(body.model_extra or {})


# The `ErrorCode` each HTTP status means. Anything unlisted is `ERROR`.
_ERROR_CODE_BY_STATUS: Mapping[int, ErrorCode] = {
    HTTPStatus.BAD_REQUEST: ErrorCode.INVALID_INPUT,
    HTTPStatus.UNAUTHORIZED: ErrorCode.AUTH_FAILED,
    HTTPStatus.FORBIDDEN: ErrorCode.FORBIDDEN,
    HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
    HTTPStatus.CONFLICT: ErrorCode.CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY: ErrorCode.INVALID_INPUT,
}


def abort_api_error(prefix: str, exc: DataMasqueApiError, *, conflict_hint: str | None = None) -> NoReturn:
    """Abort with DataMasque's explanation of a failed request."""
    reason = extract_server_error_reason(exc) or str(exc)
    code = _ERROR_CODE_BY_STATUS.get(exc.response.status_code, ErrorCode.ERROR)
    hint = "Run `dm auth login` to sign in again." if code is ErrorCode.AUTH_FAILED else None

    if code is ErrorCode.CONFLICT:
        # Prefixing a conflict repeats what the reason already says.
        abort(reason, code=code, hint=conflict_hint)
    abort(f"{prefix}: {reason}", code=code, hint=hint)


def abort_if_not_found(exc: DataMasqueApiError, subject: str) -> None:
    """Abort when the server says `subject` does not exist."""
    if exc.response.status_code == HTTPStatus.NOT_FOUND:
        abort(f"{subject} not found.", code=ErrorCode.NOT_FOUND)


def abort_if_invalid(subject: str, is_valid: ValidationStatus | None, errors: list[ValidationErrorDetails]) -> None:
    """Print each server-side validation error for `subject` and exit, if it failed validation."""
    if is_valid is not ValidationStatus.invalid and not errors:
        return
    for error in errors:
        location = f" (line {error.line_number})" if error.line_number is not None else ""
        print_error(f"{error.message}{location}")
    abort(f"{subject} is invalid.", code=ErrorCode.INVALID_INPUT)
