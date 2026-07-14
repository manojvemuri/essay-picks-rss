from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from essay_picks.errors import ConfigFailure


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChannelConfig(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    site_url: HttpUrl
    feed_url: HttpUrl
    language: str = Field(default="en-us", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2})?$")


class SourceConfig(StrictModel):
    conversation_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    task_marker: str = Field(min_length=1, max_length=100)
    timezone: str = "America/Chicago"


class LimitsConfig(StrictModel):
    expected_items: int = Field(default=5, ge=1, le=20)
    max_source_bytes: int = Field(default=524_288, ge=1024, le=10_485_760)
    max_xml_bytes: int = Field(default=131_072, ge=1024, le=2_097_152)
    max_field_characters: int = Field(default=10_000, ge=100, le=100_000)


class PathsConfig(StrictModel):
    runs: Path = Path("data/runs")
    public: Path = Path("public")
    status: Path = Path(".state/status.json")
    lock: Path = Path(".state/ingest.lock")

    def resolve_from(self, root: Path) -> PathsConfig:
        values: dict[str, Path] = {}
        for name in ("runs", "public", "status", "lock"):
            value = getattr(self, name)
            values[name] = value if value.is_absolute() else root / value
        return PathsConfig(**values)


class PublishingConfig(StrictModel):
    repository_url: str | None = None
    branch: str = Field(default="main", pattern=r"^[A-Za-z0-9._/-]+$")


class AppConfig(StrictModel):
    channel: ChannelConfig
    source: SourceConfig
    limits: LimitsConfig = LimitsConfig()
    paths: PathsConfig = PathsConfig()
    publishing: PublishingConfig = PublishingConfig()

    def resolve_paths(self, root: Path) -> AppConfig:
        return self.model_copy(update={"paths": self.paths.resolve_from(root)})


def load_config(path: Path) -> AppConfig:
    """Load and validate YAML configuration, resolving paths from the config directory."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigFailure(f"Configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigFailure(f"Configuration is not valid YAML: {path}") from exc

    if not isinstance(raw, dict):
        raise ConfigFailure("Configuration root must be a mapping")

    try:
        return AppConfig.model_validate(raw).resolve_paths(path.resolve().parent)
    except ValueError as exc:
        raise ConfigFailure(f"Configuration validation failed: {exc}") from exc
