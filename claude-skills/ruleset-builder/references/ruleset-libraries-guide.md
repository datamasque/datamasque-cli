# Ruleset Libraries Guide

Ruleset libraries are reusable YAML documents containing masking components
that can be imported and referenced across multiple rulesets.
Define masking logic once, reuse it everywhere.

## CLI Commands

```bash
dm libraries list                                    # List all libraries
dm libraries get <name> [--namespace <ns>] [--yaml]  # Show details or YAML
dm libraries create --name <name> --file lib.yml [--namespace <ns>]
dm libraries delete <name> [--namespace <ns>] [--force]
dm libraries usage <name> [--namespace <ns>]         # Which rulesets use it
```

## Library Structure

A library YAML file has `version: "1.0"` and up to 7 optional sections:

```yaml
version: "1.0"

# 1. Individual mask definitions
masks:
  email_mask:
    type: from_fixed
    value: "redacted@example.com"
  phone_mask:
    type: from_unique_imitate
    retain_prefix_length: 3

# 2. Complete database masking rules (column + masks)
database_rules:
  credit_card_rule:
    column: '"CARD_NO"'
    masks:
      - type: credit_card
        pan_format: true

# 3. Complete tabular file rules
tabular_file_rules:
  csv_name_rule:
    column: name
    masks:
      - type: from_file
        seed_file: DataMasque_firstNames_mixed.csv
        seed_column: firstname-mixed

# 4. File masking rules (JSON, XML)
file_rules:
  json_email_rule:
    masks:
      - type: from_fixed
        value: "masked@example.com"

# 5. Column mask lists (reusable masks list for any column)
columns:
  sensitive_text:
    masks:
      - type: from_unique_imitate
        skip_digits: true

# 6. Complete task definitions
tasks:
  cleanup:
    type: run_sql
    sql: "DELETE FROM temp_table"

# 7. Freeform constants and configuration
other:
  default_domain: "example.com"
  supported_countries: ["US", "CA", "UK"]
```

## The `$ref` Syntax

Rulesets reference library content using `$ref`:

```
$ref: "<namespace>/<library_name>#<section>/<key>"
$ref: "<library_name>#<section>/<key>"         # No namespace
$ref: "<lib>#<section>/<key>/<nested_key>"     # Nested access
$ref: "<lib>#<section>/0"                      # Array index
```

### Example: Ruleset using a library

```yaml
version: "1.0"
imports:
  - pii/customer_masks

tasks:
  - type: mask_table
    table: customers
    key: id
    rules:
      # Reference a complete rule (column + masks)
      - $ref: "pii/customer_masks#database_rules/credit_card_rule"

      # Reference just a mask within a rule
      - column: email
        masks:
          - $ref: "pii/customer_masks#masks/email_mask"

      # Reference a column mask list
      - column: notes
        $ref: "pii/customer_masks#columns/sensitive_text"
```

### Internal references (within a library)

Libraries can reference their own content with `#` (no library name):

```yaml
version: "1.0"
masks:
  base_name:
    type: from_file
    seed_file: DataMasque_firstNames_mixed.csv
    seed_column: firstname-mixed

database_rules:
  name_rule:
    column: first_name
    masks:
      - $ref: "#masks/base_name"    # References own masks section
```

## The `imports` Block

Every library referenced via `$ref` must be declared in `imports`:

```yaml
version: "1.0"
imports:
  - pii/customer_masks
  - common/date_masks

tasks: [...]
```

## Libraries vs YAML Anchors

| Feature | YAML Anchors (`&`/`*`) | Libraries (`$ref`) |
|---------|----------------------|-------------------|
| Scope | Within one ruleset | Across multiple rulesets |
| Management | Inline in YAML | Managed via API/CLI, versioned |
| Syntax | `<<: *anchor_name` | `$ref: "lib#path"` |
| Override | `<<:` merge key | Not supported (use as-is) |
| Best for | Single-ruleset reuse | Organisation-wide standards |

**Recommendation:**
- Start with YAML anchors (`mask_definitions`) for within-ruleset deduplication
- Promote to a library when the masks should be shared across rulesets
  or managed independently by a team

## Limitations

- Libraries **cannot import other libraries** (no cross-library `$ref`)
- `$ref` cannot be used for `type` fields (mask type, task type)
- Libraries do **not** support locality interpolation (`{{ locality }}`)
- You cannot append items to a referenced array
- Libraries are not supported for in-flight masking
