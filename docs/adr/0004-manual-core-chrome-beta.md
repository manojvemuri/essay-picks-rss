# ADR 0004: Permanent manual core and feature-gated Chrome beta

- Status: Accepted
- Date: 2026-07-11

## Context

Automatic access to the scheduled task depends on a local signed-in browser, an extension, changing
ChatGPT UI structure, and response completion timing.

## Decision

Keep file and stdin ingestion permanently supported. Treat Chrome as a thin source adapter that may
only copy one completed assistant response from the fixed conversation. Leave it disabled until the
signed-in acceptance suite passes, then use bounded local attempts at 10:30, 11:00, and noon in
America/Chicago.

## Consequences

The deterministic publisher remains useful when UI automation fails. Chrome can add convenience
without becoming a second parser, curator, credential store, or sole recovery path.
