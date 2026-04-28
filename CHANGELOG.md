# Changelog

## v1.1.0

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

## v1.0.0

Initial release.
