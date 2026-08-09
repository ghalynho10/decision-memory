# 0001. Choose Postgres for the catalog

## Context

The catalog needs one transactional source of truth.

## Options considered

**Option 1:** Use Postgres
**Pros**: Transactional integrity.
**Cons**: One more service to run.

**Option 2:** Use SQLite
**Pros**: No server to run.
**Cons**: Weak concurrency.

## Rationale

Postgres gives transactional integrity the team already knows.
