from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Never

import typer

from essay_picks.config import AppConfig, load_config
from essay_picks.errors import ConfigFailure, EssayPicksError, ValidationFailure
from essay_picks.models import SourceEnvelope, SourceKind
from essay_picks.publisher import publish_export
from essay_picks.repository import load_status
from essay_picks.service import IngestionService

app = typer.Typer(
    no_args_is_help=True,
    rich_markup_mode="markdown",
    help="Import ChatGPT's five selected essays and publish deterministic RSS/HTML.",
)

CONFIG_OPTION = Annotated[
    Path,
    typer.Option("--config", exists=True, dir_okay=False, help="Application YAML configuration."),
]


@app.command()
def ingest(
    config_path: CONFIG_OPTION = Path("config.yaml"),
    file: Annotated[
        Path | None,
        typer.Option("--file", exists=True, dir_okay=False, help="Conversation export Markdown."),
    ] = None,
    from_stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read the latest assistant response from standard input."),
    ] = False,
    source_kind: Annotated[
        SourceKind,
        typer.Option("--source-kind", help="Transport provenance for standard-input imports."),
    ] = SourceKind.STDIN,
    observed_conversation_id: Annotated[
        str | None,
        typer.Option("--observed-conversation-id", help="Conversation ID observed by Chrome."),
    ] = None,
    message_id: Annotated[
        str | None,
        typer.Option("--message-id", help="Concrete ChatGPT assistant message ID for Chrome."),
    ] = None,
) -> None:
    """Import one exported conversation or pasted assistant response."""
    if (file is None) == (not from_stdin):
        raise typer.BadParameter("Choose exactly one of --file or --stdin")
    config = _load(config_path)
    if file is not None:
        if file.stat().st_size > config.limits.max_source_bytes:
            raise typer.BadParameter("Source file exceeds the configured size limit")
        body = file.read_text(encoding="utf-8")
        effective_kind = SourceKind.EXPORT
    else:
        body = sys.stdin.read(config.limits.max_source_bytes + 1)
        effective_kind = source_kind
    if len(body.encode("utf-8")) > config.limits.max_source_bytes:
        raise typer.BadParameter("Source input exceeds the configured size limit")
    if effective_kind is SourceKind.CHROME and not config.source.chrome_enabled:
        _exit_error("Chrome ingestion is disabled in config.yaml", code="CHROME_DISABLED")

    envelope = SourceEnvelope.create(
        source_kind=effective_kind,
        expected_conversation_id=config.source.conversation_id,
        observed_conversation_id=observed_conversation_id or config.source.conversation_id,
        body=body,
        captured_at=datetime.now(UTC),
        message_id=message_id,
    )
    try:
        result = IngestionService(config).ingest(envelope)
    except ValidationFailure as exc:
        _exit_error(str(exc), code=exc.code, recovery_command=exc.recovery_command)
    except EssayPicksError as exc:
        _exit_error(str(exc), code="APPLICATION_FAILURE")
    typer.echo(result.model_dump_json(indent=2))


@app.command("status")
def show_status(config_path: CONFIG_OPTION = Path("config.yaml")) -> None:
    """Show the latest local operational result without exposing source content."""
    config = _load(config_path)
    status = load_status(config)
    typer.echo(json.dumps(status or {"code": "NEVER_RUN"}, indent=2, sort_keys=True))


@app.command()
def render(config_path: CONFIG_OPTION = Path("config.yaml")) -> None:
    """Regenerate public RSS and HTML from immutable run history."""
    config = _load(config_path)
    try:
        count = IngestionService(config).render_existing()
    except EssayPicksError as exc:
        _exit_error(str(exc), code="RENDER_FAILURE")
    typer.echo(json.dumps({"code": "SUCCESS", "runs": count}, indent=2))


@app.command()
def validate(config_path: CONFIG_OPTION = Path("config.yaml")) -> None:
    """Validate immutable history and build every projection without writing it."""
    config = _load(config_path)
    try:
        runs, artifacts = IngestionService(config).validate_existing()
    except EssayPicksError as exc:
        _exit_error(str(exc), code="VALIDATION_FAILURE")
    typer.echo(json.dumps({"code": "SUCCESS", "runs": runs, "artifacts": artifacts}, indent=2))


@app.command()
def publish(
    file: Annotated[
        Path,
        typer.Option("--file", exists=True, dir_okay=False, help="Conversation export Markdown."),
    ],
    config_path: CONFIG_OPTION = Path("config.yaml"),
) -> None:
    """Import and push from a clean disposable clone using fixed Git commands."""
    config = _load(config_path)
    if file.stat().st_size > config.limits.max_source_bytes:
        raise typer.BadParameter("Source file exceeds the configured size limit")
    try:
        result = publish_export(file.read_text(encoding="utf-8"), config)
    except EssayPicksError as exc:
        _exit_error(str(exc), code="PUBLISH_FAILURE")
    typer.echo(result.model_dump_json(indent=2))


def _load(path: Path) -> AppConfig:
    try:
        return load_config(path)
    except ConfigFailure as exc:
        _exit_error(str(exc), code="CONFIG_FAILURE")


def _exit_error(message: str, *, code: str, recovery_command: str | None = None) -> Never:
    payload = {"code": code, "message": message}
    if recovery_command:
        payload["recovery_command"] = recovery_command
    typer.echo(json.dumps(payload, indent=2), err=True)
    raise typer.Exit(code=2)
