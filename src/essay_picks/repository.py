from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from essay_picks.config import AppConfig
from essay_picks.errors import PersistenceFailure
from essay_picks.models import StatusRecord, ValidatedRun


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace one UTF-8 text file on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


class RunRepository:
    """Append-only filesystem repository for validated source runs."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.runs_path = config.paths.runs

    def all_runs(self) -> list[ValidatedRun]:
        self.runs_path.mkdir(parents=True, exist_ok=True)
        runs: list[ValidatedRun] = []
        for path in sorted(self.runs_path.glob("*.json")):
            try:
                runs.append(ValidatedRun.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValidationError, ValueError) as exc:
                raise PersistenceFailure(f"Invalid immutable run record: {path}") from exc
        return sorted(runs, key=lambda run: (run.source_selected_at, run.batch_id))

    def contains(self, batch_id: str) -> bool:
        return any(run.batch_id == batch_id for run in self.all_runs())

    def save(self, run: ValidatedRun) -> Path:
        if self.contains(run.batch_id):
            raise PersistenceFailure(f"Run already exists: {run.batch_id}")
        date = run.source_selected_at.date().isoformat()
        path = self.runs_path / f"{date}-{run.batch_id[:16]}.json"
        payload = run.model_dump_json(indent=2, exclude_none=True) + "\n"
        atomic_write_text(path, payload)
        return path

    def delivered_urls(self) -> set[str]:
        return {item.canonical_url for run in self.all_runs() for item in run.items}

    def validate(self) -> int:
        return len(self.all_runs())


def save_status(config: AppConfig, status: StatusRecord) -> None:
    atomic_write_text(
        config.paths.status,
        status.model_dump_json(indent=2, exclude_none=True) + "\n",
    )


def load_status(config: AppConfig) -> dict[str, object] | None:
    try:
        raw = config.paths.status.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PersistenceFailure("Operational status file is invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise PersistenceFailure("Operational status file must contain an object")
    return parsed
