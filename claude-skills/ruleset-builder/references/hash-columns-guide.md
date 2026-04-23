# Hash Columns Guide

Hash columns enable **deterministic masking** in DataMasque.
When `hash_columns` is set on a task or rule,
rows with identical hash column values produce identical masked output.
This ensures consistency: the same customer ID always maps to the same fake name,
across all tables and across multiple runs (when using a `run_secret`).

## Syntax

### Task-level (applies to all rules in the task)

```yaml
- type: mask_table
  table: employees
  key: id
  hash_columns:
    - customer_id
  rules:
    - column: email
      masks:
        - type: imitate
    - column: phone
      masks:
        - type: imitate
```

Both `email` and `phone` are masked deterministically based on `customer_id`.

### Column-level override

```yaml
- type: mask_table
  table: employees
  key: id
  hash_columns:
    - customer_id
  rules:
    - column: email
      masks:
        - type: imitate       # Uses task-level hash (customer_id)
    - column: backup_email
      hash_columns:
        - backup_email         # Override: hash on itself
      masks:
        - type: imitate
    - column: temp_token
      hash_columns: null       # Disable: completely random
      masks:
        - type: imitate
```

Column-level `hash_columns` **completely replaces** the task-level setting (does not merge).
Set to `null` or `[]` to disable deterministic masking for that column.

### Advanced options

```yaml
hash_columns:
  - column_name: email
    case_transform: lower     # Normalise case before hashing
    trim: true                # Strip whitespace before hashing
  - column_name: metadata
    json_path: ["user", "id"] # Hash on a value inside a JSON column
  - source: self              # Hash the column on its own value
```

## How to Pick Hash Columns

### Step 1: Identify the entity

Every table belongs to a domain entity. Find the column that identifies that entity:

| Domain | Typical hash column | Examples |
|--------|-------------------|----------|
| Customer | `cust_id`, `customer_id`, `client_id` | CUST_MASTER, CUST_ADDRESS |
| Account | `acc_id`, `account_id`, `account_no` | DEP_ACCOUNT, DEP_EMAIL_ALERT |
| Card | `card_id`, `card_no` | CARD_MASTER, CARD_INSURANCE |
| Loan | `loan_id`, `loan_no` | LOAN_COLLATERAL, LOAN_GUARANTOR |
| Employee | `emp_id`, `emp_no`, `employee_id` | COM_EMPLOYEE, COM_EMP_ROLE |
| Transaction | `tx_id`, `trf_id`, `fx_tx_id` | TRF_MASTER, FX_RECEIPT |

### Step 2: Check foreign keys in the DDL

Foreign keys explicitly tell you which entity a table belongs to.
If `CARD_INSURANCE.card_id` references `CARD_MASTER.card_id`,
then `card_id` is the right hash column for `CARD_INSURANCE`.

### Step 3: For reference/lookup tables, use the PK or natural key

- Currency master → `currency` (ISO code, natural key)
- Country risk → `country_cd`
- Branch → `branch_id`
- Role → `role_id`

Prefer natural business keys over surrogate integer PKs when they exist.

### Step 4: For mapping/junction tables, use the entity FK

- Employee-role mapping → `emp_no` (the employee, not the role)
- Customer-account mapping → `cust_id`

### Step 5: Verify the column exists

Always confirm the proposed hash column actually exists in the table.
Grep the DDL or check the discovery CSV. Column name assumptions
based on conventions can be wrong (e.g., `user_id` might actually be `emp_no`).

## When NOT to Use Hash Columns

### Tables with only `from_unique_imitate` rules

`from_unique_imitate` **disallows** `hash_columns` entirely.
If every rule in a task uses `from_unique_imitate`,
do not add `hash_columns` to that task. It will fail validation.

### Audit/log tables

Tables like `COM_AUDIT_LOG` or `COM_LOGIN_LOG` are point-in-time records.
If there's no meaningful entity FK (just a sequence PK),
deterministic masking adds processing overhead with no consistency benefit.
However, if the table has a `user_id` or `emp_no`, it may still make sense.

### Content/editorial tables

Tables like `COM_NOTICE` with free-text content and only a sequence PK
have no meaningful consistency relationship. Skip hash_columns.

### Never use ROWID

Oracle's `ROWID` is used as the masking `key` but must never be a `hash_columns` value.
ROWIDs are physical row addresses that change between database instances.

## Cross-Table Consistency

The main value of hash_columns is cross-table consistency.
If `customer_id = 42` maps to "Jane Smith" in `CUST_MASTER`,
then `customer_id = 42` in `CUST_ADDRESS` also maps to "Jane Smith"
— provided both tasks use `hash_columns: [customer_id]`
and the same `run_secret`.

For this to work:
1. Use the same hash column name across related tables
2. Use a `run_secret` on the masking run for consistency across runs
3. Use the same mask definition (via anchors or library refs) across tables
