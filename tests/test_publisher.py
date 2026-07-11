from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from essay_picks.config import AppConfig, PublishingConfig, load_config
from essay_picks.errors import PersistenceFailure
from essay_picks.models import OutcomeCode
from essay_picks.publisher import publish_export


def git(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")
    assert executable is not None
    return subprocess.run(  # noqa: S603 - test controls every Git argument.
        [executable, *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def test_publish_export_uses_disposable_clone(
    app_config: AppConfig, corrupt_export: str, tmp_path: Path
) -> None:
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    checkout = tmp_path / "checkout"
    git("init", "--bare", str(remote))
    git("init", "--initial-branch=main", str(seed))

    publishing_config = app_config.model_copy(
        update={"publishing": PublishingConfig(repository_url=str(remote), branch="main")}
    )
    config_payload = publishing_config.model_dump(mode="json")
    config_payload["paths"] = {
        "runs": "data/runs",
        "public": "public",
        "status": ".state/status.json",
        "lock": ".state/ingest.lock",
    }
    (seed / "config.yaml").write_text(
        yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8"
    )
    git("config", "user.name", "Test User", cwd=seed)
    git("config", "user.email", "test@example.com", cwd=seed)
    git("add", "config.yaml", cwd=seed)
    git("commit", "-m", "seed", cwd=seed)
    git("remote", "add", "origin", str(remote), cwd=seed)
    git("push", "-u", "origin", "main", cwd=seed)

    local_config = load_config(seed / "config.yaml")
    result = publish_export(corrupt_export, local_config)

    assert result.code is OutcomeCode.SUCCESS
    git("clone", "--branch", "main", str(remote), str(checkout))
    assert len(list((checkout / "data" / "runs").glob("*.json"))) == 1
    assert (checkout / "public" / "feed.xml").read_text().count("<item>") == 5


def test_publish_requires_repository_url(app_config: AppConfig, corrupt_export: str) -> None:
    with pytest.raises(PersistenceFailure, match="repository_url"):
        publish_export(corrupt_export, app_config)
