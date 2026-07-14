# Architecture and invariants

## Purpose

The publisher transports one editorial decision already made by a scheduled ChatGPT task. Discovery
and publication are separate systems: this repository implements publication only.

## Invariants

1. One publishable source response contains exactly five distinct RSS items.
2. No source adapter searches, follows article links, fetches article bodies, or substitutes items.
3. The configured ChatGPT conversation ID is the only accepted conversation boundary.
4. XML membership is authoritative; narrative Markdown can enrich but cannot alter membership.
5. A semantic batch imported through export, stdin, or GitHub intake has one identity and is stored
   once.
6. Valid runs are immutable. Corrections append a superseding run.
7. Duplicate article URLs remain in run history and are suppressed only from the RSS projection.
8. The RSS projection retains every unique delivered article and orders newest selections first.
9. Generated RSS and HTML are deterministic projections and may be deleted and rebuilt.
10. Imported data never enters filesystem paths, Git arguments, commit messages, logs, or recovery
   commands.
11. Failure before validation creates neither a run record nor a public projection.

## Data flow

`SourceEnvelope` preserves transport provenance, expected and observed conversation IDs, timestamps,
bounded response text, and an audit hash. `validate_envelope` selects one unambiguous fenced RSS
candidate, parses it with external entities disabled, validates its item contract, attaches optional
sanitized editorial metadata, and creates a `ValidatedRun`.

`RunRepository` appends that run using an atomic same-filesystem replacement. `build_projections`
constructs all HTML, RSS, CSS, and font artifacts in memory. `install_projections` swaps a complete
staging directory into `public/`, retaining a short-lived rollback directory during the operation.

## Trust boundaries

ChatGPT content and exports are untrusted input. Source parsing is size bounded, RSS-only, and
network-free. URLs must be public HTTPS destinations by syntax and IP classification without DNS
lookups. Raw HTML and images are disabled; generated HTML is auto-escaped and editorial Markdown is
allowlist-sanitized.

GitHub Actions treats committed run records as untrusted historical data: it validates them, rebuilds
the site, and compares bytes before deployment. The public site uses a CSP that disables scripts,
connections, objects, images, forms, and external resources.

The hosted intake is one fixed repository-owner issue. Its body is written to a bounded ephemeral
file without shell interpolation and enters the same network-free parser. Imported text never
controls workflow commands, paths, commit messages, or Git arguments.
