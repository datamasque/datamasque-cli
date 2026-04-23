# Integration tests

Live-instance tests for `dm`.
Each test spins up a real connection or ruleset on a DataMasque admin-server,
exercises the CLI against it, and cleans up afterwards.

Unit tests run by default; these are opt-in via the `integration` marker.

## Run them

Against the instance in your current `dm auth` profile:

```bash
make test-integration-local
```

Against a specific instance (CI-friendly):

```bash
DM_TEST_URL=https://... \
DM_TEST_USERNAME=... \
DM_TEST_PASSWORD=... \
make test-integration
```

If any of the three `DM_TEST_*` vars are missing,
the suite skips with a clear message — it will not blow up mid-test.

## Optional overrides

`test_runs.py` needs a file-type source and destination connection.
By default it auto-picks the first pair from `dm connections list`,
preferring `MountedShare` over `S3` / `Azure` for speed.
Pin specific connections for CI determinism:

```bash
export DM_TEST_SOURCE_CONN=<source-name>
export DM_TEST_DESTINATION_CONN=<destination-name>
```

## How cleanup works

Each test generates a unique name (`dm_int_<uuid>`).
Cleanup runs in fixture teardown,
so a failing test still deletes its resources —
you won't leave garbage on the live instance even if pytest exits mid-suite.

## Why `fast_file_yaml` exists

The run-lifecycle tests need a full start-to-finish masking run
but don't care about the masking itself.
`fast_file_yaml` is a file ruleset whose `include` regex matches nothing,
so the run completes in seconds without touching any data.
Use it whenever you need the *lifecycle*, not the masking behaviour.
