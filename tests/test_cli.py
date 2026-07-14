from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from essay_picks.cli import app

runner = CliRunner()


def test_manual_cli_workflow(config_path: Path, corrupt_export: str, tmp_path: Path) -> None:
    source = tmp_path / "export.md"
    source.write_text(corrupt_export, encoding="utf-8")

    imported = runner.invoke(
        app,
        ["ingest", "--config", str(config_path), "--file", str(source)],
    )
    assert imported.exit_code == 0, imported.output
    assert '"code": "SUCCESS"' in imported.output

    status = runner.invoke(app, ["status", "--config", str(config_path)])
    assert status.exit_code == 0
    assert '"code": "SUCCESS"' in status.output

    validated = runner.invoke(app, ["validate", "--config", str(config_path)])
    assert validated.exit_code == 0
    assert '"runs": 1' in validated.output

    rendered = runner.invoke(app, ["render", "--config", str(config_path)])
    assert rendered.exit_code == 0
    assert '"runs": 1' in rendered.output


def test_cli_stdin_is_idempotent(config_path: Path, corrupt_export: str) -> None:
    first = runner.invoke(
        app,
        ["ingest", "--config", str(config_path), "--stdin"],
        input=corrupt_export,
    )
    second = runner.invoke(
        app,
        ["ingest", "--config", str(config_path), "--stdin"],
        input=corrupt_export,
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert '"code": "NO_CHANGE"' in second.output


def test_cli_rejects_ambiguous_inputs(
    config_path: Path, corrupt_export: str, tmp_path: Path
) -> None:
    source = tmp_path / "export.md"
    source.write_text(corrupt_export, encoding="utf-8")
    ambiguous = runner.invoke(
        app,
        ["ingest", "--config", str(config_path), "--file", str(source), "--stdin"],
    )
    assert ambiguous.exit_code != 0


@pytest.mark.parametrize("source_kind", ["github", "legacy"])
def test_cli_accepts_hosted_and_legacy_transports(
    config_path: Path, corrupt_export: str, source_kind: str
) -> None:
    result = runner.invoke(
        app,
        [
            "ingest",
            "--config",
            str(config_path),
            "--stdin",
            "--source-kind",
            source_kind,
        ],
        input=corrupt_export,
    )

    assert result.exit_code == 0, result.output
    assert '"code": "SUCCESS"' in result.output


def test_status_before_first_import(config_path: Path) -> None:
    result = runner.invoke(app, ["status", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "NEVER_RUN" in result.output
