from __future__ import annotations

from datetime import UTC, datetime

from filelock import FileLock, Timeout

from essay_picks.config import AppConfig
from essay_picks.errors import PersistenceFailure, ValidationFailure
from essay_picks.extract import validate_envelope
from essay_picks.models import (
    IngestResult,
    OutcomeCategory,
    OutcomeCode,
    SourceEnvelope,
    StatusRecord,
)
from essay_picks.render import build_projections, install_projections
from essay_picks.repository import RunRepository, save_status


class IngestionService:
    """Coordinate fail-closed validation, append-only history, and public projections."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.repository = RunRepository(config)

    def ingest(self, envelope: SourceEnvelope) -> IngestResult:
        self.config.paths.lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(self.config.paths.lock, timeout=0):
                return self._ingest_locked(envelope)
        except Timeout:
            result = IngestResult(
                code=OutcomeCode.RETRYABLE,
                category=OutcomeCategory.RETRYABLE,
                retryable=True,
                changed=False,
                message="Another import is already in progress.",
                recovery_command="python -m essay_picks status",
            )
            self._record_status(envelope, result)
            return result

    def _ingest_locked(self, envelope: SourceEnvelope) -> IngestResult:
        try:
            run = validate_envelope(envelope, self.config)
        except ValidationFailure as exc:
            category = OutcomeCategory.RETRYABLE if exc.retryable else OutcomeCategory.INVALID
            code = OutcomeCode.RETRYABLE if exc.retryable else OutcomeCode.INVALID
            result = IngestResult(
                code=code,
                category=category,
                retryable=exc.retryable,
                changed=False,
                message=str(exc),
                recovery_command=exc.recovery_command,
            )
            self._record_status(envelope, result)
            raise

        existing = self.repository.all_runs()
        if any(candidate.batch_id == run.batch_id for candidate in existing):
            result = IngestResult(
                code=OutcomeCode.NO_CHANGE,
                category=OutcomeCategory.NO_CHANGE,
                retryable=False,
                changed=False,
                batch_id=run.batch_id,
                imported_items=len(run.items),
                message="This ChatGPT selection run has already been imported.",
            )
            self._record_status(envelope, result)
            return result

        delivered = {item.canonical_url for candidate in existing for item in candidate.items}
        duplicates = sum(item.canonical_url in delivered for item in run.items)
        bundle = build_projections(self.config, [*existing, run])
        self.repository.save(run)
        try:
            install_projections(self.config, bundle)
        except PersistenceFailure:
            result = IngestResult(
                code=OutcomeCode.PUBLISH_FAILURE,
                category=OutcomeCategory.PUBLISH_FAILURE,
                retryable=True,
                changed=True,
                batch_id=run.batch_id,
                imported_items=len(run.items),
                new_feed_items=len(run.items) - duplicates,
                duplicates_suppressed=duplicates,
                message="The validated run was saved, but public projection installation failed.",
                recovery_command="python -m essay_picks render",
            )
            self._record_status(envelope, result)
            raise

        result = IngestResult(
            code=OutcomeCode.SUCCESS,
            category=OutcomeCategory.SUCCESS,
            retryable=False,
            changed=True,
            batch_id=run.batch_id,
            imported_items=len(run.items),
            new_feed_items=len(run.items) - duplicates,
            duplicates_suppressed=duplicates,
            message="Imported the ChatGPT selection run and regenerated public artifacts.",
        )
        self._record_status(envelope, result)
        return result

    def render_existing(self) -> int:
        runs = self.repository.all_runs()
        install_projections(self.config, build_projections(self.config, runs))
        return len(runs)

    def validate_existing(self) -> tuple[int, int]:
        runs = self.repository.all_runs()
        bundle = build_projections(self.config, runs)
        return len(runs), len(bundle.text_files) + len(bundle.binary_files)

    def _record_status(self, envelope: SourceEnvelope, result: IngestResult) -> None:
        save_status(
            self.config,
            StatusRecord(
                attempted_at=datetime.now(UTC),
                code=result.code,
                category=result.category,
                source_kind=envelope.source_kind,
                batch_id=result.batch_id,
                imported_items=result.imported_items,
                new_feed_items=result.new_feed_items,
                duplicates_suppressed=result.duplicates_suppressed,
                message=result.message,
                recovery_command=result.recovery_command,
            ),
        )
