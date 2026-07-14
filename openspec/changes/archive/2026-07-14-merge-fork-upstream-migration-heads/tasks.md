## 1. Migration graph

- [x] 1.1 Add a no-op Alembic revision joining the fork observability head and upstream model-registry head.
- [x] 1.2 Confirm Alembic reports exactly one head and upgrades databases from either parent.

## 2. Validation

- [x] 2.1 Run the migration unit and integration suites.
- [x] 2.2 Run repository-wide tests, Ruff, ty, and OpenSpec validation.
