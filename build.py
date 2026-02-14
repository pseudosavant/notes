#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "python-frontmatter",
#   "markdown",
#   "pymdown-extensions",
#   "jinja2",
#   "watchdog",
# ]
# ///

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import posixpath
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import frontmatter
import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
CONFIG_PATH = ROOT / "notes.config.toml"

DIST_DIR = ROOT / "dist"
NOTES_OUT_DIR = DIST_DIR / "notes"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_PATTERN = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")
URL_ATTR_PATTERN = re.compile(r'(?P<attr>\b(?:href|src))="(?P<url>[^"]+)"')
LOGO_ASSET_CANDIDATES = ["pseudosavant-icon.png", "pseudosavant-icon.svg"]


class BuildError(Exception):
    pass


@dataclass
class SiteConfig:
    items_per_page: int = 10
    site_url: str = ""
    site_title: str = "Notes"


@dataclass
class Note:
    source_markdown: Path
    source_dir: Path
    slug: str
    title: str
    date: dt.date
    time: dt.time
    date_str: str
    time_str: str
    has_time: bool
    published_at: dt.datetime
    content_html: str
    note_rel_dir: str

    @property
    def out_dir(self) -> Path:
        return DIST_DIR / self.note_rel_dir


def rel_path(from_dir: str, target: str, is_dir: bool) -> str:
    value = posixpath.relpath(target, from_dir)
    if value == ".":
        return "./"
    if not value.startswith("."):
        value = f"./{value}"
    if is_dir and not value.endswith("/"):
        value = f"{value}/"
    return value


def normalize_site_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    return value.rstrip("/") + "/"


def notes_base_url(site_url: str) -> str:
    if not site_url:
        return ""
    normalized = normalize_site_url(site_url)
    if normalized.rstrip("/").endswith("/notes"):
        return normalized
    return urljoin(normalized, "notes/")


def is_relative_url(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    if lowered.startswith(("#", "/", "//", "http://", "https://", "mailto:", "tel:", "data:")):
        return False
    return True


def join_relative_url(base_href: str, value: str) -> str:
    parts = urlsplit(value)
    path = parts.path
    if not path:
        return value

    base = base_href if base_href.endswith("/") else f"{base_href}/"
    joined_path = posixpath.normpath(posixpath.join(base, path))
    if path.endswith("/") and not joined_path.endswith("/"):
        joined_path = f"{joined_path}/"

    if not joined_path.startswith("."):
        joined_path = f"./{joined_path}"
    return urlunsplit((parts.scheme, parts.netloc, joined_path, parts.query, parts.fragment))


def rewrite_relative_urls(html: str, base_href: str) -> str:
    def replace(match: re.Match[str]) -> str:
        attr = match.group("attr")
        current = match.group("url")
        if not is_relative_url(current):
            return match.group(0)
        rewritten = join_relative_url(base_href, current)
        return f'{attr}="{rewritten}"'

    return URL_ATTR_PATTERN.sub(replace, html)


def read_config(config_path: Path) -> SiteConfig:
    cfg = SiteConfig()
    if not config_path.exists():
        return cfg
    if tomllib is None:  # pragma: no cover
        raise BuildError("Python 3.11+ is required for TOML config parsing.")

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BuildError(f"Failed to parse config file {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise BuildError(f"Config root must be a TOML table in {config_path}.")

    if "items_per_page" in data:
        items_per_page = data["items_per_page"]
        if not isinstance(items_per_page, int) or items_per_page <= 0:
            raise BuildError("Config key `items_per_page` must be a positive integer.")
        cfg.items_per_page = items_per_page

    if "site_url" in data:
        site_url = data["site_url"]
        if not isinstance(site_url, str):
            raise BuildError("Config key `site_url` must be a string.")
        cfg.site_url = normalize_site_url(site_url)

    if "site_title" in data:
        site_title = data["site_title"]
        if not isinstance(site_title, str) or not site_title.strip():
            raise BuildError("Config key `site_title` must be a non-empty string.")
        cfg.site_title = site_title.strip()

    return cfg


def markdown_to_html(md_text: str) -> str:
    return markdown.markdown(
        md_text,
        extensions=["fenced_code", "sane_lists", "smarty", "pymdownx.tilde"],
        output_format="html5",
    )


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in {"1", "true", "yes", "on"}
    return False


def normalize_date(value: Any) -> tuple[dt.date, str]:
    if isinstance(value, dt.datetime):
        if value.time() != dt.time(0, 0):
            raise ValueError("must be YYYY-MM-DD (date only; put time in `time` field)")
        date_obj = value.date()
        date_str = date_obj.isoformat()
    elif isinstance(value, dt.date):
        date_obj = value
        date_str = date_obj.isoformat()
    elif isinstance(value, str):
        if not DATE_PATTERN.match(value):
            raise ValueError("must be YYYY-MM-DD")
        date_obj = dt.date.fromisoformat(value)
        date_str = value
    else:
        raise ValueError("must be a string in YYYY-MM-DD format")
    return date_obj, date_str


def normalize_time(value: Any) -> tuple[dt.time, str]:
    if isinstance(value, dt.datetime):
        time_obj = value.time()
    elif isinstance(value, dt.time):
        time_obj = value
    elif isinstance(value, str):
        if not TIME_PATTERN.match(value):
            raise ValueError("must be HH:MM or HH:MM:SS")
        try:
            time_obj = dt.time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("must be HH:MM or HH:MM:SS") from exc
    else:
        raise ValueError("must be a string in HH:MM or HH:MM:SS format")

    if time_obj.tzinfo is not None:
        raise ValueError("must not include timezone")
    if time_obj.microsecond != 0:
        raise ValueError("must not include sub-second precision")

    normalized = dt.time(time_obj.hour, time_obj.minute, time_obj.second)
    return normalized, normalized.isoformat()


def parse_note(markdown_path: Path, include_drafts: bool = False) -> tuple[Note | None, str | None]:
    raw = markdown_path.read_text(encoding="utf-8")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    if not raw.startswith("---"):
        return None, "missing YAML front matter at top of file"

    try:
        post = frontmatter.loads(raw)
    except Exception as exc:
        return None, f"invalid front matter: {exc}"

    meta = post.metadata or {}
    title = meta.get("title")
    date_value = meta.get("date")
    time_value = meta.get("time")

    if not isinstance(title, str) or not title.strip():
        return None, "missing required `title` field"
    if date_value is None:
        return None, "missing required `date` field"

    try:
        date_obj, date_str = normalize_date(date_value)
    except Exception as exc:
        return None, f"invalid `date` field: {exc}"

    if time_value is None:
        time_obj = dt.time(0, 0, 0)
        time_str = "00:00:00"
        has_time = False
    else:
        try:
            time_obj, time_str = normalize_time(time_value)
            has_time = True
        except Exception as exc:
            return None, f"invalid `time` field: {exc}"

    if to_bool(meta.get("draft", False)) and not include_drafts:
        return None, None

    slug = markdown_path.parent.name
    year = date_str[:4]
    note_rel_dir = f"notes/{year}/{date_str}-{slug}"

    return (
        Note(
            source_markdown=markdown_path,
            source_dir=markdown_path.parent,
            slug=slug,
            title=title.strip(),
            date=date_obj,
            time=time_obj,
            date_str=date_str,
            time_str=time_str,
            has_time=has_time,
            published_at=dt.datetime.combine(date_obj, time_obj),
            content_html=markdown_to_html(post.content),
            note_rel_dir=note_rel_dir,
        ),
        None,
    )


def discover_notes(include_drafts: bool = False) -> list[Note]:
    if not CONTENT_DIR.exists():
        return []

    candidates = sorted(CONTENT_DIR.glob("*/*/index.md"))
    notes: list[Note] = []
    errors: list[str] = []

    seen_rel_dirs: dict[str, Path] = {}

    for markdown_path in candidates:
        note, error = parse_note(markdown_path, include_drafts=include_drafts)
        rel_path_str = markdown_path.relative_to(ROOT).as_posix()
        if error:
            errors.append(f"{rel_path_str}: {error}")
            continue
        if note is None:
            continue
        if note.note_rel_dir in seen_rel_dirs:
            first = seen_rel_dirs[note.note_rel_dir].relative_to(ROOT).as_posix()
            errors.append(
                f"{rel_path_str}: output path collision with {first} "
                f"for {note.note_rel_dir}/"
            )
            continue
        seen_rel_dirs[note.note_rel_dir] = markdown_path
        notes.append(note)

    if errors:
        details = "\n".join(f"- {line}" for line in errors)
        raise BuildError(f"Note validation failed:\n{details}")

    notes.sort(
        key=lambda n: (
            -n.date.toordinal(),
            -(n.time.hour * 3600 + n.time.minute * 60 + n.time.second),
            n.slug.lower(),
            n.note_rel_dir,
        )
    )
    return notes


def copy_note_assets(note: Note) -> None:
    note.out_dir.mkdir(parents=True, exist_ok=True)
    for child in note.source_dir.iterdir():
        if child.name == "index.md":
            continue
        dest = note.out_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, dest)


def copy_static_assets() -> None:
    assets_dir = NOTES_OUT_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if not STATIC_DIR.exists():
        return
    for child in STATIC_DIR.iterdir():
        dest = assets_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)


def get_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def page_dir_rel(page_number: int) -> str:
    if page_number == 1:
        return "notes"
    return f"notes/page/{page_number}"


def page_out_path(page_number: int) -> Path:
    if page_number == 1:
        return NOTES_OUT_DIR / "index.html"
    return NOTES_OUT_DIR / "page" / str(page_number) / "index.html"


def split_pages(notes: list[Note], items_per_page: int) -> list[list[Note]]:
    if not notes:
        return [[]]
    return [notes[i : i + items_per_page] for i in range(0, len(notes), items_per_page)]


def make_page_url(page_number: int) -> str:
    if page_number == 1:
        return "./"
    return f"./page/{page_number}/"


def feed_urls(site_url: str) -> dict[str, str]:
    notes_url = notes_base_url(site_url)
    if notes_url:
        return {
            "home": notes_url,
            "rss": urljoin(notes_url, "rss.xml"),
            "json": urljoin(notes_url, "feed.json"),
        }
    return {"home": "./", "rss": "./rss.xml", "json": "./feed.json"}


def note_url_for_feed(note: Note, site_url: str) -> str:
    rel = f"./{note.note_rel_dir.removeprefix('notes/')}/"
    notes_url = notes_base_url(site_url)
    if notes_url:
        return urljoin(notes_url, rel[2:])
    return rel


def resolve_logo_asset() -> str:
    for name in LOGO_ASSET_CANDIDATES:
        if (STATIC_DIR / name).exists():
            return f"notes/assets/{name}"
    raise BuildError(
        "Missing logo asset in static/. Expected one of: "
        + ", ".join(LOGO_ASSET_CANDIDATES)
    )


def logo_template_path(page_dir: str) -> str:
    return rel_path(page_dir, resolve_logo_asset(), is_dir=False)


def write_note_pages(env: Environment, notes: list[Note], cfg: SiteConfig, build_year: int) -> None:
    template = env.get_template("note.html")
    for note in notes:
        copy_note_assets(note)

        page_dir = note.note_rel_dir
        css_href = rel_path(page_dir, "notes/assets/style.css", is_dir=False)
        home_href = rel_path(page_dir, "notes", is_dir=True)
        rss_href = rel_path(page_dir, "notes/rss.xml", is_dir=False)
        json_href = rel_path(page_dir, "notes/feed.json", is_dir=False)
        logo_href = logo_template_path(page_dir)

        html = template.render(
            site_title=cfg.site_title,
            page_title=note.title,
            css_href=css_href,
            home_href=home_href,
            rss_href=rss_href,
            json_href=json_href,
            logo_href=logo_href,
            copyright_year=build_year,
            note=note,
        )
        output_path = note.out_dir / "index.html"
        output_path.write_text(html, encoding="utf-8")


def write_timeline_pages(
    env: Environment, notes: list[Note], cfg: SiteConfig, build_year: int
) -> None:
    template = env.get_template("timeline.html")
    pages = split_pages(notes, cfg.items_per_page)
    total_pages = len(pages)

    for page_number, notes_on_page in enumerate(pages, start=1):
        current_dir = page_dir_rel(page_number)
        page_notes: list[dict[str, Any]] = []
        for note in notes_on_page:
            href = rel_path(current_dir, note.note_rel_dir, is_dir=True)
            page_notes.append(
                {
                    "note": note,
                    "href": href,
                    "content_html": rewrite_relative_urls(note.content_html, href),
                }
            )

        newer_href = None
        if page_number > 1:
            newer_target = page_dir_rel(page_number - 1)
            newer_href = rel_path(current_dir, newer_target, is_dir=True)

        older_href = None
        if page_number < total_pages:
            older_target = page_dir_rel(page_number + 1)
            older_href = rel_path(current_dir, older_target, is_dir=True)

        css_href = rel_path(current_dir, "notes/assets/style.css", is_dir=False)
        home_href = rel_path(current_dir, "notes", is_dir=True)
        rss_href = rel_path(current_dir, "notes/rss.xml", is_dir=False)
        json_href = rel_path(current_dir, "notes/feed.json", is_dir=False)
        logo_href = logo_template_path(current_dir)

        html = template.render(
            site_title=cfg.site_title,
            page_title=cfg.site_title if page_number == 1 else f"{cfg.site_title} - Page {page_number}",
            css_href=css_href,
            home_href=home_href,
            rss_href=rss_href,
            json_href=json_href,
            logo_href=logo_href,
            copyright_year=build_year,
            notes=page_notes,
            page_number=page_number,
            total_pages=total_pages,
            newer_href=newer_href,
            older_href=older_href,
            page_url=make_page_url(page_number),
        )
        out_path = page_out_path(page_number)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")


def rfc2822_datetime(moment: dt.datetime) -> str:
    timestamp = moment.replace(tzinfo=dt.timezone.utc)
    return timestamp.strftime("%a, %d %b %Y %H:%M:%S +0000")


def write_rss(notes: list[Note], cfg: SiteConfig) -> None:
    urls = feed_urls(cfg.site_url)

    rss = ET.Element(
        "rss",
        {"version": "2.0", "xmlns:content": "http://purl.org/rss/1.0/modules/content/"},
    )
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = cfg.site_title
    ET.SubElement(channel, "link").text = urls["home"]
    ET.SubElement(channel, "description").text = f"{cfg.site_title} timeline"

    for note in notes:
        item_url = note_url_for_feed(note, cfg.site_url)
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = note.title
        ET.SubElement(item, "link").text = item_url
        guid = ET.SubElement(item, "guid")
        guid.text = item_url
        guid.set("isPermaLink", "true" if cfg.site_url else "false")
        ET.SubElement(item, "pubDate").text = rfc2822_datetime(note.published_at)
        ET.SubElement(item, "{http://purl.org/rss/1.0/modules/content/}encoded").text = (
            note.content_html
        )

    xml_text = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    (NOTES_OUT_DIR / "rss.xml").write_bytes(xml_text)


def write_json_feed(notes: list[Note], cfg: SiteConfig) -> None:
    urls = feed_urls(cfg.site_url)
    items = []
    for note in notes:
        item_url = note_url_for_feed(note, cfg.site_url)
        items.append(
            {
                "id": item_url,
                "url": item_url,
                "title": note.title,
                "date_published": f"{note.date_str}T{note.time_str}Z",
                "content_html": note.content_html,
            }
        )

    payload: dict[str, Any] = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": cfg.site_title,
        "home_page_url": urls["home"],
        "feed_url": urls["json"],
        "items": items,
    }
    (NOTES_OUT_DIR / "feed.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _handle_remove_readonly(func, path: str, exc_info) -> None:  # pragma: no cover - OS-specific
    del exc_info
    os.chmod(path, 0o700)
    func(path)


def remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for attempt in range(3):
        try:
            shutil.rmtree(path, onerror=_handle_remove_readonly)
            return
        except PermissionError as exc:
            if attempt == 2:
                raise BuildError(
                    f"Could not remove {path}. Close any program using files there and retry."
                ) from exc
            time.sleep(0.2 * (attempt + 1))


def build_site(clean_dist: bool, include_drafts: bool = False) -> None:
    cfg = read_config(CONFIG_PATH)
    build_year = dt.date.today().year

    if clean_dist:
        remove_tree(DIST_DIR)
    remove_tree(NOTES_OUT_DIR)
    NOTES_OUT_DIR.mkdir(parents=True, exist_ok=True)

    notes = discover_notes(include_drafts=include_drafts)
    env = get_environment()
    env.globals["copyright_year"] = build_year

    copy_static_assets()
    write_note_pages(env, notes, cfg, build_year=build_year)
    write_timeline_pages(env, notes, cfg, build_year=build_year)
    write_rss(notes, cfg)
    write_json_feed(notes, cfg)

    print(f"Built {len(notes)} published note(s) into {NOTES_OUT_DIR.relative_to(ROOT)}")


class DebouncedRebuilder(FileSystemEventHandler):
    def __init__(self, delay_seconds: float, callback) -> None:
        super().__init__()
        self.delay_seconds = delay_seconds
        self.callback = callback
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._running = False
        self._queued = False

    def on_any_event(self, event: FileSystemEvent) -> None:
        with self._lock:
            self._queued = True
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay_seconds, self._drain)
            self._timer.daemon = True
            self._timer.start()

    def _drain(self) -> None:
        while True:
            with self._lock:
                if self._running:
                    return
                if not self._queued:
                    return
                self._queued = False
                self._running = True
                self._timer = None

            try:
                self.callback()
            except BuildError as exc:
                print(str(exc), file=sys.stderr)
            except Exception as exc:  # pragma: no cover
                print(f"Unexpected error: {exc}", file=sys.stderr)
            finally:
                with self._lock:
                    self._running = False
                    rerun = self._queued
                if not rerun:
                    return

    def shutdown(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._queued = False


def watch(clean_dist: bool, debounce_ms: int, include_drafts: bool = False) -> None:
    def rebuild() -> None:
        print("Rebuilding...")
        build_site(clean_dist=clean_dist, include_drafts=include_drafts)

    rebuild()
    observer = Observer()
    handler = DebouncedRebuilder(delay_seconds=debounce_ms / 1000.0, callback=rebuild)

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    observer.schedule(handler, str(CONTENT_DIR), recursive=True)
    observer.start()
    print(f"Watching {CONTENT_DIR.relative_to(ROOT)} (debounce {debounce_ms}ms). Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping watch mode...")
    finally:
        handler.shutdown()
        observer.stop()
        observer.join()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the notes static site.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch content/ for changes and rebuild automatically.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe dist/ before building.",
    )
    parser.add_argument(
        "--debounce-ms",
        type=int,
        default=350,
        help="Debounce delay for watch mode in milliseconds (default: 350).",
    )
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="Include notes marked with draft: true.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.watch:
            watch(
                clean_dist=args.clean,
                debounce_ms=args.debounce_ms,
                include_drafts=args.include_drafts,
            )
        else:
            build_site(clean_dist=args.clean, include_drafts=args.include_drafts)
    except BuildError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
