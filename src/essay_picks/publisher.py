from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from essay_picks.config import AppConfig, load_config
from essay_picks.errors import PersistenceFailure
from essay_picks.models import IngestResult, SourceEnvelope, SourceKind
from essay_picks.service import IngestionService

FIXED_COMMIT_MESSAGE = "chore: publish daily essay picks"


def publish_export(source_body: str, local_config: AppConfig) -> IngestResult:
    """Replay one source body in a disposable clone and push managed outputs."""
    repository_url = local_config.publishing.repository_url
    if not repository_url:
        raise PersistenceFailure("publishing.repository_url is not configured")

    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(2):
        with tempfile.TemporaryDirectory(prefix="essay-picks-publish-") as temporary:
            clone = Path(temporary) / "repository"
            _git(
                "clone",
                "--depth",
                "1",
                "--branch",
                local_config.publishing.branch,
                repository_url,
                str(clone),
            )
            remote_config = load_config(clone / "config.yaml")
            envelope = SourceEnvelope.create(
                source_kind=SourceKind.EXPORT,
                expected_conversation_id=remote_config.source.conversation_id,
                observed_conversation_id=remote_config.source.conversation_id,
                body=source_body,
                captured_at=datetime.now(UTC),
            )
            result = IngestionService(remote_config).ingest(envelope)
            if not result.changed:
                return result

            _git("-C", str(clone), "config", "user.name", "essay-picks-rss")
            _git(
                "-C",
                str(clone),
                "config",
                "user.email",
                "41898282+github-actions[bot]@users.noreply.github.com",
            )
            _git("-C", str(clone), "add", "--", "data/runs", "public")
            _git("-C", str(clone), "commit", "-m", FIXED_COMMIT_MESSAGE)
            try:
                _git(
                    "-C",
                    str(clone),
                    "push",
                    "origin",
                    f"HEAD:{local_config.publishing.branch}",
                )
            except subprocess.CalledProcessError as exc:
                last_error = exc
                if attempt == 0:
                    continue
                break
            return result
    raise PersistenceFailure("Git push failed after one clean replay") from last_error


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")
    if executable is None:
        raise PersistenceFailure("Git executable is unavailable")
    return subprocess.run(  # noqa: S603 - arguments are fixed by application call sites.
        [executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
