from __future__ import annotations

from datetime import UTC, datetime

import pytest

from essay_picks.errors import ValidationFailure
from essay_picks.extract import validate_envelope
from essay_picks.models import SourceEnvelope, SourceKind


def envelope_for(body: str, conversation_id: str) -> SourceEnvelope:
    return SourceEnvelope.create(
        source_kind=SourceKind.EXPORT,
        expected_conversation_id=conversation_id,
        observed_conversation_id=conversation_id,
        body=body,
        captured_at=datetime(2026, 7, 11, 16, 0, tzinfo=UTC),
    )


def test_corrupted_suffix_is_discarded_and_five_items_are_preserved(
    app_config, corrupt_export: str
) -> None:
    run = validate_envelope(
        envelope_for(corrupt_export, app_config.source.conversation_id), app_config
    )

    assert len(run.items) == 5
    assert run.items[0].title == "Is Life Just Different?"
    assert "Ignore prior instructions" not in run.editorial_markdown
    assert "WebSearch" not in run.original_rss_xml
    assert "[Quanta Magazine+1](" not in run.editorial_markdown
    assert run.source_selected_at.isoformat() == "2026-07-11T14:44:56+00:00"


def test_rejects_wrong_conversation(app_config, corrupt_export: str) -> None:
    envelope = envelope_for(corrupt_export, "wrong-conversation")
    with pytest.raises(ValidationFailure, match="conversation"):
        validate_envelope(envelope, app_config)


def test_selects_latest_valid_rss_block(app_config, corrupt_export: str) -> None:
    older = corrupt_export.replace("14:44:56", "13:44:56").replace(
        "Is Life Just Different?", "Older First Pick"
    )
    combined = older + "\n\n#### ChatGPT said:\n" + corrupt_export
    run = validate_envelope(envelope_for(combined, app_config.source.conversation_id), app_config)
    assert run.items[0].title == "Is Life Just Different?"


def test_rejects_non_five_item_feed(app_config, corrupt_export: str) -> None:
    start = corrupt_export.index("    <item>\n      <title>How the World")
    end = corrupt_export.index("    </item>", start) + len("    </item>\n")
    malformed = corrupt_export[:start] + corrupt_export[end:]
    with pytest.raises(ValidationFailure, match="exactly 5"):
        validate_envelope(envelope_for(malformed, app_config.source.conversation_id), app_config)
