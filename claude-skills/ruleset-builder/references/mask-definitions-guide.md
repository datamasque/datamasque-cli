# Mask Definitions Guide

YAML anchors and aliases let you define a mask once and reuse it
throughout a ruleset. DataMasque provides three definition sections
for organising these: `mask_definitions`, `rule_definitions`, and `task_definitions`.

## YAML Anchor Syntax

```yaml
# Define an anchor with &
mask_definitions:
  - &mask_email
    type: from_fixed
    value: "redacted@example.com"

# Reference with *
tasks:
  - type: mask_table
    table: users
    key: id
    rules:
      - column: email
        masks:
          - <<: *mask_email           # Inherit all properties

      - column: backup_email
        masks:
          - <<: *mask_email           # Inherit and override
            value: "backup@example.com"
```

The `<<:` merge key inherits all properties from the anchor
and lets you override specific ones.

## Three Definition Levels

### `mask_definitions` — reusable masks

Each entry defines a single mask (the content inside a `masks:` list item):

```yaml
mask_definitions:
  - &mask_ssn
    type: social_security_number
  - &mask_phone
    type: from_format_string
    format: "+1-{[0-9],3}-{[0-9],3}-{[0-9],4}"
  - &mask_dob
    type: from_random_date
    min: '1950-01-01'
    max: '2005-12-31'
```

### `rule_definitions` — reusable rules (column + masks)

Each entry defines a complete rule including the target column:

```yaml
rule_definitions:
  - &rule_postcode
    column: postcode
    masks:
      - type: from_random_number
        min: 1000
        max: 9999
```

Use when the same column name appears across many tables:

```yaml
tasks:
  - type: mask_table
    table: customers
    key: id
    rules:
      - <<: *rule_postcode
      - column: email
        masks:
          - <<: *mask_email

  - type: mask_table
    table: orders
    key: id
    rules:
      - <<: *rule_postcode
        column: delivery_postcode   # Override the column name
```

### `task_definitions` — reusable tasks

Each entry defines a complete task:

```yaml
task_definitions:
  - &customer_task
    type: mask_table
    table: PLACEHOLDER
    key: id
    hash_columns:
      - customer_id
    rules:
      - column: email
        masks:
          - <<: *mask_email
      - column: phone
        masks:
          - <<: *mask_phone

tasks:
  - <<: *customer_task
    table: customers
  - <<: *customer_task
    table: archived_customers
```

## Common Patterns

### Naming convention

Use `&mask_<category>` for masks, `&rule_<column>` for rules:

```yaml
mask_definitions:
  - &mask_email         # Email addresses
  - &mask_ssn           # Social security numbers
  - &mask_phone         # Phone / tel / fax
  - &mask_card          # Credit/debit card numbers
  - &mask_name_first    # First names
  - &mask_name_last     # Last names
  - &mask_addr          # Street addresses
  - &mask_dob           # Date of birth
  - &mask_company       # Company names
  - &mask_country       # Country codes
  - &mask_occupation    # Job titles / occupations
```

### Start specific, then merge related

1. Create per-field definitions for `imitate` rules:
   `&mask_phone_no`, `&mask_tel`, `&mask_fax`
2. Review and merge where the mask logic is identical:
   `&mask_phone` replaces all three
3. Keep separate only when tuning differs
   (e.g., `&mask_addr` vs `&mask_postal_addr` if formats differ)

### Dictionary-style rules for easy overriding

Instead of a list, rules can be a dictionary with arbitrary keys:

```yaml
task_definitions:
  - &base_task
    type: mask_table
    table: PLACEHOLDER
    key: id
    rules:
      postcode: *rule_postcode
      email: *rule_email
      phone: *rule_phone

tasks:
  - <<: *base_task
    table: customers
    rules:
      <<: *base_task_rules
      postcode:                    # Override just the postcode rule
        column: zip_code
        masks:
          - type: from_random_number
            min: 10000
            max: 99999
```

## Available Seed Files

Common seed files for `from_file` masks:

| Category | Files |
|----------|-------|
| Names | `DataMasque_firstNames_mixed.csv`, `DataMasque_lastNames_v2.csv` |
| Addresses | `DataMasque_US_addresses.csv`, `DataMasque_AU_addresses_real.csv`, `DataMasque_NZ_addresses_real.csv` |
| Companies | `DataMasque_companies.csv`, `DataMasque_NZ_companies.csv`, `DataMasque_AU_companies.csv` |
| Email | `DataMasque_fake_email_suffixes.csv`, `DataMasque_email_suffixes.csv` |
| Reference | `DataMasque_country_codes.csv`, `DataMasque_occupations.csv` |
| Cards | `DataMasque_credit_card_numbers.csv`, `DataMasque_credit_card_prefixes.csv` |

Regional variants exist for BR, IN, AU, NZ, US.
Use `from_file` when there are more than ~50 distinct values;
use `from_choices` for fewer.
