# 0001. Choose Postgres for the catalog

**Date**: 2026-08-09
**Status**: Accepted

## Context

The catalog needs one transactional source of truth.

## Decision

**Chosen option**: Option 1: Use Postgres

## Options considered

**Option 1:** Use Postgres
**Pros**: Transactional integrity.
**Cons**: One more service to run.

**Option 2:** Use SQLite
**Pros**: No server to run.
**Cons**: Weak concurrency.

## Consequences

**Positive**:
- Transactional integrity.

**Negative**:
- One more service to run.

## Rationale

See [rationale.md](rationale.md).
