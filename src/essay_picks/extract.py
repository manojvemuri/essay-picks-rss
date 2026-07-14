from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from xml.etree.ElementTree import Element

import bleach
from defusedxml import ElementTree as SafeElementTree

from essay_picks.canonical import canonicalize_url, validate_public_https_url
from essay_picks.config import AppConfig
from essay_picks.errors import ValidationFailure
from essay_picks.models import (
    ArticleItem,
    EditorialMetadata,
    SourceEnvelope,
    SourceKind,
    ValidatedRun,
)

FENCE_RE = re.compile(r"```[^\n]*\n(?P<content>.*?)```", re.DOTALL)
RSS_HEADING_RE = re.compile(r"(?im)^##\s+RSS-ready feed\s*$")
MARKDOWN_URL_RE = re.compile(r"\((https://[^)\s]+)\)")
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\([^)]+\)")
ARTICLE_HEADING_RE = re.compile(r"(?m)^##\s+\d+\.\s+[\"“]?(?P<title>.+?)[\"”]?\s*$")
CONVERSATION_RE = re.compile(r"https://chatgpt\.com/c/(?P<id>[0-9a-fA-F-]{36})")


@dataclass(frozen=True)
class RssCandidate:
    xml: str
    fence_start: int
    heading_start: int
    editorial_start: int


def validate_envelope(envelope: SourceEnvelope, config: AppConfig) -> ValidatedRun:
    """Convert an untrusted source envelope into a fully validated immutable run."""
    _validate_source_boundary(envelope, config)
    candidate = _select_candidate(envelope, config)
    raw_editorial_markdown = envelope.body[
        candidate.editorial_start : candidate.heading_start
    ].strip()
    editorial_markdown = _sanitize_editorial_markdown(raw_editorial_markdown)
    reading_order = _extract_reading_order(editorial_markdown)
    source_selected_at, items = _parse_rss(
        candidate.xml,
        config,
        editorial_markdown,
        narrative_markdown=raw_editorial_markdown,
    )
    batch_id = _semantic_batch_id(
        conversation_id=config.source.conversation_id,
        selected_at=source_selected_at,
        items=items,
    )
    return ValidatedRun(
        batch_id=batch_id,
        conversation_id=config.source.conversation_id,
        message_id=envelope.message_id,
        source_kind=envelope.source_kind,
        source_selected_at=source_selected_at,
        ingested_at=envelope.captured_at.astimezone(UTC),
        original_rss_xml=candidate.xml.strip(),
        editorial_markdown=editorial_markdown,
        reading_order=reading_order,
        raw_sha256=envelope.raw_sha256,
        items=items,
    )


def _validate_source_boundary(envelope: SourceEnvelope, config: AppConfig) -> None:
    source_bytes = len(envelope.body.encode("utf-8"))
    if source_bytes > config.limits.max_source_bytes:
        raise ValidationFailure("Source exceeds the configured size limit", code="SOURCE_TOO_LARGE")
    if envelope.expected_conversation_id != config.source.conversation_id:
        raise ValidationFailure(
            "Expected conversation does not match configuration", code="WRONG_CONVERSATION"
        )
    if envelope.observed_conversation_id != config.source.conversation_id:
        raise ValidationFailure(
            "Observed conversation does not match configuration", code="WRONG_CONVERSATION"
        )
    discovered = {match.group("id") for match in CONVERSATION_RE.finditer(envelope.body)}
    if discovered and discovered != {config.source.conversation_id}:
        raise ValidationFailure(
            "Export belongs to a different conversation", code="WRONG_CONVERSATION"
        )


def _select_candidate(envelope: SourceEnvelope, config: AppConfig) -> RssCandidate:
    candidates: list[RssCandidate] = []
    for fence in FENCE_RE.finditer(envelope.body):
        content = fence.group("content").strip()
        if not re.search(r"<rss(?:\s|>)", content, flags=re.IGNORECASE):
            continue
        heading_matches = list(RSS_HEADING_RE.finditer(envelope.body, 0, fence.start()))
        if not heading_matches:
            raise ValidationFailure(
                "RSS block is missing its RSS-ready feed heading", code="AMBIGUOUS_SOURCE"
            )
        heading = heading_matches[-1]
        next_heading = RSS_HEADING_RE.search(envelope.body, heading.end(), fence.start())
        if next_heading is not None:
            raise ValidationFailure("RSS block association is ambiguous", code="AMBIGUOUS_SOURCE")

        marker = envelope.body.rfind(f"**[{config.source.task_marker}]**", 0, heading.start())
        if marker < 0:
            marker = envelope.body.rfind("#### ChatGPT said:", 0, heading.start())
        if marker < 0:
            if envelope.source_kind is SourceKind.EXPORT:
                raise ValidationFailure(
                    "Export RSS block is not associated with the scheduled task",
                    code="AMBIGUOUS_SOURCE",
                )
            marker = 0
        candidates.append(
            RssCandidate(
                xml=content,
                fence_start=fence.start(),
                heading_start=heading.start(),
                editorial_start=marker,
            )
        )

    if not candidates:
        raise ValidationFailure(
            "No publishable RSS block was found",
            code="NO_RSS_BLOCK",
            recovery_command="python -m essay_picks ingest --file <export.md>",
        )

    latest = candidates[-1]
    if sum(candidate.heading_start == latest.heading_start for candidate in candidates) > 1:
        raise ValidationFailure(
            "Multiple RSS blocks share one response heading", code="AMBIGUOUS_SOURCE"
        )
    if len(latest.xml.encode("utf-8")) > config.limits.max_xml_bytes:
        raise ValidationFailure(
            "RSS block exceeds the configured XML size limit", code="XML_TOO_LARGE"
        )
    return latest


def _parse_rss(
    xml_text: str,
    config: AppConfig,
    editorial_markdown: str,
    *,
    narrative_markdown: str | None = None,
) -> tuple[datetime, tuple[ArticleItem, ...]]:
    if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
        raise ValidationFailure("DTD and entity declarations are not allowed", code="UNSAFE_XML")
    try:
        root = SafeElementTree.fromstring(xml_text)
    except Exception as exc:
        raise ValidationFailure("RSS XML is malformed", code="INVALID_XML") from exc
    if root.tag != "rss" or root.attrib.get("version") != "2.0":
        raise ValidationFailure("RSS root must be version 2.0", code="INVALID_XML")
    channels = root.findall("channel")
    if len(channels) != 1:
        raise ValidationFailure("RSS must contain exactly one channel", code="INVALID_XML")
    channel = channels[0]
    source_selected_at = _parse_rfc_date(_required_text(channel, "lastBuildDate", config))
    elements = channel.findall("item")
    if len(elements) != config.limits.expected_items:
        raise ValidationFailure(
            f"RSS must contain exactly {config.limits.expected_items} items",
            code="INVALID_ITEM_COUNT",
        )

    editorial_by_url, editorial_by_title = _parse_editorial_blocks(editorial_markdown)
    parsed_items: list[ArticleItem] = []
    canonical_urls: set[str] = set()
    for order, element in enumerate(elements, start=1):
        item = _parse_item(
            element,
            order=order,
            config=config,
            editorial_by_url=editorial_by_url,
            editorial_by_title=editorial_by_title,
        )
        if item.canonical_url in canonical_urls:
            raise ValidationFailure("RSS contains duplicate article URLs", code="DUPLICATE_ITEM")
        canonical_urls.add(item.canonical_url)
        parsed_items.append(item)

    narrative_urls = {
        canonicalize_url(match.group(1))
        for match in MARKDOWN_URL_RE.finditer(narrative_markdown or editorial_markdown)
        if _is_candidate_article_url(match.group(1))
    }
    if narrative_urls and narrative_urls != canonical_urls:
        raise ValidationFailure(
            "Editorial narrative and RSS disagree on the selected article URLs",
            code="NARRATIVE_RSS_MISMATCH",
        )
    return source_selected_at, tuple(parsed_items)


def _sanitize_editorial_markdown(value: str) -> str:
    """Retain editorial prose and emphasis while removing HTML, images, and embedded links."""
    without_images = MARKDOWN_IMAGE_RE.sub(lambda match: match.group(1), value)
    without_links = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), without_images)
    return bleach.clean(without_links, tags=set(), attributes={}, strip=True).strip()


def _parse_item(
    element: Element,
    *,
    order: int,
    config: AppConfig,
    editorial_by_url: dict[str, EditorialMetadata],
    editorial_by_title: dict[str, EditorialMetadata],
) -> ArticleItem:
    title = _required_text(element, "title", config)
    original_url = _required_text(element, "link", config)
    validate_public_https_url(original_url)
    canonical_url = canonicalize_url(original_url)
    guid_element = element.find("guid")
    if guid_element is None or guid_element.attrib.get("isPermaLink", "false").lower() != "true":
        raise ValidationFailure("Item GUID must be an explicit permalink", code="INVALID_GUID")
    guid = (guid_element.text or "").strip()
    validate_public_https_url(guid)
    if canonicalize_url(guid) != canonical_url:
        raise ValidationFailure(
            "Item GUID must match the canonical article URL", code="INVALID_GUID"
        )
    published_at = _parse_rfc_date(_required_text(element, "pubDate", config))
    description = _required_text(element, "description", config)
    categories = tuple(
        text for category in element.findall("category") if (text := (category.text or "").strip())
    )
    if not categories:
        raise ValidationFailure("Each item requires at least one category", code="INVALID_ITEM")
    for category in categories:
        _check_field_length(category, config)

    editorial = editorial_by_url.get(canonical_url)
    if editorial is None:
        editorial = editorial_by_title.get(_normalize_title(title), EditorialMetadata())
    return ArticleItem(
        source_order=order,
        title=title,
        original_url=original_url,
        canonical_url=canonical_url,
        guid=guid,
        published_at=published_at,
        description=description,
        categories=categories,
        editorial=editorial,
    )


def _required_text(element: Element, name: str, config: AppConfig) -> str:
    child = element.find(name)
    value = (child.text or "").strip() if child is not None else ""
    if not value:
        raise ValidationFailure(f"Missing required RSS field: {name}", code="INVALID_ITEM")
    _check_field_length(value, config)
    return value


def _check_field_length(value: str, config: AppConfig) -> None:
    if len(value) > config.limits.max_field_characters:
        raise ValidationFailure("RSS field exceeds configured length limit", code="FIELD_TOO_LARGE")


def _parse_rfc_date(value: str) -> datetime:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError) as exc:
        raise ValidationFailure(f"Invalid RFC date: {value}", code="INVALID_DATE") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _semantic_batch_id(
    *, conversation_id: str, selected_at: datetime, items: tuple[ArticleItem, ...]
) -> str:
    payload = {
        "canonicalization_version": 1,
        "conversation_id": conversation_id,
        "selected_at": selected_at.isoformat(),
        "items": [
            {
                "order": item.source_order,
                "title": item.title,
                "url": item.canonical_url,
                "guid": canonicalize_url(item.guid),
                "published_at": item.published_at.isoformat(),
                "description": item.description,
                "categories": list(item.categories),
            }
            for item in items
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _parse_editorial_blocks(
    markdown: str,
) -> tuple[dict[str, EditorialMetadata], dict[str, EditorialMetadata]]:
    matches = list(ARTICLE_HEADING_RE.finditer(markdown))
    by_url: dict[str, EditorialMetadata] = {}
    by_title: dict[str, EditorialMetadata] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        block = markdown[match.end() : end]
        metadata_line = re.search(r"(?m)^\*\*(.+?)\*\*\s*$", block)
        author: str | None = None
        publication: str | None = None
        if metadata_line:
            pieces = [piece.strip() for piece in metadata_line.group(1).split("—")]
            if len(pieces) >= 2:
                author, publication = pieces[0], pieces[1]
        editorial = EditorialMetadata(
            author=author,
            publication=publication,
            access_status=_extract_label(block, "Access"),
            core_idea=_extract_label(block, "Core idea"),
            why_it_stands_out=_extract_label(block, "Why it stands out"),
            who_should_read=_extract_label(block, "Who should read it"),
        )
        title_key = _normalize_title(match.group("title"))
        by_title[title_key] = editorial
        for link in MARKDOWN_URL_RE.findall(block):
            if _is_candidate_article_url(link):
                by_url[canonicalize_url(link)] = editorial
    return by_url, by_title


def _extract_label(block: str, label: str) -> str | None:
    pattern = re.compile(rf"(?ims)^\*\*{re.escape(label)}:\*\*\s*(.+?)(?=\n\s*\n|\n---|\Z)")
    match = pattern.search(block)
    return " ".join(match.group(1).split()) if match else None


def _extract_reading_order(markdown: str) -> str | None:
    match = re.search(r"(?ims)^##\s+Suggested reading order\s*$\s*(.+?)\Z", markdown)
    return " ".join(match.group(1).split()) if match else None


def _normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _is_candidate_article_url(value: str) -> bool:
    try:
        validate_public_https_url(value)
    except ValidationFailure:
        return False
    return "chatgpt.com" not in value.lower() and "example.com" not in value.lower()
