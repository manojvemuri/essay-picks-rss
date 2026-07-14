# ADR 0008: One-time normalized legacy backfill

- Status: Accepted
- Date: 2026-07-14

## Context

Four scheduled responses from July 6–9 predate the RSS output contract but are present in the
original conversation export with exact titles, article dates, canonical links, descriptions, and
ChatGPT response timestamps. Omitting them would make the historical archive incomplete.

## Decision

Normalize those four five-item responses into RSS-shaped migration inputs and import them with
`source_kind=legacy`. Use only facts and URLs present in the export. Mark categories as `Historical
Backfill` instead of inferring topical metadata. Resolve the visible America/Chicago response times
to UTC. Do not import the earlier ad-hoc manual response as a scheduled run.

## Consequences

The archive contains all seven scheduled five-item runs available in the supplied conversation.
Repeated selections remain visible in their original runs and are emitted only once in RSS. The
legacy normalizer is not part of daily production ingestion and performs no network access.
