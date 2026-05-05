# FK Cascade Invariant

The most important rule when refining a DataMasque ruleset that spans
related tables. Get this wrong and you either leak identity (by skipping
IDs entirely) or break the engine (by adding rules for FK columns).

## The rule

**Mask only the parent PK column. The engine cascades the same masked value
to every FK column referencing it.**

Three masks support this cascade:

- `imitate_unique` — recommended for new work.
- `imitate_uuid` — for UUID-shaped IDs.
- `imitate_nz_ird` — for NZ IRD numbers.

(`from_unique_imitate` and `mask_unique_key` are deprecated; do not emit.)

When `mask_table` runs and a rule on a referenced column uses one of these
masks, the engine:

1. Discovers child tables with FKs referencing this column.
2. Auto-replicates the parent's rule onto every FK column.
3. Same mask config → same masked output → joins survive.

This is documented at
<https://portal.datamasque.com/portal/documentation/latest/unique-masks.html>:

> "You can apply an `imitate_unique` mask to a primary key column or a
> column that is used as a foreign key in another table. References will be
> updated automatically. Composite primary keys are supported."

## Worked example

Schema:
- `customers.id` (PK), `customers.email`
- `orders.id` (PK), `orders.customer_id` (FK → `customers.id`), `orders.tracking_number`

Correct ruleset:

```yaml
- type: mask_table
  table: customers
  key: id
  rules:
    - column: id
      masks:
        - type: imitate_unique
          seed: customer
    - column: email
      masks:
        - type: from_file
          seed_file: DataMasque_emails.csv
          seed_column: email

- type: mask_table
  table: orders
  key: id
  rules:
    # customer_id is intentionally absent — the engine replicates the
    # `customers.id` rule onto it automatically. Adding it here would
    # be rejected by the runtime FK check.
    - column: tracking_number
      masks:
        - type: imitate_unique
          seed: tracking
```

After the run, `orders.customer_id` holds the same masked values as
`customers.id`, joins remain intact, and `tracking_number` is independently
masked with its own seed.

## Anti-patterns to refuse

- **Adding explicit FK rules** ("I'll mask both PK and FK with shared
  `$ref` so the cascade works"). The runtime rejects this by default with
  the error:
  *"To preserve referential integrity, the following foreign key columns
  cannot be directly masked by this task."*
  The engine will replicate the rule for you; adding your own conflicts.
- **Skipping IDs to "preserve FK joins"**. Leaves identifiers in plain
  sight. Mask the parent PK with `imitate_unique` — joins survive via
  the auto-cascade.
- **Inventing linking parameters** (`source_table`, `source_column`,
  `parent_column`, `link_to`). None of these exist on any DataMasque mask.
- **Inventing a hashing mask** (`hash_text`, `hash`, `link`, `match_id`).
  None of these exist. `imitate_unique` is the deterministic mask.
- **Using `from_unique_imitate` or `mask_unique_key`**. Both deprecated.
  `imitate_unique` replaces both.

## Cross-run consistency requires `run_secret`

Within a single run, `imitate_unique` is deterministic via a per-run
`insecure_seed`. Across runs, the cascade only holds if the run is
invoked with a `run_secret`. Without it, the same input maps to a
different masked value next run. If cross-run consistency matters, flag
this in the final summary.

## Self-check before finishing

For each FK relationship in the schema:

1. Is the parent PK masked with `imitate_unique`, `imitate_uuid`, or
   `imitate_nz_ird`?
2. Is the FK column **absent** from your output (no explicit rule)?
3. Are `from_unique_imitate` and `mask_unique_key` absent from your output?

If any answer is "no", fix it before validation.
