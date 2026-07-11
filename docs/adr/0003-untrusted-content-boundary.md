# ADR 0003: Imported content is inert data

- Status: Accepted
- Date: 2026-07-11

## Context

Conversation exports can contain unrelated profile data, instructions, malformed XML, active HTML,
and prompt-injection text immediately after a valid response.

## Decision

Bind imports to one configured conversation and task marker. Size-bound the source, enumerate fenced
RSS blocks, select only an unambiguous completed response, parse only fenced XML with hardened XML
settings, and discard its suffix. Validate public HTTPS URLs syntactically without DNS or HTTP.
Sanitize editorial Markdown before persistence and auto-escape every template value.

## Consequences

Imported text never receives operational authority. Strict admission may require the user to export
or paste the response again when ChatGPT changes its output contract; the application will not guess.
