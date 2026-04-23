---
name: datamasque-cli
description: Use when the user wants to interact with a DataMasque instance — start masking runs, check run status, list connections or rulesets, manage seeds, manage ruleset libraries, check system health, or any task involving the DataMasque API. Triggers on "mask the data", "start a run", "check the run", "list connections", "list rulesets", "upload a seed", "check DataMasque health", "dm status", "ruleset library", or any request to operate DataMasque programmatically.
argument-hint: e.g. "start a run with docx_masking on var_input_docx"
user-invocable: true
---

# DataMasque CLI

Operate a DataMasque instance via the `dm` command-line tool.

## Prerequisites

The `dm` CLI must be installed. Check with:
```bash
dm version
```

If not installed, install it:
```bash
uv tool install datamasque-cli
```

## Authentication

There are two ways to authenticate:

**Option 1: Environment variables**

If `DATAMASQUE_URL`, `DATAMASQUE_USERNAME`, and `DATAMASQUE_PASSWORD` are set,
`dm` uses them automatically with no login step needed.

**Option 2: Profiles (interactive use)**

```bash
dm auth login --profile <name>  # fully interactive — prompts for URL, username, password
dm auth status        # Check current auth
dm auth use <profile> # Switch active profile
```

## Common Workflows

### 1. Start a masking run and wait for it

`dm run start` blocks until the run finishes by default. Pass `--background`
to return immediately. The CLI picks the file-type or database-type ruleset
automatically by reading the source connection's type — same-name rulesets
across the two namespaces are legitimate and get disambiguated for you.

```bash
dm connections list
dm rulesets list

dm run start \
  --connection <source-connection-name> \
  --ruleset <ruleset-name> \
  --destination <dest-connection-name>

dm run logs <run-id>
```

### 2. Monitor an existing run

```bash
dm run status <run-id>
dm run list --status running
dm run wait <run-id>
dm run logs <run-id>
dm run logs <run-id> --follow   # stream until the run hits a terminal state
dm run cancel <run-id>
dm run retry <run-id>           # re-run with the same source/ruleset/destination/options
```

Pass extra server-side knobs at start via repeatable `--options key=value`:

```bash
dm run start -c <conn> -r <ruleset> -d <dest> \
  --options batch_size=1000 --options dry_run=true
```

### 3. Manage connections

```bash
dm connections list                              # includes a source/destination role column
dm connections get <name-or-id>
dm connections create --file connection.json    # from a JSON blob
dm connections create --name <n> --type database --db-type postgres \
    --host <h> --port 5432 --database <d> --user <u> --password <p>
dm connections test <name>                       # verify reachability without starting a run
dm connections update <name> --password <new>    # rotate a field in place (preserves UUID)
dm connections delete <name>
```

### 4. Manage rulesets

DataMasque has two separate ruleset namespaces — `database` and `file` — so
the same name can exist in both. `dm rulesets create` reads the server's
stored `mask_type` when updating an existing ruleset; `--type file|database`
is required only for brand-new rulesets or when two rows share a name.
`get` / `delete` / `list` accept `--type` to disambiguate.

```bash
dm rulesets list
dm rulesets list --type file
dm rulesets get <name-or-id>
dm rulesets get <name-or-id> --type file
dm rulesets get <name-or-id> --yaml
dm rulesets create --name <name> --file ruleset.yaml
dm rulesets create --name <name> --file ruleset.yaml --type file
dm rulesets delete <name> [--type file|database]
dm rulesets generate --file request.json
dm rulesets validate --file ruleset.yaml
```

### 5. Manage ruleset libraries

```bash
dm libraries list
dm libraries get <name> [--namespace <ns>] [--yaml]
dm libraries create --name <name> --file library.yml [--namespace <ns>]
dm libraries delete <name> [--namespace <ns>] [--force]
dm libraries usage <name> [--namespace <ns>]
```

### 6. System administration

```bash
dm system health
dm system licence
dm system logs --output logs.tar.gz
dm rulesets export-bundle --output bundle.zip
dm rulesets import-bundle --file bundle.zip --yes
dm system upload-licence licence.lic
dm system admin-install --email admin@example.com --username admin
```

### 7. Seed files and uploads

```bash
dm seeds list
dm seeds upload <path-to-csv>
dm seeds delete <filename>
dm files list --type snowflake-key
dm files upload <path> --name <name> --type <type>
```

### 8. Users

```bash
dm users list
dm users create --username <name> --email <email> --password <pass> --role mask_runner
dm users reset-password --username <name> --password <new-pass>
```

### 9. Data discovery

Reports print to stdout by default. Pass `--output <path>` to write them
to disk instead.

```bash
dm discover schema <connection-name>            # start a schema-discovery run (accepts name or UUID)
dm discover schema-results <run-id>             # list schema-discovery results once the run finishes
dm discover sdd-report <run-id> --output report.csv
dm discover db-report <run-id> --output report.csv
dm discover file-report <run-id> --output report.json
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Failure |
| 2 | Authentication error |

## Global Options

- `--profile <name>` — use a specific profile
- `--json` — output as JSON

## Troubleshooting

- **"Could not connect to ..."** — instance is unreachable
- **"Authentication failed"** — wrong credentials, re-run `dm auth login`
- **Run failed** — use `dm run logs <run-id>` for details
- **Validation failed** — `dm rulesets validate` shows server error messages
- **Library import error** — check `dm libraries list`, name must match exactly
