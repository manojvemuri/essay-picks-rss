# ADR 0002: Conservative URL and duplicate identity

- Status: Amended by ADR 0006
- Date: 2026-07-11

## Context

The same article can arrive with tracking parameters, while legitimate gift or access parameters may
be meaningful. Duplicate suppression must not rewrite historical ChatGPT selections.

## Decision

Canonicalize only HTTPS scheme and host casing, fragments, default port, and known tracking
parameters. Preserve unknown query parameters. Identify a batch from conversation ID, selection
time, source order, and canonical item fields. Preserve every valid run; suppress previously
delivered canonical URLs only when generating the RSS projection.

## Consequences

Tracking variants deduplicate predictably without guessing publisher-specific canonical URLs.
Different gift URLs may remain distinct, favoring access fidelity over aggressive deduplication.
