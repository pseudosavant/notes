#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"


class TweetError(Exception):
    pass


def log_status(message: str) -> None:
    timestamp = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def ordinal_suffix(day: int) -> str:
    if 11 <= (day % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def base_title_for_date(note_date: dt.date) -> str:
    month = note_date.strftime("%B")
    day = note_date.day
    return f"{month} {day}{ordinal_suffix(day)} Note"


def parse_title_and_date(markdown_text: str) -> tuple[str | None, str | None]:
    if not markdown_text.startswith("---"):
        return None, None
    block = re.search(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", markdown_text, re.DOTALL)
    if not block:
        return None, None
    frontmatter = block.group(1)

    title_match = re.search(r"(?m)^title:\s*(.+?)\s*$", frontmatter)
    date_match = re.search(r'(?m)^date:\s*"?(\d{4}-\d{2}-\d{2})"?\s*$', frontmatter)

    title_value = title_match.group(1).strip() if title_match else None
    if title_value and (
        (title_value.startswith('"') and title_value.endswith('"'))
        or (title_value.startswith("'") and title_value.endswith("'"))
    ):
        title_value = title_value[1:-1]
        title_value = title_value.replace('\\"', '"').replace("\\'", "'")

    date_value = date_match.group(1) if date_match else None
    return title_value, date_value


def pick_title(note_date: dt.date) -> str:
    base_title = base_title_for_date(note_date)
    date_str = note_date.isoformat()
    year_dir = CONTENT_DIR / note_date.strftime("%Y")
    if not year_dir.exists():
        return base_title

    pattern = re.compile(rf"^{re.escape(base_title)}(?: \((\d+)\))?$")
    highest = 0

    for markdown_path in year_dir.glob("*/index.md"):
        text = markdown_path.read_text(encoding="utf-8")
        existing_title, existing_date = parse_title_and_date(text)
        if existing_date != date_str or not existing_title:
            continue
        match = pattern.match(existing_title)
        if not match:
            continue
        seq = int(match.group(1)) if match.group(1) else 1
        highest = max(highest, seq)

    if highest <= 0:
        return base_title
    return f"{base_title} ({highest + 1})"


def slugify(text: str) -> str:
    value = text.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "note"


def truncate(text: str, length: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= length:
        return clean
    return clean[: length - 3].rstrip() + "..."


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def choose_slug_and_path(now: dt.datetime, body_text: str) -> tuple[str, Path]:
    year = now.strftime("%Y")
    base = slugify(truncate(body_text, 48))
    prefix = now.strftime("%m%d-%H%M%S")
    slug = f"{prefix}-{base}"
    note_dir = CONTENT_DIR / year / slug

    n = 2
    while note_dir.exists():
        slug = f"{prefix}-{base}-{n}"
        note_dir = CONTENT_DIR / year / slug
        n += 1

    return slug, note_dir / "index.md"


def build_markdown(
    title: str,
    date_str: str,
    time_str: str,
    body_text: str,
    image_filename: str | None = None,
    alt_text: str | None = None,
    draft: bool = False,
) -> str:
    front_matter = (
        "---\n"
        f"title: {yaml_quote(title)}\n"
        f'date: "{date_str}"\n'
        f'time: "{time_str}"\n'
    )
    if draft:
        front_matter += "draft: true\n"
    front_matter += "---\n\n"
    markdown_body = f"{body_text}\n"
    if image_filename:
        resolved_alt = (alt_text or "").strip() or image_filename
        markdown_body += f"\n![{resolved_alt}](./{image_filename})\n"
    return front_matter + markdown_body


def run_git(args: list[str]) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr if stderr else stdout
        raise TweetError(f"git {' '.join(args)} failed: {detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a short note (optionally with embed HTML and image), then stage/commit/push only those new files."
    )
    parser.add_argument(
        "positional_text",
        nargs="?",
        help='Optional tweet text (positional form). Example: uv run tweet.py "Shipping the fix now."',
    )
    parser.add_argument(
        "--text",
        help="Optional tweet text (flag form). Can be used instead of positional text.",
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        help="Optional path to image file to include in the post.",
    )
    parser.add_argument(
        "alt_text",
        nargs="?",
        help="Optional image alt text (used only when image_path is provided). Defaults to the image filename.",
    )
    parser.add_argument(
        "--text-file",
        help="Optional path to a text/HTML file to append after the main text body.",
    )
    parser.add_argument(
        "--title",
        help="Optional note title. If omitted, a date-based title is generated.",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Create and commit the note, but do not run git push.",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Include draft: true in front matter.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_status("Starting tweet publish flow")

    body_parts: list[str] = []
    positional_text = (args.positional_text or "").strip()
    if positional_text:
        body_parts.append(positional_text)

    flag_text = (args.text or "").strip()
    if flag_text:
        body_parts.append(flag_text)

    if args.text_file:
        log_status("Reading --text-file content")
        text_file = Path(args.text_file).expanduser()
        if not text_file.is_file():
            print(f"Text file not found: {text_file}", file=sys.stderr)
            return 1
        try:
            appended_text = text_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"Failed to read text file: {exc}", file=sys.stderr)
            return 1
        if appended_text:
            body_parts.append(appended_text)

    body_text = "\n\n".join(body_parts)
    if not body_text:
        print("Tweet text cannot be empty. Provide --text, --text-file, or positional text.", file=sys.stderr)
        return 1

    source_image: Path | None = None
    if args.image_path:
        log_status("Validating image path")
        source_image = Path(args.image_path).expanduser()
        if not source_image.is_file():
            print(f"Image file not found: {source_image}", file=sys.stderr)
            return 1

    now = dt.datetime.now()
    date_str = now.date().isoformat()
    time_str = now.strftime("%H:%M:%S")
    title = (args.title or "").strip() or pick_title(now.date())

    slug, markdown_path = choose_slug_and_path(now, body_text)
    note_dir = markdown_path.parent
    note_dir.mkdir(parents=True, exist_ok=True)
    log_status(f"Preparing note folder {note_dir.relative_to(ROOT).as_posix()}")

    image_name: str | None = None
    image_target: Path | None = None
    image_alt_text: str | None = None
    if source_image:
        image_name = source_image.name
        image_target = note_dir / image_name
        n = 2
        while image_target.exists():
            image_name = f"{source_image.stem}-{n}{source_image.suffix}"
            image_target = note_dir / image_name
            n += 1

        image_alt_text = (args.alt_text or "").strip() or image_name

        try:
            log_status(f"Copying image to {image_target.relative_to(ROOT).as_posix()}")
            shutil.copy2(source_image, image_target)
        except OSError as exc:
            print(f"Failed to copy image: {exc}", file=sys.stderr)
            return 1

    log_status(f"Writing note markdown {markdown_path.relative_to(ROOT).as_posix()}")
    markdown_path.write_text(
        build_markdown(title, date_str, time_str, body_text, image_name, image_alt_text, draft=args.draft),
        encoding="utf-8",
    )

    rel_markdown_path = markdown_path.relative_to(ROOT).as_posix()
    rel_image_path = image_target.relative_to(ROOT).as_posix() if image_target else None
    commit_message = f"tweet: {date_str} {slug}"
    changed_paths = [rel_markdown_path]
    if rel_image_path:
        changed_paths.append(rel_image_path)

    try:
        log_status("Staging files")
        run_git(["add", "--", *changed_paths])
        log_status(f"Creating commit '{commit_message}'")
        run_git(["commit", "--only", "-m", commit_message, "--", *changed_paths])
        if not args.no_push:
            log_status("Pushing to remote")
            run_git(["push"])
            log_status("Push completed")
        else:
            log_status("Skipping push (--no-push)")
    except TweetError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if rel_image_path:
        print(f"Published {rel_markdown_path} with image {rel_image_path}")
    else:
        print(f"Published {rel_markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
