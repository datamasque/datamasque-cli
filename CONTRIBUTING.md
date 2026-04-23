# Contributing

Thanks for your interest in contributing to `datamasque-cli`!
Contributions, bug reports, and feature requests are all welcome.

## Reporting bugs

File an issue on the
[GitHub issue tracker](https://github.com/datamasque/datamasque-cli/issues).
Please include:

- the version of `datamasque-cli` you're using (`dm --version` or `pip show datamasque-cli`);
- the Python version and operating system;
- the command you ran (with credentials and other sensitive arguments redacted);
- the full output, including any traceback.

If the bug concerns a specific DataMasque server API response,
include the status code and (with any sensitive fields redacted) the response body.

## Feature requests

Open an issue describing what you'd like to do and why.
We're particularly interested in feedback on:

- command and flag naming;
- output formats (human-readable tables vs. `--json`);
- coverage gaps where you've had to fall back to `curl` or the Python client;
- ergonomics for CI / scripted use.

## Development setup

The project uses [uv](https://docs.astral.sh/uv/) for dependency management.
Install dependencies and set up a virtual environment:

```console
git clone https://github.com/datamasque/datamasque-cli.git
cd datamasque-cli
uv sync
```

Then either activate the venv (`source .venv/bin/activate`)
or prefix commands with `uv run`.

## Running the tests

```console
make test
```

Unit tests run entirely against mocked clients,
so no DataMasque server is required.

### Integration tests

`tests/integration/` hits a real DataMasque instance to catch the bugs unit tests can't —
ruleset namespace collisions,
delete targeting,
server-state resolution,
and the full `run start → retry → logs --follow` lifecycle.
They're excluded from `make test` and run only when you opt in.

Point them at a DataMasque you own
(your local dev instance, a throwaway VM — never a shared/prod instance)
via env vars:

```console
export DM_TEST_URL=https://localhost
export DM_TEST_USERNAME=admin
export DM_TEST_PASSWORD=secret
make test-integration
```

Or skip the typing and source credentials from your active `dm` profile:

```console
make test-integration-local
```

Tests create rulesets and connections with uuid-suffixed names (`dm_int_<hex>`)
and delete them in teardown;
a crashed run may leave stragglers,
which `dm rulesets list | grep dm_int_` and `dm connections list | grep dm_int_` will surface.

The run-lifecycle tests need a working file-source and file-destination connection on the instance.
By default they auto-detect the first `MountedShare` pair
(preferring it over S3/Azure for speed).
Override with `DM_TEST_SOURCE_CONN` / `DM_TEST_DESTINATION_CONN` env vars
if auto-detection picks the wrong ones.
Tests skip cleanly if no pair is available.

Run the integration suite before opening an MR that touches server interactions
(`commands/`, `client.py`).

## Linting and type-checking

```console
make lint     # ruff check
make format   # ruff format + import sorting
make mypy     # strict mypy on src/
make check    # all of the above plus tests
```

`mypy` runs in strict mode with `disallow_untyped_defs`.

## Code style

- **Line length:**
  120 characters.
  Enforced by `ruff format`.
- **Comments and docstrings:**
  use [semantic line breaks](https://sembr.org/) —
  break at clause boundaries, not column widths.
  This applies to text files (such as this one) as well as Python source.
- **Comment content:**
  default to writing no comments;
  add one only when the *why* is non-obvious
  (a hidden constraint, a workaround, a subtle invariant).
  Don't restate what well-named code already says.
- **Spelling:**
  British English in docs and comments,
  matching the rest of the DataMasque codebase.
- **Typing:**
  new-style generics (`list[str]`, `dict[str, int]`),
  not `List` / `Dict`.
- **Imports:**

  - All imports at the top of the file; no inline imports.
  - Absolute imports only; relative imports are not used.

- **Formatting:**
  run `make format` before committing.

## DataMasque conventions

A few project-specific conventions on top of the generic style above:

- **Function naming:**
  verb-phrase form (`execute_ruleset`, `validate_username`),
  not `ruleset_executor()`.
- **Boolean naming:**
  prefix with a modal verb — `is_`, `has_`, `can_`, `will_`, `was_` —
  e.g. `is_expired`, `has_validation_errors`, `can_retry`.
- **Acronym casing:**
  follow normal casing rules; `HttpClient`, not `HTTPClient`.
  The brand `DataMasque` is always spelled out in full.
- **No `hasattr` / `getattr` / `setattr`:**
  these bypass type checking and hide bugs until runtime.
  If you reach for them, the typing probably needs reshaping —
  a protocol, a union, or a dataclass.
- **No conditional imports:**
  always import at module top.
  `TYPE_CHECKING` is the only exception, for typing-only imports.
- **Dataclasses over dicts:**
  use a `@dataclass` (or Pydantic model) when the shape is fixed.
  Reserve `dict` for genuinely dynamic key-value data.

## Pull requests

1. Fork the repository and create a feature branch.
2. Add tests for any behavioural change.
3. Run `make check` locally before opening the PR.
4. Keep commits focused; one logical change per commit is easier to review.
5. Open a PR against `main` and describe what the change does and why.
6. The maintainers will review and either merge, request changes, or close with an explanation.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format where practical:
`feat: add dm run retry command`,
`fix: handle 401 retry for multipart uploads`,
`docs: clarify connections update semantics`,
and so on.

## Releasing

Releases are published automatically by CI when a version tag is pushed.

```console
make release-patch   # 0.1.0 → 0.1.1 — bug fixes
make release-minor   # 0.1.0 → 0.2.0 — new features
make release-major   # 0.1.0 → 1.0.0 — breaking changes
```

Each target runs `make check`,
bumps the version in `pyproject.toml`,
refreshes `uv.lock`,
commits, tags, and pushes.
CI handles the publish.

To publish manually without bumping:

```console
make publish
```

## Toolchain

| Tool                                        | Purpose                          |
|---------------------------------------------|----------------------------------|
| [uv](https://docs.astral.sh/uv/)            | Package manager                  |
| [ruff](https://docs.astral.sh/ruff/)        | Linting + formatting             |
| [mypy](https://mypy-lang.org/)              | Type checking (strict mode)      |
| [pytest](https://pytest.org/)               | Testing                          |
| [Typer](https://typer.tiangolo.com/)        | CLI framework                    |

## Project structure

```
src/datamasque_cli/
    main.py             # Typer app entry point
    client.py           # Authenticated client factory
    config.py           # Profile management (~/.config/datamasque-cli/)
    output.py           # JSON / rich table output formatting
    commands/
        auth.py         # login, logout, status, profiles
        connections.py  # list, get, create, delete
        rulesets.py     # list, get, create, delete, generate, validate
        ruleset_libraries.py  # list, get, create, delete, usage
        runs.py         # start, status, list, logs, cancel, wait
        users.py        # list, create, reset-password
        discovery.py    # schema, sdd-report, db-report, file-report
        seeds.py        # list, upload, delete
        files.py        # list, upload (Snowflake keys, Oracle wallets)
        system.py       # health, licence, logs, admin-install
```

## License

By contributing,
you agree that your contributions will be licensed under the Apache License 2.0,
the same license as the rest of the project.
