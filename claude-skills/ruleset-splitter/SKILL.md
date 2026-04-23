---
name: ruleset-splitter
description: Use when the user has a directory of DataMasque-generated ruleset YAML files (from the large-schema workflow, e.g. `20240915_012_TABLE_00098_to_TABLE_00193.yml`) and wants to either join them into one file for editing, or re-split an edited combined file back to the original filenames. Typically used alongside `ruleset-builder`. Triggers on "join ruleset files", "combine rulesets for editing", "resplit rulesets", "split back to original files", "merge these ruleset files", "combine for ruleset-builder".
argument-hint: e.g. "join these rulesets, I'll refine, then resplit after"
user-invocable: true
---

# Ruleset Splitter

Round-trip between DataMasque's many-file ruleset output and a single editable YAML.

DataMasque's large-schema ruleset generator (`/api/async-generate-ruleset/<connection>/download-rulesets/`) produces one `.yml` per chunk of tables. Filenames follow `YYYYMMDD_NNN_TABLE_X_to_TABLE_Y.yml`, one or more `mask_table` tasks per file. Editing or refining N files separately is painful; this skill joins them into one combined YAML for editing (typically via `ruleset-builder` or by hand), then re-splits back to the same filenames ready to upload.

## When to use

- User has a directory of DataMasque-generated `.yml` files they want to edit as one.
- User has a combined YAML plus a manifest from an earlier join and wants to write it back to the original files.

Do **not** use this to split an arbitrary single-file ruleset into pieces — there is no obvious right split, and the large-schema workflow does not involve that.

## Step 0: Report version

Report: **Version 1.0**

## Step 1: Pick the operation

Ask the user if unclear. Typical intents:
- "Join these files" / "combine for editing" → **Join** (Step 2).
- "Split these back" / "resplit" / "write back to the original files" → **Re-split** (Step 3).
- Round trip ("join, I'll refine, then resplit") → do Step 2 now, stop, and wait for the user to signal they have finished editing before doing Step 3.

## Step 2: Join

Using `ruamel.yaml` round-trip (`uv pip install ruamel.yaml`) so formatting, comments, and `$ref` quoting survive:

1. List `.yml` / `.yaml` files in the input directory, sorted lexicographically so task order is deterministic.
2. Read the first file. Copy its header (everything other than `tasks:` — typically `version`, `skip_defaults`, `imports`) into the combined output.
3. For each file in order, append every entry in its `tasks:` list to the combined output's `tasks:` list.
4. Build a manifest keyed by original filename, value = list of task identifiers in insertion order:
   - `mask_table` → the quoted schema + table string exactly as it appears in the YAML, e.g. `'"HR"."EMPLOYEES"'`.
   - `mask_file` → `task.path` if present, else `task.root`.
   - Ambiguous tasks → `task_{global_index}`.

Write:
- `combined.yaml` — the merged ruleset.
- `.ruleset-splitter-manifest.json` — `{"filename.yml": ["task-id-1", "task-id-2"], ...}`.

Report: "Step 2 done — joined N files into `combined.yaml`, M tasks total. Manifest written to `.ruleset-splitter-manifest.json`."

## Step 3: Re-split

Given `combined.yaml` and `.ruleset-splitter-manifest.json`:

1. Load both.
2. Build a reverse index: `task-id → original-filename`.
3. For each task in `combined.yaml`, look up its identifier and group tasks by target filename. Preserve insertion order within each file.
4. Tasks not found in the manifest (added during editing) go into `unassigned.yml` with a console warning listing them, so the user can place them manually.
5. For each target filename, write a YAML with:
   - The header copied from `combined.yaml` verbatim.
   - A `tasks:` list containing only that filename's tasks.
   Write to the **exact original filename** — do not rename.
6. Validate each output with `dm rulesets validate --file <path>`. Fix errors and re-validate until passing.

Use the `ruamel.yaml` round-trip dumper. Wrap any `$ref` values in `DoubleQuotedScalarString` so the emitter preserves quoting.

Report: "Step 3 done — wrote N files (M tasks), K unassigned. Validation: passed / failed per file."

## Summary

| Metric           | Value                       |
|------------------|-----------------------------|
| Operation        | join / resplit / round-trip |
| Input file(s)    | paths                       |
| Combined output  | path (after join)           |
| Manifest         | path                        |
| Re-split output  | N files listed              |
| Unassigned tasks | N (if any)                  |
| Validation       | passed / failed             |
