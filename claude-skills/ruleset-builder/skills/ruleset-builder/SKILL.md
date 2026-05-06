---
name: ruleset-builder
description: Use when the user wants to turn auto-generated DataMasque rulesets into production-ready ones — extract a `ruleset_library`, add `hash_columns`, refine a ruleset, or clean up generated YAML. Triggers on "ruleset builder", "build ruleset", "refine ruleset", "add hash columns", "add ruleset library", "production ruleset", "clean up ruleset".
argument-hint: e.g. "build a ruleset from these generated files"
user-invocable: true
---

# Ruleset Builder

Transform auto-generated DataMasque rulesets into production-ready rulesets with three improvements:
1. **`ruleset_library` references** — `$ref` links replacing every repeated inline mask
2. **`hash_columns`** — on every applicable `mask_table` task for deterministic consistency
3. **Clean structure** — `skip_defaults`, no doc blocks, validated

FK cascade is automatic: mask the parent PK with `imitate_unique` (or `imitate_uuid` / `imitate_nz_ird`) and the engine replicates the rule onto every FK column referencing it. **Do NOT add explicit rules for FK columns.** Avoid `from_unique_imitate` and `mask_unique_key` (both deprecated). Never skip IDs.

5-step process (1–5). Use `TaskCreate` to track all 5; report after each step before proceeding. The prompt must include business domain and application type — ask if missing.

---

## Step 1: Report versions

Report the Ruleset Builder version (from `plugin.json`) and `dm version` so the operator can correlate output with releases.

---

## Step 2: Read reference docs

Canonical mask reference:
<https://portal.datamasque.com/portal/documentation/latest/masking-functions-overview.html>

Read all of these before any other work:
```
${CLAUDE_PLUGIN_ROOT}/skills/ruleset-builder/references/fk-cascade.md
${CLAUDE_PLUGIN_ROOT}/skills/ruleset-builder/references/mask-definitions-guide.md
${CLAUDE_PLUGIN_ROOT}/skills/ruleset-builder/references/hash-columns-guide.md
${CLAUDE_PLUGIN_ROOT}/skills/ruleset-builder/references/ruleset-yaml-reference.md
```

---

## Step 3: Extract ruleset_library

Write a Python script using `ruamel.yaml` (`uv pip install ruamel.yaml`).

Process the input YAML. For each `mask_table` task, replace every inline mask with a `$ref` to a rule in `ruleset_library.yaml`. Build the library progressively — read its current state at the start of each iteration, create it if absent.

The library `masks` section structure:
```yaml
version: "1.0"
masks:
  rule_name:
    type: rule_type
    ...params
```

### Classification rules (apply in order)

**1. ID columns** — any column ending in `_ID`, `_NO`, `_NR`, `_NBR` is an entity identifier.
- **FK side: drop the rule entirely.** If an ID column is a foreign key (the table's `Foreign Keys` metadata in the discovery CSV has an entry for it), do NOT emit a rule for it. The engine cascades automatically from the parent PK rule. See `fk-cascade.md`.
- **PK side: use `imitate_unique` with `seed:`.** Strip adjective/verb prefixes before the noun: `PREVIOUS_`, `OLD_`, `TRANSFERRED_`, `PRIOR_`, `CURR_`, `NEW_`, `NEXT_`, `ALT_`, `PARENT_`, `CHILD_`, `SOURCE_`, `TARGET_`, `ORIG_`, `PENDING_`, `ARCHIVED_`, `DELETED_`. Extract the core entity (`PREVIOUS_INVOICE_ID` → `invoice`).
- Library entry name: `{entity}_id`. Reference it as `$ref: "Global/RuleLib#masks/{entity}_id"`.
- Library entry body: `type: imitate_unique`, `seed: "{entity}"`. The `seed` is optional but recommended: it namespaces by entity so unrelated IDs don't collide (e.g. `customer.id=42` doesn't mask to the same value as `product.id=42`). Doesn't affect FK cascade.
- This overrides whatever mask was originally generated (even `from_random_number`).

**2. Named patterns** — detect by mask structure:

| Pattern         | Detection                                                                                                                                           | Library rule           |
|-----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|------------------------|
| Email           | `chain(concat(concat(firstName+lastName, glue='.')+email_suffix)+transform_case(lower))`                                                            | `email_address`        |
| Full name       | `chain(concat(firstName+lastName, glue=' ')+take_substring)` OR plain `concat(firstName+lastName, glue=' ')` — column not containing USERNAME/LOGIN | `full_name`            |
| Username        | Same mask as full_name but column name contains USERNAME, USER_NAME, LOGIN, LOGON                                                                   | `username`             |
| First name only | `from_file` with firstNames seed                                                                                                                    | `name_first`           |
| Last name only  | `from_file` with lastNames seed                                                                                                                     | `name_last`            |
| DOB             | Column name contains DOB/BIRTH/DATE_OF_BIRTH — use `retain_age` regardless of original type                                                         | `dob`                  |
| Company         | `chain(from_file(companies)+take_substring)`                                                                                                        | `company_name`         |
| Country name    | `from_file(country_codes, seed_column=name)`                                                                                                        | `country_name`         |
| Country alpha-2 | `from_file(country_codes, seed_column=alpha_2)`                                                                                                     | `country_code_2`       |
| Country alpha-3 | `from_file(country_codes, seed_column=alpha_3)`                                                                                                     | `country_code_3`       |
| Phone/fax       | `imitate` on column name containing PHONE, TEL, FAX, MOBILE, CELL                                                                                   | `phone`                |
| Address line 1  | `from_file(addresses, seed_column=street_address)` on LINE_1/ADDRESS_LINE_1 columns                                                                 | `address_line1`        |
| Address line N  | Same for LINE_2, LINE_3 etc.                                                                                                                        | `address_lineN`        |
| Address full    | `from_file(addresses, seed_column=street_address)` on non-line-numbered columns                                                                     | `address_full`         |
| Address expr    | `concat(address+city+state+postcode, glue=', ')`                                                                                                    | `network_address_expr` |
| City            | `from_file(addresses, seed_column=city)`                                                                                                            | `city`                 |
| Postcode        | `from_file(addresses, seed_column=postcode)`                                                                                                        | `post_code`            |
| Suburb          | `from_file(addresses, seed_column=suburb)`                                                                                                          | `suburb`               |
| Occupation      | `from_file(occupations)`                                                                                                                            | `occupation`           |

**3. Remaining** — group by column name concept. Where column names share a root (e.g., `RESULT3_VALUE`, `RESULT5_VALUE` → `result_value`; `GENERAL_2`, `GENERAL_6` → `general`), use one shared rule. Strip adjective prefixes. Use first occurrence's parameters.

- `imitate_unique` (non-ID cols) → `{col_group}: type: imitate_unique, seed: "{col_group}"` (seed recommended for namespacing; see ID columns section).
- `from_random_date` → `{col_group}: type: from_random_date, min/max from first occurrence`
- `from_random_number` → `{col_group}: type: from_random_number, min/max from first occurrence`
- String catch-all → `{col_group}: type: imitate_unique, seed: "{col_group}"` (use `imitate` only for types `imitate_unique` can't handle, e.g. datetime, bool).
- Complex chains → keep structure, group by column name

### Output format

`Global/RuleLib` below is a placeholder for `<namespace>/<library_name>` — substitute the operator's real values, and create the library with `dm libraries create` before running the ruleset.

```yaml
version: '1.0'
skip_defaults:
  - ''
  - null
imports:
  - Global/RuleLib

tasks:
  - type: mask_table
    table: '"SCHEMA"."TABLE"'
    key: '"ROWID"'
    rules:
      - column: '"FIRST_NAME"'
        masks:
          - $ref: "Global/RuleLib#masks/name_first"
```

Do NOT write a custom YAML serializer. Use `ruamel.yaml` round-trip dumper. Use `DoubleQuotedScalarString` for `$ref` values.

**Report:** "Step 3 done — extracted N rule library definitions: [list each name and usage count]."

---

## Step 4: Add hash_columns

Write a Python script that:

**Parse the discovery CSV** (comma-separated):
`Selected`, `Table schema`, `Table name`, `Column name`, `Data Type`, `Constraint`, `Foreign Keys`, `Max Length`, `Numeric Precision`, `Numeric Scale`, `Reason for flag`, `Flagged by`, `Data classifications`

Build a lookup of `(schema, table)` → columns with constraint and FK metadata:
- `Constraint` patterns: `Primary(COL)`, `Unique(COL)`, `Foreign(COL)`
- `Foreign Keys` JSON: `["FK_NAME", "SCHEMA.TABLE.COLUMN"]` — index 1 gives the referenced table

**For each `mask_table` task:**

1. **Pick hash column** using this priority:
   - **Parent-entity FK first**: find FK columns where the referenced table is the parent of the current table — i.e., the current table name *starts with* the referenced table name (e.g., `ACCOUNT_HISTORY` starts with `ACCOUNT` → use `ACCOUNT_ID`). This avoids choosing lookup-table FKs (e.g., don't choose `ACCOUNT_TYPE_ID` in `ACCOUNT` just because it has a FK).
   - **PK fallback**: if no parent-entity FK found, use the Primary Key column (never `ROWID`)
   - **Archive table fallback**: if no PK in the CSV (archive tables `_A`, `_A_R`, `_R` often lack explicit keys), strip the suffix and look up the base table recursively
   - **Composite PKs**: prefer `*_ID` or `*_NO` columns; deduplicate derivatives (`ACCOUNT_ID` + `PREVIOUS_ACCOUNT_ID` → keep `ACCOUNT_ID`)
   - **Skip** if no suitable column found

2. Insert `hash_columns: ["COLUMN_NAME"]` after the `key:` field

3. Verify all rules in output are `$ref` — fix any remaining inline masks

4. Write to output file

**Report:** "Step 4 done — added hash_columns to N tables, skipped M (all-unique), skipped K (no suitable key). Top hash columns: [column → count]."

---

## Step 5: Validate and clean up

Remove any comment lines containing `ROWID`.

Run `dm rulesets validate --file <output_file> --type database`
(use `file` for file-masking rulesets).

Fix any errors and re-validate until passing.

---

## Summary

| Metric                     | Value          |
|----------------------------|----------------|
| Total tables               | N              |
| Mask definitions extracted | N (list names) |
| Tables with hash_columns   | N              |
| Tables skipped (no key)    | N              |
| Validation                 | passed/failed  |
| Output file                | path           |
