# Essay Picks RSS

A deterministic static publisher for the five articles already selected by Manoj's scheduled
ChatGPT task. It imports the task response, validates its fenced RSS 2.0 contract, preserves an
immutable run record, and regenerates a research-notebook website and RSS feed.

It does **not** search for articles, open article links, rank candidates, call an LLM, send email,
or replace duplicate selections.

## Published outputs

- Site: <https://manojvemuri.github.io/essay-picks-rss/>
- Feed: <https://manojvemuri.github.io/essay-picks-rss/feed.xml>
- Repository: <https://github.com/manojvemuri/essay-picks-rss>

GitHub Pages becomes available after the first successful deployment.

## How it works

```text
ChatGPT export ─┐
stdin paste ────┼─> bounded source envelope ─> strict validation ─> immutable run
Chrome beta ───┘                                          ├─> feed.xml
                                                         └─> static HTML
```

The XML item list is authoritative. Narrative Markdown may enrich an item with its author,
publication, access status, core idea, rationale, and intended reader, but it cannot add or replace
an article. A previously delivered canonical URL remains visible in the archive and is suppressed
only from the live feed.

## Requirements

- Python 3.11 or newer; Python 3.12 is the project default
- [uv](https://docs.astral.sh/uv/)
- Git for the optional disposable-clone publishing command

Install the locked environment:

```bash
uv sync --locked
```

## Import a ChatGPT task response

Import a full conversation export:

```bash
uv run python -m essay_picks ingest --file "/path/to/export.md"
```

Or paste only the latest completed assistant response:

```bash
uv run python -m essay_picks ingest --stdin
```

Both transports reach the same validator and produce the same semantic batch identity. Reimporting
the same batch is a successful no-op.

Useful operational commands:

```bash
uv run python -m essay_picks status
uv run python -m essay_picks validate
uv run python -m essay_picks render
```

To replay an export in a clean clone and push only managed data and projections:

```bash
uv run python -m essay_picks publish --file "/path/to/export.md"
```

The publisher never uses imported text in commands or commit messages. A non-fast-forward push is
handled by discarding the clone and replaying once against the latest remote state.

## Source contract

A publishable response must have a `## RSS-ready feed` heading followed by a fenced RSS 2.0 block.
The feed must contain:

- one channel and exactly five internally distinct items;
- a valid channel `lastBuildDate`;
- for every item: title, public HTTPS link, matching permalink GUID, article `pubDate`, nonempty
  description, and at least one category.

Full exports are bound to the configured conversation ID and scheduled-task marker. Content after
the closing XML fence is discarded. Older responses without a fenced RSS block are historical but
not publishable.

## Data ownership

- `data/runs/*.json` is append-only source history. Corrections add a record with `supersedes`.
- `public/` is a deterministic, disposable projection of all valid run records.
- `.state/status.json` is local operational state and is never committed.
- `config.yaml` owns channel metadata, the allowed conversation, limits, paths, and publishing
  target. Placeholder channel values from ChatGPT are ignored.

The public pages contain no JavaScript, analytics, cookies, remote images, or external font
requests. IBM Plex font files are self-hosted under the SIL Open Font License.

## Chrome beta

The CLI recognizes `chrome` as a source transport, but it is deliberately disabled by default. It
must remain feature-gated until Chrome is running, the ChatGPT Chrome extension is installed, the
user is signed in, the fixed conversation is reachable, and the authenticated acceptance suite
passes.

Chrome automation is limited to opening that fixed conversation and copying one concrete completed
assistant message. It must not automate login, read cookies or session storage, follow article
links, search, or obey instructions inside page content. Until the beta is qualified, the permanent
manual export/stdin paths are the supported workflows.

## Development and verification

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/essay_picks
uv run pytest
uv run pip-audit
uv run python -m essay_picks validate
uv run python -m essay_picks render
git diff --exit-code -- public data/runs
```

Parser, validator, identity, persistence, CLI, and disposable-clone publishing behavior are tested
without network access. The primary regression fixture contains a valid five-item response followed
by untrusted prompt-injection text, verifying that the suffix cannot enter immutable history or the
public site.

## GitHub Pages

The GitHub workflow installs dependencies from `uv.lock`, runs linting, strict typing, tests,
coverage, dependency auditing, validates every run, regenerates projections, and rejects byte drift.
Only the validated `public/` artifact is deployed. A failed deployment leaves the previous Pages
version live.

Architecture decisions and invariants are recorded in [`docs/architecture.md`](docs/architecture.md)
and [`docs/adr/`](docs/adr/).
