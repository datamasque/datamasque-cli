# Changelog

## Unreleased

### Added
- `dm table-references` — manage table references (`list`, `get`, `create`,
  `update`, `delete`), the named pointers to identity data used for
  cross-system consistent masking. `create` accepts `--file` for a full
  JSON definition or `--name`/`--connection`/`--source` flags plus the
  format/CSV options (`--format`, `--delimiter`, `--encoding`,
  `--quotechar`, `--null-string`) for the common case, and is a
  create-or-update like `dm connections create`; `update` changes only the
  fields passed, preserving the reference's id.

### Internal
- Extracted `resolve_connection` (name-or-ID lookup) into `client.py` and
  routed `connections.py`'s `test`/`update` and `discover schema`/`discover
  file` through it, replacing three separate inline copies.

## v1.5.1

### Added
- `dm discover schema-results` notes when a run holds Safe Data Preview results.
  The table cannot show them, so the note points to `--json`.

### Fixed
- A fresh install no longer fails when `typer` drops a package `dm` imports.
  `rich` is now a declared dependency, and `typer` requires 0.16.0 or later.

## v1.5.0

### Added
- Support for datamasque-python 1.2.3.
  - `dm discover schema-results` handles matches with no label.
  - `dm rulesets validate` and `dm libraries validate` report each validation
    error for invalid YAML, with its line and column.
- Support for Configurable Discovery:
  - `dm discover configs` — list, get, defaults, create, delete, validate,
    and status for discovery configs (`database` or `file`).
  - `dm discover libraries` — list, get, create, delete, validate, and status
    for discovery config libraries.
  - `dm discover schema --config <name>` and `dm discover file
    [--config <name>]` start discovery runs with or without a specific config.
  - `dm discover config-snapshot <run-id>` downloads the discovery config a run
    actually used.
- `dm rulesets status` and `dm libraries status` — show a stored ruleset's or
  library's validation state and errors.
- `dm rulesets validate` and `dm discover configs validate` refuse YAML of
  60 KiB or larger, which the server validates asynchronously; create it and
  poll `status` instead.
- Safe Data Preview: `dm discover schema-results` and `dm discover file-report`
  include `safe_data_preview` in their `--json` output.

### Changed
- A declined confirmation prompt now exits 10 (`cancelled`) instead of 1,
  so a decision is not reported as a failure. Ctrl-C still exits 1.
- `dm run start --json` and `dm run retry --json` only emit the run id.
  `"status": "queued"` is no longer returned.

### Fixed
- `dm rulesets generate`, `dm connections update --password`, and the
  deprecated `dm system import` no longer fail.
- File errors now name the file instead of printing a traceback.
- Unhandled server and network errors now abort with a code, not a traceback.

## v1.4.0

### Added
- `dm connections create --file` now supports Databricks SQL Warehouse
  (`"type": "databricks"`) and MongoDB (`"type": "mongodb"`) connections.
  Both list, get, create, and delete like the existing connection types.

## v1.3.0

### Added
- `dm system ai-engine show` and `dm system ai-engine set <URL>` — view and
  configure the AI Engine URL.

## v1.2.0

### Added
- `dm ifm` command group
  for managing in-flight masking ruleset plans
  and running mask operations against the IFM service:
  - `dm ifm list` —
    list all IFM ruleset plans.
  - `dm ifm get <name>` —
    show plan metadata,
    or the ruleset YAML with `--yaml`.
  - `dm ifm create --name <name> --file <yaml>` —
    create a plan from a YAML ruleset,
    with optional `--enabled/--disabled` and `--log-level`.
  - `dm ifm update <name>` —
    update a plan;
    pass any of `--file`, `--enabled/--disabled`, `--log-level`
    and only those fields are sent.
  - `dm ifm delete <name>` —
    delete a plan
    (interactive confirm,
    or `--yes` to skip).
  - `dm ifm mask <name> --data <file|->` —
    mask a JSON list of records against a plan,
    with `--disable-instance-secret`,
    `--run-secret`,
    `--log-level`,
    `--request-id`,
    and `--json/--no-json` (NDJSON) output.
  - `dm ifm verify-token` —
    verify the current IFM token and list its scopes.

  Authentication reuses your existing `dm` profile credentials
  via the SDK's `DataMasqueIfmClient`,
  which transparently exchanges admin-server credentials for an IFM JWT.

## v1.1.0

### Added
- `dm catalog` command — emits the full subcommand tree as JSON for agent
  introspection. `--compact` for `{path, help}` only (~1.4kB), default for
  full options/arguments.
- Auto-detection of agent context: output flips to JSON automatically when
  stdout is not a TTY, when `DM_OUTPUT=json` is set, or when the
  vendor-neutral `AI_AGENT` env var is present. `DM_OUTPUT=table` forces
  human output.
- Structured error envelope on stderr in agent mode:
  `{"error": {"code": "...", "message": "...", "hint": "..."}}` — stdout
  stays empty on failure so downstream pipes don't trip.

### Changed
- Exit codes are now differentiated by error category. Previously every
  error returned 1; now: `not_found`=3, `invalid_input`=4, `ambiguous`=5,
  `auth_required`=6, `auth_failed`=7, `conflict`=8, `transport_error`=9.
  `error` (unclassified) remains 1; 2 is reserved for typer/click usage
  errors. Stable across minor versions.
- Long values (UUIDs especially) now fold across lines in table output
  rather than being silently truncated with `…` in narrow terminals.

### Internal
- `ErrorCode` and `ConnectionType` are now `StrEnum`s; the abort code arg
  is type-checked at edit time and the connection-type "Valid: ..." hint
  is generated from the enum.

## v1.0.0

Initial release.
