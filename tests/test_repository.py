from __future__ import annotations

from datetime import UTC, datetime

import pytest

from essay_picks.errors import PersistenceFailure
from essay_picks.extract import validate_envelope
from essay_picks.models import SourceEnvelope, SourceKind
from essay_picks.repository import RunRepository, load_status


def validated_run(app_config, corrupt_export: str):
    envelope = SourceEnvelope.create(
        source_kind=SourceKind.EXPORT,
        expected_conversation_id=app_config.source.conversation_id,
        observed_conversation_id=app_config.source.conversation_id,
        body=corrupt_export,
        captured_at=datetime(2026, 7, 11, 16, 0, tzinfo=UTC),
    )
    return validate_envelope(envelope, app_config)


def test_repository_queries_and_duplicate_guard(app_config, corrupt_export: str) -> None:
    repository = RunRepository(app_config)
    run = validated_run(app_config, corrupt_export)
    repository.save(run)

    assert repository.contains(run.batch_id)
    assert repository.validate() == 1
    assert repository.delivered_urls() == {item.canonical_url for item in run.items}
    with pytest.raises(PersistenceFailure, match="already exists"):
        repository.save(run)


def test_repository_rejects_corrupt_immutable_record(app_config) -> None:
    path = app_config.paths.runs / "2026-07-11-bad.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(PersistenceFailure, match="Invalid immutable run"):
        RunRepository(app_config).all_runs()


@pytest.mark.parametrize("content", ["not json", "[]"])
def test_load_status_rejects_invalid_state(app_config, content: str) -> None:
    app_config.paths.status.parent.mkdir(parents=True, exist_ok=True)
    app_config.paths.status.write_text(content, encoding="utf-8")
    with pytest.raises(PersistenceFailure, match="status"):
        load_status(app_config)
