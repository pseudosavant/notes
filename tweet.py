#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"


class TweetError(Exception):
    pass


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


def build_markdown(title: str, date_str: str, time_str: str, body_text: str) -> str:
    return (
        "---\n"
        f"title: {yaml_quote(title)}\n"
        f'date: "{date_str}"\n'
        f'time: "{time_str}"\n'
        "---\n\n"
        f"{body_text}\n"
    )


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
        description="Create a short note, then stage/commit/push only that new file."
    )
    parser.add_argument(
        "text",
        nargs="+",
        help='Tweet text. Example: uv run tweet.py "Shipping the fix now."',
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Create and commit the note, but do not run git push.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    body_text = " ".join(args.text).strip()
    if not body_text:
        print("Tweet text cannot be empty.", file=sys.stderr)
        return 1

    now = dt.datetime.now()
    date_str = now.date().isoformat()
    time_str = now.strftime("%H:%M:%S")
    title = pick_title(now.date())

    slug, markdown_path = choose_slug_and_path(now, body_text)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(build_markdown(title, date_str, time_str, body_text), encoding="utf-8")

    rel_path = markdown_path.relative_to(ROOT).as_posix()
    commit_message = f"tweet: {date_str} {slug}"

    try:
        run_git(["add", "--", rel_path])
        run_git(["commit", "--only", "-m", commit_message, "--", rel_path])
        if not args.no_push:
            run_git(["push"])
    except TweetError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Published {rel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
