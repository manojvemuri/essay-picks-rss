# ADR 0006: Append-only RSS delivery projection

- Status: Accepted
- Date: 2026-07-14

## Context

The feed is a durable reading archive, not a rolling notification window. Removing older items when
a configurable limit is reached would make previously delivered selections disappear from RSS even
though their immutable runs still exist.

## Decision

Generate RSS from every unique canonical article in immutable run history. Order items by newest
ChatGPT selection first. Preserve repeated selections in the HTML archive, but emit each canonical
article only once in RSS using its earliest delivery record.

## Consequences

New runs append durable feed history without deleting older items. Feed size grows over time; this
is intentional and can later be complemented by paginated archival feeds without changing the
primary feed's append-only contract.
