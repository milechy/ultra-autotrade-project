# Manual DDL Scripts

This directory holds raw SQL scripts intended for **manual execution** on
staging-new and production via `psql -f`.

## Why both Alembic *and* raw SQL?

Per [`docs/ops/02_db_tables.md`](../../../docs/ops/02_db_tables.md), Ultra
AutoTrade does **not** auto-run Alembic on production deployment. Schema
changes are applied by hand on Hetzner using `ALTER TABLE` / `CREATE TABLE`
statements before the new code is rolled out.

To keep the repo consistent we still write each schema change as both:

1. an Alembic revision (`backend/alembic/versions/<hash>_<name>.py`) — so
   `alembic upgrade head` works in the local dev container and CI
2. a hand-runnable SQL script (`backend/alembic/sql/<NNN>_<name>.sql`) — what
   the operator actually pastes into `psql` on Hetzner

Both files describe the **same DDL**. Run only one of them per environment.

## Scripts

| File | Alembic revision | Purpose |
|------|------------------|---------|
| `045_fee_v10_tables.sql` | `d4e5f6a7b8c9_fee_v10_tables.py` | Drop v9 billing tables (`fee_configs`, `fee_calculations`, `high_water_marks`) and create v10 (`fee_configs`, `fee_transactions`). See [Asana F-1](https://app.asana.com/0/1213741124336104/1214120248239215) and [`docs/45_fee_model_v10_migration_plan.md`](../../../docs/45_fee_model_v10_migration_plan.md). |

## Execution order

1. **staging-new** — applied during F-1 (this PR) for verification.
2. **production** — applied during F-16 (release) only after F-2 through F-15
   are merged and approved.

## Pre-flight (always run before each environment)

```bash
docker exec ultra-autotrade-postgres-<env> psql -U ultra -d <db> -c "
SELECT table_name, (SELECT COUNT(*) FROM information_schema.tables t2
                    WHERE t2.table_name = t.table_name)
FROM (VALUES ('fee_configs'),('fee_calculations'),('high_water_marks'),
              ('fee_transactions')) AS t(table_name);
"
```

The 045 DROP statements assume the v9 tables are **0 rows**. F-0 confirmed
this for production on 2026-04-25; reconfirm immediately before applying.

## Apply

```bash
# staging-new
docker exec -i ultra-autotrade-postgres-staging-new \
  psql -U ultra -d ultra_autotrade_staging \
  < backend/alembic/sql/045_fee_v10_tables.sql

# production (F-16 only)
docker exec -i ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  < backend/alembic/sql/045_fee_v10_tables.sql
```

## Rollback

Each SQL script ends with a commented-out rollback block. Uncomment and run
only if the post-deploy verification fails. v9 billing data is **not**
restorable (production was 0 rows at the cutover).

## Why v10 models live in a separate Base

`backend/app/billing/v10_models.py` uses its own `V10Base` because the v10
table names (`fee_configs`, `fee_transactions`) collide with the still-present
v9 classes in `backend/app/billing/models.py`. F-13 will delete the v9 module
and merge the v10 classes into `app.billing.models` under the regular
`app.database.Base`.
