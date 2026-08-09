---
id: valid
title: Use Postgres for the catalog
status: accepted
date: '2026-08-09'
context:
  problem: The catalog needs one transactional source of truth.
decision:
  chosen: Use Postgres for the catalog.
why:
- It is transactional
- The team knows it well
evidence:
- kind: file
  target: decisions/valid.md
---

