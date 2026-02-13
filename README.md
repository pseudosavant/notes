# Notes Microblog (Minimal Static Site Generator)

This repo builds a portable `notes/` microblog into `dist/` using Python scripts run with `uv run`.

The generated HTML uses only relative internal links, so `dist/notes/` can be hosted under any path or domain without changing output.

## Authoring layout

Notes live at:

`content/<YEAR>/<NOTE_SLUG>/index.md`

Each note folder can include colocated assets (images, files, nested folders). Use relative paths in Markdown, for example:

`![Example](./sample-image.svg)`

This works in VS Code Markdown preview, on GitHub.com, and in the generated site.

## Required front matter

Each `index.md` must start with YAML front matter:

```yaml
---
title: My Note Title
date: "2026-02-13"
time: "14:37:05"
draft: false
---
```

Required fields:

- `title` (string)
- `date` (`YYYY-MM-DD`)

Optional field:

- `time` (`HH:MM` or `HH:MM:SS`) for same-day ordering precision; omitted defaults to `00:00:00`.
- `draft: true` excludes the note from output, timeline, pagination, and feeds.

The build fails with clear errors for missing/invalid required front matter in note `index.md` files.

## Raw HTML embeds

Raw HTML passthrough is supported in Markdown content. Example:

```html
<div class="embed-frame">
  <strong>Custom embed block</strong>
</div>
```

## Output layout

Build output:

- Timeline: `dist/notes/index.html`
- Pagination: `dist/notes/page/2/index.html`, `dist/notes/page/3/index.html`, ...
- Note page: `dist/notes/<YEAR>/<DATE>-<NOTE_SLUG>/index.html`
- RSS feed: `dist/notes/rss.xml`
- JSON feed: `dist/notes/feed.json`

Assets from each source note folder are copied next to that note's generated HTML so relative links keep working.

## Config

`notes.config.toml`

```toml
items_per_page = 10
site_title = "Notes"
site_url = ""
```

- `items_per_page`: timeline page size.
- `site_title`: site title used in templates and feeds.
- `site_url`: optional absolute site URL. If set, feeds use absolute URLs; if empty, feeds use relative URLs.

## Local development

Terminal A (watch + rebuild):

```bash
uv run build.py --watch
```

Terminal B (serve `dist/`):

```bash
uv run preview.py --open
```

Preview entry point is:

`http://127.0.0.1:8000/notes/`

Quick publish command (creates one short note, commits only that new file, pushes):

```bash
uv run tweet.py "Shipping a small update."
```

Optional:

```bash
uv run tweet.py --no-push "Drafting from terminal."
```

One-shot build:

```bash
uv run build.py
```

Clean build:

```bash
uv run build.py --clean
```

## Build behavior

- Notes are sorted by front matter `date` descending, then optional `time` descending, then slug (stable tiebreaker).
- Latest `items_per_page` notes render as full-content posts on the timeline.
- Pagination uses relative Newer/Older links.
- Internal HTML links emitted by the generator are relative (no `/notes/...` absolute paths).

## GitHub Pages publish flow

Workflow file: `.github/workflows/publish.yml`

On push to `main`:

1. Checkout repository.
2. Install `uv`.
3. Run `uv run build.py --clean`.
4. Configure Pages.
5. Upload `dist/notes/` as the Pages artifact.
6. Deploy with `actions/deploy-pages`.

For a project repo named `notes`, this yields the site URL path `https://<user>.github.io/notes/`.
