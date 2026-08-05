from __future__ import annotations

import json
from collections.abc import Mapping
from enum import IntEnum, StrEnum
from http import HTTPStatus
from typing import Any, NoReturn

import typer
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.status import ValidationErrorDetails, ValidationStatus
from pydantic import BaseModel, ConfigDict

from datamasque_cli.output import console, is_agent_context, print_error


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


class _ValidationEntry(BaseModel):
    """One entry in a validation error list."""

    model_config = ConfigDict(extra="ignore")

    loc: list[str | int] = []
    msg: str


class _ErrorBody(BaseModel):
    """The shapes a DataMasque error response body takes."""

    model_config = ConfigDict(extra="ignore")

    detail: str | list[_ValidationEntry] | None = None
    error: str | None = None


def _format_validation_errors(errors: list[_ValidationEntry]) -> str:
    """Render each entry as `field.path: message`, joined with `; `."""
    parts = []
    for error in errors:
        location = ".".join(str(part) for part in error.loc if part != "body")
        parts.append(f"{location}: {error.msg}" if location else error.msg)
    return "; ".join(parts)


def _server_error_detail(exc: DataMasqueApiError) -> str | None:
    """Return the error text from the response body, or `None` when there is none."""
    try:
        body = _ErrorBody.model_validate(exc.response.json())
    except (ValueError, AttributeError):
        return None
    if isinstance(body.detail, str):
        return body.detail
    if body.detail:
        return _format_validation_errors(body.detail)
    return body.error


_DEFAULT_STATUS_CODES: Mapping[int, ErrorCode] = {HTTPStatus.CONFLICT: ErrorCode.CONFLICT}


def abort_api_error(
    prefix: str,
    exc: DataMasqueApiError,
    *,
    conflict_hint: str | None = None,
    status_codes: Mapping[int, ErrorCode] = _DEFAULT_STATUS_CODES,
) -> NoReturn:
    """Abort with DataMasque's explanation of a failed request.

    `status_codes` maps an HTTP status to an `ErrorCode`; anything unlisted is `ERROR`.
    """
    reason = _server_error_detail(exc) or str(exc)
    code = status_codes.get(exc.response.status_code, ErrorCode.ERROR)

    if code is ErrorCode.CONFLICT:
        # Prefixing a conflict repeats what the reason already says.
        abort(reason, code=code, hint=conflict_hint)
    abort(f"{prefix}: {reason}", code=code)


def abort_if_invalid(subject: str, is_valid: ValidationStatus | None, errors: list[ValidationErrorDetails]) -> None:
    """Print each server-side validation error for `subject` and exit, if it failed validation."""
    if is_valid is not ValidationStatus.invalid and not errors:
        return
    for error in errors:
        location = f" (line {error.line_number})" if error.line_number is not None else ""
        print_error(f"{error.message}{location}")
    abort(f"{subject} is invalid.", code=ErrorCode.INVALID_INPUT)
