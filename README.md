# DataMasque CLI

Official command-line interface for the
[DataMasque](https://datamasque.com/) platform.

DataMasque is a data masking platform that replaces sensitive data with realistic but non-production values,
so teams can use production-shaped data in non-production environments without exposing PII.

DataMasque CLI `dm` covers:

- connections, rulesets, ruleset libraries, and masking runs
- in-flight masking (IFM) ruleset plans and on-demand mask requests
- schema discovery and sensitive-data discovery
- users, files, and DataMasque instance administration

<p align="center">
  <img src="assets/demo.gif" width="820" alt="DataMasque CLI demo — running dm version, listing connections, and checking a masking run">
</p>

## Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```console
uv tool install datamasque-cli
```

This installs `dm` as a command in your terminal.

To run without installing:

```console
uvx --from datamasque-cli dm
```

## Quickstart

> [!NOTE]
> `dm auth login` writes credentials in plain text (mode 600).
> For shared hosts or any machine you'd rather not leave credentials on disk, [set environmental variables](#configuration) instead.
>
> Either way, prefer a `mask_builder` or `mask_runner` role over admin.

```console
# Save credentials
dm auth login

# Browse configurations
dm connections list
dm rulesets list

# Start a masking run
dm run start --connection mydb --ruleset myruleset

# Check progress on masking runs
dm run list --status running
dm run logs 42 --follow
```

`dm run start` and `dm run wait` block until the run finishes.
Pass `--background` to `start` to skip the wait.

## Claude Code skills

The [`claude-skills/`](claude-skills/) directory ships three
[Claude Code](https://claude.com/claude-code) plugins that drive `dm` on your behalf:

- **`datamasque-cli`** — operate a DataMasque instance (start runs, list connections, fetch discovery reports).
- **`ruleset-builder`** — turn auto-generated rulesets into production-ready ones.
- **`ruleset-splitter`** — join many-file rulesets into one file for editing, then re-split.

Install via the Claude Code plugin marketplace:

```
/plugin marketplace add datamasque/datamasque-cli
/plugin install datamasque-cli@datamasque-tools
/plugin install ruleset-builder@datamasque-tools
/plugin install ruleset-splitter@datamasque-tools
```

See [`claude-skills/README.md`](claude-skills/README.md) for more.

## Shell completion

`dm` provides built-in completion for bash, zsh, and fish:

```console
dm --install-completion
```

Restart your shell, then `dm run <TAB>` and friends will complete subcommands.
`dm --show-completion` prints the script without installing it.

## Configuration

To use environmental variables for DataMasque Authentication,
set `DATAMASQUE_URL`, `DATAMASQUE_USERNAME`, and `DATAMASQUE_PASSWORD`.
These take precedence over any saved profile for that call.

Otherwise, `dm auth` credentials live in `~/.config/datamasque-cli/config.toml` (mode `0600`).

Manage multiple instances by passing `--profile` to `dm auth login`,
then `dm auth use <profile>` to switch the default,
or `--profile <name>` on any command to override per-call.

For instances with self-signed or expired TLS certificates
(typically a local dev box),
pass `--insecure` to `dm auth login` to persist the toggle on the profile,
or set `DATAMASQUE_VERIFY_SSL=false` to skip verification per call.

## Commands

### Authentication

```console
dm auth login                                   # Interactive — prompts for URL, username, password
dm auth login --profile staging                 # Save credentials under a named profile
dm auth login --insecure                        # Skip TLS verification (self-signed / expired cert)
dm auth status                                  # Show current auth + licence
dm auth list                                    # List configured profiles
dm auth use <profile>                           # Switch active profile
dm auth logout                                  # Remove stored credentials
```

### Connections

```console
dm connections list                             # List all connections (includes source/destination role)
dm connections get <name>                       # Show connection details
dm connections create --file conn.json          # Create from JSON
dm connections create --name <n> --type database --db-type postgres \
    --host <h> --port 5432 --database <d> --user <u> --password <p>
dm connections test <name>                      # Verify reachability (DB handshake / filesystem / bucket)
dm connections update <name> --password <new>   # Rotate a field in place, preserving the UUID
dm connections delete <name>                    # Delete a connection
```

### Rulesets

```console
dm rulesets list                                  # List all rulesets
dm rulesets list --type file                      # Filter by type
dm rulesets get <name>                            # Show ruleset details
dm rulesets get <name> --yaml                     # Print raw YAML only
dm rulesets get <name> --type file                # Disambiguate same-name rulesets
dm rulesets create --name <n> --file rules.yaml   # Create/update (type auto-detected from YAML)
dm rulesets create --name <n> --file rules.yaml --type file  # Force a type
dm rulesets delete <name> [--type file|database]  # Delete a ruleset
dm rulesets generate --file request.json          # Generate from schema
dm rulesets generate --file req.json -o out.yaml  # Generate to file
dm rulesets validate --file rules.yaml            # Validate against server
dm rulesets export-bundle -o bundle.zip           # Export rulesets + libraries + seeds
dm rulesets import-bundle --file bundle.zip       # Import a previously exported bundle
dm rulesets import-bundle -f bundle.zip --overwrite-rulesets --overwrite-libraries  # Replace existing entries
```

### Ruleset libraries

```console
dm libraries list                                 # List all libraries
dm libraries get <name>                           # Show library details
dm libraries get <name> --yaml                    # Print raw YAML only
dm libraries create --name <n> --file lib.yaml    # Create/update from file
dm libraries create --name <n> --file lib.yaml --namespace pii  # With namespace
dm libraries delete <name>                        # Delete a library
dm libraries validate <name>                      # Re-validate against current server schema
dm libraries usage <name>                         # Show rulesets using it
```

### In-flight masking

The IFM service runs alongside the admin server,
reached at `<DataMasque URL>/ifm`.

```console
dm ifm list                                            # List ruleset plans
dm ifm get <name>                                      # Show plan metadata
dm ifm get <name> --yaml                               # Print the ruleset YAML
dm ifm create --name myplan --file rules.yaml          # Create (server suffixes a random string to the name)
dm ifm create --name myplan --file rules.yaml --disabled --log-level DEBUG
dm ifm update <name> --file rules.yaml                 # Replace the ruleset YAML
dm ifm update <name> --enabled                         # Toggle without re-sending the YAML
dm ifm update <name> --log-level INFO
dm ifm delete <name> --yes                             # Delete a plan
dm ifm mask <name> --data input.json                   # Mask a JSON list of records
dm ifm mask <name> --data -                            # Read records from stdin
dm ifm verify-token                                    # Show scopes granted to the current IFM token
```

### Masking runs

```console
dm run start -c <conn> -r <ruleset>                          # Start a run and block until done
dm run start -c <conn> -r <ruleset> --background             # Start and return immediately
dm run start -c <conn> -r <ruleset> --options batch_size=1000 --options dry_run=true
dm run retry <id>                                             # Re-run with the same config as an existing run
dm run status <id>                                            # Get run status
dm run list                                                   # List recent runs
dm run list --status running                                  # Filter by status
dm run logs <id>                                              # Show execution logs
dm run logs <id> --follow                                     # Stream logs until terminal state
dm run cancel <id>                                            # Cancel a running job
dm run wait <id>                                              # Block until complete
dm run report <id>                                            # Download the masking run CSV report
```

### Users

```console
dm users list                                   # List all users
dm users create --username <u> --email <e> --role mask_builder
dm users reset-password <username>              # Reset to temp password
dm users delete <username>                      # Delete a user
```

### Discovery

```console
dm discover schema <connection>                 # Start a schema-discovery run
dm discover schema-results <run-id>             # List schema-discovery results once the run finishes
dm discover sdd-report <run-id>                 # Sensitive data discovery report
dm discover db-report <run-id>                  # Database discovery CSV
dm discover file-report <run-id>                # File discovery report
```

### Seeds

```console
dm seeds list                                   # List all seed files
dm seeds upload ./my_seeds.csv                  # Upload a seed file
dm seeds delete my_seeds.csv                    # Delete a seed file
```

### Files

```console
dm files list snowflake-key                     # List Snowflake keys
dm files upload snowflake-key --name mykey -f key.p8  # Upload a file
dm files delete snowflake-key mykey             # Delete an uploaded file
```

### System

```console
dm system health                                # Instance health check
dm system licence                               # Licence information
dm system upload-licence ./licence.lic          # Upload a licence file
dm system logs -o logs.tar.gz                   # Download application logs
dm system admin-install --email admin@co.com    # Initial admin setup
dm system set-locality AU                       # Set system locality
```

## JSON output

Every list / get command supports `--json` for machine-parseable output:

```console
dm connections list --json | jq '.[].name'
STATUS=$(dm run status 42 --json | jq -r '.status')
dm rulesets get myruleset --json | jq -r '.yaml' > ruleset.yaml
```

JSON is also emitted automatically when:

- `stdout` is not a TTY (piped or captured),
- `DM_OUTPUT=json` is set in the environment, or
- a vendor-neutral `AI_AGENT` env var is set (e.g. by Claude Code).

Set `DM_OUTPUT=table` to force human-readable output regardless of context.

## Agent / scripting interface

For programmatic use (CI, AI coding agents, shell scripts), the CLI exposes
a discovery command and a stable error contract.

### Command catalog

`dm catalog` dumps every visible subcommand as JSON so an agent can introspect
the surface without paging through `--help` screens:

```console
dm catalog --compact   # ~1.4kB — {path, help} per command
dm catalog             # full — also includes options and arguments
```

### Structured errors

In agent mode, errors are emitted as a JSON envelope on stderr (stdout stays
empty on failure):

```json
{"error": {"code": "not_found", "message": "Connection 'foo' not found.", "hint": "Run dm connections list."}}
```

### Exit codes

| Code | Meaning           | When                                           |
| ---: | ----------------- | ---------------------------------------------- |
|    0 | success           | command completed                              |
|    1 | error             | unclassified failure                           |
|    2 | usage error       | unknown flag or missing argument (typer/click) |
|    3 | not_found         | resource lookup failed                         |
|    4 | invalid_input     | argument values rejected                       |
|    5 | ambiguous         | name matched multiple resources                |
|    6 | auth_required     | no credentials configured                      |
|    7 | auth_failed       | credentials rejected by server                 |
|    8 | conflict          | operation rejected by server state             |
|    9 | transport_error   | network or TLS failure                         |

Exit codes are stable across minor versions. The `error.code` string in the
JSON envelope mirrors these names.

## Documentation

Documentation for the DataMasque product,
including a full API reference,
can be found on the
[DataMasque portal](https://portal.datamasque.com/portal/documentation/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup,
running tests,
the release flow,
and code-style conventions.

## License

Apache License 2.0.
See [LICENSE](LICENSE).
