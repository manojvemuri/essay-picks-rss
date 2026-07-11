# ADR 0005: Time and GUID semantics

- Status: Accepted
- Date: 2026-07-11

## Context

Article publication, ChatGPT selection, local ingestion, Git persistence, and Pages deployment occur
at different times. Using render time in RSS would make identical history produce different bytes.

## Decision

Preserve item `pubDate` as article time. Use channel `lastBuildDate` as ChatGPT selection time. Store
ingestion time separately in each run; Git and deployment time remain external operational events.
Require each item GUID to be an explicit permalink matching its canonicalized HTTPS link.

## Consequences

Feed rebuilds are byte-stable and article dates do not drift. Consumers receive stable identities
without invented timestamps.
