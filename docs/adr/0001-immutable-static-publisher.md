# ADR 0001: Immutable static publisher

- Status: Accepted
- Date: 2026-07-11

## Context

The scheduled ChatGPT task already performs discovery and selection. Repeating curation in a second
system would create conflicting picks, extra cost, and an unclear source of truth.

## Decision

Use a Python command-line application with immutable JSON run records and deterministic RSS/HTML
projections. Keep both permanent manual inputs and a feature-gated local Chrome adapter. Host the
projections on GitHub Pages with no runtime backend or database.

## Consequences

Publication is reproducible, reviewable in Git, and inexpensive to host. Automatic ingestion depends
on a signed-in local browser and therefore remains beta; manual import is always available. The
system intentionally cannot repair an incomplete source response by finding substitute articles.
