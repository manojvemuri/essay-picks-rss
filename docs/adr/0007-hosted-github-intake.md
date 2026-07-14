# ADR 0007: Hosted GitHub issue intake

- Status: Accepted
- Date: 2026-07-14

## Context

Daily publication must not depend on a user's Mac, local Chrome, browser session, or extension.
ChatGPT scheduled tasks can use connected apps, but do not expose a webhook that this repository can
poll. The publisher still must use the scheduled task's exact five selections rather than running a
second curation pipeline.

## Decision

Use one fixed repository-owner GitHub issue as the cloud handoff. The scheduled ChatGPT task updates
issue 6 with its completed response. An `issues.edited` GitHub Actions workflow copies the body as
inert data, imports it with `source_kind=github`, validates all immutable history, and commits only
managed run records and deterministic public projections. Serialize intake jobs and replay once from
the latest main branch after a non-fast-forward push.

Keep file and stdin imports permanently supported. Remove Chrome as a production source adapter.

## Consequences

Daily pickup and publishing run without a local machine. The ChatGPT account must have a GitHub app
with permission to update the fixed issue; if that action requires approval or is unavailable, the
manual import remains the recovery path. Invalid issue content cannot become a run or a commit.
