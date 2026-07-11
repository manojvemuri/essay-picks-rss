# ADR 0006: Disposable Git persistence and Pages deployment boundaries

- Status: Accepted
- Date: 2026-07-11

## Context

Publishing from a developer's active worktree risks mixing unrelated edits with generated content.
Git durability and public Pages deployment are separate commit points.

## Decision

Production synchronization clones the current branch into a temporary directory, validates and
renders there, stages only immutable run records and public projections, uses an application-owned
commit message, and never force-pushes. A non-fast-forward discards the clone and replays once.
GitHub Actions independently validates the committed state before deploying `public/`.

## Consequences

User work remains untouched and failed validation creates no commit. A Git push can succeed while a
Pages deployment fails; in that case history is durable and the previous public artifact stays live.
