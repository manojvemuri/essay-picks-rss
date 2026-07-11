from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from filelock import FileLock

from essay_picks.errors import PersistenceFailure, ValidationFailure
from essay_picks.models import OutcomeCode, SourceEnvelope, SourceKind
from essay_picks.service import IngestionService


def test_ingest_is_idempotent_and_writes_deterministic_projections(
    app_config, corrupt_export: str, project_root: Path
) -> None:
    envelope = SourceEnvelope.create(
        source_kind=SourceKind.STDIN,
        expected_conversation_id=app_config.source.conversation_id,
        observed_conversation_id=app_config.source.conversation_id,
        body=corrupt_export,
        captured_at=datetime(2026, 7, 11, 16, 0, tzinfo=UTC),
    )
    service = IngestionService(app_config)

    first = service.ingest(envelope)
    second = service.ingest(envelope)

    assert first.code is OutcomeCode.SUCCESS
    assert first.imported_items == 5
    assert first.new_feed_items == 5
    assert second.code is OutcomeCode.NO_CHANGE
    assert second.changed is False
    assert len(list((project_root / "data" / "runs").glob("*.json"))) == 1
    feed = (project_root / "public" / "feed.xml").read_text(encoding="utf-8")
    index = (project_root / "public" / "index.html").read_text(encoding="utf-8")
    assert feed.count("<item>") == 5
    assert "research notebook" in index.lower()
    assert "Ignore prior instructions" not in index


def test_lock_contention_returns_retryable_result(app_config, corrupt_export: str) -> None:
    envelope = SourceEnvelope.create(
        source_kind=SourceKind.STDIN,
        expected_conversation_id=app_config.source.conversation_id,
        observed_conversation_id=app_config.source.conversation_id,
        body=corrupt_export,
    )
    lock = FileLock(app_config.paths.lock)
    with lock:
        result = IngestionService(app_config).ingest(envelope)
    assert result.code is OutcomeCode.RETRYABLE
    assert result.retryable is True


def test_validation_failure_records_status(app_config) -> None:
    envelope = SourceEnvelope.create(
        source_kind=SourceKind.STDIN,
        expected_conversation_id=app_config.source.conversation_id,
        observed_conversation_id=app_config.source.conversation_id,
        body="no feed",
    )
    with pytest.raises(ValidationFailure):
        IngestionService(app_config).ingest(envelope)
    assert "INVALID" in app_config.paths.status.read_text(encoding="utf-8")


def test_projection_failure_preserves_run_and_reports_recovery(
    app_config, corrupt_export: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    envelope = SourceEnvelope.create(
        source_kind=SourceKind.STDIN,
        expected_conversation_id=app_config.source.conversation_id,
        observed_conversation_id=app_config.source.conversation_id,
        body=corrupt_export,
    )

    def fail_install(*_args) -> None:
        raise PersistenceFailure("simulated install failure")

    monkeypatch.setattr("essay_picks.service.install_projections", fail_install)
    with pytest.raises(PersistenceFailure):
        IngestionService(app_config).ingest(envelope)

    assert len(list(app_config.paths.runs.glob("*.json"))) == 1
    status = app_config.paths.status.read_text(encoding="utf-8")
    assert "PUBLISH_FAILURE" in status
    assert "python -m essay_picks render" in status
