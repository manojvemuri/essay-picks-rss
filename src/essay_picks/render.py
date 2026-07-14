from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC
from email.utils import format_datetime
from importlib.resources import files
from pathlib import Path
from xml.etree import ElementTree

import bleach
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from markupsafe import Markup

from essay_picks.config import AppConfig
from essay_picks.errors import PersistenceFailure
from essay_picks.models import ArticleItem, ValidatedRun

ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h2",
    "h3",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
}
ALLOWED_ATTRIBUTES = {"a": ["href", "title"]}


@dataclass(frozen=True)
class DeliveredItem:
    run: ValidatedRun
    item: ArticleItem


@dataclass(frozen=True)
class ProjectionBundle:
    text_files: dict[Path, str]
    binary_files: dict[Path, bytes]


def safe_markdown(markdown: str) -> Markup:
    renderer = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    rendered = renderer.render(markdown)
    cleaned = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols={"https"},
        strip=True,
    )
    return Markup(cleaned)  # noqa: S704 - Bleach sanitizes the rendered HTML above.


def build_projections(config: AppConfig, runs: list[ValidatedRun]) -> ProjectionBundle:
    """Build every public artifact in memory without mutating the filesystem."""
    ordered_runs = sorted(runs, key=lambda run: (run.source_selected_at, run.batch_id))
    delivered, delivery_flags = _delivery_projection(ordered_runs)
    # RSS is an append-only delivery projection: retain every unique article while
    # presenting the newest runs first and preserving rank within each run.
    deliveries_by_run: dict[str, list[DeliveredItem]] = {}
    for delivery in delivered:
        deliveries_by_run.setdefault(delivery.run.batch_id, []).append(delivery)
    newest_delivered = [
        delivery
        for run in reversed(ordered_runs)
        for delivery in deliveries_by_run.get(run.batch_id, [])
    ]
    newest_runs = list(reversed(ordered_runs))
    environment = _template_environment()
    common = {
        "config": config,
        "runs": newest_runs,
        "latest_run": newest_runs[0] if newest_runs else None,
        "delivery_flags": delivery_flags,
        "safe_markdown": safe_markdown,
        "feed_count": len(newest_delivered),
        "last_updated": newest_runs[0].source_selected_at if newest_runs else None,
    }

    index = environment.get_template("index.html").render(
        **common,
        asset_prefix="",
        root_prefix="",
        page_name="home",
        page_title=config.channel.title,
    )
    archive = environment.get_template("archive.html").render(
        **common,
        asset_prefix="../",
        root_prefix="../",
        page_name="archive",
        page_title=f"Archive · {config.channel.title}",
    )
    about = environment.get_template("about.html").render(
        **common,
        asset_prefix="../",
        root_prefix="../",
        page_name="about",
        page_title=f"About · {config.channel.title}",
    )
    feed = _render_feed(config, newest_delivered, newest_runs)

    static_root = files("essay_picks").joinpath("static")
    binary_files: dict[Path, bytes] = {}
    fonts = static_root.joinpath("fonts")
    if fonts.is_dir():
        for font in fonts.iterdir():
            if font.is_file():
                binary_files[Path("assets/fonts") / font.name] = font.read_bytes()
    return ProjectionBundle(
        text_files={
            Path("index.html"): index,
            Path("archive/index.html"): archive,
            Path("about/index.html"): about,
            Path("feed.xml"): feed,
            Path("assets/style.css"): static_root.joinpath("style.css").read_text(encoding="utf-8"),
        },
        binary_files=binary_files,
    )


def install_projections(config: AppConfig, bundle: ProjectionBundle) -> None:
    """Replace the complete public projection directory with rollback on failure."""
    target = config.paths.public
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
    backup = target.parent / f".{target.name}.backup"
    try:
        for relative, text_content in bundle.text_files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text_content, encoding="utf-8", newline="\n")
        for relative, binary_content in bundle.binary_files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(binary_content)
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            os.replace(target, backup)
        os.replace(staging, target)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception as exc:
        if not target.exists() and backup.exists():
            os.replace(backup, target)
        shutil.rmtree(staging, ignore_errors=True)
        raise PersistenceFailure("Failed to atomically install public projections") from exc


def _delivery_projection(
    runs: list[ValidatedRun],
) -> tuple[list[DeliveredItem], dict[str, bool]]:
    seen: set[str] = set()
    delivered: list[DeliveredItem] = []
    flags: dict[str, bool] = {}
    for run in runs:
        for item in sorted(run.items, key=lambda candidate: candidate.source_order):
            duplicate = item.canonical_url in seen
            flags[f"{run.batch_id}|{item.canonical_url}"] = duplicate
            if not duplicate:
                seen.add(item.canonical_url)
                delivered.append(DeliveredItem(run=run, item=item))
    return delivered, flags


def _render_feed(
    config: AppConfig,
    delivered: list[DeliveredItem],
    newest_runs: list[ValidatedRun],
) -> str:
    rss = ElementTree.Element("rss", {"version": "2.0"})
    channel = ElementTree.SubElement(rss, "channel")
    _subelement(channel, "title", config.channel.title)
    _subelement(channel, "link", str(config.channel.site_url))
    _subelement(channel, "description", config.channel.description)
    _subelement(channel, "language", config.channel.language)
    if newest_runs:
        _subelement(
            channel,
            "lastBuildDate",
            format_datetime(newest_runs[0].source_selected_at.astimezone(UTC), usegmt=True),
        )
    for delivery in delivered:
        element = ElementTree.SubElement(channel, "item")
        _subelement(element, "title", delivery.item.title)
        _subelement(element, "link", delivery.item.original_url)
        guid = _subelement(element, "guid", delivery.item.guid)
        guid.set("isPermaLink", "true")
        _subelement(
            element,
            "pubDate",
            format_datetime(delivery.item.published_at.astimezone(UTC), usegmt=True),
        )
        _subelement(element, "description", delivery.item.description)
        for category in delivery.item.categories:
            _subelement(element, "category", category)
    ElementTree.indent(rss, space="  ")
    return ElementTree.tostring(rss, encoding="unicode", xml_declaration=True) + "\n"


def _subelement(parent: ElementTree.Element, tag: str, text: str) -> ElementTree.Element:
    child = ElementTree.SubElement(parent, tag)
    child.text = text
    return child


def _template_environment() -> Environment:
    template_root = Path(__file__).parent / "templates"
    environment = Environment(
        loader=FileSystemLoader(template_root),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["safe_markdown"] = safe_markdown
    return environment
