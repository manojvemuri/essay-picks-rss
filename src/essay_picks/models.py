from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceKind(StrEnum):
    EXPORT = "export"
    GITHUB = "github"
    LEGACY = "legacy"
    STDIN = "stdin"


class OutcomeCode(StrEnum):
    SUCCESS = "SUCCESS"
    NO_CHANGE = "NO_CHANGE"
    RETRYABLE = "RETRYABLE"
    USER_ACTION = "USER_ACTION"
    INVALID = "INVALID"
    PUBLISH_FAILURE = "PUBLISH_FAILURE"


class OutcomeCategory(StrEnum):
    SUCCESS = "success"
    NO_CHANGE = "no_change"
    RETRYABLE = "retryable"
    USER_ACTION = "user_action"
    INVALID = "invalid"
    PUBLISH_FAILURE = "publish_failure"


class SourceEnvelope(FrozenModel):
    schema_version: int = 1
    source_kind: SourceKind
    expected_conversation_id: str
    observed_conversation_id: str
    message_id: str | None = None
    document_ordinal: int | None = Field(default=None, ge=0)
    source_timestamp_raw: str | None = None
    source_timestamp_resolved: datetime | None = None
    timestamp_basis: str | None = None
    captured_at: datetime
    body: str
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("captured_at", "source_timestamp_resolved")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @classmethod
    def create(
        cls,
        *,
        source_kind: SourceKind,
        expected_conversation_id: str,
        observed_conversation_id: str,
        body: str,
        captured_at: datetime | None = None,
        message_id: str | None = None,
        document_ordinal: int | None = None,
        source_timestamp_raw: str | None = None,
        source_timestamp_resolved: datetime | None = None,
        timestamp_basis: str | None = None,
    ) -> SourceEnvelope:
        captured = captured_at or datetime.now(UTC)
        return cls(
            source_kind=source_kind,
            expected_conversation_id=expected_conversation_id,
            observed_conversation_id=observed_conversation_id,
            message_id=message_id,
            document_ordinal=document_ordinal,
            source_timestamp_raw=source_timestamp_raw,
            source_timestamp_resolved=source_timestamp_resolved,
            timestamp_basis=timestamp_basis,
            captured_at=captured,
            body=body,
            raw_sha256=sha256(body.encode("utf-8")).hexdigest(),
        )


class EditorialMetadata(FrozenModel):
    author: str | None = None
    publication: str | None = None
    access_status: str | None = None
    core_idea: str | None = None
    why_it_stands_out: str | None = None
    who_should_read: str | None = None


class ArticleItem(FrozenModel):
    source_order: int = Field(ge=1)
    title: str
    original_url: str
    canonical_url: str
    guid: str
    published_at: datetime
    description: str
    categories: tuple[str, ...]
    editorial: EditorialMetadata = EditorialMetadata()

    @field_validator("published_at")
    @classmethod
    def published_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("published_at must be timezone-aware")
        return value


class ValidatedRun(FrozenModel):
    schema_version: int = 1
    canonicalization_version: int = 1
    batch_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    conversation_id: str
    message_id: str | None = None
    source_kind: SourceKind
    source_selected_at: datetime
    ingested_at: datetime
    original_rss_xml: str
    editorial_markdown: str
    reading_order: str | None = None
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: tuple[ArticleItem, ...]
    supersedes: str | None = None


class IngestResult(FrozenModel):
    code: OutcomeCode
    category: OutcomeCategory
    retryable: bool
    changed: bool
    batch_id: str | None = None
    imported_items: int = 0
    new_feed_items: int = 0
    duplicates_suppressed: int = 0
    message: str
    recovery_command: str | None = None


class StatusRecord(FrozenModel):
    schema_version: int = 1
    attempted_at: datetime
    code: OutcomeCode
    category: OutcomeCategory
    source_kind: SourceKind
    batch_id: str | None = None
    imported_items: int = 0
    new_feed_items: int = 0
    duplicates_suppressed: int = 0
    message: str
    recovery_command: str | None = None
