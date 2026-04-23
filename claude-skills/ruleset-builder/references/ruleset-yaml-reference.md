# Ruleset YAML Reference

Condensed reference for DataMasque ruleset YAML format.

## Top-Level Properties

```yaml
version: '1.0'                    # Required
tasks: [...]                      # Required — list of tasks
mask_definitions: [...]           # Optional — YAML anchors for masks
rule_definitions: [...]           # Optional — YAML anchors for rules
task_definitions: [...]           # Optional — YAML anchors for tasks
skip_defaults: [null, '']         # Optional — values to skip masking
imports: [...]                    # Optional — ruleset library imports
doc: "..."                        # Optional — documentation string
auto_manage_triggers: true        # Optional — auto-disable triggers during masking
```

## Task: `mask_table`

The most common task type. Masks columns in a database table.

```yaml
- type: mask_table
  table: '"SCHEMA"."TABLE"'       # Table name (Oracle quoting shown)
  key: '"ROWID"'                  # Row uniqueness key
  hash_columns:                   # Optional — deterministic masking
    - column_name
  rules:
    - column: '"COLUMN_NAME"'
      hash_columns: null          # Optional — override task-level
      skip: [null, '']            # Optional — values to skip
      masks:
        - type: imitate
```

## Task: `mask_unique_key`

Regenerates primary/unique key values. Run BEFORE `mask_table` tasks
that reference those keys.

```yaml
- type: mask_unique_key
  table: users
  key: user_id                    # The unique key column to regenerate
  format: "{[A-Z],3}{[0-9],5}"   # Format string for new values
```

## Other Task Types

- `run_sql` — execute arbitrary SQL (`sql:` parameter)
- `truncate_table` — delete all rows (`table:` parameter)
- `build_temp_table` — create temp table from SELECT (`table:`, `select:`)
- `run_data_discovery` — sensitive data discovery (no parameters)
- `run_schema_discovery` — schema discovery (no parameters)
- `parallel` — run nested `tasks:` in parallel
- `serial` — run nested `tasks:` serially

## Oracle Quoting

Oracle identifiers must be double-quoted inside single quotes:

```yaml
table: '"OPS$SVST10"."ACCOUNT"'   # Schema.Table
key: '"ROWID"'                     # Always ROWID for Oracle
column: '"ACCOUNT_ID"'             # Column name in rules
hash_columns:
  - '"CUST_ID"'                    # Column name in hash_columns
```

For PostgreSQL/MySQL, plain names work: `table: users`, `key: id`.

## Mask Types Quick Reference

### Generic
- `from_fixed` — fixed replacement value
- `from_column` — copy from another column
- `from_file` — random value from CSV seed file (>50 distinct values)
- `from_choices` — random from a small set (<50 values)
- `from_format_string` — structured pattern (e.g., `"{[A-Z],3}{[0-9],3}"`)
- `from_blob` — replace with file contents
- `from_json_path` — copy from JSON path in another column
- `secure_shuffle` — redistribute existing values randomly

### String
- `imitate` — format-preserving (letters→letters, digits→digits)
- `from_random_text` — random alphabetic string
- `transform_case` — upper/lower/title case
- `take_substring` — extract substring
- `replace_substring` — replace part of string
- `replace_regex` — regex-based replacement

### Data Pattern
- `credit_card` — valid credit card number
- `social_security_number` — valid SSN format
- `brazilian_cpf` — valid CPF number
- `set_checksum` — fix checksum after masking

### Numeric
- `from_random_number` — random in range (`min`, `max`)
- `from_random_boolean` — random true/false
- `numeric_bucket` — preserve distribution in range buckets

### Date/Time
- `from_random_date` — random date (`min`, `max`)
- `from_random_datetime` — random datetime with timestamp
- `retain_age` — preserve age, randomise date
- `retain_year` — keep year, randomise month/day
- `retain_date_component` — keep specific components

### Transformation
- `typecast` — convert data type
- `do_nothing` — skip masking (preserve value)

### Combination
- `chain` — apply masks in sequence (output of one → input of next)
- `concat` — combine multiple mask outputs (`glue:` separator)

### Unique
- `from_unique` — unique random values
- `from_unique_imitate` — unique format-preserving
  **Note:** Disallows `hash_columns`. Tables with only these rules need no hash.

### Document
- `json` — mask JSON fields within a column
- `xml` — mask XML elements within a column

## skip_defaults

Prevents masking null/empty values (saves processing time):

```yaml
skip_defaults:
  - null
  - ''
```

Can also be set per-column with `skip:`.

## Definitions (YAML Anchors)

See `mask-definitions-guide.md` for full details.

```yaml
mask_definitions:
  - &mask_email
    type: from_fixed
    value: "redacted@example.com"

tasks:
  - type: mask_table
    table: users
    key: id
    rules:
      - column: email
        masks:
          - <<: *mask_email
```

## Ruleset Libraries

See `ruleset-libraries-guide.md` for full details.

```yaml
imports:
  - namespace/library_name

tasks:
  - type: mask_table
    table: users
    key: id
    rules:
      - $ref: "namespace/library_name#database_rules/email_rule"
```
