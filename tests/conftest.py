from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from essay_picks.config import AppConfig


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "data" / "runs").mkdir(parents=True)
    (tmp_path / "public").mkdir()
    return tmp_path


@pytest.fixture
def app_config(project_root: Path) -> AppConfig:
    return AppConfig.model_validate(
        {
            "channel": {
                "title": "Manoj's Daily Essay Picks",
                "description": "Five serious articles and essays.",
                "site_url": "https://example.test/essay-picks/",
                "feed_url": "https://example.test/essay-picks/feed.xml",
                "language": "en-us",
            },
            "source": {
                "conversation_id": "6a4b19df-f410-83ea-a29d-49673df84cb6",
                "task_marker": "Daily Essay Picks",
                "timezone": "America/Chicago",
                "chrome_enabled": False,
            },
            "limits": {
                "expected_items": 5,
                "feed_items": 60,
                "max_source_bytes": 524288,
                "max_xml_bytes": 131072,
                "max_field_characters": 10000,
            },
            "paths": {
                "runs": str(project_root / "data" / "runs"),
                "public": str(project_root / "public"),
                "status": str(project_root / ".state" / "status.json"),
                "lock": str(project_root / ".state" / "ingest.lock"),
            },
        }
    )


@pytest.fixture
def corrupt_export() -> str:
    path = Path(__file__).parent / "fixtures" / "corrupted_suffix_single_rss.md"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def config_path(app_config: AppConfig, project_root: Path) -> Path:
    path = project_root / "config.yaml"
    path.write_text(
        yaml.safe_dump(app_config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return path
