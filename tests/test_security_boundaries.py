from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from essay_picks.errors import ValidationFailure
from essay_picks.extract import validate_envelope
from essay_picks.models import SourceEnvelope, SourceKind


def source_envelope(
    body: str,
    conversation_id: str,
    *,
    kind: SourceKind = SourceKind.EXPORT,
    observed: str | None = None,
    message_id: str | None = None,
) -> SourceEnvelope:
    return SourceEnvelope.create(
        source_kind=kind,
        expected_conversation_id=conversation_id,
        observed_conversation_id=observed or conversation_id,
        body=body,
        captured_at=datetime(2026, 7, 11, 16, 0, tzinfo=UTC),
        message_id=message_id,
    )


def assert_invalid(app_config, body: str, code: str) -> None:
    with pytest.raises(ValidationFailure) as captured:
        validate_envelope(source_envelope(body, app_config.source.conversation_id), app_config)
    assert captured.value.code == code


def add_doctype(text: str) -> str:
    return text.replace('<rss version="2.0">', '<!DOCTYPE rss><rss version="2.0">', 1)


def break_xml(text: str) -> str:
    return text.replace('<rss version="2.0">', '<rss version="2.0"><broken>', 1)


def change_root(text: str) -> str:
    return text.replace('<rss version="2.0">', '<rss version="1.0">', 1)


def disable_permalink(text: str) -> str:
    return text.replace('<guid isPermaLink="true">', '<guid isPermaLink="false">', 1)


def invalidate_date(text: str) -> str:
    return text.replace("Wed, 08 Jul 2026 00:00:00 GMT", "not-a-date", 1)


def remove_first_categories(text: str) -> str:
    categories = "      <category>Science</category><category>Ideas</category>"
    return text.replace(categories, "", 1)


def use_private_url(text: str) -> str:
    return text.replace(
        "https://www.quantamagazine.org/is-life-just-different-20260708/",
        "https://127.0.0.1/private",
        3,
    )


def test_source_boundaries_reject_size_observed_id_and_export_id(
    app_config, corrupt_export: str
) -> None:
    small_limit = app_config.model_copy(
        update={"limits": app_config.limits.model_copy(update={"max_source_bytes": 1024})}
    )
    with pytest.raises(ValidationFailure, match="size"):
        validate_envelope(
            source_envelope(corrupt_export, app_config.source.conversation_id), small_limit
        )

    wrong_observed = source_envelope(
        corrupt_export,
        app_config.source.conversation_id,
        observed="00000000-0000-0000-0000-000000000000",
    )
    with pytest.raises(ValidationFailure, match="Observed"):
        validate_envelope(wrong_observed, app_config)

    foreign = "https://chatgpt.com/c/00000000-0000-0000-0000-000000000000\n" + corrupt_export
    assert_invalid(app_config, foreign, "WRONG_CONVERSATION")


def test_github_missing_rss_fails_closed(app_config) -> None:
    no_rss = source_envelope(
        "completed response",
        app_config.source.conversation_id,
        kind=SourceKind.GITHUB,
    )
    with pytest.raises(ValidationFailure) as missing:
        validate_envelope(no_rss, app_config)
    assert missing.value.code == "NO_RSS_BLOCK"
    assert missing.value.retryable is False
    assert missing.value.recovery_command is not None


def test_candidate_boundary_rejects_missing_heading_shared_heading_and_oversize_xml(
    app_config, corrupt_export: str
) -> None:
    assert_invalid(
        app_config,
        corrupt_export.replace("## RSS-ready feed", "RSS-ready feed", 1),
        "AMBIGUOUS_SOURCE",
    )

    fenced = re.search(r"```\n(?P<xml><\?xml.*?)```", corrupt_export, re.DOTALL)
    assert fenced is not None
    shared_heading = corrupt_export.replace(
        fenced.group(0),
        f"{fenced.group(0)}\n\n```xml\n{fenced.group('xml')}```",
        1,
    )
    assert_invalid(app_config, shared_heading, "AMBIGUOUS_SOURCE")

    small_xml_limit = app_config.model_copy(
        update={"limits": app_config.limits.model_copy(update={"max_xml_bytes": 1024})}
    )
    with pytest.raises(ValidationFailure) as oversized:
        validate_envelope(
            source_envelope(corrupt_export, app_config.source.conversation_id),
            small_xml_limit,
        )
    assert oversized.value.code == "XML_TOO_LARGE"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (add_doctype, "UNSAFE_XML"),
        (break_xml, "INVALID_XML"),
        (change_root, "INVALID_XML"),
        (disable_permalink, "INVALID_GUID"),
        (invalidate_date, "INVALID_DATE"),
        (remove_first_categories, "INVALID_ITEM"),
        (use_private_url, "UNSAFE_URL"),
    ],
)
def test_xml_and_item_security_failures(
    app_config,
    corrupt_export: str,
    mutation: Callable[[str], str],
    code: str,
) -> None:
    assert_invalid(app_config, mutation(corrupt_export), code)


def test_rejects_duplicate_urls_guid_mismatch_large_field_and_narrative_disagreement(
    app_config, corrupt_export: str
) -> None:
    duplicate = corrupt_export.replace(
        "https://www.construction-physics.com/p/the-fall-and-rise-of-screwworm",
        "https://www.quantamagazine.org/is-life-just-different-20260708/",
    )
    assert_invalid(app_config, duplicate, "DUPLICATE_ITEM")

    mismatch = corrupt_export.replace(
        '<guid isPermaLink="true">https://www.quantamagazine.org/is-life-just-different-20260708/</guid>',
        '<guid isPermaLink="true">https://www.quantamagazine.org/another-story/</guid>',
        1,
    )
    assert_invalid(app_config, mismatch, "INVALID_GUID")

    long_title = corrupt_export.replace(
        "<title>Is Life Just Different?</title>",
        f"<title>{'X' * 101}</title>",
        1,
    )
    short_fields = app_config.model_copy(
        update={"limits": app_config.limits.model_copy(update={"max_field_characters": 100})}
    )
    with pytest.raises(ValidationFailure) as too_large:
        validate_envelope(
            source_envelope(long_title, app_config.source.conversation_id), short_fields
        )
    assert too_large.value.code == "FIELD_TOO_LARGE"

    narrative_disagreement = corrupt_export.replace(
        "## RSS-ready feed",
        "[Different article](https://www.quantamagazine.org/different-narrative-story/)\n\n"
        "## RSS-ready feed",
        1,
    )
    assert_invalid(app_config, narrative_disagreement, "NARRATIVE_RSS_MISMATCH")


def test_editorial_markdown_removes_html_images_and_embedded_links(
    app_config, corrupt_export: str
) -> None:
    injected = corrupt_export.replace(
        "## RSS-ready feed",
        "<script>not executable</script>\n"
        "![remote image](data:image/png;base64,AAAA)\n"
        "[unsafe](javascript:alert(1))\n\n## RSS-ready feed",
        1,
    )
    run = validate_envelope(
        source_envelope(injected, app_config.source.conversation_id), app_config
    )
    assert "<script>" not in run.editorial_markdown
    assert "data:image" not in run.editorial_markdown
    assert "javascript:" not in run.editorial_markdown


def test_latest_invalid_rss_fails_instead_of_falling_back(app_config, corrupt_export: str) -> None:
    older = corrupt_export.replace("14:44:56", "13:44:56")
    latest_invalid = corrupt_export.replace("Wed, 08 Jul 2026 00:00:00 GMT", "bad-date", 1)
    combined = older + "\n\n#### ChatGPT said:\n" + latest_invalid
    assert_invalid(app_config, combined, "INVALID_DATE")
