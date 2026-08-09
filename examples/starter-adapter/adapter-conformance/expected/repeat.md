---
id: repeat
title: Repeat decision
status: accepted
date: '2026-08-09'
context:
  problem: Two nested files derive the same id from their filename stem.
decision:
  chosen: Use the one at the lower path.
why:
- Lexical order decides.
evidence:
- kind: file
  target: decisions/a/repeat.md
---

