---
name: datamasque-cli
description: Use when the user wants to interact with a DataMasque instance — start masking runs, check run status, list connections or rulesets, manage seeds, manage ruleset libraries, check system health, configure the AI Engine, or any task involving the DataMasque API. Triggers on "mask the data", "start a run", "check the run", "list connections", "list rulesets", "upload a seed", "check DataMasque health", "dm status", "ruleset library", "configure the AI Engine", "set the AI Engine URL", or any request to operate DataMasque programmatically.
argument-hint: e.g. "start a run with docx_masking on var_input_docx"
user-invocable: true
---

# DataMasque CLI

Operate a DataMasque instance via the `dm` command-line tool.

Run `dm catalog --compact` for a JSON list of every subcommand. The sections
below cover idioms the catalog can't show you.

## Output and errors

In agent mode — auto-detected when stdout is not a TTY, `AI_AGENT` is set, or
`DM_OUTPUT=json` — output is JSON on stdout, errors are JSON on stderr:

```json
{"error": {"code": "not_found", "message": "...", "hint": "..."}}
```

`error.code` is the stable identifier; branch on it rather than the message.
The set is `not_found`, `invalid_input`, `ambiguous`, `auth_required`,
`auth_failed`, `conflict`, `transport_error`, `error`. Exit code is non-zero
on any error; exit 2 specifically means a CLI usage error (unknown flag,
missing argument) from typer.

`DM_OUTPUT=table` forces human-readable output.

## Authentication

Set `DATAMASQUE_URL`, `DATAMASQUE_USERNAME`, `DATAMASQUE_PASSWORD` to auth
without saving anything (right choice for CI / one-offs). For interactive
use, `dm auth login --profile <name>` prompts and persists to
`~/.config/datamasque-cli/config.toml`. `--insecure` (on login) or
`DATAMASQUE_VERIFY_SSL=false` (per call) skip TLS verification.

## Quick start: a masking run

```bash
dm connections list                                   # find a source
dm rulesets list                                      # find a ruleset
dm run start -c <source> -r <ruleset> [-d <dest>]     # blocks until done
```

Add `--background` to return immediately with the run id, then poll with
`dm run wait <id>`, `dm run status <id>`, or `dm run logs <id> --follow`.
Pass repeated `--options key=value` for server-side knobs
(e.g. `--options batch_size=1000 --options dry_run=true`).

## Idioms and gotchas

- **Ruleset namespaces.** `database` and `file` rulesets share a name
  namespace, so `customers` can exist in both. `dm run start` reads the
  source connection's type and picks the matching ruleset automatically.
  For `get` / `create` / `delete`, pass `--type file|database` only when
  two rows share the name and you need to disambiguate.

- **File masking needs a destination.** Database masking is in-place;
  file masking writes through to a destination connection and fails
  with `invalid_input` without `--destination`.

- **`dm run start` blocks by default.** No flag needed for "wait then
  return"; use `--background` only when you genuinely want fire-and-forget.

- **`dm run report` is file-masking-only.** The CSV is one row per file
  the worker considered, with `path`, `file_size`, `file_type`, and
  `skip_reason` (e.g. "File archived with Glacier", "File type unsupported
  by data discovery", "Matched a skip filter"). Database runs don't
  produce a report — `not_found` is expected for them, and for any run
  that hasn't reached a terminal state yet.

- **`dm libraries delete` refuses to delete libraries imported by a
  ruleset.** Run `dm libraries usage <name>` first to see what depends on
  it; pass `--force` only after you've made an informed decision.

- **`dm connections update` preserves the UUID.** Use it to rotate
  passwords or change hosts without invalidating the rulesets and runs
  that already reference the connection.

- **`dm rulesets create` is also "update"** — it reads the existing
  `mask_type` from the server, so you only need `--type` for brand-new
  rulesets or to disambiguate a same-name update.

- **Discovery is a kind of run.** `dm discover schema <connection>` kicks
  off a discovery run and returns a run id. Poll with `dm run status <id>`,
  then fetch results with `dm discover schema-results <id>` /
  `sdd-report` / `db-report` / `file-report`.

- **`dm rulesets validate --file <file> --type <type>`** runs server-side
  validation without committing the ruleset. Use this before `create`
  when you want a clean failure mode for bad YAML.

- **"Build a ruleset" usually means the `ruleset-builder` skill, not
  `dm rulesets generate`.** `generate` is server-side scaffolding from a
  JSON generation request. The `ruleset-builder` skill (separate skill in
  this repo) handles the production-quality workflow — hash columns,
  library extraction, refinement — which is what users typically want.

- **Names or UUIDs, either works.** `dm connections get <x>`,
  `dm run start -c <x>`, `dm discover schema <x>`, etc. all try the name
  first and fall back to a UUID match. Prefer names for readability;
  reach for UUIDs only when names collide (rare).
